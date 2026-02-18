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
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = "8577787177:AAH-p_2EVtcgff_ML8Rc0jGrJ2OiV-lExTY"
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"

# إعدادات جوجل درايف
DRIVE_CREDENTIALS_FILE = "credentials.json"
FOLDER_ID = "1Y-rECgcPmzLw8UQ2NW-wWr6Y_KHlfoLY" 

# ✅ الآيدي الثابت للملف (لضمان الحفظ وعدم التكرار)
DB_FILE_ID = "1xfU3GMswuvbWrnY8fybQxTU5_jDC_jjL" 

# ====== ☁️ دوال Google Drive (تعديل مباشر) ======
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
        "orders": {}, 
        "settings": {"maintenance": False},
        "stats": {"total_api": 0, "total_stock": 0, "last_order_id": 0},
        "codes_map": {}
    }
    
    if not service: return default_db

    try:
        logger.info(f"📥 جاري تحميل البيانات من الملف ID: {DB_FILE_ID}")
        # استخدام الآيدي مباشرة بدون بحث
        request = service.files().get_media(fileId=DB_FILE_ID)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        fh.seek(0)
        # التعامل مع ملف فارغ
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            data = default_db
        
        if "users" in data:
            data["users"] = {int(k): v for k, v in data["users"].items()}
        
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

        # تحديث الملف مباشرة باستخدام الآيدي (لن يحاول الإنشاء)
        service.files().update(fileId=DB_FILE_ID, media_body=media).execute()
        # logger.info("✅ تم تحديث الملف في جوجل درايف.") 
            
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
def home(): return "✅ Bot Online & Ready (Direct ID Mode)!", 200
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
        InlineKeyboardButton("🔍 كشف طلب (ID)", callback_data="check_order_id"),
        InlineKeyboardButton("📂 أرشيفي", callback_data="my_history")
    ])
    
    buttons.append([InlineKeyboardButton("❓ مساعدة", callback_data="help_menu")])

    if role == "admin":
        buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons)

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📦 إدارة المخزن", callback_data="admin_stock_menu")],
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
        [InlineKeyboardButton("📜 سجلات مستخدم (Logs)", callback_data="admin_get_user_logs_btn")],
        [InlineKeyboardButton("📋 عرض القائمة", callback_data="admin_list_users_btn")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
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
def admin_users_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للمستخدمين", callback_data="admin_users_menu")]])

# ====== 🚀 Handlers ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
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
    
    if user_id not in DB["users"] and user_id == ADMIN_ID:
        DB["users"][user_id] = {"role":"admin", "tokens":[], "max":1, "history":[], "logs":[], "stats":{"api":0,"stock":0}, "name":"Admin"}
        save_db_changes()
    
    if user_id not in DB["users"]: return
    user_data = DB["users"][user_id]
    role = user_data.get("role", "user")

    if DB["settings"].get("maintenance") and role != "admin":
        await query.edit_message_text("⚠️ **الصيانة جارية حالياً...**", reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        return

    # --- التنقلات (تم إضافة تفريغ الحالة لإصلاح الأزرار) ---
    if data == "back_home":
        context.user_data.clear() # ✅ إصلاح التعليق
        await query.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard(role))
        return
        
    if data == "admin_panel" and role == "admin":
        context.user_data.clear() # ✅ إصلاح التعليق
        status = "🔴 مفعل" if DB['settings']['maintenance'] else "🟢 معطل"
        stock_len = len(DB["stock"])
        await query.edit_message_text(f"🛠 **لوحة الأدمن**\n📦 المخزن: {stock_len}\n🛠 الصيانة: {status}", reply_markup=admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- إدارة المستخدمين ---
    if data == "admin_users_menu" and role == "admin":
        context.user_data.clear() # ✅ إصلاح هام: زر الرجوع سيعمل الآن
        await query.edit_message_text(f"👥 **إدارة المستخدمين**\nعدد المستخدمين: {len(DB['users'])}", reply_markup=admin_users_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_add_user_btn" and role == "admin":
        context.user_data["state"] = "waiting_add_user_id"
        await query.edit_message_text("✍️ **أرسل الآيدي (ID) الخاص بالشخص:**", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_remove_user_btn" and role == "admin":
        context.user_data["state"] = "waiting_remove_user_id"
        await query.edit_message_text("🗑 **أرسل الآيدي (ID) المراد حذفه:**", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # طلب سجلات مستخدم معين
    if data == "admin_get_user_logs_btn" and role == "admin":
        context.user_data["state"] = "waiting_user_logs_id"
        await query.edit_message_text("📜 **أرسل الآيدي (ID) لاستخراج سجلاته:**", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("set_role_") and role == "admin":
        new_uid = context.user_data.get("new_user_id")
        if not new_uid:
            await query.edit_message_text("❌ حدث خطأ، يرجى إعادة المحاولة.", reply_markup=admin_users_back_btn())
            return
            
        selected_role = "employee" if data == "set_role_employee" else "user"
        
        DB["users"][new_uid] = {
            "role": selected_role, 
            "name": "User", "tokens": [], "max": 1, "history": [], "logs": [], "stats": {"api":0,"stock":0}
        }
        save_db_changes()
        context.user_data.clear()
        role_txt = "موظف (صلاحية المخزن)" if selected_role == "employee" else "مستخدم عادي"
        await query.edit_message_text(f"✅ تم إضافة المستخدم `{new_uid}` برتبة **{role_txt}**.", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_list_users_btn" and role == "admin":
        msg = f"👥 **قائمة المستخدمين ({len(DB['users'])})**:\n\n"
        count = 0
        for uid, u in list(DB["users"].items())[-20:]:
             role_icon = "👮‍♂️" if u['role'] == "admin" else "👤" if u['role'] == "employee" else "🆕"
             msg += f"{role_icon} `{uid}` | {u.get('name', 'بدون اسم')}\n"
             count += 1
        if len(DB["users"]) > 20: msg += "\n⚠️ (يتم عرض آخر 20 فقط)"
        await query.edit_message_text(msg, reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- إدارة المخزن ---
    if data == "admin_stock_menu" and role == "admin":
        context.user_data.clear() # ✅ إصلاح التعليق
        await query.edit_message_text(f"📦 **إدارة المخزن**\nالعدد الحالي: {len(DB['stock'])}", reply_markup=stock_manage_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "admin_upload_stock_file" and role == "admin":
        context.user_data["state"] = "admin_uploading_file"
        await query.edit_message_text("📂 **أرسل ملف .txt يحتوي على الأكواد:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return
        
    if data == "admin_add_stock_text" and role == "admin":
        context.user_data["state"] = "adding_stock_manual"
        await query.edit_message_text("✍️ **أرسل الأكواد للإضافة:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # معالجة تكرار الأكواد
    if data == "confirm_add_all" and role == "admin":
        pending = context.user_data.get("pending_stock")
        if not pending: return
        DB["stock"].extend(pending["unique"])
        DB["stock"].extend(pending["dupes"])
        save_db_changes()
        total = len(pending["unique"]) + len(pending["dupes"])
        context.user_data.clear()
        await query.edit_message_text(f"✅ تم إضافة الكل ({total} كود) بما في ذلك المكرر.", reply_markup=admin_back_btn())
        return

    if data == "confirm_add_unique" and role == "admin":
        pending = context.user_data.get("pending_stock")
        if not pending: return
        DB["stock"].extend(pending["unique"])
        save_db_changes()
        context.user_data.clear()
        await query.edit_message_text(f"✅ تم إضافة {len(pending['unique'])} كود جديد فقط.", reply_markup=admin_back_btn())
        return
        
    if data == "cancel_add_stock" and role == "admin":
        context.user_data.clear()
        await query.edit_message_text("❌ تم إلغاء عملية الإضافة.", reply_markup=admin_back_btn())
        return

    if data == "admin_clear_stock" and role == "admin":
        DB["stock"] = []
        save_db_changes()
        await query.edit_message_text("🗑 **تم تصفير المخزن بنجاح.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- القوائم العامة ---
    if data == "help_menu":
        msg = "❓ **المساعدة:**\n1️⃣ أضف توكن -> سحب API.\n2️⃣ موظف -> سحب مخزن (ببجي).\n3️⃣ رقم الطلب: استخدمه لاسترجاع الكود."
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
        await query.edit_message_text("🔢 **أرسل الرقم الجديد (للسحب في المرة الواحدة):**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
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
        await query.edit_message_text("📝 **أرسل التوكنات (كل توكن في سطر):**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "check_order_id":
        context.user_data["state"] = "waiting_order_id"
        await query.edit_message_text("🔍 **أرسل رقم الطلب (ID) للكشف عن محتواه:**\n(مثال: 1, 2, 5...)", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- أدوات الأدمن الأخرى ---
    if data == "toggle_maintenance" and role == "admin":
        DB['settings']['maintenance'] = not DB['settings']['maintenance']
        save_db_changes()
        status = "🔴 مفعل" if DB['settings']['maintenance'] else "🟢 معطل"
        await query.edit_message_text(f"🛠 **لوحة الأدمن**\n📦 المخزن: {len(DB['stock'])}\n🛠 الصيانة: {status}", reply_markup=admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_get_logs" and role == "admin":
        await query.edit_message_text("⏳ **جاري جلب السجلات...**", parse_mode=ParseMode.MARKDOWN)
        all_logs = []
        for uid, u in DB["users"].items():
            if u.get("logs"):
                all_logs.append(f"--- 👤 {u['name']} ({uid}) ---")
                all_logs.extend(u["logs"][-5:])
        
        if not all_logs:
            await query.edit_message_text("📭 لا توجد سجلات نشاط حديثة.", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        else:
            report = "\n".join(all_logs)
            if len(report) > 4000: report = report[:4000] + "\n..."
            await query.edit_message_text(f"📝 **ملخص النشاط:**\n\n{report}", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "admin_reverse_search" and role == "admin":
        context.user_data["state"] = "waiting_reverse_code"
        await query.edit_message_text("🔍 **أرسل الكود لمعرفة من قام بسحبه:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_search_order" and role == "admin":
        context.user_data["state"] = "waiting_admin_order_search"
        await query.edit_message_text("📄 **أرسل رقم الطلب لعرض تفاصيله الكاملة:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # ====== عمليات السحب ======
    
    # 1. سحب ببجي
    if data == "pull_stock":
        if role not in ["admin", "employee"]: return
        if not DB["stock"]:
            await query.edit_message_text("⚠️ **المخزن فارغ!**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return
        
        count = user_data.get("max", 1)
        if len(DB["stock"]) < count:
            await query.edit_message_text(f"⚠️ **الكمية غير كافية!** المتوفر: {len(DB['stock'])}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return

        DB["stats"]["last_order_id"] = DB["stats"].get("last_order_id", 0) + 1
        order_id = DB["stats"]["last_order_id"]
        
        pulled = []
        for _ in range(count):
            code = DB["stock"].pop(0)
            pulled.append(code)
            DB.setdefault("codes_map", {})[code] = {
                "name": user_data["name"], 
                "id": user_id, 
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "order_id": order_id
            }
        
        DB.setdefault("orders", {})[str(order_id)] = {
            "type": "PUBG Stock",
            "user": user_data["name"],
            "user_id": user_id,
            "items": pulled,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        user_data["history"].append(f"📦 طلب #{order_id} ({len(pulled)} كود)")
        user_data["stats"]["stock"] += len(pulled)
        log_activity(user_id, f"سحب ببجي (طلب #{order_id} - عدد {len(pulled)})")
        save_db_changes()
        
        msg = "\n".join([f"🎮 <code>{c}</code>" for c in pulled])
        await query.edit_message_text(f"✅ **تم السحب بنجاح (طلب #{order_id}):**\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=back_btn())
        return

    # 2. سحب API
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
                        acc_str = f"📧 {a['email']} : {a['password']}"
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
            
            display_txt = "\n\n".join(accs)
            await query.edit_message_text(f"✅ **تم السحب (طلب #{order_id}):**\n\n`{display_txt}`", parse_mode=ParseMode.MARKDOWN, reply_markup=back_btn())
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
                [InlineKeyboardButton("موظف 👤 (يفتح المخزن)", callback_data="set_role_employee")],
                [InlineKeyboardButton("مستخدم عادي 🆕 (بدون مخزن)", callback_data="set_role_user")]
            ]
            await update.message.reply_text(
                f"👤 **اختر رتبة المستخدم:** `{new_uid}`",
                reply_markup=InlineKeyboardMarkup(role_buttons),
                parse_mode=ParseMode.MARKDOWN
            )

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

    # استخراج سجلات مستخدم كملف نصي
    elif state == "waiting_user_logs_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target_id = int(txt)
        user = DB["users"].get(target_id)
        
        if not user:
            await update.message.reply_text("⚠️ هذا المستخدم غير موجود.", reply_markup=admin_users_back_btn())
        elif not user.get("logs"):
            await update.message.reply_text("📭 لا توجد سجلات لهذا المستخدم.", reply_markup=admin_users_back_btn())
        else:
            logs_text = f"User Logs for: {user['name']} ({target_id})\nRole: {user['role']}\n-----------------------------\n"
            logs_text += "\n".join(user["logs"])
            
            file_stream = io.BytesIO(logs_text.encode('utf-8'))
            file_stream.name = f"logs_{target_id}.txt"
            
            await update.message.reply_document(document=file_stream, caption=f"📜 سجلات المستخدم: {user['name']}", reply_markup=admin_users_back_btn())
        context.user_data.clear()

    elif state == "waiting_order_id":
        order_id = txt
        order_data = DB.get("orders", {}).get(order_id)
        if order_data:
            if order_data["user_id"] == uid or DB["users"][uid]["role"] == "admin":
                items_str = "\n".join([f"`{i}`" for i in order_data["items"]])
                msg = (f"📄 **تفاصيل الطلب #{order_id}**\n"
                       f"📅 التاريخ: {order_data['date']}\n"
                       f"👤 المستخدم: {order_data['user']}\n"
                       f"📦 النوع: {order_data['type']}\n"
                       f"⬇️ **المحتوى:**\n{items_str}")
                await update.message.reply_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("⛔ هذا الطلب لا يخصك.", reply_markup=back_btn())
        else:
            await update.message.reply_text("❌ رقم الطلب غير موجود.", reply_markup=back_btn())
        context.user_data.clear()

    elif state == "waiting_admin_order_search" and uid == ADMIN_ID:
        order_id = txt
        order_data = DB.get("orders", {}).get(order_id)
        if order_data:
             items_str = "\n".join([f"`{i}`" for i in order_data["items"]])
             msg = (f"📄 **تقرير الطلب #{order_id}**\n"
                    f"📅 التاريخ: {order_data['date']}\n"
                    f"👤 المستخدم: {order_data['user']} (ID: `{order_data['user_id']}`)\n"
                    f"⬇️ **المحتوى المسحوب:**\n{items_str}")
             await update.message.reply_text(msg, reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        else:
             await update.message.reply_text("❌ لم يتم العثور على طلب بهذا الرقم.", reply_markup=admin_back_btn())
        context.user_data.clear()

    elif state == "waiting_reverse_code" and uid == ADMIN_ID:
        res = DB.get("codes_map", {}).get(txt)
        if res:
            order_info = f"\n📦 طلب رقم: #{res.get('order_id', 'N/A')}"
            await update.message.reply_text(
                f"🔍 **نتائج البحث:**\n📝 الكود: `{txt}`\n👤 سحبه: {res['name']}\n🆔 ID: `{res['id']}`\n📅 الوقت: {res['time']}{order_info}",
                reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ غير موجود.", reply_markup=admin_back_btn())
        context.user_data.clear()

    elif state == "adding_stock_manual" and uid == ADMIN_ID:
        lines = txt.splitlines()
        new_items = [c.strip() for c in lines if c.strip()]
        
        duplicates = [c for c in new_items if c in DB["stock"] or c in DB.get("codes_map", {})]
        unique = [c for c in new_items if c not in duplicates]
        
        if duplicates:
            context.user_data["pending_stock"] = {"unique": unique, "dupes": duplicates}
            btns = [
                [InlineKeyboardButton(f"✅ إضافة الكل ({len(new_items)})", callback_data="confirm_add_all")],
                [InlineKeyboardButton(f"🚫 إضافة الجديد فقط ({len(unique)})", callback_data="confirm_add_unique")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")]
            ]
            await update.message.reply_text(
                f"⚠️ **تنبيه:** تم العثور على {len(duplicates)} كود مكرر.\nماذا تريد أن تفعل؟",
                reply_markup=InlineKeyboardMarkup(btns),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            DB["stock"].extend(unique)
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"📦 تم إضافة {len(unique)} كود جديد بنجاح.", reply_markup=admin_back_btn())

# ====== 📂 معالج الملفات ======
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    
    if uid == ADMIN_ID and state == "admin_uploading_file":
        doc = update.message.document
        if not doc.file_name.endswith(".txt"):
            await update.message.reply_text("❌ الملف يجب أن يكون .txt", reply_markup=admin_back_btn())
            return
        file = await doc.get_file()
        content = await file.download_as_bytearray()
        decoded_text = content.decode("utf-8", errors="ignore")
        
        lines = decoded_text.splitlines()
        new_items = [c.strip() for c in lines if c.strip()]
        
        duplicates = [c for c in new_items if c in DB["stock"] or c in DB.get("codes_map", {})]
        unique = [c for c in new_items if c not in duplicates]
        
        if duplicates:
            context.user_data["pending_stock"] = {"unique": unique, "dupes": duplicates}
            btns = [
                [InlineKeyboardButton(f"✅ إضافة الكل ({len(new_items)})", callback_data="confirm_add_all")],
                [InlineKeyboardButton(f"🚫 إضافة الجديد فقط ({len(unique)})", callback_data="confirm_add_unique")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")]
            ]
            await update.message.reply_text(
                f"⚠️ **تنبيه (من الملف):** تم العثور على {len(duplicates)} كود مكرر.\nاختر إجراء:",
                reply_markup=InlineKeyboardMarkup(btns),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            DB["stock"].extend(unique)
            save_db_changes()
            context.user_data.clear()
            await update.message.reply_text(f"📂 تم استيراد {len(unique)} كود من الملف.", reply_markup=admin_back_btn())

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
