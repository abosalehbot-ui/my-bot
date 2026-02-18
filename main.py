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

# ====== 📝 إعداد اللوجز (System Logs) ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
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
DB_FILE_NAME = "bot_system_v5_final.json" 

# إعدادات الموظفين
EMPLOYEE_DAILY_LIMIT = 20  # الحد الأقصى لسحب أكواد ببجي يومياً للموظف

# ====== ☁️ دوال Google Drive (Database) ======
def get_drive_service():
    try:
        creds = service_account.Credentials.from_service_account_file(
            DRIVE_CREDENTIALS_FILE, scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"❌ Drive Auth Error: {e}")
        return None

def download_db_from_drive():
    service = get_drive_service()
    # الهيكل الأساسي لقاعدة البيانات
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
            logger.info("ℹ️ إنشاء قاعدة بيانات جديدة.")
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
        
        # تصحيح مفاتيح الـ IDs لتكون أرقاماً
        if "users" in data:
            data["users"] = {int(k): v for k, v in data["users"].items()}
        
        # دمج أي حقول ناقصة (للتحديثات المستقبلية)
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

# ====== 💾 إدارة البيانات واللوجز ======
DB = download_db_from_drive()

def save_db_changes():
    threading.Thread(target=upload_db_to_drive, args=(DB,)).start()

def log_activity(user_id, action):
    """تسجيل نشاط المستخدم"""
    if user_id not in DB["users"]: return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {action}"
    
    if "logs" not in DB["users"][user_id]: DB["users"][user_id]["logs"] = []
    DB["users"][user_id]["logs"].append(log_entry)
    
    # الاحتفاظ بآخر 200 سجل فقط
    if len(DB["users"][user_id]["logs"]) > 200:
        DB["users"][user_id]["logs"] = DB["users"][user_id]["logs"][-200:]
    
    save_db_changes()

# ====== 🌐 سيرفر Flask ======
app_server = Flask(__name__)
@app_server.route('/')
def home(): return "✅ Bot is Online (V5 Enterprise)!", 200
def run_flask(): app_server.run(host="0.0.0.0", port=8080)

# ====== ⌨️ الكيبوردات (UI) ======
def get_main_keyboard(role):
    buttons = []
    
    # 1. زر السحب (يختلف حسب الرتبة)
    if role in ["employee", "admin"]:
        buttons.append([InlineKeyboardButton("📦 سحب من المخزن (ببجي)", callback_data="pull_stock")])
    
    buttons.append([InlineKeyboardButton("🚀 سحب حسابات (API)", callback_data="pull_api")])
    
    # 2. إدارة التوكنات والرصيد
    buttons.append([
        InlineKeyboardButton("➕ إضافة توكن", callback_data="add_tokens"),
        InlineKeyboardButton("🗑 حذف توكن", callback_data="clear_tokens")
    ])
    
    buttons.append([
        InlineKeyboardButton("💰 رصيدي", callback_data="check_balance"),
        InlineKeyboardButton("🔢 العدد", callback_data="set_count")
    ])
    
    # 3. الأرشيف والمساعدة
    buttons.append([
        InlineKeyboardButton("📂 أرشيفي", callback_data="my_history"),
        InlineKeyboardButton("❓ مساعدة", callback_data="help_menu")
    ])
    
    return InlineKeyboardMarkup(buttons)

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📦 إدارة المخزن (ببجي)", callback_data="admin_stock_menu")],
        [InlineKeyboardButton("📝 تقارير وسجلات", callback_data="admin_logs_menu")],
        [InlineKeyboardButton("🛠 وضع الصيانة", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("📢 إذاعة عامة", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🏠 وضع المستخدم", callback_data="back_home")]
    ])

def stock_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 رفع ملف أكواد (.txt)", callback_data="admin_upload_stock_file")],
        [InlineKeyboardButton("✍️ إضافة كود يدوياً", callback_data="admin_add_stock_text")],
        [InlineKeyboardButton("🗑 تصفير المخزن", callback_data="admin_clear_stock")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ])

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]])

# ====== 🚀 البداية ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    # تهيئة الأدمن
    if user_id == ADMIN_ID and user_id not in DB["users"]:
        DB["users"][user_id] = {
            "role": "admin", "tokens": [], "max": 1, "history": [], "logs": [], 
            "stats": {"api": 0, "stock": 0}, "name": "Admin"
        }
        save_db_changes()

    if user_id not in DB["users"]:
        await update.message.reply_text("⛔ **البوت خاص.** تواصل مع الإدارة للتفعيل.", parse_mode=ParseMode.MARKDOWN)
        return

    # تحديث البيانات
    DB["users"][user_id]["name"] = name
    if "stats" not in DB["users"][user_id]: DB["users"][user_id]["stats"] = {"api": 0, "stock": 0}
    save_db_changes()
    
    role = DB["users"][user_id].get("role", "user")
    role_ar = "👑 أدمن" if role == "admin" else "👔 موظف" if role == "employee" else "👤 مستخدم"

    await update.message.reply_text(
        f"👋 **أهلاً بك يا {name}**\n\n🔹 **رتبتك:** {role_ar}\n🔹 **حالة البوت:** {'✅ يعمل' if not DB['settings']['maintenance'] else '⚠️ صيانة'}",
        reply_markup=get_main_keyboard(role),
        parse_mode=ParseMode.MARKDOWN
    )

# ====== 👑 لوحة الأدمن ======
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        status = "🔴 مفعل" if DB['settings']['maintenance'] else "🟢 معطل"
        stock_count = len(DB["stock"])
        await update.message.reply_text(
            f"🛠 **لوحة التحكم المركزية**\n\n"
            f"📦 **المخزن:** {stock_count} كود\n"
            f"👥 **المستخدمين:** {len(DB['users'])}\n"
            f"🛠 **وضع الصيانة:** {status}",
            reply_markup=admin_keyboard(), parse_mode=ParseMode.MARKDOWN
        )

# ====== 🕹 معالج الأزرار (The Brain) ======
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if user_id not in DB["users"] and user_id != ADMIN_ID: return
    user_data = DB["users"][user_id]
    role = user_data.get("role", "user")

    # 🛑 فحص الصيانة (يستثنى الأدمن)
    if DB["settings"].get("maintenance") and role != "admin":
        await query.edit_message_text("⚠️ **النظام في وضع الصيانة حالياً.**\nيرجى المحاولة لاحقاً.", reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        return

    # --- 🏠 العودة ---
    if data == "back_home":
        context.user_data.clear() # تنظيف الحالات
        await query.edit_message_text("🏠 **القائمة الرئيسية:**", reply_markup=get_main_keyboard(role), parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "admin_panel":
        await admin_panel(query, context)
        return

    # ==========================
    # ❓ قسم المساعدة (Help)
    # ==========================
    if data == "help_menu":
        msg = "❓ **دليل المساعدة:**\n\n"
        if role == "user":
            msg += ("1️⃣ **إضافة توكن:** انسخ التوكنات وأرسلها للبوت.\n"
                    "2️⃣ **سحب حسابات:** اضغط سحب لاستخراج إيميلات.\n"
                    "3️⃣ **الأرشيف:** لمراجعة ما قمت بسحبه.")
        elif role == "employee":
            msg += ("1️⃣ **سحب من المخزن:** لسحب أكواد ببجي (لك حد يومي).\n"
                    "2️⃣ **سحب API:** لسحب إيميلات عادية.\n"
                    "3️⃣ **مشكلة؟** تواصل مع الأدمن.")
        elif role == "admin":
            msg += ("👑 **أنت المدير.** يمكنك التحكم في المخزن والمستخدمين.\n"
                    "- لرفع أكواد: استخدم قائمة 'إدارة المخزن'.\n"
                    "- لتحميل السجلات: استخدم قائمة 'تقارير'.")
        
        await query.edit_message_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # ==========================
    # 📦 سحب من المخزن (للموظفين والأدمن)
    # ==========================
    if data == "pull_stock":
        if role == "user": return # حماية إضافية
        
        count = user_data.get("max", 1)
        stock_len = len(DB["stock"])

        # 1. فحص توفر الكمية
        if stock_len < count:
            await query.edit_message_text(f"⚠️ **المخزن لا يكفي!**\nالمتاح: {stock_len}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return

        # 2. فحص الكوتا اليومية (للموظفين فقط)
        if role == "employee":
            today = datetime.now().strftime("%Y-%m-%d")
            quota = user_data.get("quota", {"date": today, "count": 0})
            
            # تصفير العداد لو يوم جديد
            if quota["date"] != today:
                quota = {"date": today, "count": 0}
            
            if quota["count"] + count > EMPLOYEE_DAILY_LIMIT:
                rem = EMPLOYEE_DAILY_LIMIT - quota["count"]
                await query.edit_message_text(f"⛔ **تجاوزت الحد اليومي!**\nمتبقي لك اليوم: {rem} كود", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
                return
            
            # تحديث الكوتا
            quota["count"] += count
            DB["users"][user_id]["quota"] = quota

        # 3. السحب الفعلي (FIFO)
        pulled = []
        for _ in range(count):
            code = DB["stock"].pop(0)
            pulled.append(code)
        
        # 4. الحفظ والتسجيل
        DB["stats"]["total_stock"] += len(pulled)
        DB["users"][user_id]["stats"]["stock"] += len(pulled)
        log_activity(user_id, f"سحب {len(pulled)} كود من المخزن")
        
        # حفظ في الأرشيف
        formatted_codes = []
        for c in pulled:
            formatted_codes.append(f"📦 Code: {c}")
        
        if "history" not in DB["users"][user_id]: DB["users"][user_id]["history"] = []
        DB["users"][user_id]["history"].extend(formatted_codes)
        
        save_db_changes()

        # 5. العرض (تنسيق النسخ)
        msg_text = ""
        for code in pulled:
            msg_text += f"🎮 <code>{code}</code>\n"
            
        await query.edit_message_text(
            f"✅ **تم السحب بنجاح:**\n\n{msg_text}\n\n📦 المتبقي في المخزن: {len(DB['stock'])}",
            parse_mode=ParseMode.HTML, # HTML عشان النسخ
            reply_markup=back_btn()
        )
        return

    # ==========================
    # 🚀 سحب API (للجميع)
    # ==========================
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
                        # تنسيق HTML للنسخ الذكي
                        email = acc.get('email')
                        password = acc.get('password')
                        # حفظ في الأرشيف
                        full_acc_str = f"{email}:{password}"
                        if "history" not in DB["users"][user_id]: DB["users"][user_id]["history"] = []
                        DB["users"][user_id]["history"].append(full_acc_str)
                        
                        # تنسيق العرض
                        fmt_acc = (
                            f"📧 <code>{email}</code>\n"
                            f"🔑 <code>{password}</code>\n"
                            f"------------------"
                        )
                        accounts.append(fmt_acc)

                    log_activity(user_id, f"سحب API ناجح ({len(accounts)})")
                    DB["stats"]["total_api"] += len(accounts)
                    DB["users"][user_id]["stats"]["api"] += len(accounts)
                    break # خروج عند النجاح
                else:
                    if "Invalid token" in res.get("message", ""):
                        tokens_to_remove.append(token)
            except Exception as e:
                logger.error(f"API Error: {e}")
                continue
        
        # تنظيف التوكنات
        if tokens_to_remove:
            for t in tokens_to_remove:
                if t in DB["users"][user_id]["tokens"]: DB["users"][user_id]["tokens"].remove(t)
        
        save_db_changes()
        
        if accounts:
            msg_body = "\n".join(accounts)
            if len(msg_body) > 3500: msg_body = msg_body[:3500] + "\n...(باقي الحسابات في الأرشيف)"
            
            await query.edit_message_text(
                f"✅ **تمت العملية:**\n\n{msg_body}",
                parse_mode=ParseMode.HTML,
                reply_markup=back_btn()
            )
        else:
            await query.edit_message_text("❌ **فشل السحب.** تأكد من رصيد التوكنات.", reply_markup=back_btn())
        return

    # ==========================
    # ⚙️ أدوات عامة (Token, Count, History)
    # ==========================
    if data == "add_tokens":
        context.user_data["state"] = "waiting_tokens"
        await query.edit_message_text("📝 **أرسل التوكنات الآن (كل توكن في سطر):**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "clear_tokens":
        DB["users"][user_id]["tokens"] = []
        save_db_changes()
        await query.edit_message_text("🗑 **تم حذف جميع التوكنات.**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "set_count":
        context.user_data["state"] = "waiting_count"
        await query.edit_message_text("🔢 **أرسل الرقم الجديد:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "check_balance":
        t_count = len(user_data.get("tokens", []))
        stats = user_data.get("stats", {})
        await query.edit_message_text(
            f"💰 **محفظتك:**\n\n"
            f"🔑 التوكنات المحفوظة: {t_count}\n"
            f"📊 إجمالي سحب (API): {stats.get('api', 0)}\n"
            f"🎮 إجمالي سحب (مخزن): {stats.get('stock', 0)}",
            reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if data == "my_history":
        hist = user_data.get("history", [])
        if not hist:
            await query.edit_message_text("📂 أرشيفك فارغ.", reply_markup=back_btn())
        else:
            # عرض آخر 5 فقط لتجنب طول الرسالة
            last_5 = hist[-5:]
            txt = "\n".join(last_5)
            await query.edit_message_text(f"📂 **آخر 5 عمليات:**\n\n{txt}", reply_markup=back_btn())
        return

    # ==========================
    # 👑 أدوات الأدمن (إدارة المخزن والمستخدمين)
    # ==========================
    if role == "admin":
        if data == "admin_stock_menu":
            await query.edit_message_text(f"📦 **إدارة المخزن**\nالعدد الحالي: {len(DB['stock'])}", reply_markup=stock_manage_keyboard())
            return
        
        if data == "admin_add_stock_text":
            context.user_data["state"] = "admin_adding_stock"
            await query.edit_message_text("✍️ **أرسل الأكواد (كل كود في سطر):**", reply_markup=back_btn())
            return
        
        if data == "admin_upload_stock_file":
            context.user_data["state"] = "admin_uploading_file"
            await query.edit_message_text("📂 **أرسل ملف .txt يحتوي على الأكواد:**", reply_markup=back_btn())
            return
        
        if data == "admin_clear_stock":
            DB["stock"] = []
            save_db_changes()
            await query.answer("🗑 تم تصفير المخزن!", show_alert=True)
            await query.edit_message_text("🗑 المخزن فارغ الآن.", reply_markup=back_btn())
            return

        if data == "admin_users_menu":
            # اختصار: عرض إحصائية سريعة
            msg = f"👥 **المستخدمين:** {len(DB['users'])}\n\n"
            for uid, u in DB["users"].items():
                msg += f"👤 {u['name']} | {u.get('role')} | ID: `{uid}`\n"
            await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ إضافة مستخدم/موظف", callback_data="admin_add_user_prompt")], [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]))
            return

        if data == "admin_add_user_prompt":
            context.user_data["state"] = "admin_adding_user"
            await query.edit_message_text("✍️ **أرسل ID المستخدم:**", reply_markup=back_btn())
            return
        
        if data == "toggle_maintenance":
            DB["settings"]["maintenance"] = not DB["settings"]["maintenance"]
            save_db_changes()
            st = "مفعل" if DB["settings"]["maintenance"] else "معطل"
            await query.answer(f"تم تغيير وضع الصيانة إلى: {st}", show_alert=True)
            await admin_panel(query, context)
            return

# ====== 📩 معالج النصوص والملفات ======
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data.get("state")
    
    if not state: return

    # --- إضافة توكنات (User/Employee) ---
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
        await update.message.reply_text(f"✅ تم إضافة {added} توكن جديد.", reply_markup=back_btn())
        return

    # --- تعيين العدد (User/Employee) ---
    if state == "waiting_count":
        if text.isdigit() and int(text) > 0:
            DB["users"][user_id]["max"] = int(text)
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"✅ تم تعيين عدد السحب: {text}", reply_markup=back_btn())
        return

    # --- أدوات الأدمن ---
    if user_id == ADMIN_ID:
        # إضافة أكواد نصية
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
            await update.message.reply_text(f"📦 تم إضافة {added} كود للمخزن.", reply_markup=back_btn())
            return
        
        # إضافة مستخدم
        if state == "admin_adding_user":
            try:
                target_id = int(text.strip())
                if target_id not in DB["users"]:
                    # افتراضياً نضيفه كموظف (يمكنك تغييرها)
                    DB["users"][target_id] = {
                        "role": "employee", "tokens": [], "max": 1, "history": [], "logs": [], 
                        "stats": {"api": 0, "stock": 0}, "name": "New Employee"
                    }
                    save_db_changes()
                    await update.message.reply_text(f"✅ تم إضافة {target_id} كموظف.", reply_markup=back_btn())
                else:
                    await update.message.reply_text("⚠️ المستخدم موجود بالفعل.", reply_markup=back_btn())
            except:
                await update.message.reply_text("❌ تأكد من أن الـ ID رقم صحيح.", reply_markup=back_btn())
            context.user_data.clear()
            return

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # معالج ملفات المخزن (Admin Only)
    user_id = update.effective_user.id
    state = context.user_data.get("state")
    
    if user_id == ADMIN_ID and state == "admin_uploading_file":
        doc = update.message.document
        if not doc.file_name.endswith(".txt"):
            await update.message.reply_text("❌ الملف يجب أن يكون .txt", reply_markup=back_btn())
            return
            
        file = await doc.get_file()
        content = await file.download_as_bytearray()
        decoded_text = content.decode("utf-8")
        
        lines = decoded_text.splitlines()
        added = 0
        for code in lines:
            code = code.strip()
            if code and code not in DB["stock"]:
                DB["stock"].append(code)
                added += 1
                
        save_db_changes()
        context.user_data.clear()
        await update.message.reply_text(f"📂 تم استيراد {added} كود من الملف.", reply_markup=back_btn())

# ====== 🏁 التشغيل ======
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    print("🚀 Bot Started Successfully!")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    
    app.run_polling()
