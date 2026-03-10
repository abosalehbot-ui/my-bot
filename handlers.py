import io
import re
import httpx
import traceback
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_ID, API_BASE_URL, PRODUCT_ID, logger
from database import db, get_user, check_maintenance, get_tracked_users, get_next_order_id, analyze_codes, log_important_action, get_dynamic_categories
from keyboards import (get_main_keyboard, admin_keyboard, auto_cache_keyboard, 
                       admin_users_keyboard, stock_manage_keyboard, categories_keyboard, 
                       success_pull_keyboard, back_btn, admin_back_btn, admin_users_back_btn, 
                       profile_keyboard, admin_logs_keyboard, admin_logs_back_btn, retry_keyboard,
                       shared_tokens_keyboard)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("❌ حدث خطأ:", exc_info=context.error)
    tb_string = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    log_file = io.BytesIO(tb_string.encode('utf-8'))
    log_file.name = f"Crash_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        if update and hasattr(update, 'effective_message') and update.effective_message:
            await context.bot.send_document(chat_id=ADMIN_ID, document=log_file, caption="🚨 <b>حدث خطأ برمجي غير متوقع!</b>", parse_mode=ParseMode.HTML)
    except: pass

async def process_api_pull(uid, reply_func, user, qty, context):
    role = user.get("role", "user")
    pending_qty = context.user_data.get("pending_topup_qty", 0)
    if pending_qty > 0:
        await db.users.update_one({"_id": uid}, {"$inc": {"stats.topups": pending_qty}})
        context.user_data.pop("pending_topup_qty", None)

    personal_tokens = list(user.get("tokens", []))
    shared_doc = await db.settings.find_one({"_id": "shared_tokens"})
    shared_tokens = shared_doc.get("tokens", []) if shared_doc else []
    
    needed = qty
    personal_to_use = personal_tokens[:needed]
    needed -= len(personal_to_use)
    
    shared_to_use = []
    if needed > 0 and role in ["admin", "employee"]:
        shared_to_use = shared_tokens[:needed]
        needed -= len(shared_to_use)
        
    if needed > 0:
        return await reply_func("⚠️ <b>لا يوجد توكنات كافية!</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
        
    tokens_to_use = personal_to_use + shared_to_use
    waiting_msg = await reply_func(f"⏳ <b>جاري السحب باستخدام {len(tokens_to_use)} توكن...</b>", parse_mode=ParseMode.HTML)
    
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

    db_updates = {}
    if used_personal: db_updates["$pull"] = {"tokens": {"$in": used_personal}}
    if token_logs_updates: db_updates["$push"] = {"token_logs": {"$each": token_logs_updates, "$slice": -500}}
    if db_updates: await db.users.update_one({"_id": uid}, db_updates)
    
    if used_shared:
        await db.settings.update_one({"_id": "shared_tokens"}, {"$pull": {"tokens": {"$in": used_shared}}})

    if accs:
        tracked_users = await get_tracked_users()
        if uid in tracked_users and raw_accs:
            cached_docs = [{"account": raw, "added_at": datetime.now()} for raw in raw_accs]
            await db.cached_accounts.insert_many(cached_docs)
            
        order_id = await get_next_order_id()
        await db.orders.insert_one({"_id": order_id, "type": "API Pull", "user": user["name"], "user_id": uid, "items": accs, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        await db.users.update_one({"_id": uid}, {"$push": {"history": f"🚀 طلب <code>#{order_id}</code>"}, "$inc": {"stats.api": len(accs)}})
        await log_important_action(uid, user["name"], f"🚀 سحب {len(accs)} حساب API (طلب #{order_id})", " | ".join(raw_accs))
        
        context.user_data["pending_topup_qty"] = len(accs)
        btns = [
            [InlineKeyboardButton("✅ تم الشحن (دن)", callback_data="topup_done"), InlineKeyboardButton("❌ متمتش (مشكلة)", callback_data="topup_failed")],
            [InlineKeyboardButton(f"🔄 سحب حساب آخر ({qty})", callback_data="pull_api_again")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
        ]
        display_txt = "\n━━━━━━━━━━━━\n".join(accs)
        await waiting_msg.edit_text(f"✅ <b>تم السحب بنجاح (طلب <code>#{order_id}</code>):</b>\n\n{display_txt}", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btns))
    else:
        btns = [[InlineKeyboardButton(f"🔄 محاولة أخرى ({qty})", callback_data="pull_api_again")], [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]]
        await waiting_msg.edit_text("❌ <b>فشل السحب من التوكنات.</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btns))

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
            await db.codes_map.insert_one({"code": code_str, "name": user["name"], "user_id": uid, "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "order_id": order_id, "source": "Bot"})

    if pulled_codes:
        await db.orders.insert_one({"_id": order_id, "type": f"Bot Stock ({cat})", "user": user["name"], "user_id": uid, "items": pulled_codes, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        await db.users.update_one({"_id": uid}, {"$push": {"history": f"📦 طلب <code>#{order_id}</code>"}, "$inc": {"stats.stock": len(pulled_codes)}})
        await log_important_action(uid, user["name"], f"🎮 سحب {len(pulled_codes)} كود ({cat}) - طلب #{order_id}", " | ".join(pulled_codes))

        individual = "\n".join([f"🎮 <code>{c}</code>" for c in pulled_codes])
        bulk = "\n".join(pulled_codes)
        msg = f"✅ <b>تم سحب {cat} بنجاح!</b> (طلب <code>#{order_id}</code>)\n\n🎯 <b>نسخ كود بكود:</b>\n{individual}\n\n📋 <b>نسخ الكل دفعة واحدة:</b>\n<code>{bulk}</code>"
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
        await log_important_action(uid, user["name"], f"♻️ سحب {len(pulled_accs)} حساب تخزين (24س)", " | ".join(raw_accs_for_log))
        msg = "\n━━━━━━━━━━━━\n".join(pulled_accs)
        return await reply_func(f"✅ <b>سحب {len(pulled_accs)} حساب:</b>\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=retry_keyboard("pull_cached_api", "back_home"))

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user or user["role"] not in ["admin", "employee"]: return
    help_text = """⚡ <b>الأوامر السريعة لتسريع الشغل:</b>\n\n🎮 <b>سحب أكواد:</b>\n<code>/pull [الفئة] [العدد]</code>\nمثال: <code>/pull 60_uc 5</code>\n\n🚀 <b>سحب حسابات API:</b>\n<code>/api [العدد]</code>"""
    if user["role"] == "admin": help_text += "\n\n♻️ <b>سحب تخزين (24س):</b>\n<code>/cache [العدد]</code>\n\n📂 <b>الرفع الذكي:</b>\nأرسل أي ملف <code>.txt</code> وسيتعرف عليه البوت."
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def cmd_pull(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user or user["role"] not in ["admin", "employee"]: return
    if len(context.args) != 2: return await update.message.reply_text("❌ <b>استخدم:</b> <code>/pull 60_uc 5</code>", parse_mode=ParseMode.HTML)
    cat, count_str = context.args
    
    stock_keys = await get_dynamic_categories()
    if cat not in stock_keys or not count_str.isdigit() or int(count_str) <= 0: 
        return await update.message.reply_text("❌ <b>فئة غير صالحة أو عدد غير صحيح.</b>", parse_mode=ParseMode.HTML)
    await process_stock_pull(uid, update.message.reply_text, user, cat, int(count_str), context)

async def cmd_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user: return
    if not context.args or not context.args[0].isdigit() or int(context.args[0]) <= 0: return await update.message.reply_text("❌ <b>استخدم:</b> <code>/api 2</code>", parse_mode=ParseMode.HTML)
    qty = int(context.args[0])
    context.user_data["last_api_count"] = qty
    await process_api_pull(uid, update.message.reply_text, user, qty, context)

async def cmd_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user or user["role"] != "admin": return
    if not context.args or not context.args[0].isdigit() or int(context.args[0]) <= 0: return await update.message.reply_text("❌ <b>استخدم:</b> <code>/cache 5</code>", parse_mode=ParseMode.HTML)
    await process_cache_pull(uid, update.message.reply_text, user, int(context.args[0]), context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    context.user_data.clear() 
    
    user = await get_user(user_id)
    if user_id == ADMIN_ID and not user:
        new_admin = {"_id": user_id, "role": "admin", "name": name, "tokens": [], "history": [], "logs": [], "stats": {"api": 0, "stock": 0, "topups": 0}}
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
        stats_msg = f"\n\n📊 <b>نظرة سريعة:</b>\n📦 المخزن: <code>{stock_count}</code> كود\n♻️ التخزين التلقائي: <code>{cache_count}</code> حساب"

    await update.message.reply_text(f"👋 أهلاً <b>{name}</b>\n🔹 الرتبة: {role}{maint_msg}{stats_msg}", reply_markup=get_main_keyboard(role), parse_mode=ParseMode.HTML)

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

    if data == "topup_done":
        qty = context.user_data.get("pending_topup_qty", 0)
        if qty > 0:
            await db.users.update_one({"_id": uid}, {"$inc": {"stats.topups": qty}})
            context.user_data.pop("pending_topup_qty", None)
        await query.answer("✅ تم احتساب الشحنة بنجاح!", show_alert=True)
        new_btns = [[InlineKeyboardButton("🔄 سحب حساب آخر", callback_data="pull_api_again")], [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]]
        return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_btns))

    if data == "topup_failed":
        context.user_data.pop("pending_topup_qty", None)
        await query.answer("❌ تم الإلغاء، لم يتم احتساب هذه الشحنة.", show_alert=True)
        new_btns = [[InlineKeyboardButton("🔄 سحب حساب آخر", callback_data="pull_api_again")], [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]]
        return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_btns))

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
        return await query.edit_message_text("📜 <b>مركز السجلات والبحث</b>", reply_markup=admin_logs_keyboard(), parse_mode=ParseMode.HTML)

    if data == "admin_shared_tokens_menu" and role == "admin":
        await query.answer()
        doc = await db.settings.find_one({"_id": "shared_tokens"})
        count = len(doc.get("tokens", [])) if doc else 0
        return await query.edit_message_text(f"🔗 <b>إدارة التوكنات المشتركة</b>\n\nالعدد الحالي: <code>{count}</code> توكن", reply_markup=shared_tokens_keyboard(), parse_mode=ParseMode.HTML)

    if data == "view_shared_tokens" and role == "admin":
        await query.answer()
        doc = await db.settings.find_one({"_id": "shared_tokens"})
        tokens = doc.get("tokens", []) if doc else []
        if not tokens: return await query.edit_message_text("📭 <b>لا يوجد توكنات.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)
        txt = "\n".join([f"<code>{t}</code>" for t in tokens[:100]])
        return await query.edit_message_text(f"📋 <b>التوكنات:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)

    if data == "add_shared_tokens_btn" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_shared_tokens"
        return await query.edit_message_text("📝 <b>أرسل التوكنات:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)

    if data == "clear_shared_tokens" and role == "admin":
        await query.answer()
        await db.settings.update_one({"_id": "shared_tokens"}, {"$set": {"tokens": []}}, upsert=True)
        return await query.edit_message_text("🗑 <b>تم تصفير التوكنات.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)

    if data == "admin_global_search" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_global_search"
        return await query.edit_message_text("🔍 <b>البحث الشامل:</b>\n\nأرسل (<code>كود</code> / <code>رقم طلب</code> / <code>آيدي مستخدم</code>)", reply_markup=admin_logs_back_btn(), parse_mode=ParseMode.HTML)

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
        st = user.get("stats", {"api": 0, "stock": 0, "topups": 0})
        msg = f"💳 <b>حسابك:</b>\n👤 الاسم: {user.get('name')}\n🎖 الرتبة: {role}\n🔑 توكنات: <code>{t_count}</code>\n\n🛒 <b>السحوبات:</b>\n🎮 أكواد: <code>{st.get('stock',0)}</code>\n🚀 API: <code>{st.get('api',0)}</code>\n⚡ شحنات: <code>{st.get('topups', 0)}</code>"
        return await query.edit_message_text(msg, reply_markup=profile_keyboard(role), parse_mode=ParseMode.HTML)

    if data == "view_my_tokens":
        await query.answer()
        tokens = user.get("tokens", [])
        txt = "\n".join([f"🔑 <code>{t[:8]}...{t[-4:]}</code>" for t in tokens]) if tokens else "📭 لا يوجد توكنات."
        btns = [[InlineKeyboardButton("➕ إضافة توكن", callback_data="add_tokens")], [InlineKeyboardButton("📜 سجل التوكنات", callback_data="view_token_logs")]]
        if tokens: btns.append([InlineKeyboardButton("🗑 حذف جميع توكناتي", callback_data="clear_tokens")])
        btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="my_profile")])
        return await query.edit_message_text(f"📋 <b>توكناتك ({len(tokens)}):</b>\n\n{txt}" if tokens else txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    if data == "view_token_logs":
        await query.answer()
        logs = user.get("token_logs", [])
        if not logs: return await query.edit_message_text("📭 لا يوجد سجل.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)
        txt = "\n".join(logs[-30:])
        return await query.edit_message_text(f"📜 <b>سجل التوكنات:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)

    if data == "clear_tokens":
        await query.answer()
        await db.users.update_one({"_id": uid}, {"$set": {"tokens": []}})
        return await query.edit_message_text("🗑 <b>تم حذف التوكنات.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)

    if data == "add_tokens":
        await query.answer()
        context.user_data["state"] = "waiting_tokens"
        return await query.edit_message_text("📝 <b>أرسل التوكنات:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)

    if data == "my_history":
        await query.answer()
        hist = user.get("history", [])
        txt = "\n".join([f"<code>{h}</code>" for h in hist[-10:]]) if hist else "📂 أرشيفك فارغ."
        btns = [[InlineKeyboardButton("🔍 البحث عن طلب", callback_data="check_order_id")]]
        if role in ["admin", "employee"]: btns.append([InlineKeyboardButton("↩️ إرجاع طلب", callback_data="return_order")])
        btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="my_profile")])
        return await query.edit_message_text(f"📂 <b>آخر 10 عمليات:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    if data == "check_order_id":
        await query.answer()
        context.user_data["state"] = "waiting_order_id"
        return await query.edit_message_text("🔍 <b>أرسل رقم الطلب:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للأرشيف", callback_data="my_history")]]), parse_mode=ParseMode.HTML)

    if data == "return_order" and role in ["admin", "employee"]:
        await query.answer()
        context.user_data["state"] = "waiting_return_order_id"
        return await query.edit_message_text("↩️ <b>أرسل رقم الطلب المراد إرجاعه:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للأرشيف", callback_data="my_history")]]), parse_mode=ParseMode.HTML)

    if data == "pull_stock_menu" and role in ["admin", "employee"]: 
        await query.answer()
        return await query.edit_message_text("🎮 <b>اختر الفئة للسحب:</b>", reply_markup=await categories_keyboard("pull_cat", db), parse_mode=ParseMode.HTML)
    
    if data.startswith("pull_cat_") and role in ["admin", "employee"]:
        await query.answer()
        cat = data.split("pull_cat_")[-1]
        context.user_data["state"] = "waiting_stock_count"
        context.user_data["target_pull_cat"] = cat
        return await query.edit_message_text(f"🔢 <b>أرسل العدد لـ {cat}:</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

    if data == "pull_api":
        await query.answer()
        tokens = user.get("tokens", [])
        shared_doc = await db.settings.find_one({"_id": "shared_tokens"})
        shared_tokens = shared_doc.get("tokens", []) if shared_doc else []
        
        if not tokens and (role == "user" or not shared_tokens):
             return await query.edit_message_text("⚠️ <b>لا يوجد توكنات!</b> أضف توكن أولاً.", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
             
        context.user_data["state"] = "waiting_api_count"
        return await query.edit_message_text("🔢 <b>أرسل عدد الحسابات لسحبها:</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

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
        return await query.edit_message_text("📂 <b>الرفع الذكي:</b>\nأرسل ملف <code>.txt</code> هنا مباشرة.", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)
    
    if data == "admin_choose_cat_clear" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("🗑 <b>اختر الفئة لتصفيرها:</b>", reply_markup=await categories_keyboard("admin_clear_cat", db), parse_mode=ParseMode.HTML)

    if data.startswith("admin_add_manual_") and role == "admin":
        await query.answer()
        cat = data.split("admin_add_manual_")[-1]
        context.user_data["state"] = "adding_stock_manual"
        context.user_data["target_cat"] = cat
        return await query.edit_message_text(f"✍️ <b>أرسل أكواد {cat}:</b>", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)

    if data.startswith("admin_clear_cat_") and role == "admin":
        await query.answer()
        cat = data.split("admin_clear_cat_")[-1]
        await db.stock.delete_many({"category": cat})
        return await query.edit_message_text(f"🗑 <b>تم تصفير فئة {cat} بنجاح.</b>", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)

    if data.startswith("smart_cat_") and role == "admin":
        await query.answer()
        cat = data.split("smart_cat_")[-1]
        lines = context.user_data.get("smart_upload_lines")
        if not lines: return await query.edit_message_text("❌ أرسل الملف مجدداً.")
        await query.edit_message_text("⏳ <b>جاري الفحص...</b>", parse_mode=ParseMode.HTML)
        new_codes, dupes, all_codes = await analyze_codes(lines)
        context.user_data["pending_stock"] = {"all": all_codes, "new": new_codes, "dupes": dupes, "cat": cat} 
        btns = [[InlineKeyboardButton("✅ استيراد الكل", callback_data="confirm_add_all")], [InlineKeyboardButton("✨ استيراد الجديد", callback_data="confirm_add_new")]]
        if dupes: btns.append([InlineKeyboardButton("👁️ عرض المكرر", callback_data="show_dupes_list")])
        btns.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")])
        msg = f"📂 <b>تقرير الرفع ({cat}):</b>\nإجمالي: <code>{len(all_codes)}</code>\n✅ جديد: <code>{len(new_codes)}</code>\n⚠️ مكرر: <code>{len(dupes)}</code>"
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
            await log_important_action(uid, user["name"], f"📥 إضافة {len(docs)} كود لفئة {pending['cat']}")

        context.user_data.clear()
        btns = [[InlineKeyboardButton("➕ إضافة المزيد", callback_data="admin_choose_cat_manual")], [InlineKeyboardButton("🔙 رجوع", callback_data="admin_stock_menu")]]
        return await query.edit_message_text(f"✅ <b>تم إضافة الأكواد بنجاح.</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
        
    if data == "show_dupes_list" and role == "admin":
        pending = context.user_data.get("pending_stock")
        if not pending or not pending.get("dupes"): return await query.answer("لا يوجد!", show_alert=True)
        dupes_list = pending["dupes"]
        txt = "\n".join([f"<code>{d}</code>" for d in dupes_list[:50]])
        if len(dupes_list) > 50: txt += f"\n... و {len(dupes_list)-50} أخرى."
        await query.answer() 
        return await query.message.reply_text(f"⚠️ <b>المكرر ({len(dupes_list)}):</b>\n\n{txt}", parse_mode=ParseMode.HTML)

    if data in ["file_shared_tokens", "file_personal_tokens"] and role in ["admin", "employee"]:
        await query.answer()
        lines = context.user_data.get("smart_upload_lines", [])
        valid_tokens = [re.split(r'[;:\s\|]', l)[0].strip() for l in lines if len(re.split(r'[;:\s\|]', l)[0].strip()) > 15]
        
        if not valid_tokens: return await query.edit_message_text("❌ <b>لا يوجد توكنات صالحة!</b>", parse_mode=ParseMode.HTML)
            
        if data == "file_shared_tokens" and role == "admin":
            await db.settings.update_one({"_id": "shared_tokens"}, {"$push": {"tokens": {"$each": valid_tokens}}}, upsert=True)
            msg = f"✅ تم إضافة <code>{len(valid_tokens)}</code> توكن مشترك."
        else:
            await db.users.update_one({"_id": uid}, {"$push": {"tokens": {"$each": valid_tokens}}})
            msg = f"✅ تم إضافة <code>{len(valid_tokens)}</code> توكن شخصي."
            
        context.user_data.clear()
        return await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=back_btn())

    if data == "cancel_add_stock" and role == "admin":
        await query.answer()
        context.user_data.clear()
        return await query.edit_message_text("❌ <b>تم الإلغاء.</b>", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)

    if data == "admin_users_menu" and role == "admin":
        await query.answer()
        context.user_data.clear()
        c = await db.users.count_documents({})
        msg = f"👥 <b>إدارة المستخدمين</b> (<code>{c}</code>)\n\n"
        async for u in db.users.find().sort("_id", -1).limit(20):
             ic = "👮‍♂️" if u.get('role') == "admin" else "👤" if u.get('role') == "employee" else "🆕"
             msg += f"{ic} <code>{u['_id']}</code> | {u.get('name', 'بدون اسم')}\n"
        return await query.edit_message_text(msg, reply_markup=admin_users_keyboard(), parse_mode=ParseMode.HTML)

    if data in ["admin_add_user_btn", "admin_remove_user_btn", "admin_search_manage_user", "admin_get_user_logs_btn"] and role == "admin":
        await query.answer()
        states = {
            "admin_add_user_btn": ("waiting_add_user_id", "✍️ <b>أرسل الآيدي للإضافة:</b>"),
            "admin_remove_user_btn": ("waiting_remove_user_id", "🗑 <b>أرسل الآيدي للحذف:</b>"),
            "admin_search_manage_user": ("waiting_manage_user_id", "🔍 <b>أرسل الآيدي للتحكم:</b>"),
            "admin_get_user_logs_btn": ("waiting_user_logs_id", "📜 <b>أرسل الآيدي للسجلات:</b>")
        }
        context.user_data["state"] = states[data][0]
        return await query.edit_message_text(states[data][1], reply_markup=admin_users_back_btn(), parse_mode=ParseMode.HTML)

    if data.startswith("manage_clear_tokens_") and role == "admin":
        tid = int(data.split("_")[-1])
        await db.users.update_one({"_id": tid}, {"$set": {"tokens": []}})
        return await query.answer("✅ تم التصفير", show_alert=True)
        
    if data.startswith("manage_switch_role_") and role == "admin":
        tid = int(data.split("_")[-1])
        target = await get_user(tid)
        if target and target["_id"] != ADMIN_ID:
            nr = "employee" if target["role"] == "user" else "user"
            await db.users.update_one({"_id": tid}, {"$set": {"role": nr}})
            return await query.answer(f"✅ أصبح: {nr}", show_alert=True)
        return await query.answer("❌ لا يمكن تعديله", show_alert=True)
        
    if data.startswith("manage_clear_logs_") and role == "admin":
        tid = int(data.split("_")[-1])
        await db.users.update_one({"_id": tid}, {"$set": {"logs": [], "history": [], "token_logs": []}})
        return await query.answer("✅ تم المسح", show_alert=True)

    if data.startswith("set_role_") and role == "admin":
        await query.answer()
        new_uid = context.user_data.get("new_user_id")
        if not new_uid: return
        r = "employee" if data == "set_role_employee" else "user"
        await db.users.insert_one({"_id": new_uid, "role": r, "name": "User", "tokens": [], "history": [], "logs": [], "token_logs": [], "stats": {"api":0,"stock":0,"topups":0}})
        context.user_data.clear()
        return await query.edit_message_text(f"✅ تم إضافة <code>{new_uid}</code> كرتبة <b>{r}</b>.", reply_markup=retry_keyboard("admin_add_user_btn", "admin_users_menu"), parse_mode=ParseMode.HTML)

    if data == "admin_get_logs" and role == "admin":
        await query.answer()
        await query.edit_message_text("⏳ <b>جاري جلب السجلات...</b>", parse_mode=ParseMode.HTML)
        logs = await db.system_logs.find().sort("timestamp", -1).limit(15).to_list(length=15)
        if not logs: return await query.edit_message_text("📭 لا توجد سجلات.", reply_markup=admin_logs_back_btn(), parse_mode=ParseMode.HTML)
        rep = "📝 <b>أحدث العمليات:</b>\n\n"
        for l in logs: rep += f"👤 <b>{l['name']}</b> | ⏱ {l['time']}\n🔹 {l['action']}\n───────────\n"
        btns = [[InlineKeyboardButton("🔄 تحديث", callback_data="admin_get_logs")], [InlineKeyboardButton("🔙 رجوع", callback_data="admin_logs_hub")]]
        return await query.edit_message_text(rep, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    uid = update.effective_user.id
    txt = update.message.text.strip()
    state = context.user_data.get("state")
    
    user = await get_user(uid)
    if not user: return
    role = user.get("role", "user")
    
    if not state: return await update.message.reply_text("💡 يرجى اختيار عملية أولاً.", reply_markup=back_btn())

    if state == "waiting_add_tracked" and role == "admin":
        if not txt.isdigit(): return
        await db.settings.update_one({"_id": "cache_config"}, {"$addToSet": {"tracked_users": int(txt)}}, upsert=True)
        context.user_data.clear()
        return await update.message.reply_text(f"✅ تم الإضافة.", reply_markup=retry_keyboard("add_tracked_user", "admin_auto_cache_menu"))

    elif state == "waiting_remove_tracked" and role == "admin":
        if not txt.isdigit(): return
        await db.settings.update_one({"_id": "cache_config"}, {"$pull": {"tracked_users": int(txt)}}, upsert=True)
        context.user_data.clear()
        return await update.message.reply_text(f"🗑 تم الإزالة.", reply_markup=retry_keyboard("remove_tracked_user", "admin_auto_cache_menu"))

    elif state == "waiting_cached_api_count" and role == "admin":
        if not txt.isdigit() or int(txt) <= 0: return
        await process_cache_pull(uid, update.message.reply_text, user, int(txt), context)

    elif state == "waiting_global_search" and role == "admin":
        is_bot_order = txt.isdigit()
        is_web_order = txt.endswith('S') and txt[:-1].isdigit()
        
        if is_bot_order or is_web_order:
            order = await db.orders.find_one({"_id": int(txt)}) if is_bot_order else await db.store_orders.find_one({"_id": txt})
            if order:
                if "items" in order:
                    items_str = "\n".join([f"<code>{i}</code>" for i in order["items"]])
                    res_msg = f"📄 <b>طلب بوت <code>#{txt}</code></b>\n👤 بواسطة: <code>{order['user']}</code>\n⬇️ العناصر:\n{items_str}"
                else:
                    res_msg = f"🛒 <b>طلب متجر <code>#{txt}</code></b>\n👤 بواسطة: <code>{order['name']}</code>\n⬇️ الكود:\n<code>{order['code']}</code>"
                return await update.message.reply_text(res_msg, reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)
            
            if is_bot_order:
                target = await get_user(int(txt))
                if target:
                    msg = f"👤 <b>الاسم:</b> {target.get('name')}\n🆔 <code>{target['_id']}</code>\n🎖 <b>الرتبة:</b> {target['role']}"
                    return await update.message.reply_text(msg, reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)

        records = await db.codes_map.find({"$or": [{"_id": txt}, {"code": txt}]}).to_list(None)
        in_stock = await db.stock.count_documents({"$or": [{"_id": txt}, {"code": txt}]})
        
        if not records and in_stock == 0:
            await update.message.reply_text("❌ <b>لا توجد نتائج!</b>", reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)
        else:
            msg = f"🔍 <b>الكود:</b> <code>{txt}</code>\n📦 بالمخزن حالياً: <code>{in_stock}</code>\n\n"
            if records:
                for i, r in enumerate(records, 1):
                    msg += f"--- سحبة {i} ---\n👤 {r['name']} ({r.get('source', 'Bot')})\n📅 {r['time']}\n📦 طلب: <code>{r.get('order_id')}</code>\n\n"
            await update.message.reply_text(msg, reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)
        context.user_data.clear()

    elif state == "waiting_order_id":
        order = await db.orders.find_one({"_id": int(txt) if txt.isdigit() else txt})
        if not order: order = await db.store_orders.find_one({"_id": txt})
        
        if order and (order.get("user_id") == uid or role == "admin"):
            if "items" in order:
                items_str = "\n".join([f"<code>{i}</code>" for i in order["items"]])
                res_msg = f"📄 <b>الطلب <code>#{txt}</code></b>\n📅 {order['date']}\n⬇️ العناصر:\n{items_str}"
            else:
                res_msg = f"🛒 <b>طلب متجر <code>#{txt}</code></b>\n📅 {order['date']}\n⬇️ الكود:\n<code>{order['code']}</code>"
        else: res_msg = "❌ الطلب غير موجود."
        context.user_data.clear()
        return await update.message.reply_text(res_msg, reply_markup=retry_keyboard("check_order_id", "my_history"), parse_mode=ParseMode.HTML)

    elif state == "waiting_return_order_id":
        order = await db.orders.find_one({"_id": int(txt) if txt.isdigit() else txt})
        if not order: order = await db.store_orders.find_one({"_id": txt})
        
        if not order or (order.get("user_id") != uid and role != "admin"): 
            return await update.message.reply_text("❌ الطلب غير موجود.", reply_markup=back_btn())
            
        order_time = datetime.strptime(order['date'], "%Y-%m-%d %H:%M:%S" if "items" in order else "%Y-%m-%d %H:%M")
        if (datetime.now() - order_time).total_seconds() > 900 and role != "admin":
            return await update.message.reply_text("⏳ <b>انتهت مهلة الإرجاع (15 دقيقة).</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
            
        if "items" in order:
            cat = order["type"].split("(")[1].split(")")[0]
            codes_to_return = [{"code": code, "category": cat, "added_at": datetime.now()} for code in order["items"]]
            await db.stock.insert_many(codes_to_return, ordered=False) 
            await db.codes_map.delete_many({"$or": [{"_id": {"$in": order["items"]}}, {"code": {"$in": order["items"]}}], "order_id": int(txt)}) 
            await db.orders.delete_one({"_id": int(txt)}) 
            await db.users.update_one({"_id": uid}, {"$inc": {"stats.stock": -len(order["items"])}}) 
        else:
            await db.stock.insert_one({"code": order["code"], "category": order["category"], "added_at": datetime.now()})
            await db.codes_map.delete_many({"$or": [{"_id": order["code"]}, {"code": order["code"]}], "order_id": txt})
            await db.store_orders.delete_one({"_id": txt})

        context.user_data.clear()
        return await update.message.reply_text(f"✅ <b>تم إرجاع الطلب <code>#{txt}</code> بنجاح!</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

    elif state == "waiting_stock_count":
        if not txt.isdigit() or int(txt) <= 0: return
        count = int(txt)
        cat = context.user_data.get("target_pull_cat")
        context.user_data.clear() 
        await process_stock_pull(uid, update.message.reply_text, user, cat, count, context)

    elif state == "waiting_api_count":
        if not txt.isdigit() or int(txt) <= 0: return
        qty = int(txt)
        context.user_data.clear()
        context.user_data["last_api_count"] = qty
        await process_api_pull(uid, update.message.reply_text, user, qty, context)

    elif state == "waiting_tokens":
        valid = [re.split(r'[;:\s\|]', l)[0].strip() for l in txt.splitlines() if len(re.split(r'[;:\s\|]', l)[0].strip()) > 15]
        if valid: 
            await db.users.update_one({"_id": uid}, {"$addToSet": {"tokens": {"$each": valid}}})
            msg = f"✅ تم إضافة <code>{len(valid)}</code> توكن."
        else: msg = "❌ لا توجد توكنات صالحة."
        context.user_data.clear()
        return await update.message.reply_text(msg, reply_markup=retry_keyboard("add_tokens", "view_my_tokens"), parse_mode=ParseMode.HTML)

    elif state == "waiting_shared_tokens" and role == "admin":
        valid = [re.split(r'[;:\s\|]', l)[0].strip() for l in txt.splitlines() if len(re.split(r'[;:\s\|]', l)[0].strip()) > 15]
        if valid: 
            await db.settings.update_one({"_id": "shared_tokens"}, {"$push": {"tokens": {"$each": valid}}}, upsert=True)
            msg = f"✅ تم إضافة <code>{len(valid)}</code> توكن مشترك."
        else: msg = "❌ لا توجد توكنات صالحة."
        context.user_data.clear()
        return await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)

    elif state == "waiting_add_user_id" and role == "admin":
        if not txt.isdigit(): return
        new_uid = int(txt)
        if await get_user(new_uid): return await update.message.reply_text("⚠️ موجود بالفعل!", reply_markup=retry_keyboard("admin_add_user_btn", "admin_users_menu"))
        context.user_data["new_user_id"] = new_uid
        btns = [[InlineKeyboardButton("موظف 👤", callback_data="set_role_employee")], [InlineKeyboardButton("مستخدم عادي 🆕", callback_data="set_role_user")]]
        return await update.message.reply_text(f"👤 <b>اختر الرتبة:</b> <code>{new_uid}</code>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    elif state == "waiting_remove_user_id" and role == "admin":
        if txt.isdigit():
            await db.users.delete_one({"_id": int(txt)})
            context.user_data.clear()
            return await update.message.reply_text(f"🗑 تم الحذف.", reply_markup=retry_keyboard("admin_remove_user_btn", "admin_users_menu"))

    elif state == "waiting_manage_user_id" and role == "admin":
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target:
            btns = [[InlineKeyboardButton("🗑 تصفير توكنات", callback_data=f"manage_clear_tokens_{target['_id']}"), InlineKeyboardButton("🔄 تغيير رتبة", callback_data=f"manage_switch_role_{target['_id']}")]]
            await update.message.reply_text(f"👤 <b>{target.get('name')}</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
        context.user_data.clear()

    elif state == "waiting_user_logs_id" and role == "admin":
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target and target.get("logs"):
            await update.message.reply_text(f"📜 <b>سجلات:</b>\n\n" + "\n\n".join(target["logs"][-15:]), reply_markup=retry_keyboard("admin_get_user_logs_btn", "admin_users_menu"), parse_mode=ParseMode.HTML)
        context.user_data.clear()

    elif state == "adding_stock_manual" and role == "admin":
        lines = [c.strip() for c in txt.splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        if cat and lines:
            waiting_msg = await update.message.reply_text("⏳ <b>جاري الفحص...</b>", parse_mode=ParseMode.HTML)
            new_codes, dupes, all_codes = await analyze_codes(lines)
            context.user_data["pending_stock"] = {"all": all_codes, "new": new_codes, "dupes": dupes, "cat": cat} 
            btns = [[InlineKeyboardButton("✅ إضافة الكل", callback_data="confirm_add_all")], [InlineKeyboardButton("✨ إضافة الجديد", callback_data="confirm_add_new")]]
            return await waiting_msg.edit_text(f"📊 <b>التقرير:</b>\nإجمالي: {len(all_codes)} | جديد: {len(new_codes)}", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user or user["role"] not in ["admin", "employee"]: return
    
    doc = update.message.document
    if not doc.file_name.endswith(".txt"): return
    
    waiting_msg = await update.message.reply_text("⏳ <b>جاري القراءة...</b>", parse_mode=ParseMode.HTML)
    file = await doc.get_file()
    content = await file.download_as_bytearray()
    lines = [c.strip() for c in content.decode("utf-8", errors="ignore").splitlines() if c.strip()]
    if not lines: return await waiting_msg.edit_text("❌ الملف فارغ!")
    
    context.user_data["smart_upload_lines"] = lines
    
    btns = []
    if user["role"] == "admin":
        stock_keys = await get_dynamic_categories()
        row = []
        for key in stock_keys:
            row.append(InlineKeyboardButton(f"{key}", callback_data=f"smart_cat_{key}"))
            if len(row) == 3:
                btns.append(row)
                row = []
        if row: btns.append(row)
        btns.append([InlineKeyboardButton("🔑 استخراج توكنات (مشتركة)", callback_data="file_shared_tokens")])
        
    btns.append([InlineKeyboardButton("🔐 استخراج توكنات (شخصية)", callback_data="file_personal_tokens")])
    btns.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")])
    
    await waiting_msg.edit_text(f"📂 <b>ملف (<code>{len(lines)}</code> سطر)</b>\n🎯 <b>ماذا تريد أن تفعل؟</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
