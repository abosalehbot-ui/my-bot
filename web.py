import os
from fastapi import FastAPI, Depends, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import motor.motor_asyncio

app = FastAPI(title="SalehZon Dashboard")

# إعداد مجلد القوالب
templates = Jinja2Templates(directory="templates")

# الاتصال بقاعدة البيانات
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["salehzon_db"]

# إعدادات الحساب السري
ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "123456")
SECRET_TOKEN = "salehzon_secure_cookie_2026" # كلمة سر الكوكيز

# دالة التحقق من تسجيل الدخول
def check_auth(request: Request):
    return request.cookies.get("admin_session") == SECRET_TOKEN

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def do_login(request: Request, response: Response, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        # إذا كانت البيانات صحيحة، نوجه للمسار الرئيسي ونحفظ جلسة الدخول
        redirect_resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        redirect_resp.set_cookie(key="admin_session", value=SECRET_TOKEN, httponly=True)
        return redirect_resp
    else:
        # إذا كانت خاطئة نرسل رسالة خطأ
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})

@app.get("/logout")
async def logout():
    # تسجيل الخروج ومسح الجلسة
    redirect_resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    redirect_resp.delete_cookie("admin_session")
    return redirect_resp

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    # التحقق من أن المستخدم قام بتسجيل الدخول أولاً
    if not check_auth(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # جلب الإحصائيات
    users_count = await db.users.count_documents({})
    stock_count = await db.stock.count_documents({})
    orders_count = await db.orders.count_documents({})
    cached_count = await db.cached_accounts.count_documents({})
    recent_orders = await db.orders.find().sort("date", -1).limit(10).to_list(10)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "users_count": users_count,
        "stock_count": stock_count,
        "orders_count": orders_count,
        "cached_count": cached_count,
        "recent_orders": recent_orders
    })
