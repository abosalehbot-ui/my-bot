import os
import logging
import asyncio
from datetime import datetime
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

# ====== 🗄️ إعدادات MongoDB (Motor) ======
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["salehzon_db"]

# ====== 📝 إعداد اللوجز ======
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

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

# ====== 💾 دوال مساعدة لقاعدة البيانات ======
async def get_user(user_id):
    user = await db.users.find_one({"_id": user_id})
    return user

async def log_activity(user_id, user_name, action):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {action}"
    logger.info(f"📝 Activity | User: {user_id} | {action}")
    
    await db.users.update_one(
        {"_id": user_id},
        {"$push": {"logs": {"$each": [log_entry], "$slice": -200}}}
    )

async def get_next_order_id():
    stat = await db.stats.find_one_and_update(
        {"_id": "global_stats"},
        {"$inc": {"last_order_id": 1}},
        upsert=True,
        return_document=True
    )
    return stat["last_order_id"]

async def check_maintenance():
    settings = await db.settings.find_one({"_id": "config"})
    if not settings:
        await db.settings.insert_one({"_id": "config", "maintenance": False})
        return False
    return settings.get("maintenance", False)

# ====== ⌨️ الكيبوردات ======
def get_main_keyboard(role):
    buttons = []
    if role in ["employee", "admin"]:
        buttons.append([InlineKeyboardButton("🎮 سحب كود ببجي (UC)", callback_data="pull_stock_menu")])
    buttons.append([InlineKeyboardButton("🚀 سحب حسابات (API)", callback_data="pull_api")])
    buttons.append([
        InlineKeyboardButton("➕ إضافة توكن", callback_data="add_tokens"),
        InlineKeyboardButton("📋 توكناتي الحالية", callback_data="view_my_tokens")
    ])
    buttons.append([
        InlineKeyboardButton("💳 حسابي", callback_data="my_profile"),
        InlineKeyboardButton("📂 أرشيفي", callback_data="my_history")
    ])
    buttons.append([InlineKeyboardButton("🔍 كشف طلب (ID)", callback_data="check_order_id")])
    if role == "admin":
        buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

async def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton(f"📦 إدارة المخزن", callback_data="admin_stock_menu")],
        [InlineKeyboardButton("🔍 بحث عكسي (كود)", callback_data="admin_reverse_search"),
         InlineKeyboardButton("📄 بحث برقم الطلب", callback_data="admin_search_order")],
        [InlineKeyboardButton("📝 سجلات النظام", callback_data="admin_get_logs")],
        [InlineKeyboardButton("🛠 وضع الصيانة", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("🏠 خروج", callback_data="back_home")]
    ])

def admin_users_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 بحث وإدارة مستخدم فردي", callback_data="admin_search_manage_user")],
        [InlineKeyboardButton("➕ إضافة مستخدم", callback_data="admin_add_user_btn"),
         InlineKeyboardButton("🗑 حذف مستخدم", callback_data="admin_remove_user_btn")],
        [InlineKeyboardButton("📜 سجلات مستخدم", callback_data="admin_get_user_logs_btn"),
         InlineKeyboardButton("📋 عرض القائمة", callback_data="admin_list_users_btn")],
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

async def categories_keyboard(action_prefix):
    buttons = []
    row = []
    for cat in UC_CATEGORIES:
        count = await db.stock.count_documents({"category": cat})
        # إشارات المرور الذكية للمخزن
        icon = "🔴" if count == 0 else ("🟡" if count < 5 else "🟢")
        btn_text = f"{icon} {cat} UC ({count})"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"{action_prefix}_{cat}"))
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

# ====== 🚀 Handlers ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    user = await get_user(user_id)
    
    if user_id == ADMIN_ID and not user:
        new_admin = {"_id": user_id, "role": "admin", "name": name, "tokens": [], "history": [], "logs": [], "stats": {"api": 0, "stock": 0}}
        await db.users.insert_one(new_admin)
        user = new_admin

    if not user:
        await update.message.reply_text("⛔ غير مسجل. تواصل مع الإدارة.", parse_mode=ParseMode.MARKDOWN)
        return

    if user.get("name") != name:
        await db.users.update_one({"_id": user_id}, {"$set": {"name": name}})

    role = user.get("role", "user")
    is_maint = await check_maintenance()
    maint_msg = "\n⚠️ **النظام في وضع الصيانة**" if is_maint else ""
    
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
    
    user = await get_user(user_id)
    if not user: return
    role = user.get("role", "user")

    is_maint = await check_maintenance()
    if is_maint and role != "admin":
        await query.edit_message_text("⚠️ **الصيانة جارية حالياً...**", reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        return

    if data == "back_home":
        context.user_data.clear()
        await query.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard(role))
        return

    # --- لوحة القيادة المتطورة للأدمن ---
    if data == "admin_panel" and role == "admin":
        context.user_data.clear()
        status = "🔴 مفعل" if is_maint else "🟢 معطل"
        total_stock = await db.stock.count_documents({})
        today_str = datetime.now().strftime("%Y-%m-%d")
        orders_today = await db.orders.count_documents({"date": {"$regex": f"^{today_str}"}})
        
        # حساب إجمالي التوكنات الفعالة في النظام
        pipeline = [{"$project": {"token_count": {"$size": {"$ifNull": ["$tokens", []]}}}}, {"$group": {"_id": None, "total": {"$sum": "$token_count"}}}]
        res = await db.users.aggregate(pipeline).to_list(length=1)
        total_tokens = res[0]["total"] if res else 0

        msg = f"📊 **لوحة الإحصائيات (Dashboard)**\n\n📦 إجمالي أكواد المخزن: **{total_stock}**\n🔑 توكنات النظام النشطة: **{total_tokens}**\n🛒 طلبات اليوم: **{orders_today}**\n🛠 الصيانة: {status}"
        await query.edit_message_text(msg, reply_markup=await admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- بطاقة حساب المستخدم (Profile) ---
    if data == "my_profile":
        t_count = len(user.get("tokens", []))
        stats = user.get("stats", {"api": 0, "stock": 0})
        role_icon = "👮‍♂️ أدمن" if role == "admin" else "👤 موظف" if role == "employee" else "🆕 مستخدم"
        msg = f"💳 **بطاقة حسابك:**\n\n👤 **الاسم:** {user.get('name')}\n🎖 **الرتبة:** {role_icon}\n🔑 **توكناتك النشطة:** {t_count}\n\n🛒 **إجمالي سحوباتك:**\n🚀 سحب API: {stats['api']}\n🎮 سحب مخزن: {stats['stock']}"
        await query.edit_message_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- إدارة التوكنات بذكاء ---
    if data == "view_my_tokens":
        tokens = user.get("tokens", [])
        if not tokens:
            await query.edit_message_text("📭 لا يوجد لديك توكنات نشطة.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return
        # إخفاء جزء من التوكنات للأمان
        txt = "\n".join([f"🔑 `{t[:8]}...{t[-4:]}`" for t in tokens])
        btns = [[InlineKeyboardButton("🗑 حذف جميع توكناتي", callback_data="clear_tokens")], [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]]
        await query.edit_message_text(f"📋 **توكناتك الحالية ({len(tokens)}):**\n\n{txt}", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "clear_tokens":
        await db.users.update_one({"_id": user_id}, {"$set": {"tokens": []}})
        await query.edit_message_text("🗑 **تم حذف جميع التوكنات.**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- إدارة المستخدمين ---
    if data == "admin_users_menu" and role == "admin":
        context.user_data.clear()
        users_count = await db.users.count_documents({})
        await query.edit_message_text(f"👥 **إدارة المستخدمين**\nعدد المسجلين: {users_count}", reply_markup=admin_users_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    if data in ["admin_add_user_btn", "admin_remove_user_btn", "admin_search_manage_user", "admin_get_user_logs_btn"] and role == "admin":
        states = {
            "admin_add_user_btn": ("waiting_add_user_id", "✍️ **أرسل الآيدي (ID) لإضافته:**"),
            "admin_remove_user_btn": ("waiting_remove_user_id", "🗑 **أرسل الآيدي (ID) لحذفه:**"),
            "admin_search_manage_user": ("waiting_manage_user_id", "🔍 **أرسل الآيدي (ID) للتحكم في حسابه:**"),
            "admin_get_user_logs_btn": ("waiting_user_logs_id", "📜 **أرسل الآيدي لاستخراج سجلاته:**")
        }
        context.user_data["state"] = states[data][0]
        await query.edit_message_text(states[data][1], reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- تحكمات الإدارة الفردية ---
    if data.startswith("manage_clear_tokens_") and role == "admin":
        tid = int(data.split("_")[-1])
        await db.users.update_one({"_id": tid}, {"$set": {"tokens": []}})
        await query.answer("✅ تم تصفير التوكنات بنجاح", show_alert=True)
        return
        
    if data.startswith("manage_switch_role_") and role == "admin":
        tid = int(data.split("_")[-1])
        target = await get_user(tid)
        if target and target["_id"] != ADMIN_ID:
            new_role = "employee" if target["role"] == "user" else "user"
            await db.users.update_one({"_id": tid}, {"$set": {"role": new_role}})
            await query.answer(f"✅ تم تغيير الرتبة لـ {new_role}", show_alert=True)
        return
        
    if data.startswith("manage_clear_logs_") and role == "admin":
        tid = int(data.split("_")[-1])
        await db.users.update_one({"_id": tid}, {"$set": {"logs": [], "history": []}})
        await query.answer("✅ تم مسح السجلات والأرشيف", show_alert=True)
        return

    if data.startswith("set_role_") and role == "admin":
        new_uid = context.user_data.get("new_user_id")
        if not new_uid: return
        selected_role = "employee" if data == "set_role_employee" else "user"
        new_user = {"_id": new_uid, "role": selected_role, "name": "User", "tokens": [], "history": [], "logs": [], "stats": {"api":0,"stock":0}}
        await db.users.insert_one(new_user)
        context.user_data.clear()
        await query.edit_message_text(f"✅ تم إضافة `{new_uid}` كرتبة **{selected_role}**.", reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_list_users_btn" and role == "admin":
        msg = "👥 **آخر المستخدمين:**\n\n"
        async for u in db.users.find().sort("_id", -1).limit(20):
             role_icon = "👮‍♂️" if u['role'] == "admin" else "👤" if u['role'] == "employee" else "🆕"
             msg += f"{role_icon} `{u['_id']}` | {u.get('name', 'بدون اسم')}\n"
        await query.edit_message_text(msg, reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- إدارة المخزن ---
    if data == "admin_stock_menu" and role == "admin":
        context.user_data.clear()
        await query.edit_message_text(f"📦 **إدارة المخزن**\nاختر العملية:", reply_markup=stock_manage_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return
    
    if data == "admin_choose_cat_manual" and role == "admin":
        await query.edit_message_text("🔢 **اختر الفئة للإضافة اليدوية:**", reply_markup=await categories_keyboard("admin_add_manual"))
        return

    if data == "admin_choose_cat_file" and role == "admin":
        await query.edit_message_text("📂 **اختر الفئة لرفع الملف:**", reply_markup=await categories_keyboard("admin_add_file"))
        return

    if data == "admin_choose_cat_clear" and role == "admin":
        await query.edit_message_text("🗑 **اختر الفئة لتصفيرها:**", reply_markup=await categories_keyboard("admin_clear_cat"))
        return

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
        await db.stock.delete_many({"category": cat})
        await query.edit_message_text(f"🗑 **تم تصفير فئة {cat} UC بنجاح.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_clear_all_confirm" and role == "admin":
        await db.stock.delete_many({})
        await query.edit_message_text("🗑 **تم تصفير جميع الفئات بنجاح.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data in ["confirm_add_all", "confirm_add_unique"] and role == "admin":
        pending = context.user_data.get("pending_stock")
        cat = context.user_data.get("target_cat")
        if not pending or not cat: return
        codes_to_add = pending["unique"] if data == "confirm_add_unique" else pending["unique"] + pending["dupes"]
        docs = [{"_id": c, "category": cat, "added_at": datetime.now()} for c in codes_to_add]
        if docs:
            try: await db.stock.insert_many(docs, ordered=False) 
            except Exception: pass
        context.user_data.clear()
        await query.edit_message_text(f"✅ تم إضافة الأكواد بنجاح لفئة {cat}.", reply_markup=admin_back_btn())
        return

    if data == "cancel_add_stock" and role == "admin":
        context.user_data.clear()
        await query.edit_message_text("❌ تم إلغاء العملية.", reply_markup=admin_back_btn())
        return

    # --- القوائم العامة ---
    if data == "add_tokens" or data == "check_order_id":
        states = {
            "add_tokens": ("waiting_tokens", "📝 **أرسل التوكنات:**"),
            "check_order_id": ("waiting_order_id", "🔍 **أرسل رقم الطلب (ID):**")
        }
        context.user_data["state"] = states[data][0]
        await query.edit_message_text(states[data][1], reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "my_history":
        hist = user.get("history", [])
        txt = "\n".join(hist[-10:]) if hist else "📂 أرشيفك فارغ."
        await query.edit_message_text(f"📂 **آخر 10 عمليات:**\n\n{txt}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "toggle_maintenance" and role == "admin":
        new_status = not is_maint
        await db.settings.update_one({"_id": "config"}, {"$set": {"maintenance": new_status}}, upsert=True)
        status = "🔴 مفعل" if new_status else "🟢 معطل"
        await query.edit_message_text(f"🛠 **لوحة الأدمن**\n📦 الحالة: {status}", reply_markup=await admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return
        
    if data in ["admin_reverse_search", "admin_search_order"] and role == "admin":
        state = "waiting_reverse_code" if data == "admin_reverse_search" else "waiting_admin_order_search"
        msg = "🔍 **أرسل الكود:**" if data == "admin_reverse_search" else "📄 **أرسل رقم الطلب:**"
        context.user_data["state"] = state
        await query.edit_message_text(msg, reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # ====== 🚀 عمليات السحب (الذكية) ======
    
    if data == "pull_stock_menu":
        if role not in ["admin", "employee"]: return
        await query.edit_message_text("🎮 **اختر فئة الشدات للسحب:**", reply_markup=await categories_keyboard("pull_cat"))
        return

    # طلب عدد الأكواد
    if data.startswith("pull_cat_"):
        if role not in ["admin", "employee"]: return
        cat = data.split("_")[-1]
        context.user_data["state"] = "waiting_stock_count"
        context.user_data["target_pull_cat"] = cat
        await query.edit_message_text(f"🔢 **أرسل عدد الأكواد التي تريد سحبها من فئة {cat} UC:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # طلب عدد حسابات API
    if data == "pull_api":
        tokens = user.get("tokens", [])
        if not tokens:
            await query.edit_message_text("⚠️ **لا يوجد توكنات!** أضف توكن أولاً من القائمة الرئيسية.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return
        context.user_data["state"] = "waiting_api_count"
        await query.edit_message_text("🔢 **أرسل عدد الحسابات التي تريد سحبها:**\n*(سيقوم البوت بالبحث في توكناتك حتى إكمال العدد)*", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

# ====== 📩 معالج الرسائل النصية وطلبات السحب ======
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    uid = update.effective_user.id
    txt = update.message.text.strip()
    state = context.user_data.get("state")
    
    user = await get_user(uid)
    if not user: return

    # --- تنفيذ سحب المخزن ---
    if state == "waiting_stock_count":
        if not txt.isdigit() or int(txt) <= 0:
            await update.message.reply_text("❌ أرسل رقم صحيح أكبر من 0.", reply_markup=back_btn())
            return
        
        count = int(txt)
        cat = context.user_data.get("target_pull_cat")
        context.user_data.clear() # تفريغ الحالة
        
        available = await db.stock.count_documents({"category": cat})
        if available < count:
            await update.message.reply_text(f"⚠️ **الكمية غير كافية!** المتوفر: {available}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            return

        order_id = await get_next_order_id()
        pulled = []
        for _ in range(count):
            code_doc = await db.stock.find_one_and_delete({"category": cat})
            if code_doc:
                pulled.append(code_doc["_id"])
                await db.codes_map.insert_one({"_id": code_doc["_id"], "name": user["name"], "user_id": uid, "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "order_id": order_id})

        if not pulled: return
            
        await db.orders.insert_one({"_id": order_id, "type": f"PUBG Stock ({cat} UC)", "user": user["name"], "user_id": uid, "items": pulled, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        hist_entry = f"📦 طلب #{order_id} ({len(pulled)} كود)"
        await db.users.update_one({"_id": uid}, {"$push": {"history": hist_entry}, "$inc": {"stats.stock": len(pulled)}})
        await log_activity(uid, user["name"], f"سحب {len(pulled)} كود من فئة {cat}")

        if (available - count) < 4:
            try: await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ **تنبيه:** مخزون فئة **{cat} UC** أوشك على النفاذ!")
            except: pass

        msg = "\n".join([f"🎮 <code>{c}</code>" for c in pulled])
        await update.message.reply_text(f"✅ **تم سحب {cat} UC بنجاح (طلب #{order_id}):**\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=success_pull_keyboard(f"pull_cat_{cat}"))
        return

    # --- تنفيذ سحب API المتعدد ---
    elif state == "waiting_api_count":
        if not txt.isdigit() or int(txt) <= 0:
            await update.message.reply_text("❌ أرسل رقم صحيح أكبر من 0.", reply_markup=back_btn())
            return
            
        qty = int(txt)
        context.user_data.clear()
        
        tokens = list(user.get("tokens", []))
        if not tokens: return
        
        waiting_msg = await update.message.reply_text("⏳ **جاري الاتصال بالسيرفر وجمع الحسابات...**", parse_mode=ParseMode.MARKDOWN)
        
        order_id = await get_next_order_id()
        accs = []
        tokens_to_remove = []
        
        async with httpx.AsyncClient() as client:
            for t in tokens:
                if len(accs) >= qty: break
                needed = qty - len(accs)
                
                try:
                    res = await client.post(f"{API_BASE_URL}/api/redeem-bulk", json={"token":t, "product":PRODUCT_ID, "qty":needed}, timeout=15.0)
                    r = res.json()
                    if r.get("success"):
                        for a in r["accounts"]:
                            accs.append(f"📧 `{a['email']}`\n🔑 `{a['password']}`")
                    elif "Invalid" in r.get("message", ""): 
                        tokens_to_remove.append(t)
                except Exception as e:
                    logger.error(f"API Error: {e}")
                    continue
        
        if tokens_to_remove:
            await db.users.update_one({"_id": uid}, {"$pull": {"tokens": {"$in": tokens_to_remove}}})
            await update.message.reply_text(f"⚠️ تنبيه: تم إزالة {len(tokens_to_remove)} توكن تالف من حسابك بشكل تلقائي.")
            
        if accs:
            await db.orders.insert_one({"_id": order_id, "type": "API Pull", "user": user["name"], "user_id": uid, "items": accs, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            hist_entry = f"🚀 طلب #{order_id} ({len(accs)} حساب)"
            await db.users.update_one({"_id": uid}, {"$push": {"history": hist_entry}, "$inc": {"stats.api": len(accs)}})
            await log_activity(uid, user["name"], f"سحب API (طلب #{order_id} - عدد {len(accs)})")
            
            display_txt = "\n━━━━━━━━━━━━\n".join(accs)
            await waiting_msg.edit_text(f"✅ **تم السحب بنجاح (طلب #{order_id}):**\n\n{display_txt}", parse_mode=ParseMode.MARKDOWN, reply_markup=success_pull_keyboard("pull_api"))
        else:
            await waiting_msg.edit_text("❌ **فشل السحب.** تأكد من صحة التوكنات المتبقية أو رصيدها في السيرفر الرئيسي.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # --- باقي الحالات النصية ---
    if state == "waiting_tokens":
        lines = [t.strip() for t in txt.splitlines() if t.strip()]
        if lines: await db.users.update_one({"_id": uid}, {"$addToSet": {"tokens": {"$each": lines}}})
        context.user_data.clear()
        await update.message.reply_text(f"✅ تم إضافة التوكنات بنجاح.", reply_markup=back_btn())

    elif state == "waiting_add_user_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        new_uid = int(txt)
        if await get_user(new_uid):
            await update.message.reply_text("⚠️ هذا المستخدم موجود بالفعل!", reply_markup=admin_users_back_btn())
        else:
            context.user_data["new_user_id"] = new_uid
            btns = [[InlineKeyboardButton("موظف 👤", callback_data="set_role_employee")], [InlineKeyboardButton("مستخدم عادي 🆕", callback_data="set_role_user")]]
            await update.message.reply_text(f"👤 **اختر الرتبة:** `{new_uid}`", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)

    elif state == "waiting_remove_user_id" and uid == ADMIN_ID:
        if txt.isdigit():
            await db.users.delete_one({"_id": int(txt)})
            context.user_data.clear()
            await update.message.reply_text(f"🗑 تم الحذف.", reply_markup=admin_users_back_btn())

    elif state == "waiting_manage_user_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target:
            msg = f"👤 **المستخدم:** {target.get('name')}\n🆔 `{target['_id']}`\n🎖 **الرتبة:** {target['role']}\n🔑 **التوكنات:** {len(target.get('tokens',[]))}"
            btns = [
                [InlineKeyboardButton("🗑 تصفير التوكنات", callback_data=f"manage_clear_tokens_{target['_id']}"),
                 InlineKeyboardButton("🔄 تغيير الرتبة", callback_data=f"manage_switch_role_{target['_id']}")],
                [InlineKeyboardButton("🗑 مسح السجلات", callback_data=f"manage_clear_logs_{target['_id']}")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_users_menu")]
            ]
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ المستخدم غير موجود.", reply_markup=admin_users_back_btn())
        context.user_data.clear()

    elif state == "waiting_order_id":
        if txt.isdigit():
            order = await db.orders.find_one({"_id": int(txt)})
            if order and (order["user_id"] == uid or user["role"] == "admin"):
                items_str = "\n".join([f"`{i}`" for i in order["items"]])
                await update.message.reply_text(f"📄 **طلب #{txt}**\n📅 {order['date']}\n⬇️:\n{items_str}", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("❌ غير موجود أو لا تملك صلاحية.", reply_markup=back_btn())
        context.user_data.clear()

    elif state == "waiting_admin_order_search" and uid == ADMIN_ID:
        if txt.isdigit():
            order = await db.orders.find_one({"_id": int(txt)})
            if order:
                items_str = "\n".join([f"`{i}`" for i in order["items"]])
                await update.message.reply_text(f"📄 تقرير #{txt}\n👤 {order['user']}\n⬇️:\n{items_str}", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        context.user_data.clear()

    elif state == "waiting_reverse_code" and uid == ADMIN_ID:
        res = await db.codes_map.find_one({"_id": txt})
        if res:
            await update.message.reply_text(f"🔍 وجدته:\n👤 {res['name']}\n📅 {res['time']}\n📦 طلب #{res.get('order_id')}", reply_markup=admin_back_btn())
        else:
            await update.message.reply_text("❌ غير موجود.", reply_markup=admin_back_btn())
        context.user_data.clear()

    elif state == "adding_stock_manual" and uid == ADMIN_ID:
        lines = [c.strip() for c in txt.splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        if cat and lines:
            context.user_data["pending_stock"] = {"unique": lines, "dupes": []}
            btns = [[InlineKeyboardButton("✅ تأكيد الإضافة", callback_data="confirm_add_unique")], [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")]]
            await update.message.reply_text(f"سجلات للتأكيد: {len(lines)}", reply_markup=InlineKeyboardMarkup(btns))

# ====== 📂 معالج الملفات ======
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    
    if uid == ADMIN_ID and state == "admin_uploading_file":
        doc = update.message.document
        if not doc.file_name.endswith(".txt"): return
        
        file = await doc.get_file()
        content = await file.download_as_bytearray()
        lines = [c.strip() for c in content.decode("utf-8", errors="ignore").splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        
        if cat and lines:
            context.user_data["pending_stock"] = {"unique": lines, "dupes": []}
            btns = [[InlineKeyboardButton("✅ تأكيد الإستيراد", callback_data="confirm_add_unique")], [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")]]
            await update.message.reply_text(f"أكواد بالملف: {len(lines)}\n(سيتم تجاهل الأكواد المكررة تلقائياً)", reply_markup=InlineKeyboardMarkup(btns))

# ====== 🏁 التشغيل ======
def main():
    threading.Thread(target=run_flask).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    print("🚀 Bot Started with Async MongoDB Engine!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
