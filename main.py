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
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# ====== 📝 إعداد اللوجز (سريع ونظيف) ======
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = "8577787177:AAHAH06rraN86cZQykyhnxV3hxkIQOCyxk8"
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"
DRIVE_CREDENTIALS_FILE = "credentials.json"
DB_FILE_NAME = "bot_system_v8_ultra.json" 
EMPLOYEE_DAILY_LIMIT = 20

# ====== ☁️ Google Drive Core ======
def get_drive_service():
    try:
        creds = service_account.Credentials.from_service_account_file(
            DRIVE_CREDENTIALS_FILE, scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive Auth Error: {e}")
        return None

def download_db():
    service = get_drive_service()
    default_db = {"users": {}, "stock": [], "settings": {"maintenance": False}, "stats": {"total_api": 0, "total_stock": 0}}
    if not service: return default_db
    try:
        results = service.files().list(q=f"name='{DB_FILE_NAME}' and trashed=false", fields="files(id)").execute()
        items = results.get('files', [])
        if not items: return default_db
        request = service.files().get_media(fileId=items[0]['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        data = json.load(fh)
        data["users"] = {int(k): v for k, v in data.get("users", {}).items()}
        return data
    except Exception as e:
        logger.error(f"DB Download Fail: {e}")
        return default_db

def upload_db(data):
    service = get_drive_service()
    if not service: return
    try:
        with open("temp_db.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        results = service.files().list(q=f"name='{DB_FILE_NAME}' and trashed=false", fields="files(id)").execute()
        items = results.get('files', [])
        media = MediaFileUpload("temp_db.json", mimetype='application/json')
        if items:
            service.files().update(fileId=items[0]['id'], media_body=media).execute()
        else:
            service.files().create(body={'name': DB_FILE_NAME}, media_body=media).execute()
    except Exception as e:
        logger.error(f"DB Upload Fail: {e}")

DB = download_db()

def save_changes():
    threading.Thread(target=upload_db, args=(DB,)).start()

def log_act(uid, msg):
    if uid not in DB["users"]: return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logs = DB["users"][uid].setdefault("logs", [])
    logs.append(f"[{ts}] {msg}")
    if len(logs) > 150: DB["users"][uid]["logs"] = logs[-150:]
    save_changes()

# ====== 🌐 Flask ======
app_server = Flask(__name__)
@app_server.route('/')
def home(): return "Online", 200
def run_flask(): app_server.run(host="0.0.0.0", port=8080)

# ====== ⌨️ Keyboards ======
def main_kb(role):
    btns = []
    if role in ["employee", "admin"]:
        btns.append([InlineKeyboardButton("📦 سحب مخزن (ببجي)", callback_data="pull_stock")])
    btns.append([InlineKeyboardButton("🚀 سحب حسابات (API)", callback_data="pull_api")])
    btns.append([InlineKeyboardButton("➕ إضافة توكن", callback_data="add_tokens"), InlineKeyboardButton("🗑 حذف توكن", callback_data="clear_tokens")])
    btns.append([InlineKeyboardButton("💰 رصيدي", callback_data="check_balance"), InlineKeyboardButton("🔢 العدد", callback_data="set_count")])
    btns.append([InlineKeyboardButton("📂 أرشيفي", callback_data="my_history"), InlineKeyboardButton("❓ مساعدة", callback_data="help")])
    if role == "admin": btns.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="adm_main")])
    return InlineKeyboardMarkup(btns)

def adm_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="adm_users"), InlineKeyboardButton("📦 إدارة المخزن", callback_data="adm_stock")],
        [InlineKeyboardButton("📝 تحميل السجلات", callback_data="adm_logs"), InlineKeyboardButton("🛠 الصيانة", callback_data="adm_maint")],
        [InlineKeyboardButton("🏠 خروج (وضع المستخدم)", callback_data="back_u")]
    ])

def adm_back(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="adm_main")]])
def usr_back(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_u")]])

# ====== 🚀 Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    if uid == ADMIN_ID and uid not in DB["users"]:
        DB["users"][uid] = {"role":"admin","tokens":[],"max":1,"history":[],"stats":{"api":0,"stock":0},"name":"Admin"}
        save_changes()
    if uid not in DB["users"]:
        await update.message.reply_text("⛔ غير مسجل.")
        return
    role = DB["users"][uid].get("role", "user")
    await update.message.reply_text(f"👋 أهلاً {name} | الرتبة: {role}", reply_markup=main_kb(role))

async def handle_btns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    await q.answer()

    if uid not in DB["users"]:
        if uid == ADMIN_ID: # Auto-fix for Admin
            DB["users"][uid] = {"role":"admin","tokens":[],"max":1,"history":[],"stats":{"api":0,"stock":0},"name":"Admin"}
            save_changes()
        else: return

    user = DB["users"][uid]
    role = user.get("role", "user")

    if DB["settings"]["maintenance"] and role != "admin":
        await q.edit_message_text("⚠️ صيانة...")
        return

    if data == "back_u":
        context.user_data.clear()
        await q.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=main_kb(role))
    
    elif data == "adm_main":
        if role != "admin": return
        m = "🔴" if DB["settings"]["maintenance"] else "🟢"
        await q.edit_message_text(f"🛠 لوحة الأدمن\n📦 المخزن: {len(DB['stock'])}\n🛠 الصيانة: {m}", reply_markup=adm_kb())

    elif data == "help":
        await q.edit_message_text("❓ دليل الاستخدام:\n- أضف توكن ثم اسحب API.\n- الموظف يسحب من المخزن بحد يومي.", reply_markup=usr_back())

    elif data == "pull_stock":
        if role not in ["admin", "employee"]: return
        count = user.get("max", 1)
        if len(DB["stock"]) < count:
            await q.edit_message_text(f"⚠️ المخزن غير كافي ({len(DB['stock'])})", reply_markup=usr_back())
            return
        pulled = [DB["stock"].pop(0) for _ in range(count)]
        user["stats"]["stock"] += len(pulled)
        user.setdefault("history", []).extend([f"📦 {c}" for c in pulled])
        log_act(uid, f"سحب {len(pulled)} من المخزن")
        save_changes()
        res = "\n".join([f"🎮 <code>{c}</code>" for c in pulled])
        await q.edit_message_text(f"✅ تم السحب:\n\n{res}", parse_mode=ParseMode.HTML, reply_markup=usr_back())

    elif data == "pull_api":
        if not user["tokens"]:
            await q.edit_message_text("⚠️ أضف توكنات أولاً.", reply_markup=usr_back())
            return
        await q.edit_message_text("⏳ جاري السحب...")
        success_accs = []
        for t in list(user["tokens"]):
            try:
                r = requests.post(f"{API_BASE_URL}/api/redeem-bulk", json={"token":t,"product":PRODUCT_ID,"qty":user["max"]}, timeout=15).json()
                if r.get("success"):
                    for acc in r["accounts"]:
                        e, p = acc['email'], acc['password']
                        success_accs.append(f"📧 <code>{e}</code>\n🔑 <code>{p}</code>\n---")
                        user.setdefault("history", []).append(f"{e}:{p}")
                    user["stats"]["api"] += len(r["accounts"])
                    log_act(uid, f"سحب API ({len(r['accounts'])})")
                    break
                elif "Invalid" in r.get("message", ""): user["tokens"].remove(t)
            except: continue
        save_changes()
        if success_accs:
            await q.edit_message_text("\n".join(success_accs), parse_mode=ParseMode.HTML, reply_markup=usr_back())
        else: await q.edit_message_text("❌ فشل السحب.", reply_markup=usr_back())

    elif data == "add_tokens":
        context.user_data["st"] = "tk"
        await q.edit_message_text("📝 أرسل التوكنات (كل توكن في سطر):", reply_markup=usr_back())
    
    elif data == "adm_logs":
        lines = []
        for u_id, u_dat in DB["users"].items():
            if u_dat.get("logs"):
                lines.append(f"👤 {u_dat['name']} ({u_id}):")
                lines.extend(u_dat["logs"][-10:])
        if not lines: await q.answer("لا يوجد سجلات")
        else:
            bio = io.BytesIO("\n".join(lines).encode())
            bio.name = "logs.txt"
            await context.bot.send_document(uid, bio, reply_markup=adm_back())

    elif data == "adm_stock":
        await q.edit_message_text(f"📦 إدارة المخزن\nالعدد: {len(DB['stock'])}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ إضافة يدوي", callback_data="add_s_t"), InlineKeyboardButton("📂 ملف", callback_data="add_s_f")], [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")]]))

    elif data == "add_s_t": context.user_data["st"] = "s_t"; await q.edit_message_text("أرسل الأكواد:", reply_markup=adm_back())
    elif data == "add_s_f": context.user_data["st"] = "s_f"; await q.edit_message_text("أرسل ملف .txt:", reply_markup=adm_back())
    elif data == "adm_maint": DB["settings"]["maintenance"] = not DB["settings"]["maintenance"]; save_changes(); await q.answer("تم التغيير"); await handle_btns(update, context)

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = context.user_data.get("st")
    txt = update.message.text
    if not st or uid not in DB["users"]: return

    if st == "tk":
        added = 0
        for t in txt.splitlines():
            t = t.strip()
            if t and t not in DB["users"][uid]["tokens"]: DB["users"][uid]["tokens"].append(t); added += 1
        save_changes(); await update.message.reply_text(f"✅ أضيف {added}", reply_markup=usr_back())
    
    elif st == "s_t" and uid == ADMIN_ID:
        added = 0
        for c in txt.splitlines():
            c = c.strip()
            if c and c not in DB["stock"]: DB["stock"].append(c); added += 1
        save_changes(); await update.message.reply_text(f"📦 أضيف {added}", reply_markup=adm_back())
    
    context.user_data.clear()

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == ADMIN_ID and context.user_data.get("st") == "s_f":
        file = await update.message.document.get_file()
        buf = await file.download_as_bytearray()
        added = 0
        for c in buf.decode().splitlines():
            c = c.strip()
            if c and c not in DB["stock"]: DB["stock"].append(c); added += 1
        save_changes(); await update.message.reply_text(f"📂 أضيف {added}", reply_markup=adm_back())
        context.user_data.clear()

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_btns))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.run_polling(drop_pending_updates=True)
