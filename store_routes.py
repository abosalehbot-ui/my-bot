from fastapi import APIRouter, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import motor.motor_asyncio
import os
import httpx
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["salehzon_db"]
SECRET_TOKEN = "salehzon_secure_2026"

# الـ Client ID الخاص بك من ملف الـ JSON
GOOGLE_CLIENT_ID = "771769206518-8mm08g177dfraqr2u9da8lu85r2svulb.apps.googleusercontent.com"

def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

# ==========================================
# 1. لوحة تحكم المتجر الشاملة للأدمن (Store ERP)
# ==========================================
@router.get("/store-admin", response_class=HTMLResponse)
async def store_admin_page(request: Request):
    if not check_auth(request): return RedirectResponse(url="/login")
    store_prices = await db.settings.find_one({"_id": "store_prices"}) or {}
    store_customers = await db.store_customers.find().sort("created_at", -1).to_list(100)
    store_orders = await db.store_orders.find().sort("date", -1).to_list(100)
    
    total_revenue = sum(int(o.get("price", 0)) for o in store_orders)
    stock_details = {cat: await db.stock.count_documents({"category": cat}) for cat in ["60", "325", "660", "1800", "3850", "8100"]}

    return templates.TemplateResponse("store_admin.html", {
        "request": request, "store_prices": store_prices, "store_customers": store_customers,
        "store_orders": store_orders, "stock": stock_details,
        "stats": {"revenue": total_revenue, "orders": len(store_orders), "customers": len(store_customers)}
    })

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

# ==========================================
# 2. واجهة متجر الزبائن العام وتأكيد جوجل
# ==========================================
@router.get("/shop", response_class=HTMLResponse)
async def public_storefront(request: Request):
    store_prices = await db.settings.find_one({"_id": "store_prices"}) or {}
    stock_details = {cat: await db.stock.count_documents({"category": cat}) for cat in ["60", "325", "660", "1800", "3850", "8100"]}
    return templates.TemplateResponse("storefront.html", {"request": request, "prices": store_prices, "stock": stock_details})

@router.get("/store-login", response_class=HTMLResponse)
async def store_login_page(request: Request):
    return templates.TemplateResponse("store_login.html", {"request": request, "client_id": GOOGLE_CLIENT_ID})

@router.post("/api/store/google-login")
async def google_login(request: Request, credential: str = Form(...)):
    # التحقق من مصداقية توكن جوجل
    async with httpx.AsyncClient() as client_http:
        res = await client_http.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}")
        if res.status_code != 200: return JSONResponse({"success": False, "msg": "فشل التحقق من حساب جوجل."})
        
        user_info = res.json()
        if user_info.get("aud") != GOOGLE_CLIENT_ID: return JSONResponse({"success": False, "msg": "توكن غير صالح."})
        
        email = user_info.get("email")
        name = user_info.get("name")
        
        # لو الزبون جديد، يتم عمل حساب له تلقائياً برصيد صفر
        user = await db.store_customers.find_one({"email": email})
        if not user:
            await db.store_customers.insert_one({"email": email, "name": name, "balance": 0, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
            balance = 0
        else:
            balance = user.get("balance", 0)
            
        return JSONResponse({"success": True, "email": email, "name": name, "balance": balance})

@router.post("/api/store/buy")
async def customer_buy_uc(request: Request, email: str = Form(...), category: str = Form(...)):
    user = await db.store_customers.find_one({"email": email})
    if not user: return JSONResponse({"success": False, "msg": "حساب غير موجود!"})
    
    prices = await db.settings.find_one({"_id": "store_prices"}) or {}
    price = int(prices.get(category, 999999))
    
    if user["balance"] < price: return JSONResponse({"success": False, "msg": "رصيدك غير كافٍ! يرجى شحن محفظتك."})
        
    code_doc = await db.stock.find_one_and_delete({"category": category})
    if not code_doc: return JSONResponse({"success": False, "msg": "عذراً، هذه الفئة نفذت من المخزن حالياً."})
        
    code_str = str(code_doc.get("code") or code_doc["_id"])
    
    await db.store_customers.update_one({"email": email}, {"$inc": {"balance": -price}})
    order_id = int(datetime.now().timestamp() % 100000)
    await db.store_orders.insert_one({"_id": order_id, "email": email, "name": user["name"], "category": category, "code": code_str, "price": price, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
    
    return JSONResponse({"success": True, "code": code_str, "new_balance": user["balance"] - price, "msg": "تم الشراء بنجاح!"})
