import io
import httpx
import traceback
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_ID, API_BASE_URL, PRODUCT_ID, logger, UC_CATEGORIES
from database import db, get_user, check_maintenance, get_tracked_users, get_next_order_id, analyze_codes, log_important_action
from keyboards import (get_main_keyboard, admin_keyboard, auto_cache_keyboard, 
                       admin_users_keyboard, stock_manage_keyboard, categories_keyboard, 
                       success_pull_keyboard, back_btn, admin_back_btn, admin_users_back_btn, 
                       profile_keyboard, admin_logs_keyboard, admin_logs_back_btn, retry_keyboard)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("❌ حدث خطأ:", exc_info=context.error)
    tb_string = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    log_file = io.BytesIO(tb_string.encode('utf-8'))
    log_file.name = f"Crash_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        if update and hasattr(update, 'effective_message') and update.effective_message:
            await context.bot.send_document(chat_id=ADMIN_ID, document=log_file, caption="🚨 <b>حدث خطأ برمجي غير متوقع!</b>", parse_mode=ParseMode.HTML)
    except: pass

# ====== 🚀 دوال السحب المجمعة ======
async def process_api_pull(uid, reply_func, user, qty, context):
    role = user.get("role", "user")
    personal_tokens = list(user.get("tokens", []))
    
    # جلب التوكنات المشتركة من قاعدة البيانات
    shared_doc = await db.settings.find_one({"_id": "shared_tokens"})
    shared_tokens = shared_doc.get("tokens", []) if shared_doc else []
    
    # الحساب الذكي للتوكنات (يأخذ الشخصي أولاً، ثم المشترك)
    needed = qty
    personal_to_use = personal_tokens[:needed]
    needed -= len(personal_to_use)
    
    shared_to_use = []
    # فقط الأدمن والموظف يحق لهم استخدام التوكنات المشتركة إذا نقصت توكناتهم الشخصية
    if needed > 0 and role in ["admin", "employee"]:
        shared_to_use = shared_tokens[:needed]
        needed -= len(shared_to_use)
        
    if needed > 0:
        return await reply_func("⚠️ <b>لا يوجد توكنات كافية!</b>\n(التوكنات الشخصية والمشتركة معاً لا تكفي لإتمام العدد المطلوب).", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
        
    tokens_to_use = personal_to_use + shared_to_use
    waiting_msg = await reply_func(f"⏳ <b>جاري السحب باستخدام {len(tokens_to_use)} توكن...</b>\n<i>(شخصي: {len(personal_to_use)} | مشترك: {len(shared_to_use)})</i>", parse_mode=ParseMode.HTML)
    
    accs, raw_accs, token_logs_updates = [], [], []
    used_personal, used_shared = [], []
    
    async with httpx.AsyncClient() as client:
        tasks = [(t, client.post(f"{API_BASE_URL}/api/redeem-bulk", json={"token": t, "product": PRODUCT_ID, "qty": 1}, timeout=15.0)) for t in tokens_to_use]
        for t, req in tasks:
            if t in personal_to_use: used_personal.append(t)
            else: used_shared.append(t)
            short_t = f"{t[:8]}...{t[-4:]}"
            try:
                res = await req
                r = res.json()
                if r.get("success") and r.get("accounts"):
                    a = r["accounts"][0]
                    accs.append(f"<code>{a['email']}</code>\n<code>{a['password']}</code>")
                    raw_accs.append(f"{a['email']}:{a['password']}") 
                    token_logs_updates.append(f"✅ نجاح | {short_t} | {a['email']}")
                else:
                    token_logs_updates.append(f"❌ فشل | {short_t} | {r.get('message', 'مجهول')}")
            except Exception as e:
                token_logs_updates.append(f"⚠️ خطأ | {short_t}")

    # تحديث التوكنات وحذف ما تم استهلاكه
    db_updates = {}
    if used_personal: db_updates["$pull"] = {"tokens": {"$in": used_personal}}
    if token_logs_updates: db_updates["$push"] = {"token_logs": {"$each": token_logs_updates, "$slice": -500}}
    if db_updates: await db.users.update_one({"_id": uid}, db_updates)
    
    if used_shared:
        await db.settings.update_one({"_id": "shared_tokens"}, {"$pull": {"tokens": {"$in": used_shared}}})

    btns = [[InlineKeyboardButton(f"🔄 حساب آخر ({qty})", callback_data="pull_api_again")], [InlineKeyboardButton("✏️ تعديل العدد", callback_data="pull_api")], [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]]
    reply_markup = InlineKeyboardMarkup(btns)
    
    if accs:
        # تسجيل وحفظ الطلب
        tracked_users = await get_tracked_users()
        if uid in tracked_users and raw_accs:
            cached_docs = [{"account": raw, "added_at": datetime.now()} for raw in raw_accs]
            await db.cached_accounts.insert_many(cached_docs)
            
        order_id = await get_next_order_id()
        await db.orders.insert_one({"_id": order_id, "type": "API Pull", "user": user["name"], "user_id": uid, "items": accs, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        await db.users.update_one({"_id": uid}, {"$push": {"history": f"🚀 طلب <code>#{order_id}</code>"}, "$inc": {"stats.api": len(accs)}})
        await log_important_action(uid, user["name"], f"🚀 سحب {len(accs)} حساب API (طلب #{order_id})", " | ".join(raw_accs))
        
        display_txt = "\n━━━━━━━━━━━━\n".join(accs)
        await waiting_msg.edit_text(f"✅ <b>تم السحب بنجاح (طلب <code>#{order_id}</code>):</b>\n\n{display_txt}\n\n📝 <i>(تم حذف التوكنات المستخدمة)</i>", parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await waiting_msg.edit_text("❌ <b>فشل السحب من التوكنات.</b>", parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def process_stock_pull(uid, reply_func, user, cat, count, context):
    if await db.stock.count_documents({"category": cat}) < count: 
        return await reply_func("⚠️ <b>الكمية غير كافية في المخزن!</b>", parse_mode=ParseMode.HTML, reply_markup=back_btn())

    order_id = await get_next_order_id()
    pulled_codes = []
    for _ in range(count):
        c = await db.stock.find_one_and_delete({"category": cat})
        if c:
            code_str = str(c.get("code") or c["_id"])
            pulled_codes.append(code_str)
            await db.codes_map.insert_one({"code": code_str, "name": user["name"], "user_id": uid, "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "order_id": order_id})

    if pulled_codes:
        await db.orders.insert_one({"_id": order_id, "type": f"PUBG Stock ({cat} UC)", "user": user["name"], "user_id": uid, "items": pulled_codes, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        await db.users.update_one({"_id": uid}, {"$push": {"history": f"📦 طلب <code>#{order_id}</code>"}, "$inc": {"stats.stock": len(pulled_codes)}})
        await log_important_action(uid, user["name"], f"🎮 سحب {len(pulled_codes)} كود ({cat} UC) - طلب #{order_id}", " | ".join(pulled_codes))

        individual = "\n".join([f"🎮 <code>{c}</code>" for c in pulled_codes])
        bulk = "\n".join(pulled_codes)
        msg = f"✅ <b>تم سحب {cat} UC بنجاح!</b> (طلب <code>#{order_id}</code>)\n\n🎯 <b>نسخ كود بكود:</b>\n{individual}\n\n📋 <b>نسخ الكل دفعة واحدة:</b>\n<code>{bulk}</code>"
        return await reply_func(msg, parse_mode=ParseMode.HTML, reply_markup=success_pull_keyboard(f"pull_cat_{cat}"))

async def process_cache_pull(uid, reply_func, user, qty, context):
    await db.cached_accounts.delete_many({"added_at": {"$lt": datetime.now() - timedelta(hours=24)}})
    available = await db.cached_accounts.count_documents({})
    if qty > available: return await reply_func(f"⚠️ <b>الكمية غير كافية!</b> المتاح: <code>{available}</code>", parse_mode=ParseMode.HTML, reply_markup=back_btn())
        
    pulled_accs, raw_accs_for_log = [], []
    for _ in range(qty):
        doc = await db.cached_accounts.find_one_and_delete({}, sort=[("added_at", 1)])
        if doc: 
            raw_accs_for_log.append(doc["account"])
            try:
                e, p = doc["account"].split(":", 1)
                pulled_accs.append(f"<code>{e}</code>\n<code>{p}</code>")
            except:
                pulled_accs.append(f"<code>{doc['account']}</code>")
            
    if pulled_accs:
        await log_important_action(uid, user["name"], f"♻️ سحب {len(pulled_accs)} حساب من المخزن المحلي (24س)", " | ".join(raw_accs_for_log))
        msg = "\n━━━━━━━━━━━━\n".join(pulled_accs)
        return await reply_func(f"✅ <b>سحب {len(pulled_accs)} حساب:</b>\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=retry_keyboard("pull_cached_api", "back_home"))

# ====== 🚀 الأوامر السريعة (Shortcuts) ======
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user or user["role"] not in ["admin", "employee"]: return
    help_text = """⚡ <b>الأوامر السريعة لتسريع الشغل:</b>\n\n🎮 <b>سحب أكواد UC:</b>\n<code>/pull [الفئة] [العدد]</code>\nمثال: <code>/pull 60 5</code> (لسحب 5 أكواد 60 شدة)\n\n🚀 <b>سحب حسابات API:</b>\n<code>/api [العدد]</code>\nمثال: <code>/api 2</code>"""
    if user["role"] == "admin":
        help_text += "\n\n♻️ <b>سحب تخزين (24س):</b>\n<code>/cache [العدد]</code>\nمثال: <code>/cache 3</code>\n\n📂 <b>الرفع الذكي:</b>\nأرسل أي ملف <code>.txt</code> وسيتعرف عليه البوت لإضافته فوراً."
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def cmd_pull(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user or user["role"] not in ["admin", "employee"]: return
    if len(context.args) != 2: return await update.message.reply_text("❌ <b>صيغة خاطئة.</b> استخدم:\n<code>/pull 60 5</code>", parse_mode=ParseMode.HTML)
    cat, count_str = context.args
    if cat not in UC_CATEGORIES or not count_str.isdigit() or int(count_str) <= 0: return await update.message.reply_text("❌ <b>فئة غير صالحة أو عدد غير صحيح.</b>", parse_mode=ParseMode.HTML)
    await process_stock_pull(uid, update.message.reply_text, user, cat, int(count_str), context)

async def cmd_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user: return
    if not context.args or not context.args[0].isdigit() or int(context.args[0]) <= 0: return await update.message.reply_text("❌ <b>صيغة خاطئة.</b> استخدم:\n<code>/api 2</code>", parse_mode=ParseMode.HTML)
    qty = int(context.args[0])
    context.user_data["last_api_count"] = qty
    await process_api_pull(uid, update.message.reply_text, user, qty, context)

async def cmd_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user or user["role"] != "admin": return
    if not context.args or not context.args[0].isdigit() or int(context.args[0]) <= 0: return await update.message.reply_text("❌ <b>صيغة خاطئة.</b> استخدم:\n<code>/cache 5</code>", parse_mode=ParseMode.HTML)
    await process_cache_pull(uid, update.message.reply_text, user, int(context.args[0]), context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    user = await get_user(user_id)
    if user_id == ADMIN_ID and not user:
        new_admin = {"_id": user_id, "role": "admin", "name": name, "tokens": [], "history": [], "logs": [], "stats": {"api": 0, "stock": 0}}
        await db.users.insert_one(new_admin)
        user = new_admin
    if not user: return await update.message.reply_text("⛔ غير مسجل.")
    if user.get("name") != name: await db.users.update_one({"_id": user_id}, {"$set": {"name": name}})

    role = user.get("role", "user")
    maint_msg = "\n⚠️ <b>النظام في وضع الصيانة</b>" if await check_maintenance() else ""
    stats_msg = ""
    if role in ["admin", "employee"]:
        stock_count = await db.stock.count_documents({})
        cache_count = await db.cached_accounts.count_documents({})
        stats_msg = f"\n\n📊 <b>نظرة سريعة:</b>\n📦 المخزن: <code>{stock_count}</code> كود\n♻️ التخزين التلقائي: <code>{cache_count}</code> حساب\n💡 لمعرفة الأوامر السريعة أرسل /help"

    await update.message.reply_text(f"👋 أهلاً <b>{name}</b>\n🔹 الرتبة: {role}{maint_msg}{stats_msg}", reply_markup=get_main_keyboard(role), parse_mode=ParseMode.HTML)

# ====== 🔘 معالج الأزرار ======
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    user = await get_user(uid)
    if not user: return
    role = user.get("role", "user")

    if await check_maintenance() and role != "admin": 
        await query.answer()
        return await query.edit_message_text("⚠️ <b>الصيانة جارية...</b>", parse_mode=ParseMode.HTML)
    
    if data == "back_home":
        context.user_data.clear()
        await query.answer()
        return await query.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard(role))

    if data == "pull_cached_api" and role == "admin":
        await query.answer()
        await db.cached_accounts.delete_many({"added_at": {"$lt": datetime.now() - timedelta(hours=24)}})
        count = await db.cached_accounts.count_documents({})
        if count == 0: return await query.edit_message_text("📭 <b>المخزن فارغ</b>.", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
        context.user_data["state"] = "waiting_cached_api_count"
        return await query.edit_message_text(f"♻️ <b>المتاح الآن:</b> <code>{count}</code> حساب\n\n🔢 <b>أرسل العدد:</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

    if data == "admin_logs_hub" and role == "admin":
        await query.answer()
        context.user_data.clear()
        return await query.edit_message_text("📜 <b>مركز السجلات والبحث والتخزين</b>", reply_markup=admin_logs_keyboard(), parse_mode=ParseMode.HTML)

    if data == "admin_global_search" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_global_search"
        return await query.edit_message_text("🔍 <b>البحث الشامل الذكي:</b>\n\nأرسل أي شيء للبحث عنه:\n(<code>كود ببجي</code> / <code>رقم طلب</code> / <code>آيدي مستخدم</code>)", reply_markup=admin_logs_back_btn(), parse_mode=ParseMode.HTML)

    if data == "admin_auto_cache_menu" and role == "admin":
        await query.answer()
        return await query.edit_message_text("♻️ <b>إعدادات التخزين التلقائي</b>", reply_markup=auto_cache_keyboard(), parse_mode=ParseMode.HTML)

    if data == "list_tracked_users" and role == "admin":
        await query.answer()
        tracked = await get_tracked_users()
        txt = "\n".join([f"🆔 <code>{t}</code>" for t in tracked])
        return await query.edit_message_text(f"📋 <b>قائمة المراقبة:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_auto_cache_menu")]]), parse_mode=ParseMode.HTML)

    if data == "add_tracked_user" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_add_tracked"
        return await query.edit_message_text("✍️ <b>أرسل الآيدي المراد إضافته:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_auto_cache_menu")]]), parse_mode=ParseMode.HTML)

    if data == "remove_tracked_user" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_remove_tracked"
        return await query.edit_message_text("🗑 <b>أرسل الآيدي المراد إزالته:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_auto_cache_menu")]]), parse_mode=ParseMode.HTML)

    if data == "my_profile":
        await query.answer()
        t_count = len(user.get("tokens", []))
        st = user.get("stats", {"api": 0, "stock": 0})
        msg = f"💳 <b>حسابك:</b>\n👤 الاسم: {user.get('name')}\n🎖 الرتبة: {role}\n🔑 توكنات نشطة: <code>{t_count}</code>\n\n🛒 <b>السحوبات:</b>\n🎮 أكواد مسحوبة: <code>{st.get('stock',0)}</code>\n🚀 حسابات API: <code>{st.get('api',0)}</code>"
        return await query.edit_message_text(msg, reply_markup=profile_keyboard(role), parse_mode=ParseMode.HTML)

    if data == "view_my_tokens":
        await query.answer()
        tokens = user.get("tokens", [])
        txt = "\n".join([f"🔑 <code>{t[:8]}...{t[-4:]}</code>" for t in tokens]) if tokens else "📭 لا يوجد لديك توكنات نشطة."
        btns = [[InlineKeyboardButton("➕ إضافة توكن", callback_data="add_tokens")], [InlineKeyboardButton("📜 سجل التوكنات", callback_data="view_token_logs")]]
        if tokens: btns.append([InlineKeyboardButton("🗑 حذف جميع توكناتي", callback_data="clear_tokens")])
        btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_home")])
        return await query.edit_message_text(f"📋 <b>توكناتك الحالية ({len(tokens)}):</b>\n\n{txt}" if tokens else txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    if data == "view_token_logs":
        await query.answer()
        logs = user.get("token_logs", [])
        if not logs: return await query.edit_message_text("📭 لا يوجد سجل للتوكنات حتى الآن.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع لتوكناتي", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)
        txt = "\n".join(logs[-30:])
        return await query.edit_message_text(f"📜 <b>سجل نشاط التوكنات:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع لتوكناتي", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)

    if data == "clear_tokens":
        await query.answer()
        await db.users.update_one({"_id": uid}, {"$set": {"tokens": []}})
        return await query.edit_message_text("🗑 <b>تم حذف جميع التوكنات.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)

    if data == "add_tokens":
        await query.answer()
        context.user_data["state"] = "waiting_tokens"
        return await query.edit_message_text("📝 <b>أرسل التوكنات:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)

    if data == "my_history":
        await query.answer()
        hist = user.get("history", [])
        txt = "\n".join([f"<code>{h}</code>" for h in hist[-10:]]) if hist else "📂 أرشيفك فارغ."
        btns = [[InlineKeyboardButton("🔍 البحث عن طلب (بالرقم)", callback_data="check_order_id")], [InlineKeyboardButton("🔙 رجوع", callback_data="my_profile")]]
        return await query.edit_message_text(f"📂 <b>آخر 10 عمليات:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    if data == "check_order_id":
        await query.answer()
        context.user_data["state"] = "waiting_order_id"
        return await query.edit_message_text("🔍 <b>أرسل رقم الطلب المراد كشفه:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للأرشيف", callback_data="my_history")]]), parse_mode=ParseMode.HTML)

    if data == "return_order" and role in ["admin", "employee"]:
        await query.answer()
        context.user_data["state"] = "waiting_return_order_id"
        return await query.edit_message_text("↩️ <b>نظام المرتجعات السريع</b>\n\nأرسل <b>رقم الطلب (Order ID)</b> الذي تريد إرجاعه.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="my_profile")]]), parse_mode=ParseMode.HTML)

    if data == "pull_stock_menu" and role in ["admin", "employee"]: 
        await query.answer()
        return await query.edit_message_text("🎮 <b>اختر الفئة للسحب:</b>", reply_markup=await categories_keyboard("pull_cat", db), parse_mode=ParseMode.HTML)
    
    if data.startswith("pull_cat_") and role in ["admin", "employee"]:
        await query.answer()
        cat = data.split("_")[-1]
        context.user_data["state"] = "waiting_stock_count"
        context.user_data["target_pull_cat"] = cat
        return await query.edit_message_text(f"🔢 <b>أرسل العدد لـ {cat} UC:</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

    if data == "pull_api":
        await query.answer()
        tokens = user.get("tokens", [])
        shared_doc = await db.settings.find_one({"_id": "shared_tokens"})
        shared_tokens = shared_doc.get("tokens", []) if shared_doc else []
        
        if not tokens and (role == "user" or not shared_tokens):
             return await query.edit_message_text("⚠️ <b>لا يوجد توكنات متاحة!</b> أضف توكن أولاً.", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
             
        context.user_data["state"] = "waiting_api_count"
        return await query.edit_message_text("🔢 <b>أرسل عدد الحسابات التي تريد سحبها الآن:</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

    if data == "pull_api_again":
        await query.answer()
        qty = context.user_data.get("last_api_count", 1)
        await process_api_pull(uid, query.message.reply_text, user, qty, context)
        return

    if data == "admin_panel" and role == "admin":
        await query.answer()
        st = await db.stock.count_documents({})
        return await query.edit_message_text(f"🛠 <b>الأدمن</b>\n📦 المخزن: <code>{st}</code>", reply_markup=await admin_keyboard(), parse_mode=ParseMode.HTML)
    
    if data == "admin_stock_menu" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("📦 <b>المخزن:</b>", reply_markup=stock_manage_keyboard(), parse_mode=ParseMode.HTML)
    
    if data == "admin_choose_cat_manual" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("🔢 <b>اختر الفئة للإضافة اليدوية:</b>", reply_markup=await categories_keyboard("admin_add_manual", db), parse_mode=ParseMode.HTML)
    
    if data == "admin_choose_cat_file" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("📂 <b>الرفع الذكي:</b>\n\nقم بإرسال ملف <code>.txt</code> مباشرة هنا في الشات، وسيسألك البوت عن الفئة تلقائياً بدون الحاجة لهذه القائمة.", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)
    
    if data == "admin_choose_cat_clear" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("🗑 <b>اختر الفئة لتصفيرها:</b>", reply_markup=await categories_keyboard("admin_clear_cat", db), parse_mode=ParseMode.HTML)

    if data.startswith("admin_add_manual_") and role == "admin":
        await query.answer()
        cat = data.split("_")[-1]
        context.user_data["state"] = "adding_stock_manual"
        context.user_data["target_cat"] = cat
        return await query.edit_message_text(f"✍️ <b>أرسل أكواد {cat} UC:</b>", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)

    if data.startswith("admin_clear_cat_") and role == "admin":
        await query.answer()
        cat = data.split("_")[-1]
        await db.stock.delete_many({"category": cat})
        return await query.edit_message_text(f"🗑 <b>تم تصفير فئة {cat} UC بنجاح.</b>", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)

    if data.startswith("smart_cat_") and role == "admin":
        await query.answer()
        cat = data.split("_")[-1]
        lines = context.user_data.get("smart_upload_lines")
        if not lines: return await query.edit_message_text("❌ حدث خطأ، أرسل الملف مجدداً.")
        await query.edit_message_text("⏳ <b>جاري فحص الأكواد...</b>", parse_mode=ParseMode.HTML)
        new_codes, dupes, all_codes = await analyze_codes(lines)
        context.user_data["pending_stock"] = {"all": all_codes, "new": new_codes, "dupes": dupes, "cat": cat} 
        btns = [[InlineKeyboardButton("✅ استيراد الكل (حتى المكرر)", callback_data="confirm_add_all")], [InlineKeyboardButton("✨ استيراد الجديد فقط", callback_data="confirm_add_new")]]
        if dupes: btns.append([InlineKeyboardButton("👁️ عرض الأكواد المكررة", callback_data="show_dupes_list")])
        btns.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")])
        msg = f"📂 <b>تقرير الرفع الذكي ({cat} UC):</b>\n\nإجمالي الأكواد: <code>{len(all_codes)}</code>\n✅ أكواد جديدة: <code>{len(new_codes)}</code>\n⚠️ أكواد مكررة/مسحوبة: <code>{len(dupes)}</code>\n\n❓ ماذا تريد أن تفعل؟"
        return await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    if data in ["confirm_add_all", "confirm_add_new"] and role == "admin":
        await query.answer()
        pending = context.user_data.get("pending_stock")
        if pending:
            target_list = pending["all"] if data == "confirm_add_all" else pending["new"]
            docs = [{"code": c, "category": pending["cat"], "added_at": datetime.now()} for c in target_list]
            if docs: 
                try: await db.stock.insert_many(docs, ordered=False) 
                except Exception as e: logger.error(e)
            await log_important_action(uid, user["name"], f"📥 إضافة {len(docs)} كود لفئة {pending['cat']} UC")

        context.user_data.clear()
        btns = [[InlineKeyboardButton("➕ إضافة المزيد من الأكواد", callback_data="admin_choose_cat_manual")], [InlineKeyboardButton("🔙 رجوع للمخزن", callback_data="admin_stock_menu")]]
        return await query.edit_message_text(f"✅ <b>تم إضافة الأكواد بنجاح.</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
        
    if data == "show_dupes_list" and role == "admin":
        pending = context.user_data.get("pending_stock")
        if not pending or not pending.get("dupes"): return await query.answer("لا يوجد أكواد مكررة!", show_alert=True)
        dupes_list = pending["dupes"]
        txt = "\n".join([f"<code>{d}</code>" for d in dupes_list[:50]])
        if len(dupes_list) > 50: txt += f"\n... و {len(dupes_list)-50} أكواد أخرى."
        await query.answer() 
        return await query.message.reply_text(f"⚠️ <b>الأكواد المكررة ({len(dupes_list)} كود):</b>\n\n{txt}", parse_mode=ParseMode.HTML)

    if data == "cancel_add_stock" and role == "admin":
        await query.answer()
        context.user_data.clear()
        return await query.edit_message_text("❌ <b>تم الإلغاء.</b>", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)

    if data == "admin_users_menu" and role == "admin":
        await query.answer()
        context.user_data.clear()
        c = await db.users.count_documents({})
        msg = f"👥 <b>إدارة المستخدمين</b> (الإجمالي: <code>{c}</code>)\n\n"
        msg += "📋 <b>قائمة المستخدمين الحالية:</b>\n"
        
        async for u in db.users.find().sort("_id", -1).limit(20):
             ic = "👮‍♂️" if u.get('role') == "admin" else "👤" if u.get('role') == "employee" else "🆕"
             msg += f"{ic} <code>{u['_id']}</code> | {u.get('name', 'بدون اسم')}\n"
             
        msg += "\n⚙️ <b>اختر الإجراء المطلوب من الأزرار أدناه:</b>"
        return await query.edit_message_text(msg, reply_markup=admin_users_keyboard(), parse_mode=ParseMode.HTML)

    if data in ["admin_add_user_btn", "admin_remove_user_btn", "admin_search_manage_user", "admin_get_user_logs_btn"] and role == "admin":
        await query.answer()
        states = {
            "admin_add_user_btn": ("waiting_add_user_id", "✍️ <b>أرسل الآيدي (ID) لإضافته:</b>"),
            "admin_remove_user_btn": ("waiting_remove_user_id", "🗑 <b>أرسل الآيدي (ID) لحذفه:</b>"),
            "admin_search_manage_user": ("waiting_manage_user_id", "🔍 <b>أرسل الآيدي (ID) للتحكم وتعديل الرتبة:</b>"),
            "admin_get_user_logs_btn": ("waiting_user_logs_id", "📜 <b>أرسل الآيدي لاستخراج سجلاته:</b>")
        }
        context.user_data["state"] = states[data][0]
        return await query.edit_message_text(states[data][1], reply_markup=admin_users_back_btn(), parse_mode=ParseMode.HTML)

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
        return await query.answer("✅ تم مسح أرشيفه وسجلاته", show_alert=True)

    if data.startswith("set_role_") and role == "admin":
        await query.answer()
        new_uid = context.user_data.get("new_user_id")
        if not new_uid: return
        r = "employee" if data == "set_role_employee" else "user"
        await db.users.insert_one({"_id": new_uid, "role": r, "name": "User", "tokens": [], "history": [], "logs": [], "token_logs": [], "stats": {"api":0,"stock":0}})
        context.user_data.clear()
        return await query.edit_message_text(f"✅ تم إضافة الحساب <code>{new_uid}</code> كرتبة <b>{r}</b>.", reply_markup=retry_keyboard("admin_add_user_btn", "admin_users_menu"), parse_mode=ParseMode.HTML)

    if data == "admin_get_logs" and role == "admin":
        await query.answer()
        await query.edit_message_text("⏳ <b>جاري جلب السجلات...</b>", parse_mode=ParseMode.HTML)
        logs = await db.system_logs.find().sort("timestamp", -1).limit(15).to_list(length=15)
        if not logs: return await query.edit_message_text("📭 لا توجد سجلات.", reply_markup=admin_logs_back_btn(), parse_mode=ParseMode.HTML)
        
        rep = "📝 <b>أحدث العمليات في النظام:</b>\n\n"
        for l in logs:
            rep += f"👤 <b>{l['name']}</b> | ⏱ {l['time']}\n🔹 {l['action']}\n"
            if l.get('details'): rep += f"└ <code>{l['details']}</code>\n"
            rep += "───────────\n"
            
        if len(rep) > 4000: rep = rep[:4000] + "\n..."
        btns = [[InlineKeyboardButton("🔄 تحديث السجلات", callback_data="admin_get_logs")], [InlineKeyboardButton("🔙 رجوع", callback_data="admin_logs_hub")]]
        return await query.edit_message_text(rep, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

# ====== 📩 معالج الرسائل النصية ======
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    uid = update.effective_user.id
    txt = update.message.text.strip()
    state = context.user_data.get("state")
    
    user = await get_user(uid)
    if not user: return
    
    if not state: return await update.message.reply_text("💡 يرجى اختيار عملية من القائمة أولاً.", reply_markup=back_btn())

    if state == "waiting_add_tracked" and user["role"] == "admin":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل آيدي صحيح.", reply_markup=retry_keyboard("add_tracked_user", "admin_auto_cache_menu"))
        target_id = int(txt)
        await db.settings.update_one({"_id": "cache_config"}, {"$addToSet": {"tracked_users": target_id}}, upsert=True)
        context.user_data.clear()
        return await update.message.reply_text(f"✅ تم إضافة <code>{target_id}</code> للمراقبة.", parse_mode=ParseMode.HTML, reply_markup=retry_keyboard("add_tracked_user", "admin_auto_cache_menu"))

    elif state == "waiting_remove_tracked" and user["role"] == "admin":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل آيدي صحيح.", reply_markup=retry_keyboard("remove_tracked_user", "admin_auto_cache_menu"))
        target_id = int(txt)
        await db.settings.update_one({"_id": "cache_config"}, {"$pull": {"tracked_users": target_id}}, upsert=True)
        context.user_data.clear()
        return await update.message.reply_text(f"🗑 تم إزالة <code>{target_id}</code>.", parse_mode=ParseMode.HTML, reply_markup=retry_keyboard("remove_tracked_user", "admin_auto_cache_menu"))

    elif state == "waiting_cached_api_count" and user["role"] == "admin":
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        await process_cache_pull(uid, update.message.reply_text, user, int(txt), context)

    # 🔍 البحث الشامل الذكي
    elif state == "waiting_global_search" and user["role"] == "admin":
        if txt.isdigit():
            order = await db.orders.find_one({"_id": int(txt)})
            if order:
                items_str = "\n".join([f"<code>{i}</code>" for i in order["items"]])
                res_msg = f"📄 <b>تقرير الطلب <code>#{txt}</code></b>\n👤 بواسطة: <code>{order['user']}</code>\n⬇️ العناصر:\n{items_str}"
                return await update.message.reply_text(res_msg, reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)
            
            target = await get_user(int(txt))
            if target:
                msg = f"👤 <b>الاسم:</b> {target.get('name')}\n🆔 <code>{target['_id']}</code>\n🎖 <b>الرتبة:</b> {target['role']}\n🔑 <b>التوكنات:</b> <code>{len(target.get('tokens',[]))}</code>"
                btns = [
                    [InlineKeyboardButton("🗑 تصفير التوكنات", callback_data=f"manage_clear_tokens_{target['_id']}"), InlineKeyboardButton("🔄 تغيير الرتبة", callback_data=f"manage_switch_role_{target['_id']}")],
                    [InlineKeyboardButton("🗑 مسح السجلات", callback_data=f"manage_clear_logs_{target['_id']}")],
                    [InlineKeyboardButton("🔄 بحث آخر", callback_data="admin_global_search")], [InlineKeyboardButton("🔙 رجوع", callback_data="admin_logs_hub")]
                ]
                return await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

        records = await db.codes_map.find({"$or": [{"_id": txt}, {"code": txt}]}).to_list(None)
        in_stock = await db.stock.count_documents({"$or": [{"_id": txt}, {"code": txt}]})
        
        if not records and in_stock == 0:
            await update.message.reply_text("❌ <b>لم يتم العثور على أي نتائج!</b> (لا يوجد طلب، أو مستخدم، أو كود بهذا النص).", reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)
        else:
            msg = f"🔍 <b>نتيجة البحث عن الكود:</b>\n<code>{txt}</code>\n\n"
            if in_stock > 0: msg += f"📦 <b>موجود حالياً في المخزن</b> (العدد: <code>{in_stock}</code>)\n\n"
            if records:
                msg += f"🛒 <b>سجل السحوبات ({len(records)} مرات سحب):</b>\n"
                for i, r in enumerate(records, 1):
                    msg += f"--- السحبة #{i} ---\n👤 بواسطة: <code>{r['name']}</code>\n📅 الوقت: {r['time']}\n📦 رقم الطلب: <code>{r.get('order_id')}</code>\n\n"
            else: msg += "لم يتم سحبه حتى الآن.\n"
            await update.message.reply_text(msg, reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)
        context.user_data.clear()

    elif state == "waiting_order_id":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=retry_keyboard("check_order_id", "my_history"))
        order = await db.orders.find_one({"_id": int(txt)})
        if order and (order["user_id"] == uid or user["role"] == "admin"):
            items_str = "\n".join([f"<code>{i}</code>" for i in order["items"]])
            res_msg = f"📄 <b>الطلب <code>#{txt}</code></b>\n📅 {order['date']}\n⬇️ العناصر:\n{items_str}"
        else: res_msg = "❌ الطلب غير موجود أو يخص شخصاً آخر."
        context.user_data.clear()
        return await update.message.reply_text(res_msg, reply_markup=retry_keyboard("check_order_id", "my_history"), parse_mode=ParseMode.HTML)

    elif state == "waiting_return_order_id":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        order = await db.orders.find_one({"_id": int(txt)})
        if not order or (order["user_id"] != uid and user["role"] != "admin"): return await update.message.reply_text("❌ الطلب غير موجود أو لا تملك صلاحية.", reply_markup=back_btn())
        if "PUBG Stock" not in order["type"]: return await update.message.reply_text("❌ لا يمكن إرجاع هذا النوع من الطلبات.", reply_markup=back_btn())
            
        order_time = datetime.strptime(order['date'], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - order_time).total_seconds() > 900 and user["role"] != "admin":
            return await update.message.reply_text("⏳ <b>انتهت مهلة الإرجاع (15 دقيقة).</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
            
        cat = order["type"].split("(")[1].split(" ")[0]
        codes_to_return = [{"code": code, "category": cat, "added_at": datetime.now()} for code in order["items"]]
        
        await db.stock.insert_many(codes_to_return, ordered=False) 
        await db.codes_map.delete_many({"$or": [{"_id": {"$in": order["items"]}}, {"code": {"$in": order["items"]}}], "order_id": int(txt)}) 
        await db.orders.delete_one({"_id": int(txt)}) 
        await db.users.update_one({"_id": uid}, {"$inc": {"stats.stock": -len(order["items"])}}) 
        await log_important_action(uid, user["name"], f"↩️ إرجاع طلب #{txt} للمخزن", f"العدد: {len(order['items'])}")
        
        context.user_data.clear()
        return await update.message.reply_text(f"✅ <b>تم إرجاع الطلب <code>#{txt}</code> للمخزن بنجاح!</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

    elif state == "waiting_stock_count":
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        count = int(txt)
        cat = context.user_data.get("target_pull_cat")
        context.user_data.clear() 
        await process_stock_pull(uid, update.message.reply_text, user, cat, count, context)

    elif state == "waiting_api_count":
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=retry_keyboard("pull_api", "back_home"))
        qty = int(txt)
        context.user_data.clear()
        context.user_data["last_api_count"] = qty
        await process_api_pull(uid, update.message.reply_text, user, qty, context)

    elif state == "waiting_tokens":
        lines = [t.strip() for t in txt.splitlines() if t.strip()]
        if lines: await db.users.update_one({"_id": uid}, {"$addToSet": {"tokens": {"$each": lines}}})
        context.user_data.clear()
        return await update.message.reply_text(f"✅ <b>تم إضافة التوكنات.</b>", reply_markup=retry_keyboard("add_tokens", "view_my_tokens"), parse_mode=ParseMode.HTML)

    elif state == "waiting_add_user_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        new_uid = int(txt)
        if await get_user(new_uid): return await update.message.reply_text("⚠️ هذا المستخدم موجود بالفعل!", reply_markup=retry_keyboard("admin_add_user_btn", "admin_users_menu"))
        context.user_data["new_user_id"] = new_uid
        btns = [[InlineKeyboardButton("موظف 👤", callback_data="set_role_employee")], [InlineKeyboardButton("مستخدم عادي 🆕", callback_data="set_role_user")]]
        return await update.message.reply_text(f"👤 <b>اختر الرتبة للآيدي:</b> <code>{new_uid}</code>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    elif state == "waiting_remove_user_id" and uid == ADMIN_ID:
        if txt.isdigit():
            await db.users.delete_one({"_id": int(txt)})
            context.user_data.clear()
            return await update.message.reply_text(f"🗑 تم الحذف بنجاح.", reply_markup=retry_keyboard("admin_remove_user_btn", "admin_users_menu"))

    elif state == "waiting_manage_user_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target:
            msg = f"👤 <b>الاسم:</b> {target.get('name')}\n🆔 <code>{target['_id']}</code>\n🎖 <b>الرتبة:</b> {target['role']}\n🔑 <b>التوكنات:</b> <code>{len(target.get('tokens',[]))}</code>"
            btns = [
                [InlineKeyboardButton("🗑 تصفير التوكنات", callback_data=f"manage_clear_tokens_{target['_id']}"), InlineKeyboardButton("🔄 تغيير الرتبة", callback_data=f"manage_switch_role_{target['_id']}")],
                [InlineKeyboardButton("🗑 مسح السجلات", callback_data=f"manage_clear_logs_{target['_id']}")],
                [InlineKeyboardButton("🔍 إدارة مستخدم آخر", callback_data="admin_search_manage_user")], [InlineKeyboardButton("🔙 رجوع", callback_data="admin_users_menu")]
            ]
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("❌ الحساب غير موجود.", reply_markup=retry_keyboard("admin_search_manage_user", "admin_users_menu"))
        context.user_data.clear()

    elif state == "waiting_user_logs_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target and target.get("logs"):
            logs_txt = "\n\n".join(target["logs"][-15:]) 
            await update.message.reply_text(f"📜 <b>سجلات (<code>{txt}</code>):</b>\n\n{logs_txt}", reply_markup=retry_keyboard("admin_get_user_logs_btn", "admin_users_menu"), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("📭 لا توجد سجلات لهذا الحساب.", reply_markup=retry_keyboard("admin_get_user_logs_btn", "admin_users_menu"))
        context.user_data.clear()

    elif state == "adding_stock_manual" and uid == ADMIN_ID:
        lines = [c.strip() for c in txt.splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        if cat and lines:
            waiting_msg = await update.message.reply_text("⏳ <b>جاري فحص الأكواد...</b>", parse_mode=ParseMode.HTML)
            new_codes, dupes, all_codes = await analyze_codes(lines)
            context.user_data["pending_stock"] = {"all": all_codes, "new": new_codes, "dupes": dupes, "cat": cat} 
            btns = [[InlineKeyboardButton("✅ إضافة الكل (حتى المكرر)", callback_data="confirm_add_all")], [InlineKeyboardButton("✨ إضافة الجديد فقط", callback_data="confirm_add_new")]]
            if dupes: btns.append([InlineKeyboardButton("👁️ عرض الأكواد المكررة", callback_data="show_dupes_list")])
            btns.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")])
            msg = f"📊 <b>تقرير الأكواد المدخلة:</b>\n\nإجمالي الأكواد: <code>{len(all_codes)}</code>\n✅ أكواد جديدة: <code>{len(new_codes)}</code>\n⚠️ أكواد مكررة/مسحوبة: <code>{len(dupes)}</code>\n\n❓ ماذا تريد أن تفعل؟"
            return await waiting_msg.edit_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

# ====== 📂 الرفع الذكي للملفات ======
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID: return
    
    doc = update.message.document
    if not doc.file_name.endswith(".txt"): return
    
    waiting_msg = await update.message.reply_text("⏳ <b>جاري قراءة الملف الذكي...</b>", parse_mode=ParseMode.HTML)
    file = await doc.get_file()
    content = await file.download_as_bytearray()
    lines = [c.strip() for c in content.decode("utf-8", errors="ignore").splitlines() if c.strip()]
    if not lines: return await waiting_msg.edit_text("❌ الملف فارغ!")
    
    context.user_data["smart_upload_lines"] = lines
    btns, row = [], []
    for cat in UC_CATEGORIES:
        row.append(InlineKeyboardButton(f"{cat} UC", callback_data=f"smart_cat_{cat}"))
        if len(row) == 3:
            btns.append(row)
            row = []
    if row: btns.append(row)
    btns.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")])
    
    await waiting_msg.edit_text(f"📂 <b>تم استلام ملف (<code>{len(lines)}</code> كود)</b>\n\n🎯 <b>اختر الفئة لإضافة الأكواد إليها:</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
