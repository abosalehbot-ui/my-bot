from fastapi import APIRouter, Request, Form, Query, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import hashlib
import hmac
import json
import random
import re
import secrets
import httpx
import traceback
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pydantic import BaseModel
from typing import Any, List, Optional
from werkzeug.security import check_password_hash, generate_password_hash
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

# Shared imports (no duplicate connections)
from database import db, get_next_order_id
from config import (
    BOT_TOKEN,
    OTP_MAX_ATTEMPTS,
    OTP_TTL_SECONDS,
    SECRET_TOKEN,
    STORE_SESSION_COOKIE_NAME,
    STORE_SESSION_TTL_SECONDS,
    TELEGRAM_AUTH_MAX_AGE_SECONDS,
    logger,
)

router = APIRouter()
templates = Jinja2Templates(directory='templates')

GOOGLE_CLIENT_ID = (
    '671995925834-4bf0od4fm0pkkhvkfrvqh41h6rpb574v.apps.googleusercontent.com'
)


class CartItem(BaseModel):
    stock_key: str
    price: float
    currency: str
    quantity: int


class CheckoutRequest(BaseModel):
    cart: List[CartItem]
    transaction_id: Optional[str] = ''


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return (email or '').strip().lower()


def _hash_sha256(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def hash_password(password: str) -> str:
    return generate_password_hash(password, method='pbkdf2:sha256:600000', salt_length=16)


def _is_legacy_sha256_hash(value: str) -> bool:
    return bool(value) and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value.lower())


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False

    if _is_legacy_sha256_hash(stored_hash):
        return hmac.compare_digest(stored_hash, _hash_sha256(password))

    try:
        return check_password_hash(stored_hash, password)
    except ValueError:
        return False


def check_auth(request: Request):
    incoming = request.cookies.get('admin_session') or ''
    expected = SECRET_TOKEN or ''
    return bool(incoming and expected and hmac.compare_digest(incoming, expected))


async def generate_unique_id():
    while True:
        new_id = random.randint(10000000, 99999999)
        if not await db.store_customers.find_one({'user_id': new_id}):
            return new_id


async def log_wallet_txn(email: str, amount: float, currency: str, note: str, ref: str = ''):
    await db.store_wallet_ledger.insert_one(
        {
            'email': email,
            'amount': float(amount),
            'currency': currency.upper(),
            'note': note,
            'ref': ref,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'ts': datetime.now(),
        }
    )


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get('x-forwarded-for', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    if request.client:
        return request.client.host or ''
    return ''


def _cookie_is_secure(request: Request) -> bool:
    proto = request.headers.get('x-forwarded-proto', '')
    if proto:
        return proto.split(',')[0].strip().lower() == 'https'
    return request.url.scheme == 'https'


def _store_sessions_collection():
    return db.store_sessions


def _otp_collection():
    return db.store_otp_challenges


def _session_digest(raw_token: str) -> str:
    return _hash_sha256(raw_token)


def _otp_doc_id(identifier: str, purpose: str) -> str:
    return f'{purpose}:{_normalize_email(identifier)}'


async def _set_store_session_cookie(response: JSONResponse, request: Request, user: dict):
    raw_token = secrets.token_urlsafe(48)
    now = _utcnow()
    expires_at = now + timedelta(seconds=STORE_SESSION_TTL_SECONDS)

    await _store_sessions_collection().insert_one(
        {
            '_id': _session_digest(raw_token),
            'user_id': user.get('user_id'),
            'email': user.get('email'),
            'created_at': now,
            'updated_at': now,
            'expires_at': expires_at,
            'last_seen_at': now,
            'ip_address': _client_ip(request),
            'user_agent': request.headers.get('user-agent', ''),
        }
    )

    response.set_cookie(
        key=STORE_SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        max_age=STORE_SESSION_TTL_SECONDS,
        path='/',
        samesite='lax',
        secure=_cookie_is_secure(request),
    )


async def _invalidate_current_store_session(request: Request):
    raw_token = request.cookies.get(STORE_SESSION_COOKIE_NAME)
    if not raw_token:
        return
    await _store_sessions_collection().delete_one({'_id': _session_digest(raw_token)})


async def _invalidate_store_sessions_for_user(user_id: int | None):
    if user_id is None:
        return
    await _store_sessions_collection().delete_many({'user_id': user_id})


def _clear_store_session_cookie(response: JSONResponse, request: Request):
    response.delete_cookie(
        key=STORE_SESSION_COOKIE_NAME,
        path='/',
        samesite='lax',
        secure=_cookie_is_secure(request),
    )


async def _get_store_session(request: Request, touch: bool = True) -> dict | None:
    raw_token = request.cookies.get(STORE_SESSION_COOKIE_NAME)
    if not raw_token:
        return None

    session = await _store_sessions_collection().find_one({'_id': _session_digest(raw_token)})
    if not session:
        return None

    now = _utcnow()
    expires_at = session.get('expires_at')
    if expires_at and expires_at <= now:
        await _store_sessions_collection().delete_one({'_id': session['_id']})
        return None

    if touch:
        await _store_sessions_collection().update_one(
            {'_id': session['_id']},
            {'$set': {'last_seen_at': now, 'updated_at': now}},
        )
        session['last_seen_at'] = now
        session['updated_at'] = now

    return session


async def _get_current_store_user(request: Request, touch_session: bool = True) -> dict | None:
    session = await _get_store_session(request, touch=touch_session)
    if not session:
        return None

    user = None
    user_id = session.get('user_id')
    if user_id is not None:
        user = await db.store_customers.find_one({'user_id': user_id})

    if not user and session.get('email'):
        user = await db.store_customers.find_one({'email': session['email']})

    if not user:
        await _store_sessions_collection().delete_one({'_id': session['_id']})
        return None

    if session.get('email') != user.get('email'):
        await _store_sessions_collection().update_one(
            {'_id': session['_id']},
            {'$set': {'email': user.get('email'), 'updated_at': _utcnow()}},
        )

    return user


async def _get_authenticated_email(request: Request, touch_session: bool = True) -> str | None:
    user = await _get_current_store_user(request, touch_session=touch_session)
    if not user:
        return None
    return user.get('email')


async def _create_store_auth_response(request: Request, user: dict):
    response = JSONResponse({'success': True, **get_user_data(user)})
    await _set_store_session_cookie(response, request, user)
    return response


async def _create_otp_challenge(identifier: str, purpose: str, payload: dict | None = None) -> str:
    code = f'{random.randint(0, 999999):06d}'
    now = _utcnow()
    doc_id = _otp_doc_id(identifier, purpose)
    doc = {
        '_id': doc_id,
        'email': _normalize_email(identifier),
        'purpose': purpose,
        'code_hash': _hash_sha256(code),
        'payload': payload or {},
        'attempts': 0,
        'max_attempts': OTP_MAX_ATTEMPTS,
        'created_at': now,
        'updated_at': now,
        'expires_at': now + timedelta(seconds=OTP_TTL_SECONDS),
    }
    await _otp_collection().update_one({'_id': doc_id}, {'$set': doc}, upsert=True)
    logger.warning('OTP challenge generated for %s (%s). Delivery integration is still pending. Code: %s', identifier, purpose, code)
    return code


async def _verify_otp_challenge(identifier: str, purpose: str, code: str) -> tuple[dict | None, str | None]:
    doc = await _otp_collection().find_one({'_id': _otp_doc_id(identifier, purpose)})
    if not doc:
        return None, 'Invalid verification code!'

    now = _utcnow()
    expires_at = doc.get('expires_at')
    if expires_at and expires_at <= now:
        await _otp_collection().delete_one({'_id': doc['_id']})
        return None, 'Code expired! Please try again.'

    attempts = int(doc.get('attempts', 0))
    max_attempts = int(doc.get('max_attempts', OTP_MAX_ATTEMPTS))
    if attempts >= max_attempts:
        await _otp_collection().delete_one({'_id': doc['_id']})
        return None, 'Too many invalid attempts. Please request a new code.'

    if not hmac.compare_digest(doc.get('code_hash', ''), _hash_sha256(code)):
        await _otp_collection().update_one(
            {'_id': doc['_id']},
            {'$inc': {'attempts': 1}, '$set': {'updated_at': now, 'last_attempt_at': now}},
        )
        return None, 'Invalid verification code!'

    return doc, None


async def _clear_otp_challenge(identifier: str, purpose: str):
    await _otp_collection().delete_one({'_id': _otp_doc_id(identifier, purpose)})


def _telegram_check_string(payload: dict[str, str]) -> str:
    parts = []
    for key in sorted(payload.keys()):
        if key == 'hash':
            continue
        value = payload.get(key)
        if value in (None, ''):
            continue
        parts.append(f'{key}={value}')
    return '\n'.join(parts)


def _verify_telegram_payload(payload: dict[str, str]) -> tuple[bool, str, dict[str, str] | None]:
    if not BOT_TOKEN:
        return False, 'Telegram login is not configured.', None

    telegram_id = (payload.get('id') or payload.get('tg_id') or '').strip()
    auth_hash = (payload.get('hash') or '').strip()
    auth_date = (payload.get('auth_date') or '').strip()
    if not telegram_id or not auth_hash or not auth_date:
        return False, 'Missing signed Telegram auth fields.', None

    try:
        auth_timestamp = int(auth_date)
    except ValueError:
        return False, 'Invalid Telegram auth timestamp.', None

    age_seconds = int(_utcnow().timestamp()) - auth_timestamp
    if age_seconds < 0 or age_seconds > TELEGRAM_AUTH_MAX_AGE_SECONDS:
        return False, 'Telegram auth expired. Please try again.', None

    signed_payload = {
        'id': telegram_id,
        'first_name': (payload.get('first_name') or '').strip(),
        'last_name': (payload.get('last_name') or '').strip(),
        'username': (payload.get('username') or '').strip(),
        'photo_url': (payload.get('photo_url') or '').strip(),
        'auth_date': auth_date,
        'hash': auth_hash,
    }
    secret_key = hashlib.sha256(BOT_TOKEN.encode('utf-8')).digest()
    computed_hash = hmac.new(
        secret_key,
        _telegram_check_string(signed_payload).encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(computed_hash, auth_hash):
        return False, 'Invalid Telegram login signature.', None

    first_name = signed_payload['first_name']
    last_name = signed_payload['last_name']
    full_name = ' '.join(part for part in [first_name, last_name] if part).strip()
    if not full_name:
        full_name = (payload.get('name') or signed_payload['username'] or f'Telegram User {telegram_id}').strip()

    normalized = {
        'id': telegram_id,
        'username': signed_payload['username'],
        'name': full_name,
        'photo_url': signed_payload['photo_url'],
    }
    return True, '', normalized


@router.get('/', response_class=HTMLResponse)
async def public_storefront(request: Request):
    try:
        settings = await db.settings.find_one({'_id': 'config'})
        maintenance = settings.get('maintenance', False) if settings else False

        user = await _get_current_store_user(request, touch_session=False)
        raw_categories = await db.store_categories.find().to_list(100)

        stock_keys = []
        prepared_categories = []
        for category in raw_categories:
            normalized_products = []
            for product in category.get('products') or []:
                normalized = _normalize_catalog_product(product)
                if normalized.get('stock_key'):
                    stock_keys.append(normalized['stock_key'])
                normalized_products.append(normalized)
            prepared_categories.append((category, normalized_products))

        stock_counts = await _count_stock_by_keys(stock_keys)
        web_sales = await _count_web_sales_by_keys(stock_keys)
        categories = []
        stock_details = {}

        for category, products in prepared_categories:
            visible_products = []
            for product in products:
                stock_key = product.get('stock_key') or ''
                if not stock_key:
                    continue

                effective_web_available = _effective_channel_available(
                    product,
                    'web',
                    stock_counts.get(stock_key, 0),
                    web_sales.get(stock_key, 0),
                )
                if effective_web_available <= 0:
                    continue

                stock_details[stock_key] = effective_web_available
                visible_products.append(product)

            if not visible_products:
                continue

            categories.append(
                {
                    '_id': str(category.get('_id') or ''),
                    'name': str(category.get('name') or ''),
                    'icon': str(category.get('icon') or 'fa-gamepad'),
                    'image': str(category.get('image') or ''),
                    'logo': str(category.get('logo') or ''),
                    'products': visible_products,
                }
            )

        currencies = await db.store_currencies.find().to_list(100)
        if not currencies:
            currencies = [{'_id': 'EGP', 'symbol': 'EGP'}, {'_id': 'USD', 'symbol': 'USD'}]

        return templates.TemplateResponse(
            'storefront.html',
            {
                'request': request,
                'categories': categories,
                'stock': stock_details,
                'client_id': GOOGLE_CLIENT_ID,
                'maintenance': maintenance,
                'currencies': currencies,
                'user': user,
            },
        )
    except Exception:
        error_details = traceback.format_exc()
        print(error_details)
        return HTMLResponse(
            content=(
                "<div style='direction:ltr; text-align:left; background:#111; color:#7dfc89; "
                "padding:20px; font-family:monospace; height:100vh; overflow:auto;'>"
                f'<h2>System Error Debugger:</h2><pre>{error_details}</pre></div>'
            ),
            status_code=500,
        )


async def get_server_price(stock_key: str, currency: str):
    snapshot = await _get_channel_product_snapshot(stock_key, 'web')
    if not snapshot or snapshot.get('effective_available', 0) <= 0:
        return None
    return _resolve_product_price(snapshot, currency)


async def _acquire_txn_lock(transaction_id: str, email: str, action: str):
    txid = (transaction_id or str(uuid.uuid4())).strip()
    now = datetime.now()

    existing = await db.store_txn_locks.find_one({'_id': txid})
    if existing and existing.get('status') == 'done':
        return None

    await db.store_txn_locks.update_one(
        {'_id': txid},
        {
            '$setOnInsert': {
                '_id': txid,
                'email': email,
                'action': action,
                'created_at': now,
                'status': 'pending',
            }
        },
        upsert=True,
    )
    return txid


async def _finish_txn_lock(txid: str, status_value: str, note: str = ''):
    await db.store_txn_locks.update_one(
        {'_id': txid},
        {
            '$set': {
                'status': status_value,
                'note': note,
                'finished_at': datetime.now(),
            }
        },
        upsert=True,
    )


def get_user_data(user):
    return {
        'user_id': user.get('user_id'),
        'email': user['email'],
        'name': user['name'],
        'username': user.get('username', ''),
        'balance_egp': user.get('balance_egp', 0),
        'balance_usd': user.get('balance_usd', 0),
        'avatar': user.get('avatar', ''),
    }

@router.post("/api/store/login-manual")
async def login_manual(
    request: Request, email: str = Form(...), password: str = Form(...)
):
    email = _normalize_email(email)
    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse(
            {"success": False, "msg": "Account not found. Please sign up."}
        )
    if not user.get("password"):
        return JSONResponse(
            {"success": False, "msg": "Please login with Google or Telegram."}
        )
    if not verify_password(password, user["password"]):
        return JSONResponse({"success": False, "msg": "Incorrect password!"})
    if _is_legacy_sha256_hash(user.get("password", "")):
        new_hash = hash_password(password)
        await db.store_customers.update_one(
            {"user_id": user.get("user_id")},
            {"$set": {"password": new_hash}},
        )
        user["password"] = new_hash
    if user.get("is_banned", False):
        return JSONResponse(
            {"success": False, "msg": "Your account has been suspended by the admin."}
        )

    return await _create_store_auth_response(request, user)


@router.post("/api/store/signup-request")
async def signup_request(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    email = _normalize_email(email)
    username = username.lower().strip()
    if len(password) < 8:
        return JSONResponse(
            {"success": False, "msg": "Password must be at least 8 characters!"}
        )
    if await db.store_customers.find_one({"email": email}):
        return JSONResponse({"success": False, "msg": "Email is already registered!"})
    if await db.store_customers.find_one({"username": username}):
        return JSONResponse({"success": False, "msg": "Username is already taken!"})

    await _create_otp_challenge(
        email,
        "signup",
        {
            "name": name.strip(),
            "username": username,
            "password_hash": hash_password(password),
        },
    )
    return JSONResponse({"success": True, "msg": "OTP sent to your email!"})


@router.post("/api/store/signup-verify")
async def signup_verify(
    request: Request, email: str = Form(...), code: str = Form(...)
):
    email = _normalize_email(email)
    otp_doc, error_msg = await _verify_otp_challenge(email, "signup", code.strip())
    if not otp_doc:
        return JSONResponse({"success": False, "msg": error_msg})

    payload = otp_doc.get("payload") or {}
    user_id = await generate_unique_id()
    user = {
        "user_id": user_id,
        "username": payload.get("username", ""),
        "email": email,
        "name": payload.get("name", ""),
        "password": payload.get("password_hash", ""),
        "balance_egp": 0,
        "balance_usd": 0,
        "is_banned": False,
        "balance_frozen": False,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    try:
        await db.store_customers.insert_one(user)
    except DuplicateKeyError:
        await _clear_otp_challenge(email, "signup")
        return JSONResponse({"success": False, "msg": "Email or username is already registered."})

    await _clear_otp_challenge(email, "signup")
    return await _create_store_auth_response(request, user)


@router.post("/api/store/google-login")
async def google_login(request: Request, credential: str = Form(...)):
    async with httpx.AsyncClient(timeout=10.0) as http:
        res = await http.get(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
        )
        if res.status_code != 200:
            return JSONResponse(
                {"success": False, "msg": "Google verification failed."}
            )
        user_info = res.json()
        if user_info.get("aud") != GOOGLE_CLIENT_ID:
            return JSONResponse({"success": False, "msg": "Invalid token."})
        if str(user_info.get("email_verified", "")).lower() not in {"true", "1"}:
            return JSONResponse({"success": False, "msg": "Google email is not verified."})

        email = _normalize_email(user_info.get("email"))
        if not email:
            return JSONResponse({"success": False, "msg": "Google account did not return an email."})

        name = (user_info.get("name") or email.split("@")[0]).strip()
        user = await db.store_customers.find_one({"email": email})

        if not user:
            user_id = await generate_unique_id()
            username = email.split("@")[0].lower() + str(random.randint(10, 99))
            user = {
                "user_id": user_id,
                "username": username,
                "email": email,
                "name": name,
                "google_sub": user_info.get("sub"),
                "balance_egp": 0,
                "balance_usd": 0,
                "is_banned": False,
                "balance_frozen": False,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            try:
                await db.store_customers.insert_one(user)
            except DuplicateKeyError:
                user = await db.store_customers.find_one({"email": email})

        if user.get("is_banned", False):
            return JSONResponse(
                {
                    "success": False,
                    "msg": "Your account has been suspended by the admin.",
                }
            )

        return await _create_store_auth_response(request, user)


@router.post("/api/store/telegram-login")
async def telegram_login(request: Request):
    form = await request.form()
    payload = {key: str(form.get(key, "") or "") for key in [
        "id",
        "tg_id",
        "first_name",
        "last_name",
        "username",
        "photo_url",
        "auth_date",
        "hash",
        "name",
    ]}
    is_valid, error_msg, telegram_user = _verify_telegram_payload(payload)
    if not is_valid or not telegram_user:
        return JSONResponse({"success": False, "msg": error_msg})

    tg_id = telegram_user["id"]
    email = f"tg_{tg_id}@telegram.zone"
    user = await db.store_customers.find_one({"email": email})

    if not user:
        user_id = await generate_unique_id()
        final_username = telegram_user.get("username", "").lower() or f"user{tg_id}"
        user = {
            "user_id": user_id,
            "telegram_id": tg_id,
            "username": final_username,
            "email": email,
            "name": telegram_user["name"],
            "avatar": telegram_user.get("photo_url", ""),
            "balance_egp": 0,
            "balance_usd": 0,
            "is_banned": False,
            "balance_frozen": False,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        try:
            await db.store_customers.insert_one(user)
        except DuplicateKeyError:
            user = await db.store_customers.find_one({"email": email})

    if user.get("is_banned", False):
        return JSONResponse(
            {"success": False, "msg": "Your account has been suspended by the admin."}
        )

    return await _create_store_auth_response(request, user)


@router.post("/api/store/logout")
async def store_logout(request: Request):
    await _invalidate_current_store_session(request)
    response = JSONResponse({"success": True})
    _clear_store_session_cookie(response, request)
    return response


# ==========================================
# 3. Ù†Ø¸Ø§Ù… Ø§Ø³ØªØ¹Ø§Ø¯Ø© ÙƒÙ„Ù…Ø© Ø§Ù„Ù…Ø±ÙˆØ±
# ==========================================
@router.post("/api/store/forgot-password")
async def forgot_password(request: Request, email: str = Form(...)):
    email = _normalize_email(email)
    user = await db.store_customers.find_one({"email": email})
    if user:
        await _create_otp_challenge(email, "reset")

    return JSONResponse(
        {"success": True, "msg": "If the account exists, a password reset code has been sent."}
    )


@router.post("/api/store/reset-password")
async def reset_password(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    new_password: str = Form(...),
):
    email = _normalize_email(email)
    if len(new_password) < 8:
        return JSONResponse(
            {"success": False, "msg": "Password must be at least 8 characters!"}
        )

    otp_doc, error_msg = await _verify_otp_challenge(email, "reset", code.strip())
    if not otp_doc:
        return JSONResponse({"success": False, "msg": error_msg or "Invalid or expired reset code!"})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        await _clear_otp_challenge(email, "reset")
        return JSONResponse({"success": False, "msg": "Account not found."})

    new_hash = hash_password(new_password)
    await db.store_customers.update_one(
        {"user_id": user.get("user_id")}, {"$set": {"password": new_hash}}
    )
    await _clear_otp_challenge(email, "reset")
    await _invalidate_store_sessions_for_user(user.get("user_id"))
    return JSONResponse(
        {"success": True, "msg": "Password updated successfully! You can now login."}
    )


# ==========================================
# 4. Ø§Ù„Ø´Ø±Ø§Ø¡ ÙˆØ³Ø¬Ù„ Ø§Ù„Ø·Ù„Ø¨Ø§Øª
# ==========================================
class StoreCheckoutError(Exception):
    def __init__(self, message: str, status_code: int = 400, *, force_logout: bool = False):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.force_logout = force_logout


def _validate_checkout_customer(user: Optional[dict]) -> None:
    if not user:
        raise StoreCheckoutError('Account not found!', status_code=401, force_logout=True)
    if user.get('is_banned', False):
        raise StoreCheckoutError('Your account is suspended.', status_code=403, force_logout=True)
    if user.get('balance_frozen', False):
        raise StoreCheckoutError(
            'Your balance is currently frozen. Please contact support.',
            status_code=403,
        )


def _mask_code(raw_code: Any) -> str:
    code = str(raw_code or '')
    if not code:
        return ''

    visible = min(4, len(code))
    return ('*' * max(len(code) - visible, 0)) + code[-visible:]


def _format_store_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    return str(value or '')


def _serialize_store_order(order: dict) -> dict:
    masked_code = order.get('code_masked') or _mask_code(order.get('code'))
    return {
        'order_id': str(order.get('_id', '')),
        'date': order.get('date', ''),
        'category': order.get('category', ''),
        'price': float(order.get('price') or 0),
        'currency': (order.get('currency') or '').upper(),
        'code_masked': masked_code,
        'delivery_state': order.get('delivery_state') or 'delivered',
        'can_reveal': bool(order.get('code')) and not order.get('code_revealed_at'),
        'code_revealed_at': _format_store_timestamp(order.get('code_revealed_at')),
    }



def _iso_datetime_string(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return str(value or '')


def _normalize_channel_flag(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    lowered = str(value).strip().lower()
    if lowered in {'1', 'true', 'yes', 'on'}:
        return True
    if lowered in {'0', 'false', 'no', 'off'}:
        return False
    return default


def _normalize_channel_allocation(value: Any) -> Optional[int]:
    if value in (None, ''):
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(parsed, 0)


def _parse_allocation_form_value(value: Any) -> tuple[bool, Optional[int]]:
    raw = str(value or '').strip()
    if not raw:
        return True, None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return False, None
    if parsed < 0:
        return False, None
    return True, parsed


def _normalize_product_prices(product: dict) -> dict:
    raw_prices = product.get('prices') or {}
    prices = {}
    for key, value in raw_prices.items():
        code = str(key or '').upper()
        if not code:
            continue
        try:
            prices[code] = float(value or 0)
        except (TypeError, ValueError):
            prices[code] = 0.0

    for legacy_key, currency in (('price_egp', 'EGP'), ('price_usd', 'USD')):
        if currency in prices:
            continue
        raw_value = product.get(legacy_key)
        if raw_value in (None, ''):
            continue
        try:
            prices[currency] = float(raw_value or 0)
        except (TypeError, ValueError):
            prices[currency] = 0.0
    return prices


def _normalize_catalog_product(product: dict | None) -> dict:
    raw = dict(product or {})
    prices = _normalize_product_prices(raw)
    raw['stock_key'] = str(raw.get('stock_key') or '').strip()
    raw['name'] = str(raw.get('name') or '').strip()
    raw['image'] = str(raw.get('image') or '').strip()
    raw['prices'] = prices
    raw['price_egp'] = prices.get('EGP', 0.0)
    raw['price_usd'] = prices.get('USD', 0.0)
    raw['is_visible_web'] = _normalize_channel_flag(raw.get('is_visible_web'), True)
    raw['is_visible_bot'] = _normalize_channel_flag(raw.get('is_visible_bot'), True)
    raw['allocation_web'] = _normalize_channel_allocation(raw.get('allocation_web'))
    raw['allocation_bot'] = _normalize_channel_allocation(raw.get('allocation_bot'))
    return raw


def _resolve_product_price(product: dict, currency: str) -> Optional[float]:
    currency = (currency or '').upper()
    prices = product.get('prices') or {}
    if currency in prices:
        return float(prices[currency])

    legacy_key = f'price_{currency.lower()}'
    if legacy_key in product:
        try:
            return float(product.get(legacy_key) or 0)
        except (TypeError, ValueError):
            return None

    if 'EGP' in prices:
        return float(prices['EGP'])
    return None


def _remaining_channel_allocation(product: dict, channel: str, sold_count: int) -> Optional[int]:
    allocation = product.get(f'allocation_{channel}')
    if allocation is None:
        return None
    return max(int(allocation) - int(sold_count or 0), 0)


def _effective_channel_available(product: dict, channel: str, stock_count: int, sold_count: int) -> int:
    if not product.get(f'is_visible_{channel}', True):
        return 0

    available_stock = max(int(stock_count or 0), 0)
    if available_stock <= 0:
        return 0

    remaining = _remaining_channel_allocation(product, channel, sold_count)
    if remaining is None:
        return available_stock
    return min(available_stock, remaining)


async def _count_stock_by_keys(stock_keys: List[str]) -> dict:
    unique_keys = [str(key).strip() for key in dict.fromkeys(stock_keys or []) if str(key).strip()]
    counts = {}
    for stock_key in unique_keys:
        counts[stock_key] = await db.stock.count_documents({'category': stock_key})
    return counts


async def _count_web_sales_by_keys(stock_keys: List[str]) -> dict:
    unique_keys = [str(key).strip() for key in dict.fromkeys(stock_keys or []) if str(key).strip()]
    if not unique_keys:
        return {}

    counts = defaultdict(int)
    orders = await db.store_orders.find({'category': {'$in': unique_keys}}, {'category': 1}).to_list(None)
    for order in orders:
        stock_key = str(order.get('category') or '').strip()
        if stock_key:
            counts[stock_key] += 1
    return dict(counts)


async def _count_bot_sales_by_keys(stock_keys: List[str]) -> dict:
    unique_keys = [str(key).strip() for key in dict.fromkeys(stock_keys or []) if str(key).strip()]
    if not unique_keys:
        return {}

    type_map = {f'Bot Stock ({stock_key})': stock_key for stock_key in unique_keys}
    counts = defaultdict(int)
    orders = await db.orders.find({'type': {'$in': list(type_map.keys())}}, {'type': 1, 'items': 1}).to_list(None)
    for order in orders:
        stock_key = type_map.get(str(order.get('type') or ''))
        if not stock_key:
            continue
        counts[stock_key] += len(order.get('items') or [])
    return dict(counts)


async def _find_catalog_product(stock_key: str) -> Optional[dict]:
    stock_key = str(stock_key or '').strip()
    if not stock_key:
        return None

    category = await db.store_categories.find_one(
        {'products.stock_key': stock_key},
        {'_id': 1, 'name': 1, 'products.$': 1},
    )
    if not category or not category.get('products'):
        return None

    product = _normalize_catalog_product(category['products'][0])
    product['category_id'] = str(category.get('_id') or '')
    product['category_name'] = str(category.get('name') or '')
    return product


async def _build_inventory_product_snapshot(stock_key: str) -> Optional[dict]:
    product = await _find_catalog_product(stock_key)
    if not product:
        return None

    stock_counts = await _count_stock_by_keys([stock_key])
    web_sales = await _count_web_sales_by_keys([stock_key])
    bot_sales = await _count_bot_sales_by_keys([stock_key])

    actual_stock = stock_counts.get(stock_key, 0)
    web_sold = web_sales.get(stock_key, 0)
    bot_sold = bot_sales.get(stock_key, 0)
    remaining_web = _remaining_channel_allocation(product, 'web', web_sold)
    remaining_bot = _remaining_channel_allocation(product, 'bot', bot_sold)
    effective_web_available = _effective_channel_available(product, 'web', actual_stock, web_sold)
    effective_bot_available = _effective_channel_available(product, 'bot', actual_stock, bot_sold)

    return {
        'stock_key': stock_key,
        'name': product.get('name') or stock_key,
        'image': product.get('image') or '',
        'prices': product.get('prices') or {},
        'price_egp': float(product.get('price_egp') or 0),
        'price_usd': float(product.get('price_usd') or 0),
        'is_visible_web': bool(product.get('is_visible_web', True)),
        'is_visible_bot': bool(product.get('is_visible_bot', True)),
        'allocation_web': product.get('allocation_web'),
        'allocation_bot': product.get('allocation_bot'),
        'stock_count': int(actual_stock),
        'web_sold': int(web_sold),
        'bot_sold': int(bot_sold),
        'remaining_web': remaining_web,
        'remaining_bot': remaining_bot,
        'effective_web_available': int(effective_web_available),
        'effective_bot_available': int(effective_bot_available),
        'web_unlimited': remaining_web is None,
        'bot_unlimited': remaining_bot is None,
        'category_id': product.get('category_id') or '',
        'category_name': product.get('category_name') or '',
    }


async def _get_channel_product_snapshot(stock_key: str, channel: str) -> Optional[dict]:
    snapshot = await _build_inventory_product_snapshot(stock_key)
    if not snapshot:
        return None

    sold_count = snapshot['web_sold'] if channel == 'web' else snapshot['bot_sold']
    remaining = snapshot['remaining_web'] if channel == 'web' else snapshot['remaining_bot']
    effective_available = snapshot['effective_web_available'] if channel == 'web' else snapshot['effective_bot_available']
    snapshot['sold_count'] = sold_count
    snapshot['remaining_allocation'] = remaining
    snapshot['effective_available'] = effective_available
    return snapshot


def _serialize_admin_order(order: dict) -> dict:
    return {
        'order_id': str(order.get('_id', '')),
        'category': str(order.get('category') or ''),
        'price': float(order.get('price') or 0),
        'currency': (order.get('currency') or '').upper(),
        'date': order.get('date') or _format_store_timestamp(order.get('created_at')),
        'code': str(order.get('code') or ''),
        'code_masked': order.get('code_masked') or _mask_code(order.get('code')),
        'delivery_state': order.get('delivery_state') or 'delivered',
        'created_at': _iso_datetime_string(order.get('created_at')),
        'updated_at': _iso_datetime_string(order.get('updated_at')),
    }


def _split_bulk_order_ids(raw_value: str) -> List[str]:
    return [entry for entry in re.split(r'[\s,]+', (raw_value or '').strip()) if entry]


async def _build_admin_catalog_payload() -> List[dict]:
    raw_categories = await db.store_categories.find().to_list(200)
    normalized_categories = []
    stock_keys = []

    for category in raw_categories:
        normalized_products = []
        for product in category.get('products') or []:
            normalized = _normalize_catalog_product(product)
            if normalized.get('stock_key'):
                stock_keys.append(normalized['stock_key'])
            normalized_products.append(normalized)
        normalized_categories.append((category, normalized_products))

    stock_counts = await _count_stock_by_keys(stock_keys)
    web_sales = await _count_web_sales_by_keys(stock_keys)
    bot_sales = await _count_bot_sales_by_keys(stock_keys)

    payload = []
    for category, products in normalized_categories:
        serialized_products = []
        visible_web_count = 0
        visible_bot_count = 0

        for product in products:
            stock_key = product.get('stock_key') or ''
            stock_count = stock_counts.get(stock_key, 0)
            web_sold = web_sales.get(stock_key, 0)
            bot_sold = bot_sales.get(stock_key, 0)
            remaining_web = _remaining_channel_allocation(product, 'web', web_sold)
            remaining_bot = _remaining_channel_allocation(product, 'bot', bot_sold)
            effective_web_available = _effective_channel_available(product, 'web', stock_count, web_sold)
            effective_bot_available = _effective_channel_available(product, 'bot', stock_count, bot_sold)

            if product.get('is_visible_web', True):
                visible_web_count += 1
            if product.get('is_visible_bot', True):
                visible_bot_count += 1

            serialized_products.append(
                {
                    'stock_key': stock_key,
                    'name': product.get('name') or stock_key,
                    'image': product.get('image') or '',
                    'prices': product.get('prices') or {},
                    'price_egp': float(product.get('price_egp') or 0),
                    'price_usd': float(product.get('price_usd') or 0),
                    'is_visible_web': bool(product.get('is_visible_web', True)),
                    'is_visible_bot': bool(product.get('is_visible_bot', True)),
                    'allocation_web': product.get('allocation_web'),
                    'allocation_bot': product.get('allocation_bot'),
                    'stock_count': int(stock_count),
                    'web_sold': int(web_sold),
                    'bot_sold': int(bot_sold),
                    'remaining_web': remaining_web,
                    'remaining_bot': remaining_bot,
                    'effective_web_available': int(effective_web_available),
                    'effective_bot_available': int(effective_bot_available),
                    'web_unlimited': remaining_web is None,
                    'bot_unlimited': remaining_bot is None,
                }
            )

        payload.append(
            {
                'cat_id': str(category.get('_id') or ''),
                'name': str(category.get('name') or ''),
                'icon': str(category.get('icon') or 'fa-gamepad'),
                'image': str(category.get('image') or ''),
                'logo': str(category.get('logo') or ''),
                'product_count': len(serialized_products),
                'visible_web_count': visible_web_count,
                'visible_bot_count': visible_bot_count,
                'products': serialized_products,
            }
        )
    return payload


async def _process_store_order_return(order_id: str) -> tuple[bool, str]:
    order_id = (order_id or '').strip()
    if not order_id:
        return False, 'Order ID is required.'

    order = await db.store_orders.find_one({'_id': order_id})
    if not order:
        return False, 'Order not found.'

    code_value = str(order.get('code') or '').strip()
    stock_key = str(order.get('category') or '').strip()
    if code_value and stock_key:
        await db.stock.insert_one(
            {
                'code': code_value,
                'category': stock_key,
                'added_at': datetime.now(),
            }
        )

    await db.codes_map.delete_many({'order_id': order_id})
    delete_result = await db.store_orders.delete_one({'_id': order_id})
    if delete_result.deleted_count == 0:
        return False, 'Order not found.'

    email = _normalize_email(order.get('email'))
    price = float(order.get('price') or 0)
    currency = (order.get('currency') or 'EGP').upper()
    if email and price > 0:
        bal_field = f'balance_{currency.lower()}'
        await db.store_customers.update_one({'email': email}, {'$inc': {bal_field: price}})
        await log_wallet_txn(email, price, currency, f'Order return refund #{order_id}', ref=order_id)

    return True, 'Order returned to stock!'
def _normalize_checkout_items(raw_items: List[dict]) -> List[dict]:
    normalized = []
    for item in raw_items or []:
        try:
            quantity = int(item.get('quantity') or 0)
        except (TypeError, ValueError):
            quantity = 0

        normalized.append(
            {
                'stock_key': str(item.get('stock_key') or '').strip(),
                'currency': str(item.get('currency') or '').upper().strip(),
                'quantity': quantity,
            }
        )
    return normalized


def _checkout_payload_hash(items: List[dict]) -> str:
    return _hash_sha256(
        json.dumps(items, sort_keys=True, separators=(',', ':'))
    )


def _require_idempotency_key(request: Request) -> str:
    raw_key = (request.headers.get('Idempotency-Key') or '').strip()
    if not raw_key:
        raise StoreCheckoutError('Missing Idempotency-Key header.', status_code=400)
    if len(raw_key) > 128:
        raise StoreCheckoutError('Idempotency-Key is too long.', status_code=400)
    return raw_key


def _idempotency_doc_id(email: str, action: str, raw_key: str) -> str:
    normalized_email = _normalize_email(email)
    return _hash_sha256(f'{normalized_email}:{action}:{raw_key}')


async def _begin_checkout_idempotency(
    email: str,
    action: str,
    raw_key: str,
    payload_hash: str,
) -> dict:
    now = _utcnow()
    doc_id = _idempotency_doc_id(email, action, raw_key)
    document = {
        '_id': doc_id,
        'email': _normalize_email(email),
        'action': action,
        'request_hash': payload_hash,
        'status': 'pending',
        'created_at': now,
        'updated_at': now,
        'expires_at': now + timedelta(days=2),
    }

    try:
        await db.store_txn_locks.insert_one(document)
        return {'doc_id': doc_id, 'cached_response': None, 'cached_status': None}
    except DuplicateKeyError:
        existing = await db.store_txn_locks.find_one({'_id': doc_id}) or {}
        if existing.get('request_hash') and existing.get('request_hash') != payload_hash:
            raise StoreCheckoutError(
                'This Idempotency-Key was already used for a different checkout payload.',
                status_code=409,
            )

        if existing.get('status') in {'done', 'failed'} and isinstance(existing.get('response'), dict):
            return {
                'doc_id': doc_id,
                'cached_response': existing['response'],
                'cached_status': int(existing.get('status_code') or 200),
            }

        raise StoreCheckoutError(
            'This checkout is already being processed. Please wait a moment.',
            status_code=409,
        )


async def _finish_checkout_idempotency(
    doc_id: str,
    status_value: str,
    response_payload: dict,
    *,
    status_code: int = 200,
    note: str = '',
) -> None:
    now = _utcnow()
    await db.store_txn_locks.update_one(
        {'_id': doc_id},
        {
            '$set': {
                'status': status_value,
                'response': response_payload,
                'status_code': int(status_code),
                'note': note,
                'finished_at': now,
                'updated_at': now,
                'expires_at': now + timedelta(days=2),
            }
        },
        upsert=True,
    )


async def _restore_reserved_stock(reserved_items: List[dict]) -> None:
    docs = [entry.get('stock_doc') for entry in reserved_items if entry.get('stock_doc')]
    if not docs:
        return

    try:
        await db.stock.insert_many(docs, ordered=False)
        return
    except Exception:
        pass

    for doc in docs:
        try:
            stock_id = doc.get('_id')
            if stock_id is None:
                await db.stock.insert_one(doc)
                continue
            await db.stock.update_one(
                {'_id': stock_id},
                {'$setOnInsert': doc},
                upsert=True,
            )
        except Exception:
            logger.exception('Failed to restore reserved stock %s', doc.get('_id'))


async def _rollback_store_checkout(
    email: str,
    reserved_items: List[dict],
    created_orders: List[dict],
    deducted_totals: dict,
) -> None:
    order_ids = [order.get('_id') for order in created_orders if order.get('_id')]

    if order_ids:
        await db.store_wallet_ledger.delete_many(
            {'email': _normalize_email(email), 'ref': {'$in': order_ids}}
        )
        await db.codes_map.delete_many({'order_id': {'$in': order_ids}})
        await db.store_orders.delete_many({'_id': {'$in': order_ids}})

    for currency, amount in deducted_totals.items():
        if not amount:
            continue
        bal_field = f"balance_{currency.lower()}"
        await db.store_customers.update_one(
            {'email': _normalize_email(email)},
            {'$inc': {bal_field: float(amount)}},
        )

    await _restore_reserved_stock(reserved_items)


async def _execute_store_checkout(
    request: Request,
    email: str,
    raw_items: List[dict],
    action_name: str,
    success_message: str,
    *,
    single_item: bool = False,
):
    idempotency_doc_id = None
    reserved_items: List[dict] = []
    created_orders: List[dict] = []
    deducted_totals: dict = {}

    try:
        raw_key = _require_idempotency_key(request)
        normalized_items = _normalize_checkout_items(raw_items)
        if not normalized_items:
            raise StoreCheckoutError('Your cart is empty.', status_code=400)

        for item in normalized_items:
            if not item['stock_key'] or not item['currency'] or item['quantity'] <= 0:
                raise StoreCheckoutError('Invalid checkout payload.', status_code=400)

        payload_hash = _checkout_payload_hash(normalized_items)
        idempotency_state = await _begin_checkout_idempotency(
            email,
            action_name,
            raw_key,
            payload_hash,
        )
        idempotency_doc_id = idempotency_state['doc_id']
        if idempotency_state.get('cached_response') is not None:
            return idempotency_state['cached_response'], idempotency_state.get('cached_status') or 200

        user = await db.store_customers.find_one({'email': _normalize_email(email)})
        _validate_checkout_customer(user)

        web_availability = {}
        for item in normalized_items:
            stock_key = item['stock_key']
            snapshot = web_availability.get(stock_key)
            if snapshot is None:
                snapshot = await _get_channel_product_snapshot(stock_key, 'web')
                if not snapshot or snapshot.get('effective_available', 0) <= 0:
                    raise StoreCheckoutError(
                        f"Sorry, {stock_key} is currently unavailable on the web store.",
                        status_code=409,
                    )
                web_availability[stock_key] = snapshot

            trusted_price = _resolve_product_price(snapshot, item['currency'])
            if trusted_price is None:
                raise StoreCheckoutError('Invalid product or currency.', status_code=400)

            remaining_available = int(snapshot.get('effective_available', 0) or 0)
            if remaining_available < item['quantity']:
                raise StoreCheckoutError(
                    f"Sorry, {stock_key} only has {remaining_available} item(s) available for web checkout.",
                    status_code=409,
                )

            snapshot['effective_available'] = max(remaining_available - int(item['quantity']), 0)

            for _ in range(item['quantity']):
                stock_doc = await db.stock.find_one_and_delete({'category': stock_key})
                if not stock_doc:
                    raise StoreCheckoutError(
                        f"Sorry, {stock_key} is out of stock.",
                        status_code=409,
                    )

                reserved_items.append(
                    {
                        'stock_key': stock_key,
                        'currency': item['currency'],
                        'price': float(trusted_price),
                        'stock_doc': stock_doc,
                    }
                )
        fresh_user = await db.store_customers.find_one({'email': _normalize_email(email)})
        _validate_checkout_customer(fresh_user)

        totals_by_currency: dict = {}
        for reserved in reserved_items:
            currency = reserved['currency']
            totals_by_currency[currency] = round(
                float(totals_by_currency.get(currency, 0)) + float(reserved['price']),
                2,
            )

        for currency, amount in totals_by_currency.items():
            bal_field = f"balance_{currency.lower()}"
            current_balance = float((fresh_user or {}).get(bal_field, 0) or 0)
            if current_balance < amount:
                raise StoreCheckoutError(
                    f'Insufficient {currency} balance! Please recharge.',
                    status_code=409,
                )

        now_local = datetime.now()
        now_utc = _utcnow()
        now_str = now_local.strftime('%Y-%m-%d %H:%M')

        for reserved in reserved_items:
            code_value = reserved['stock_doc'].get('code') or reserved['stock_doc'].get('_id')
            code_str = str(code_value)
            seq = await get_next_order_id()
            order_id = f'{seq}S'
            order_doc = {
                '_id': order_id,
                'email': _normalize_email(email),
                'name': fresh_user['name'],
                'category': reserved['stock_key'],
                'code': code_str,
                'code_masked': _mask_code(code_str),
                'price': float(reserved['price']),
                'currency': reserved['currency'],
                'date': now_str,
                'created_at': now_utc,
                'updated_at': now_utc,
                'delivery_state': 'reserved',
                'code_reveal_count': 0,
                'source': 'Web Store',
            }
            await db.store_orders.insert_one(order_doc)
            created_orders.append(order_doc)

        latest_user = fresh_user
        for currency, amount in totals_by_currency.items():
            bal_field = f"balance_{currency.lower()}"
            latest_user = await db.store_customers.find_one_and_update(
                {
                    'email': _normalize_email(email),
                    bal_field: {'$gte': float(amount)},
                },
                {'$inc': {bal_field: -float(amount)}},
                return_document=ReturnDocument.AFTER,
            )
            if not latest_user:
                raise StoreCheckoutError(
                    f'Insufficient {currency} balance! Please recharge.',
                    status_code=409,
                )
            deducted_totals[currency] = float(amount)

        results = []
        for order_doc in created_orders:
            order_id = order_doc['_id']
            await db.codes_map.insert_one(
                {
                    'code': order_doc['code'],
                    'order_id': order_id,
                    'name': f"{fresh_user['name']} (Web)",
                    'time': now_str,
                    'source': 'Web Store',
                }
            )
            await log_wallet_txn(
                _normalize_email(email),
                -float(order_doc['price']),
                order_doc['currency'],
                f"Order #{order_id}",
                ref=order_id,
            )
            await db.store_orders.update_one(
                {'_id': order_id},
                {
                    '$set': {
                        'delivery_state': 'delivered',
                        'delivered_at': now_utc,
                        'updated_at': now_utc,
                    }
                },
            )
            order_doc['delivery_state'] = 'delivered'
            results.append(
                {
                    'stock_key': order_doc['category'],
                    'status': 'Success',
                    'price': float(order_doc['price']),
                    'currency': order_doc['currency'],
                    'order_id': order_id,
                    'code_masked': order_doc['code_masked'],
                    'can_reveal': True,
                }
            )

        final_user = await db.store_customers.find_one({'email': _normalize_email(email)}) or latest_user or fresh_user
        new_balances = {
            key: value
            for key, value in (final_user or {}).items()
            if key.startswith('balance_')
        }

        response_payload = {
            'success': True,
            'results': results,
            'new_balances': new_balances,
            'msg': success_message,
        }

        if single_item and results:
            first_result = results[0]
            response_payload.update(
                {
                    'order_id': first_result['order_id'],
                    'currency': first_result['currency'],
                    'new_balance': new_balances.get(
                        f"balance_{first_result['currency'].lower()}"
                    ),
                    'code_masked': first_result['code_masked'],
                    'can_reveal': first_result['can_reveal'],
                }
            )

        await _finish_checkout_idempotency(
            idempotency_doc_id,
            'done',
            response_payload,
            status_code=200,
            note='ok',
        )
        return response_payload, 200
    except StoreCheckoutError as exc:
        if idempotency_doc_id:
            try:
                await _rollback_store_checkout(
                    email,
                    reserved_items,
                    created_orders,
                    deducted_totals,
                )
            except Exception:
                logger.exception('Checkout rollback failed for %s', email)

        response_payload = {'success': False, 'msg': exc.message}
        if exc.force_logout:
            response_payload['force_logout'] = True

        if idempotency_doc_id:
            await _finish_checkout_idempotency(
                idempotency_doc_id,
                'failed',
                response_payload,
                status_code=exc.status_code,
                note=exc.message,
            )
        return response_payload, exc.status_code
    except Exception:
        logger.exception('Store checkout failed for %s', email)
        if idempotency_doc_id:
            try:
                await _rollback_store_checkout(
                    email,
                    reserved_items,
                    created_orders,
                    deducted_totals,
                )
            except Exception:
                logger.exception('Checkout rollback failed for %s', email)

        response_payload = {
            'success': False,
            'msg': 'Checkout failed due to server error.',
        }
        if idempotency_doc_id:
            await _finish_checkout_idempotency(
                idempotency_doc_id,
                'failed',
                response_payload,
                status_code=500,
                note='internal_error',
            )
        return response_payload, 500


@router.post("/api/store/buy")
async def customer_buy(
    request: Request,
    stock_key: str = Form(...),
    currency: str = Form(...),
    transaction_id: str = Form(''),
    price: float = Form(0),
):
    del transaction_id, price

    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse(
            {
                'success': False,
                'msg': 'Unauthorized! Please login again.',
                'force_logout': True,
            },
            status_code=401,
        )

    payload, status_code = await _execute_store_checkout(
        request,
        email,
        [
            {
                'stock_key': stock_key,
                'currency': currency,
                'quantity': 1,
            }
        ],
        'store_buy',
        'Purchase successful!',
        single_item=True,
    )
    return JSONResponse(payload, status_code=status_code)


@router.get("/api/store/my-orders")
async def get_my_orders(request: Request):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'orders': [], 'force_logout': True})

    orders = await db.store_orders.find({'email': _normalize_email(email)}).sort('date', -1).to_list(100)
    serialized_orders = [_serialize_store_order(order) for order in orders]
    return JSONResponse({'success': True, 'orders': serialized_orders})


@router.post("/api/store/orders/reveal")
async def reveal_store_order_code(request: Request, order_id: str = Form(...)):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse(
            {
                'success': False,
                'msg': 'Unauthorized! Please login again.',
                'force_logout': True,
            },
            status_code=401,
        )

    order_id = (order_id or '').strip()
    if not order_id:
        return JSONResponse({'success': False, 'msg': 'Missing order id.'}, status_code=400)

    now_utc = _utcnow()
    order = await db.store_orders.find_one_and_update(
        {
            '_id': order_id,
            'email': _normalize_email(email),
            'code': {'$exists': True, '$ne': ''},
            '$or': [
                {'code_revealed_at': {'$exists': False}},
                {'code_revealed_at': None},
            ],
        },
        {
            '$set': {
                'code_revealed_at': now_utc,
                'delivery_state': 'revealed',
                'updated_at': now_utc,
            },
            '$inc': {'code_reveal_count': 1},
        },
        return_document=ReturnDocument.BEFORE,
    )

    if order:
        raw_code = str(order.get('code') or '')
        return JSONResponse(
            {
                'success': True,
                'order_id': order_id,
                'code': raw_code,
                'code_masked': order.get('code_masked') or _mask_code(raw_code),
                'revealed_at': now_utc.strftime('%Y-%m-%d %H:%M'),
            }
        )

    existing = await db.store_orders.find_one(
        {'_id': order_id, 'email': _normalize_email(email)},
        {'code': 1, 'code_masked': 1, 'code_revealed_at': 1},
    )
    if not existing:
        return JSONResponse({'success': False, 'msg': 'Order not found.'}, status_code=404)

    return JSONResponse(
        {
            'success': False,
            'msg': 'This code has already been revealed for this order.',
            'code_masked': existing.get('code_masked') or _mask_code(existing.get('code')),
            'revealed_at': _format_store_timestamp(existing.get('code_revealed_at')),
        },
        status_code=409,
    )


@router.get("/api/store/wallet-history")
async def wallet_history(request: Request):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({"success": False, "txns": []})

    txns = await db.store_wallet_ledger.find({"email": email}).sort("ts", -1).to_list(200)
    for t in txns:
        t["id"] = str(t.get("_id", ""))
        if "_id" in t:
            del t["_id"]
        t.pop("ts", None)
    return JSONResponse({"success": True, "txns": txns})


@router.post("/api/store/checkout-cart")
async def checkout_cart(request: Request, payload: CheckoutRequest):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse(
            {
                'success': False,
                'msg': 'Unauthorized! Please login again.',
                'force_logout': True,
            },
            status_code=401,
        )

    checkout_items = [
        {
            'stock_key': item.stock_key,
            'currency': item.currency,
            'quantity': item.quantity,
        }
        for item in payload.cart
    ]

    response_payload, status_code = await _execute_store_checkout(
        request,
        email,
        checkout_items,
        'store_checkout_cart',
        'Checkout completed!',
    )
    return JSONResponse(response_payload, status_code=status_code)

@router.get("/store-admin", response_class=HTMLResponse)
async def store_admin_page(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login")

    settings = await db.settings.find_one({"_id": "config"})
    maintenance = settings.get("maintenance", False) if settings else False

    store_customers = (
        await db.store_customers.find().sort("created_at", -1).to_list(200)
    )

    # ØªØ­ÙˆÙŠÙ„ Ø§Ù„Ù€ ObjectId Ù„Ù€ string Ø¹Ø´Ø§Ù† Ø§Ù„Ù€ Error 500
    for customer in store_customers:
        if "_id" in customer:
            customer["_id"] = str(customer["_id"])

    store_orders = await db.store_orders.find().sort("date", -1).to_list(500)

    # â”€â”€ Support Tickets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        open_tickets = (
            await db.support_tickets.find({"status": {"$ne": "closed"}})
            .sort("created_at", -1)
            .to_list(200)
        )
        support_tickets = (
            await db.support_tickets.find().sort("created_at", -1).to_list(500)
        )
        for t in open_tickets:
            t["ticket_id"] = str(t["_id"])
            t["message_count"] = int(t.get("message_count") or len(t.get("messages") or []))
        for t in support_tickets:
            t["ticket_id"] = str(t["_id"])
            t["message_count"] = int(t.get("message_count") or len(t.get("messages") or []))
    except Exception:
        open_tickets = []
        support_tickets = []

    return templates.TemplateResponse(
        "store_admin.html",
        {
            "request": request,
            "store_customers": store_customers,
            "store_orders": store_orders,
            "maintenance": maintenance,
            "open_tickets": open_tickets,
            "support_tickets": support_tickets,
        },
    )

def _sanitize_positive_int(value, field_name: str, max_value: int | None = None) -> int:
    """
    Validate that value is a positive integer (supports str/float/int inputs).
    Raises ValueError with a user-friendly message.
    """
    try:
        v = float(value)
    except Exception:
        raise ValueError(f"Invalid {field_name} value.")

    if v <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")

    if v != int(v):
        raise ValueError(f"{field_name} must be a whole number (no decimals).")

    v_int = int(v)

    if max_value is not None and v_int > max_value:
        raise ValueError(f"{field_name} is too large. Max allowed is {max_value}.")

    return v_int


def _normalize_currency(currency: str) -> str:
    """
    Normalize currency input to 'EGP' or 'USD' (accepts common variants).
    Raises ValueError if currency is invalid.
    """
    c = (currency or "").strip().upper()

    if c in {"EGP", "LE", "L.E", "L.E.", "Ø¬", "Ø¬.Ù…", "Ø¬Ù†ÙŠÙ‡"}:
        return "EGP"
    if c in {"USD", "$", "US$", "US DOLLAR"}:
        return "USD"

    raise ValueError("Invalid currency. Allowed: EGP, USD.")
@router.post("/api/store/manage_balance")
async def store_manage_balance(
    request: Request,
    email: str = Form(...),
    amount: float = Form(...),
    action: str = Form(...),
    currency: str = Form(...),
    transaction_id: str = Form(""),
):
    if not check_auth(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"}, status_code=403)

    sanitizer = globals().get("_sanitize_positive_int")
    currency_normalizer = globals().get("_normalize_currency")
    acquire_lock = globals().get("_acquire_txn_lock")
    finish_lock = globals().get("_finish_txn_lock")
    if not all(callable(fn) for fn in [sanitizer, currency_normalizer, acquire_lock, finish_lock]):
        return JSONResponse(
            {"success": False, "msg": "Server misconfiguration: balance validators unavailable."},
            status_code=500,
        )

    try:
        amount_int = sanitizer(amount, "amount", max_value=1_000_000)
        currency = currency_normalizer(currency)
    except ValueError as e:
        return JSONResponse({"success": False, "msg": str(e)})

    txid = await acquire_lock(transaction_id, email, f"admin_balance_{action}")
    if not txid:
        return JSONResponse(
            {"success": False, "msg": "Duplicate transaction detected."},
            status_code=409,
        )

    try:
        amount_int = _sanitize_positive_int(amount, "amount", max_value=1_000_000)
        amount = float(amount_int)
        currency = _normalize_currency(currency)
    except ValueError as e:
        return JSONResponse({"success": False, "msg": str(e)})

    txid = await _acquire_txn_lock(transaction_id, email, f"admin_balance_{action}")
    if not txid:
        return JSONResponse({"success": False, "msg": "Duplicate transaction detected."})

    bal_field = f"balance_{currency.lower()}"

    if action == "add":
        await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: amount}})
        await log_wallet_txn(email, amount, currency, "Top-up (Admin)")
    elif action == "sub":
        await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: -amount}})
        await log_wallet_txn(email, -amount, currency, "Manual deduction (Admin)")

    await _finish_txn_lock(txid, "done", "ok")
    return JSONResponse({"success": True, "msg": f"{currency} balance updated successfully!", "transaction_id": txid})

# Endpoint ØªØ¬Ù…ÙŠØ¯ Ø§Ù„Ø±ØµÙŠØ¯ Ø£Ùˆ Ø­Ø¸Ø± Ø§Ù„Ø­Ø³Ø§Ø¨
@router.post("/api/store/admin/toggle-status")
async def admin_toggle_status(
    request: Request, email: str = Form(...), action: str = Form(...)
):
    if not check_auth(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "User not found"})

    if action == "ban":
        new_status = not user.get("is_banned", False)
        await db.store_customers.update_one(
            {"email": email}, {"$set": {"is_banned": new_status}}
        )
        msg = (
            "Account Suspended Successfully!"
            if new_status
            else "Account Reactivated Successfully!"
        )
    elif action == "freeze":
        new_status = not user.get("balance_frozen", False)
        await db.store_customers.update_one(
            {"email": email}, {"$set": {"balance_frozen": new_status}}
        )
        msg = (
            "Balance Frozen Successfully!"
            if new_status
            else "Balance Unfrozen Successfully!"
        )
    else:
        return JSONResponse({"success": False, "msg": "Invalid action"})

    return JSONResponse({"success": True, "msg": msg, "new_status": new_status})


# ==========================================
# 6. Profile â€” Get / Edit / Avatar / Password / Email
# ==========================================

import base64, re as _re


def _make_username(name: str, user_id: int) -> str:
    base = _re.sub(r"[^a-z0-9]", "", name.lower())[:12] or "user"
    return f"{base}{str(user_id)[-4:]}"


@router.get("/api/store/me")
async def get_profile(request: Request):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "User not found"})

    if not user.get("username"):
        auto_uname = _make_username(user["name"], user["user_id"])
        await db.store_customers.update_one(
            {"email": email}, {"$set": {"username": auto_uname}}
        )
        user["username"] = auto_uname

    return JSONResponse(
        {
            "success": True,
            "user_id": user.get("user_id"),
            "name": user.get("name"),
            "username": user.get("username"),
            "email": user.get("email"),
            "balance_egp": user.get("balance_egp", 0),
            "balance_usd": user.get("balance_usd", 0),
            "avatar": user.get("avatar", ""),
            "created_at": user.get("created_at", ""),
        }
    )


@router.post("/api/store/update-profile")
async def update_profile(
    request: Request, name: str = Form(...), username: str = Form(...)
):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    username = username.lower().strip()
    if not _re.match(r"^[a-z0-9_]{3,20}$", username):
        return JSONResponse(
            {
                "success": False,
                "msg": "Username must be 3-20 characters (letters, numbers, _)",
            }
        )
    if not name.strip():
        return JSONResponse({"success": False, "msg": "Name cannot be empty"})

    existing = await db.store_customers.find_one(
        {"username": username, "email": {"$ne": email}}
    )
    if existing:
        return JSONResponse({"success": False, "msg": "Username is already taken!"})

    await db.store_customers.update_one(
        {"email": email}, {"$set": {"name": name.strip(), "username": username}}
    )
    return JSONResponse(
        {
            "success": True,
            "msg": "Profile updated successfully!",
            "name": name.strip(),
            "username": username,
        }
    )


@router.post("/api/store/upload-avatar")
async def upload_avatar(request: Request, avatar_b64: str = Form(...)):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    if len(avatar_b64) > 1_400_000:
        return JSONResponse({"success": False, "msg": "Image too large! Max 1MB."})
    if not avatar_b64.startswith("data:image/"):
        return JSONResponse({"success": False, "msg": "Invalid image format."})

    await db.store_customers.update_one(
        {"email": email}, {"$set": {"avatar": avatar_b64}}
    )
    return JSONResponse(
        {"success": True, "msg": "Avatar updated!", "avatar": avatar_b64}
    )


@router.post("/api/store/change-password")
async def change_password(
    request: Request, current_password: str = Form(...), new_password: str = Form(...)
):
    user = await _get_current_store_user(request)
    if not user:
        return JSONResponse({"success": False, "msg": "Not logged in"})
    if not user.get("password"):
        return JSONResponse(
            {
                "success": False,
                "msg": "Your account uses Google/Telegram login â€” no password to change.",
            }
        )
    if not verify_password(current_password, user["password"]):
        return JSONResponse({"success": False, "msg": "Current password is incorrect!"})
    if len(new_password) < 8:
        return JSONResponse(
            {"success": False, "msg": "New password must be at least 8 characters."}
        )
    if current_password == new_password:
        return JSONResponse(
            {"success": False, "msg": "New password must be different from current."}
        )

    new_hash = hash_password(new_password)
    await db.store_customers.update_one(
        {"user_id": user.get("user_id")}, {"$set": {"password": new_hash}}
    )
    user["password"] = new_hash
    await _invalidate_store_sessions_for_user(user.get("user_id"))

    response = JSONResponse({"success": True, "msg": "Password changed successfully!"})
    await _set_store_session_cookie(response, request, user)
    return response


@router.post("/api/store/change-email-request")
async def change_email_request(request: Request, new_email: str = Form(...)):
    current_email = await _get_authenticated_email(request)
    if not current_email:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    new_email = _normalize_email(new_email)
    if not _re.match(r"^[^@]+@[^@]+\.[^@]+$", new_email):
        return JSONResponse({"success": False, "msg": "Invalid email address."})
    if new_email == current_email:
        return JSONResponse(
            {"success": False, "msg": "This is already your current email."}
        )
    if await db.store_customers.find_one({"email": new_email}):
        return JSONResponse(
            {"success": False, "msg": "This email is already registered."}
        )

    await _create_otp_challenge(
        current_email,
        "email_change",
        {"new_email": new_email},
    )
    return JSONResponse(
        {"success": True, "msg": f"Verification code sent to {new_email}"}
    )


@router.post("/api/store/change-email-verify")
async def change_email_verify(request: Request, code: str = Form(...)):
    current_user = await _get_current_store_user(request)
    if not current_user:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    current_email = current_user["email"]
    otp_doc, error_msg = await _verify_otp_challenge(
        current_email, "email_change", code.strip()
    )
    if not otp_doc:
        return JSONResponse({"success": False, "msg": error_msg or "Invalid verification code."})

    payload = otp_doc.get("payload") or {}
    new_email = _normalize_email(payload.get("new_email", ""))
    if not new_email:
        await _clear_otp_challenge(current_email, "email_change")
        return JSONResponse({"success": False, "msg": "Pending email change request is invalid."})
    if await db.store_customers.find_one({"email": new_email}):
        return JSONResponse(
            {"success": False, "msg": "This email was just registered by someone else."}
        )

    await db.store_customers.update_one(
        {"user_id": current_user.get("user_id")}, {"$set": {"email": new_email}}
    )
    await db.store_orders.update_many(
        {"email": current_email}, {"$set": {"email": new_email}}
    )
    await _store_sessions_collection().update_many(
        {"user_id": current_user.get("user_id")},
        {"$set": {"email": new_email, "updated_at": _utcnow()}},
    )
    await _clear_otp_challenge(current_email, "email_change")
    await _invalidate_store_sessions_for_user(current_user.get("user_id"))

    current_user["email"] = new_email
    response = JSONResponse(
        {"success": True, "msg": "Email updated successfully!", "new_email": new_email}
    )
    await _set_store_session_cookie(response, request, current_user)
    return response


# ==========================================
# 7. Admin â€” Full Customer Control
# ==========================================


def admin_check(request: Request):
    incoming = request.cookies.get("admin_session") or ""
    expected = SECRET_TOKEN or ""
    return bool(incoming and expected and hmac.compare_digest(incoming, expected))


@router.get("/api/store/customer-info")
async def customer_info(request: Request, email: str):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})
    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "Not found"})

    # Ø¬Ù„Ø¨ Ø£ÙŠ Ø¹Ù…Ù„Ø© Ø¯ÙŠÙ†Ø§Ù…ÙŠÙƒÙŠØ© Ù…ØªØ³Ø¬Ù„Ø© Ù„Ù„Ø¹Ù…ÙŠÙ„
    balances = {k: v for k, v in user.items() if k.startswith("balance_")}
    return JSONResponse({"success": True, **balances})


@router.post("/api/store/admin/update-customer")
async def admin_update_customer(
    request: Request,
    email: str = Form(...),
    name: str = Form(...),
    username: str = Form(...),
    new_password: str = Form(""),
):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    username = username.lower().strip()
    if not _re.match(r"^[a-z0-9_]{3,20}$", username):
        return JSONResponse(
            {"success": False, "msg": "Username: 3-20 chars (letters/numbers/_)"}
        )
    if not name.strip():
        return JSONResponse({"success": False, "msg": "Name cannot be empty"})

    existing = await db.store_customers.find_one(
        {"username": username, "email": {"$ne": email}}
    )
    if existing:
        return JSONResponse({"success": False, "msg": "Username already taken"})

    update = {"name": name.strip(), "username": username}
    if new_password:
        if len(new_password) < 8:
            return JSONResponse(
                {"success": False, "msg": "Password must be at least 8 characters"}
            )
        update["password"] = hash_password(new_password)

    await db.store_customers.update_one({"email": email}, {"$set": update})
    return JSONResponse(
        {
            "success": True,
            "msg": "Customer updated!",
            "name": name.strip(),
            "username": username,
        }
    )


@router.post("/api/store/admin/email-request")
async def admin_email_request(
    request: Request, email: str = Form(...), new_email: str = Form(...)
):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    email = _normalize_email(email)
    new_email = _normalize_email(new_email)
    if not _re.match(r"^[^@]+@[^@]+\.[^@]+$", new_email):
        return JSONResponse({"success": False, "msg": "Invalid email address"})
    if new_email == email:
        return JSONResponse({"success": False, "msg": "Same as current email"})
    if await db.store_customers.find_one({"email": new_email}):
        return JSONResponse({"success": False, "msg": "Email already registered"})

    await _create_otp_challenge(email, "admin_email_change", {"new_email": new_email})
    return JSONResponse({"success": True, "msg": f"Code sent to {new_email}"})


@router.post("/api/store/admin/email-verify")
async def admin_email_verify(
    request: Request, email: str = Form(...), code: str = Form(...)
):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    email = _normalize_email(email)
    otp_doc, error_msg = await _verify_otp_challenge(
        email, "admin_email_change", code.strip()
    )
    if not otp_doc:
        return JSONResponse({"success": False, "msg": error_msg or "Invalid code"})

    payload = otp_doc.get("payload") or {}
    new_email = _normalize_email(payload.get("new_email", ""))
    if not new_email:
        await _clear_otp_challenge(email, "admin_email_change")
        return JSONResponse({"success": False, "msg": "Pending email change request is invalid"})
    if await db.store_customers.find_one({"email": new_email}):
        return JSONResponse(
            {"success": False, "msg": "Email just taken by someone else"}
        )

    user = await db.store_customers.find_one({"email": email})
    await db.store_customers.update_one(
        {"email": email}, {"$set": {"email": new_email}}
    )
    await db.store_orders.update_many({"email": email}, {"$set": {"email": new_email}})
    if user:
        await _store_sessions_collection().update_many(
            {"user_id": user.get("user_id")},
            {"$set": {"email": new_email, "updated_at": _utcnow()}},
        )
    await _clear_otp_challenge(email, "admin_email_change")
    return JSONResponse(
        {"success": True, "msg": "Email changed successfully!", "new_email": new_email}
    )


@router.post("/api/store/admin/set-avatar")
async def admin_set_avatar(
    request: Request, email: str = Form(...), avatar_b64: str = Form("")
):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})
    if avatar_b64 and len(avatar_b64) > 1_400_000:
        return JSONResponse({"success": False, "msg": "Image too large (max 1MB)"})
    if avatar_b64 and not avatar_b64.startswith("data:image/"):
        return JSONResponse({"success": False, "msg": "Invalid image format"})

    await db.store_customers.update_one(
        {"email": email}, {"$set": {"avatar": avatar_b64}}
    )
    msg = "Avatar updated!" if avatar_b64 else "Avatar removed!"
    return JSONResponse({"success": True, "msg": msg})


@router.get("/api/store/admin/catalog")
async def admin_catalog(request: Request):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized", "categories": []}, status_code=401)

    categories = await _build_admin_catalog_payload()
    return JSONResponse({"success": True, "categories": categories})


@router.post("/api/store/admin/catalog/product-channel")
async def admin_update_product_channel(
    request: Request,
    cat_id: str = Form(...),
    stock_key: str = Form(...),
    is_visible_web: str = Form('true'),
    is_visible_bot: str = Form('true'),
    allocation_web: str = Form(''),
    allocation_bot: str = Form(''),
):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"}, status_code=401)

    cat_id = str(cat_id or '').strip()
    stock_key = str(stock_key or '').strip()
    if not cat_id or not stock_key:
        return JSONResponse({"success": False, "msg": "Category and stock key are required."}, status_code=400)

    web_ok, allocation_web_value = _parse_allocation_form_value(allocation_web)
    bot_ok, allocation_bot_value = _parse_allocation_form_value(allocation_bot)
    if not web_ok or not bot_ok:
        return JSONResponse({"success": False, "msg": "Allocations must be whole numbers or left blank for unlimited."}, status_code=400)

    category = await db.store_categories.find_one({'products.stock_key': stock_key}, {'_id': 1})
    if not category:
        return JSONResponse({"success": False, "msg": "Product not found."}, status_code=404)
    if cat_id and str(category.get('_id') or '') != cat_id:
        return JSONResponse({"success": False, "msg": "Product category mismatch."}, status_code=404)

    update_ops = {
        '$set': {
            'products.$.is_visible_web': _normalize_channel_flag(is_visible_web, True),
            'products.$.is_visible_bot': _normalize_channel_flag(is_visible_bot, True),
        }
    }
    unset_ops = {}
    if allocation_web_value is None:
        unset_ops['products.$.allocation_web'] = ''
    else:
        update_ops['$set']['products.$.allocation_web'] = allocation_web_value

    if allocation_bot_value is None:
        unset_ops['products.$.allocation_bot'] = ''
    else:
        update_ops['$set']['products.$.allocation_bot'] = allocation_bot_value

    if unset_ops:
        update_ops['$unset'] = unset_ops

    result = await db.store_categories.update_one(
        {'_id': category.get('_id'), 'products.stock_key': stock_key},
        update_ops,
    )
    if result.matched_count == 0:
        return JSONResponse({"success": False, "msg": "Product not found."}, status_code=404)

    product_snapshot = await _build_inventory_product_snapshot(stock_key)
    return JSONResponse(
        {
            "success": True,
            "msg": "Product channel settings updated.",
            "product": product_snapshot,
        }
    )


@router.post("/api/store/admin/return-order")
async def admin_return_order(request: Request, order_id: str = Form(...)):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"}, status_code=401)

    ok, msg = await _process_store_order_return(order_id)
    return JSONResponse({"success": ok, "msg": msg}, status_code=200 if ok else 404)


@router.post("/api/store/admin/return-orders-bulk")
async def admin_return_orders_bulk(request: Request, order_ids: str = Form(...)):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"}, status_code=401)

    ids = _split_bulk_order_ids(order_ids)
    if not ids:
        return JSONResponse({"success": False, "msg": "No order IDs provided."}, status_code=400)

    done, failed = [], []
    for order_id in ids:
        ok, msg = await _process_store_order_return(order_id)
        if ok:
            done.append(order_id)
        else:
            failed.append(f"{order_id} ({msg})")

    return JSONResponse(
        {
            "success": len(done) > 0 and len(failed) == 0,
            "processed": len(done),
            "failed": len(failed),
            "done": done,
            "errors": failed,
            "msg": f"Processed {len(done)} returns, {len(failed)} failed.",
        },
        status_code=200 if len(done) > 0 or not failed else 400,
    )


@router.get("/api/store/admin/customer-orders")
async def admin_customer_orders(request: Request, email: str):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized", "orders": []}, status_code=401)

    orders = await db.store_orders.find({"email": email}).sort("date", -1).to_list(200)
    serialized = [_serialize_admin_order(order) for order in orders]
    return JSONResponse({"success": True, "orders": serialized})


@router.post("/api/store/admin/delete-customer")
async def admin_delete_customer(request: Request, email: str = Form(...)):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    email = _normalize_email(email)
    user = await db.store_customers.find_one({"email": email})
    result = await db.store_customers.delete_one({"email": email})
    if result.deleted_count == 0:
        return JSONResponse({"success": False, "msg": "Customer not found"})

    if user:
        await _invalidate_store_sessions_for_user(user.get("user_id"))
    await _otp_collection().delete_many({"email": email})
    return JSONResponse({"success": True, "msg": f"Account {email} deleted."})


# ==========================================
# 8. Support Tickets System
# ==========================================
CHAT_SUBJECT_MAX_LENGTH = 120
CHAT_MESSAGE_MAX_LENGTH = 2000
CHAT_HISTORY_LIMIT_MAX = 50
_CHAT_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def _chat_threads_collection():
    return db.support_tickets


def _chat_messages_collection():
    return db.support_ticket_messages


def _chat_room_name(thread_id: str) -> str:
    return f'thread:{thread_id}'


def _sanitize_chat_text(
    value: str,
    field_name: str,
    max_length: int,
    *,
    allow_blank: bool = False,
) -> str:
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n')
    text = _CHAT_CONTROL_CHARS_RE.sub('', text).strip()
    if not text and not allow_blank:
        raise ValueError(f'{field_name} is required.')
    if len(text) > max_length:
        raise ValueError(f'{field_name} is too long.')
    return text


def _sanitize_chat_name(value: str, fallback: str) -> str:
    try:
        return _sanitize_chat_text(value, 'Name', 80)
    except ValueError:
        return fallback


def _chat_preview(message: str, max_length: int = 80) -> str:
    compact = ' '.join(str(message or '').split())
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 3].rstrip() + '...'


def _chat_time_label(dt_value: datetime | None = None) -> str:
    if isinstance(dt_value, datetime):
        return dt_value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')
    return datetime.now().strftime('%Y-%m-%d %H:%M')


def _serialize_chat_thread(thread: dict) -> dict:
    message_count = int(thread.get('message_count') or len(thread.get('messages') or []))
    return {
        'ticket_id': str(thread.get('_id', '')),
        'subject': thread.get('subject', ''),
        'status': thread.get('status', 'open'),
        'email': thread.get('email', ''),
        'name': thread.get('name', 'Customer'),
        'created_at': thread.get('created_at') or _format_store_timestamp(thread.get('created_at_ts')),
        'last_message_at': thread.get('last_message_at_label') or _format_store_timestamp(thread.get('last_message_at')),
        'last_message_preview': thread.get('last_message_preview', ''),
        'message_count': message_count,
        'unread_customer_count': int(thread.get('unread_customer_count', 0) or 0),
        'unread_admin_count': int(thread.get('unread_admin_count', 0) or 0),
    }


def _serialize_chat_message(message: dict) -> dict:
    return {
        'message_id': str(message.get('_id', '')),
        'ticket_id': message.get('thread_id', ''),
        'sender': message.get('sender', 'customer'),
        'name': message.get('name', ''),
        'message': message.get('message', ''),
        'time': message.get('created_at_label') or _format_store_timestamp(message.get('created_at')),
        'created_at': _format_store_timestamp(message.get('created_at')),
        'is_read_by_customer': bool(message.get('read_by_customer_at')),
        'is_read_by_admin': bool(message.get('read_by_admin_at')),
    }


def _parse_legacy_chat_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    raw = str(value or '').strip()
    if not raw:
        return _utcnow()

    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return _utcnow()


async def _get_store_user_from_raw_session(raw_token: str, touch_session: bool = True) -> dict | None:
    if not raw_token:
        return None

    session = await _store_sessions_collection().find_one({'_id': _session_digest(raw_token)})
    if not session:
        return None

    now = _utcnow()
    expires_at = session.get('expires_at')
    if expires_at and expires_at <= now:
        await _store_sessions_collection().delete_one({'_id': session['_id']})
        return None

    if touch_session:
        await _store_sessions_collection().update_one(
            {'_id': session['_id']},
            {'$set': {'last_seen_at': now, 'updated_at': now}},
        )

    user = None
    if session.get('user_id') is not None:
        user = await db.store_customers.find_one({'user_id': session.get('user_id')})
    if not user and session.get('email'):
        user = await db.store_customers.find_one({'email': session.get('email')})
    if not user:
        await _store_sessions_collection().delete_one({'_id': session['_id']})
        return None

    if session.get('email') != user.get('email'):
        await _store_sessions_collection().update_one(
            {'_id': session['_id']},
            {'$set': {'email': user.get('email'), 'updated_at': now}},
        )

    return user


def _cookie_value_from_header(cookie_header: str, name: str) -> str:
    jar = SimpleCookie()
    if not cookie_header:
        return ''

    try:
        jar.load(cookie_header)
    except Exception:
        return ''

    morsel = jar.get(name)
    return morsel.value if morsel else ''


async def _authenticate_store_chat_socket(websocket: WebSocket) -> dict | None:
    role_hint = (websocket.query_params.get('role') or '').strip().lower()
    cookie_header = websocket.headers.get('cookie', '')

    if role_hint == 'admin':
        incoming = _cookie_value_from_header(cookie_header, 'admin_session')
        expected = SECRET_TOKEN or ''
        if incoming and expected and hmac.compare_digest(incoming, expected):
            return {'role': 'admin', 'name': 'Support Team', 'email': '', 'user_id': None}
        return None

    raw_token = _cookie_value_from_header(cookie_header, STORE_SESSION_COOKIE_NAME)
    user = await _get_store_user_from_raw_session(raw_token, touch_session=True)
    if user:
        return {
            'role': 'customer',
            'name': user.get('name', 'Customer'),
            'email': user.get('email', ''),
            'user_id': user.get('user_id'),
        }

    incoming = _cookie_value_from_header(cookie_header, 'admin_session')
    expected = SECRET_TOKEN or ''
    if incoming and expected and hmac.compare_digest(incoming, expected):
        return {'role': 'admin', 'name': 'Support Team', 'email': '', 'user_id': None}

    return None


async def _backfill_legacy_thread_messages(thread: dict) -> None:
    thread_id = str(thread.get('_id', ''))
    if not thread_id:
        return

    if await _chat_messages_collection().count_documents({'thread_id': thread_id}, limit=1):
        return

    legacy_messages = [item for item in (thread.get('messages') or []) if isinstance(item, dict)]
    if not legacy_messages:
        await _chat_threads_collection().update_one(
            {'_id': thread_id},
            {'$set': {'message_count': int(thread.get('message_count', 0) or 0), 'messages': []}},
        )
        return

    docs = []
    last_message = None
    for index, entry in enumerate(legacy_messages, start=1):
        body = _sanitize_chat_text(entry.get('message', ''), 'Message', CHAT_MESSAGE_MAX_LENGTH, allow_blank=True)
        if not body:
            continue

        sender = 'admin' if entry.get('sender') == 'admin' else 'customer'
        created_at = _parse_legacy_chat_timestamp(entry.get('time'))
        label = str(entry.get('time') or _chat_time_label(created_at))
        doc = {
            '_id': f'{thread_id}:legacy:{index}',
            'thread_id': thread_id,
            'email': thread.get('email', ''),
            'sender': sender,
            'name': _sanitize_chat_name(
                entry.get('name'),
                'Support Team' if sender == 'admin' else thread.get('name', 'Customer'),
            ),
            'message': body,
            'created_at': created_at,
            'created_at_label': label,
            'read_by_customer_at': created_at if sender == 'customer' else None,
            'read_by_admin_at': created_at if sender == 'admin' else None,
            'transport': 'legacy',
        }
        docs.append(doc)
        last_message = doc

    if docs:
        try:
            await _chat_messages_collection().insert_many(docs, ordered=False)
        except DuplicateKeyError:
            pass

        await _chat_threads_collection().update_one(
            {'_id': thread_id},
            {
                '$set': {
                    'message_count': len(docs),
                    'last_message_preview': _chat_preview(last_message['message']),
                    'last_message_at': last_message['created_at'],
                    'last_message_at_label': last_message['created_at_label'],
                    'updated_at': _utcnow(),
                    'messages': [],
                }
            },
        )
    else:
        await _chat_threads_collection().update_one(
            {'_id': thread_id},
            {'$set': {'message_count': 0, 'messages': []}},
        )


async def _get_chat_thread_for_actor(thread_id: str, actor: dict) -> dict | None:
    filters = {'_id': thread_id}
    if actor.get('role') == 'customer':
        filters['email'] = _normalize_email(actor.get('email', ''))

    thread = await _chat_threads_collection().find_one(filters)
    if not thread:
        return None

    await _backfill_legacy_thread_messages(thread)
    return await _chat_threads_collection().find_one(filters)


async def _generate_ticket_id() -> str:
    ticket_id = f'TKT-{random.randint(10000, 99999)}'
    while await _chat_threads_collection().find_one({'_id': ticket_id}):
        ticket_id = f'TKT-{random.randint(10000, 99999)}'
    return ticket_id


async def _append_chat_message(
    thread: dict,
    sender_role: str,
    sender_name: str,
    raw_message: str,
    *,
    transport: str,
) -> tuple[dict, dict]:
    clean_message = _sanitize_chat_text(raw_message, 'Message', CHAT_MESSAGE_MAX_LENGTH)
    now = _utcnow()
    label = _chat_time_label(now)
    thread_id = str(thread.get('_id'))

    message_doc = {
        '_id': uuid.uuid4().hex,
        'thread_id': thread_id,
        'email': thread.get('email', ''),
        'sender': sender_role,
        'name': _sanitize_chat_name(
            sender_name,
            'Support Team' if sender_role == 'admin' else thread.get('name', 'Customer'),
        ),
        'message': clean_message,
        'created_at': now,
        'created_at_label': label,
        'transport': transport,
        'read_by_customer_at': now if sender_role == 'customer' else None,
        'read_by_admin_at': now if sender_role == 'admin' else None,
    }
    await _chat_messages_collection().insert_one(message_doc)

    set_fields = {
        'messages': [],
        'updated_at': now,
        'last_message_at': now,
        'last_message_at_label': label,
        'last_message_preview': _chat_preview(clean_message),
        'last_sender': sender_role,
    }
    inc_fields = {'message_count': 1}

    if sender_role == 'admin':
        set_fields['unread_admin_count'] = 0
        set_fields['status'] = 'closed' if thread.get('status') == 'closed' else 'in_progress'
        inc_fields['unread_customer_count'] = 1
    else:
        set_fields['unread_customer_count'] = 0
        if thread.get('status') not in {'closed', 'in_progress'}:
            set_fields['status'] = 'open'
        inc_fields['unread_admin_count'] = 1

    await _chat_threads_collection().update_one(
        {'_id': thread_id},
        {'$set': set_fields, '$inc': inc_fields},
    )
    updated_thread = await _chat_threads_collection().find_one({'_id': thread_id})
    return message_doc, updated_thread


async def _mark_thread_read(thread_id: str, actor: dict) -> int:
    now = _utcnow()
    role = actor.get('role')
    read_field = 'read_by_customer_at' if role == 'customer' else 'read_by_admin_at'
    unread_field = 'unread_customer_count' if role == 'customer' else 'unread_admin_count'

    result = await _chat_messages_collection().update_many(
        {
            'thread_id': thread_id,
            'sender': {'$ne': role},
            '$or': [{read_field: {'$exists': False}}, {read_field: None}],
        },
        {'$set': {read_field: now}},
    )
    await _chat_threads_collection().update_one(
        {'_id': thread_id},
        {'$set': {unread_field: 0, 'updated_at': now, 'messages': []}},
    )
    return int(result.modified_count)


async def _load_thread_history(thread: dict, page: int, limit: int) -> tuple[list[dict], int, bool]:
    thread_id = str(thread.get('_id'))
    skip = max(page - 1, 0) * limit
    cursor = (
        _chat_messages_collection()
        .find({'thread_id': thread_id})
        .sort([('created_at', -1), ('_id', -1)])
        .skip(skip)
        .limit(limit)
    )
    messages_desc = await cursor.to_list(length=limit)
    messages = list(reversed(messages_desc))
    total_messages = int(thread.get('message_count') or await _chat_messages_collection().count_documents({'thread_id': thread_id}))
    has_more = total_messages > skip + len(messages_desc)
    return messages, total_messages, has_more


class StoreChatSocketManager:
    def __init__(self):
        self.connections: dict[str, dict] = {}
        self.rooms: defaultdict[str, set[str]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, actor: dict) -> str:
        await websocket.accept()
        connection_id = uuid.uuid4().hex
        self.connections[connection_id] = {
            'socket': websocket,
            'actor': actor,
            'rooms': set(),
        }
        return connection_id

    async def disconnect(self, connection_id: str) -> list[str]:
        meta = self.connections.pop(connection_id, None)
        if not meta:
            return []

        affected_rooms = list(meta['rooms'])
        for room in affected_rooms:
            members = self.rooms.get(room)
            if not members:
                continue
            members.discard(connection_id)
            if not members:
                self.rooms.pop(room, None)
        return affected_rooms

    def join(self, connection_id: str, room: str) -> None:
        if connection_id not in self.connections:
            return
        self.rooms[room].add(connection_id)
        self.connections[connection_id]['rooms'].add(room)

    def leave(self, connection_id: str, room: str) -> None:
        if connection_id not in self.connections:
            return
        members = self.rooms.get(room)
        if members:
            members.discard(connection_id)
            if not members:
                self.rooms.pop(room, None)
        self.connections[connection_id]['rooms'].discard(room)

    async def send_to_connection(self, connection_id: str, payload: dict) -> None:
        meta = self.connections.get(connection_id)
        if not meta:
            return
        await meta['socket'].send_json(payload)

    async def broadcast(self, room: str, payload: dict) -> None:
        stale = []
        for connection_id in list(self.rooms.get(room, set())):
            meta = self.connections.get(connection_id)
            if not meta:
                stale.append(connection_id)
                continue
            try:
                await meta['socket'].send_json(payload)
            except Exception:
                stale.append(connection_id)

        for connection_id in stale:
            await self.disconnect(connection_id)

    def presence_snapshot(self, room: str) -> dict:
        snapshot = {'customer_online': False, 'admin_online': False}
        for connection_id in self.rooms.get(room, set()):
            role = self.connections.get(connection_id, {}).get('actor', {}).get('role')
            if role == 'admin':
                snapshot['admin_online'] = True
            elif role == 'customer':
                snapshot['customer_online'] = True
        return snapshot


store_chat_manager = StoreChatSocketManager()


async def _broadcast_chat_presence(thread_id: str) -> None:
    room = _chat_room_name(thread_id)
    await store_chat_manager.broadcast(
        room,
        {
            'event': 'presence',
            'thread_id': thread_id,
            'presence': store_chat_manager.presence_snapshot(room),
        },
    )


async def _broadcast_chat_message(thread_id: str, thread: dict, message_doc: dict) -> None:
    await store_chat_manager.broadcast(
        _chat_room_name(thread_id),
        {
            'event': 'message:new',
            'thread_id': thread_id,
            'thread': _serialize_chat_thread(thread),
            'message': _serialize_chat_message(message_doc),
        },
    )


async def _broadcast_thread_status_change(thread_id: str, thread: dict) -> None:
    await store_chat_manager.broadcast(
        _chat_room_name(thread_id),
        {
            'event': 'thread:status_changed',
            'thread_id': thread_id,
            'thread': _serialize_chat_thread(thread),
        },
    )


@router.websocket('/ws/store-chat')
async def store_chat_websocket(websocket: WebSocket):
    actor = await _authenticate_store_chat_socket(websocket)
    if not actor:
        await websocket.close(code=4401)
        return

    connection_id = await store_chat_manager.connect(websocket, actor)
    await store_chat_manager.send_to_connection(
        connection_id,
        {
            'event': 'system:connected',
            'role': actor.get('role'),
            'name': actor.get('name'),
        },
    )

    try:
        while True:
            payload = await websocket.receive_json()
            action = str(payload.get('action') or '').strip().lower()
            thread_id = str(payload.get('thread_id') or '').strip()

            if action == 'ping':
                await store_chat_manager.send_to_connection(connection_id, {'event': 'pong'})
                continue

            if action == 'join_room':
                thread = await _get_chat_thread_for_actor(thread_id, actor)
                if not thread:
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'Thread not found.'},
                    )
                    continue

                room = _chat_room_name(thread_id)
                store_chat_manager.join(connection_id, room)
                await store_chat_manager.send_to_connection(
                    connection_id,
                    {
                        'event': 'system:joined',
                        'thread_id': thread_id,
                        'thread': _serialize_chat_thread(thread),
                    },
                )
                await _broadcast_chat_presence(thread_id)
                continue

            if action == 'leave_room':
                if thread_id:
                    store_chat_manager.leave(connection_id, _chat_room_name(thread_id))
                    await _broadcast_chat_presence(thread_id)
                continue

            if action == 'send_message':
                thread = await _get_chat_thread_for_actor(thread_id, actor)
                if not thread:
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'Thread not found.'},
                    )
                    continue
                if actor.get('role') == 'customer' and thread.get('status') == 'closed':
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'This ticket is closed.'},
                    )
                    continue

                room = _chat_room_name(thread_id)
                store_chat_manager.join(connection_id, room)
                try:
                    message_doc, updated_thread = await _append_chat_message(
                        thread,
                        actor.get('role', 'customer'),
                        actor.get('name', 'Customer'),
                        payload.get('message', ''),
                        transport='ws',
                    )
                except ValueError as exc:
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': str(exc)},
                    )
                    continue

                await _broadcast_chat_message(thread_id, updated_thread, message_doc)
                continue

            if action == 'mark_read':
                thread = await _get_chat_thread_for_actor(thread_id, actor)
                if not thread:
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'Thread not found.'},
                    )
                    continue

                room = _chat_room_name(thread_id)
                store_chat_manager.join(connection_id, room)
                read_count = await _mark_thread_read(thread_id, actor)
                updated_thread = await _chat_threads_collection().find_one({'_id': thread_id})
                await store_chat_manager.broadcast(
                    room,
                    {
                        'event': 'message:read',
                        'thread_id': thread_id,
                        'reader_role': actor.get('role'),
                        'read_count': read_count,
                        'thread': _serialize_chat_thread(updated_thread or thread),
                    },
                )
                continue

            await store_chat_manager.send_to_connection(
                connection_id,
                {'event': 'error', 'thread_id': thread_id, 'msg': 'Unsupported chat action.'},
            )
    except WebSocketDisconnect:
        pass
    finally:
        affected_rooms = await store_chat_manager.disconnect(connection_id)
        for room in affected_rooms:
            if room.startswith('thread:'):
                await _broadcast_chat_presence(room.split(':', 1)[1])


@router.post('/api/store/tickets/create')
async def create_ticket(
    request: Request,
    subject: str = Form(...),
    message: str = Form(...),
):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'msg': 'Please login first.'}, status_code=401)

    user = await db.store_customers.find_one({'email': email})
    if not user:
        return JSONResponse({'success': False, 'msg': 'Account not found.'}, status_code=404)

    try:
        clean_subject = _sanitize_chat_text(subject, 'Subject', CHAT_SUBJECT_MAX_LENGTH)
        clean_message = _sanitize_chat_text(message, 'Message', CHAT_MESSAGE_MAX_LENGTH)
    except ValueError as exc:
        return JSONResponse({'success': False, 'msg': str(exc)}, status_code=400)

    ticket_id = await _generate_ticket_id()
    now = _utcnow()
    thread_doc = {
        '_id': ticket_id,
        'email': _normalize_email(email),
        'name': _sanitize_chat_name(user.get('name', 'Customer'), 'Customer'),
        'subject': clean_subject,
        'status': 'open',
        'created_at': _chat_time_label(now),
        'created_at_ts': now,
        'updated_at': now,
        'last_message_at': now,
        'last_message_at_label': _chat_time_label(now),
        'last_message_preview': '',
        'message_count': 0,
        'unread_customer_count': 0,
        'unread_admin_count': 0,
        'messages': [],
    }

    try:
        await _chat_threads_collection().insert_one(thread_doc)
        message_doc, updated_thread = await _append_chat_message(
            thread_doc,
            'customer',
            user.get('name', 'Customer'),
            clean_message,
            transport='rest',
        )
    except Exception:
        await _chat_threads_collection().delete_one({'_id': ticket_id})
        raise

    return JSONResponse(
        {
            'success': True,
            'msg': f'Ticket {ticket_id} submitted!',
            'ticket_id': ticket_id,
            'thread': _serialize_chat_thread(updated_thread),
            'message': _serialize_chat_message(message_doc),
        }
    )


@router.get('/api/store/tickets/my')
async def get_my_tickets(request: Request):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'tickets': [], 'force_logout': True}, status_code=401)

    tickets = (
        await _chat_threads_collection()
        .find({'email': _normalize_email(email)})
        .sort([('last_message_at', -1), ('created_at_ts', -1)])
        .to_list(100)
    )
    serialized = [_serialize_chat_thread(ticket) for ticket in tickets]
    return JSONResponse({'success': True, 'tickets': serialized})


@router.get('/api/store/tickets/history')
async def get_ticket_history(
    request: Request,
    ticket_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=CHAT_HISTORY_LIMIT_MAX),
):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'msg': 'Please login first.'}, status_code=401)

    actor = {'role': 'customer', 'email': _normalize_email(email)}
    thread = await _get_chat_thread_for_actor(ticket_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    messages, total_messages, has_more = await _load_thread_history(thread, page, limit)
    return JSONResponse(
        {
            'success': True,
            'thread': _serialize_chat_thread(thread),
            'messages': [_serialize_chat_message(message) for message in messages],
            'page': page,
            'limit': limit,
            'has_more': has_more,
            'total_messages': total_messages,
        }
    )


@router.post('/api/store/tickets/reply')
async def customer_reply_ticket(
    request: Request,
    ticket_id: str = Form(...),
    message: str = Form(...),
):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'msg': 'Please login first.'}, status_code=401)

    actor = {'role': 'customer', 'email': _normalize_email(email)}
    thread = await _get_chat_thread_for_actor(ticket_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)
    if thread.get('status') == 'closed':
        return JSONResponse({'success': False, 'msg': 'This ticket is closed.'}, status_code=409)

    user = await db.store_customers.find_one({'email': _normalize_email(email)})
    try:
        message_doc, updated_thread = await _append_chat_message(
            thread,
            'customer',
            (user or {}).get('name', 'Customer'),
            message,
            transport='rest',
        )
    except ValueError as exc:
        return JSONResponse({'success': False, 'msg': str(exc)}, status_code=400)

    await _broadcast_chat_message(ticket_id, updated_thread, message_doc)
    return JSONResponse(
        {
            'success': True,
            'msg': 'Reply sent!',
            'thread': _serialize_chat_thread(updated_thread),
            'message': _serialize_chat_message(message_doc),
        }
    )


@router.get('/api/store/admin/tickets/history')
async def admin_ticket_history(
    request: Request,
    ticket_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=CHAT_HISTORY_LIMIT_MAX),
):
    if not admin_check(request):
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=403)

    thread = await _get_chat_thread_for_actor(ticket_id, {'role': 'admin'})
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    messages, total_messages, has_more = await _load_thread_history(thread, page, limit)
    return JSONResponse(
        {
            'success': True,
            'thread': _serialize_chat_thread(thread),
            'messages': [_serialize_chat_message(message) for message in messages],
            'page': page,
            'limit': limit,
            'has_more': has_more,
            'total_messages': total_messages,
        }
    )


@router.post('/api/store/admin/tickets/reply')
async def admin_reply_ticket(
    request: Request,
    ticket_id: str = Form(...),
    message: str = Form(...),
):
    if not admin_check(request):
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=403)

    thread = await _get_chat_thread_for_actor(ticket_id, {'role': 'admin'})
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    try:
        message_doc, updated_thread = await _append_chat_message(
            thread,
            'admin',
            'Support Team',
            message,
            transport='rest',
        )
    except ValueError as exc:
        return JSONResponse({'success': False, 'msg': str(exc)}, status_code=400)

    await _broadcast_chat_message(ticket_id, updated_thread, message_doc)
    return JSONResponse(
        {
            'success': True,
            'msg': 'Reply sent!',
            'thread': _serialize_chat_thread(updated_thread),
            'message': _serialize_chat_message(message_doc),
        }
    )


@router.post('/api/store/admin/tickets/change-status')
async def admin_change_ticket_status(
    request: Request,
    ticket_id: str = Form(...),
    status: str = Form(...),
):
    if not admin_check(request):
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=403)

    if status not in ('open', 'in_progress', 'closed'):
        return JSONResponse({'success': False, 'msg': 'Invalid status.'}, status_code=400)

    result = await _chat_threads_collection().update_one(
        {'_id': ticket_id},
        {'$set': {'status': status, 'updated_at': _utcnow(), 'messages': []}},
    )
    if result.matched_count == 0:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    updated_thread = await _chat_threads_collection().find_one({'_id': ticket_id})
    await _broadcast_thread_status_change(ticket_id, updated_thread)
    return JSONResponse({'success': True, 'msg': f'Status updated to {status}.', 'thread': _serialize_chat_thread(updated_thread)})


@router.get('/api/store/admin/tickets/view')
async def admin_view_ticket(request: Request, ticket_id: str):
    if not admin_check(request):
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=403)

    thread = await _get_chat_thread_for_actor(ticket_id, {'role': 'admin'})
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    return JSONResponse({'success': True, 'ticket': _serialize_chat_thread(thread)})










