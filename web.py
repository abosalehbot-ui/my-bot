import os
import secrets
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import motor.motor_asyncio

app = FastAPI(title="SalehZon Dashboard")
security = HTTPBasic()

# إعداد مجلد قوالب HTML
templates = Jinja2Templates(directory="templates")

# الاتصال بقاعدة البيانات (نفس رابط البوت)
MONGO_URI = os.environ.get("MONGO_URI")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["salehzon_db"]

# بيانات تسجيل الدخول للوحة (يتم سحبها من Railway أو استخدام الافتراضي)
ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "123456")

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اسم المستخدم أو كلمة المرور غير صحيحة",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, username: str = Depends(verify_credentials)):
    # جلب الإحصائيات من قاعدة البيانات
    users_count = await db.users.count_documents({})
    stock_count = await db.stock.count_documents({})
    orders_count = await db.orders.count_documents({})
    cached_count = await db.cached_accounts.count_documents({})
    
    # جلب أحدث 10 طلبات
    recent_orders = await db.orders.find().sort("date", -1).limit(10).to_list(10)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "users_count": users_count,
        "stock_count": stock_count,
        "orders_count": orders_count,
        "cached_count": cached_count,
        "recent_orders": recent_orders
    })
