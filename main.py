import requests
import json
import os
import threading
import logging
from datetime import datetime
import io
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
# مكتبات جوجل درايف
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# ====== 📝 إعداد اللوجز (بسيط ونظيف) ======
logging.basicConfig(
    format='%(asctime)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = "8577787177:AAH-p_2EVtcgff_ML8Rc0jGrJ2OiV-lExTY"
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"

# إعدادات جوجل درايف
DRIVE_CREDENTIALS_FILE = "credentials.json"
DB_FILE_NAME = "bot_system_v10_ultimate.json" 

# إعدادات الموظفين
EMPLOYEE_DAILY_LIMIT = 20

# ====== ☁️ دوال Google Drive ======
def get_drive_service():
    try:
        if not os.path.exists(DRIVE_CREDENTIALS_FILE):
            logger.error("❌ ملف credentials.json غير موجود!")
            return None
        creds = service_account.Credentials.from_service_account_file(
            DRIVE_CREDENTIALS_FILE, scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"❌ Drive Auth Error: {e}")
        return None

def download_db_from_drive():
    service = get_drive_service()
    default_db = {
        "users": {}, 
        "stock": [], 
        "settings": {"maintenance": False},
        "stats": {"total_api": 0, "total_stock": 0},
        "codes_map": {}  # لقاعدة بيانات البحث العكسي
    }
    
    if not service: return default_db

    try:
        results = service.files().list(
            q=f"name='{DB_FILE_NAME}' and trashed=false",
            fields="files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            return default_db

        file_id = items[0]['id']
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        fh.seek(0)
        data = json.load(fh)
        
        if "users" in data:
            data["users"] = {int(k): v for k, v in data["users"].items()}
        
        for key in default_db:
            if key not in data: data[key] = default_db[key]
            
        return data
    except Exception as e:
        logger.error(f"❌ Download Error: {e}")
        return default_db

def upload_db_to_drive(data):
    service = get_drive_service()
    if not service: return
    try:
        with open("temp_db.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        results = service.files().list(q=f"name='{DB_FILE_NAME}' and trashed=false", fields="files(id)").execute()
        items = results.get('files', [])

        media = MediaFileUpload("temp_db.json", mimetype='application/json')

        if items:
            service.files().update(fileId=items[0]['id'], media_body=media).execute()
        else:
            file_metadata = {'name': DB_FILE_NAME}
            service.files().create(body=file_metadata, media_body=media).execute()
    except Exception as e:
        logger.error(f"❌ Upload Error: {e}")

# ====== 💾 إدارة البيانات ======
DB = download_db_from_drive()

def save_db_changes():
    threading.Thread(target=upload_db_to_drive, args=(DB,)).start()

def log_activity(user_id, action):
    if user_id not in DB["users"]: return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {action}"
    
    if "logs" not in DB["users"][user_id]: DB["users"][user_id]["logs"] = []
    DB["users"][user_id]["logs"].append(log_entry)
    
    if len(DB["users"][user_id]["logs"]) > 200:
        DB["users"][user_id]["logs"] = DB["users"][user_id]["logs"][-200:]
    
    save_db_changes()

# ====== 🌐 سيرفر Flask ======
app_server = Flask(__name__)
@app_server.route('/')
def home(): return "✅ Bot Online!", 200
def run_flask(): app_server.run(host="0.0.0.0", port=8080)

# ====== ⌨️ الكيبوردات ======

def get_main_keyboard(role):
    buttons = []
    if role in ["employee", "admin"]:
        buttons.append([InlineKeyboardButton("🎮 سحب كود ببجي", callback_data="pull_stock")])
    
    buttons.append([InlineKeyboardButton("🚀 سحب حسابات (API)", callback_data="pull_api")])
    buttons.append([InlineKeyboardButton("➕ إضافة توكن", callback_data="add_tokens"),
                    InlineKeyboardButton("🗑 حذف توكن", callback_data="clear_tokens")])
    buttons.append([InlineKeyboardButton("💰 رصيدي", callback_data="check_balance"),
                    InlineKeyboardButton("🔢 العدد", callback_data="set_count")])
    buttons.append([InlineKeyboardButton("📂 أرشيفي", callback_data="my_history"),
                    InlineKeyboardButton("❓ مساعدة", callback_data="help_menu")])

    if role == "admin":
        buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons)

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📦 إدارة المخزن", callback_data="admin_stock_menu")],
        [InlineKeyboardButton("🔍 البحث العكسي", callback_data="admin_reverse_search")],
        [InlineKeyboardButton("📝 السجلات", callback_data="admin_get_logs")],
        [InlineKeyboardButton("🛠 الصيانة", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("🏠 خروج", callback_data="back_home")]
    ])

def stock_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 رفع ملف (.txt)", callback_data="admin_upload_stock_file")],
        [InlineKeyboardButton("✍️ إضافة يدوي", callback_data="admin_add_stock_text")],
        [InlineKeyboardButton("🗑 تصفير", callback_data="admin_clear_stock")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]])
def admin_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]])

# ====== 🚀 Handlers ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    if user_id == ADMIN_ID and user_id not in DB["users"]:
        DB["users"][user_id] = {"role":"admin", "tokens":[], "max":1, "history":[], "logs":[], "stats":{"api":0,"stock":0}, "name":"Admin"}
        save_db_changes()

    if user_id not in DB["users"]:
        await update.message.reply_text("⛔ غير مسجل.")
        return

    DB["users"][user_id]["name"] = name
    role = DB["users"][user_id].get("role", "user")
    await update.message.reply_text(f"👋 أهلاً {name} | الرتبة: {role}", reply_markup=get_main_keyboard(role))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; user_id = query.from_user.id; data = query.data; await query.answer()
    
    if user_id not in DB["users"] and user_id == ADMIN_ID:
        DB["users"][user_id] = {"role":"admin", "tokens":[], "max":1, "history":[], "logs":[], "stats":{"api":0,"stock":0}, "name":"Admin"}
        save_db_changes()
    
    user_data = DB["users"].get(user_id)
    if not user_data: return
    role = user_data.get("role", "user")

    if data == "back_home":
        context.user_data.clear()
        await query.edit_message_text("🏠 الرئيسية:", reply_markup=get_main_keyboard(role))
    elif data == "admin_panel":
        if role != "admin": return
        status = "🔴 مفعل" if DB['settings']['maintenance'] else "🟢 معطل"
        await query.edit_message_text(f"🛠 لوحة الأدمن\n📦 المخزن: {len(DB['stock'])}\n🛠 الصيانة: {status}", reply_markup=admin_keyboard())

    # --- البحث العكسي ---
    elif data == "admin_reverse_search":
        if role != "admin": return
        context.user_data["state"] = "waiting_reverse_code"
        await query.edit_message_text("🔍 أرسل الكود لمعرفة من قام بسحبه:", reply_markup=admin_back_btn())

    # --- سحب مخزن ببجي ---
    elif data == "pull_stock":
        if role not in ["admin", "employee"]: return
        if not DB["stock"]:
            await query.edit_message_text("⚠️ المخزن فارغ!", reply_markup=back_btn())
            return
        
        count = user_data.get("max", 1)
        if len(DB["stock"]) < count:
            await query.edit_message_text(f"⚠️ المخزن لا يكفي ({len(DB['stock'])})", reply_markup=back_btn())
            return

        pulled = [DB["stock"].pop(0) for _ in range(count)]
        for code in pulled:
            DB["codes_map"][code] = {"name": user_data["name"], "id": user_id, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
            user_data["history"].append(f"📦 {code}")
        
        user_data["stats"]["stock"] += len(pulled)
        log_activity(user_id, f"سحب {len(pulled)} كود ببجي")
        save_db_changes()
        
        msg = "\n".join([f"🎮 <code>{c}</code>" for c in pulled])
        await query.edit_message_text(f"✅ تم السحب:\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=back_btn())

    # --- سحب API ---
    elif data == "pull_api":
        if not user_data["tokens"]:
            await query.edit_message_text("⚠️ أضف توكن أولاً.", reply_markup=back_btn())
            return
        await query.edit_message_text("⏳ جاري السحب..."); accs = []
        for t in list(user_data["tokens"]):
            try:
                r = requests.post(f"{API_BASE_URL}/api/redeem-bulk", json={"token":t, "product":PRODUCT_ID, "qty":user_data["max"]}, timeout=10).json()
                if r.get("success"):
                    for a in r["accounts"]:
                        accs.append(f"📧 <code>{a['email']}</code>\n🔑 <code>{a['password']}</code>\n---")
                        user_data["history"].append(f"{a['email']}:{a['password']}")
                    user_data["stats"]["api"] += len(r["accounts"]); break
                elif "Invalid" in r.get("message", ""): user_data["tokens"].remove(t)
            except: continue
        save_db_changes()
        if accs: await query.edit_message_text("\n".join(accs), parse_mode=ParseMode.HTML, reply_markup=back_btn())
        else: await query.edit_message_text("❌ فشل السحب.", reply_markup=back_btn())

    elif data == "add_tokens":
        context.user_data["state"] = "waiting_tokens"
        await query.edit_message_text("📝 أرسل التوكنات (كل توكن في سطر):", reply_markup=back_btn())

    elif data == "admin_stock_menu":
        await query.edit_message_text(f"📦 إدارة المخزن\nالعدد الحالي: {len(DB['stock'])}", reply_markup=stock_manage_keyboard())

    elif data == "admin_add_stock_text":
        context.user_data["state"] = "adding_stock_manual"
        await query.edit_message_text("✍️ أرسل الأكواد للإضافة:", reply_markup=admin_back_btn())

# ====== 📩 معالج الرسائل ======

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; state = context.user_data.get("state"); txt = update.message.text
    if uid not in DB["users"]: return

    if state == "waiting_reverse_code" and uid == ADMIN_ID:
        res = DB["codes_map"].get(txt.strip())
        if res: await update.message.reply_text(f"✅ كود: {txt}\n👤 سحب بواسطة: {res['name']}\n🆔 ID: {res['id']}\n📅 التاريخ: {res['time']}", reply_markup=admin_back_btn())
        else: await update.message.reply_text("❌ الكود غير موجود في سجل السحب.", reply_markup=admin_back_btn())
    
    elif state == "adding_stock_manual" and uid == ADMIN_ID:
        added = 0
        for c in txt.splitlines():
            c = c.strip()
            if c and c not in DB["stock"]: DB["stock"].append(c); added += 1
        save_db_changes(); await update.message.reply_text(f"📦 تمت إضافة {added} كود.", reply_markup=admin_back_btn())
    
    elif state == "waiting_tokens":
        added = 0
        for t in txt.splitlines():
            t = t.strip()
            if t and t not in DB["users"][uid]["tokens"]: DB["users"][uid]["tokens"].append(t); added += 1
        save_db_changes(); await update.message.reply_text(f"✅ أضيف {added} توكن.", reply_markup=back_btn())

    context.user_data.clear()

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling(drop_pending_updates=True)
