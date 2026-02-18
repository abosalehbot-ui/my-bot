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

# ====== 📝 إعداد اللوجز ======
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = "8577787177:AAHAH06rraN86cZQykyhnxV3hxkIQOCyxk8"
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"
DRIVE_CREDENTIALS_FILE = "credentials.json"
DB_FILE_NAME = "bot_system_v9_fast.json" 
EMPLOYEE_DAILY_LIMIT = 20

# ====== ☁️ Google Drive Core ======
def get_drive_service():
    try:
        creds = service_account.Credentials.from_service_account_file(
            DRIVE_CREDENTIALS_FILE, scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=creds, cache_discovery=False)
    except: return None

def download_db():
    service = get_drive_service()
    default = {"users": {}, "stock": [], "settings": {"maintenance": False}, "stats": {"total_api": 0, "total_stock": 0}}
    if not service: return default
    try:
        res = service.files().list(q=f"name='{DB_FILE_NAME}' and trashed=false", fields="files(id)").execute()
        items = res.get('files', [])
        if not items: return default
        req = service.files().get_media(fileId=items[0]['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        data = json.load(fh)
        data["users"] = {int(k): v for k, v in data.get("users", {}).items()}
        return data
    except: return default

def upload_db(data):
    service = get_drive_service()
    if not service: return
    try:
        with open("temp.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        res = service.files().list(q=f"name='{DB_FILE_NAME}' and trashed=false", fields="files(id)").execute()
        items = res.get('files', [])
        media = MediaFileUpload("temp.json", mimetype='application/json')
        if items: service.files().update(fileId=items[0]['id'], media_body=media).execute()
        else: service.files().create(body={'name': DB_FILE_NAME}, media_body=media).execute()
    except: pass

DB = download_db()

def save():
    threading.Thread(target=upload_db, args=(DB,)).start()

# ====== 🌐 Flask ======
app_server = Flask(__name__)
@app_server.route('/')
def home(): return "OK", 200
def run_flask(): app_server.run(host="0.0.0.0", port=8080)

# ====== ⌨️ Keyboards ======
def main_kb(uid):
    user = DB["users"].get(uid, {})
    role = user.get("role", "user")
    btns = []
    if role in ["admin", "employee"]:
        btns.append([InlineKeyboardButton("📦 سحب مخزن (ببجي)", callback_data="p_s")])
    btns.append([InlineKeyboardButton("🚀 سحب حسابات (API)", callback_data="p_a")])
    btns.append([InlineKeyboardButton("➕ إضافة توكن", callback_data="a_t"), InlineKeyboardButton("🗑 حذف توكن", callback_data="c_t")])
    btns.append([InlineKeyboardButton("💰 رصيدي", callback_data="bal"), InlineKeyboardButton("🔢 العدد", callback_data="cnt")])
    btns.append([InlineKeyboardButton("📂 أرشيفي", callback_data="hist"), InlineKeyboardButton("❓ مساعدة", callback_data="help")])
    if role == "admin": btns.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="adm")])
    return InlineKeyboardMarkup(btns)

def adm_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 المستخدمين", callback_data="adm_u"), InlineKeyboardButton("📦 المخزن", callback_data="adm_s")],
        [InlineKeyboardButton("📝 السجلات", callback_data="adm_l"), InlineKeyboardButton("🛠 الصيانة", callback_data="adm_m")],
        [InlineKeyboardButton("🏠 خروج", callback_data="exit")]
    ])

# ====== 🚀 Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == ADMIN_ID and uid not in DB["users"]:
        DB["users"][uid] = {"role":"admin","tokens":[],"max":1,"history":[],"stats":{"api":0,"stock":0},"name":"Admin"}
        save()
    if uid not in DB["users"]:
        await update.message.reply_text("⛔ غير مسجل.")
        return
    await update.message.reply_text(f"👋 أهلاً {update.effective_user.first_name}", reply_markup=main_kb(uid))

async def btns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    await q.answer()

    # حماية الـ KeyError للأدمن
    if uid not in DB["users"] and uid == ADMIN_ID:
        DB["users"][uid] = {"role":"admin","tokens":[],"max":1,"history":[],"stats":{"api":0,"stock":0},"name":"Admin"}
        save()

    user = DB["users"].get(uid)
    if not user: return
    role = user.get("role", "user")

    if data == "exit":
        await q.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=main_kb(uid))
    elif data == "adm":
        if role != "admin": return
        await q.edit_message_text(f"🛠 لوحة الأدمن\n📦 المخزن: {len(DB['stock'])}", reply_markup=adm_kb())
    elif data == "p_s":
        if role not in ["admin", "employee"]: return
        if not DB["stock"]: await q.edit_message_text("⚠️ فارغ", reply_markup=main_kb(uid)); return
        code = DB["stock"].pop(0)
        user["stats"]["stock"] += 1
        user.setdefault("history", []).append(f"📦 {code}")
        save()
        await q.edit_message_text(f"✅ تم السحب:\n<code>{code}</code>", parse_mode=ParseMode.HTML, reply_markup=main_kb(uid))
    elif data == "p_a":
        if not user["tokens"]: await q.edit_message_text("⚠️ أضف توكن", reply_markup=main_kb(uid)); return
        await q.edit_message_text("⏳ جاري السحب..."); accs = []
        for t in list(user["tokens"]):
            try:
                r = requests.post(f"{API_BASE_URL}/api/redeem-bulk", json={"token":t,"product":PRODUCT_ID,"qty":user["max"]}, timeout=10).json()
                if r.get("success"):
                    for a in r["accounts"]:
                        accs.append(f"📧 <code>{a['email']}</code>\n🔑 <code>{a['password']}</code>\n---")
                        user["history"].append(f"{a['email']}:{a['password']}")
                    user["stats"]["api"] += len(r["accounts"]); break
                elif "Invalid" in r.get("message", ""): user["tokens"].remove(t)
            except: continue
        save()
        if accs: await q.edit_message_text("\n".join(accs), parse_mode=ParseMode.HTML, reply_markup=main_kb(uid))
        else: await q.edit_message_text("❌ فشل", reply_markup=main_kb(uid))
    elif data == "a_t":
        context.user_data["s"] = "tk"
        await q.edit_message_text("📝 أرسل التوكنات (كل توكن في سطر):")

async def txt_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = context.user_data.get("s")
    if not st or uid not in DB["users"]: return
    if st == "tk":
        for t in update.message.text.splitlines():
            t = t.strip()
            if t and t not in DB["users"][uid]["tokens"]: DB["users"][uid]["tokens"].append(t)
        save(); await update.message.reply_text("✅ تم الحفظ", reply_markup=main_kb(uid))
    context.user_data.clear()

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(btns))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_msg))
    # التشغيل مع تجاهل الرسائل القديمة لمنع التضارب
    app.run_polling(drop_pending_updates=True)
if __name__ == "__main__":
    # تشغيل سيرفر Flask في الخلفية
    threading.Thread(target=run_flask).start()
    
    print("🚀 Starting Bot...")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(btns))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_msg))
    
    # التعديل السحري هنا:
    # drop_pending_updates=True: يتجاهل الرسائل القديمة
    # close_loop=True: يغلق أي اتصالات قديمة عالقة
    app.run_polling(drop_pending_updates=True, stop_signals=None)
