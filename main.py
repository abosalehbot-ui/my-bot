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
    # حفظ كل حركة في الداتا بيز (الحد الأقصى 500 حركة لكل مستخدم لمنع الضغط)
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
            # نرسل ريكوست لكل توكن لوحده يطلب حساب واحد فقط
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

    # تحديث الداتا بيز: مسح التوكنات المستخدمة (سواء ناجحة أو بايظة) وإضافة السجلات
    db_updates = {"$pull": {"tokens": {"$in": used_tokens}}}
    if token_logs_updates:
        db_updates["$push"] = {"token_logs": {"$each": token_logs_updates, "$slice": -500}} # حفظ آخر 500 سجل توكنات
    
    await db.users.update_one({"_id": uid}, db_updates)
    
    # تحديث الكيبورد للعمليات المتكررة
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

    # --- القوائم العامة والإحصائيات ---
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
        txt = "\n".join(logs[-30:]) # يعرض آخر 30 حركة
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

    # --- سحب الـ API المتطور ---
    if data == "pull_api":
        tokens = user.get("tokens", [])
        if not tokens: return await query.edit_message_text("⚠️ **لا يوجد توكنات!** أضف توكن أولاً من القائمة الرئيسية.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        context.user_data["state"] = "waiting_api_count"
        return await query.edit_message_text("🔢 **أرسل عدد الحسابات التي تريد سحبها الآن:**\n*(سيتم استخدام توكن واحد لكل حساب)*", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "pull_api_again":
        qty = context.user_data.get("last_api_count", 1)
        # نرسل رسالة جديدة بالطلب المعُاد
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

    if data =
