from fastapi import APIRouter, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import motor.motor_asyncio
import os
import httpx
import random
import smtplib
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["salehzon_db"]
SECRET_TOKEN = "salehzon_secure_2026"
GOOGLE_CLIENT_ID = "671995925834-4bf0od4fm0pkkhvkfrvqh41h6rpb574v.apps.googleusercontent.com"

def hash_password(password: str) -> str: 
    return hashlib.sha256(password.encode()).hexdigest()

def check_auth(request: Request): 
    return request.cookies.get("admin_session") == SECRET_TOKEN

async def get_next_order_id():
    stat = await db.stats.find_one_and_update({"_id": "global_stats"}, {"$inc": {"last_order_id": 1}}, upsert=True, return_document=True)
    return stat["last_order_id"]

async def generate_unique_id():
    while True:
        new_id = random.randint(10000000, 99999999)
        if not await db.store_customers.find_one({"user_id": new_id}): return new_id

# ==========================================
# 1. الواجهة الرئيسية للمتجر (ديناميكية ومربوطة بالصيانة)
# ==========================================
@router.get("/", response_class=HTMLResponse)
async def public_storefront(request: Request):
    # جلب حالة الصيانة من الداتا بيز
    settings = await db.settings.find_one({"_id": "config"})
    maintenance = settings.get("maintenance", False) if settings else False

    categories = await db.store_categories.find().to_list(100)
    stock_details = {}
    for cat in categories:
        for p in cat.get("products", []):
            sk = p["stock_key"]
            if sk not in stock_details: 
                stock_details[sk] = await db.stock.count_documents({"category": sk})
                
    return templates.TemplateResponse("storefront.html", {
        "request": request, 
        "categories": categories, 
        "stock": stock_details, 
        "client_id": GOOGLE_CLIENT_ID,
        "maintenance": maintenance
    })

# ==========================================
# 2. أنظمة التسجيل والمصادقة الموحدة
# ==========================================
def get_user_data(user):
    return {"email": user["email"], "name": user["name"], "username": user.get("username", ""), "balance_egp": user.get("balance_egp", 0), "balance_usd": user.get("balance_usd", 0)}

@router.post("/api/store/login-manual")
async def login_manual(request: Request, email: str = Form(...), password: str = Form(...)):
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "Account not found. Please sign up."})
    if not user.get("password"): return JSONResponse({"success": False, "msg": "Please login with Google or Telegram."})
    
    if user["password"] != hash_password(password): 
        return JSONResponse({"success": False, "msg": "Incorrect password!"})
        
    response = JSONResponse({"success": True, **get_user_data(user)})
    response.set_cookie(key="store_session", value=user["email"], httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/signup-request")
async def signup_request(request: Request, name: str = Form(...), username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if len(password) < 8: return JSONResponse({"success": False, "msg": "Password must be at least 8 characters!"})
    if await db.store_customers.find_one({"email": email}): return JSONResponse({"success": False, "msg": "Email is already registered!"})
    if await db.store_customers.find_one({"username": username.lower()}): return JSONResponse({"success": False, "msg": "Username is already taken!"})
    
    code = str(random.randint(100000, 999999))
    hashed_pw = hash_password(password)
    await db.otps.update_one({"email": email}, {"$set": {"code": code, "name": name, "username": username.lower(), "password": hashed_pw, "type": "signup", "created_at": datetime.now()}}, upsert=True)
    
    print(f"\n[MOCK EMAIL] To: {email} | SIGNUP OTP: {code}\n")
    return JSONResponse({"success": True, "msg": "OTP sent to your email!"})

@router.post("/api/store/signup-verify")
async def signup_verify(request: Request, email: str = Form(...), code: str = Form(...)):
    otp_doc = await db.otps.find_one({"email": email, "code": code, "type": "signup"})
    if not otp_doc: return JSONResponse({"success": False, "msg": "Invalid verification code!"})
    if (datetime.now() - otp_doc["created_at"]).total_seconds() > 300: return JSONResponse({"success": False, "msg": "Code expired! Please try again."})
        
    user_id = await generate_unique_id()
    await db.store_customers.insert_one({"user_id": user_id, "username": otp_doc["username"], "email": email, "name": otp_doc["name"], "password": otp_doc["password"], "balance_egp": 0, "balance_usd": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    
    response = JSONResponse({"success": True, "email": email, "name": otp_doc["name"], "username": otp_doc["username"], "balance_egp": 0, "balance_usd": 0})
    response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/google-login")
async def google_login(request: Request, credential: str = Form(...)):
    async with httpx.AsyncClient() as client_http:
        res = await client_http.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}")
        if res.status_code != 200: return JSONResponse({"success": False, "msg": "Google verification failed."})
        user_info = res.json()
        if user_info.get("aud") != GOOGLE_CLIENT_ID: return JSONResponse({"success": False, "msg": "Invalid token."})
        
        email = user_info.get("email"); name = user_info.get("name")
        user = await db.store_customers.find_one({"email": email})
        
        if not user:
            user_id = await generate_unique_id()
            username = email.split("@")[0].lower() + str(random.randint(10,99))
            user = {"user_id": user_id, "username": username, "email": email, "name": name, "balance_egp": 0, "balance_usd": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
            await db.store_customers.insert_one(user)
            
        response = JSONResponse({"success": True, **get_user_data(user)})
        response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
        return response

@router.post("/api/store/telegram-login")
async def telegram_login(request: Request, tg_id: str = Form(...), name: str = Form(...), username: str = Form("")):
    email = f"tg_{tg_id}@telegram.zone"
    user = await db.store_customers.find_one({"email": email})
    
    if not user:
        user_id = await generate_unique_id()
        final_username = username.lower() if username else f"user{tg_id}"
        user = {"user_id": user_id, "username": final_username, "email": email, "name": name, "balance_egp": 0, "balance_usd": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
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
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "Account with this email does not exist."})
    
    code = str(random.randint(100000, 999999))
    await db.otps.update_one({"email": email}, {"$set": {"code": code, "type": "reset", "created_at": datetime.now()}}, upsert=True)
    
    print(f"\n[MOCK EMAIL] To: {email} | PASSWORD RESET OTP: {code}\n")
    return JSONResponse({"success": True, "msg": "Password reset code sent to your email!"})

@router.post("/api/store/reset-password")
async def reset_password(request: Request, email: str = Form(...), code: str = Form(...), new_password: str = Form(...)):
    if len(new_password) < 8: return JSONResponse({"success": False, "msg": "Password must be at least 8 characters!"})
    
    otp_doc = await db.otps.find_one({"email": email, "code": code, "type": "reset"})
    if not otp_doc: return JSONResponse({"success": False, "msg": "Invalid or expired reset code!"})
    
    await db.store_customers.update_one({"email": email}, {"$set": {"password": hash_password(new_password)}})
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    
    return JSONResponse({"success": True, "msg": "Password updated successfully! You can now login."})

# ==========================================
# 4. الشراء وجلب سجل الطلبات للعميل
# ==========================================
@router.post("/api/store/buy")
async def customer_buy_uc(request: Request, stock_key: str = Form(...), price: float = Form(...), currency: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "msg": "Unauthorized! Please login again.", "force_logout": True})
    
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "Account not found!", "force_logout": True})
    
    bal_field = f"balance_{currency.lower()}"
    if user.get(bal_field, 0) < price: 
        return JSONResponse({"success": False, "msg": f"Insufficient {currency.upper()} balance! Please recharge."})
        
    code_doc = await db.stock.find_one_and_delete({"category": stock_key})
    if not code_doc: return JSONResponse({"success": False, "msg": "Sorry, this product is out of stock."})
        
    code_str = str(code_doc.get("code") or code_doc["_id"])
    seq = await get_next_order_id()
    order_id_str = f"{seq}S"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: -price}})
    new_bal = user.get(bal_field, 0) - price
    
    await db.store_orders.insert_one({
        "_id": order_id_str, "email": email, "name": user["name"], 
        "category": stock_key, "code": code_str, "price": price, 
        "currency": currency.upper(), "date": now_str
    })
    
    await db.codes_map.insert_one({
        "code": code_str, "order_id": order_id_str, 
        "name": f"{user['name']} (Web)", "time": now_str, "source": "Web Store"
    })
    
    return JSONResponse({"success": True, "code": code_str, "new_balance": new_bal, "currency": currency.upper(), "msg": "Purchase successful!"})

@router.get("/api/store/my-orders")
async def get_my_orders(request: Request):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "orders": []})
    
    orders = await db.store_orders.find({"email": email}).sort("date", -1).to_list(100)
    for o in orders:
        if '_id' in o: o['order_id'] = str(o['_id'])
    return JSONResponse({"success": True, "orders": orders})

# ==========================================
# 5. لوحة أدمن الاستور (لإدارة العملاء)
# ==========================================
@router.get("/store-admin", response_class=HTMLResponse)
async def store_admin_page(request: Request):
    if not check_auth(request): return RedirectResponse(url="/login")
    store_customers = await db.store_customers.find().sort("created_at", -1).to_list(100)
    store_orders = await db.store_orders.find().sort("date", -1).to_list(200)
    return templates.TemplateResponse("store_admin.html", {"request": request, "store_customers": store_customers, "store_orders": store_orders})

@router.post("/api/store/manage_balance")
async def store_manage_balance(request: Request, email: str = Form(...), amount: float = Form(...), action: str = Form(...), currency: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    bal_field = f"balance_{currency.lower()}"
    if action == "add": await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: amount}})
    elif action == "set": await db.store_customers.update_one({"email": email}, {"$set": {bal_field: amount}})
    return JSONResponse({"success": True, "msg": f"{currency.upper()} Balance updated successfully!"})
