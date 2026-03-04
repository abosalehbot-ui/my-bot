from fastapi import APIRouter, Request, Form, Response, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import motor.motor_asyncio
import os
import httpx
import random
import hashlib
from datetime import datetime

from database import db, get_next_order_id
from config import SECRET_TOKEN
from pydantic import BaseModel
from typing import List

class CartItem(BaseModel):
    stock_key: str
    price: float
    currency: str
    quantity: int

class CheckoutRequest(BaseModel):
    cart: List[CartItem]

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
        if not await db.store_customers.find_one({"user_id": new_id}): return new_id

# ==========================================
# 1. الواجهة الرئيسية للمتجر
# ==========================================
@router.get("/", response_class=HTMLResponse)
async def public_storefront(request: Request):
    settings = await db.settings.find_one({"_id": "config"})
    maintenance = settings.get("maintenance", False) if settings else False

    email = request.cookies.get("store_session")
    customer_data = {"name": ""} 
    if email:
        user = await db.store_customers.find_one({"email": email})
        if user:
            customer_data = user

    categories = await db.store_categories.find().to_list(100)
    
    for cat in categories:
        for p in cat.get("products", []):
            if "prices" not in p:
                p["prices"] = {
                    "EGP": p.get("price_egp", 0),
                    "USD": p.get("price_usd", 0)
                }

    currencies = await db.store_currencies.find().to_list(100)
    if not currencies:
        currencies = [{"_id": "EGP", "symbol": "EGP"}, {"_id": "USD", "symbol": "USD"}]

    stock_details = {}
    for cat in categories:
        for p in cat.get("products", []):
            sk = p["stock_key"]
            if sk not in stock_details: 
                stock_details[sk] = await db.stock.count_documents({"category": sk})
                
    return templates.TemplateResponse("storefront.html", {
        "request": request, 
        "categories": categories, 
        "currencies": currencies,
        "stock": stock_details, 
        "client_id": GOOGLE_CLIENT_ID, 
        "maintenance": maintenance,
        "customer": customer_data
    })

# ==========================================
# 2. أنظمة التسجيل والمصادقة الموحدة
# ==========================================
def get_user_data(user):
    data = {"email": user["email"], "name": user["name"], "username": user.get("username", ""), "avatar": user.get("avatar", "")}
    for key, val in user.items():
        if key.startswith("balance_"):
            data[key] = val
    return data

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
    
    return JSONResponse({"success": True, "msg": "OTP sent to your email!"})

@router.post("/api/store/signup-verify")
async def signup_verify(request: Request, email: str = Form(...), code: str = Form(...)):
    otp_doc = await db.otps.find_one({"email": email, "code": code, "type": "signup"})
    if not otp_doc: return JSONResponse({"success": False, "msg": "Invalid verification code!"})
    if (datetime.now() - otp_doc["created_at"]).total_seconds() > 300: return JSONResponse({"success": False, "msg": "Code expired! Please try again."})
        
    user_id = await generate_unique_id()
    new_user = {"user_id": user_id, "username": otp_doc["username"], "email": email, "name": otp_doc["name"], "password": otp_doc["password"], "balance_egp": 0, "balance_usd": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    await db.store_customers.insert_one(new_user)
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    
    response = JSONResponse({"success": True, **get_user_data(new_user)})
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

@router.post("/api/store/checkout-cart")
async def checkout_cart(request: Request, payload: CheckoutRequest):
    email = request.cookies.get("store_session")
    if not email: 
        return JSONResponse({"success": False, "msg": "Unauthorized! Please login again.", "force_logout": True})
    
    user = await db.store_customers.find_one({"email": email})
    if not user: 
        return JSONResponse({"success": False, "msg": "Account not found!", "force_logout": True})
    
    results = []
    
    for item in payload.cart:
        for _ in range(item.quantity):
            stock_key = item.stock_key
            price = item.price
            currency = item.currency.upper()
            bal_field = f"balance_{currency.lower()}"

            user = await db.store_customers.find_one({"email": email})
            
            if user.get(bal_field, 0) < price:
                results.append({"name": stock_key, "status": "Failed", "msg": f"Insufficient {currency} balance!"})
                continue

            code_doc = await db.stock.find_one_and_delete({"category": stock_key})
            if not code_doc:
                results.append({"name": stock_key, "status": "Failed", "msg": "Out of stock"})
                continue

            code_str = str(code_doc.get("code") or code_doc["_id"])
            seq = await get_next_order_id()
            order_id_str = f"{seq}S"
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: -price}})
            
            await db.store_orders.insert_one({
                "_id": order_id_str, "email": email, "name": user["name"], 
                "category": stock_key, "code": code_str, "price": price, 
                "currency": currency, "date": now_str
            })
            
            await db.codes_map.insert_one({
                "code": code_str, "order_id": order_id_str, 
                "name": f"{user['name']} (Web)", "time": now_str, "source": "Web Store"
            })
            
            results.append({"name": stock_key, "status": "Success", "code": code_str, "price": price, "currency": currency})
    
    user = await db.store_customers.find_one({"email": email})
    new_balances = {
        "EGP": user.get("balance_egp", 0),
        "USD": user.get("balance_usd", 0)
    }

    return JSONResponse({"success": True, "results": results, "new_balances": new_balances, "msg": "Checkout completed!"})

@router.get("/api/store/my-orders")
async def get_my_orders(request: Request):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "orders": []})
    
    orders = await db.store_orders.find({"email": email}).sort("date", -1).to_list(100)
    for o in orders:
        if '_id' in o: 
            o['order_id'] = str(o['_id'])
            o['_id'] = str(o['_id'])
    return JSONResponse({"success": True, "orders": orders})

# ==========================================
# 5. دوال البروفايل (الاسم والصورة والإيميل)
# ==========================================
@router.get("/api/store/profile")
async def get_profile(request: Request):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "msg": "Unauthorized"})
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "User not found"})
    return JSONResponse({
        "success": True,
        "user": {
            "name": user.get("name", ""),
            "email": user.get("email", ""),
            "avatar": user.get("avatar", ""),
            "created_at": user.get("created_at", "")
        }
    })

@router.post("/api/store/update-profile")
async def update_profile(request: Request, name: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "msg": "Unauthorized"})
    await db.store_customers.update_one({"email": email}, {"$set": {"name": name}})
    return JSONResponse({"success": True, "msg": "Profile updated!"})

@router.post("/api/store/update-avatar")
async def update_avatar(request: Request, avatar: UploadFile = File(None)):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "msg": "Unauthorized"})
    
    from web import save_upload
    if avatar and avatar.filename:
        avatar_url = await save_upload(avatar)
        await db.store_customers.update_one({"email": email}, {"$set": {"avatar": avatar_url}})
    return JSONResponse({"success": True, "msg": "Avatar updated!"})

@router.post("/api/store/change-email-request")
async def change_email_req(request: Request, new_email: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False})
    if await db.store_customers.find_one({"email": new_email}): return JSONResponse({"success": False, "msg": "Email already in use!"})
    
    code = str(random.randint(100000, 999999))
    await db.otps.update_one({"email": new_email}, {"$set": {"code": code, "old_email": email, "type": "change_email", "created_at": datetime.now()}}, upsert=True)
    return JSONResponse({"success": True, "msg": "Verification code sent to the new email."})

@router.post("/api/store/change-email-verify")
async def change_email_verify(request: Request, new_email: str = Form(...), code: str = Form(...)):
    email = request.cookies.get("store_session")
    otp_doc = await db.otps.find_one({"email": new_email, "code": code, "type": "change_email", "old_email": email})
    if not otp_doc: return JSONResponse({"success": False, "msg": "Invalid code!"})
    
    await db.store_customers.update_one({"email": email}, {"$set": {"email": new_email}})
    await db.store_orders.update_many({"email": email}, {"$set": {"email": new_email}})
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    
    res = JSONResponse({"success": True, "msg": "Email updated successfully!"})
    res.set_cookie(key="store_session", value=new_email, httponly=True, max_age=86400 * 30)
    return res

@router.post("/api/store/change-password")
async def change_password(request: Request, old_password: str = Form(...), new_password: str = Form(...)):
    email = request.cookies.get("store_session")
    if not email: return JSONResponse({"success": False, "msg": "Unauthorized"})
    
    user = await db.store_customers.find_one({"email": email})
    if not user or user.get("password") != hash_password(old_password):
        return JSONResponse({"success": False, "msg": "Incorrect current password!"})
        
    if len(new_password) < 8:
        return JSONResponse({"success": False, "msg": "New password must be at least 8 characters!"})
        
    await db.store_customers.update_one({"email": email}, {"$set": {"password": hash_password(new_password)}})
    return JSONResponse({"success": True, "msg": "Password updated successfully!"})

# ==========================================
# 6. لوحة أدمن الاستور
# ==========================================
@router.get("/store-admin", response_class=HTMLResponse)
async def store_admin_page(request: Request):
    if not check_auth(request): return RedirectResponse(url="/login")
    store_customers = await db.store_customers.find().sort("created_at", -1).to_list(100)
    store_orders = await db.store_orders.find().sort("date", -1).to_list(200)
    
    for c in store_customers:
        if '_id' in c: c['_id'] = str(c['_id'])
    for o in store_orders:
        if '_id' in o: o['_id'] = str(o['_id'])
        
    currencies = await db.store_currencies.find().to_list(100)
    if not currencies:
        currencies = [{"_id": "EGP", "symbol": "EGP"}, {"_id": "USD", "symbol": "USD"}]
        
    return templates.TemplateResponse("store_admin.html", {
        "request": request, 
        "store_customers": store_customers, 
        "store_orders": store_orders,
        "currencies": currencies
    })

@router.post("/api/store/admin/set-avatar")
async def admin_set_avatar(request: Request, email: str = Form(...), avatar: UploadFile = File(None), avatar_b64: str = Form("")):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    
    if avatar and avatar.filename:
        from web import save_upload
        avatar_url = await save_upload(avatar)
        await db.store_customers.update_one({"email": email}, {"$set": {"avatar": avatar_url}})
    elif avatar_b64 == "":
        await db.store_customers.update_one({"email": email}, {"$set": {"avatar": ""}})
    return JSONResponse({"success": True, "msg": "Avatar updated!"})

@router.post("/api/store/manage_balance")
async def store_manage_balance(request: Request, email: str = Form(...), amount: float = Form(...), action: str = Form(...), currency: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    
    query = [{"email": email}, {"username": email}]
    try: query.append({"user_id": int(email)})
    except: pass
        
    user = await db.store_customers.find_one({"$or": query})
    if not user: return JSONResponse({"success": False, "msg": "User not found."})
        
    bal_field = f"balance_{currency.lower()}"
    if action == "add": await db.store_customers.update_one({"_id": user["_id"]}, {"$inc": {bal_field: amount}})
    elif action == "set": await db.store_customers.update_one({"_id": user["_id"]}, {"$set": {bal_field: amount}})
    
    return JSONResponse({"success": True, "msg": f"{currency.upper()} Balance updated successfully!"})

@router.post("/api/store/admin/delete-customer")
async def admin_delete_customer(request: Request, email: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    await db.store_customers.delete_one({"email": email})
    return JSONResponse({"success": True, "msg": "Customer account deleted."})

@router.post("/api/store/admin/update-customer")
async def admin_update_customer(request: Request, email: str = Form(...), name: str = Form(None), password: str = Form(None), username: str = Form(None)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    
    update_data = {}
    if name: update_data["name"] = name
    if username: update_data["username"] = username
    if password: update_data["password"] = hash_password(password)
    
    if update_data:
        await db.store_customers.update_one({"email": email}, {"$set": update_data})
        
    return JSONResponse({"success": True, "msg": "Customer updated successfully!"})

@router.post("/api/store/admin/email-request")
async def admin_change_email_req(request: Request, email: str = Form(...), new_email: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    
    existing = await db.store_customers.find_one({"email": new_email})
    if existing: return JSONResponse({"success": False, "msg": "New email is already registered!"})
    
    code = str(random.randint(100000, 999999))
    await db.otps.update_one({"email": new_email}, {"$set": {"code": code, "old_email": email, "type": "admin_change_email", "created_at": datetime.now()}}, upsert=True)
    return JSONResponse({"success": True, "msg": "Verification OTP generated."})

@router.post("/api/store/admin/email-verify")
async def admin_change_email_ver(request: Request, email: str = Form(...), code: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    
    otp_doc = await db.otps.find_one({"old_email": email, "code": code, "type": "admin_change_email"})
    if not otp_doc: return JSONResponse({"success": False, "msg": "Invalid code!"})
    
    new_email = otp_doc["email"]
    await db.store_customers.update_one({"email": email}, {"$set": {"email": new_email}})
    await db.store_orders.update_many({"email": email}, {"$set": {"email": new_email}})
    await db.otps.delete_one({"_id": otp_doc["_id"]})
    
    return JSONResponse({"success": True, "msg": "Email changed successfully!", "new_email": new_email})

@router.post("/api/store/admin/toggle-status")
async def admin_toggle_status(request: Request, email: str = Form(...), action: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "User not found!"})
    
    if action == "ban":
        new_status = not user.get("is_banned", False)
        await db.store_customers.update_one({"email": email}, {"$set": {"is_banned": new_status}})
        return JSONResponse({"success": True, "msg": "Account Banned!" if new_status else "Account Unbanned!", "new_status": new_status})
        
    elif action == "freeze":
        new_status = not user.get("balance_frozen", False)
        await db.store_customers.update_one({"email": email}, {"$set": {"balance_frozen": new_status}})
        return JSONResponse({"success": True, "msg": "Balance Frozen!" if new_status else "Balance Unfrozen!", "new_status": new_status})
        
    return JSONResponse({"success": False, "msg": "Invalid action."})

@router.get("/api/store/customer-info")
async def get_customer_info(request: Request, email: str):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False})
    return JSONResponse({"success": True, **get_user_data(user)})

@router.get("/api/store/admin/customer-orders")
async def admin_customer_orders(request: Request, email: str):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    orders = await db.store_orders.find({"email": email}).sort("date", -1).to_list(100)
    for o in orders:
        if '_id' in o:
            o['order_id'] = str(o['_id'])
            o['_id'] = str(o['_id'])
    return JSONResponse({"success": True, "orders": orders})

# ==========================================
# 8. إرجاع الطلبات والأموال (المشكلة التي تم حلها!)
# ==========================================
@router.post("/api/store/admin/return-order")
async def admin_return_single_order(request: Request, order_id: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    
    order = await db.store_orders.find_one({"_id": order_id})
    if not order: return JSONResponse({"success": False, "msg": "Order not found!"})
    
    # 1. إرجاع الرصيد للمستخدم (المشكلة السابقة)
    email = order.get("email")
    price = float(order.get("price", 0))
    currency = order.get("currency", "EGP").lower()
    bal_field = f"balance_{currency}"
    
    if email and price > 0:
        await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: price}})
    
    # 2. إرجاع الكود للمخزن
    await db.stock.insert_one({"code": order["code"], "category": order["category"], "added_at": datetime.now()})
    
    # 3. مسح الطلب من السجلات
    await db.codes_map.delete_many({"order_id": order_id})
    await db.store_orders.delete_one({"_id": order_id})
    
    return JSONResponse({"success": True, "msg": f"Order #{order_id} returned and {price} {currency.upper()} refunded!"})

@router.post("/api/store/admin/return-all-orders")
async def admin_return_all_orders(request: Request, email: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    
    orders = await db.store_orders.find({"email": email}).to_list(None)
    if not orders: return JSONResponse({"success": False, "msg": "No orders found for this user."})
    
    refund_egp = 0.0
    refund_usd = 0.0
    codes_to_return = []
    order_ids = []
    
    # حساب الفلوس وتجهيز الأكواد
    for o in orders:
        codes_to_return.append({"code": o["code"], "category": o["category"], "added_at": datetime.now()})
        order_ids.append(o["_id"])
        
        curr = o.get("currency", "").upper()
        if curr == "EGP": refund_egp += float(o.get("price", 0))
        elif curr == "USD": refund_usd += float(o.get("price", 0))
        
    # إرجاع المال للمستخدم
    if refund_egp > 0 or refund_usd > 0:
        await db.store_customers.update_one(
            {"email": email},
            {"$inc": {"balance_egp": refund_egp, "balance_usd": refund_usd}}
        )
        
    # إرجاع الأكواد وحذف السجلات
    await db.stock.insert_many(codes_to_return, ordered=False)
    await db.codes_map.delete_many({"order_id": {"$in": order_ids}})
    await db.store_orders.delete_many({"email": email})
    
    return JSONResponse({"success": True, "msg": f"Success! {len(orders)} orders returned and money refunded."})
