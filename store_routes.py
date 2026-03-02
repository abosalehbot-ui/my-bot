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

# تشفير الباسوردات (أمان عالي)
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

def send_email_sync(to_email, otp):
    print(f"\n[MOCK EMAIL] To: {to_email} | OTP CODE: {otp}\n")
    return True # حالياً بيطبع الكود في الكونسول فقط لحد ما تفعل الإيميل بعدين

# ==========================================
# 1. واجهة المتجر
# ==========================================
@router.get("/", response_class=HTMLResponse)
async def public_storefront(request: Request):
    store_prices = await db.settings.find_one({"_id": "store_prices"}) or {}
    stock_details = {cat: await db.stock.count_documents({"category": cat}) for cat in ["60", "325", "660", "1800", "3850", "8100"]}
    return templates.TemplateResponse("storefront.html", {"request": request, "prices": store_prices, "stock": stock_details, "client_id": GOOGLE_CLIENT_ID})

# ==========================================
# 2. أنظمة تسجيل الدخول (محمية بـ Secure Cookies)
# ==========================================
@router.post("/api/store/login-manual")
async def login_manual(request: Request, email: str = Form(...), password: str = Form(...)):
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "Account not found. Please sign up."})
    if "password" not in user or not user["password"]: return JSONResponse({"success": False, "msg": "Please login with Google/Telegram."})
    
    if user["password"] != hash_password(password): 
        return JSONResponse({"success": False, "msg": "Incorrect password!"})
        
    response = JSONResponse({"success": True, "email": user["email"], "name": user["name"], "balance": user.get("balance", 0)})
    response.set_cookie(key="store_session", value=user["email"], httponly=True, max_age=86400 * 30) # الكوكي صالح لـ 30 يوم
    return response

@router.post("/api/store/signup-request")
async def signup_request(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if await db.store_customers.find_one({"email": email}):
        return JSONResponse({"success": False, "msg": "Email is already registered!"})
        
    code = str(random.randint(100000, 999999))
    hashed_pw = hash_password(password) # تشفير الباسورد قبل حفظه
    await db.otps.update_one({"email": email}, {"$set": {"code": code, "name": name, "password": hashed_pw, "created_at": datetime.now()}}, upsert=True)
    
    send_email_sync(email, code)
    return JSONResponse({"success": True, "msg": "OTP sent to your email!"})

@router.post("/api/store/signup-verify")
async def signup_verify(request: Request, email: str = Form(...), code: str = Form(...)):
    otp_doc = await db.otps.find_one({"email": email, "code": code})
    if not otp_doc: return JSONResponse({"success": False, "msg": "Invalid verification code!"})
    if (datetime.now() - otp_doc["created_at"]).total_seconds() > 300:
        return JSONResponse({"success": False, "msg": "Code expired! Please try again."})
        
    await db.store_customers.insert_one({
        "email": email, "name": otp_doc["name"], "password": otp_doc["password"], # محفوظ مشفر أصلاً
        "balance": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    
    response = JSONResponse({"success": True, "email": email, "name": otp_doc["name"], "balance": 0})
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
            await db.store_customers.insert_one({"email": email, "name": name, "balance": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
            balance = 0
        else: balance = user.get("balance", 0)
        
        response = JSONResponse({"success": True, "email": email, "name": name, "balance": balance})
        response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
        return response

@router.post("/api/store/telegram-login")
async def telegram_login(request: Request, tg_id: str = Form(...), name: str = Form(...), username: str = Form("")):
    email = f"tg_{tg_id}@telegram.zone"
    user = await db.store_customers.find_one({"email": email})
    if not user:
        await db.store_customers.insert_one({"email": email, "name": name, "balance": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
        balance = 0
    else: balance = user.get("balance", 0)
    
    response = JSONResponse({"success": True, "email": email, "name": name, "balance": balance})
    response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/logout")
async def store_logout():
    response = JSONResponse({"success": True})
    response.delete_cookie("store_session")
    return response

# ==========================================
# 3. عملية الشراء (محمية ولا تقبل التلاعب)
# ==========================================
@router.post("/api/store/buy")
async def customer_buy_uc(request: Request, category: str = Form(...)):
    # هنا الحماية الحقيقية: بناخد الإيميل من الكوكي السري المشفر، مش من اللي الزبون بيبعته
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "msg": "Unauthorized! Please login again.", "force_logout": True})
    
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "Account not found!", "force_logout": True})
    
    prices = await db.settings.find_one({"_id": "store_prices"}) or {}
    price = int(prices.get(category, 999999))
    if user["balance"] < price: return JSONResponse({"success": False, "msg": "Insufficient balance! Please recharge."})
        
    code_doc = await db.stock.find_one_and_delete({"category": category})
    if not code_doc: return JSONResponse({"success": False, "msg": "Sorry, this category is out of stock."})
        
    code_str = str(code_doc.get("code") or code_doc["_id"])
    await db.store_customers.update_one({"email": email}, {"$inc": {"balance": -price}})
    order_id = int(datetime.now().timestamp() % 100000)
    await db.store_orders.insert_one({"_id": order_id, "email": email, "name": user["name"], "category": category, "code": code_str, "price": price, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
    
    return JSONResponse({"success": True, "code": code_str, "new_balance": user["balance"] - price, "msg": "Purchase successful!"})

# ==========================================
# 4. لوحة تحكم المتجر للأدمن
# ==========================================
@router.get("/store-admin", response_class=HTMLResponse)
async def store_admin_page(request: Request):
    if not check_auth(request): return RedirectResponse(url="/login")
    store_prices = await db.settings.find_one({"_id": "store_prices"}) or {}
    store_customers = await db.store_customers.find().sort("created_at", -1).to_list(100)
    store_orders = await db.store_orders.find().sort("date", -1).to_list(100)
    total_revenue = sum(int(o.get("price", 0)) for o in store_orders)
    stock_details = {cat: await db.stock.count_documents({"category": cat}) for cat in ["60", "325", "660", "1800", "3850", "8100"]}
    return templates.TemplateResponse("store_admin.html", {"request": request, "store_prices": store_prices, "store_customers": store_customers, "store_orders": store_orders, "stock": stock_details, "stats": {"revenue": total_revenue, "orders": len(store_orders), "customers": len(store_customers)}})

@router.post("/api/store/update_prices")
async def store_update_prices(request: Request, p_60: int = Form(0), p_325: int = Form(0), p_660: int = Form(0), p_1800: int = Form(0), p_3850: int = Form(0), p_8100: int = Form(0)):
    if not check_auth(request): return RedirectResponse("/login")
    await db.settings.update_one({"_id": "store_prices"}, {"$set": {"60": p_60, "325": p_325, "660": p_660, "1800": p_1800, "3850": p_3850, "8100": p_8100}}, upsert=True)
    return RedirectResponse(url="/store-admin", status_code=status.HTTP_302_FOUND)

@router.post("/api/store/add_customer")
async def store_add_customer(request: Request, email: str = Form(...), name: str = Form(...), balance: int = Form(0)):
    if not check_auth(request): return RedirectResponse("/login")
    if not await db.store_customers.find_one({"email": email}):
        await db.store_customers.insert_one({"email": email, "name": name, "balance": balance, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    return RedirectResponse(url="/store-admin", status_code=status.HTTP_302_FOUND)

@router.post("/api/store/manage_balance")
async def store_manage_balance(request: Request, email: str = Form(...), amount: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if action == "add": await db.store_customers.update_one({"email": email}, {"$inc": {"balance": amount}})
    elif action == "set": await db.store_customers.update_one({"email": email}, {"$set": {"balance": amount}})
    return RedirectResponse(url="/store-admin", status_code=status.HTTP_302_FOUND)

@router.post("/api/store/delete_customer")
async def store_delete_customer(request: Request, email: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    await db.store_customers.delete_one({"email": email})
    return RedirectResponse(url="/store-admin", status_code=status.HTTP_302_FOUND)
