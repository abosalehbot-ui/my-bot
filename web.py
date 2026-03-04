import os
import re
import uuid
import base64
from fastapi import FastAPI, Request, Form, Response, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta

# ─── الاتصال الوحيد بقاعدة البيانات للـ web process ────────────────────
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
        if not line:
            continue
        token = re.split(r'[;:\s\|]', line)[0].strip()
        if len(token) > 15 and re.match(r'^[A-Za-z0-9\-_]+$', token):
            valid_tokens.append(token)
    return valid_tokens


async def save_upload(file: UploadFile) -> str:
    """حفظ الملف المرفوع داخل Mongo كـ data URI لتفادي ضياع الصور مع إعادة التشغيل."""
    if not file or not file.filename:
        return ""

    content = await file.read()
    if not content:
        return ""
    if len(content) > 2_000_000:
        raise ValueError("Image too large (max 2MB)")

    content_type = (file.content_type or "").lower()
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
    if content_type not in allowed_types:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        guessed = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "gif": "image/gif",
        }.get(ext)
        if guessed:
            content_type = guessed
        else:
            raise ValueError("Invalid image type")

    b64 = base64.b64encode(content).decode("utf-8")
    return f"data:{content_type};base64,{b64}"


def convert_objectids(document):
    """تحويل ObjectId لـ string لتجنب أخطاء JSON."""
    if isinstance(document, list):
        for item in document:
            convert_objectids(item)
    elif isinstance(document, dict):
        for key, value in list(document.items()):
            if key == "_id" and not isinstance(value, (str, int, float)):
                document[key] = str(value)
            else:
                convert_objectids(value)
    return document


# ==========================================
# Login / Logout
# ==========================================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def do_login(response: Response, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        resp = RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
        resp.set_cookie(key="admin_session", value=SECRET_TOKEN, httponly=True)
        return resp
    return RedirectResponse(url="/login?error=1", status_code=status.HTTP_302_FOUND)

@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie("admin_session")
    return resp


# ==========================================
# Dashboard
# ==========================================
@app.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login")

    now               = datetime.now()
    today_str         = now.strftime("%Y-%m-%d")
    start_of_month    = now.strftime("%Y-%m-01")

    users_count  = await db.users.count_documents({})
    stock_count  = await db.stock.count_documents({})
    cached_count = await db.cached_accounts.count_documents({})
    logs         = await db.system_logs.find().sort("timestamp", -1).to_list(length=100)
    all_users    = await db.users.find().sort("_id", -1).to_list(length=50)

    month_orders = await db.orders.find({"date": {"$gte": start_of_month}}).to_list(None)
    global_stats = {"api_today": 0, "api_month": 0, "stock_today": 0, "stock_month": 0}
    user_stats   = {}

    for o in month_orders:
        uid      = o.get("user_id")
        count    = len(o.get("items", []))
        is_today = o.get("date", "").startswith(today_str)
        is_api   = "API" in o.get("type", "")
        if uid not in user_stats:
            user_stats[uid] = {"api_today": 0, "api_month": 0, "stock_today": 0, "stock_month": 0}

        key = "api" if is_api else "stock"
        global_stats[f"{key}_month"] += count
        user_stats[uid][f"{key}_month"] += count
        if is_today:
            global_stats[f"{key}_today"] += count
            user_stats[uid][f"{key}_today"] += count

    store_orders = await db.store_orders.find({"date": {"$gte": start_of_month}}).to_list(None)
    store_stats  = {"sales_today": 0, "sales_month": len(store_orders), "rev_today": 0.0, "rev_month": 0.0}
    for so in store_orders:
        price = float(so.get("price", 0))
        store_stats["rev_month"] += price
        if so.get("date", "").startswith(today_str):
            store_stats["sales_today"] += 1
            store_stats["rev_today"]   += price

    total_user_tokens   = sum(len(u.get("tokens", [])) for u in all_users)
    shared_doc          = await db.settings.find_one({"_id": "shared_tokens"})
    shared_tokens_count = len(shared_doc.get("tokens", [])) if shared_doc else 0
    total_system_tokens = total_user_tokens + shared_tokens_count

    for u in all_users:
        u["stats_details"] = user_stats.get(u["_id"], {"api_today": 0, "api_month": 0, "stock_today": 0, "stock_month": 0})

    categories       = await db.store_categories.find().to_list(100)
    dynamic_stock_keys = []
    stock_details    = {}
    for c in categories:
        for p in c.get("products", []):
            dynamic_stock_keys.append(p["stock_key"])
            stock_details[p["stock_key"]] = await db.stock.count_documents({"category": p["stock_key"]})

    # ── جلب العملات للـ Dashboard ──────────────────────────────────────────
    currencies = await db.store_currencies.find().to_list(None)
    if not currencies:
        default_curs = [{"_id": "EGP", "symbol": "EGP"}, {"_id": "USD", "symbol": "USD"}]
        await db.store_currencies.insert_many(default_curs)
        currencies = default_curs

    # ── حماية المنتجات القديمة من أخطاء prices ────────────────────────────
    for cat in categories:
        for p in cat.get("products", []):
            if "prices" not in p:
                p["prices"] = {
                    "EGP": p.get("price_egp", 0),
                    "USD": p.get("price_usd", 0),
                }

    settings    = await db.settings.find_one({"_id": "config"})
    maintenance = settings.get("maintenance", False) if settings else False

    cache_config  = await db.settings.find_one({"_id": "cache_config"})
    tracked_users = cache_config.get("tracked_users", []) if cache_config else []

    all_users  = convert_objectids(all_users)
    categories = convert_objectids(categories)
    logs       = convert_objectids(logs)

    return templates.TemplateResponse("index.html", {
        "request": request, "users_count": users_count, "stock_count": stock_count,
        "cached_count": cached_count, "logs": logs, "all_users": all_users,
        "stock_details": stock_details, "dynamic_stock_keys": dynamic_stock_keys,
        "categories": categories, "currencies": currencies, "maintenance": maintenance,
        "shared_tokens_count": shared_tokens_count, "total_system_tokens": total_system_tokens,
        "global_stats": global_stats, "store_stats": store_stats, "tracked_users": tracked_users,
    })


# ==========================================
# Currencies APIs (إدارة العملات)
# ==========================================
@app.post("/api/catalog/currency/add")
async def api_add_currency(request: Request, code: str = Form(...), symbol: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    code = code.upper().strip()
    if await db.store_currencies.find_one({"_id": code}):
        return JSONResponse({"success": False, "msg": "Currency already exists!"})
    await db.store_currencies.insert_one({"_id": code, "symbol": symbol.strip()})
    await web_log("إضافة عملة", f"{code} ({symbol})")
    return JSONResponse({"success": True, "msg": f"Currency {code} added successfully!"})

@app.post("/api/catalog/currency/delete")
async def api_delete_currency(request: Request, code: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauthorized"})
    await db.store_currencies.delete_one({"_id": code})
    await web_log("حذف عملة", code)
    return JSONResponse({"success": True, "msg": f"Currency {code} deleted!"})


# ==========================================
# Catalog APIs (الكتالوج والصور والأسعار)
# ==========================================
@app.post("/api/catalog/category/add")
async def api_add_category(
    request: Request,
    cat_id: str = Form(...),
    name: str = Form(...),
    icon: str = Form("fa-gamepad"),
    image: UploadFile = File(None),
    logo: UploadFile = File(None),
):
    if not check_auth(request): return JSONResponse({"success": False, "msg": "Unauth"})
    cat_id = cat_id.lower().replace(" ", "_")
    if await db.store_categories.find_one({"_id": cat_id}):
        return JSONResponse({"success": False, "msg": "ID exists!"})
    try:
        image_url = await save_upload(image) if image and image.filename else ""
        logo_url  = await save_upload(logo)  if logo  and logo.filename  else ""
    except ValueError as e:
        return JSONResponse({"success": False, "msg": str(e)})
    await db.store_categories.insert_one({
        "_id": cat_id, "name": name, "icon": icon,
        "image": image_url, "logo": logo_url, "products": []
    })
    await web_log("إنشاء فئة جديدة", f"الفئة: {name}")
    return JSONResponse({"success": True, "msg": "Category Added!"})

@app.post("/api/catalog/category/edit")
async def api_edit_category(
    request: Request,
    cat_id: str = Form(...),
    name: str = Form(...),
    icon: str = Form(...),
    image: UploadFile = File(None),
    logo: UploadFile = File(None),
):
    if not check_auth(request): return JSONResponse({"success": False})
    update_data = {"name": name, "icon": icon}
    try:
        if image and image.filename:
            update_data["image"] = await save_upload(image)
        if logo and logo.filename:
            update_data["logo"] = await save_upload(logo)
    except ValueError as e:
        return JSONResponse({"success": False, "msg": str(e)})
    await db.store_categories.update_one({"_id": cat_id}, {"$set": update_data})
    await web_log("تعديل فئة", f"{cat_id} → {name}")
    return JSONResponse({"success": True, "msg": "Category Updated!"})

@app.post("/api/catalog/category/delete")
async def api_delete_category(request: Request, cat_id: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    await db.store_categories.delete_one({"_id": cat_id})
    return JSONResponse({"success": True, "msg": "Category Deleted!"})

@app.post("/api/catalog/product/add")
async def api_add_product(request: Request, image: UploadFile = File(None)):
    if not check_auth(request): return JSONResponse({"success": False})
    form      = await request.form()
    cat_id    = form.get("cat_id")
    stock_key = form.get("stock_key")
    name      = form.get("name")

    try:
        image_url = await save_upload(image) if image and image.filename else form.get("image", "")
    except ValueError as e:
        return JSONResponse({"success": False, "msg": str(e)})

    # بناء كائن الأسعار ديناميكياً لدعم أي عملة
    prices = {}
    for key, val in form.items():
        if key.startswith("price_"):
            curr_code = key.replace("price_", "").upper()
            try:
                prices[curr_code] = float(val) if val else 0.0
            except ValueError:
                prices[curr_code] = 0.0

    product = {
        "stock_key": stock_key,
        "name":      name,
        "image":     image_url,
        "prices":    prices,
        "price_egp": prices.get("EGP", 0),
        "price_usd": prices.get("USD", 0),
    }
    await db.store_categories.update_one({"_id": cat_id}, {"$push": {"products": product}})
    await web_log("إضافة منتج", f"{name} في {cat_id}")
    return JSONResponse({"success": True, "msg": "Product Added!"})

@app.post("/api/catalog/product/edit")
async def api_edit_product(request: Request, image: UploadFile = File(None)):
    if not check_auth(request): return JSONResponse({"success": False})
    form      = await request.form()
    cat_id    = form.get("cat_id")
    stock_key = form.get("stock_key")
    name      = form.get("name")

    update_fields = {"products.$.name": name}
    try:
        if image and image.filename:
            update_fields["products.$.image"] = await save_upload(image)
        elif form.get("image"):
            update_fields["products.$.image"] = form.get("image")
    except ValueError as e:
        return JSONResponse({"success": False, "msg": str(e)})

    prices = {}
    for key, val in form.items():
        if key.startswith("price_"):
            curr_code = key.replace("price_", "").upper()
            try:
                prices[curr_code] = float(val) if val else 0.0
            except ValueError:
                prices[curr_code] = 0.0

    update_fields["products.$.prices"]    = prices
    update_fields["products.$.price_egp"] = prices.get("EGP", 0)
    update_fields["products.$.price_usd"] = prices.get("USD", 0)

    await db.store_categories.update_one(
        {"_id": cat_id, "products.stock_key": stock_key},
        {"$set": update_fields}
    )
    return JSONResponse({"success": True, "msg": "Product Updated!"})

@app.post("/api/catalog/product/delete")
async def api_delete_product(request: Request, cat_id: str = Form(...), stock_key: str = Form(...)):
    if not check_auth(request): return JSONResponse({"success": False})
    await db.store_categories.update_one({"_id": cat_id}, {"$pull": {"products": {"stock_key": stock_key}}})
    return JSONResponse({"success": True, "msg": "Product Deleted!"})


# ==========================================
# Tools & Stock APIs
# ==========================================
@app.post("/api/toggle_maintenance")
async def toggle_maint(request: Request):
    if not check_auth(request): return {"status": "error"}
    current   = await db.settings.find_one({"_id": "config"})
    new_state = not current.get("maintenance", False) if current else True
    await db.settings.update_one({"_id": "config"}, {"$set": {"maintenance": new_state}}, upsert=True)
    return {"status": "success"}

@app.post("/api/add_stock_smart")
async def api_add_stock_smart(request: Request, category: str = Form(...), codes: str = Form(...)):
    if not check_auth(request): return JSONResponse({"error": "unauth"}, status_code=401)
    lines = [c.strip() for c in codes.splitlines() if c.strip()]
    if not lines: return JSONResponse({"error": "No codes to upload"})

    unique_input, dupes_in_input, seen = [], [], set()
    for c in lines:
        if c in seen: dupes_in_input.append(c)
        else: seen.add(c); unique_input.append(c)

    in_stock = await db.stock.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    in_map   = await db.codes_map.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    db_dupes = set(str(x.get("code") or x.get("_id")) for x in in_stock + in_map)

    new_codes, db_dupes_list = [], []
    for c in unique_input:
        if c in db_dupes: db_dupes_list.append(c)
        else: new_codes.append(c)

    all_dupes = dupes_in_input + db_dupes_list
    if new_codes:
        docs = [{"code": c, "category": category, "added_at": datetime.now()} for c in new_codes]
        await db.stock.insert_many(docs, ordered=False)

    return JSONResponse({"success": True, "total": len(lines), "added": len(new_codes),
                         "dupes": len(all_dupes), "dupes_list": all_dupes})

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
    return RedirectResponse(url="/admin?tab=stock", status_code=status.HTTP_302_FOUND)

@app.get("/api/view_shared_tokens")
async def api_view_shared_tokens(request: Request):
    if not check_auth(request): return JSONResponse({"error": "unauth"}, status_code=401)
    shared_doc = await db.settings.find_one({"_id": "shared_tokens"})
    tokens = shared_doc.get("tokens", []) if shared_doc else []
    return JSONResponse({"tokens": tokens})

@app.post("/api/add_shared_tokens")
async def api_add_shared(request: Request, tokens: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    extracted = clean_and_extract_tokens(tokens)
    if extracted:
        await db.settings.update_one({"_id": "shared_tokens"}, {"$push": {"tokens": {"$each": extracted}}}, upsert=True)
    return RedirectResponse(url="/admin?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/clear_shared_tokens")
async def api_clear_shared(request: Request):
    if not check_auth(request): return RedirectResponse("/login")
    await db.settings.update_one({"_id": "shared_tokens"}, {"$set": {"tokens": []}}, upsert=True)
    return RedirectResponse(url="/admin?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/add_user_tokens")
async def api_add_user_tokens(request: Request, user_id: int = Form(...), tokens: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    extracted = clean_and_extract_tokens(tokens)
    if extracted:
        await db.users.update_one({"_id": user_id}, {"$push": {"tokens": {"$each": extracted}}})
    return RedirectResponse(url="/admin?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/add_user")
async def api_add_user(request: Request, user_id: int = Form(...), name: str = Form(...), role: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if not await db.users.find_one({"_id": user_id}):
        await db.users.insert_one({"_id": user_id, "role": role, "name": name, "tokens": [],
                                   "history": [], "logs": [], "token_logs": [], "stats": {"api": 0, "stock": 0}})
    return RedirectResponse(url="/admin?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/user_action")
async def api_user_action(request: Request, user_id: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if action == "delete":
        await db.users.delete_one({"_id": user_id})
    elif action == "clear_tokens":
        await db.users.update_one({"_id": user_id}, {"$set": {"tokens": []}})
    elif action == "toggle_role":
        u = await db.users.find_one({"_id": user_id})
        new_role = "employee" if u.get("role") == "user" else "user"
        await db.users.update_one({"_id": user_id}, {"$set": {"role": new_role}})
    elif action == "clear_logs":
        await db.users.update_one({"_id": user_id}, {"$set": {"logs": [], "history": [], "token_logs": []}})
    return RedirectResponse(url="/admin?tab=users", status_code=status.HTTP_302_FOUND)

@app.post("/api/tracked_users")
async def api_tracked_users(request: Request, user_id: int = Form(...), action: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if action == "add":
        await db.settings.update_one({"_id": "cache_config"}, {"$addToSet": {"tracked_users": user_id}}, upsert=True)
    elif action == "remove":
        await db.settings.update_one({"_id": "cache_config"}, {"$pull": {"tracked_users": user_id}}, upsert=True)
    return RedirectResponse(url="/admin?tab=tools", status_code=status.HTTP_302_FOUND)

async def _log_store_wallet_txn(email: str, amount: float, currency: str, note: str, ref: str = ""):
    await db.store_wallet_ledger.insert_one({
        "email": email,
        "amount": float(amount),
        "currency": currency.upper(),
        "note": note,
        "ref": ref,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ts": datetime.now(),
    })

async def _process_return_order(order_id: str):
    order = await db.orders.find_one({"_id": int(order_id)}) if order_id.isdigit() else None
    if not order:
        order = await db.store_orders.find_one({"_id": order_id})

    if order and "items" in order:
        cat             = order["type"].split("(")[1].split(")")[0] if "(" in order.get("type", "") else "Unknown"
        codes_to_return = [{"code": c, "category": cat, "added_at": datetime.now()} for c in order["items"]]
        await db.stock.insert_many(codes_to_return, ordered=False)
        await db.codes_map.delete_many({"$or": [{"_id": {"$in": order["items"]}}, {"code": {"$in": order["items"]}}], "order_id": int(order_id)})
        await db.orders.delete_one({"_id": int(order_id)})
        await db.users.update_one({"_id": order["user_id"]}, {"$inc": {"stats.stock": -len(order["items"])}})
        return True, "Bot order returned"
    elif order and "code" in order:
        await db.stock.insert_one({"code": order["code"], "category": order["category"], "added_at": datetime.now()})
        await db.codes_map.delete_many({"$or": [{"_id": order["code"]}, {"code": order["code"]}], "order_id": order_id})
        await db.store_orders.delete_one({"_id": order_id})

        email = order.get("email")
        price = float(order.get("price", 0) or 0)
        currency = (order.get("currency") or "EGP").upper()
        if email and price > 0:
            bal_field = f"balance_{currency.lower()}"
            await db.store_customers.update_one({"email": email}, {"$inc": {bal_field: price}})
            await _log_store_wallet_txn(email, price, currency, f"Return refund #{order_id}", ref=order_id)

        return True, "Store order returned"

    return False, "Order not found"

@app.post("/api/return_order")
async def api_return_order(request: Request, order_id: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    ok, _ = await _process_return_order(order_id)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"success": ok, "msg": "Order returned to stock!" if ok else "Order not found"})
    return RedirectResponse(url="/store-admin", status_code=status.HTTP_302_FOUND)

@app.post("/api/return_orders_bulk")
async def api_return_orders_bulk(request: Request, order_ids: str = Form(...)):
    if not check_auth(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"}, status_code=401)

    ids = [x.strip() for x in order_ids.replace(',', '\\n').splitlines() if x.strip()]
    if not ids:
        return JSONResponse({"success": False, "msg": "No order IDs provided"})

    done, failed = [], []
    for oid in ids:
        ok, msg = await _process_return_order(oid)
        (done if ok else failed).append(oid if ok else f"{oid} ({msg})")

    return JSONResponse({
        "success": True,
        "processed": len(done),
        "failed": len(failed),
        "done": done,
        "errors": failed,
        "msg": f"Processed {len(done)} returns, {len(failed)} failed.",
    })

@app.post("/api/search")
async def api_search(request: Request):
    if not check_auth(request): return JSONResponse({"error": "unauth"})
    form  = await request.form()
    query = form.get("query", "").strip()
    if not query: return JSONResponse({"result": "❌ Send text to search"})

    is_bot = query.isdigit()
    is_web = query.endswith('S') and query[:-1].isdigit()

    if is_bot or is_web:
        order = await db.orders.find_one({"_id": int(query)}) if is_bot else await db.store_orders.find_one({"_id": query})
        if order:
            if "items" in order:
                items_str = "\n".join([f"  - {item}" for item in order.get("items", [])])
                return JSONResponse({"result": f"📄 Bot Order #{query}\n👤 By: {order.get('user', 'Unknown')} | ID: {order.get('user_id')}\n📅 Date: {order.get('date')}\n📦 Type: {order.get('type')}\n\n⬇️ Items ({len(order.get('items',[]))}):\n{items_str}"})
            else:
                # ✅ FIX: store orders use 'price', not 'price_egp'/'price_usd'
                price    = order.get("price", "N/A")
                currency = order.get("currency", "")
                return JSONResponse({"result": f"🛒 Web Store Order #{query}\n👤 By: {order.get('name', 'Unknown')} | Email: {order.get('email')}\n📅 Date: {order.get('date')}\n📦 Package: {order.get('category')}\n💰 Paid: {price} {currency}\n\n⬇️ Delivered Code:\n  - {order.get('code')}"})

        if is_bot:
            user = await db.users.find_one({"_id": int(query)})
            if user:
                return JSONResponse({"result": f"👤 {user.get('name')}\n🆔 ID: {user.get('_id')}\n🎖 Role: {user.get('role')}\n🔑 Tokens: {len(user.get('tokens', []))}"})

    records  = await db.codes_map.find({"$or": [{"_id": query}, {"code": query}]}).to_list(length=10)
    in_stock = await db.stock.count_documents({"$or": [{"_id": query}, {"code": query}]})
    res_str  = f"🔍 Search result for: {query}\n📦 Currently in stock: {in_stock} times\n"
    if records:
        res_str += f"\n🛒 Pulled {len(records)} times:\n"
        for i, r in enumerate(records, 1):
            res_str += f" {i}. By: {r.get('name', 'Unknown')} ({r.get('source', 'Bot')}) | Time: {r.get('time')} | Order: #{r.get('order_id')}\n"
    elif in_stock == 0:
        res_str += "\n❌ Not found in history."

    return JSONResponse({"result": res_str})
