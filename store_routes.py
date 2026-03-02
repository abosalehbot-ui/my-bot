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

def send_email_sync(to_email, otp):
    print(f"\n[MOCK EMAIL] To: {to_email} | OTP CODE: {otp}\n")
    return True

# توليد رقم طلب متزامن وموحد للموقع والبوت
async def get_next_order_id():
    doc = await db.counters.find_one_and_update(
        {"_id": "global_order_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    return doc["seq"]

async def generate_unique_id():
    while True:
        new_id = random.randint(10000000, 99999999)
        if not await db.store_customers.find_one({"user_id": new_id}): return new_id

# ==========================================
# 1. واجهة المتجر (ديناميكية بالكامل)
# ==========================================
@router.get("/", response_class=HTMLResponse)
async def public_storefront(request: Request):
    # جلب الفئات والمنتجات من الداتا بيز بدل الثوابت
    categories = await db.store_categories.find().to_list(100)
    stock_details = {}
    for cat in categories:
        for p in cat.get("products", []):
            sk = p["stock_key"]
            if sk not in stock_details:
                stock_details[sk] = await db.stock.count_documents({"category": sk})
                
    return templates.TemplateResponse("storefront.html", {"request": request, "categories": categories, "stock": stock_details, "client_id": GOOGLE_CLIENT_ID})

# ==========================================
# 2. أنظمة التسجيل (بدون تغيير)
# ==========================================
@router.post("/api/store/login-manual")
async def login_manual(request: Request, email: str = Form(...), password: str = Form(...)):
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "Account not found."})
    if "password" not in user or not user["password"]: return JSONResponse({"success": False, "msg": "Login with Google/Telegram."})
    if user["password"] != hash_password(password): return JSONResponse({"success": False, "msg": "Incorrect password!"})
    response = JSONResponse({"success": True, "email": user["email"], "name": user["name"], "balance": user.get("balance", 0)})
    response.set_cookie(key="store_session", value=user["email"], httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/signup-request")
async def signup_request(request: Request, name: str = Form(...), username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if len(password) < 8: return JSONResponse({"success": False, "msg": "Password must be at least 8 chars!"})
    if await db.store_customers.find_one({"email": email}): return JSONResponse({"success": False, "msg": "Email registered!"})
    if await db.store_customers.find_one({"username": username.lower()}): return JSONResponse({"success": False, "msg": "Username taken!"})
    code = str(random.randint(100000, 999999))
    await db.otps.update_one({"email": email}, {"$set": {"code": code, "name": name, "username": username.lower(), "password": hash_password(password), "created_at": datetime.now()}}, upsert=True)
    send_email_sync(email, code)
    return JSONResponse({"success": True, "msg": "OTP sent to email!"})

@router.post("/api/store/signup-verify")
async def signup_verify(request: Request, email: str = Form(...), code: str = Form(...)):
    otp_doc = await db.otps.find_one({"email": email, "code": code})
    if not otp_doc: return JSONResponse({"success": False, "msg": "Invalid code!"})
    if (datetime.now() - otp_doc["created_at"]).total_seconds() > 300: return JSONResponse({"success": False, "msg": "Code expired!"})
    user_id = await generate_unique_id()
    await db.store_customers.insert_one({"user_id": user_id, "username": otp_doc["username"], "email": email, "name": otp_doc["name"], "password": otp_doc["password"], "balance": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    response = JSONResponse({"success": True, "email": email, "name": otp_doc["name"], "balance": 0})
    response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/google-login")
async def google_login(request: Request, credential: str = Form(...)):
    async with httpx.AsyncClient() as client_http:
        res = await client_http.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}")
        if res.status_code != 200: return JSONResponse({"success": False, "msg": "Google failed."})
        user_info = res.json()
        if user_info.get("aud") != GOOGLE_CLIENT_ID: return JSONResponse({"success": False, "msg": "Invalid token."})
        email = user_info.get("email"); name = user_info.get("name")
        user = await db.store_customers.find_one({"email": email})
        if not user:
            user_id = await generate_unique_id()
            username = email.split("@")[0].lower() + str(random.randint(10,99))
            await db.store_customers.insert_one({"user_id": user_id, "username": username, "email": email, "name": name, "balance": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
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
        user_id = await generate_unique_id()
        final_username = username.lower() if username else f"user{tg_id}"
        await db.store_customers.insert_one({"user_id": user_id, "username": final_username, "email": email, "name": name, "balance": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
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
# 3. الشراء المربوط بالبوت ونظام الأكواد
# ==========================================
@router.post("/api/store/buy")
async def customer_buy_uc(request: Request, stock_key: str = Form(...), price: int = Form(...)):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "msg": "Unauthorized!", "force_logout": True})
    
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "Account not found!", "force_logout": True})
    
    if user["balance"] < price: return JSONResponse({"success": False, "msg": "Insufficient balance!"})
        
    code_doc = await db.stock.find_one_and_delete({"category": stock_key})
    if not code_doc: return JSONResponse({"success": False, "msg": "Out of stock."})
        
    code_str = str(code_doc.get("code") or code_doc["_id"])
    
    # 1. إنشاء رقم طلب موحد بصيغة 1005S
    seq = await get_next_order_id()
    order_id_str = f"{seq}S"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    await db.store_customers.update_one({"email": email}, {"$inc": {"balance": -price}})
    
    # 2. تسجيل الطلب
    await db.store_orders.insert_one({
        "_id": order_id_str, "email": email, "name": user["name"], 
        "category": stock_key, "code": code_str, "price": price, "date": now_str
    })
    
    # 3. الأهم: تسجيل الكود في السجل الموحد عشان يظهر في بحث الماستر!!
    await db.codes_map.insert_one({
        "code": code_str, "order_id": order_id_str, 
        "name": f"{user['name']} (Web)", "time": now_str, "source": "Web Store"
    })
    
    return JSONResponse({"success": True, "code": code_str, "new_balance": user["balance"] - price, "msg": "Success!"})

# ==========================================
# 4. لوحة تحكم المتجر (نظام الفئات الجديد)
# ==========================================
@router.get("/store-admin", response_class=HTMLResponse)
async def store_admin_page(request: Request):
    if not check_auth(request): return RedirectResponse(url="/login")
    store_customers = await db.store_customers.find().sort("created_at", -1).to_list(100)
    store_orders = await db.store_orders.find().sort("date", -1).to_list(200)
    categories = await db.store_categories.find().to_list(100)
    
    total_revenue = sum(int(o.get("price", 0)) for o in store_orders)
    stock_details = {}
    for cat in categories:
        for p in cat.get("products", []):
            sk = p["stock_key"]
            if sk not in stock_details: stock_details[sk] = await db.stock.count_documents({"category": sk})

    return templates.TemplateResponse("store_admin.html", {
        "request": request, "categories": categories, "store_customers": store_customers, 
        "store_orders": store_orders, "stock": stock_details, 
        "stats": {"revenue": total_revenue, "orders": len(store_orders), "customers": len(store_customers)}
    })

# API إدارة الفئات
@router.post("/api/store/category/add")
async def api_add_category(request: Request, cat_id: str = Form(...), name: str = Form(...), icon: str = Form("fa-gamepad")):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauth"})
    cat_id = cat_id.lower().replace(" ", "_")
    if await db.store_categories.find_one({"_id": cat_id}): return JSONResponse({"success": False, "msg": "Category ID exists!"})
    await db.store_categories.insert_one({"_id": cat_id, "name": name, "icon": icon, "products": []})
    return JSONResponse({"success": True, "msg": "Category Added!"})

@router.post("/api/store/category/delete")
async def api_delete_category(request: Request, cat_id: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    await db.store_categories.delete_one({"_id": cat_id})
    return JSONResponse({"success": True, "msg": "Category Deleted!"})

@router.post("/api/store/product/add")
async def api_add_product(request: Request, cat_id: str = Form(...), stock_key: str = Form(...), name: str = Form(...), price: int = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    product = {"stock_key": stock_key, "name": name, "price": price}
    await db.store_categories.update_one({"_id": cat_id}, {"$push": {"products": product}})
    return JSONResponse({"success": True, "msg": "Product Added!"})

@router.post("/api/store/product/delete")
async def api_delete_product(request: Request, cat_id: str = Form(...), stock_key: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    await db.store_categories.update_one({"_id": cat_id}, {"$pull": {"products": {"stock_key": stock_key}}})
    return JSONResponse({"success": True, "msg": "Product Deleted!"})

# إدارة العملاء
@router.post("/api/store/add_customer")
async def store_add_customer(request: Request, email: str = Form(...), name: str = Form(...), balance: int = Form(0)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    if not await db.store_customers.find_one({"email": email}):
        user_id = await generate_unique_id()
        username = email.split("@")[0] + str(random.randint(10,99))
        await db.store_customers.insert_one({"user_id": user_id, "username": username, "email": email, "name": name, "balance": balance, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
        return JSONResponse({"success": True, "msg": "Customer added!"})
    return JSONResponse({"success": False, "msg": "Email already exists!"})

@router.post("/api/store/manage_balance")
async def store_manage_balance(request: Request, email: str = Form(...), amount: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    if action == "add": await db.store_customers.update_one({"email": email}, {"$inc": {"balance": amount}})
    elif action == "set": await db.store_customers.update_one({"email": email}, {"$set": {"balance": amount}})
    return JSONResponse({"success": True, "msg": f"Balance updated!"})

@router.post("/api/store/delete_customer")
async def store_delete_customer(request: Request, email: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    await db.store_customers.delete_one({"email": email})
    return JSONResponse({"success": True, "msg": "Customer deleted!"})
