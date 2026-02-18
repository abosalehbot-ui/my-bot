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

# ====== 📝 إعداد اللوجز ======
logging.basicConfig(
    format='%(asctime)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
# تقليل الضجيج
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = "8577787177:AAH-p_2EVtcgff_ML8Rc0jGrJ2OiV-lExTY"
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"

# إعدادات جوجل درايف (مع حل المساحة)
DRIVE_CREDENTIALS_FILE = "credentials.json"
DB_FILE_NAME = "bot_system_v10_ultimate.json" 
FOLDER_ID = "1Y-rECgcPmzLw8UQ2NW-wWr6Y_KHlfoLY" # مجلدك المشترك

# إعدادات الموظفين
EMPLOYEE_DAILY_LIMIT = 20

# ====== ☁️ دوال Google Drive (المعدلة) ======
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
        "codes_map": {}
    }
    
    if not service: return default_db

    try:
        # البحث داخل المجلد المشترك فقط
        query = f"name='{DB_FILE_NAME}' and '{FOLDER_ID}' in parents and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            logger.info("ℹ️ قاعدة البيانات غير موجودة، سيتم إنشاؤها لاحقاً.")
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
        
        # تحويل مفاتيح المستخدمين لأرقام (Integers)
        if "users" in data:
            data["users"] = {int(k): v for k, v in data["users"].items()}
        
        # دمج القيم الافتراضية
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

        # البحث عن الملف لتحديثه
        query = f"name='{DB_FILE_NAME}' and '{FOLDER_ID}' in parents and trashed=false"
        results = service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])

        media = MediaFileUpload("temp_db.json", mimetype='application/json')

        if items:
            # تحديث الملف الموجود
            service.files().update(fileId=items[0]['id'], media_body=media).execute()
        else:
            # إنشاء ملف جديد داخل المجلد المشترك (لتفادي الكوتا)
            file_metadata = {'name': DB_FILE_NAME, 'parents': [FOLDER_ID]}
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
    
    # الاحتفاظ بآخر 50 سجل فقط لتوفير المساحة
    if len(DB["users"][user_id]["logs"]) > 50:
        DB["users"][user_id]["logs"] = DB["users"][user_id]["logs"][-50:]
    
    save_db_changes()

# ====== 🌐 سيرفر Flask (للبقاء أونلاين) ======
app_server = Flask(__name__)
@app_server.route('/')
def home(): return "✅ Bot Online & Ready!", 200
def run_flask(): app_server.run(host="0.0.0.0", port=8080)

# ====== ⌨️ الكيبوردات ======

def get_main_keyboard(role):
    buttons = []
    if role in ["employee", "admin"]:
        buttons.append([InlineKeyboardButton("🎮 سحب كود ببجي", callback_data="pull_stock")])
    
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

    if role == "admin":
        buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons)

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📦 إدارة المخزن", callback_data="admin_stock_menu")],
        [InlineKeyboardButton("🔍 البحث العكسي", callback_data="admin_reverse_search")],
        [InlineKeyboardButton("📝 السجلات", callback_data="admin_get_logs")],
        [InlineKeyboardButton("🛠 وضع الصيانة", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("🏠 خروج", callback_data="back_home")]
    ])

def stock_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 رفع ملف (.txt)", callback_data="admin_upload_stock_file")],
        [InlineKeyboardButton("✍️ إضافة يدوي", callback_data="admin_add_stock_text")],
        [InlineKeyboardButton("🗑 تصفير المخزن", callback_data="admin_clear_stock")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]])
def admin_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]])

# ====== 🚀 Handlers ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    # تعريف الأدمن تلقائياً
    if user_id == ADMIN_ID and user_id not in DB["users"]:
        DB["users"][user_id] = {"role":"admin", "tokens":[], "max":1, "history":[], "logs":[], "stats":{"api":0,"stock":0}, "name":"Admin"}
        save_db_changes()

    if user_id not in DB["users"]:
        await update.message.reply_text("⛔ غير مسجل. تواصل مع الإدارة.", parse_mode=ParseMode.MARKDOWN)
        return

    DB["users"][user_id]["name"] = name
    role = DB["users"][user_id].get("role", "user")
    
    maint_msg = "\n⚠️ **النظام في وضع الصيانة**" if DB['settings']['maintenance'] else ""
    
    await update.message.reply_text(
        f"👋 أهلاً {name}\n🔹 الرتبة: {role}{maint_msg}",
        reply_markup=get_main_keyboard(role),
        parse_mode=ParseMode.MARKDOWN
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()
    
    # Auto-fix admin
    if user_id not in DB["users"] and user_id == ADMIN_ID:
        DB["users"][user_id] = {"role":"admin", "tokens":[], "max":1, "history":[], "logs":[], "stats":{"api":0,"stock":0}, "name":"Admin"}
        save_db_changes()
    
    if user_id not in DB["users"]: return
    user_data = DB["users"][user_id]
    role = user_data.get("role", "user")

    # فحص الصيانة
    if DB["settings"].get("maintenance") and role != "admin":
        await query.edit_message_text("⚠️ **الصيانة جارية حالياً...**", reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        return

    # --- التنقلات ---
    if data == "back_home":
        context.user_data.clear()
        await query.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard(role))
        return
        
    if data == "admin_panel" and role == "admin":
        status = "🔴 مفعل" if DB['settings']['maintenance'] else "🟢 معطل"
        stock_len = len(DB["stock"])
        await query.edit_message_text(f"🛠 **لوحة الأدمن**\n📦 المخزن: {stock_len}\n🛠 الصيانة: {status}", reply_markup=admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_stock_menu" and role == "admin":
        await query.edit_message_text(f"📦 **إدارة المخزن**\nالعدد الحالي: {len(DB['stock'])}", reply_markup=stock_manage_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "help_menu":
        msg = "❓ **المساعدة:**\n1️⃣ أضف توكن -> سحب API.\n2️⃣ موظف -> سحب مخزن (ببجي).\n3️⃣ تابع أرشيفك."
        await query.edit_message_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- الأزرار التي كانت لا تعمل (تم الإصلاح) ---

    # 1. حذف التوكنات
    if data == "clear_tokens":
        user_data["tokens"] = []
        save_db_changes()
        await query.edit_message_text("🗑 **تم حذف جميع التوكنات.**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # 2. فحص الرصيد
    if data == "check_balance":
        t_count = len(user_data.get("tokens", []))
        stats = user_data.get("stats", {"api": 0, "stock": 0})
        await query.edit_message_text(
            f"💰 **محفظتك:**\n🔑 توكنات: {t_count}\n🚀 سحب API: {stats['api']}\n🎮 سحب مخزن: {stats['stock']}",
            reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN
        )
        return

    # 3. تعيين العدد
    if data == "set_count":
        context.user_data["state"] = "waiting_count"
        await query.edit_message_text("🔢 **أرسل الرقم الجديد (للسحب في المرة الواحدة):**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # 4. الأرشيف
    if data == "my_history":
        hist = user_data.get("history", [])
        if not hist:
            await query.edit_message_text("📂 أرشيفك فارغ.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        else:
            txt = "\n".join(hist[-10:]) # آخر 10
            await query.edit_message_text(f"📂 **آخر 10 عمليات:**\n\n{txt}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return
    
    # 5. إضافة توكنات (كانت موجودة لكن للتأكيد)
    if data == "add_tokens":
        context.user_data["state"] = "waiting_tokens"
        await query.edit_message_text("📝 **أرسل التوكنات (كل توكن في سطر):**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- أدوات الأدمن (التي كانت لا تعمل) ---

    # 6. تفعيل/تعطيل الصيانة
    if data == "toggle_maintenance" and role == "admin":
        DB['settings']['maintenance'] = not DB['settings']['maintenance']
        save_db_changes()
        # إعادة تحميل اللوحة لتحديث الحالة
        status = "🔴 مفعل" if DB['settings']['maintenance'] else "🟢 معطل"
        await query.edit_message_text(f"🛠 **لوحة الأدمن**\n📦 المخزن: {len(DB['stock'])}\n🛠 الصيانة: {status}", reply_markup=admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    # 7. تحميل السجلات
    if data == "admin_get_logs" and role == "admin":
        await query.edit_message_text("⏳ **جاري جلب السجلات...**", parse_mode=ParseMode.MARKDOWN)
        all_logs = []
        for uid, u in DB["users"].items():
            if u.get("logs"):
                all_logs.append(f"--- 👤 {u['name']} ({uid}) ---")
                all_logs.extend(u["logs"][-5:]) # آخر 5 لكل شخص
        
        if not all_logs:
            await query.edit_message_text("📭 لا توجد سجلات نشاط حديثة.", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        else:
            report = "\n".join(all_logs)
            if len(report) > 4000: report = report[:4000] + "\n..."
            await query.edit_message_text(f"📝 **ملخص النشاط:**\n\n{report}", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # 8. تصفير المخزن
    if data == "admin_clear_stock" and role == "admin":
        DB["stock"] = []
        save_db_changes()
        await query.edit_message_text("🗑 **تم تصفير المخزن بنجاح.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return
    
    # 9. البحث العكسي
    if data == "admin_reverse_search" and role == "admin":
        context.user_data["state"] = "waiting_reverse_code"
        await query.edit_message_text("🔍 **أرسل الكود لمعرفة من قام بسحبه:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # 10. إضافة مخزن يدوي وملف
    if data == "admin_add_stock_text" and role == "admin":
        context.user_data["state"] = "adding_stock_manual"
        await query.edit_message_text("✍️ **أرسل الأكواد للإضافة:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "admin_upload_stock_file" and role == "admin":
        context.user_data["state"] = "admin_uploading_file"
        await query.edit_message_text("📂 **أرسل ملف .txt يحتوي على الأكواد:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return
    
    # 11. إدارة المستخدمين (عرض سريع)
    if data == "admin_users_menu" and role == "admin":
         msg = f"👥 **المستخدمين المسجلين:** {len(DB['users'])}\n"
         # عرض أول 10 فقط كمثال
         count = 0
         for uid, u in DB["users"].items():
             if count >= 10: break
             msg += f"- {u['name']} ({u.get('role')})\n"
             count += 1
         await query.edit_message_text(msg, reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
         return

    # --- عمليات السحب ---
    
    # سحب ببجي
    if data == "pull_stock":
        if role not in ["admin", "employee"]: return
        if not DB["stock"]:
            await query.edit_message_text("⚠️ **المخزن فارغ!**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return
        
        count = user_data.get("max", 1)
        if len(DB["stock"]) < count:
            await query.edit_message_text(f"⚠️ **الكمية غير كافية!** المتوفر: {len(DB['stock'])}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return

        pulled = []
        for _ in range(count):
            code = DB["stock"].pop(0)
            pulled.append(code)
            # تسجيل للبحث العكسي
            DB.setdefault("codes_map", {})[code] = {
                "name": user_data["name"], 
                "id": user_id, 
                "time": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        
        # حفظ السجل والإحصائيات
        for c in pulled:
             user_data["history"].append(f"📦 {c}")
        user_data["stats"]["stock"] += len(pulled)
        log_activity(user_id, f"سحب {len(pulled)} كود ببجي")
        save_db_changes()
        
        msg = "\n".join([f"🎮 <code>{c}</code>" for c in pulled])
        await query.edit_message_text(f"✅ **تم السحب:**\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=back_btn())
        return

    # سحب API
    if data == "pull_api":
        if not user_data["tokens"]:
            await query.edit_message_text("⚠️ **لا يوجد توكنات!** أضف توكن أولاً.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return
        
        await query.edit_message_text("⏳ **جاري الاتصال بالسيرفر...**", parse_mode=ParseMode.MARKDOWN)
        accs = []
        tokens_to_remove = []
        
        for t in list(user_data["tokens"]):
            try:
                r = requests.post(f"{API_BASE_URL}/api/redeem-bulk", json={"token":t, "product":PRODUCT_ID, "qty":user_data["max"]}, timeout=15).json()
                if r.get("success"):
                    for a in r["accounts"]:
                        accs.append(f"📧 <code>{a['email']}</code>\n🔑 <code>{a['password']}</code>\n---")
                        user_data["history"].append(f"{a['email']}:{a['password']}")
                    user_data["stats"]["api"] += len(r["accounts"])
                    log_activity(user_id, f"سحب API ناجح ({len(r['accounts'])})")
                    break
                elif "Invalid" in r.get("message", ""): 
                    tokens_to_remove.append(t)
            except Exception as e:
                logger.error(f"API Error: {e}")
                continue
        
        for t in tokens_to_remove:
            if t in user_data["tokens"]: user_data["tokens"].remove(t)
            
        save_db_changes()
        
        if accs: 
            await query.edit_message_text("\n".join(accs), parse_mode=ParseMode.HTML, reply_markup=back_btn())
        else: 
            await query.edit_message_text("❌ **فشل السحب.** تأكد من صحة التوكنات.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

# ====== 📩 معالج الرسائل ======

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    uid = update.effective_user.id
    state = context.user_data.get("state")
    txt = update.message.text.strip()
    
    if uid not in DB["users"]: return
    
    # 1. إضافة توكنات
    if state == "waiting_tokens":
        lines = txt.splitlines()
        added = 0
        if "tokens" not in DB["users"][uid]: DB["users"][uid]["tokens"] = []
        for t in lines:
            t = t.strip()
            if t and t not in DB["users"][uid]["tokens"]:
                DB["users"][uid]["tokens"].append(t)
                added += 1
        save_db_changes()
        context.user_data.clear()
        await update.message.reply_text(f"✅ تم إضافة {added} توكن بنجاح.", reply_markup=back_btn())
    
    # 2. تعيين العدد
    elif state == "waiting_count":
        if txt.isdigit() and int(txt) > 0:
            DB["users"][uid]["max"] = int(txt)
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"✅ تم تعيين عدد السحب إلى: {txt}", reply_markup=back_btn())
        else:
            await update.message.reply_text("❌ يرجى إرسال رقم صحيح أكبر من 0.")

    # 3. البحث العكسي (أدمن)
    elif state == "waiting_reverse_code" and uid == ADMIN_ID:
        res = DB.get("codes_map", {}).get(txt)
        if res:
            await update.message.reply_text(
                f"🔍 **نتائج البحث:**\n\n📝 الكود: `{txt}`\n👤 سحبه: {res['name']}\n🆔 ID: `{res['id']}`\n📅 الوقت: {res['time']}",
                reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ لم يتم العثور على هذا الكود في السجلات.", reply_markup=admin_back_btn())
        context.user_data.clear()

    # 4. إضافة مخزن يدوي (أدمن)
    elif state == "adding_stock_manual" and uid == ADMIN_ID:
        lines = txt.splitlines()
        added = 0
        for c in lines:
            c = c.strip()
            if c and c not in DB["stock"]:
                DB["stock"].append(c)
                added += 1
        save_db_changes()
        context.user_data.clear()
        await update.message.reply_text(f"📦 تم إضافة {added} كود للمخزن.", reply_markup=admin_back_btn())

# ====== 📂 معالج الملفات (لرفع الأكواد) ======
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    
    if uid == ADMIN_ID and state == "admin_uploading_file":
        doc = update.message.document
        if not doc.file_name.endswith(".txt"):
            await update.message.reply_text("❌ الملف يجب أن يكون بصيغة .txt", reply_markup=admin_back_btn())
            return
            
        file = await doc.get_file()
        content = await file.download_as_bytearray()
        decoded_text = content.decode("utf-8", errors="ignore")
        
        lines = decoded_text.splitlines()
        added = 0
        for c in lines:
            c = c.strip()
            if c and c not in DB["stock"]:
                DB["stock"].append(c)
                added += 1
        
        save_db_changes()
        context.user_data.clear()
        await update.message.reply_text(f"📂 تم استيراد {added} كود من الملف.", reply_markup=admin_back_btn())

# ====== 🏁 التشغيل ======
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    print("🚀 Bot Started Successfully")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    
    app.run_polling(drop_pending_updates=True)
