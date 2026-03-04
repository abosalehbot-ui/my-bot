from fastapi import APIRouter, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import hashlib
import random
import httpx
import traceback
import uuid
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional
from pymongo.errors import DuplicateKeyError, OperationFailure

# ─── Shared imports (no duplicate connections) ──────────────────────────
from database import db, get_next_order_id
from config import SECRET_TOKEN, MONGO_URI

router = APIRouter()
templates = Jinja2Templates(directory="templates")

GOOGLE_CLIENT_ID = "671995925834-4bf0od4fm0pkkhvkfrvqh41h6rpb574v.apps.googleusercontent.com"


# ── Pydantic models لـ Checkout Cart ──────────────────────────────────────
class CartItem(BaseModel):
    stock_key: str
    price:     float
    currency:  str
    quantity:  int

class CheckoutRequest(BaseModel):
    cart: List[CartItem]
    transaction_id: Optional[str] = ""


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

async def generate_unique_id():
    while True:
        new_id = random.randint(10000000, 99999999)
        if not await db.store_customers.find_one({"user_id": new_id}):
            return new_id

async def log_wallet_txn(email: str, amount: float, currency: str, note: str, ref: str = "", session=None):
    await db.store_wallet_ledger.insert_one({
        "email": email,
        "amount": float(amount),
        "currency": currency.upper(),
        "note": note,
        "ref": ref,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ts": datetime.now(),
    }, session=session)


def _sanitize_positive_int(val, field: str, max_value: int = 1000):
    if isinstance(val, bool) or val is None:
        raise ValueError(f"{field} must be a positive integer")
    try:
        num = int(val)
    except Exception:
        raise ValueError(f"{field} must be a positive integer")
    if num <= 0 or num > max_value:
        raise ValueError(f"{field} must be between 1 and {max_value}")
    return num


def _normalize_currency(cur: str) -> str:
    c = (cur or "").upper().strip()
    if not c or not c.isalnum() or len(c) > 6:
        raise ValueError("Invalid currency")
    return c


async def _get_product_price(stock_key: str, currency: str):
    cat = await db.store_categories.find_one({"products.stock_key": stock_key}, {"products.$": 1})
    if not cat or not cat.get("products"):
        return None
    product = cat["products"][0]
    prices = product.get("prices") or {
        "EGP": product.get("price_egp", 0),
        "USD": product.get("price_usd", 0),
    }
    val = prices.get(currency)
    if val is None:
        val = prices.get(currency.lower())
    try:
        price = float(val)
    except Exception:
        return None
    return price if price > 0 else None


async def _acquire_txn_lock(transaction_id: str, email: str, action: str):
    txid = (transaction_id or '').strip() or str(uuid.uuid4())
    try:
        await db.store_txn_locks.insert_one({
            "_id": txid,
            "email": email,
            "action": action,
            "status": "processing",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "ts": datetime.now(),
        })
    except DuplicateKeyError:
        return None
    return txid


async def _finish_txn_lock(txid: str, status: str, msg: str):
    await db.store_txn_locks.update_one(
        {"_id": txid},
        {"$set": {"status": status, "msg": msg, "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M")}}
    )


async def _purchase_one_unit(email: str, user_name: str, stock_key: str, currency: str):
    currency = _normalize_currency(currency)
    price = await _get_product_price(stock_key, currency)
    if price is None:
        return {"success": False, "msg": "Invalid product/currency price."}

    bal_field = f"balance_{currency.lower()}"

    async def _run_with_session(session):
        code_doc = await db.stock.find_one_and_delete({"category": stock_key}, session=session)
        if not code_doc:
            return {"success": False, "msg": "Out of stock"}

        bal_res = await db.store_customers.update_one(
            {"email": email, bal_field: {"$gte": price}, "is_banned": {"$ne": True}, "balance_frozen": {"$ne": True}},
            {"$inc": {bal_field: -price}},
            session=session,
        )
        if bal_res.modified_count != 1:
            raise ValueError(f"Insufficient {currency} balance")

        stat = await db.stats.find_one_and_update(
            {"_id": "global_stats"},
            {"$inc": {"last_order_id": 1}},
            upsert=True,
            return_document=True,
            session=session,
        )
        order_id = f"{stat['last_order_id']}S"
        now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")
        code_str = str(code_doc.get("code") or code_doc["_id"])

        await db.store_orders.insert_one({
            "_id": order_id,
            "email": email,
            "name": user_name,
            "category": stock_key,
            "code": code_str,
            "price": price,
            "currency": currency,
            "date": now_str,
        }, session=session)

        await db.codes_map.insert_one({
            "code": code_str,
            "order_id": order_id,
            "name": f"{user_name} (Web)",
            "time": now_str,
            "source": "Web Store",
        }, session=session)

        await log_wallet_txn(email, -price, currency, f"Order #{order_id}", ref=order_id, session=session)
        return {"success": True, "order_id": order_id, "code": code_str, "price": price, "currency": currency}

    # Try transaction (all-or-nothing). Fallback to atomic compensating flow.
    try:
        from database import db_client
        async with await db_client.start_session() as session:
            async with session.start_transaction():
                return await _run_with_session(session)
    except (OperationFailure, ValueError):
        raise
    except Exception:
        pass

    code_doc = await db.stock.find_one_and_delete({"category": stock_key})
    if not code_doc:
        return {"success": False, "msg": "Out of stock"}

    bal_res = await db.store_customers.update_one(
        {"email": email, bal_field: {"$gte": price}, "is_banned": {"$ne": True}, "balance_frozen": {"$ne": True}},
        {"$inc": {bal_field: -price}},
    )
    if bal_res.modified_count != 1:
        await db.stock.insert_one({"code": code_doc.get("code") or str(code_doc.get("_id")), "category": stock_key, "added_at": datetime.now()})
        return {"success": False, "msg": f"Insufficient {currency} balance"}

    stat = await db.stats.find_one_and_update({"_id": "global_stats"}, {"$inc": {"last_order_id": 1}}, upsert=True, return_document=True)
    order_id = f"{stat['last_order_id']}S"
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")
    code_str = str(code_doc.get("code") or code_doc["_id"])

    await db.store_orders.insert_one({
        "_id": order_id,
        "email": email,
        "name": user_name,
        "category": stock_key,
        "code": code_str,
        "price": price,
        "currency": currency,
        "date": now_str,
    })
    await db.codes_map.insert_one({"code": code_str, "order_id": order_id, "name": f"{user_name} (Web)", "time": now_str, "source": "Web Store"})
    await log_wallet_txn(email, -price, currency, f"Order #{order_id}", ref=order_id)
    return {"success": True, "order_id": order_id, "code": code_str, "price": price, "currency": currency}

# ==========================================
# 1. الواجهة الرئيسية للمتجر
# ==========================================
@router.get("/", response_class=HTMLResponse)
async def public_storefront(request: Request):
    try:
        settings    = await db.settings.find_one({"_id": "config"})
        maintenance = settings.get("maintenance", False) if settings else False

        user = None
        email = request.cookies.get("store_session")
        if email:
            user = await db.store_customers.find_one({"email": email})

        categories    = await db.store_categories.find().to_list(100)
        stock_details = {}
        
        for cat in categories:
            # 1. تحويل الآيدي لنص عشان مايعملش Error في الـ HTML
            if "_id" in cat:
                cat["_id"] = str(cat["_id"])
                
            # 2. الحماية من أن يكون قسم المنتجات فارغ تماماً (null)
            products = cat.get("products") or []
            for p in products:
                # 3. الحماية من المنتجات اللي ملهاش stock_key
                sk = p.get("stock_key")
                if sk and sk not in stock_details:
                    stock_details[sk] = await db.stock.count_documents({"category": sk})
                # 4. توحيد prices لدعم المنتجات القديمة والجديدة
                if "prices" not in p:
                    p["prices"] = {
                        "EGP": p.get("price_egp", 0),
                        "USD": p.get("price_usd", 0),
                    }

        # 5. جلب العملات المتاحة من قاعدة البيانات
        currencies = await db.store_currencies.find().to_list(100)
        if not currencies:
            currencies = [{"_id": "EGP", "symbol": "EGP"}, {"_id": "USD", "symbol": "USD"}]

        return templates.TemplateResponse("storefront.html", {
            "request":     request,
            "categories":  categories,
            "stock":       stock_details,
            "client_id":   GOOGLE_CLIENT_ID,
            "maintenance": maintenance,
            "currencies":  currencies,
            "user":        user,
        })
    except Exception as e:
        # 6. طباعة الخطأ بالكامل على الشاشة بدل الإيرور 500 المزعج
        error_details = traceback.format_exc()
        print(error_details)
        return HTMLResponse(
            content=f"<div style='direction:ltr; text-align:left; background:#111; color:#7dfc89; padding:20px; font-family:monospace; height:100vh; overflow:auto;'><h2>System Error Debugger:</h2><pre>{error_details}</pre></div>", 
            status_code=500
        )

    return templates.TemplateResponse("storefront.html", {
        "request":     request,
        "categories":  categories,
        "stock":       stock_details,
        "client_id":   GOOGLE_CLIENT_ID,
        "maintenance": maintenance,
        "user":        user if 'user' in locals() else None,
    })

# ==========================================
# 2. أنظمة التسجيل والمصادقة
# ==========================================
def get_user_data(user):
    return {
        "email":       user["email"],
        "name":        user["name"],
        "username":    user.get("username", ""),
        "balance_egp": user.get("balance_egp", 0),
        "balance_usd": user.get("balance_usd", 0),
    }

@router.post("/api/store/login-manual")
async def login_manual(request: Request, email: str = Form(...), password: str = Form(...)):
    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "Account not found. Please sign up."})
    if not user.get("password"):
        return JSONResponse({"success": False, "msg": "Please login with Google or Telegram."})
    if user["password"] != hash_password(password):
        return JSONResponse({"success": False, "msg": "Incorrect password!"})
    if user.get("is_banned", False):
        return JSONResponse({"success": False, "msg": "Your account has been suspended by the admin."})

    response = JSONResponse({"success": True, **get_user_data(user)})
    response.set_cookie(key="store_session", value=user["email"], httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/signup-request")
async def signup_request(request: Request, name: str = Form(...), username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if len(password) < 8:
        return JSONResponse({"success": False, "msg": "Password must be at least 8 characters!"})
    if await db.store_customers.find_one({"email": email}):
        return JSONResponse({"success": False, "msg": "Email is already registered!"})
    if await db.store_customers.find_one({"username": username.lower()}):
        return JSONResponse({"success": False, "msg": "Username is already taken!"})

    code = str(random.randint(100000, 999999))
    await db.otps.update_one(
        {"email": email},
        {"$set": {"code": code, "name": name, "username": username.lower(),
                  "password": hash_password(password), "type": "signup", "created_at": datetime.now()}},
        upsert=True
    )
    print(f"\n[MOCK EMAIL] To: {email} | SIGNUP OTP: {code}\n")
    return JSONResponse({"success": True, "msg": "OTP sent to your email!"})

@router.post("/api/store/signup-verify")
async def signup_verify(request: Request, email: str = Form(...), code: str = Form(...)):
    otp_doc = await db.otps.find_one({"email": email, "code": code, "type": "signup"})
    if not otp_doc:
        return JSONResponse({"success": False, "msg": "Invalid verification code!"})
    if (datetime.now() - otp_doc["created_at"]).total_seconds() > 300:
        return JSONResponse({"success": False, "msg": "Code expired! Please try again."})

    user_id = await generate_unique_id()
    await db.store_customers.insert_one({
        "user_id":     user_id,
        "username":    otp_doc["username"],
        "email":       email,
        "name":        otp_doc["name"],
        "password":    otp_doc["password"],
        "balance_egp": 0,
        "balance_usd": 0,
        "is_banned":   False,
        "balance_frozen": False,
        "created_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    await db.otps.delete_one({"_id": otp_doc["_id"]})

    response = JSONResponse({"success": True, "email": email, "name": otp_doc["name"],
                             "username": otp_doc["username"], "balance_egp": 0, "balance_usd": 0})
    response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/google-login")
async def google_login(request: Request, credential: str = Form(...)):
    async with httpx.AsyncClient() as http:
        res = await http.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}")
        if res.status_code != 200:
            return JSONResponse({"success": False, "msg": "Google verification failed."})
        user_info = res.json()
        if user_info.get("aud") != GOOGLE_CLIENT_ID:
            return JSONResponse({"success": False, "msg": "Invalid token."})

        email = user_info.get("email")
        name  = user_info.get("name")
        user  = await db.store_customers.find_one({"email": email})

        if not user:
            user_id  = await generate_unique_id()
            username = email.split("@")[0].lower() + str(random.randint(10, 99))
            user = {"user_id": user_id, "username": username, "email": email, "name": name,
                    "balance_egp": 0, "balance_usd": 0, "is_banned": False, "balance_frozen": False, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
            await db.store_customers.insert_one(user)

        if user.get("is_banned", False):
            return JSONResponse({"success": False, "msg": "Your account has been suspended by the admin."})

        response = JSONResponse({"success": True, **get_user_data(user)})
        response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
        return response

@router.post("/api/store/telegram-login")
async def telegram_login(request: Request, tg_id: str = Form(...), name: str = Form(...), username: str = Form("")):
    email = f"tg_{tg_id}@telegram.zone"
    user  = await db.store_customers.find_one({"email": email})

    if not user:
        user_id        = await generate_unique_id()
        final_username = username.lower() if username else f"user{tg_id}"
        user = {"user_id": user_id, "username": final_username, "email": email, "name": name,
                "balance_egp": 0, "balance_usd": 0, "is_banned": False, "balance_frozen": False, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        await db.store_customers.insert_one(user)

    if user.get("is_banned", False):
        return JSONResponse({"success": False, "msg": "Your account has been suspended by the admin."})

    response = JSONResponse({"success": True, **get_user_data(user)})
    response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/logout")
async def store_logout():
    response = JSONResponse({"success": True})
    response.delete_cookie("store_session")
    return response

# ==========================================
# 3. نظام استعادة كلمة المرور
# ==========================================
@router.post("/api/store/forgot-password")
async def forgot_password(request: Request, email: str = Form(...)):
    if not await db.store_customers.find_one({"email": email}):
        return JSONResponse({"success": False, "msg": "Account with this email does not exist."})

    code = str(random.randint(100000, 999999))
    await db.otps.update_one(
        {"email": email},
        {"$set": {"code": code, "type": "reset", "created_at": datetime.now()}},
        upsert=True
    )
    return JSONResponse({"success": True, "msg": "Password reset code sent to your email!"})

@router.post("/api/store/reset-password")
async def reset_password(request: Request, email: str = Form(...), code: str = Form(...), new_password: str = Form(...)):
    if len(new_password) < 8:
        return JSONResponse({"success": False, "msg": "Password must be at least 8 characters!"})

    otp_doc = await db.otps.find_one({"email": email, "code": code, "type": "reset"})
    if not otp_doc:
        return JSONResponse({"success": False, "msg": "Invalid or expired reset code!"})

    await db.store_customers.update_one({"email": email}, {"$set": {"password": hash_password(new_password)}})
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    return JSONResponse({"success": True, "msg": "Password updated successfully! You can now login."})

# ==========================================
# 4. الشراء وسجل الطلبات
# ==========================================
@router.post("/api/store/buy")
async def customer_buy(
    request: Request,
    stock_key: str = Form(...),
    currency: str = Form(...),
    transaction_id: str = Form(""),
    price: float = Form(0),
):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Unauthorized! Please login again.", "force_logout": True})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "Account not found!", "force_logout": True})
    if user.get("is_banned", False):
        return JSONResponse({"success": False, "msg": "Your account is suspended.", "force_logout": True})
    if user.get("balance_frozen", False):
        return JSONResponse({"success": False, "msg": "Your balance is currently frozen. Please contact support."})

    txid = await _acquire_txn_lock(transaction_id, email, "buy")
    if not txid:
        return JSONResponse({"success": False, "msg": "Duplicate transaction detected. This payment was already processed."})

    try:
        result = await _purchase_one_unit(email, user.get("name", "Customer"), stock_key, currency)
        if not result.get("success"):
            await _finish_txn_lock(txid, "failed", result.get("msg", "failed"))
            return JSONResponse({"success": False, "msg": result.get("msg", "Purchase failed")})

        bal_field = f"balance_{result['currency'].lower()}"
        fresh_user = await db.store_customers.find_one(
            {"email": email},
            {bal_field: 1},
        )
        new_balance = float((fresh_user or {}).get(bal_field, 0))

        await _finish_txn_lock(txid, "done", "ok")
        return JSONResponse({
            "success": True,
            "code": result["code"],
            "new_balance": new_balance,
            "currency": result["currency"],
            "msg": "Purchase successful!",
            "transaction_id": txid,
        })
    except ValueError as e:
        await _finish_txn_lock(txid, "failed", str(e))
        return JSONResponse({"success": False, "msg": str(e)})
    except Exception:
        await _finish_txn_lock(txid, "failed", "internal_error")
        return JSONResponse({"success": False, "msg": "Purchase failed due to a server error."})

@router.get("/api/store/my-orders")
async def get_my_orders(request: Request):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "orders": []})

    orders = await db.store_orders.find({"email": email}).sort("date", -1).to_list(100)
    for o in orders:
        o["order_id"] = str(o.get("_id", ""))
    return JSONResponse({"success": True, "orders": orders})

@router.get("/api/store/wallet-history")
async def wallet_history(request: Request):
    email = request.cookies.get("store_session")
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
    """Secure checkout with atomic wallet deduction + atomic stock reservation per unit."""
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Unauthorized! Please login again.", "force_logout": True})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "Account not found!", "force_logout": True})
    if user.get("is_banned", False):
        return JSONResponse({"success": False, "msg": "Your account is suspended.", "force_logout": True})
    if user.get("balance_frozen", False):
        return JSONResponse({"success": False, "msg": "Your balance is currently frozen. Please contact support."})

    txid = await _acquire_txn_lock(payload.transaction_id, email, "checkout_cart")
    if not txid:
        return JSONResponse({"success": False, "msg": "Duplicate transaction detected. This checkout was already processed."})

    results = []
    try:
        for item in payload.cart:
            qty = _sanitize_positive_int(item.quantity, "quantity", max_value=100)
            currency = _normalize_currency(item.currency)

            for _ in range(qty):
                unit = await _purchase_one_unit(email, user.get("name", "Customer"), item.stock_key, currency)
                if not unit.get("success"):
                    results.append({"stock_key": item.stock_key, "status": "Failed", "msg": unit.get("msg", "Failed")})
                    break

                results.append({
                    "stock_key": item.stock_key,
                    "status": "Success",
                    "code": unit["code"],
                    "price": unit["price"],
                    "currency": unit["currency"],
                    "order_id": unit["order_id"],
                })

        fresh_user = await db.store_customers.find_one({"email": email})
        balances_src = fresh_user or {}
        new_balances = {
            k: v for k, v in balances_src.items() if k.startswith("balance_")
        }
        await _finish_txn_lock(txid, "done", "ok")
        return JSONResponse({
            "success": True,
            "results": results,
            "new_balances": new_balances,
            "msg": "Checkout completed!",
            "transaction_id": txid,
        })
    except ValueError as e:
        await _finish_txn_lock(txid, "failed", str(e))
        return JSONResponse({"success": False, "msg": str(e)})
    except Exception:
        await _finish_txn_lock(txid, "failed", "internal_error")
        return JSONResponse({"success": False, "msg": "Checkout failed due to server error."})

# ==========================================
# 5. لوحة أدمن المتجر
# ==========================================
@router.get("/store-admin", response_class=HTMLResponse)
async def store_admin_page(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login")

    settings    = await db.settings.find_one({"_id": "config"})
    maintenance = settings.get("maintenance", False) if settings else False

    store_customers = await db.store_customers.find().sort("created_at", -1).to_list(200)
    
    # تحويل الـ ObjectId لـ string عشان الـ Error 500
    for customer in store_customers:
        if "_id" in customer:
            customer["_id"] = str(customer["_id"])

    store_orders    = await db.store_orders.find().sort("date", -1).to_list(500)

    # ── Support Tickets ──────────────────────────────────────────────────
    try:
        open_tickets    = await db.support_tickets.find({"status": {"$ne": "closed"}}).sort("created_at", -1).to_list(200)
        support_tickets = await db.support_tickets.find().sort("created_at", -1).to_list(500)
        for t in open_tickets:
            t["ticket_id"] = str(t["_id"])
        for t in support_tickets:
            t["ticket_id"] = str(t["_id"])
    except Exception:
        open_tickets    = []
        support_tickets = []

    return templates.TemplateResponse("store_admin.html", {
        "request":         request,
        "store_customers": store_customers,
        "store_orders":    store_orders,
        "maintenance":     maintenance,
        "open_tickets":    open_tickets,
        "support_tickets": support_tickets,
    })

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
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    try:
        amount_int = _sanitize_positive_int(amount, "amount", max_value=1_000_000)
        currency = _normalize_currency(currency)
    except ValueError as e:
        return JSONResponse({"success": False, "msg": str(e)})

    txid = await _acquire_txn_lock(transaction_id, email, f"admin_balance_{action}")
    if not txid:
        return JSONResponse({"success": False, "msg": "Duplicate transaction detected."})

    bal_field = f"balance_{currency.lower()}"

    if action == "add":
        res = await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: amount_int}})
        if res.modified_count != 1:
            await _finish_txn_lock(txid, "failed", "user_not_found")
            return JSONResponse({"success": False, "msg": "User not found"})
        await log_wallet_txn(email, amount_int, currency, "Top-up (Admin)", ref=txid)
    elif action == "sub":
        res = await db.store_customers.update_one({"email": email, bal_field: {"$gte": amount_int}}, {"$inc": {bal_field: -amount_int}})
        if res.modified_count != 1:
            await _finish_txn_lock(txid, "failed", "insufficient_or_not_found")
            return JSONResponse({"success": False, "msg": f"Insufficient {currency} balance or user not found."})
        await log_wallet_txn(email, -amount_int, currency, "Manual deduction (Admin)", ref=txid)
    else:
        await _finish_txn_lock(txid, "failed", "invalid_action")
        return JSONResponse({"success": False, "msg": "Invalid action"})

    await _finish_txn_lock(txid, "done", "ok")
    return JSONResponse({"success": True, "msg": f"{currency} balance updated successfully!", "transaction_id": txid})

# Endpoint تجميد الرصيد أو حظر الحساب
@router.post("/api/store/admin/toggle-status")
async def admin_toggle_status(request: Request, email: str = Form(...), action: str = Form(...)):
    if not check_auth(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})
        
    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "User not found"})
        
    if action == "ban":
        new_status = not user.get("is_banned", False)
        await db.store_customers.update_one({"email": email}, {"$set": {"is_banned": new_status}})
        msg = "Account Suspended Successfully!" if new_status else "Account Reactivated Successfully!"
    elif action == "freeze":
        new_status = not user.get("balance_frozen", False)
        await db.store_customers.update_one({"email": email}, {"$set": {"balance_frozen": new_status}})
        msg = "Balance Frozen Successfully!" if new_status else "Balance Unfrozen Successfully!"
    else:
        return JSONResponse({"success": False, "msg": "Invalid action"})
        
    return JSONResponse({"success": True, "msg": msg, "new_status": new_status})

# ==========================================
# 6. Profile — Get / Edit / Avatar / Password / Email
# ==========================================

import base64, re as _re

def _make_username(name: str, user_id: int) -> str:
    base = _re.sub(r'[^a-z0-9]', '', name.lower())[:12] or "user"
    return f"{base}{str(user_id)[-4:]}"

@router.get("/api/store/me")
async def get_profile(request: Request):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "User not found"})

    if not user.get("username"):
        auto_uname = _make_username(user["name"], user["user_id"])
        await db.store_customers.update_one({"email": email}, {"$set": {"username": auto_uname}})
        user["username"] = auto_uname

    return JSONResponse({
        "success":     True,
        "user_id":     user.get("user_id"),
        "name":        user.get("name"),
        "username":    user.get("username"),
        "email":       user.get("email"),
        "balance_egp": user.get("balance_egp", 0),
        "balance_usd": user.get("balance_usd", 0),
        "avatar":      user.get("avatar", ""),
        "created_at":  user.get("created_at", ""),
    })

@router.post("/api/store/update-profile")
async def update_profile(request: Request, name: str = Form(...), username: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    username = username.lower().strip()
    if not _re.match(r'^[a-z0-9_]{3,20}$', username):
        return JSONResponse({"success": False, "msg": "Username must be 3-20 characters (letters, numbers, _)"})
    if not name.strip():
        return JSONResponse({"success": False, "msg": "Name cannot be empty"})

    existing = await db.store_customers.find_one({"username": username, "email": {"$ne": email}})
    if existing:
        return JSONResponse({"success": False, "msg": "Username is already taken!"})

    await db.store_customers.update_one(
        {"email": email},
        {"$set": {"name": name.strip(), "username": username}}
    )
    return JSONResponse({"success": True, "msg": "Profile updated successfully!", "name": name.strip(), "username": username})

@router.post("/api/store/upload-avatar")
async def upload_avatar(request: Request, avatar_b64: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    if len(avatar_b64) > 1_400_000:
        return JSONResponse({"success": False, "msg": "Image too large! Max 1MB."})
    if not avatar_b64.startswith("data:image/"):
        return JSONResponse({"success": False, "msg": "Invalid image format."})

    await db.store_customers.update_one({"email": email}, {"$set": {"avatar": avatar_b64}})
    return JSONResponse({"success": True, "msg": "Avatar updated!", "avatar": avatar_b64})

@router.post("/api/store/change-password")
async def change_password(request: Request,
                          current_password: str = Form(...),
                          new_password: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "User not found"})
    if not user.get("password"):
        return JSONResponse({"success": False, "msg": "Your account uses Google/Telegram login — no password to change."})
    if user["password"] != hash_password(current_password):
        return JSONResponse({"success": False, "msg": "Current password is incorrect!"})
    if len(new_password) < 8:
        return JSONResponse({"success": False, "msg": "New password must be at least 8 characters."})
    if current_password == new_password:
        return JSONResponse({"success": False, "msg": "New password must be different from current."})

    await db.store_customers.update_one({"email": email}, {"$set": {"password": hash_password(new_password)}})
    return JSONResponse({"success": True, "msg": "Password changed successfully!"})

@router.post("/api/store/change-email-request")
async def change_email_request(request: Request, new_email: str = Form(...)):
    current_email = request.cookies.get("store_session")
    if not current_email:
        return JSONResponse({"success": False, "msg": "Not logged in"})
    if not _re.match(r'^[^@]+@[^@]+\.[^@]+$', new_email):
        return JSONResponse({"success": False, "msg": "Invalid email address."})
    if new_email == current_email:
        return JSONResponse({"success": False, "msg": "This is already your current email."})
    if await db.store_customers.find_one({"email": new_email}):
        return JSONResponse({"success": False, "msg": "This email is already registered."})

    code = str(random.randint(100000, 999999))
    await db.otps.update_one(
        {"email": current_email},
        {"$set": {"code": code, "new_email": new_email, "type": "email_change", "created_at": datetime.now()}},
        upsert=True
    )
    return JSONResponse({"success": True, "msg": f"Verification code sent to {new_email}"})

@router.post("/api/store/change-email-verify")
async def change_email_verify(request: Request, code: str = Form(...)):
    current_email = request.cookies.get("store_session")
    if not current_email:
        return JSONResponse({"success": False, "msg": "Not logged in"})

    otp_doc = await db.otps.find_one({"email": current_email, "code": code, "type": "email_change"})
    if not otp_doc:
        return JSONResponse({"success": False, "msg": "Invalid verification code."})
    if (datetime.now() - otp_doc["created_at"]).total_seconds() > 300:
        return JSONResponse({"success": False, "msg": "Code expired! Please try again."})

    new_email = otp_doc["new_email"]
    if await db.store_customers.find_one({"email": new_email}):
        return JSONResponse({"success": False, "msg": "This email was just registered by someone else."})

    await db.store_customers.update_one({"email": current_email}, {"$set": {"email": new_email}})
    await db.store_orders.update_many({"email": current_email}, {"$set": {"email": new_email}})
    await db.otps.delete_one({"_id": otp_doc["_id"]})

    response = JSONResponse({"success": True, "msg": "Email updated successfully!", "new_email": new_email})
    response.set_cookie(key="store_session", value=new_email, httponly=True, max_age=86400 * 30)
    return response

# ==========================================
# 7. Admin — Full Customer Control
# ==========================================

def admin_check(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

@router.get("/api/store/customer-info")
async def customer_info(request: Request, email: str):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})
    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "Not found"})
        
    # جلب أي عملة ديناميكية متسجلة للعميل
    balances = {k: v for k, v in user.items() if k.startswith("balance_")}
    return JSONResponse({
        "success": True,
        **balances
    })

@router.post("/api/store/admin/update-customer")
async def admin_update_customer(
    request: Request,
    email:        str = Form(...),
    name:         str = Form(...),
    username:     str = Form(...),
    new_password: str = Form(""),
):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    username = username.lower().strip()
    if not _re.match(r'^[a-z0-9_]{3,20}$', username):
        return JSONResponse({"success": False, "msg": "Username: 3-20 chars (letters/numbers/_)"})
    if not name.strip():
        return JSONResponse({"success": False, "msg": "Name cannot be empty"})

    existing = await db.store_customers.find_one({"username": username, "email": {"$ne": email}})
    if existing:
        return JSONResponse({"success": False, "msg": "Username already taken"})

    update = {"name": name.strip(), "username": username}
    if new_password:
        if len(new_password) < 8:
            return JSONResponse({"success": False, "msg": "Password must be at least 8 characters"})
        update["password"] = hash_password(new_password)

    await db.store_customers.update_one({"email": email}, {"$set": update})
    return JSONResponse({"success": True, "msg": "Customer updated!", "name": name.strip(), "username": username})

@router.post("/api/store/admin/email-request")
async def admin_email_request(request: Request, email: str = Form(...), new_email: str = Form(...)):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})
    if not _re.match(r'^[^@]+@[^@]+\.[^@]+$', new_email):
        return JSONResponse({"success": False, "msg": "Invalid email address"})
    if new_email == email:
        return JSONResponse({"success": False, "msg": "Same as current email"})
    if await db.store_customers.find_one({"email": new_email}):
        return JSONResponse({"success": False, "msg": "Email already registered"})

    code = str(random.randint(100000, 999999))
    await db.otps.update_one(
        {"email": email},
        {"$set": {"code": code, "new_email": new_email, "type": "admin_email_change", "created_at": datetime.now()}},
        upsert=True
    )
    return JSONResponse({"success": True, "msg": f"Code sent to {new_email}"})

@router.post("/api/store/admin/email-verify")
async def admin_email_verify(request: Request, email: str = Form(...), code: str = Form(...)):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    otp_doc = await db.otps.find_one({"email": email, "code": code, "type": "admin_email_change"})
    if not otp_doc:
        return JSONResponse({"success": False, "msg": "Invalid code"})
    if (datetime.now() - otp_doc["created_at"]).total_seconds() > 600:
        return JSONResponse({"success": False, "msg": "Code expired"})

    new_email = otp_doc["new_email"]
    if await db.store_customers.find_one({"email": new_email}):
        return JSONResponse({"success": False, "msg": "Email just taken by someone else"})

    await db.store_customers.update_one({"email": email}, {"$set": {"email": new_email}})
    await db.store_orders.update_many({"email": email}, {"$set": {"email": new_email}})
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    return JSONResponse({"success": True, "msg": "Email changed successfully!", "new_email": new_email})

@router.post("/api/store/admin/set-avatar")
async def admin_set_avatar(request: Request, email: str = Form(...), avatar_b64: str = Form("")):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})
    if avatar_b64 and len(avatar_b64) > 1_400_000:
        return JSONResponse({"success": False, "msg": "Image too large (max 1MB)"})
    if avatar_b64 and not avatar_b64.startswith("data:image/"):
        return JSONResponse({"success": False, "msg": "Invalid image format"})

    await db.store_customers.update_one({"email": email}, {"$set": {"avatar": avatar_b64}})
    msg = "Avatar updated!" if avatar_b64 else "Avatar removed!"
    return JSONResponse({"success": True, "msg": msg})

@router.get("/api/store/admin/customer-orders")
async def admin_customer_orders(request: Request, email: str):
    if not admin_check(request):
        return JSONResponse({"success": False, "orders": []})
    orders = await db.store_orders.find({"email": email}).sort("date", -1).to_list(200)
    for o in orders:
        o["order_id"] = str(o.get("_id", ""))
    return JSONResponse({"success": True, "orders": orders})

@router.post("/api/store/admin/delete-customer")
async def admin_delete_customer(request: Request, email: str = Form(...)):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})
    result = await db.store_customers.delete_one({"email": email})
    if result.deleted_count == 0:
        return JSONResponse({"success": False, "msg": "Customer not found"})
    await db.otps.delete_many({"email": email})
    return JSONResponse({"success": True, "msg": f"Account {email} deleted."})

# ==========================================
# 8. Support Tickets System
# ==========================================

@router.post("/api/store/tickets/create")
async def create_ticket(
    request:  Request,
    subject:  str = Form(...),
    message:  str = Form(...),
):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Please login first."})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "Account not found."})

    if not subject.strip() or not message.strip():
        return JSONResponse({"success": False, "msg": "Subject and message are required."})

    # Generate unique ticket ID
    ticket_id = f"TKT-{random.randint(10000, 99999)}"
    while await db.support_tickets.find_one({"_id": ticket_id}):
        ticket_id = f"TKT-{random.randint(10000, 99999)}"

    await db.support_tickets.insert_one({
        "_id":        ticket_id,
        "email":      email,
        "name":       user.get("name", "Customer"),
        "subject":    subject.strip(),
        "status":     "open",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "messages": [{
            "sender":  "customer",
            "name":    user.get("name", "Customer"),
            "message": message.strip(),
            "time":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        }],
    })

    return JSONResponse({"success": True, "msg": f"Ticket {ticket_id} submitted!", "ticket_id": ticket_id})


@router.get("/api/store/tickets/my")
async def get_my_tickets(request: Request):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "tickets": []})

    tickets = await db.support_tickets.find({"email": email}).sort("created_at", -1).to_list(50)
    for t in tickets:
        t["ticket_id"] = str(t["_id"])
    return JSONResponse({"success": True, "tickets": tickets})


@router.post("/api/store/tickets/reply")
async def customer_reply_ticket(
    request:   Request,
    ticket_id: str = Form(...),
    message:   str = Form(...),
):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Please login first."})

    ticket = await db.support_tickets.find_one({"_id": ticket_id, "email": email})
    if not ticket:
        return JSONResponse({"success": False, "msg": "Ticket not found."})
    if ticket.get("status") == "closed":
        return JSONResponse({"success": False, "msg": "This ticket is closed."})

    user = await db.store_customers.find_one({"email": email})
    await db.support_tickets.update_one(
        {"_id": ticket_id},
        {"$push": {"messages": {
            "sender":  "customer",
            "name":    user.get("name", "Customer") if user else "Customer",
            "message": message.strip(),
            "time":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        }}}
    )
    return JSONResponse({"success": True, "msg": "Reply sent!"})


@router.post("/api/store/admin/tickets/reply")
async def admin_reply_ticket(
    request:   Request,
    ticket_id: str = Form(...),
    message:   str = Form(...),
):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    ticket = await db.support_tickets.find_one({"_id": ticket_id})
    if not ticket:
        return JSONResponse({"success": False, "msg": "Ticket not found."})

    await db.support_tickets.update_one(
        {"_id": ticket_id},
        {
            "$push": {"messages": {
                "sender":  "admin",
                "name":    "Support Team",
                "message": message.strip(),
                "time":    datetime.now().strftime("%Y-%m-%d %H:%M"),
            }},
            "$set": {"status": "in_progress"},
        }
    )
    return JSONResponse({"success": True, "msg": "Reply sent!"})


@router.post("/api/store/admin/tickets/change-status")
async def admin_change_ticket_status(
    request:   Request,
    ticket_id: str = Form(...),
    status:    str = Form(...),
):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    if status not in ("open", "in_progress", "closed"):
        return JSONResponse({"success": False, "msg": "Invalid status."})

    result = await db.support_tickets.update_one({"_id": ticket_id}, {"$set": {"status": status}})
    if result.matched_count == 0:
        return JSONResponse({"success": False, "msg": "Ticket not found."})
    return JSONResponse({"success": True, "msg": f"Status updated to {status}."})


@router.get("/api/store/admin/tickets/view")
async def admin_view_ticket(request: Request, ticket_id: str):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    ticket = await db.support_tickets.find_one({"_id": ticket_id})
    if not ticket:
        return JSONResponse({"success": False, "msg": "Ticket not found."})

    ticket["ticket_id"] = str(ticket["_id"])
    del ticket["_id"]
    return JSONResponse({"success": True, "ticket": ticket})
