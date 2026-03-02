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

def hash_password(password: str) -> str: return hashlib.sha256(password.encode()).hexdigest()
def check_auth(request: Request): return request.cookies.get("admin_session") == SECRET_TOKEN

async def get_next_order_id():
    stat = await db.stats.find_one_and_update({"_id": "global_stats"}, {"$inc": {"last_order_id": 1}}, upsert=True, return_document=True)
    return stat["last_order_id"]

async def generate_unique_id():
    while True:
        new_id = random.randint(10000000, 99999999)
        if not await db.store_customers.find_one({"user_id": new_id}): return new_id

@router.get("/", response_class=HTMLResponse)
async def public_storefront(request: Request):
    categories = await db.store_categories.find().to_list(100)
    stock_details = {}
    for cat in categories:
        for p in cat.get("products", []):
            sk = p["stock_key"]
            if sk not in stock_details: stock_details[sk] = await db.stock.count_documents({"category": sk})
    return templates.TemplateResponse("storefront.html", {"request": request, "categories": categories, "stock": stock_details, "client_id": GOOGLE_CLIENT_ID})

def get_user_data(user):
    return {"email": user["email"], "name": user["name"], "balance_egp": user.get("balance_egp", 0), "balance_usd": user.get("balance_usd", 0)}

@router.post("/api/store/login-manual")
async def login_manual(request: Request, email: str = Form(...), password: str = Form(...)):
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "Account not found."})
    if user.get("password") != hash_password(password): return JSONResponse({"success": False, "msg": "Incorrect password!"})
    response = JSONResponse({"success": True, **get_user_data(user)})
    response.set_cookie(key="store_session", value=user["email"], httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/signup-request")
async def signup_request(request: Request, name: str = Form(...), username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if len(password) < 8: return JSONResponse({"success": False, "msg": "Password must be at least 8 chars!"})
    if await db.store_customers.find_one({"email": email}): return JSONResponse({"success": False, "msg": "Email registered!"})
    if await db.store_customers.find_one({"username": username.lower()}): return JSONResponse({"success": False, "msg": "Username taken!"})
    code = str(random.randint(100000, 999999))
    await db.otps.update_one({"email": email}, {"$set": {"code": code, "name": name, "username": username.lower(), "password": hash_password(password), "created_at": datetime.now()}}, upsert=True)
    print(f"\n[MOCK EMAIL] To: {email} | OTP CODE: {code}\n")
    return JSONResponse({"success": True, "msg": "OTP sent to email!"})

@router.post("/api/store/signup-verify")
async def signup_verify(request: Request, email: str = Form(...), code: str = Form(...)):
    otp_doc = await db.otps.find_one({"email": email, "code": code})
    if not otp_doc: return JSONResponse({"success": False, "msg": "Invalid code!"})
    user_id = await generate_unique_id()
    await db.store_customers.insert_one({"user_id": user_id, "username": otp_doc["username"], "email": email, "name": otp_doc["name"], "password": otp_doc["password"], "balance_egp": 0, "balance_usd": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    response = JSONResponse({"success": True, "email": email, "name": otp_doc["name"], "balance_egp": 0, "balance_usd": 0})
    response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/google-login")
async def google_login(request: Request, credential: str = Form(...)):
    async with httpx.AsyncClient() as client_http:
        res = await client_http.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}")
        if res.status_code != 200: return JSONResponse({"success": False, "msg": "Google failed."})
        user_info = res.json(); email = user_info.get("email"); name = user_info.get("name")
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
    email = f"tg_{tg_id}@telegram.zone"; user = await db.store_customers.find_one({"email": email})
    if not user:
        user_id = await generate_unique_id(); final_username = username.lower() if username else f"user{tg_id}"
        user = {"user_id": user_id, "username": final_username, "email": email, "name": name, "balance_egp": 0, "balance_usd": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        await db.store_customers.insert_one(user)
    response = JSONResponse({"success": True, **get_user_data(user)})
    response.set_cookie(key="store_session", value=email, httponly=True, max_age=86400 * 30)
    return response

@router.post("/api/store/logout")
async def store_logout():
    response = JSONResponse({"success": True}); response.delete_cookie("store_session"); return response

@router.post("/api/store/buy")
async def customer_buy_uc(request: Request, stock_key: str = Form(...), price: float = Form(...), currency: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "msg": "Unauthorized!", "force_logout": True})
    
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "Account not found!", "force_logout": True})
    
    bal_field = f"balance_{currency.lower()}"
    if user.get(bal_field, 0) < price: return JSONResponse({"success": False, "msg": f"Insufficient {currency.upper()} balance!"})
        
    code_doc = await db.stock.find_one_and_delete({"category": stock_key})
    if not code_doc: return JSONResponse({"success": False, "msg": "Out of stock."})
        
    code_str = str(code_doc.get("code") or code_doc["_id"])
    seq = await get_next_order_id(); order_id_str = f"{seq}S"; now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: -price}})
    new_bal = user.get(bal_field, 0) - price
    
    await db.store_orders.insert_one({"_id": order_id_str, "email": email, "name": user["name"], "category": stock_key, "code": code_str, "price": price, "currency": currency.upper(), "date": now_str})
    await db.codes_map.insert_one({"code": code_str, "order_id": order_id_str, "name": f"{user['name']} (Web)", "time": now_str, "source": "Web Store"})
    
    return JSONResponse({"success": True, "code": code_str, "new_balance": new_bal, "currency": currency.upper(), "msg": "Success!"})

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
    return JSONResponse({"success": True, "msg": f"{currency.upper()} Balance updated!"})
