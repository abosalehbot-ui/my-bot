from fastapi import APIRouter, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import motor.motor_asyncio
import os
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["salehzon_db"]
SECRET_TOKEN = "salehzon_secure_2026"

def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

# ==========================================
# 1. لوحة تحكم المتجر الشاملة للأدمن
# ==========================================
@router.get("/store-admin", response_class=HTMLResponse)
async def store_admin_page(request: Request):
    if not check_auth(request): return RedirectResponse(url="/login")
    
    # جلب البيانات
    store_prices = await db.settings.find_one({"_id": "store_prices"}) or {}
    store_customers = await db.store_customers.find().sort("created_at", -1).to_list(100)
    store_orders = await db.store_orders.find().sort("date", -1).to_list(100)
    
    # حساب الإحصائيات
    total_revenue = sum(int(o.get("price", 0)) for o in store_orders)
    total_orders = len(store_orders)
    customers_count = len(store_customers)
    
    # المخزن المتاح للمتجر
    categories = ["60", "325", "660", "1800", "3850", "8100"]
    stock_details = {cat: await db.stock.count_documents({"category": cat}) for cat in categories}

    return templates.TemplateResponse("store_admin.html", {
        "request": request, 
        "store_prices": store_prices, 
        "store_customers": store_customers,
        "store_orders": store_orders,
        "stats": {
            "revenue": total_revenue,
            "orders": total_orders,
            "customers": customers_count
        },
        "stock": stock_details
    })

@router.post("/api/store/update_prices")
async def store_update_prices(request: Request, p_60: int = Form(0), p_325: int = Form(0), p_660: int = Form(0), p_1800: int = Form(0), p_3850: int = Form(0), p_8100: int = Form(0)):
    if not check_auth(request): return RedirectResponse("/login")
    prices = {"60": p_60, "325": p_325, "660": p_660, "1800": p_1800, "3850": p_3850, "8100": p_8100}
    await db.settings.update_one({"_id": "store_prices"}, {"$set": prices}, upsert=True)
    return RedirectResponse(url="/store-admin", status_code=status.HTTP_302_FOUND)

@router.post("/api/store/add_customer")
async def store_add_customer(request: Request, phone: str = Form(...), name: str = Form(...), balance: int = Form(0)):
    if not check_auth(request): return RedirectResponse("/login")
    if not await db.store_customers.find_one({"phone": phone}):
        await db.store_customers.insert_one({
            "phone": phone, "name": name, "balance": balance, 
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
    return RedirectResponse(url="/store-admin", status_code=status.HTTP_302_FOUND)

@router.post("/api/store/manage_balance")
async def store_manage_balance(request: Request, phone: str = Form(...), amount: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if action == "add":
        await db.store_customers.update_one({"phone": phone}, {"$inc": {"balance": amount}})
    elif action == "set":
        await db.store_customers.update_one({"phone": phone}, {"$set": {"balance": amount}})
    return RedirectResponse(url="/store-admin", status_code=status.HTTP_302_FOUND)

@router.post("/api/store/delete_customer")
async def store_delete_customer(request: Request, phone: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    await db.store_customers.delete_one({"phone": phone})
    return RedirectResponse(url="/store-admin", status_code=status.HTTP_302_FOUND)


# ==========================================
# 2. واجهة متجر الزبائن العام (موقع الزبون)
# ==========================================
@router.get("/shop", response_class=HTMLResponse)
async def public_storefront(request: Request):
    store_prices = await db.settings.find_one({"_id": "store_prices"}) or {}
    categories = ["60", "325", "660", "1800", "3850", "8100"]
    stock_details = {cat: await db.stock.count_documents({"category": cat}) for cat in categories}
    return templates.TemplateResponse("storefront.html", {
        "request": request, "prices": store_prices, "stock": stock_details
    })

@router.post("/api/store/login")
async def customer_login(request: Request, phone: str = Form(...)):
    user = await db.store_customers.find_one({"phone": phone})
    if user: return JSONResponse({"success": True, "name": user["name"], "balance": user["balance"], "phone": user["phone"]})
    return JSONResponse({"success": False, "msg": "رقم الهاتف غير مسجل! تواصل مع الإدارة لشحن حسابك."})

@router.post("/api/store/buy")
async def customer_buy_uc(request: Request, phone: str = Form(...), category: str = Form(...)):
    user = await db.store_customers.find_one({"phone": phone})
    if not user: return JSONResponse({"success": False, "msg": "يجب تسجيل الدخول!"})
    
    prices = await db.settings.find_one({"_id": "store_prices"}) or {}
    price = int(prices.get(category, 999999))
    
    if user["balance"] < price:
        return JSONResponse({"success": False, "msg": "رصيدك غير كافٍ! يرجى شحن محفظتك."})
        
    code_doc = await db.stock.find_one_and_delete({"category": category})
    if not code_doc:
        return JSONResponse({"success": False, "msg": "عذراً، هذه الفئة نفذت من المخزن حالياً."})
        
    code_str = str(code_doc.get("code") or code_doc["_id"])
    
    # خصم الرصيد وتسجيل الطلب
    await db.store_customers.update_one({"phone": phone}, {"$inc": {"balance": -price}})
    order_id = int(datetime.now().timestamp() % 100000)
    
    await db.store_orders.insert_one({
        "_id": order_id, 
        "phone": phone,
        "name": user["name"],
        "category": category, 
        "code": code_str, 
        "price": price, 
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    
    return JSONResponse({"success": True, "code": code_str, "new_balance": user["balance"] - price, "msg": "تم الشراء بنجاح!"})

@router.get("/store-login", response_class=HTMLResponse)
async def store_login_page(request: Request):
    return templates.TemplateResponse("store_login.html", {"request": request})
