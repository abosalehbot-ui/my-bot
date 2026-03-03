import os
import re
from fastapi import FastAPI, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta

# ─── الاتصال بقاعدة البيانات والإعدادات ────────────────────
from database import db, get_next_order_id
from config import SECRET_TOKEN, ADMIN_ID

from store_routes import router as store_router

app = FastAPI(title="Saleh Zone Dashboard")
app.include_router(store_router)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "123456")

def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

async def web_log(action, details=""):
    await db.system_logs.insert_one({
        "user_id": "WEB_ADMIN", "name": "Admin Dashboard", "action": action,
        "details": details, "time": datetime.now().strftime('%Y-%m-%d %H:%M'), "timestamp": datetime.now()
    })

def clean_and_extract_tokens(raw_text):
    valid_tokens = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line: continue
        if "::" in line:
            parts = line.split()
            for p in parts:
                if "::" in p: valid_tokens.append(p); break
        elif len(line) > 20 and not " " in line:
            valid_tokens.append(line)
    return valid_tokens

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if check_auth(request): return RedirectResponse(url="/admin")
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def do_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="admin_session", value=SECRET_TOKEN, httponly=True, max_age=86400)
        await web_log("Login Success", "Master admin logged in via web.")
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials!"})

@app.get("/logout")
async def do_logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("admin_session")
    return response

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not check_auth(request): return RedirectResponse(url="/login")

    users_count = await db.users.count_documents({})
    global_stats = await db.stats.find_one({"_id": "global_stats"}) or {}
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    month_str = datetime.now().strftime("%Y-%m")
    
    store_orders = await db.store_orders.find().to_list(None)
    rev_today = sum(float(o.get("price", 0)) for o in store_orders if o.get("date", "").startswith(today_str) and o.get("currency") == "EGP")
    rev_month = sum(float(o.get("price", 0)) for o in store_orders if o.get("date", "").startswith(month_str) and o.get("currency") == "EGP")
    sales_today = sum(1 for o in store_orders if o.get("date", "").startswith(today_str))
    sales_month = sum(1 for o in store_orders if o.get("date", "").startswith(month_str))

    store_stats = {
        "rev_today": round(rev_today, 2), "rev_month": round(rev_month, 2),
        "sales_today": sales_today, "sales_month": sales_month
    }

    categories = await db.store_categories.find().to_list(None)
    
    # 🔴 هنا حل المشكلة: بنأمن المنتجات القديمة عشان متعملش إيرور في الواجهة
    for cat in categories:
        for p in cat.get("products", []):
            if "prices" not in p:
                p["prices"] = {
                    "EGP": p.get("price_egp", 0),
                    "USD": p.get("price_usd", 0)
                }

    currencies = await db.store_currencies.find().to_list(None)
    if not currencies:
        default_curs = [{"_id": "EGP", "symbol": "EGP"}, {"_id": "USD", "symbol": "USD"}]
        await db.store_currencies.insert_many(default_curs)
        currencies = default_curs

    stock_keys = []
    for c in categories:
        for p in c.get("products", []): stock_keys.append(p["stock_key"])
    
    stock_details = {}
    for sk in stock_keys:
        count = await db.stock.count_documents({"category": sk})
        if count > 0: stock_details[sk] = count

    stock_count = await db.stock.count_documents({})
    logs = await db.system_logs.find().sort("timestamp", -1).limit(50).to_list(None)
    all_users = await db.users.find().to_list(None)
    shared_tokens_count = await db.shared_tokens.count_documents({})
    
    config = await db.settings.find_one({"_id": "config"}) or {}
    maintenance = config.get("maintenance", False)
    cache_cfg = await db.settings.find_one({"_id": "cache_config"}) or {}
    tracked_users = cache_cfg.get("tracked_users", [ADMIN_ID])

    return templates.TemplateResponse("index.html", {
        "request": request, "users_count": users_count, "global_stats": global_stats,
        "store_stats": store_stats, "categories": categories, "currencies": currencies, 
        "stock_details": stock_details, "dynamic_stock_keys": stock_keys,
        "logs": logs, "all_users": all_users, "shared_tokens_count": shared_tokens_count,
        "maintenance": maintenance, "tracked_users": tracked_users, "stock_count": stock_count
    })

@app.post("/api/catalog/currency/add")
async def add_currency(request: Request, code: str = Form(...), symbol: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    code = code.upper().strip()
    if await db.store_currencies.find_one({"_id": code}):
        return JSONResponse({"success": False, "msg": "Currency already exists!"})
    await db.store_currencies.insert_one({"_id": code, "symbol": symbol})
    await web_log(f"Added Currency: {code}")
    return JSONResponse({"success": True, "msg": "Currency added successfully!"})

@app.post("/api/catalog/currency/delete")
async def delete_currency(request: Request, code: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    await db.store_currencies.delete_one({"_id": code})
    await web_log(f"Deleted Currency: {code}")
    return JSONResponse({"success": True, "msg": "Currency deleted!"})

@app.post("/api/catalog/category/add")
async def add_category(request: Request, cat_id: str = Form(...), name: str = Form(...), icon: str = Form("fa-gamepad"), image: str = Form("")):
    if not check_auth(request): return JSONResponse({"success": False})
    if await db.store_categories.find_one({"_id": cat_id}):
        return JSONResponse({"success": False, "msg": "Category ID already exists!"})
    await db.store_categories.insert_one({"_id": cat_id, "name": name, "icon": icon, "image": image, "products": []})
    await web_log(f"Added Category: {name}")
    return JSONResponse({"success": True, "msg": "Category created!"})

@app.post("/api/catalog/category/edit")
async def edit_category(request: Request, cat_id: str = Form(...), name: str = Form(...), icon: str = Form(...), image: str = Form("")):
    if not check_auth(request): return JSONResponse({"success": False})
    await db.store_categories.update_one({"_id": cat_id}, {"$set": {"name": name, "icon": icon, "image": image}})
    await web_log(f"Edited Category: {name}")
    return JSONResponse({"success": True, "msg": "Category updated!"})

@app.post("/api/catalog/category/delete")
async def delete_category(request: Request, cat_id: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    await db.store_categories.delete_one({"_id": cat_id})
    await web_log(f"Deleted Category: {cat_id}")
    return JSONResponse({"success": True, "msg": "Category deleted!"})

@app.post("/api/catalog/product/add")
async def add_product(request: Request):
    if not check_auth(request): return JSONResponse({"success": False})
    form = await request.form()
    cat_id = form.get("cat_id")
    stock_key = form.get("stock_key")
    name = form.get("name")
    
    prices = {}
    for key, val in form.items():
        if key.startswith("price_"):
            curr_code = key.replace("price_", "").upper()
            prices[curr_code] = float(val) if val else 0.0

    new_prod = {
        "stock_key": stock_key, "name": name, "prices": prices,
        "price_egp": prices.get("EGP", 0), "price_usd": prices.get("USD", 0)
    }
    
    await db.store_categories.update_one({"_id": cat_id}, {"$push": {"products": new_prod}})
    await web_log(f"Added Product: {name} ({stock_key})")
    return JSONResponse({"success": True, "msg": "Product added!"})

@app.post("/api/catalog/product/edit")
async def edit_product(request: Request):
    if not check_auth(request): return JSONResponse({"success": False})
    form = await request.form()
    cat_id = form.get("cat_id")
    stock_key = form.get("stock_key")
    name = form.get("name")

    prices = {}
    for key, val in form.items():
        if key.startswith("price_"):
            curr_code = key.replace("price_", "").upper()
            prices[curr_code] = float(val) if val else 0.0

    await db.store_categories.update_one(
        {"_id": cat_id, "products.stock_key": stock_key},
        {"$set": {
            "products.$.name": name,
            "products.$.prices": prices,
            "products.$.price_egp": prices.get("EGP", 0),
            "products.$.price_usd": prices.get("USD", 0)
        }}
    )
    await web_log(f"Edited Product Pricing: {name}")
    return JSONResponse({"success": True, "msg": "Product pricing updated!"})

@app.post("/api/catalog/product/delete")
async def delete_product(request: Request, cat_id: str = Form(...), stock_key: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    await db.store_categories.update_one({"_id": cat_id}, {"$pull": {"products": {"stock_key": stock_key}}})
    await web_log(f"Deleted Product: {stock_key}")
    return JSONResponse({"success": True, "msg": "Product removed!"})

# --- بقية الدوال الخاصة باليوزرز والأدوات كما هي تماماً ---
@app.post("/api/add_user")
async def add_user(request: Request, user_id: int = Form(...), name: str = Form(...), role: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/admin")
    await db.users.update_one({"_id": user_id}, {"$set": {"name": name, "role": role, "tokens": [], "logs": [], "stats": {"api": 0, "stock": 0}, "stats_details": {"api_today": 0, "api_month": 0, "stock_today": 0, "stock_month": 0}}}, upsert=True)
    return RedirectResponse("/admin?tab=users", status_code=303)

@app.post("/api/add_user_tokens")
async def add_user_tokens(request: Request, user_id: int = Form(...), tokens: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    extracted = clean_and_extract_tokens(tokens)
    if not extracted: return JSONResponse({"success": False, "msg": "No valid tokens found!"})
    await db.users.update_one({"_id": user_id}, {"$push": {"tokens": {"$each": extracted}}})
    return JSONResponse({"success": True, "msg": f"Added {len(extracted)} tokens!"})

@app.post("/api/user_action")
async def user_action(request: Request, user_id: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/admin")
    if action == "delete": await db.users.delete_one({"_id": user_id})
    elif action == "clear_tokens": await db.users.update_one({"_id": user_id}, {"$set": {"tokens": []}})
    elif action == "clear_logs": await db.users.update_one({"_id": user_id}, {"$set": {"logs": []}})
    elif action == "toggle_role":
        user = await db.users.find_one({"_id": user_id})
        if user:
            new_role = "employee" if user.get("role") == "user" else "user"
            await db.users.update_one({"_id": user_id}, {"$set": {"role": new_role}})
    return RedirectResponse("/admin?tab=users", status_code=303)

@app.post("/api/add_shared_tokens")
async def add_shared_tokens(request: Request, tokens: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/admin")
    extracted = clean_and_extract_tokens(tokens)
    if extracted: await db.shared_tokens.insert_many([{"token": t} for t in extracted])
    return RedirectResponse("/admin?tab=users", status_code=303)

@app.post("/api/clear_shared_tokens")
async def clear_shared_tokens(request: Request):
    if not check_auth(request): return RedirectResponse("/admin")
    await db.shared_tokens.delete_many({})
    return RedirectResponse("/admin?tab=users", status_code=303)

@app.get("/api/view_shared_tokens")
async def view_shared_tokens(request: Request):
    if not check_auth(request): return JSONResponse({"tokens": []})
    tokens = await db.shared_tokens.find().to_list(None)
    return JSONResponse({"tokens": [t["token"] for t in tokens]})

@app.post("/api/add_stock_smart")
async def add_stock_smart(request: Request, category: str = Form(...), codes: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    lines = [c.strip() for c in codes.splitlines() if c.strip()]
    if not lines: return JSONResponse({"success": False, "msg": "Empty input!"})
    
    unique_input, dupes_in_input, seen = [], [], set()
    for c in lines:
        if c in seen: dupes_in_input.append(c)
        else:
            seen.add(c)
            unique_input.append(c)

    in_stock = await db.stock.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    in_map = await db.codes_map.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    
    existing = {doc["_id"] for doc in in_stock}.union({doc.get("code") for doc in in_stock})
    existing.update({doc["_id"] for doc in in_map}.union({doc.get("code") for doc in in_map}))
    
    to_insert = [c for c in unique_input if c not in existing]
    dupes_db = [c for c in unique_input if c in existing]
    
    if to_insert:
        await db.stock.insert_many([{"_id": str(random.randint(1000000, 9999999)), "code": c, "category": category} for c in to_insert])
        
    return JSONResponse({"success": True, "total": len(lines), "added": len(to_insert), "dupes": len(dupes_in_input + dupes_db), "dupes_list": dupes_in_input + dupes_db})

@app.post("/api/clear_stock")
async def clear_stock(request: Request, category: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/admin")
    await db.stock.delete_many({"category": category})
    return RedirectResponse("/admin?tab=stock", status_code=303)

@app.get("/api/view_stock/{category}")
async def view_stock(request: Request, category: str):
    if not check_auth(request): return JSONResponse({"codes": []})
    codes = await db.stock.find({"category": category}).to_list(None)
    return JSONResponse({"codes": [c.get("code", c["_id"]) for c in codes]})

@app.post("/api/toggle_maintenance")
async def api_toggle_maintenance(request: Request):
    if not check_auth(request): return JSONResponse({"success": False})
    config = await db.settings.find_one({"_id": "config"}) or {}
    await db.settings.update_one({"_id": "config"}, {"$set": {"maintenance": not config.get("maintenance", False)}}, upsert=True)
    return JSONResponse({"success": True})

@app.post("/api/tracked_users")
async def manage_tracked_users(request: Request, user_id: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/admin")
    if action == "add": await db.settings.update_one({"_id": "cache_config"}, {"$addToSet": {"tracked_users": user_id}}, upsert=True)
    elif action == "remove": await db.settings.update_one({"_id": "cache_config"}, {"$pull": {"tracked_users": user_id}}, upsert=True)
    return RedirectResponse("/admin?tab=tools", status_code=303)

@app.post("/api/return_order")
async def return_order(request: Request, order_id: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/admin")
    order_id = order_id.strip()
    if order_id.endswith("S"):
        order = await db.store_orders.find_one_and_delete({"_id": order_id})
        if not order: return RedirectResponse("/admin?tab=tools", status_code=303)
        if order.get("code") and order.get("category"):
            await db.stock.insert_one({"_id": str(random.randint(1000000,9999999)), "code": order["code"], "category": order["category"]})
        if order.get("email") and order.get("price", 0) > 0:
            await db.store_customers.update_one({"email": order["email"]}, {"$inc": {f"balance_{order.get('currency', 'EGP').lower()}": order["price"]}})
        await db.codes_map.delete_one({"order_id": order_id})
    else:
        try: record = await db.codes_map.find_one_and_delete({"order_id": int(order_id)})
        except: return RedirectResponse("/admin?tab=tools", status_code=303)
        if record and record.get("source") != "API":
            await db.stock.insert_one({"_id": str(random.randint(1000000,9999999)), "code": record["code"], "category": record.get("category", "Returned")})
    return RedirectResponse("/admin?tab=tools", status_code=303)

@app.post("/api/search")
async def search_database(request: Request, query: str = Form(...)):
    if not check_auth(request): return JSONResponse({"result": "Unauthorized"})
    query = query.strip()
    if query.isdigit() or query.endswith("S"):
        is_bot = query.isdigit()
        if is_bot:
            record = await db.codes_map.find_one({"order_id": int(query)})
            if record: return JSONResponse({"result": f"🤖 Bot Order #{query}\n👤 By: {record.get('name')}\n📅 Date: {record.get('time')}\n📦 Type: {record.get('source')}\n\n⬇️ Delivered Code:\n  - {record.get('code')}"})
            order = await db.orders.find_one({"_id": int(query)})
            if order: return JSONResponse({"result": f"🤖 Bot API Order #{query}\n👤 By: {order.get('name')}\n📅 Date: {order.get('time')}\n📦 Type: {order.get('type')}\n\n⬇️ Items ({len(order.get('items',[]))}):\n" + "\n".join([f"  - {i}" for i in order.get('items', [])])})
        else:
            order = await db.store_orders.find_one({"_id": query})
            if order: return JSONResponse({"result": f"🛒 Web Store Order #{query}\n👤 By: {order.get('name', 'Unknown')} | Email: {order.get('email')}\n📅 Date: {order.get('date')}\n📦 Package: {order.get('category')}\n💰 Paid: {order.get('price', 'N/A')} {order.get('currency', '')}\n\n⬇️ Delivered Code:\n  - {order.get('code')}"})
        if is_bot:
            user = await db.users.find_one({"_id": int(query)})
            if user: return JSONResponse({"result": f"👤 {user.get('name')}\n🆔 ID: {user.get('_id')}\n🎖 Role: {user.get('role')}\n🔑 Tokens: {len(user.get('tokens', []))}"})

    records = await db.codes_map.find({"$or": [{"_id": query}, {"code": query}]}).to_list(length=10)
    in_stock = await db.stock.count_documents({"$or": [{"_id": query}, {"code": query}]})
    res_str = f"🔍 Search result for: {query}\n📦 Currently in stock: {in_stock} times\n"
    if records:
        res_str += f"\n📜 Found in {len(records)} previous orders:\n" + "".join([f" - Order #{r.get('order_id')} by {r.get('name')} at {r.get('time')}\n" for r in records])
    else: res_str += "\n❌ Not found in sales history."
    return JSONResponse({"result": res_str})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
