import os
import logging
import asyncio
import traceback
from datetime import datetime, timedelta
import io
import threading
from flask import Flask
import httpx

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

# ====== 🗄️ إعدادات MongoDB ======
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["salehzon_db"]

# ====== 📝 إعداد اللوجز ======
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO, handlers=[logging.StreamHandler()])
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("SalehZonBot")

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"
UC_CATEGORIES = ["60", "325", "660", "1800", "3850", "8100"]

# ====== 🌐 سيرفر Flask ======
app_server = Flask(__name__)
@app_server.route('/')
def home(): return "✅ Saleh Zon Bot Online!", 200
def run_flask(): app_server.run(host="0.0.0.0", port=8080)

# ====== 💾 دوال مساعدة ======
async def get_user(user_id): 
    return await db.users.find_one({"_id": user_id})

async def log_activity(user_id, user_name, action):
    log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {action}"
    logger.info(f"📝 User: {user_id} | {action}")
    await db.users.update_one({"_id": user_id}, {"$push": {"logs": {"$each": [log_entry], "$slice": -500}}})

async def get_next_order_id():
    stat = await db.stats.find_one_and_update({"_id": "global_stats"}, {"$inc": {"last_order_id": 1}}, upsert=True, return_document=True)
    return stat["last_order_id"]

async def check_maintenance():
    settings = await db.settings.find_one({"_id": "config"})
    if not settings:
        await db.settings.insert_one({"_id": "config", "maintenance": False})
        return False
    return settings.get("maintenance", False)

# ====== 🚀 دالة السحب المخصصة للـ API ======
async def process_api_pull(uid, reply_func, user, qty, context):
    tokens = list(user.get("tokens", []))
    if not tokens:
        await reply_func("⚠️ **لا يوجد لديك توكنات!** أضف توكنات أولاً من القائمة الرئيسية.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    tokens_to_use = tokens[:qty]
    waiting_msg = await reply_func(f"⏳ **جاري السحب باستخدام {len(tokens_to_use)} توكن...**", parse_mode=ParseMode.MARKDOWN)
    
    accs = []
    used_tokens = []
    token_logs_updates = []
    
    async with httpx.AsyncClient() as client:
        tasks = []
        for t in tokens_to_use:
            req = client.post(f"{API_BASE_URL}/api/redeem-bulk", json={"token": t, "product": PRODUCT_ID, "qty": 1}, timeout=15.0)
            tasks.append((t, req))
        
        for t, req in tasks:
            used_tokens.append(t)
            short_t = f"{t[:8]}...{t[-4:]}"
            try:
                res = await req
                r = res.json()
                if r.get("success") and r.get("accounts"):
                    a = r["accounts"][0]
                    accs.append(f"📧 `{a['email']}`\n🔑 `{a['password']}`")
                    token_logs_updates.append(f"✅ نجاح | توكن {short_t} | سحب: {a['email']}")
                else:
                    err = r.get("message", "مجهول/بايظ")
                    token_logs_updates.append(f"❌ فشل | توكن {short_t} | السبب: {err}")
            except Exception as e:
                token_logs_updates.append(f"⚠️ خطأ | توكن {short_t} | خطأ في الاتصال بالسيرفر.")
                logger.error(f"API Error for token {t}: {e}")

    db_updates = {"$pull": {"tokens": {"$in": used_tokens}}}
    if token_logs_updates:
        db_updates["$push"] = {"token_logs": {"$each": token_logs_updates, "$slice": -500}}
    
    await db.users.update_one({"_id": uid}, db_updates)
    
    btns = [
        [InlineKeyboardButton(f"🔄 حساب آخر (العدد: {qty})", callback_data="pull_api_again")],
        [InlineKeyboardButton("✏️ تعديل العدد", callback_data="pull_api")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
    ]
    reply_markup = InlineKeyboardMarkup(btns)
    
    if accs:
        order_id = await get_next_order_id()
        await db.orders.insert_one({"_id": order_id, "type": "API Pull", "user": user["name"], "user_id": uid, "items": accs, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        await db.users.update_one({"_id": uid}, {"$push": {"history": f"🚀 طلب #{order_id}"}, "$inc": {"stats.api": len(accs)}})
        
        display_txt = "\n━━━━━━━━━━━━\n".join(accs)
        await waiting_msg.edit_text(f"✅ **تم السحب بنجاح (طلب #{order_id}):**\n\n{display_txt}\n\n📝 *(تم حذف التوكنات المستخدمة وحفظها في السجل)*", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    else:
        await waiting_msg.edit_text("❌ **فشل السحب من التوكنات.**\n*(تم حذف التوكنات التالفة وتسجيل السبب في سجل التوكنات)*", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

# ====== ⌨️ الكيبوردات ======
def get_main_keyboard(role):
    buttons = []
    if role in ["employee", "admin"]:
        buttons.append([
            InlineKeyboardButton("🎮 سحب كود (UC)", callback_data="pull_stock_menu"),
            InlineKeyboardButton("🎯 سحب آيديات للعمل", callback_data="pull_ids_task")
        ])
        buttons.append([
            InlineKeyboardButton("✅ تقفيل الآيديات المنجزة", callback_data="finish_ids_task"),
            InlineKeyboardButton("↩️ إرجاع طلب (15د)", callback_data="return_order")
        ])
    
    buttons.append([InlineKeyboardButton("🚀 سحب حسابات (API)", callback_data="pull_api")])
    buttons.append([InlineKeyboardButton("➕ إضافة توكن", callback_data="add_tokens"), InlineKeyboardButton("📋 توكناتي", callback_data="view_my_tokens")])
    
    buttons.append([
        InlineKeyboardButton("💳 حسابي وإحصائياتي", callback_data="my_profile"), 
        InlineKeyboardButton("📂 أرشيفي", callback_data="my_history")
    ])
    
    if role == "admin": buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

async def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة الموظفين والمستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📦 إدارة المخزن", callback_data="admin_stock_menu"), InlineKeyboardButton("🎯 إدارة الآيديات", callback_data="admin_tasks_menu")],
        [InlineKeyboardButton("🔍 بحث عكسي (كود)", callback_data="admin_reverse_search"), InlineKeyboardButton("📄 بحث بطلب عام", callback_data="admin_search_order")],
        [InlineKeyboardButton("📝 سجلات النظام", callback_data="admin_get_logs"), InlineKeyboardButton("🛠 الصيانة", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("🏠 خروج", callback_data="back_home")]
    ])

def admin_tasks_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة آيديات جديدة", callback_data="admin_add_ids")],
        [InlineKeyboardButton("🗑 مسح الآيديات المعلقة", callback_data="admin_clear_pending_ids")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
    ])

def admin_users_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 بحث وتحكم فردي بالآيدي", callback_data="admin_search_manage_user")],
        [InlineKeyboardButton("➕ إضافة مستخدم", callback_data="admin_add_user_btn"), InlineKeyboardButton("🗑 حذف مستخدم", callback_data="admin_remove_user_btn")],
        [InlineKeyboardButton("📜 سجلات مستخدم", callback_data="admin_get_user_logs_btn"), InlineKeyboardButton("📋 عرض القائمة", callback_data="admin_list_users_btn")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
    ])

def stock_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 رفع ملف (.txt)", callback_data="admin_choose_cat_file"), InlineKeyboardButton("✍️ إضافة يدوي", callback_data="admin_choose_cat_manual")],
        [InlineKeyboardButton("🗑 تصفير فئة محددة", callback_data="admin_choose_cat_clear")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
    ])

async def categories_keyboard(action_prefix):
    buttons = []
    row = []
    for cat in UC_CATEGORIES:
        count = await db.stock.count_documents({"category": cat})
        icon = "🔴" if count == 0 else ("🟡" if count < 5 else "🟢")
        row.append(InlineKeyboardButton(f"{icon} {cat} ({count})", callback_data=f"{action_prefix}_{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    back_cb = "admin_stock_menu" if "admin" in action_prefix else "back_home"
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=back_cb)])
    return InlineKeyboardMarkup(buttons)

def success_pull_keyboard(callback_data):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 طلب آخر", callback_data=callback_data)],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]])
def admin_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]])
def admin_users_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للمستخدمين", callback_data="admin_users_menu")]])

# ====== 🚨 رادار التقاط الأخطاء المتقدم (Error Handler) ======
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("❌ حدث خطأ برمجي:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    error_msg = f"🚨 **تنبيه عاجل للنظام!**\n\nحدث خطأ برمجي غير متوقع في البوت. تم حفظ اللوجز في الملف المرفق لتسهيل الحل."
    log_file = io.BytesIO(tb_string.encode('utf-8'))
    log_file.name = f"Crash_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        await context.bot.send_document(chat_id=ADMIN_ID, document=log_file, caption=error_msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"فشل إرسال ملف الخطأ: {e}")

# ====== 🚀 Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    user = await get_user(user_id)
    if user_id == ADMIN_ID and not user:
        new_admin = {"_id": user_id, "role": "admin", "name": name, "tokens": [], "history": [], "logs": [], "stats": {"api": 0, "stock": 0, "ids_done": 0}}
        await db.users.insert_one(new_admin)
        user = new_admin

    if not user: return await update.message.reply_text("⛔ غير مسجل.")
    if user.get("name") != name: await db.users.update_one({"_id": user_id}, {"$set": {"name": name}})

    await log_activity(user_id, name, "أرسل أمر /start")
    
    role = user.get("role", "user")
    maint_msg = "\n⚠️ **النظام في وضع الصيانة**" if await check_maintenance() else ""
    await update.message.reply_text(f"👋 أهلاً {name}\n🔹 الرتبة: {role}{maint_msg}", reply_markup=get_main_keyboard(role), parse_mode=ParseMode.MARKDOWN)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()
    
    user = await get_user(uid)
    if not user: return
    role = user.get("role", "user")

    await log_activity(uid, user["name"], f"🔘 ضغط على زر: {data}")

    if await check_maintenance() and role != "admin": return await query.edit_message_text("⚠️ **الصيانة جارية...**")
    
    if data == "back_home":
        context.user_data.clear()
        return await query.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard(role))

    if data == "my_profile":
        t_count = len(user.get("tokens", []))
        st = user.get("stats", {"api": 0, "stock": 0, "ids_done": 0})
        msg = f"💳 **حسابك:**\n👤 الاسم: {user.get('name')}\n🎖 الرتبة: {role}\n🔑 توكنات نشطة: {t_count}\n\n🛒 **السحوبات والمهام:**\n🎮 أكواد مسحوبة: {st.get('stock',0)}\n🚀 حسابات API: {st.get('api',0)}\n✅ آيديات تم تقفيلها: {st.get('ids_done',0)}"
        return await query.edit_message_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "view_my_tokens":
        tokens = user.get("tokens", [])
        if not tokens: return await query.edit_message_text("📭 لا يوجد لديك توكنات نشطة.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        txt = "\n".join([f"🔑 `{t[:8]}...{t[-4:]}`" for t in tokens])
        btns = [
            [InlineKeyboardButton("📜 سجل التوكنات (الهيستوري)", callback_data="view_token_logs")],
            [InlineKeyboardButton("🗑 حذف جميع توكناتي", callback_data="clear_tokens")], 
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
        ]
        return await query.edit_message_text(f"📋 **توكناتك الحالية ({len(tokens)}):**\n\n{txt}", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)

    if data == "view_token_logs":
        logs = user.get("token_logs", [])
        if not logs:
            return await query.edit_message_text("📭 لا يوجد سجل للتوكنات حتى الآن.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع لتوكناتي", callback_data="view_my_tokens")]]), parse_mode=ParseMode.MARKDOWN)
        txt = "\n".join(logs[-30:])
        return await query.edit_message_text(f"📜 **سجل نشاط التوكنات:**\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع لتوكناتي", callback_data="view_my_tokens")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "clear_tokens":
        await db.users.update_one({"_id": uid}, {"$set": {"tokens": []}})
        return await query.edit_message_text("🗑 **تم حذف جميع التوكنات.**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "add_tokens":
        context.user_data["state"] = "waiting_tokens"
        return await query.edit_message_text("📝 **أرسل التوكنات:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "my_history":
        hist = user.get("history", [])
        txt = "\n".join(hist[-10:]) if hist else "📂 أرشيفك فارغ."
        btns = [
            [InlineKeyboardButton("🔍 بحث برقم الطلب (Order ID)", callback_data="check_order_id")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
        ]
        return await query.edit_message_text(f"📂 **آخر 10 عمليات:**\n\n{txt}", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)

    if data == "check_order_id":
        context.user_data["state"] = "waiting_order_id"
        return await query.edit_message_text("🔍 **أرسل رقم الطلب المراد كشفه:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للأرشيف", callback_data="my_history")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "pull_ids_task" and role in ["admin", "employee"]:
        pending = await db.player_ids.count_documents({"status": "pending"})
        if pending == 0: return await query.edit_message_text("📭 لا يوجد آيديات معلقة للعمل حالياً.", reply_markup=back_btn())
        current_tasks = await db.player_ids.count_documents({"status": "processing", "assigned_to": uid})
        if current_tasks > 0:
            return await query.edit_message_text(f"⚠️ لديك {current_tasks} آيديات قيد العمل!\nيرجى تقفيلهم أولاً من القائمة الرئيسية.", reply_markup=back_btn())
        context.user_data["state"] = "waiting_pull_ids_count"
        return await query.edit_message_text(f"🎯 **سحب مهام شحن**\nالآيديات المتاحة: {pending}\n\n🔢 **أرسل عدد الآيديات التي تريد سحبها للعمل عليها الآن:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "finish_ids_task" and role in ["admin", "employee"]:
        tasks = await db.player_ids.find({"status": "processing", "assigned_to": uid}).to_list(length=None)
        if not tasks: return await query.edit_message_text("✅ ليس لديك أي آيديات معلقة للتقفيل.", reply_markup=back_btn())
        await db.player_ids.update_many({"status": "processing", "assigned_to": uid}, {"$set": {"status": "done", "done_at": datetime.now()}})
        await db.users.update_one({"_id": uid}, {"$inc": {"stats.ids_done": len(tasks)}})
        return await query.edit_message_text(f"✅ **عاش!** تم تقفيل {len(tasks)} آيديات وإضافتهم لإحصائياتك.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "return_order" and role in ["admin", "employee"]:
        context.user_data["state"] = "waiting_return_order_id"
        return await query.edit_message_text("↩️ **نظام المرتجعات السريع**\n\nأرسل **رقم الطلب (Order ID)** الذي تريد إرجاعه:\n*(ملاحظة: الإرجاع متاح لأكواد ببجي فقط، وخلال 15 دقيقة من السحب)*", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "pull_stock_menu" and role in ["admin", "employee"]: return await query.edit_message_text("🎮 **اختر الفئة للسحب:**", reply_markup=await categories_keyboard("pull_cat"))
    
    if data.startswith("pull_cat_") and role in ["admin", "employee"]:
        cat = data.split("_")[-1]
        context.user_data["state"] = "waiting_stock_count"
        context.user_data["target_pull_cat"] = cat
        return await query.edit_message_text(f"🔢 **أرسل العدد لـ {cat} UC:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "pull_api":
        tokens = user.get("tokens", [])
        if not tokens: return await query.edit_message_text("⚠️ **لا يوجد توكنات!** أضف توكن أولاً من القائمة الرئيسية.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        context.user_data["state"] = "waiting_api_count"
        return await query.edit_message_text("🔢 **أرسل عدد الحسابات التي تريد سحبها الآن:**\n*(سيتم استخدام توكن واحد لكل حساب)*", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "pull_api_again":
        qty = context.user_data.get("last_api_count", 1)
        await process_api_pull(uid, query.message.reply_text, user, qty, context)
        return

    # ====== ⚙️ لوحة الأدمن ======
    if data == "admin_panel" and role == "admin":
        st = await db.stock.count_documents({})
        pending_ids = await db.player_ids.count_documents({"status": "pending"})
        return await query.edit_message_text(f"🛠 **الأدمن**\n📦 المخزن: {st}\n🎯 آيديات معلقة: {pending_ids}", reply_markup=await admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
    
    if data == "admin_tasks_menu" and role == "admin":
        pending = await db.player_ids.count_documents({"status": "pending"})
        done = await db.player_ids.count_documents({"status": "done"})
        return await query.edit_message_text(f"🎯 **إدارة الآيديات**\n⏳ معلق: {pending}\n✅ تم الانتهاء: {done}", reply_markup=admin_tasks_keyboard(), parse_mode=ParseMode.MARKDOWN)
        
    if data == "admin_add_ids" and role == "admin":
        context.user_data["state"] = "waiting_admin_add_ids"
        return await query.edit_message_text("✍️ **أرسل الآيديات (كل آيدي في سطر):**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "admin_clear_pending_ids" and role == "admin":
        await db.player_ids.delete_many({"status": "pending"})
        return await query.edit_message_text("🗑 **تم مسح جميع الآيديات المعلقة.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "admin_stock_menu" and role == "admin": return await query.edit_message_text("📦 **المخزن:**", reply_markup=stock_manage_keyboard())
    if data == "admin_choose_cat_manual" and role == "admin": return await query.edit_message_text("🔢 **اختر الفئة:**", reply_markup=await categories_keyboard("admin_add_manual"))
    if data == "admin_choose_cat_file" and role == "admin": return await query.edit_message_text("📂 **اختر الفئة لرفع الملف:**", reply_markup=await categories_keyboard("admin_add_file"))
    if data == "admin_choose_cat_clear" and role == "admin": return await query.edit_message_text("🗑 **اختر الفئة لتصفيرها:**", reply_markup=await categories_keyboard("admin_clear_cat"))

    if data.startswith("admin_add_manual_") and role == "admin":
        cat = data.split("_")[-1]
        context.user_data["state"] = "adding_stock_manual"
        context.user_data["target_cat"] = cat
        return await query.edit_message_text(f"✍️ **أرسل أكواد {cat} UC:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        
    if data.startswith("admin_add_file_") and role == "admin":
        cat = data.split("_")[-1]
        context.user_data["state"] = "admin_uploading_file"
        context.user_data["target_cat"] = cat
        return await query.edit_message_text(f"📂 **أرسل ملف .txt لفئة {cat} UC:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data.startswith("admin_clear_cat_") and role == "admin":
        cat = data.split("_")[-1]
        await db.stock.delete_many({"category": cat})
        return await query.edit_message_text(f"🗑 **تم تصفير فئة {cat} UC بنجاح.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "admin_clear_all_confirm" and role == "admin":
        await db.stock.delete_many({})
        return await query.edit_message_text("🗑 **تم تصفير جميع الفئات بنجاح.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data in ["confirm_add_unique"] and role == "admin":
        pending = context.user_data.get("pending_stock")
        cat = context.user_data.get("target_cat")
        if pending and cat:
            docs = [{"_id": c, "category": cat, "added_at": datetime.now()} for c in pending["unique"]]
            if docs: 
                try: await db.stock.insert_many(docs, ordered=False) 
                except: pass
        context.user_data.clear()
        return await query.edit_message_text(f"✅ تم إضافة الأكواد.", reply_markup=admin_back_btn())
        
    if data == "cancel_add_stock" and role == "admin":
        context.user_data.clear()
        return await query.edit_message_text("❌ تم الإلغاء.", reply_markup=admin_back_btn())

    if data == "admin_users_menu" and role == "admin":
        context.user_data.clear()
        c = await db.users.count_documents({})
        return await query.edit_message_text(f"👥 **إدارة المستخدمين والموظفين**\nالإجمالي: {c}", reply_markup=admin_users_keyboard(), parse_mode=ParseMode.MARKDOWN)

    if data in ["admin_add_user_btn", "admin_remove_user_btn", "admin_search_manage_user", "admin_get_user_logs_btn"] and role == "admin":
        states = {
            "admin_add_user_btn": ("waiting_add_user_id", "✍️ **أرسل الآيدي (ID) لإضافته:**"),
            "admin_remove_user_btn": ("waiting_remove_user_id", "🗑 **أرسل الآيدي (ID) لحذفه:**"),
            "admin_search_manage_user": ("waiting_manage_user_id", "🔍 **أرسل الآيدي (ID) للتحكم في حسابه:**"),
            "admin_get_user_logs_btn": ("waiting_user_logs_id", "📜 **أرسل الآيدي لاستخراج سجلاته:**")
        }
        context.user_data["state"] = states[data][0]
        return await query.edit_message_text(states[data][1], reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "admin_list_users_btn" and role == "admin":
        msg = "👥 **قائمة المستخدمين:**\n\n"
        async for u in db.users.find().sort("_id", -1).limit(20):
             ic = "👮‍♂️" if u['role'] == "admin" else "👤" if u['role'] == "employee" else "🆕"
             msg += f"{ic} `{u['_id']}` | {u.get('name', 'بدون اسم')}\n"
        return await query.edit_message_text(msg, reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data.startswith("manage_clear_tokens_") and role == "admin":
        tid = int(data.split("_")[-1])
        await db.users.update_one({"_id": tid}, {"$set": {"tokens": []}})
        return await query.answer("✅ تم تصفير التوكنات للمستخدم", show_alert=True)
        
    if data.startswith("manage_switch_role_") and role == "admin":
        tid = int(data.split("_")[-1])
        target = await get_user(tid)
        if target and target["_id"] != ADMIN_ID:
            nr = "employee" if target["role"] == "user" else "user"
            await db.users.update_one({"_id": tid}, {"$set": {"role": nr}})
            return await query.answer(f"✅ أصبحت رتبته: {nr}", show_alert=True)
        return await query.answer("❌ لا يمكن تغيير رتبة هذا الشخص", show_alert=True)
        
    if data.startswith("manage_clear_logs_") and role == "admin":
        tid = int(data.split("_")[-1])
        await db.users.update_one({"_id": tid}, {"$set": {"logs": [], "history": [], "token_logs": []}})
        return await query.answer("✅ تم مسح أرشيفه وسجلاته بالكامل", show_alert=True)

    if data.startswith("set_role_") and role == "admin":
        new_uid = context.user_data.get("new_user_id")
        if not new_uid: return
        r = "employee" if data == "set_role_employee" else "user"
        await db.users.insert_one({"_id": new_uid, "role": r, "name": "User", "tokens": [], "history": [], "logs": [], "token_logs": [], "stats": {"api":0,"stock":0,"ids_done":0}})
        context.user_data.clear()
        return await query.edit_message_text(f"✅ تم إضافة الحساب كرتبة **{r}**.", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "toggle_maintenance" and role == "admin":
        n = not is_maint
        await db.settings.update_one({"_id": "config"}, {"$set": {"maintenance": n}}, upsert=True)
        st = "🔴 مفعل" if n else "🟢 معطل"
        return await query.edit_message_text(f"🛠 **تم التغيير!**\n📦 وضع الصيانة الآن: {st}", reply_markup=await admin_keyboard(), parse_mode=ParseMode.MARKDOWN)

    if data == "admin_get_logs" and role == "admin":
        await query.edit_message_text("⏳ **جاري جلب السجلات...**", parse_mode=ParseMode.MARKDOWN)
        cursor = db.users.find({"logs": {"$exists": True, "$ne": []}}).limit(10)
        all_logs = []
        async for u in cursor:
            all_logs.append(f"--- 👤 {u.get('name')} ({u['_id']}) ---")
            all_logs.extend(u["logs"][-5:])
        
        if not all_logs: return await query.edit_message_text("📭 لا توجد سجلات.", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        rep = "\n".join(all_logs)
        if len(rep) > 4000: rep = rep[:4000] + "\n..."
        return await query.edit_message_text(f"📝 **ملخص النشاط:**\n\n{rep}", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data in ["admin_reverse_search", "admin_search_order"] and role == "admin":
        state = "waiting_reverse_code" if data == "admin_reverse_search" else "waiting_admin_order_search"
        msg = "🔍 **أرسل الكود:**" if data == "admin_reverse_search" else "📄 **أرسل رقم الطلب:**"
        context.user_data["state"] = state
        return await query.edit_message_text(msg, reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)

# ====== 📩 معالج الرسائل النصية ======
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    uid = update.effective_user.id
    txt = update.message.text.strip()
    state = context.user_data.get("state")
    
    user = await get_user(uid)
    if not user: return
    
    await log_activity(uid, user["name"], f"📝 أرسل نص: {txt[:30]}")
    
    if not state: return await update.message.reply_text("💡 يرجى اختيار عملية من القائمة أولاً.", reply_markup=back_btn())

    if state == "waiting_order_id":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للأرشيف", callback_data="my_history")]]))
        order = await db.orders.find_one({"_id": int(txt)})
        
        if order and (order["user_id"] == uid or user["role"] == "admin"):
            items_str = "\n".join([f"`{i}`" for i in order["items"]])
            res_msg = f"📄 **الطلب #{txt}**\n📅 {order['date']}\n⬇️ العناصر:\n{items_str}"
        else:
            res_msg = "❌ الطلب غير موجود أو يخص شخصاً آخر."
        
        btns = [
            [InlineKeyboardButton("🔍 بحث عن طلب آخر", callback_data="check_order_id")],
            [InlineKeyboardButton("📂 العودة للأرشيف", callback_data="my_history")]
        ]
        context.user_data.clear()
        return await update.message.reply_text(f"{res_msg}\n\n❓ **ماذا تريد أن تفعل الآن؟**", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)

    elif state == "waiting_return_order_id":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        order = await db.orders.find_one({"_id": int(txt)})
        
        if not order or (order["user_id"] != uid and user["role"] != "admin"):
            return await update.message.reply_text("❌ الطلب غير موجود أو لا تملك صلاحية.", reply_markup=back_btn())
        if "PUBG Stock" not in order["type"]:
            return await update.message.reply_text("❌ لا يمكن إرجاع هذا النوع من الطلبات.", reply_markup=back_btn())
            
        order_time = datetime.strptime(order['date'], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - order_time).total_seconds() > 900 and user["role"] != "admin":
            return await update.message.reply_text("⏳ **انتهت مهلة الإرجاع (15 دقيقة).**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            
        cat = order["type"].split("(")[1].split(" ")[0]
        codes_to_return = [{"_id": code, "category": cat, "added_at": datetime.now()} for code in order["items"]]
        
        await db.stock.insert_many(codes_to_return, ordered=False) 
        await db.codes_map.delete_many({"_id": {"$in": order["items"]}}) 
        await db.orders.delete_one({"_id": int(txt)}) 
        await db.users.update_one({"_id": uid}, {"$inc": {"stats.stock": -len(order["items"])}}) 
        
        context.user_data.clear()
        return await update.message.reply_text(f"✅ **تم إرجاع الطلب #{txt} للمخزن بنجاح!**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    elif state == "waiting_pull_ids_count" and user["role"] in ["admin", "employee"]:
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ رقم غير صحيح.", reply_markup=back_btn())
        qty = int(txt)
        pulled_ids = []
        for _ in range(qty):
            task = await db.player_ids.find_one_and_update({"status": "pending"}, {"$set": {"status": "processing", "assigned_to": uid, "pulled_at": datetime.now()}})
            if task: pulled_ids.append(task["_id"])
            else: break
            
        context.user_data.clear()
        if not pulled_ids: return await update.message.reply_text("❌ لا يوجد آيديات متاحة.", reply_markup=back_btn())
        
        ids_text = "\n".join([f"🎯 `{pid}`" for pid in pulled_ids])
        msg = f"✅ **تم الاستلام!**\nاشحن الآيديات التالية:\n\n{ids_text}\n\n⚠️ *اضغط 'تقفيل' بعد الانتهاء!*"
        return await update.message.reply_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    elif state == "waiting_admin_add_ids" and user["role"] == "admin":
        lines = [c.strip() for c in txt.splitlines() if c.strip()]
        if lines:
            docs = [{"_id": pid, "status": "pending", "assigned_to": None} for pid in lines]
            try: await db.player_ids.insert_many(docs, ordered=False)
            except: pass
        context.user_data.clear()
        return await update.message.reply_text(f"✅ تم إضافة {len(lines)} آيدي للمهام.", reply_markup=admin_back_btn())

    elif state == "waiting_stock_count":
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        count = int(txt)
        cat = context.user_data.get("target_pull_cat")
        context.user_data.clear() 
        
        if await db.stock.count_documents({"category": cat}) < count:
            return await update.message.reply_text("⚠️ الكمية غير كافية!", reply_markup=back_btn())

        order_id = await get_next_order_id()
        pulled = []
        for _ in range(count):
            c = await db.stock.find_one_and_delete({"category": cat})
            if c:
                pulled.append(c["_id"])
                await db.codes_map.insert_one({"_id": c["_id"], "name": user["name"], "user_id": uid, "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "order_id": order_id})

        if pulled:
            await db.orders.insert_one({"_id": order_id, "type": f"PUBG Stock ({cat} UC)", "user": user["name"], "user_id": uid, "items": pulled, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            await db.users.update_one({"_id": uid}, {"$push": {"history": f"📦 طلب #{order_id}"}, "$inc": {"stats.stock": len(pulled)}})
            
            msg = "\n".join([f"🎮 <code>{c}</code>" for c in pulled])
            return await update.message.reply_text(f"✅ **سحب {cat} UC (طلب #{order_id}):**\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=success_pull_keyboard(f"pull_cat_{cat}"))

    elif state == "waiting_api_count":
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        qty = int(txt)
        context.user_data.clear()
        context.user_data["last_api_count"] = qty
        
        await process_api_pull(uid, update.message.reply_text, user, qty, context)
        return

    elif state == "waiting_tokens":
        lines = [t.strip() for t in txt.splitlines() if t.strip()]
        if lines: await db.users.update_one({"_id": uid}, {"$addToSet": {"tokens": {"$each": lines}}})
        context.user_data.clear()
        return await update.message.reply_text(f"✅ تم إضافة التوكنات.", reply_markup=back_btn())

    elif state == "waiting_add_user_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        new_uid = int(txt)
        if await get_user(new_uid): return await update.message.reply_text("⚠️ هذا المستخدم موجود بالفعل!", reply_markup=admin_users_back_btn())
        context.user_data["new_user_id"] = new_uid
        btns = [[InlineKeyboardButton("موظف 👤", callback_data="set_role_employee")], [InlineKeyboardButton("مستخدم عادي 🆕", callback_data="set_role_user")]]
        return await update.message.reply_text(f"👤 **اختر الرتبة للآيدي:** `{new_uid}`", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)

    elif state == "waiting_remove_user_id" and uid == ADMIN_ID:
        if txt.isdigit():
            await db.users.delete_one({"_id": int(txt)})
            context.user_data.clear()
            return await update.message.reply_text(f"🗑 تم الحذف بنجاح.", reply_markup=admin_users_back_btn())

    elif state == "waiting_manage_user_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target:
            msg = f"👤 **الاسم:** {target.get('name')}\n🆔 `{target['_id']}`\n🎖 **الرتبة:** {target['role']}\n🔑 **التوكنات:** {len(target.get('tokens',[]))}"
            btns = [
                [InlineKeyboardButton("🗑 تصفير التوكنات", callback_data=f"manage_clear_tokens_{target['_id']}"), InlineKeyboardButton("🔄 تغيير الرتبة", callback_data=f"manage_switch_role_{target['_id']}")],
                [InlineKeyboardButton("🗑 مسح السجلات", callback_data=f"manage_clear_logs_{target['_id']}")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_users_menu")]
            ]
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ الحساب غير موجود.", reply_markup=admin_users_back_btn())
        context.user_data.clear()

    elif state == "waiting_user_logs_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target and target.get("logs"):
            logs_txt = "\n".join(target["logs"][-30:]) 
            await update.message.reply_text(f"📜 **سجلات ({txt}):**\n\n{logs_txt}", reply_markup=admin_users_back_btn())
        else:
            await update.message.reply_text("📭 لا توجد سجلات لهذا الحساب.", reply_markup=admin_users_back_btn())
        context.user_data.clear()

    elif state == "waiting_admin_order_search" and uid == ADMIN_ID:
        if txt.isdigit():
            order = await db.orders.find_one({"_id": int(txt)})
            if order:
                items_str = "\n".join([f"`{i}`" for i in order["items"]])
                await update.message.reply_text(f"📄 تقرير #{txt}\n👤 بواسطة: {order['user']}\n⬇️:\n{items_str}", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("❌ غير موجود.", reply_markup=admin_back_btn())
        context.user_data.clear()

    elif state == "waiting_reverse_code" and uid == ADMIN_ID:
        res = await db.codes_map.find_one({"_id": txt})
        if res:
            await update.message.reply_text(f"🔍 وجدته:\n👤 ساحب الكود: {res['name']}\n📅 الوقت: {res['time']}\n📦 في طلب #{res.get('order_id')}", reply_markup=admin_back_btn())
        else:
            await update.message.reply_text("❌ غير موجود.", reply_markup=admin_back_btn())
        context.user_data.clear()

    elif state == "adding_stock_manual" and uid == ADMIN_ID:
        lines = [c.strip() for c in txt.splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        if cat and lines:
            context.user_data["pending_stock"] = {"unique": lines, "dupes": []} 
            btns = [[InlineKeyboardButton("✅ تأكيد الإضافة", callback_data="confirm_add_unique")], [InlineKeyboardButton("❌ إلغاء", callback_data="back_home")]]
            return await update.message.reply_text(f"سجلات للتأكيد: {len(lines)}", reply_markup=InlineKeyboardMarkup(btns))

# ====== 📂 معالج الملفات ======
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    user = await get_user(uid)
    
    if uid == ADMIN_ID and state == "admin_uploading_file":
        doc = update.message.document
        if not doc.file_name.endswith(".txt"): return
        
        await log_activity(uid, user["name"], f"رفع ملف أكواد: {doc.file_name}")
        
        file = await doc.get_file()
        content = await file.download_as_bytearray()
        lines = [c.strip() for c in content.decode("utf-8", errors="ignore").splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        
        if cat and lines:
            context.user_data["pending_stock"] = {"unique": lines, "dupes": []}
            btns = [[InlineKeyboardButton("✅ تأكيد الإستيراد", callback_data="confirm_add_unique")], [InlineKeyboardButton("❌ إلغاء", callback_data="back_home")]]
            await update.message.reply_text(f"أكواد بالملف: {len(lines)}\n(سيتم تجاهل المكرر تلقائياً)", reply_markup=InlineKeyboardMarkup(btns))

# ====== 🏁 التشغيل ======
def main():
    threading.Thread(target=run_flask).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    
    app.add_error_handler(error_handler)
    
    logger.info("🚀 Bot Started Successfully with Advanced Logs & Error Handling!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
