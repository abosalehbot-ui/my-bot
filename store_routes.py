from fastapi import APIRouter, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import hashlib
import random
import httpx
from datetime import datetime

# ─── Shared imports (no duplicate connections) ──────────────────────────
from database import db, get_next_order_id
from config import SECRET_TOKEN, MONGO_URI

router = APIRouter()
templates = Jinja2Templates(directory="templates")

GOOGLE_CLIENT_ID = "671995925834-4bf0od4fm0pkkhvkfrvqh41h6rpb574v.apps.googleusercontent.com"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

async def generate_unique_id():
    while True:
        new_id = random.randint(10000000, 99999999)
        if not await db.store_customers.find_one({"user_id": new_id}):
            return new_id

# ==========================================
# 1. الواجهة الرئيسية للمتجر
# ==========================================
@router.get("/", response_class=HTMLResponse)
async def public_storefront(request: Request):
    settings    = await db.settings.find_one({"_id": "config"})
    maintenance = settings.get("maintenance", False) if settings else False

    categories    = await db.store_categories.find().to_list(100)
    stock_details = {}
    for cat in categories:
        for p in cat.get("products", []):
            sk = p["stock_key"]
            if sk not in stock_details:
                stock_details[sk] = await db.stock.count_documents({"category": sk})

    return templates.TemplateResponse("storefront.html", {
        "request":     request,
        "categories":  categories,
        "stock":       stock_details,
        "client_id":   GOOGLE_CLIENT_ID,
        "maintenance": maintenance,
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
                    "balance_egp": 0, "balance_usd": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
            await db.store_customers.insert_one(user)

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
                "balance_egp": 0, "balance_usd": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        await db.store_customers.insert_one(user)

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
    print(f"\n[MOCK EMAIL] To: {email} | PASSWORD RESET OTP: {code}\n")
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
async def customer_buy(request: Request, stock_key: str = Form(...), price: float = Form(...), currency: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Unauthorized! Please login again.", "force_logout": True})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "Account not found!", "force_logout": True})

    bal_field = f"balance_{currency.lower()}"
    if user.get(bal_field, 0) < price:
        return JSONResponse({"success": False, "msg": f"Insufficient {currency.upper()} balance! Please recharge."})

    code_doc = await db.stock.find_one_and_delete({"category": stock_key})
    if not code_doc:
        return JSONResponse({"success": False, "msg": "Sorry, this product is out of stock."})

    code_str    = str(code_doc.get("code") or code_doc["_id"])
    seq         = await get_next_order_id()
    order_id    = f"{seq}S"
    now_str     = datetime.now().strftime("%Y-%m-%d %H:%M")

    await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: -price}})
    new_bal = user.get(bal_field, 0) - price

    await db.store_orders.insert_one({
        "_id":      order_id,
        "email":    email,
        "name":     user["name"],
        "category": stock_key,
        "code":     code_str,
        "price":    price,
        "currency": currency.upper(),
        "date":     now_str,
    })
    await db.codes_map.insert_one({
        "code":     code_str,
        "order_id": order_id,
        "name":     f"{user['name']} (Web)",
        "time":     now_str,
        "source":   "Web Store",
    })

    return JSONResponse({"success": True, "code": code_str, "new_balance": new_bal,
                         "currency": currency.upper(), "msg": "Purchase successful!"})
import json

@router.post("/api/store/buy-cart")
async def customer_buy_cart(request: Request, cart_data: str = Form(...), currency: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "msg": "Unauthorized! Please login again.", "force_logout": True})

    user = await db.store_customers.find_one({"email": email})
    if not user:
        return JSONResponse({"success": False, "msg": "Account not found!", "force_logout": True})

    try:
        items = json.loads(cart_data) # فك شفرة السلة
    except:
        return JSONResponse({"success": False, "msg": "Invalid cart data."})

    if not items:
        return JSONResponse({"success": False, "msg": "Cart is empty."})

    total_price = sum(float(item["price"]) * int(item["qty"]) for item in items)
    bal_field = f"balance_{currency.lower()}"
    
    if user.get(bal_field, 0) < total_price:
        return JSONResponse({"success": False, "msg": f"Insufficient {currency.upper()} balance! Please recharge."})

    # 1. التأكد إن المخزون يكفي لكل المنتجات اللي في السلة قبل ما نخصم الفلوس
    for item in items:
        available = await db.stock.count_documents({"category": item["stock_key"]})
        if available < int(item["qty"]):
            return JSONResponse({"success": False, "msg": f"Not enough stock for {item['name']}. Available: {available}"})

    # 2. خصم إجمالي الفلوس من الرصيد
    await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: -total_price}})
    new_bal = user.get(bal_field, 0) - total_price

    # 3. سحب الأكواد وإنشاء الطلبات في الداتا بيز
    pulled_codes_display = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    for item in items:
        sk = item["stock_key"]
        qty = int(item["qty"])
        price_per_item = float(item["price"])
        
        for _ in range(qty):
            code_doc = await db.stock.find_one_and_delete({"category": sk})
            if code_doc:
                code_str = str(code_doc.get("code") or code_doc["_id"])
                seq = await get_next_order_id()
                order_id = f"{seq}S"
                
                await db.store_orders.insert_one({
                    "_id":      order_id,
                    "email":    email,
                    "name":     user["name"],
                    "category": sk,
                    "code":     code_str,
                    "price":    price_per_item,
                    "currency": currency.upper(),
                    "date":     now_str,
                })
                await db.codes_map.insert_one({
                    "code":     code_str,
                    "order_id": order_id,
                    "name":     f"{user['name']} (Web)",
                    "time":     now_str,
                    "source":   "Web Store",
                })
                pulled_codes_display.append(f"<b>{item['name']}</b>: <code>{code_str}</code>")

    return JSONResponse({"success": True, "codes": pulled_codes_display, "new_balance": new_bal,
                         "currency": currency.upper(), "msg": "Purchase successful!"})
@router.get("/api/store/my-orders")
async def get_my_orders(request: Request):
    email = request.cookies.get("store_session")
    if not email:
        return JSONResponse({"success": False, "orders": []})

    orders = await db.store_orders.find({"email": email}).sort("date", -1).to_list(100)
    for o in orders:
        o["order_id"] = str(o.get("_id", ""))
    return JSONResponse({"success": True, "orders": orders})

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
    
    # ✅ الحل هنا: تحويل الـ ObjectId لنص عشان الصفحة تفهمه وماتضربش 500
    for customer in store_customers:
        if "_id" in customer:
            customer["_id"] = str(customer["_id"])

    store_orders    = await db.store_orders.find().sort("date", -1).to_list(500)

    return templates.TemplateResponse("store_admin.html", {
        "request":         request,
        "store_customers": store_customers,
        "store_orders":    store_orders,
        "maintenance":     maintenance,
    })
   

@router.post("/api/store/manage_balance")
async def store_manage_balance(request: Request, email: str = Form(...), amount: float = Form(...), action: str = Form(...), currency: str = Form(...)):
    if not check_auth(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"})

    bal_field = f"balance_{currency.lower()}"
    if action == "add":
        await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: amount}})
    elif action == "set":
        await db.store_customers.update_one({"email": email}, {"$set": {bal_field: amount}})
    elif action == "sub":
        await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: -amount}})

    return JSONResponse({"success": True, "msg": f"{currency.upper()} balance updated successfully!"})

# ==========================================
# 6. Profile — Get / Edit / Avatar / Password / Email
# ==========================================

import base64, re as _re

def _make_username(name: str, user_id: int) -> str:
    """توليد يوزر تلقائي من الاسم + آخر 4 أرقام من الـ id"""
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

    # Auto-generate username if missing
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

    # Check username not taken by someone else
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

    # Validate it's a real base64 image (max ~1MB)
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
    print(f"\n[MOCK EMAIL] To: {new_email} | EMAIL CHANGE OTP: {code}\n")
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
    # Double-check new email not taken
    if await db.store_customers.find_one({"email": new_email}):
        return JSONResponse({"success": False, "msg": "This email was just registered by someone else."})

    await db.store_customers.update_one({"email": current_email}, {"$set": {"email": new_email}})
    await db.store_orders.update_many({"email": current_email}, {"$set": {"email": new_email}})
    await db.otps.delete_one({"_id": otp_doc["_id"]})

    # Update session cookie
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
    return JSONResponse({
        "success":     True,
        "balance_egp": user.get("balance_egp", 0),
        "balance_usd": user.get("balance_usd", 0),
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
    print(f"\n[ADMIN EMAIL CHANGE] To: {new_email} | OTP: {code}\n")
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
    # Also clean up their OTPs
    await db.otps.delete_many({"email": email})
    return JSONResponse({"success": True, "msg": f"Account {email} deleted."})
