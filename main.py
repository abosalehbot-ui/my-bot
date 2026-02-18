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

# ====== 📝 إعداد اللوجز (يظهر في التيرمينال) ======
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = "8577787177:AAF7Vs0kE-p6_PX8AyKvzGtG1YyJw0cmDmU"
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"

# إعدادات جوجل درايف
DRIVE_CREDENTIALS_FILE = "credentials.json"
FOLDER_ID = "1Y-rECgcPmzLw8UQ2NW-wWr6Y_KHlfoLY" 

# ✅ الآيدي الثابت للملف
DB_FILE_ID = "1xfU3GMswuvbWrnY8fybQxTU5_jDC_jjL" 

# فئات الشدات (مرتبة)
UC_CATEGORIES = ["60", "325", "660", "1800", "3850", "8100"]

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
    # الهيكل الجديد: Stock أصبح قاموساً للفئات
    default_db = {
        "users": {}, 
        "stock": {cat: [] for cat in UC_CATEGORIES}, 
        "orders": {}, 
        "settings": {"maintenance": False},
        "stats": {"total_api": 0, "total_stock": 0, "last_order_id": 0},
        "codes_map": {}
    }
    
    if not service: return default_db

    try:
        logger.info(f"📥 جاري تحميل البيانات من الملف ID: {DB_FILE_ID}")
        request = service.files().get_media(fileId=DB_FILE_ID)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        fh.seek(0)
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            data = default_db
        
        if "users" in data:
            data["users"] = {int(k): v for k, v in data["users"].items()}
        
        # === 🛠️ ترحيل البيانات للنظام الجديد ===
        # إذا كان المخزن قائمة قديمة، نضع محتواه في فئة 60
        if isinstance(data.get("stock"), list):
            logger.warning("⚠️ تحديث هيكل قاعدة البيانات لنظام الفئات...")
            old_stock = data["stock"]
            data["stock"] = {cat: [] for cat in UC_CATEGORIES}
            if old_stock:
                data["stock"]["60"] = old_stock
        
        # التأكد من وجود كل الفئات
        if isinstance(data.get("stock"), dict):
            for cat in UC_CATEGORIES:
                if cat not in data["stock"]:
                    data["stock"][cat] = []

        for key in default_db:
            if key not in data: data[key] = default_db[key]
            
        logger.info("✅ تم تحميل البيانات بنجاح.")
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

        media = MediaFileUpload("temp_db.json", mimetype='application/json', resumable=True)
        service.files().update(fileId=DB_FILE_ID, media_body=media).execute()
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
    
    logger.info(f"📝 Activity | User: {user_id} | {action}")
    
    if "logs" not in DB["users"][user_id]: DB["users"][user_id]["logs"] = []
    DB["users"][user_id]["logs"].append(log_entry)
    
    if len(DB["users"][user_id]["logs"]) > 200:
        DB["users"][user_id]["logs"] = DB["users"][user_id]["logs"][-200:]
    
    save_db_changes()

# ====== 🌐 سيرفر Flask ======
app_server = Flask(__name__)
@app_server.route('/')
def home(): return "✅ Bot Online & Ready!", 200
def run_flask(): app_server.run(host="0.0.0.0", port=8080)

# ====== ⌨️ الكيبوردات ======

def get_main_keyboard(role):
    buttons = []
    if role in ["employee", "admin"]:
        buttons.append([InlineKeyboardButton("🎮 سحب كود ببجي (UC)", callback_data="pull_stock_menu")])
    
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
        InlineKeyboardButton("🔍 كشف طلب (ID)", callback_data="check_order_id"),
        InlineKeyboardButton("📂 أرشيفي", callback_data="my_history")
    ])
    
    buttons.append([InlineKeyboardButton("❓ مساعدة", callback_data="help_menu")])

    if role == "admin":
        buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons)

def admin_keyboard():
    # حساب الإجمالي
    total = sum(len(v) for v in DB["stock"].values())
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton(f"📦 إدارة المخزن ({total})", callback_data="admin_stock_menu")],
        [InlineKeyboardButton("🔍 بحث عكسي (كود)", callback_data="admin_reverse_search"),
         InlineKeyboardButton("📄 بحث برقم الطلب", callback_data="admin_search_order")],
        [InlineKeyboardButton("📝 سجلات النظام", callback_data="admin_get_logs")],
        [InlineKeyboardButton("🛠 وضع الصيانة", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("🏠 خروج", callback_data="back_home")]
    ])

def admin_users_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة مستخدم", callback_data="admin_add_user_btn"),
         InlineKeyboardButton("🗑 حذف مستخدم", callback_data="admin_remove_user_btn")],
        [InlineKeyboardButton("🔄 تغيير رتبة (عادي/موظف)", callback_data="admin_switch_role_btn")], # زر جديد
        [InlineKeyboardButton("📜 سجلات مستخدم", callback_data="admin_get_user_logs_btn")],
        [InlineKeyboardButton("📋 عرض القائمة", callback_data="admin_list_users_btn")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
    ])

def stock_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 رفع ملف (.txt)", callback_data="admin_choose_cat_file")],
        [InlineKeyboardButton("✍️ إضافة يدوي", callback_data="admin_choose_cat_manual")],
        [InlineKeyboardButton("🗑 تصفير فئة محددة", callback_data="admin_choose_cat_clear")],
        [InlineKeyboardButton("⚠️ تصفير المخزن بالكامل", callback_data="admin_clear_all_confirm")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ])

# كيبورد الفئات (ديناميكي مع العدد)
def categories_keyboard(action_prefix):
    buttons = []
    row = []
    for cat in UC_CATEGORIES:
        count = len(DB["stock"].get(cat, []))
        btn_text = f"{cat} UC ({count})"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"{action_prefix}_{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    back_cb = "admin_stock_menu" if "admin" in action_prefix else "back_home"
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=back_cb)])
    return InlineKeyboardMarkup(buttons)

# كيبورد ما بعد السحب
def success_pull_keyboard(callback_data):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 طلب آخر", callback_data=callback_data)],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]])
def admin_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]])
def admin_users_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للمستخدمين", callback_data="admin_users_menu")]])

# ====== 🚀 Handlers ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    logger.info(f"🚀 Start command from: {name} ({user_id})")
    
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
    
    logger.info(f"🔘 Button: {data} | User: {user_id}")

    if user_id not in DB["users"] and user_id == ADMIN_ID:
        DB["users"][user_id] = {"role":"admin", "tokens":[], "max":1, "history":[], "logs":[], "stats":{"api":0,"stock":0}, "name":"Admin"}
        save_db_changes()
    
    if user_id not in DB["users"]: return
    user_data = DB["users"][user_id]
    role = user_data.get("role", "user")

    if DB["settings"].get("maintenance") and role != "admin":
        await query.edit_message_text("⚠️ **الصيانة جارية حالياً...**", reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        return

    # --- التنقلات ---
    if data == "back_home":
        context.user_data.clear()
        await query.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard(role))
        return
        
    if data == "admin_panel" and role == "admin":
        context.user_data.clear()
        status = "🔴 مفعل" if DB['settings']['maintenance'] else "🟢 معطل"
        stock_total = sum(len(v) for v in DB["stock"].values())
        await query.edit_message_text(f"🛠 **لوحة الأدمن**\n📦 إجمالي المخزن: {stock_total}\n🛠 الصيانة: {status}", reply_markup=admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- إدارة المستخدمين ---
    if data == "admin_users_menu" and role == "admin":
        context.user_data.clear()
        await query.edit_message_text(f"👥 **إدارة المستخدمين**\nعدد المستخدمين: {len(DB['users'])}", reply_markup=admin_users_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_add_user_btn" and role == "admin":
        context.user_data["state"] = "waiting_add_user_id"
        await query.edit_message_text("✍️ **أرسل الآيدي (ID) لإضافته:**", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_remove_user_btn" and role == "admin":
        context.user_data["state"] = "waiting_remove_user_id"
        await query.edit_message_text("🗑 **أرسل الآيدي (ID) لحذفه:**", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "admin_switch_role_btn" and role == "admin":
        context.user_data["state"] = "waiting_switch_role_id"
        await query.edit_message_text("🔄 **أرسل الآيدي (ID) لتغيير رتبته:**\n(سيتحول من عادي لموظف، أو العكس)", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_get_user_logs_btn" and role == "admin":
        context.user_data["state"] = "waiting_user_logs_id"
        await query.edit_message_text("📜 **أرسل الآيدي (ID) لاستخراج سجلاته:**", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("set_role_") and role == "admin":
        new_uid = context.user_data.get("new_user_id")
        if not new_uid:
            await query.edit_message_text("❌ حدث خطأ، أعد المحاولة.", reply_markup=admin_users_back_btn())
            return
        selected_role = "employee" if data == "set_role_employee" else "user"
        DB["users"][new_uid] = {"role": selected_role, "name": "User", "tokens": [], "max": 1, "history": [], "logs": [], "stats": {"api":0,"stock":0}}
        save_db_changes()
        context.user_data.clear()
        role_txt = "موظف" if selected_role == "employee" else "مستخدم"
        await query.edit_message_text(f"✅ تم إضافة `{new_uid}` كرتبة **{role_txt}**.", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_list_users_btn" and role == "admin":
        msg = f"👥 **المستخدمين ({len(DB['users'])})**:\n\n"
        count = 0
        for uid, u in list(DB["users"].items())[-20:]:
             role_icon = "👮‍♂️" if u['role'] == "admin" else "👤" if u['role'] == "employee" else "🆕"
             msg += f"{role_icon} `{uid}` | {u.get('name', 'بدون اسم')}\n"
             count += 1
        if len(DB["users"]) > 20: msg += "\n⚠️ (يتم عرض آخر 20 فقط)"
        await query.edit_message_text(msg, reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- إدارة المخزن (أدمن) ---
    if data == "admin_stock_menu" and role == "admin":
        context.user_data.clear()
        await query.edit_message_text(f"📦 **إدارة المخزن**\nاختر العملية:", reply_markup=stock_manage_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return
    
    # اختيار فئة للإضافة
    if data == "admin_choose_cat_manual" and role == "admin":
        await query.edit_message_text("🔢 **اختر الفئة للإضافة اليدوية:**", reply_markup=categories_keyboard("admin_add_manual"))
        return

    if data == "admin_choose_cat_file" and role == "admin":
        await query.edit_message_text("📂 **اختر الفئة لرفع الملف:**", reply_markup=categories_keyboard("admin_add_file"))
        return

    if data == "admin_choose_cat_clear" and role == "admin":
        await query.edit_message_text("🗑 **اختر الفئة لتصفيرها:**", reply_markup=categories_keyboard("admin_clear_cat"))
        return

    # تنفيذ الأوامر
    if data.startswith("admin_add_manual_") and role == "admin":
        cat = data.split("_")[-1]
        context.user_data["state"] = "adding_stock_manual"
        context.user_data["target_cat"] = cat
        await query.edit_message_text(f"✍️ **أرسل الأكواد لفئة {cat} UC:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("admin_add_file_") and role == "admin":
        cat = data.split("_")[-1]
        context.user_data["state"] = "admin_uploading_file"
        context.user_data["target_cat"] = cat
        await query.edit_message_text(f"📂 **أرسل ملف .txt لفئة {cat} UC:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("admin_clear_cat_") and role == "admin":
        cat = data.split("_")[-1]
        DB["stock"][cat] = []
        save_db_changes()
        await query.edit_message_text(f"🗑 **تم تصفير فئة {cat} UC بنجاح.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_clear_all_confirm" and role == "admin":
        for cat in DB["stock"]:
            DB["stock"][cat] = []
        save_db_changes()
        await query.edit_message_text("🗑 **تم تصفير جميع الفئات بنجاح.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # معالجة التكرار
    if data == "confirm_add_all" and role == "admin":
        pending = context.user_data.get("pending_stock")
        cat = context.user_data.get("target_cat")
        if not pending or not cat: return
        DB["stock"][cat].extend(pending["unique"])
        DB["stock"][cat].extend(pending["dupes"])
        save_db_changes()
        total = len(pending["unique"]) + len(pending["dupes"])
        context.user_data.clear()
        await query.edit_message_text(f"✅ تم إضافة {total} كود لفئة {cat} UC.", reply_markup=admin_back_btn())
        return

    if data == "confirm_add_unique" and role == "admin":
        pending = context.user_data.get("pending_stock")
        cat = context.user_data.get("target_cat")
        if not pending or not cat: return
        DB["stock"][cat].extend(pending["unique"])
        save_db_changes()
        context.user_data.clear()
        await query.edit_message_text(f"✅ تم إضافة {len(pending['unique'])} كود جديد لفئة {cat} UC.", reply_markup=admin_back_btn())
        return
        
    if data == "cancel_add_stock" and role == "admin":
        context.user_data.clear()
        await query.edit_message_text("❌ تم إلغاء العملية.", reply_markup=admin_back_btn())
        return

    # --- القوائم العامة ---
    if data == "help_menu":
        msg = "❓ **المساعدة:**\n1️⃣ أضف توكن -> سحب API.\n2️⃣ موظف -> سحب مخزن.\n3️⃣ رقم الطلب: لاسترجاع الكود."
        await query.edit_message_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "clear_tokens":
        user_data["tokens"] = []
        save_db_changes()
        await query.edit_message_text("🗑 **تم حذف جميع التوكنات.**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "check_balance":
        t_count = len(user_data.get("tokens", []))
        stats = user_data.get("stats", {"api": 0, "stock": 0})
        await query.edit_message_text(
            f"💰 **محفظتك:**\n🔑 توكنات: {t_count}\n🚀 سحب API: {stats['api']}\n🎮 سحب مخزن: {stats['stock']}",
            reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN
        )
        return

    if data == "set_count":
        context.user_data["state"] = "waiting_count"
        await query.edit_message_text("🔢 **أرسل الرقم الجديد:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "my_history":
        hist = user_data.get("history", [])
        if not hist:
            await query.edit_message_text("📂 أرشيفك فارغ.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        else:
            txt = "\n".join(hist[-10:])
            await query.edit_message_text(f"📂 **آخر 10 عمليات:**\n\n{txt}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "add_tokens":
        context.user_data["state"] = "waiting_tokens"
        await query.edit_message_text("📝 **أرسل التوكنات:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "check_order_id":
        context.user_data["state"] = "waiting_order_id"
        await query.edit_message_text("🔍 **أرسل رقم الطلب (ID):**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "toggle_maintenance" and role == "admin":
        DB['settings']['maintenance'] = not DB['settings']['maintenance']
        save_db_changes()
        status = "🔴 مفعل" if DB['settings']['maintenance'] else "🟢 معطل"
        await query.edit_message_text(f"🛠 **لوحة الأدمن**\n📦 الحالة: {status}", reply_markup=admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_get_logs" and role == "admin":
        await query.edit_message_text("⏳ **جاري جلب السجلات...**", parse_mode=ParseMode.MARKDOWN)
        all_logs = []
        for uid, u in DB["users"].items():
            if u.get("logs"):
                all_logs.append(f"--- 👤 {u['name']} ({uid}) ---")
                all_logs.extend(u["logs"][-5:])
        
        if not all_logs:
            await query.edit_message_text("📭 لا توجد سجلات.", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        else:
            report = "\n".join(all_logs)
            if len(report) > 4000: report = report[:4000] + "\n..."
            await query.edit_message_text(f"📝 **ملخص النشاط:**\n\n{report}", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "admin_reverse_search" and role == "admin":
        context.user_data["state"] = "waiting_reverse_code"
        await query.edit_message_text("🔍 **أرسل الكود:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_search_order" and role == "admin":
        context.user_data["state"] = "waiting_admin_order_search"
        await query.edit_message_text("📄 **أرسل رقم الطلب:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # ====== عمليات السحب ======
    
    # 1. قائمة سحب ببجي (اختيار الفئة)
    if data == "pull_stock_menu":
        if role not in ["admin", "employee"]: return
        await query.edit_message_text("🎮 **اختر فئة الشدات للسحب:**", reply_markup=categories_keyboard("pull_cat"))
        return

    # 2. تنفيذ سحب ببجي
    if data.startswith("pull_cat_"):
        if role not in ["admin", "employee"]: return
        cat = data.split("_")[-1]
        
        stock_list = DB["stock"].get(cat, [])
        if not stock_list:
            await query.edit_message_text(f"❌ **فئة {cat} UC فارغة حالياً!**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return
        
        count = user_data.get("max", 1)
        if len(stock_list) < count:
            await query.edit_message_text(f"⚠️ **الكمية غير كافية!** المتوفر في {cat}: {len(stock_list)}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return

        DB["stats"]["last_order_id"] = DB["stats"].get("last_order_id", 0) + 1
        order_id = DB["stats"]["last_order_id"]
        
        pulled = []
        for _ in range(count):
            code = DB["stock"][cat].pop(0)
            pulled.append(code)
            DB.setdefault("codes_map", {})[code] = {
                "name": user_data["name"], 
                "id": user_id, 
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "order_id": order_id
            }
        
        DB.setdefault("orders", {})[str(order_id)] = {
            "type": f"PUBG Stock ({cat} UC)",
            "user": user_data["name"],
            "user_id": user_id,
            "items": pulled,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        user_data["history"].append(f"📦 طلب #{order_id} ({len(pulled)} كود)")
        user_data["stats"]["stock"] += len(pulled)
        log_activity(user_id, f"سحب {len(pulled)} كود من فئة {cat}")
        save_db_changes()
        
        # التنبيه في حال انخفاض المخزون
        remaining = len(DB["stock"][cat])
        if remaining < 4:
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ **تنبيه:** مخزون فئة **{cat} UC** أوشك على النفاذ! المتبقي: {remaining}")
            except: pass

        msg = "\n".join([f"🎮 <code>{c}</code>" for c in pulled])
        await query.edit_message_text(f"✅ **تم سحب {cat} UC بنجاح (طلب #{order_id}):**\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=success_pull_keyboard(data))
        return

    # 3. سحب API
    if data == "pull_api":
        if not user_data["tokens"]:
            await query.edit_message_text("⚠️ **لا يوجد توكنات!** أضف توكن أولاً.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return
        
        await query.edit_message_text("⏳ **جاري الاتصال بالسيرفر...**", parse_mode=ParseMode.MARKDOWN)
        
        DB["stats"]["last_order_id"] = DB["stats"].get("last_order_id", 0) + 1
        order_id = DB["stats"]["last_order_id"]

        accs = []
        tokens_to_remove = []
        
        for t in list(user_data["tokens"]):
            try:
                r = requests.post(f"{API_BASE_URL}/api/redeem-bulk", json={"token":t, "product":PRODUCT_ID, "qty":user_data["max"]}, timeout=15).json()
                if r.get("success"):
                    for a in r["accounts"]:
                        # تنسيق النسخ (ايميل في سطر وباسورد في سطر)
                        acc_str = f"📧 `{a['email']}`\n🔑 `{a['password']}`"
                        accs.append(acc_str)
                    
                    user_data["stats"]["api"] += len(r["accounts"])
                    log_activity(user_id, f"سحب API (طلب #{order_id} - عدد {len(r['accounts'])})")
                    break
                elif "Invalid" in r.get("message", ""): 
                    tokens_to_remove.append(t)
            except Exception as e:
                logger.error(f"API Error: {e}")
                continue
        
        for t in tokens_to_remove:
            if t in user_data["tokens"]: user_data["tokens"].remove(t)
        
        if accs:
            DB.setdefault("orders", {})[str(order_id)] = {
                "type": "API Pull",
                "user": user_data["name"],
                "user_id": user_id,
                "items": accs,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            user_data["history"].append(f"🚀 طلب #{order_id} ({len(accs)} حساب)")
            save_db_changes()
            
            display_txt = "\n━━━━━━━━━━━━\n".join(accs)
            await query.edit_message_text(f"✅ **تم السحب (طلب #{order_id}):**\n\n{display_txt}", parse_mode=ParseMode.MARKDOWN, reply_markup=success_pull_keyboard("pull_api"))
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
    
    elif state == "waiting_count":
        if txt.isdigit() and int(txt) > 0:
            DB["users"][uid]["max"] = int(txt)
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"✅ تم تعيين عدد السحب إلى: {txt}", reply_markup=back_btn())
        else:
            await update.message.reply_text("❌ يرجى إرسال رقم صحيح أكبر من 0.")

    elif state == "waiting_add_user_id" and uid == ADMIN_ID:
        if not txt.isdigit():
            await update.message.reply_text("❌ يجب إرسال الآيدي كأرقام فقط.", reply_markup=admin_users_back_btn())
            return
        new_uid = int(txt)
        if new_uid in DB["users"]:
            await update.message.reply_text("⚠️ هذا المستخدم موجود بالفعل!", reply_markup=admin_users_back_btn())
        else:
            context.user_data["new_user_id"] = new_uid
            role_buttons = [
                [InlineKeyboardButton("موظف 👤", callback_data="set_role_employee")],
                [InlineKeyboardButton("مستخدم عادي 🆕", callback_data="set_role_user")]
            ]
            await update.message.reply_text(f"👤 **اختر الرتبة:** `{new_uid}`", reply_markup=InlineKeyboardMarkup(role_buttons), parse_mode=ParseMode.MARKDOWN)

    elif state == "waiting_remove_user_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target_id = int(txt)
        if target_id == ADMIN_ID:
            await update.message.reply_text("⛔ لا يمكن حذف الأدمن.", reply_markup=admin_users_back_btn())
        elif target_id in DB["users"]:
            del DB["users"][target_id]
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"🗑 تم الحذف.", reply_markup=admin_users_back_btn())
        else:
            await update.message.reply_text("⚠️ غير موجود.", reply_markup=admin_users_back_btn())

    # تغيير الرتبة (Switch Role)
    elif state == "waiting_switch_role_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target_id = int(txt)
        if target_id == ADMIN_ID:
            await update.message.reply_text("⛔ الأدمن ثابت.", reply_markup=admin_users_back_btn())
        elif target_id in DB["users"]:
            current_role = DB["users"][target_id]["role"]
            new_role = "employee" if current_role == "user" else "user"
            DB["users"][target_id]["role"] = new_role
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"🔄 تم تغيير رتبة `{target_id}` إلى **{new_role}**.", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("⚠️ المستخدم غير موجود.", reply_markup=admin_users_back_btn())

    elif state == "waiting_user_logs_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target_id = int(txt)
        user = DB["users"].get(target_id)
        if not user:
            await update.message.reply_text("⚠️ غير موجود.", reply_markup=admin_users_back_btn())
        elif not user.get("logs"):
            await update.message.reply_text("📭 لا توجد سجلات.", reply_markup=admin_users_back_btn())
        else:
            logs_text = f"User Logs for: {user['name']} ({target_id})\nRole: {user['role']}\n-----------------------------\n"
            logs_text += "\n".join(user["logs"])
            file_stream = io.BytesIO(logs_text.encode('utf-8'))
            file_stream.name = f"logs_{target_id}.txt"
            await update.message.reply_document(document=file_stream, caption=f"📜 سجلات: {user['name']}", reply_markup=admin_users_back_btn())
        context.user_data.clear()

    elif state == "waiting_order_id":
        order_id = txt
        order_data = DB.get("orders", {}).get(order_id)
        if order_data:
            if order_data["user_id"] == uid or DB["users"][uid]["role"] == "admin":
                items_str = "\n".join([f"`{i}`" for i in order_data["items"]])
                msg = (f"📄 **طلب #{order_id}**\n📅 {order_data['date']}\n👤 {order_data['user']}\n📦 {order_data['type']}\n⬇️:\n{items_str}")
                await update.message.reply_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("⛔ ليس لك.", reply_markup=back_btn())
        else:
            await update.message.reply_text("❌ غير موجود.", reply_markup=back_btn())
        context.user_data.clear()

    elif state == "waiting_admin_order_search" and uid == ADMIN_ID:
        order_id = txt
        order_data = DB.get("orders", {}).get(order_id)
        if order_data:
             items_str = "\n".join([f"`{i}`" for i in order_data["items"]])
             msg = (f"📄 **تقرير طلب #{order_id}**\n📅 {order_data['date']}\n👤 {order_data['user']}\n⬇️:\n{items_str}")
             await update.message.reply_text(msg, reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        else:
             await update.message.reply_text("❌ غير موجود.", reply_markup=admin_back_btn())
        context.user_data.clear()

    elif state == "waiting_reverse_code" and uid == ADMIN_ID:
        res = DB.get("codes_map", {}).get(txt)
        if res:
            await update.message.reply_text(f"🔍 **وجدته:**\n📝 `{txt}`\n👤 {res['name']}\n🆔 `{res['id']}`\n📅 {res['time']}\n📦 طلب #{res.get('order_id')}", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ غير موجود.", reply_markup=admin_back_btn())
        context.user_data.clear()

    elif state == "adding_stock_manual" and uid == ADMIN_ID:
        lines = txt.splitlines()
        new_items = [c.strip() for c in lines if c.strip()]
        cat = context.user_data.get("target_cat")
        
        if not cat: return
        
        # فحص التكرار (الشامل)
        all_stock = []
        for c_list in DB["stock"].values(): all_stock.extend(c_list)
        
        duplicates = [c for c in new_items if c in all_stock or c in DB.get("codes_map", {})]
        unique = [c for c in new_items if c not in duplicates]
        
        if duplicates:
            context.user_data["pending_stock"] = {"unique": unique, "dupes": duplicates}
            btns = [
                [InlineKeyboardButton(f"✅ الكل ({len(new_items)})", callback_data="confirm_add_all")],
                [InlineKeyboardButton(f"🚫 الجديد ({len(unique)})", callback_data="confirm_add_unique")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")]
            ]
            await update.message.reply_text(f"⚠️ مكرر: {len(duplicates)}\nجديد: {len(unique)}", reply_markup=InlineKeyboardMarkup(btns))
        else:
            DB["stock"][cat].extend(unique)
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"📦 تم إضافة {len(unique)} كود لفئة {cat}.", reply_markup=admin_back_btn())

# ====== 📂 معالج الملفات ======
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    
    if uid == ADMIN_ID and state == "admin_uploading_file":
        doc = update.message.document
        if not doc.file_name.endswith(".txt"):
            await update.message.reply_text("❌ فقط .txt", reply_markup=admin_back_btn())
            return
        file = await doc.get_file()
        content = await file.download_as_bytearray()
        decoded_text = content.decode("utf-8", errors="ignore")
        lines = decoded_text.splitlines()
        new_items = [c.strip() for c in lines if c.strip()]
        cat = context.user_data.get("target_cat")
        
        if not cat: return

        # فحص التكرار
        all_stock = []
        for c_list in DB["stock"].values(): all_stock.extend(c_list)

        duplicates = [c for c in new_items if c in all_stock or c in DB.get("codes_map", {})]
        unique = [c for c in new_items if c not in duplicates]
        
        if duplicates:
            context.user_data["pending_stock"] = {"unique": unique, "dupes": duplicates}
            btns = [
                [InlineKeyboardButton(f"✅ الكل ({len(new_items)})", callback_data="confirm_add_all")],
                [InlineKeyboardButton(f"🚫 الجديد ({len(unique)})", callback_data="confirm_add_unique")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")]
            ]
            await update.message.reply_text(f"⚠️ مكرر: {len(duplicates)}\nجديد: {len(unique)}", reply_markup=InlineKeyboardMarkup(btns))
        else:
            DB["stock"][cat].extend(unique)
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"📂 تم استيراد {len(unique)} كود لفئة {cat}.", reply_markup=admin_back_btn())

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
