import os
from fastapi import FastAPI, Depends, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import motor.motor_asyncio
from datetime import datetime

app = FastAPI(title="SalehZon Dashboard")

# تفعيل مجلد الملفات الثابتة (للصور واللوجو)
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["salehzon_db"]

ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "123456")
SECRET_TOKEN = "salehzon_secure_cookie_2026"

def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def do_login(request: Request, response: Response, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        redirect_resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        redirect_resp.set_cookie(key="admin_session", value=SECRET_TOKEN, httponly=True)
        return redirect_resp
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials!"})

@app.get("/logout")
async def logout():
    redirect_resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    redirect_resp.delete_cookie("admin_session")
    return redirect_resp

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    users_count = await db.users.count_documents({})
    stock_count = await db.stock.count_documents({})
    orders_count = await db.orders.count_documents({})
    cached_count = await db.cached_accounts.count_documents({})
    
    recent_orders = await db.orders.find().sort("date", -1).limit(10).to_list(10)
    all_users = await db.users.find().sort("_id", -1).limit(50).to_list(50)
    
    # جلب إحصائيات الفئات
    categories = ["60", "325", "660", "1800", "3850", "8100"]
    stock_details = {}
    for cat in categories:
        stock_details[cat] = await db.stock.count_documents({"category": cat})
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "users_count": users_count, "stock_count": stock_count,
        "orders_count": orders_count, "cached_count": cached_count,
        "recent_orders": recent_orders, "all_users": all_users,
        "stock_details": stock_details
    })

# --- API Endpoints for Dashboard Buttons ---
@app.post("/api/add_stock")
async def api_add_stock(request: Request, category: str = Form(...), codes: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    lines = [c.strip() for c in codes.splitlines() if c.strip()]
    docs = [{"code": c, "category": category, "added_at": datetime.now()} for c in lines]
    if docs:
        await db.stock.insert_many(docs, ordered=False)
    return RedirectResponse(url="/?msg=Stock+Added", status_code=status.HTTP_302_FOUND)

@app.post("/api/add_user")
async def api_add_user(request: Request, user_id: int = Form(...), name: str = Form(...), role: str = Form(...)):
    if not check_auth(request): return RedirectResponse("/login")
    if not await db.users.find_one({"_id": user_id}):
        await db.users.insert_one({"_id": user_id, "role": role, "name": name, "tokens": [], "history": [], "logs": [], "stats": {"api": 0, "stock": 0}})
    return RedirectResponse(url="/?msg=User+Added", status_code=status.HTTP_302_FOUND)
