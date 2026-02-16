import requests
import json
import os
import threading
import logging
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ====== 📝 إعداد نظام اللوجز (Logging System) ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s', # شلت الـ levelname عشان يبقى الشكل أنظف
    handlers=[
        logging.FileHandler("bot_logs.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 👇👇👇 هنا التعديل: إلغاء رسائل الـ HTTP المزعجة 👇👇👇
# نطلب من المكتبات دي متتكلمش إلا لو فيه مصيبة (Warning او Error)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = "8577787177:AAHAH06rraN86cZQykyhnxV3hxkIQOCyxk8"
ADMIN_ID = 1635871816
API_URL = "https://api.redeem999.org/process"
PRODUCT_ID = "2191d640-7319-486e-857b-afcd2b0ed921"
USERS_FILE = "users_db.json"

# ====== 🌐 سيرفر Flask ======
app_server = Flask(__name__)

# إيقاف لوجز السيرفر كمان عشان ميعملش دوشة
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app_server.route('/')
def home():
    return "✅ Bot is Online!", 200

def run_flask():
    app_server.run(host="0.0.0.0", port=8080)

# ====== 💾 قاعدة البيانات ======
def load_db():
    default_db = {"users": {}, "stats": {"total_pulled": 0}}
    if not os.path.exists(USERS_FILE): return default_db
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["users"] = {int(k): v for k, v in data["users"].items()}
            return data
    except: return default_db

def save_db(data):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ Save DB Error: {e}")

DB = load_db()

# ====== ⌨️ الكيبورد ======
def user_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 سحب حساب (API)", callback_data="pull_api")],
        [InlineKeyboardButton("📂 أرشيفي", callback_data="my_history"),
         InlineKeyboardButton("💰 فحص الرصيد", callback_data="check_balance")],
        [InlineKeyboardButton("⚙️ التوكن", callback_data="set_token"),
         InlineKeyboardButton("🔢 العدد", callback_data="set_count")]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 قائمة المستخدمين", callback_data="admin_list_users")],
        [InlineKeyboardButton("➕ إضافة", callback_data="admin_add_user"),
         InlineKeyboardButton("⛔ حذف", callback_data="admin_del_user")],
        [InlineKeyboardButton("📢 إذاعة", callback_data="admin_broadcast"),
         InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_home")]
    ])

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_home")]])

def after_pull_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 سحب حساب آخر", callback_data="pull_api")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_home")]
    ])

# ====== 🚀 البداية ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name

    # تسجيل في اللوج
    logger.info(f"🟢 User Started Bot: {first_name} (ID: {user_id})")

    if user_id == ADMIN_ID and user_id not in DB["users"]:
        DB["users"][user_id] = {"token": None, "max": 1, "history": [], "balance_msg": "غير متوفر", "name": "Admin"}
        save_db(DB)

    if user_id not in DB["users"]:
        logger.warning(f"🔴 Unauthorized Access: {first_name} ({user_id})")
        await update.message.reply_text("⛔ **البوت خاص.** تواصل مع الأدمن.", parse_mode="Markdown")
        return

    if "balance_msg" not in DB["users"][user_id]:
        DB["users"][user_id]["balance_msg"] = "لم يتم السحب بعد"
    DB["users"][user_id]["name"] = first_name
    save_db(DB)

    await update.message.reply_text(
        f"👋 **أهلاً {first_name}**\n🤖 بوت سحب الحسابات المتطور.",
        reply_markup=user_keyboard(), parse_mode="Markdown"
    )

# ====== 👑 الأدمن ======
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        logger.info("👑 Admin opened control panel")
        await update.message.reply_text("🛠 **لوحة التحكم**", reply_markup=admin_keyboard(), parse_mode="Markdown")

# ====== 🕹 الأزرار ======
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if user_id not in DB["users"] and user_id != ADMIN_ID: return

    # --- 🏠 العودة ---
    if data == "back_home":
        context.user_data["state"] = None
        await query.edit_message_text("🏠 **القائمة الرئيسية:**", reply_markup=user_keyboard(), parse_mode="Markdown")
        return

    # --- 💰 فحص الرصيد ---
    if data == "check_balance":
        logger.info(f"🔍 User {user_id} checked balance")
        info = DB["users"][user_id]
        token = info.get("token")
        last_bal = info.get("balance_msg", "لا يوجد بيانات")

        if not token:
            await query.edit_message_text("❌ أضف التوكن أولاً.", reply_markup=back_btn())
        else:
            msg = (f"💳 **معلومات الرصيد:**\n\n"
                   f"🔑 التوكن: `{token}`\n"
                   f"💰 **آخر حالة رصيد:** {last_bal}\n\n"
                   f"*(يتم تحديث الرصيد تلقائياً مع كل عملية سحب)*")
            await query.edit_message_text(msg, reply_markup=back_btn(), parse_mode="Markdown")
        return

    # --- 🚀 سحب الحسابات ---
    if data == "pull_api":
        user_info = DB["users"][user_id]
        token = user_info.get("token")
        count = user_info.get("max", 1)

        if not token:
            await query.edit_message_text("⚠️ أضف التوكن أولاً.", reply_markup=back_btn())
            return

        logger.info(f"🚀 User {user_id} requesting {count} accounts...") # تسجيل بداية السحب

        await query.edit_message_text(f"⏳ **جاري سحب {count} حساب...**", parse_mode="Markdown")

        accounts = []
        errors = []
        last_api_msg = ""

        for _ in range(count):
            try:
                payload = {"product_id": PRODUCT_ID, "token": token, "qty": 1, "use_master_token": False}
                req = requests.post(API_URL, json=payload, timeout=20)
                res = req.json()

                if res.get("success") and "api_response" in res:
                    acc = res["api_response"][0]
                    accounts.append(acc)

                    if "history" not in DB["users"][user_id]: DB["users"][user_id]["history"] = []
                    DB["users"][user_id]["history"].append(acc)
                    DB["stats"]["total_pulled"] += 1

                    last_api_msg = res.get("message", "تم السحب")
                    DB["users"][user_id]["balance_msg"] = last_api_msg

                    logger.info(f"✅ Pulled: {acc} | User: {user_id}") # تسجيل نجاح العملية
                else:
                    errors.append(res.get("message", "خطأ"))
                    logger.warning(f"⚠️ API Error for {user_id}: {res.get('message')}")
                    break
            except Exception as e:
                errors.append("فشل الاتصال")
                logger.error(f"❌ Connection Error for {user_id}: {e}")
                break

        save_db(DB)

        if accounts:
            archive_count = len(DB["users"][user_id]["history"])
            acc_text = "\n".join([f"`{a}`" for a in accounts])

            final_msg = (f"✅ **تم السحب بنجاح!**\n\n"
                         f"{acc_text}\n\n"
                         f"─────────────────\n"
                         f"💰 **حالة الرصيد:** {last_api_msg}\n"
                         f"📦 **في أرشيفك:** {archive_count} حساب")

            await query.edit_message_text(final_msg, parse_mode="Markdown", reply_markup=after_pull_keyboard())
        else:
            err = errors[0] if errors else "خطأ غير معروف"
            await query.edit_message_text(f"❌ **فشل:** {err}", parse_mode="Markdown", reply_markup=back_btn())

    # --- باقي الأزرار ---
    if data == "my_history":
        hist = DB["users"][user_id].get("history", [])
        if not hist:
            await query.edit_message_text("📂 أرشيفك فارغ.", reply_markup=back_btn())
        else:
            txt = "\n".join([f"`{a}`" for a in hist[-10:]])
            await query.edit_message_text(f"📂 **آخر 10 حسابات (من أصل {len(hist)}):**\n\n{txt}", parse_mode="Markdown", reply_markup=back_btn())
        return

    if data == "set_token":
        context.user_data["state"] = "waiting_token"
        await query.edit_message_text("🔑 أرسل التوكن:", reply_markup=back_btn())
        return

    if data == "set_count":
        context.user_data["state"] = "waiting_count"
        await query.edit_message_text("🔢 أرسل العدد:", reply_markup=back_btn())
        return

    # --- Admin Logic ---
    if user_id == ADMIN_ID:
        if data == "admin_stats":
            await query.edit_message_text(f"📊 اليوزرات: {len(DB['users'])}\n📦 السحب الكلي: {DB['stats']['total_pulled']}", reply_markup=admin_keyboard())
        elif data == "admin_list_users":
            msg = "📋 **المستخدمين:**\n"
            for uid, u in DB["users"].items():
                msg += f"👤 {u.get('name')} | 📦 {len(u.get('history',[]))} | ID: `{uid}`\n"
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_btn())
        elif data == "admin_add_user":
            context.user_data["state"] = "admin_adding"
            await query.edit_message_text("✍️ أرسل ID:", reply_markup=back_btn())
        elif data == "admin_del_user":
            context.user_data["state"] = "admin_deleting"
            await query.edit_message_text("🗑 أرسل ID:", reply_markup=back_btn())
        elif data == "admin_broadcast":
            context.user_data["state"] = "admin_broadcasting"
            await query.edit_message_text("📢 الرسالة:", reply_markup=back_btn())

# ====== 📩 النصوص ======
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = context.user_data.get("state")
    if not state: return

    if user_id in DB["users"]:
        if state == "waiting_token":
            DB["users"][user_id]["token"] = text
            save_db(DB)
            context.user_data["state"] = None
            logger.info(f"✏️ User {user_id} updated token")
            await update.message.reply_text("✅ تم حفظ التوكن!", reply_markup=back_btn())
            return
        if state == "waiting_count":
            if text.isdigit() and int(text) > 0:
                DB["users"][user_id]["max"] = int(text)
                save_db(DB)
                context.user_data["state"] = None
                logger.info(f"✏️ User {user_id} set count to {text}")
                await update.message.reply_text(f"✅ العدد: {text}", reply_markup=back_btn())
            return

    if user_id == ADMIN_ID:
        if state == "admin_adding":
            try:
                nid = int(text)
                if nid not in DB["users"]:
                    DB["users"][nid] = {"token": None, "max": 1, "history": [], "balance_msg": "", "name": "User"}
                    save_db(DB)
                    logger.info(f"➕ Admin added user: {nid}")
                    await update.message.reply_text("✅ تم!", reply_markup=admin_keyboard())
                else: await update.message.reply_text("⚠️ موجود!", reply_markup=admin_keyboard())
            except: pass
            context.user_data["state"] = None
        elif state == "admin_deleting":
            try:
                did = int(text)
                if did in DB["users"]:
                    del DB["users"][did]
                    save_db(DB)
                    logger.info(f"🗑 Admin deleted user: {did}")
                    await update.message.reply_text("🗑 تم!", reply_markup=admin_keyboard())
            except: pass
            context.user_data["state"] = None
        elif state == "admin_broadcasting":
            c = 0
            for uid in DB["users"]:
                try:
                    await context.bot.send_message(uid, f"📢 {text}")
                    c += 1
                except: continue
            logger.info(f"📢 Broadcast sent to {c} users")
            await update.message.reply_text(f"✅ تم النشر ({c})", reply_markup=admin_keyboard())
            context.user_data["state"] = None

# ====== 🏁 تشغيل ======
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()

    # رسالة ترحيبية في الكونسول تبين أن اللوجز اشتغلت
    print("\n" + "="*40)
    print("🚀 Bot Started! HTTP Logs are now HIDDEN.")
    print("📋 Only important actions will appear here.")
    print("="*40 + "\n")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling()

