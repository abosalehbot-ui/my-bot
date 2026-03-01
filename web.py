import os
from fastapi import FastAPI, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import motor.motor_asyncio
from datetime import datetime

app = FastAPI(title="Saleh Zone Dashboard")

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["salehzon_db"]

ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "123456")
SECRET_TOKEN = "salehzon_secure_2026"

def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

async def web_log(action, details=""):
    """تسجيل العمليات التي تتم من لوحة التحكم لتظهر في السجلات"""
    await db.system_logs.insert_one({
        "user_id": "WEB_ADMIN", "name": "Admin Dashboard", "action": action,
        "details": details, "time": datetime.now().strftime('%Y-%m-%d %H:%M'), "timestamp": datetime.now()
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def do_login(response: Response, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        resp.set_cookie(key="admin_session", value=SECRET_TOKEN, httponly=True)
        return resp
    return RedirectResponse(url="/login?error=1", status_code=status.HTTP_302_FOUND)

@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie("admin_session")
    return resp

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not check_auth(request): return RedirectResponse(url="/login")
    
    users_count = await db.users.count_documents({})
    stock_count = await db.stock.count_documents({})
    orders_count = await db.orders.count_documents({})
    cached_count = await db.cached_accounts.count_documents({})
    
    logs = await db.system_logs.find().sort("timestamp", -1).to_list(length=100)
    all_users = await db.users.find().sort("_id", -1).to_list(length=50)
    
    categories = ["60", "325", "660", "1800", "3850", "8100"]
    stock_details = {cat: await db.stock.count_documents({"category": cat}) for cat in categories}
        
    settings = await db.settings.find_one({"_id": "config"})
    maintenance = settings.get("maintenance", False) if settings else False

    shared_doc = await db.settings.find_one({"_id": "shared_tokens"})
    shared_tokens_count = len(shared_doc.get("tokens", [])) if shared_doc else 0

    return templates.TemplateResponse("index.html", {
        "request": request, "users_count": users_count, "stock_count": stock_count,
        "orders_count": orders_count, "cached_count": cached_count,
        "logs": logs, "all_users": all_users, "stock_details": stock_details,
        "maintenance": maintenance, "shared_tokens_count": shared_tokens_count
    })

# ----------------- APIs للميزات المتكاملة -----------------

@app.post("/api/toggle_maintenance")
async def toggle_maint(request: Request):
    if not check_auth(request): return {"status": "error"}
    current = await db.settings.find_one({"_id": "config"})
    new_state = not current.get("maintenance", False) if current else True
    await db.settings.update_one({"_id": "config"}, {"$set": {"maintenance": new_state}}, upsert=True)
    await web_log(f"تغيير وضع الصيانة إلى: {'تشغيل' if new_state else 'إيقاف'}")
    return {"status": "success"}

@app.post("/api/add_stock")
async def api_add_stock(request: Request, category: str = Form(...), codes: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    lines = [c.strip() for c in codes.splitlines() if c.strip()]
    docs = [{"code": c, "category": category, "added_at": datetime.now()} for c in lines]
    if docs: 
        await db.stock.insert_many(docs, ordered=False)
        await web_log(f"إضافة مخزن: {len(docs)} كود لفئة {category}")
    return RedirectResponse(url="/?tab=stock", status_code=status.HTTP_302_FOUND)

@app.post("/api/clear_stock")
async def api_clear_stock(request: Request, category: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    await db.stock.delete_many({"category": category})
    return RedirectResponse(url="/?tab=stock", status_code=status.HTTP_302_FOUND)

@app.post("/api/add_shared_tokens")
async def api_add_shared(request: Request, tokens: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    lines = [t.strip() for t in tokens.splitlines() if t.strip()]
    if lines: 
        await db.settings.update_one({"_id": "shared_tokens"}, {"$push": {"tokens": {"$each": lines}}}, upsert=True)
        await web_log(f"تمت إضافة {len(lines)} توكنات مشتركة")
    return RedirectResponse(url="/?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/clear_shared_tokens")
async def api_clear_shared(request: Request):
    if not check_auth(request): return RedirectResponse("/login")
    await db.settings.update_one({"_id": "shared_tokens"}, {"$set": {"tokens": []}}, upsert=True)
    await web_log("تصفير جميع التوكنات المشتركة")
    return RedirectResponse(url="/?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/add_user_tokens")
async def api_add_user_tokens(request: Request, user_id: int = Form(...), tokens: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    lines = [t.strip() for t in tokens.splitlines() if t.strip()]
    if lines: 
        await db.users.update_one({"_id": user_id}, {"$push": {"tokens": {"$each": lines}}})
        await web_log(f"إضافة {len(lines)} توكن شخصي للمستخدم {user_id}")
    return RedirectResponse(url="/?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/add_user")
async def api_add_user(request: Request, user_id: int = Form(...), name: str = Form(...), role: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if not await db.users.find_one({"_id": user_id}):
        await db.users.insert_one({"_id": user_id, "role": role, "name": name, "tokens": [], "history": [], "logs": [], "token_logs": [], "stats": {"api": 0, "stock": 0}})
    return RedirectResponse(url="/?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/user_action")
async def api_user_action(request: Request, user_id: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if action == "delete": await db.users.delete_one({"_id": user_id})
    elif action == "clear_tokens": await db.users.update_one({"_id": user_id}, {"$set": {"tokens": []}})
    elif action == "toggle_role":
        u = await db.users.find_one({"_id": user_id})
        nr = "employee" if u.get("role") == "user" else "user"
        await db.users.update_one({"_id": user_id}, {"$set": {"role": nr}})
        await web_log(f"تعديل رتبة المستخدم {user_id} إلى {nr}")
    elif action == "clear_logs":
        await db.users.update_one({"_id": user_id}, {"$set": {"logs": [], "history": [], "token_logs": []}})
    return RedirectResponse(url="/?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/tracked_users")
async def api_tracked_users(request: Request, user_id: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if action == "add": await db.settings.update_one({"_id": "cache_config"}, {"$addToSet": {"tracked_users": user_id}}, upsert=True)
    elif action == "remove": await db.settings.update_one({"_id": "cache_config"}, {"$pull": {"tracked_users": user_id}}, upsert=True)
    return RedirectResponse(url="/?tab=tools", status_code=status.HTTP_302_FOUND)

@app.post("/api/return_order")
async def api_return_order(request: Request, order_id: int = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    order = await db.orders.find_one({"_id": order_id})
    if order and "PUBG Stock" in order.get("type", ""):
        cat = order["type"].split("(")[1].split(" ")[0]
        codes_to_return = [{"code": c, "category": cat, "added_at": datetime.now()} for c in order["items"]]
        await db.stock.insert_many(codes_to_return, ordered=False)
        await db.codes_map.delete_many({"$or": [{"_id": {"$in": order["items"]}}, {"code": {"$in": order["items"]}}], "order_id": order_id})
        await db.orders.delete_one({"_id": order_id})
        await db.users.update_one({"_id": order["user_id"]}, {"$inc": {"stats.stock": -len(order["items"])}})
    return RedirectResponse(url="/?tab=tools", status_code=status.HTTP_302_FOUND)

@app.post("/api/search")
async def api_search(request: Request):
    if not check_auth(request): return JSONResponse({"error": "unauth"})
    form = await request.form()
    query = form.get("query", "").strip()
    if not query: return JSONResponse({"result": "❌ أرسل نصاً للبحث"})
    
    if query.isdigit():
        order = await db.orders.find_one({"_id": int(query)})
        if order: return JSONResponse({"result": f"📄 طلب #{query} | المستلم: {order['user']} | الأكواد: {len(order['items'])}"})
        user = await db.users.find_one({"_id": int(query)})
        if user: return JSONResponse({"result": f"👤 {user.get('name')} | الرتبة: {user.get('role')} | التوكنات: {len(user.get('tokens',[]))}"})

    records = await db.codes_map.find({"$or": [{"_id": query}, {"code": query}]}).to_list(length=5)
    in_stock = await db.stock.count_documents({"$or": [{"_id": query}, {"code": query}]})
    res_str = f"🔍 الكود: {query}\n📦 متوفر بالمخزن: {in_stock}\n"
    if records:
        res_str += f"🛒 تم سحبه {len(records)} مرات (بواسطة: {', '.join([r['name'] for r in records])})"
    return JSONResponse({"result": res_str})
