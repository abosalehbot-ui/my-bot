import os
from fastapi import FastAPI, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import motor.motor_asyncio
from datetime import datetime, timedelta

app = FastAPI(title="Saleh Zone Dashboard")

# إعداد المجلدات الثابتة والقوالب
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# الاتصال بقاعدة البيانات
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["salehzon_db"]

ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "123456")
SECRET_TOKEN = "salehzon_secure_2026"

def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

async def web_log(action, details=""):
    await db.system_logs.insert_one({
        "user_id": "WEB_ADMIN", "name": "Admin Dashboard", "action": action,
        "details": details, "time": datetime.now().strftime('%Y-%m-%d %H:%M'), "timestamp": datetime.now()
    })

# 🧠 الفلتر الذكي لاستخراج التوكنات (نفس الموجود في التليجرام)
def clean_and_extract_tokens(raw_text):
    valid_tokens = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or "===" in line or "↓↓" in line or "Заказ" in line: 
            continue
        token = line.split(";")[0].strip()
        if len(token) > 15 and "http" not in token and " " not in token:
            valid_tokens.append(token)
    return valid_tokens

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
    
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    start_of_month_str = now.strftime("%Y-%m-01")
    start_of_week_str = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")

    users_count = await db.users.count_documents({})
    stock_count = await db.stock.count_documents({})
    cached_count = await db.cached_accounts.count_documents({})
    logs = await db.system_logs.find().sort("timestamp", -1).to_list(length=100)
    all_users = await db.users.find().sort("_id", -1).to_list(length=50)
    
    month_orders = await db.orders.find({"type": {"$regex": "API Pull|PUBG Stock"}, "date": {"$gte": start_of_month_str}}).to_list(None)
    
    user_pull_stats = {}
    global_today, global_month = 0, 0
    
    for o in month_orders:
        uid = o.get("user_id")
        count = len(o.get("items", []))
        if uid not in user_pull_stats:
            user_pull_stats[uid] = {"today": 0, "week": 0, "month": 0}
            
        global_month += count
        user_pull_stats[uid]["month"] += count
        if o.get("date", "").startswith(today_str):
            global_today += count
            user_pull_stats[uid]["today"] += count
        if o.get("date", "") >= start_of_week_str:
            user_pull_stats[uid]["week"] += count

    total_user_tokens = sum(len(u.get("tokens", [])) for u in all_users)
    shared_doc = await db.settings.find_one({"_id": "shared_tokens"})
    shared_tokens_count = len(shared_doc.get("tokens", [])) if shared_doc else 0
    total_system_tokens = total_user_tokens + shared_tokens_count

    for u in all_users:
        u["pull_stats"] = user_pull_stats.get(u["_id"], {"today": 0, "week": 0, "month": 0})

    categories = ["60", "325", "660", "1800", "3850", "8100"]
    stock_details = {cat: await db.stock.count_documents({"category": cat}) for cat in categories}
        
    settings = await db.settings.find_one({"_id": "config"})
    maintenance = settings.get("maintenance", False) if settings else False
    
    cache_config = await db.settings.find_one({"_id": "cache_config"})
    tracked_users = cache_config.get("tracked_users", []) if cache_config else []

    return templates.TemplateResponse("index.html", {
        "request": request, "users_count": users_count, "stock_count": stock_count,
        "cached_count": cached_count, "logs": logs, "all_users": all_users,
        "stock_details": stock_details, "maintenance": maintenance,
        "shared_tokens_count": shared_tokens_count, "total_system_tokens": total_system_tokens,
        "global_today": global_today, "global_month": global_month,
        "tracked_users": tracked_users
    })

# --- APIs للتحكم المتقدم (جميع ميزات التليجرام) ---

@app.post("/api/toggle_maintenance")
async def toggle_maint(request: Request):
    if not check_auth(request): return {"status": "error"}
    current = await db.settings.find_one({"_id": "config"})
    new_state = not current.get("maintenance", False) if current else True
    await db.settings.update_one({"_id": "config"}, {"$set": {"maintenance": new_state}}, upsert=True)
    await web_log(f"تغيير وضع الصيانة إلى: {'تشغيل' if new_state else 'إيقاف'}")
    return {"status": "success"}

@app.post("/api/add_stock_smart")
async def api_add_stock_smart(request: Request, category: str = Form(...), codes: str = Form(...)):
    if not check_auth(request): return JSONResponse({"error": "unauth"}, status_code=401)
    
    lines = [c.strip() for c in codes.splitlines() if c.strip()]
    if not lines: return JSONResponse({"error": "لا توجد أكواد للرفع"})

    unique_input, dupes_in_input, seen = [], [], set()
    for c in lines:
        if c in seen: dupes_in_input.append(c)
        else:
            seen.add(c)
            unique_input.append(c)
            
    in_stock = await db.stock.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    in_map = await db.codes_map.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    
    db_dupes = set([str(x.get("code") or x.get("_id")) for x in in_stock + in_map])
    
    new_codes, db_dupes_list = [], []
    for c in unique_input:
        if c in db_dupes: db_dupes_list.append(c)
        else: new_codes.append(c)
            
    all_dupes = dupes_in_input + db_dupes_list
    
    if new_codes:
        docs = [{"code": c, "category": category, "added_at": datetime.now()} for c in new_codes]
        await db.stock.insert_many(docs, ordered=False)
        await web_log(f"إضافة ذكية للمخزن ({category} UC)", f"تم إضافة {len(new_codes)} كود جديد.")

    return JSONResponse({
        "success": True,
        "total": len(lines),
        "added": len(new_codes),
        "dupes": len(all_dupes),
        "dupes_list": all_dupes
    })

@app.get("/api/view_stock/{category}")
async def api_view_stock(category: str, request: Request):
    if not check_auth(request): return JSONResponse({"error": "unauth"}, status_code=401)
    codes_docs = await db.stock.find({"category": category}).to_list(None)
    codes_list = [str(c.get("code") or c.get("_id")) for c in codes_docs]
    return JSONResponse({"category": category, "codes": codes_list})

@app.post("/api/clear_stock")
async def api_clear_stock(request: Request, category: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    await db.stock.delete_many({"category": category})
    await web_log(f"تصفير فئة {category} بالكامل من المخزن")
    return RedirectResponse(url="/?tab=stock", status_code=status.HTTP_302_FOUND)

@app.post("/api/add_shared_tokens")
async def api_add_shared(request: Request, tokens: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    extracted_tokens = clean_and_extract_tokens(tokens) # استخدام الفلتر الذكي
    if extracted_tokens: 
        await db.settings.update_one({"_id": "shared_tokens"}, {"$push": {"tokens": {"$each": extracted_tokens}}}, upsert=True)
        await web_log(f"تمت إضافة {len(extracted_tokens)} توكنات مشتركة")
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
    extracted_tokens = clean_and_extract_tokens(tokens) # استخدام الفلتر الذكي
    if extracted_tokens: 
        await db.users.update_one({"_id": user_id}, {"$push": {"tokens": {"$each": extracted_tokens}}})
        await web_log(f"إضافة {len(extracted_tokens)} توكن للمستخدم {user_id}")
    return RedirectResponse(url="/?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/add_user")
async def api_add_user(request: Request, user_id: int = Form(...), name: str = Form(...), role: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if not await db.users.find_one({"_id": user_id}):
        await db.users.insert_one({"_id": user_id, "role": role, "name": name, "tokens": [], "history": [], "logs": [], "token_logs": [], "stats": {"api": 0, "stock": 0}})
        await web_log(f"إضافة مستخدم جديد", f"الاسم: {name} | الآيدي: {user_id} | الرتبة: {role}")
    return RedirectResponse(url="/?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/user_action")
async def api_user_action(request: Request, user_id: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if action == "delete": 
        await db.users.delete_one({"_id": user_id})
        await web_log(f"حذف المستخدم ID: {user_id}")
    elif action == "clear_tokens": 
        await db.users.update_one({"_id": user_id}, {"$set": {"tokens": []}})
        await web_log(f"تصفير توكنات المستخدم {user_id}")
    elif action == "toggle_role":
        u = await db.users.find_one({"_id": user_id})
        nr = "employee" if u.get("role") == "user" else "user"
        await db.users.update_one({"_id": user_id}, {"$set": {"role": nr}})
        await web_log(f"تعديل رتبة المستخدم {user_id} إلى {nr}")
    elif action == "clear_logs":
        await db.users.update_one({"_id": user_id}, {"$set": {"logs": [], "history": [], "token_logs": []}})
        await web_log(f"مسح سجلات المستخدم {user_id}")
    return RedirectResponse(url="/?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/tracked_users")
async def api_tracked_users(request: Request, user_id: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if action == "add": 
        await db.settings.update_one({"_id": "cache_config"}, {"$addToSet": {"tracked_users": user_id}}, upsert=True)
        await web_log(f"إضافة الآيدي {user_id} لقائمة التخزين التلقائي")
    elif action == "remove": 
        await db.settings.update_one({"_id": "cache_config"}, {"$pull": {"tracked_users": user_id}}, upsert=True)
        await web_log(f"إزالة الآيدي {user_id} من قائمة التخزين التلقائي")
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
        await web_log(f"إرجاع الطلب #{order_id} للمخزن", f"الفئة: {cat} | العدد: {len(order['items'])}")
    return RedirectResponse(url="/?tab=tools", status_code=status.HTTP_302_FOUND)

@app.post("/api/search")
async def api_search(request: Request):
    if not check_auth(request): return JSONResponse({"error": "unauth"})
    form = await request.form()
    query = form.get("query", "").strip()
    if not query: return JSONResponse({"result": "❌ أرسل نصاً للبحث"})
    
    if query.isdigit():
        order = await db.orders.find_one({"_id": int(query)})
        if order: 
            items_str = "\n".join([f"  - {item}" for item in order.get('items', [])])
            res_msg = (f"📄 تقرير الطلب #{query}\n👤 المستلم: {order.get('user', 'غير معروف')} | ID: {order.get('user_id', 'غير معروف')}\n"
                       f"📅 التاريخ: {order.get('date', 'غير متوفر')}\n📦 النوع: {order.get('type', 'غير محدد')}\n\n"
                       f"⬇️ العناصر المسحوبة ({len(order.get('items', []))}):\n{items_str}")
            return JSONResponse({"result": res_msg})
        user = await db.users.find_one({"_id": int(query)})
        if user: 
            return JSONResponse({"result": f"👤 {user.get('name')}\n🆔 الآيدي: {user.get('_id')}\n🎖 الرتبة: {user.get('role')}\n🔑 التوكنات: {len(user.get('tokens',[]))}"})

    records = await db.codes_map.find({"$or": [{"_id": query}, {"code": query}]}).to_list(length=10)
    in_stock = await db.stock.count_documents({"$or": [{"_id": query}, {"code": query}]})
    
    res_str = f"🔍 نتيجة البحث عن: {query}\n📦 متوفر بالمخزن حالياً: {in_stock} مرات\n"
    if records:
        res_str += f"\n🛒 تم سحبه {len(records)} مرات:\n"
        for i, r in enumerate(records, 1):
            res_str += f" {i}. بواسطة: {r.get('name', 'مجهول')} | الوقت: {r.get('time', '')} | طلب: #{r.get('order_id', '؟')}\n"
    elif in_stock == 0:
        res_str += "\n❌ لا يوجد بيانات! (لم يتم العثور على طلب، مستخدم، أو كود)."
    return JSONResponse({"result": res_str})
