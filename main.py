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

# ====== 📝 إعداد اللوجز (بسيط ونظيف كما طلبت) ======
logging.basicConfig(
    format='%(asctime)s - %(message)s', # تنسيق بسيط: الوقت - الرسالة
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)

# تقليل رسائل المكتبات المزعجة
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = "8577787177:AAHAH06rraN86cZQykyhnxV3hxkIQOCyxk8"
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"

# إعدادات جوجل درايف
DRIVE_CREDENTIALS_FILE = "credentials.json"
DB_FILE_NAME = "bot_system_v6_final.json" 

# إعدادات الموظفين
EMPLOYEE_DAILY_LIMIT = 20

# ====== ☁️ دوال Google Drive ======
def get_drive_service():
    try:
        creds = service_account.Credentials.from_service_account_file(
            DRIVE_CREDENTIALS_FILE, scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"Drive Auth Error: {e}")
        return None

def download_db_from_drive():
    service = get_drive_service()
    default_db = {
        "users": {}, 
        "stock": [], 
        "settings": {"maintenance": False},
        "stats": {"total_api": 0, "total_stock": 0}
    }
    
    if not service: return default_db

    try:
        results = service.files().list(
            q=f"name='{DB_FILE_NAME}' and trashed=false",
            fields="files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            logger.info("ℹ️ Creating new DB on Drive.")
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
        logger.error(f"Download Error: {e}")
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
        logger.error(f"Upload Error: {e}")

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
def home(): return "✅ Bot is Online!", 200
def run_flask(): app_server.run(host="0.0.0.0", port=8080)

# ====== ⌨️ الكيبوردات ======

# 1. كيبورد المستخدم/الموظف (واجهة السحب)
def get_main_keyboard(role):
    buttons = []
    if role in ["employee", "admin"]:
        buttons.append([InlineKeyboardButton("📦 سحب من المخزن (ببجي)", callback_data="pull_stock")])
    
    buttons.append([InlineKeyboardButton("🚀 سحب حسابات (API)", callback_data="pull_api")])
    
    buttons.append([
        InlineKeyboardButton("➕ إضافة توكن", callback_data="add_tokens"),
        InlineKeyboardButton("🗑 حذف توكن", callback_data="clear_tokens")
    ])
    
    buttons.append([
        InlineKeyboardButton("💰 رصيدي", callback_data="check_balance"),
        InlineKeyboardButton("🔢 العدد", callback_data="set_count")
    ])
    
    buttons.append([
        InlineKeyboardButton("📂 أرشيفي", callback_data="my_history"),
        InlineKeyboardButton("❓ مساعدة", callback_data="help_menu")
    ])

    # لو أدمن، نضيف زر للدخول للوحة التحكم
    if role == "admin":
        buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons)

# 2. كيبورد الأدمن الرئيسية
def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📦 إدارة المخزن (ببجي)", callback_data="admin_stock_menu")],
        [InlineKeyboardButton("📝 تقارير وسجلات", callback_data="admin_logs_menu")],
        [InlineKeyboardButton("🛠 وضع الصيانة", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("📢 إذاعة عامة", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🏠 وضع المستخدم (خروج)", callback_data="back_home")] # يرجع لواجهة المستخدم
    ])

# 3. كيبورد إدارة المخزن
def stock_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 رفع ملف أكواد (.txt)", callback_data="admin_upload_stock_file")],
        [InlineKeyboardButton("✍️ إضافة كود يدوياً", callback_data="admin_add_stock_text")],
        [InlineKeyboardButton("🗑 تصفير المخزن", callback_data="admin_clear_stock")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")] # يرجع للوحة الأدمن
    ])

# 4. أزرار الرجوع
def back_btn(): # رجوع للمستخدم
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]])

def admin_back_btn(): # رجوع للأدمن
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]])

# ====== 🚀 البداية ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    if user_id == ADMIN_ID and user_id not in DB["users"]:
        DB["users"][user_id] = {
            "role": "admin", "tokens": [], "max": 1, "history": [], "logs": [], 
            "stats": {"api": 0, "stock": 0}, "name": "Admin"
        }
        save_db_changes()

    if user_id not in DB["users"]:
        await update.message.reply_text("⛔ **البوت خاص.** تواصل مع الإدارة.", parse_mode=ParseMode.MARKDOWN)
        return

    DB["users"][user_id]["name"] = name
    if "stats" not in DB["users"][user_id]: DB["users"][user_id]["stats"] = {"api": 0, "stock": 0}
    save_db_changes()
    
    role = DB["users"][user_id].get("role", "user")
    
    await update.message.reply_text(
        f"👋 **أهلاً بك يا {name}**\n\n🔹 **الرتبة:** {role}\n🔹 **الحالة:** {'✅ يعمل' if not DB['settings']['maintenance'] else '⚠️ صيانة'}",
        reply_markup=get_main_keyboard(role),
        parse_mode=ParseMode.MARKDOWN
    )

# ====== 👑 لوحة الأدمن ======
async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    # يمكن استدعاؤها من رسالة أو زر
    target_msg = update.message if update.message else update.callback_query.message
    
    status = "🔴 مفعل" if DB['settings']['maintenance'] else "🟢 معطل"
    stock_count = len(DB["stock"])
    
    txt = (
        f"🛠 **لوحة التحكم المركزية**\n\n"
        f"📦 **المخزن:** {stock_count} كود\n"
        f"👥 **المستخدمين:** {len(DB['users'])}\n"
        f"🛠 **وضع الصيانة:** {status}"
    )
    
    # لو الاستدعاء من زرار نعدل الرسالة، لو كوماند نبعت جديد
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
    else:
        await target_msg.reply_text(txt, reply_markup=admin_keyboard(), parse_mode=ParseMode.MARKDOWN)

# ====== 🕹 المعالج الرئيسي ======
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if user_id not in DB["users"] and user_id != ADMIN_ID: return
    user_data = DB["users"][user_id]
    role = user_data.get("role", "user")

    if DB["settings"].get("maintenance") and role != "admin":
        await query.edit_message_text("⚠️ **الصيانة جارية...**", reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        return

    # --- التنقلات ---
    if data == "back_home":
        context.user_data.clear()
        await query.edit_message_text("🏠 **القائمة الرئيسية:**", reply_markup=get_main_keyboard(role), parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "admin_panel":
        await admin_panel_handler(update, context)
        return

    # --- المساعدة ---
    if data == "help_menu":
        msg = "❓ **المساعدة:**\n\n"
        if role == "user":
            msg += "1️⃣ إضافة توكن > سحب حسابات API.\n2️⃣ تابع أرشيفك باستمرار."
        elif role == "employee":
            msg += "1️⃣ سحب مخزن (ببجي) متاح لك بحد يومي.\n2️⃣ سحب API متاح بلا حدود."
        elif role == "admin":
            msg += "👑 استخدم لوحة الأدمن لإدارة كل شيء."
        await query.edit_message_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- سحب مخزن (ببجي) ---
    if data == "pull_stock":
        if role == "user": return
        
        count = user_data.get("max", 1)
        stock_len = len(DB["stock"])

        if stock_len < count:
            await query.edit_message_text(f"⚠️ **الكمية غير متوفرة!**\nالمتاح: {stock_len}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return

        if role == "employee":
            today = datetime.now().strftime("%Y-%m-%d")
            quota = user_data.get("quota", {"date": today, "count": 0})
            if quota["date"] != today: quota = {"date": today, "count": 0}
            
            if quota["count"] + count > EMPLOYEE_DAILY_LIMIT:
                rem = EMPLOYEE_DAILY_LIMIT - quota["count"]
                await query.edit_message_text(f"⛔ **الحد اليومي!**\nمتبقي: {rem}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
                return
            
            quota["count"] += count
            DB["users"][user_id]["quota"] = quota

        pulled = []
        for _ in range(count):
            pulled.append(DB["stock"].pop(0))
        
        DB["stats"]["total_stock"] += len(pulled)
        DB["users"][user_id]["stats"]["stock"] += len(pulled)
        log_activity(user_id, f"Stock Pull ({len(pulled)})")
        
        # حفظ الأرشيف
        if "history" not in DB["users"][user_id]: DB["users"][user_id]["history"] = []
        for c in pulled:
            DB["users"][user_id]["history"].append(f"📦 {c}")
        
        save_db_changes()

        msg_text = ""
        for code in pulled:
            msg_text += f"🎮 <code>{code}</code>\n"
            
        await query.edit_message_text(
            f"✅ **تم السحب:**\n\n{msg_text}\n📦 المتبقي: {len(DB['stock'])}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_btn() # يرجع للمستخدم
        )
        return

    # --- سحب API ---
    if data == "pull_api":
        tokens = user_data.get("tokens", [])
        count = user_data.get("max", 1)

        if not tokens:
            await query.edit_message_text("⚠️ **لا يوجد توكنات!**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return
        
        await query.edit_message_text("⏳ **جاري الاتصال...**", parse_mode=ParseMode.MARKDOWN)
        
        accounts = []
        tokens_to_remove = []
        
        for token in tokens:
            try:
                payload = {"token": token, "product": PRODUCT_ID, "qty": count}
                req = requests.post(f"{API_BASE_URL}/api/redeem-bulk", json=payload, timeout=20)
                res = req.json()
                
                if res.get("success"):
                    for acc in res.get("accounts", []):
                        email = acc.get('email')
                        password = acc.get('password')
                        
                        full_acc_str = f"{email}:{password}"
                        if "history" not in DB["users"][user_id]: DB["users"][user_id]["history"] = []
                        DB["users"][user_id]["history"].append(full_acc_str)
                        
                        fmt_acc = (
                            f"📧 <code>{email}</code>\n"
                            f"🔑 <code>{password}</code>\n"
                            f"------------------"
                        )
                        accounts.append(fmt_acc)

                    log_activity(user_id, f"API Pull ({len(accounts)})")
                    DB["stats"]["total_api"] += len(accounts)
                    DB["users"][user_id]["stats"]["api"] += len(accounts)
                    break
                else:
                    if "Invalid token" in res.get("message", ""):
                        tokens_to_remove.append(token)
            except Exception as e:
                logger.error(f"API: {e}")
                continue
        
        if tokens_to_remove:
            for t in tokens_to_remove:
                if t in DB["users"][user_id]["tokens"]: DB["users"][user_id]["tokens"].remove(t)
        
        save_db_changes()
        
        if accounts:
            msg_body = "\n".join(accounts)
            if len(msg_body) > 3500: msg_body = msg_body[:3500] + "\n..."
            await query.edit_message_text(f"✅ **تم:**\n\n{msg_body}", parse_mode=ParseMode.HTML, reply_markup=back_btn())
        else:
            await query.edit_message_text("❌ **فشل السحب.**", reply_markup=back_btn())
        return

    # --- أدوات المستخدم ---
    if data == "add_tokens":
        context.user_data["state"] = "waiting_tokens"
        await query.edit_message_text("📝 **أرسل التوكنات:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "clear_tokens":
        DB["users"][user_id]["tokens"] = []
        save_db_changes()
        await query.edit_message_text("🗑 **تم الحذف.**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "set_count":
        context.user_data["state"] = "waiting_count"
        await query.edit_message_text("🔢 **أرسل العدد:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "check_balance":
        t_count = len(user_data.get("tokens", []))
        stats = user_data.get("stats", {})
        await query.edit_message_text(
            f"💰 **المحفظة:**\n🔑 توكنات: {t_count}\n📊 سحب API: {stats.get('api', 0)}\n🎮 سحب مخزن: {stats.get('stock', 0)}",
            reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if data == "my_history":
        hist = user_data.get("history", [])
        if not hist:
            await query.edit_message_text("📂 فارغ.", reply_markup=back_btn())
        else:
            txt = "\n".join(hist[-5:])
            await query.edit_message_text(f"📂 **آخر 5:**\n\n{txt}", reply_markup=back_btn())
        return

    # --- أدوات الأدمن (اللوحة) ---
    if role == "admin":
        if data == "admin_stock_menu":
            await query.edit_message_text(f"📦 **إدارة المخزن**\nالعدد: {len(DB['stock'])}", reply_markup=stock_manage_keyboard())
            return
        
        if data == "admin_add_stock_text":
            context.user_data["state"] = "admin_adding_stock"
            await query.edit_message_text("✍️ **أرسل الأكواد:**", reply_markup=admin_back_btn())
            return
        
        if data == "admin_upload_stock_file":
            context.user_data["state"] = "admin_uploading_file"
            await query.edit_message_text("📂 **أرسل ملف .txt:**", reply_markup=admin_back_btn())
            return
        
        if data == "admin_clear_stock":
            DB["stock"] = []
            save_db_changes()
            await query.answer("🗑 تم التصفير!", show_alert=True)
            await query.edit_message_text("🗑 المخزن فارغ.", reply_markup=admin_back_btn())
            return

        if data == "admin_users_menu":
            msg = f"👥 **المستخدمين:** {len(DB['users'])}\n\n"
            for uid, u in DB["users"].items():
                msg += f"👤 {u['name']} | {u.get('role')} | ID: `{uid}`\n"
            # زر إضافة مستخدم وزر رجوع للأدمن
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة مستخدم/موظف", callback_data="admin_add_user_prompt")],
                [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
            ])
            await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            return

        if data == "admin_add_user_prompt":
            context.user_data["state"] = "admin_adding_user"
            await query.edit_message_text("✍️ **أرسل ID المستخدم:**", reply_markup=admin_back_btn())
            return
        
        if data == "toggle_maintenance":
            DB["settings"]["maintenance"] = not DB["settings"]["maintenance"]
            save_db_changes()
            await admin_panel_handler(update, context) # تحديث اللوحة
            return

# ====== 📩 معالجة الرسائل والملفات ======
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data.get("state")
    
    if not state: return

    # إضافة توكنات (مستخدم/موظف)
    if state == "waiting_tokens":
        lines = text.splitlines()
        added = 0
        if "tokens" not in DB["users"][user_id]: DB["users"][user_id]["tokens"] = []
        for t in lines:
            t = t.strip()
            if t and t not in DB["users"][user_id]["tokens"]:
                DB["users"][user_id]["tokens"].append(t)
                added += 1
        save_db_changes()
        context.user_data.clear()
        await update.message.reply_text(f"✅ تم إضافة {added} توكن.", reply_markup=back_btn())
        return

    # تعيين العدد
    if state == "waiting_count":
        if text.isdigit() and int(text) > 0:
            DB["users"][user_id]["max"] = int(text)
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"✅ تم تعيين العدد: {text}", reply_markup=back_btn())
        return

    # أدوات الأدمن
    if user_id == ADMIN_ID:
        if state == "admin_adding_stock":
            lines = text.splitlines()
            added = 0
            for code in lines:
                code = code.strip()
                if code and code not in DB["stock"]:
                    DB["stock"].append(code)
                    added += 1
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"📦 تم إضافة {added} كود.", reply_markup=admin_back_btn())
            return
        
        if state == "admin_adding_user":
            try:
                target_id = int(text.strip())
                if target_id not in DB["users"]:
                    DB["users"][target_id] = {
                        "role": "employee", "tokens": [], "max": 1, "history": [], "logs": [], 
                        "stats": {"api": 0, "stock": 0}, "name": "New Employee"
                    }
                    save_db_changes()
                    await update.message.reply_text(f"✅ تم إضافة {target_id} كموظف.", reply_markup=admin_back_btn())
                else:
                    await update.message.reply_text("⚠️ المستخدم موجود.", reply_markup=admin_back_btn())
            except:
                pass
            context.user_data.clear()
            return

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get("state")
    
    if user_id == ADMIN_ID and state == "admin_uploading_file":
        doc = update.message.document
        if not doc.file_name.endswith(".txt"):
            await update.message.reply_text("❌ ملف .txt فقط.", reply_markup=admin_back_btn())
            return
            
        file = await doc.get_file()
        content = await file.download_as_bytearray()
        lines = content.decode("utf-8").splitlines()
        
        added = 0
        for code in lines:
            code = code.strip()
            if code and code not in DB["stock"]:
                DB["stock"].append(code)
                added += 1
                
        save_db_changes()
        context.user_data.clear()
        await update.message.reply_text(f"📂 تم استيراد {added} كود.", reply_markup=admin_back_btn())

# ====== 🏁 التشغيل ======
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    print("🚀 Bot Started")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel_handler)) # كوماند مباشر للأدمن
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    
    app.run_polling()
