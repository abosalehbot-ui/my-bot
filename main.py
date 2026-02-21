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
async def get_user(user_id): return await db.users.find_one({"_id": user_id})

async def log_activity(user_id, user_name, action):
    log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {action}"
    logger.info(f"📝 Activity | User: {user_id} | {action}")
    await db.users.update_one({"_id": user_id}, {"$push": {"logs": {"$each": [log_entry], "$slice": -200}}})

async def get_next_order_id():
    stat = await db.stats.find_one_and_update({"_id": "global_stats"}, {"$inc": {"last_order_id": 1}}, upsert=True, return_document=True)
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
    buttons.append([InlineKeyboardButton("💳 حسابي وإحصائياتي", callback_data="my_profile"), InlineKeyboardButton("🔍 كشف طلب", callback_data="check_order_id")])
    
    if role == "admin": buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

async def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة الموظفين والمستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📦 إدارة مخزن الأكواد", callback_data="admin_stock_menu"), InlineKeyboardButton("🎯 إدارة الآيديات", callback_data="admin_tasks_menu")],
        [InlineKeyboardButton("🔍 بحث عكسي (كود)", callback_data="admin_reverse_search"), InlineKeyboardButton("📄 بحث بطلب", callback_data="admin_search_order")],
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
        [InlineKeyboardButton("🔍 بحث وتحكم فردي", callback_data="admin_search_manage_user")],
        [InlineKeyboardButton("➕ إضافة موظف/مستخدم", callback_data="admin_add_user_btn")],
        [InlineKeyboardButton("📜 سجلات مستخدم", callback_data="admin_get_user_logs_btn"), InlineKeyboardButton("📋 قائمة الموظفين", callback_data="admin_list_users_btn")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ])

def stock_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 رفع ملف (.txt)", callback_data="admin_choose_cat_file"), InlineKeyboardButton("✍️ إضافة يدوي", callback_data="admin_choose_cat_manual")],
        [InlineKeyboardButton("🗑 تصفير فئة محددة", callback_data="admin_choose_cat_clear")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
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

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]])
def admin_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]])

# ====== 🚨 نظام التقاط الأخطاء ======
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("❌ Exception:", exc_info=context.error)

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

    if data in ["add_tokens", "check_order_id"]:
        states = {"add_tokens": ("waiting_tokens", "📝 **أرسل التوكنات:**"), "check_order_id": ("waiting_order_id", "🔍 **أرسل رقم الطلب:**")}
        context.user_data["state"] = states[data][0]
        return await query.edit_message_text(states[data][1], reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    # --- 🎯 نظام الآيديات للموظفين ---
    if data == "pull_ids_task" and role in ["admin", "employee"]:
        pending = await db.player_ids.count_documents({"status": "pending"})
        if pending == 0: return await query.edit_message_text("📭 لا يوجد آيديات معلقة للعمل حالياً.", reply_markup=back_btn())
        
        # التأكد إن الموظف مش واخد آيديات لسه مقفلهاش
        current_tasks = await db.player_ids.count_documents({"status": "processing", "assigned_to": uid})
        if current_tasks > 0:
            return await query.edit_message_text(f"⚠️ لديك {current_tasks} آيديات قيد العمل!\nيرجى تقفيلهم أولاً من القائمة الرئيسية.", reply_markup=back_btn())
            
        context.user_data["state"] = "waiting_pull_ids_count"
        return await query.edit_message_text(f"🎯 **سحب مهام شحن**\nالآيديات المتاحة: {pending}\n\n🔢 **أرسل عدد الآيديات التي تريد سحبها للعمل عليها الآن:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "finish_ids_task" and role in ["admin", "employee"]:
        tasks = await db.player_ids.find({"status": "processing", "assigned_to": uid}).to_list(length=None)
        if not tasks: return await query.edit_message_text("✅ ليس لديك أي آيديات معلقة للتقفيل.", reply_markup=back_btn())
        
        # تقفيل المهام
        await db.player_ids.update_many({"status": "processing", "assigned_to": uid}, {"$set": {"status": "done", "done_at": datetime.now()}})
        await db.users.update_one({"_id": uid}, {"$inc": {"stats.ids_done": len(tasks)}})
        await log_activity(uid, user["name"], f"قفل {len(tasks)} آيدي")
        
        return await query.edit_message_text(f"✅ **عاش!** تم تقفيل {len(tasks)} آيديات وإضافتهم لإحصائياتك.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    # --- ↩️ نظام المرتجعات (15 دقيقة) ---
    if data == "return_order" and role in ["admin", "employee"]:
        context.user_data["state"] = "waiting_return_order_id"
        return await query.edit_message_text("↩️ **نظام المرتجعات السريع**\n\nأرسل **رقم الطلب (Order ID)** الذي تريد إرجاعه:\n*(ملاحظة: الإرجاع متاح لأكواد ببجي فقط، وخلال 15 دقيقة من السحب)*", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    # --- سحب الأكواد العادي ---
    if data == "pull_stock_menu" and role in ["admin", "employee"]: return await query.edit_message_text("🎮 **اختر الفئة للسحب:**", reply_markup=await categories_keyboard("pull_cat"))
    if data.startswith("pull_cat_") and role in ["admin", "employee"]:
        cat = data.split("_")[-1]
        context.user_data["state"] = "waiting_stock_count"
        context.user_data["target_pull_cat"] = cat
        return await query.edit_message_text(f"🔢 **أرسل العدد لـ {cat} UC:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    # --- لوحة الأدمن ---
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
    if data.startswith("admin_add_manual_") and role == "admin":
        cat = data.split("_")[-1]
        context.user_data["state"] = "adding_stock_manual"
        context.user_data["target_cat"] = cat
        return await query.edit_message_text(f"✍️ **أرسل أكواد {cat} UC:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        
    if data in ["confirm_add_unique"] and role == "admin":
        pending = context.user_data.get("pending_stock")
        cat = context.user_data.get("target_cat")
        if pending and cat:
            docs = [{"_id": c, "category": cat, "added_at": datetime.now()} for c in pending["unique"]]
            if docs: await db.stock.insert_many(docs, ordered=False) 
        context.user_data.clear()
        return await query.edit_message_text(f"✅ تم إضافة الأكواد.", reply_markup=admin_back_btn())


# ====== 📩 معالج الرسائل النصية ======
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    uid = update.effective_user.id
    txt = update.message.text.strip()
    state = context.user_data.get("state")
    
    if not state: return await update.message.reply_text("💡 اختر عملية من القائمة أولاً.", reply_markup=back_btn())
    user = await get_user(uid)
    if not user: return

    # --- إرجاع طلب (نظام الـ 15 دقيقة) ---
    if state == "waiting_return_order_id":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        order = await db.orders.find_one({"_id": int(txt)})
        
        if not order or (order["user_id"] != uid and user["role"] != "admin"):
            return await update.message.reply_text("❌ الطلب غير موجود أو لا تملك صلاحية.", reply_markup=back_btn())
            
        if "PUBG Stock" not in order["type"]:
            return await update.message.reply_text("❌ لا يمكن إرجاع هذا النوع من الطلبات (متاح للأكواد فقط).", reply_markup=back_btn())
            
        # فحص الوقت (15 دقيقة)
        order_time = datetime.strptime(order['date'], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - order_time).total_seconds() > 900 and user["role"] != "admin": # 900 ثانية = 15 دقيقة
            return await update.message.reply_text("⏳ **عذراً، انتهت مهلة الإرجاع (15 دقيقة).**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            
        # استخراج الفئة وإرجاع الأكواد
        cat = order["type"].split("(")[1].split(" ")[0]
        codes_to_return = [{"_id": code, "category": cat, "added_at": datetime.now()} for code in order["items"]]
        
        await db.stock.insert_many(codes_to_return, ordered=False) # إرجاع للمخزن
        await db.codes_map.delete_many({"_id": {"$in": order["items"]}}) # مسح من الماب
        await db.orders.delete_one({"_id": int(txt)}) # حذف الطلب
        await db.users.update_one({"_id": uid}, {"$inc": {"stats.stock": -len(order["items"])}}) # خصم من الإحصائيات
        await log_activity(uid, user["name"], f"إرجاع طلب #{txt} ({len(order['items'])} كود)")
        
        context.user_data.clear()
        return await update.message.reply_text(f"✅ **تم إرجاع الطلب #{txt} بنجاح!**\nتم إعادة الأكواد للمخزن وخصمها من عهدتك.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    # --- سحب مهام الآيديات للموظف ---
    elif state == "waiting_pull_ids_count" and user["role"] in ["admin", "employee"]:
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ رقم غير صحيح.", reply_markup=back_btn())
        qty = int(txt)
        
        # سحب وتعيين المهام
        pulled_ids = []
        for _ in range(qty):
            task = await db.player_ids.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "processing", "assigned_to": uid, "pulled_at": datetime.now()}}
            )
            if task: pulled_ids.append(task["_id"])
            else: break # لو مفيش تاني
            
        context.user_data.clear()
        if not pulled_ids: return await update.message.reply_text("❌ لا يوجد آيديات متاحة حالياً.", reply_markup=back_btn())
        
        ids_text = "\n".join([f"🎯 `{pid}`" for pid in pulled_ids])
        msg = f"✅ **تم استلام المهام!**\nعليك شحن الآيديات التالية:\n\n{ids_text}\n\n⚠️ *لا تنسَ الضغط على 'تقفيل' بعد الانتهاء!*"
        return await update.message.reply_text(msg, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    # --- إضافة آيديات (للأدمن) ---
    elif state == "waiting_admin_add_ids" and user["role"] == "admin":
        lines = [c.strip() for c in txt.splitlines() if c.strip()]
        if lines:
            docs = [{"_id": pid, "status": "pending", "assigned_to": None} for pid in lines]
            try: await db.player_ids.insert_many(docs, ordered=False)
            except: pass
            
        context.user_data.clear()
        return await update.message.reply_text(f"✅ تم إضافة {len(lines)} آيدي للمهام.", reply_markup=admin_back_btn())

    # --- سحب مخزن أكواد (العادي) ---
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
            await log_activity(uid, user["name"], f"سحب {len(pulled)} كود فئة {cat}")
            
            msg = "\n".join([f"🎮 <code>{c}</code>" for c in pulled])
            return await update.message.reply_text(f"✅ **سحب {cat} UC (طلب #{order_id}):**\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الرئيسية", callback_data="back_home")]]))

    # --- إضافة أكواد يدوية للمخزن ---
    elif state == "adding_stock_manual" and uid == ADMIN_ID:
        lines = [c.strip() for c in txt.splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        if cat and lines:
            context.user_data["pending_stock"] = {"unique": lines, "dupes": []} 
            btns = [[InlineKeyboardButton("✅ تأكيد الإضافة", callback_data="confirm_add_unique")], [InlineKeyboardButton("❌ إلغاء", callback_data="back_home")]]
            return await update.message.reply_text(f"سجلات للتأكيد: {len(lines)}", reply_markup=InlineKeyboardMarkup(btns))

def main():
    threading.Thread(target=run_flask).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)
    logger.info("🚀 Bot Started with Task Management & Returns!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
