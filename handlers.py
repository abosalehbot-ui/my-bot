import io
import httpx
import traceback
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_ID, API_BASE_URL, PRODUCT_ID, logger
from database import db, get_user, check_maintenance, get_tracked_users, get_next_order_id, analyze_codes, log_important_action
from keyboards import (get_main_keyboard, admin_keyboard, auto_cache_keyboard, 
                       admin_users_keyboard, stock_manage_keyboard, categories_keyboard, 
                       success_pull_keyboard, back_btn, admin_back_btn, admin_users_back_btn, 
                       profile_keyboard, admin_logs_keyboard, admin_logs_back_btn, retry_keyboard)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("❌ حدث خطأ برمجي:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    error_msg = f"🚨 **تنبيه عاجل للنظام!**\n\nحدث خطأ برمجي غير متوقع في البوت."
    log_file = io.BytesIO(tb_string.encode('utf-8'))
    log_file.name = f"Crash_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        if update and hasattr(update, 'effective_message') and update.effective_message:
            await context.bot.send_document(chat_id=ADMIN_ID, document=log_file, caption=error_msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"فشل إرسال ملف الخطأ: {e}")

async def process_api_pull(uid, reply_func, user, qty, context):
    tokens = list(user.get("tokens", []))
    if not tokens:
        return await reply_func("⚠️ **لا يوجد لديك توكنات!** أضف توكنات أولاً من قائمة 'توكناتي'.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    tokens_to_use = tokens[:qty]
    waiting_msg = await reply_func(f"⏳ **جاري السحب باستخدام {len(tokens_to_use)} توكن...**", parse_mode=ParseMode.MARKDOWN)
    
    accs, raw_accs, used_tokens, token_logs_updates = [], [], [], []
    
    async with httpx.AsyncClient() as client:
        tasks = [(t, client.post(f"{API_BASE_URL}/api/redeem-bulk", json={"token": t, "product": PRODUCT_ID, "qty": 1}, timeout=15.0)) for t in tokens_to_use]
        for t, req in tasks:
            used_tokens.append(t)
            short_t = f"{t[:8]}...{t[-4:]}"
            try:
                res = await req
                r = res.json()
                if r.get("success") and r.get("accounts"):
                    a = r["accounts"][0]
                    accs.append(f"`{a['email']}`\n`{a['password']}`")
                    raw_accs.append(f"{a['email']}:{a['password']}") 
                    token_logs_updates.append(f"✅ نجاح | توكن {short_t} | سحب: {a['email']}")
                else:
                    err = r.get("message", "مجهول/بايظ")
                    token_logs_updates.append(f"❌ فشل | توكن {short_t} | السبب: {err}")
            except Exception as e:
                token_logs_updates.append(f"⚠️ خطأ | توكن {short_t} | خطأ في الاتصال بالسيرفر.")
                logger.error(f"API Error for token {t}: {e}")

    db_updates = {"$pull": {"tokens": {"$in": used_tokens}}}
    if token_logs_updates: db_updates["$push"] = {"token_logs": {"$each": token_logs_updates, "$slice": -500}}
    await db.users.update_one({"_id": uid}, db_updates)
    
    reply_markup = retry_keyboard("pull_api", "back_home")
    
    if accs:
        tracked_users = await get_tracked_users()
        if uid in tracked_users and raw_accs:
            cached_docs = [{"account": raw, "added_at": datetime.now()} for raw in raw_accs]
            await db.cached_accounts.insert_many(cached_docs)
            
        order_id = await get_next_order_id()
        await db.orders.insert_one({"_id": order_id, "type": "API Pull", "user": user["name"], "user_id": uid, "items": accs, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        await db.users.update_one({"_id": uid}, {"$push": {"history": f"🚀 طلب #{order_id}"}, "$inc": {"stats.api": len(accs)}})
        
        # 🆕 تسجيل العملية في اللوجز بالتفاصيل
        details_txt = " | ".join(raw_accs)
        await log_important_action(uid, user["name"], f"🚀 سحب {len(accs)} حساب API (طلب #{order_id})", details_txt)
        
        display_txt = "\n━━━━━━━━━━━━\n".join(accs)
        await waiting_msg.edit_text(f"✅ **تم السحب بنجاح (طلب #{order_id}):**\n\n{display_txt}\n\n📝 *(تم حذف التوكنات المستخدمة)*", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    else:
        await waiting_msg.edit_text("❌ **فشل السحب من التوكنات.**", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

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
    maint_msg = "\n⚠️ **النظام في وضع الصيانة**" if await check_maintenance() else ""
    await update.message.reply_text(f"👋 أهلاً {name}\n🔹 الرتبة: {role}{maint_msg}", reply_markup=get_main_keyboard(role), parse_mode=ParseMode.MARKDOWN)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    user = await get_user(uid)
    if not user: return
    role = user.get("role", "user")

    if await check_maintenance() and role != "admin": 
        await query.answer()
        return await query.edit_message_text("⚠️ **الصيانة جارية...**")
    
    if data == "back_home":
        context.user_data.clear()
        await query.answer()
        return await query.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard(role))

    if data == "pull_cached_api" and role == "admin":
        await query.answer()
        await db.cached_accounts.delete_many({"added_at": {"$lt": datetime.now() - timedelta(hours=24)}})
        count = await db.cached_accounts.count_documents({})
        if count == 0: return await query.edit_message_text("📭 المخزن فارغ، أو الحسابات انتهت صلاحيتها.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        context.user_data["state"] = "waiting_cached_api_count"
        return await query.edit_message_text(f"♻️ **المتاح الآن:** {count} حساب\n\n🔢 **أرسل عدد الحسابات للسحب:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    # 🆕 قائمة السجلات والتخزين المدمجة
    if data == "admin_logs_hub" and role == "admin":
        await query.answer()
        context.user_data.clear()
        return await query.edit_message_text("📜 **مركز السجلات والتخزين**\nاختر العملية التي تريدها:", reply_markup=admin_logs_keyboard(), parse_mode=ParseMode.MARKDOWN)

    if data == "admin_auto_cache_menu" and role == "admin":
        await query.answer()
        return await query.edit_message_text("♻️ **إعدادات التخزين التلقائي**\nحدد من يتم نسخ حساباتهم للمخزن المحلي تلقائياً عند سحبهم من الـ API.", reply_markup=auto_cache_keyboard(), parse_mode=ParseMode.MARKDOWN)

    if data == "list_tracked_users" and role == "admin":
        await query.answer()
        tracked = await get_tracked_users()
        txt = "\n".join([f"🆔 `{t}`" for t in tracked])
        return await query.edit_message_text(f"📋 **قائمة المراقبة للتخزين التلقائي:**\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_auto_cache_menu")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "add_tracked_user" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_add_tracked"
        return await query.edit_message_text("✍️ **أرسل الآيدي المراد إضافته:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_auto_cache_menu")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "remove_tracked_user" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_remove_tracked"
        return await query.edit_message_text("🗑 **أرسل الآيدي المراد إزالته:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_auto_cache_menu")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "my_profile":
        await query.answer()
        t_count = len(user.get("tokens", []))
        st = user.get("stats", {"api": 0, "stock": 0})
        msg = f"💳 **حسابك:**\n👤 الاسم: {user.get('name')}\n🎖 الرتبة: {role}\n🔑 توكنات نشطة: {t_count}\n\n🛒 **السحوبات:**\n🎮 أكواد مسحوبة: {st.get('stock',0)}\n🚀 حسابات API: {st.get('api',0)}"
        return await query.edit_message_text(msg, reply_markup=profile_keyboard(role), parse_mode=ParseMode.MARKDOWN)

    if data == "view_my_tokens":
        await query.answer()
        tokens = user.get("tokens", [])
        txt = "\n".join([f"🔑 `{t[:8]}...{t[-4:]}`" for t in tokens]) if tokens else "📭 لا يوجد لديك توكنات نشطة."
        btns = [[InlineKeyboardButton("➕ إضافة توكن", callback_data="add_tokens")], [InlineKeyboardButton("📜 سجل التوكنات (الهيستوري)", callback_data="view_token_logs")]]
        if tokens: btns.append([InlineKeyboardButton("🗑 حذف جميع توكناتي", callback_data="clear_tokens")])
        btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_home")])
        msg = f"📋 **توكناتك الحالية ({len(tokens)}):**\n\n{txt}" if tokens else txt
        return await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)

    if data == "view_token_logs":
        await query.answer()
        logs = user.get("token_logs", [])
        if not logs: return await query.edit_message_text("📭 لا يوجد سجل للتوكنات حتى الآن.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع لتوكناتي", callback_data="view_my_tokens")]]), parse_mode=ParseMode.MARKDOWN)
        txt = "\n".join(logs[-30:])
        return await query.edit_message_text(f"📜 **سجل نشاط التوكنات:**\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع لتوكناتي", callback_data="view_my_tokens")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "clear_tokens":
        await query.answer()
        await db.users.update_one({"_id": uid}, {"$set": {"tokens": []}})
        return await query.edit_message_text("🗑 **تم حذف جميع التوكنات.**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="view_my_tokens")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "add_tokens":
        await query.answer()
        context.user_data["state"] = "waiting_tokens"
        return await query.edit_message_text("📝 **أرسل التوكنات:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="view_my_tokens")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "my_history":
        await query.answer()
        hist = user.get("history", [])
        txt = "\n".join(hist[-10:]) if hist else "📂 أرشيفك فارغ."
        btns = [[InlineKeyboardButton("🔍 بحث برقم الطلب (Order ID)", callback_data="check_order_id")], [InlineKeyboardButton("🔙 رجوع", callback_data="my_profile")]]
        return await query.edit_message_text(f"📂 **آخر 10 عمليات:**\n\n{txt}", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)

    if data == "check_order_id":
        await query.answer()
        context.user_data["state"] = "waiting_order_id"
        return await query.edit_message_text("🔍 **أرسل رقم الطلب المراد كشفه:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للأرشيف", callback_data="my_history")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "return_order" and role in ["admin", "employee"]:
        await query.answer()
        context.user_data["state"] = "waiting_return_order_id"
        return await query.edit_message_text("↩️ **نظام المرتجعات السريع**\n\nأرسل **رقم الطلب (Order ID)** الذي تريد إرجاعه:\n*(ملاحظة: الإرجاع متاح لأكواد ببجي فقط، وخلال 15 دقيقة من السحب)*", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="my_profile")]]), parse_mode=ParseMode.MARKDOWN)

    if data == "pull_stock_menu" and role in ["admin", "employee"]: 
        await query.answer()
        return await query.edit_message_text("🎮 **اختر الفئة للسحب:**", reply_markup=await categories_keyboard("pull_cat", db))
    
    if data.startswith("pull_cat_") and role in ["admin", "employee"]:
        await query.answer()
        cat = data.split("_")[-1]
        context.user_data["state"] = "waiting_stock_count"
        context.user_data["target_pull_cat"] = cat
        return await query.edit_message_text(f"🔢 **أرسل العدد لـ {cat} UC:**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "pull_api":
        await query.answer()
        tokens = user.get("tokens", [])
        if not tokens: return await query.edit_message_text("⚠️ **لا يوجد توكنات!** أضف توكن أولاً من قائمة 'توكناتي'.", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
        context.user_data["state"] = "waiting_api_count"
        return await query.edit_message_text("🔢 **أرسل عدد الحسابات التي تريد سحبها الآن:**\n*(سيتم استخدام توكن واحد لكل حساب)*", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "admin_panel" and role == "admin":
        await query.answer()
        st = await db.stock.count_documents({})
        return await query.edit_message_text(f"🛠 **الأدمن**\n📦 المخزن: {st}", reply_markup=await admin_keyboard(), parse_mode=ParseMode.MARKDOWN)
    
    if data == "admin_stock_menu" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("📦 **المخزن:**", reply_markup=stock_manage_keyboard())
    
    if data == "admin_choose_cat_manual" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("🔢 **اختر الفئة:**", reply_markup=await categories_keyboard("admin_add_manual", db))
    
    if data == "admin_choose_cat_file" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("📂 **اختر الفئة لرفع الملف:**", reply_markup=await categories_keyboard("admin_add_file", db))
    
    if data == "admin_choose_cat_clear" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("🗑 **اختر الفئة لتصفيرها:**", reply_markup=await categories_keyboard("admin_clear_cat", db))

    if data.startswith("admin_add_manual_") and role == "admin":
        await query.answer()
        cat = data.split("_")[-1]
        context.user_data["state"] = "adding_stock_manual"
        context.user_data["target_cat"] = cat
        return await query.edit_message_text(f"✍️ **أرسل أكواد {cat} UC:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)
        
    if data.startswith("admin_add_file_") and role == "admin":
        await query.answer()
        cat = data.split("_")[-1]
        context.user_data["state"] = "admin_uploading_file"
        context.user_data["target_cat"] = cat
        return await query.edit_message_text(f"📂 **أرسل ملف .txt لفئة {cat} UC:**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data.startswith("admin_clear_cat_") and role == "admin":
        await query.answer()
        cat = data.split("_")[-1]
        await db.stock.delete_many({"category": cat})
        return await query.edit_message_text(f"🗑 **تم تصفير فئة {cat} UC بنجاح.**", reply_markup=admin_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data in ["confirm_add_all", "confirm_add_new"] and role == "admin":
        await query.answer()
        pending = context.user_data.get("pending_stock")
        if pending:
            target_list = pending["all"] if data == "confirm_add_all" else pending["new"]
            docs = [{"code": c, "category": pending["cat"], "added_at": datetime.now()} for c in target_list]
            if docs: 
                try: await db.stock.insert_many(docs, ordered=False) 
                except Exception as e: logger.error(e)
            
            # 🆕 تسجيل العملية في اللوجز
            await log_important_action(uid, user["name"], f"📥 إضافة {len(docs)} كود لفئة {pending['cat']} UC")

        context.user_data.clear()
        btns = [[InlineKeyboardButton("➕ إضافة المزيد من الأكواد", callback_data="admin_choose_cat_manual")], [InlineKeyboardButton("🔙 رجوع للمخزن", callback_data="admin_stock_menu")]]
        return await query.edit_message_text(f"✅ تم إضافة الأكواد بنجاح.", reply_markup=InlineKeyboardMarkup(btns))
        
    if data == "show_dupes_list" and role == "admin":
        pending = context.user_data.get("pending_stock")
        if not pending or not pending.get("dupes"):
            return await query.answer("لا يوجد أكواد مكررة!", show_alert=True)
        
        dupes_list = pending["dupes"]
        txt = "\n".join(dupes_list[:50])
        if len(dupes_list) > 50: txt += f"\n... و {len(dupes_list)-50} أكواد أخرى."
        
        await query.answer() 
        msg = f"⚠️ **الأكواد المكررة ({len(dupes_list)} كود):**\n\n`{txt}`"
        return await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    if data == "cancel_add_stock" and role == "admin":
        await query.answer()
        context.user_data.clear()
        return await query.edit_message_text("❌ تم الإلغاء.", reply_markup=admin_back_btn())

    if data == "admin_users_menu" and role == "admin":
        await query.answer()
        context.user_data.clear()
        c = await db.users.count_documents({})
        return await query.edit_message_text(f"👥 **إدارة المستخدمين والموظفين**\nالإجمالي: {c}", reply_markup=admin_users_keyboard(), parse_mode=ParseMode.MARKDOWN)

    if data in ["admin_add_user_btn", "admin_remove_user_btn", "admin_search_manage_user", "admin_get_user_logs_btn"] and role == "admin":
        await query.answer()
        states = {
            "admin_add_user_btn": ("waiting_add_user_id", "✍️ **أرسل الآيدي (ID) لإضافته:**"),
            "admin_remove_user_btn": ("waiting_remove_user_id", "🗑 **أرسل الآيدي (ID) لحذفه:**"),
            "admin_search_manage_user": ("waiting_manage_user_id", "🔍 **أرسل الآيدي (ID) للتحكم في حسابه:**"),
            "admin_get_user_logs_btn": ("waiting_user_logs_id", "📜 **أرسل الآيدي لاستخراج سجلاته:**")
        }
        context.user_data["state"] = states[data][0]
        return await query.edit_message_text(states[data][1], reply_markup=admin_users_back_btn(), parse_mode=ParseMode.MARKDOWN)

    if data == "admin_list_users_btn" and role == "admin":
        await query.answer()
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
        await query.answer()
        new_uid = context.user_data.get("new_user_id")
        if not new_uid: return
        r = "employee" if data == "set_role_employee" else "user"
        await db.users.insert_one({"_id": new_uid, "role": r, "name": "User", "tokens": [], "history": [], "logs": [], "token_logs": [], "stats": {"api":0,"stock":0}})
        context.user_data.clear()
        return await query.edit_message_text(f"✅ تم إضافة الحساب كرتبة **{r}**.", reply_markup=retry_keyboard("admin_add_user_btn", "admin_users_menu"), parse_mode=ParseMode.MARKDOWN)

    # 🆕 نظام عرض السجلات المطور
    if data == "admin_get_logs" and role == "admin":
        await query.answer()
        await query.edit_message_text("⏳ **جاري جلب السجلات...**", parse_mode=ParseMode.MARKDOWN)
        logs_cursor = db.system_logs.find().sort("timestamp", -1).limit(15)
        logs = await logs_cursor.to_list(length=15)
        
        if not logs:
            return await query.edit_message_text("📭 لا توجد سجلات عمليات حتى الآن.", reply_markup=admin_logs_back_btn(), parse_mode=ParseMode.MARKDOWN)
        
        rep = "📝 **أحدث العمليات في النظام:**\n\n"
        for l in logs:
            rep += f"👤 **{l['name']}** | ⏱ {l['time']}\n"
            rep += f"🔹 {l['action']}\n"
            if l.get('details'):
                rep += f"└ <code>{l['details']}</code>\n"
            rep += "───────────\n"
            
        if len(rep) > 4000: rep = rep[:4000] + "\n..."
        btns = [[InlineKeyboardButton("🔄 تحديث السجلات", callback_data="admin_get_logs")], [InlineKeyboardButton("🔙 رجوع للسجلات", callback_data="admin_logs_hub")]]
        return await query.edit_message_text(rep, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    if data in ["admin_reverse_search", "admin_search_order"] and role == "admin":
        await query.answer()
        state = "waiting_reverse_code" if data == "admin_reverse_search" else "waiting_admin_order_search"
        msg = "🔍 **أرسل الكود:**" if data == "admin_reverse_search" else "📄 **أرسل رقم الطلب:**"
        context.user_data["state"] = state
        return await query.edit_message_text(msg, reply_markup=admin_logs_back_btn(), parse_mode=ParseMode.MARKDOWN)
        
    await query.answer()

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
        return await update.message.reply_text(f"✅ تم إضافة `{target_id}` لقائمة التخزين التلقائي بنجاح.", parse_mode=ParseMode.MARKDOWN, reply_markup=retry_keyboard("add_tracked_user", "admin_auto_cache_menu"))

    elif state == "waiting_remove_tracked" and user["role"] == "admin":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل آيدي صحيح.", reply_markup=retry_keyboard("remove_tracked_user", "admin_auto_cache_menu"))
        target_id = int(txt)
        await db.settings.update_one({"_id": "cache_config"}, {"$pull": {"tracked_users": target_id}}, upsert=True)
        context.user_data.clear()
        return await update.message.reply_text(f"🗑 تم إزالة `{target_id}` من قائمة التخزين التلقائي.", parse_mode=ParseMode.MARKDOWN, reply_markup=retry_keyboard("remove_tracked_user", "admin_auto_cache_menu"))

    elif state == "waiting_cached_api_count" and user["role"] == "admin":
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        qty = int(txt)
        context.user_data.clear()
        await db.cached_accounts.delete_many({"added_at": {"$lt": datetime.now() - timedelta(hours=24)}})
        
        available = await db.cached_accounts.count_documents({})
        if qty > available: return await update.message.reply_text(f"⚠️ الكمية غير كافية! المتاح: {available}", reply_markup=back_btn())
            
        pulled_accs = []
        raw_accs_for_log = []
        for _ in range(qty):
            doc = await db.cached_accounts.find_one_and_delete({}, sort=[("added_at", 1)])
            if doc: 
                raw_accs_for_log.append(doc["account"])
                try:
                    e, p = doc["account"].split(":", 1)
                    pulled_accs.append(f"`{e}`\n`{p}`")
                except:
                    pulled_accs.append(f"`{doc['account']}`")
                
        if pulled_accs:
            # 🆕 تسجيل السحب في اللوجز
            details_str = " | ".join(raw_accs_for_log)
            await log_important_action(uid, user["name"], f"♻️ سحب {len(pulled_accs)} حساب من المخزن المحلي (24س)", details_str)
            
            msg = "\n━━━━━━━━━━━━\n".join(pulled_accs)
            return await update.message.reply_text(f"✅ **سحب {len(pulled_accs)} حساب:**\n\n{msg}", parse_mode=ParseMode.MARKDOWN, reply_markup=retry_keyboard("pull_cached_api", "back_home"))

    elif state == "waiting_order_id":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=retry_keyboard("check_order_id", "my_history"))
        order = await db.orders.find_one({"_id": int(txt)})
        
        if order and (order["user_id"] == uid or user["role"] == "admin"):
            items_str = "\n".join([f"`{i}`" for i in order["items"]])
            res_msg = f"📄 **الطلب #{txt}**\n📅 {order['date']}\n⬇️ العناصر:\n{items_str}"
        else:
            res_msg = "❌ الطلب غير موجود أو يخص شخصاً آخر."
        
        context.user_data.clear()
        return await update.message.reply_text(f"{res_msg}", reply_markup=retry_keyboard("check_order_id", "my_history"), parse_mode=ParseMode.MARKDOWN)

    elif state == "waiting_return_order_id":
        if not txt.isdigit(): return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        order = await db.orders.find_one({"_id": int(txt)})
        
        if not order or (order["user_id"] != uid and user["role"] != "admin"): return await update.message.reply_text("❌ الطلب غير موجود أو لا تملك صلاحية.", reply_markup=back_btn())
        if "PUBG Stock" not in order["type"]: return await update.message.reply_text("❌ لا يمكن إرجاع هذا النوع من الطلبات.", reply_markup=back_btn())
            
        order_time = datetime.strptime(order['date'], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - order_time).total_seconds() > 900 and user["role"] != "admin":
            return await update.message.reply_text("⏳ **انتهت مهلة الإرجاع (15 دقيقة).**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
            
        cat = order["type"].split("(")[1].split(" ")[0]
        codes_to_return = [{"code": code, "category": cat, "added_at": datetime.now()} for code in order["items"]]
        
        await db.stock.insert_many(codes_to_return, ordered=False) 
        await db.codes_map.delete_many({"$or": [{"_id": {"$in": order["items"]}}, {"code": {"$in": order["items"]}}], "order_id": int(txt)}) 
        await db.orders.delete_one({"_id": int(txt)}) 
        await db.users.update_one({"_id": uid}, {"$inc": {"stats.stock": -len(order["items"])}}) 
        
        # 🆕 تسجيل الإرجاع في اللوجز
        await log_important_action(uid, user["name"], f"↩️ إرجاع طلب #{txt} للمخزن", f"عدد الأكواد المرجعة: {len(order['items'])}")
        
        context.user_data.clear()
        return await update.message.reply_text(f"✅ **تم إرجاع الطلب #{txt} للمخزن بنجاح!**", reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)

    elif state == "waiting_stock_count":
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=back_btn())
        count = int(txt)
        cat = context.user_data.get("target_pull_cat")
        context.user_data.clear() 
        
        if await db.stock.count_documents({"category": cat}) < count: return await update.message.reply_text("⚠️ الكمية غير كافية!", reply_markup=back_btn())

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
            await db.users.update_one({"_id": uid}, {"$push": {"history": f"📦 طلب #{order_id}"}, "$inc": {"stats.stock": len(pulled_codes)}})
            
            # 🆕 تسجيل السحب في اللوجز
            details_str = " | ".join(pulled_codes)
            await log_important_action(uid, user["name"], f"🎮 سحب {len(pulled_codes)} كود ({cat} UC) - طلب #{order_id}", details_str)

            individual = "\n".join([f"🎮 <code>{c}</code>" for c in pulled_codes])
            bulk = "\n".join(pulled_codes)
            
            msg = f"✅ **تم سحب {cat} UC بنجاح!** (طلب #{order_id})\n\n🎯 **نسخ كود بكود:**\n{individual}\n\n📋 **نسخ الكل دفعة واحدة:**\n<code>{bulk}</code>"
            return await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=success_pull_keyboard(f"pull_cat_{cat}"))

    elif state == "waiting_api_count":
        if not txt.isdigit() or int(txt) <= 0: return await update.message.reply_text("❌ أرسل رقم صحيح.", reply_markup=retry_keyboard("pull_api", "back_home"))
        qty = int(txt)
        context.user_data.clear()
        context.user_data["last_api_count"] = qty
        await process_api_pull(uid, update.message.reply_text, user, qty, context)
        return

    elif state == "waiting_tokens":
        lines = [t.strip() for t in txt.splitlines() if t.strip()]
        if lines: await db.users.update_one({"_id": uid}, {"$addToSet": {"tokens": {"$each": lines}}})
        context.user_data.clear()
        return await update.message.reply_text(f"✅ تم إضافة التوكنات.", reply_markup=retry_keyboard("add_tokens", "view_my_tokens"))

    elif state == "waiting_add_user_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        new_uid = int(txt)
        if await get_user(new_uid): return await update.message.reply_text("⚠️ هذا المستخدم موجود بالفعل!", reply_markup=retry_keyboard("admin_add_user_btn", "admin_users_menu"))
        context.user_data["new_user_id"] = new_uid
        btns = [[InlineKeyboardButton("موظف 👤", callback_data="set_role_employee")], [InlineKeyboardButton("مستخدم عادي 🆕", callback_data="set_role_user")]]
        return await update.message.reply_text(f"👤 **اختر الرتبة للآيدي:** `{new_uid}`", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)

    elif state == "waiting_remove_user_id" and uid == ADMIN_ID:
        if txt.isdigit():
            await db.users.delete_one({"_id": int(txt)})
            context.user_data.clear()
            return await update.message.reply_text(f"🗑 تم الحذف بنجاح.", reply_markup=retry_keyboard("admin_remove_user_btn", "admin_users_menu"))

    elif state == "waiting_manage_user_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target:
            msg = f"👤 **الاسم:** {target.get('name')}\n🆔 `{target['_id']}`\n🎖 **الرتبة:** {target['role']}\n🔑 **التوكنات:** {len(target.get('tokens',[]))}"
            btns = [
                [InlineKeyboardButton("🗑 تصفير التوكنات", callback_data=f"manage_clear_tokens_{target['_id']}"), InlineKeyboardButton("🔄 تغيير الرتبة", callback_data=f"manage_switch_role_{target['_id']}")],
                [InlineKeyboardButton("🗑 مسح السجلات", callback_data=f"manage_clear_logs_{target['_id']}")],
                [InlineKeyboardButton("🔍 إدارة مستخدم آخر", callback_data="admin_search_manage_user")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_users_menu")]
            ]
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ الحساب غير موجود.", reply_markup=retry_keyboard("admin_search_manage_user", "admin_users_menu"))
        context.user_data.clear()

    elif state == "waiting_user_logs_id" and uid == ADMIN_ID:
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target and target.get("logs"):
            logs_txt = "\n\n".join(target["logs"][-15:]) 
            await update.message.reply_text(f"📜 **سجلات ({txt}):**\n\n{logs_txt}", reply_markup=retry_keyboard("admin_get_user_logs_btn", "admin_users_menu"), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("📭 لا توجد سجلات لهذا الحساب.", reply_markup=retry_keyboard("admin_get_user_logs_btn", "admin_users_menu"))
        context.user_data.clear()

    # 🆕 زر بحث آخر في بحث الطلبات
    elif state == "waiting_admin_order_search" and uid == ADMIN_ID:
        if txt.isdigit():
            order = await db.orders.find_one({"_id": int(txt)})
            if order:
                items_str = "\n".join([f"<code>{i}</code>" for i in order["items"]])
                res_msg = f"📄 تقرير #{txt}\n👤 بواسطة: {order['user']}\n⬇️:\n{items_str}"
            else:
                res_msg = "❌ غير موجود."
            await update.message.reply_text(res_msg, reply_markup=retry_keyboard("admin_search_order", "admin_logs_hub"), parse_mode=ParseMode.HTML)
        context.user_data.clear()

    # 🆕 زر بحث آخر في البحث العكسي
    elif state == "waiting_reverse_code" and uid == ADMIN_ID:
        records = await db.codes_map.find({"$or": [{"_id": txt}, {"code": txt}]}).to_list(None)
        in_stock = await db.stock.count_documents({"$or": [{"_id": txt}, {"code": txt}]})
        
        if not records and in_stock == 0:
            await update.message.reply_text("❌ الكود غير موجود في النظام نهائياً.", reply_markup=retry_keyboard("admin_reverse_search", "admin_logs_hub"))
        else:
            msg = f"🔍 **نتيجة البحث عن الكود:**\n`{txt}`\n\n"
            if in_stock > 0:
                msg += f"📦 **موجود حالياً في المخزن** (عدد المرات: {in_stock})\n\n"
            
            if records:
                msg += f"🛒 **سجل السحوبات ({len(records)} مرات سحب):**\n"
                for i, r in enumerate(records, 1):
                    msg += f"--- السحبة #{i} ---\n👤 بواسطة: {r['name']}\n📅 الوقت: {r['time']}\n📦 رقم الطلب: #{r.get('order_id')}\n\n"
            else:
                msg += "لم يتم سحبه حتى الآن.\n"
            await update.message.reply_text(msg, reply_markup=retry_keyboard("admin_reverse_search", "admin_logs_hub"))
        context.user_data.clear()

    elif state == "adding_stock_manual" and uid == ADMIN_ID:
        lines = [c.strip() for c in txt.splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        if cat and lines:
            waiting_msg = await update.message.reply_text("⏳ **جاري فحص الأكواد...**", parse_mode=ParseMode.MARKDOWN)
            new_codes, dupes, all_codes = await analyze_codes(lines)
            
            context.user_data["pending_stock"] = {"all": all_codes, "new": new_codes, "dupes": dupes, "cat": cat} 
            
            btns = [[InlineKeyboardButton("✅ إضافة الكل (حتى المكرر)", callback_data="confirm_add_all")], [InlineKeyboardButton("✨ إضافة الجديد فقط", callback_data="confirm_add_new")]]
            if dupes: btns.append([InlineKeyboardButton("👁️ عرض الأكواد المكررة", callback_data="show_dupes_list")])
            btns.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")])
            
            msg = f"📊 **تقرير الأكواد المدخلة:**\n\nإجمالي الأكواد: {len(all_codes)}\n✅ أكواد جديدة: {len(new_codes)}\n⚠️ أكواد مكررة/مسحوبة: {len(dupes)}\n\n❓ ماذا تريد أن تفعل؟"
            return await waiting_msg.edit_text(msg, reply_markup=InlineKeyboardMarkup(btns))

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    
    if uid == ADMIN_ID and state == "admin_uploading_file":
        doc = update.message.document
        if not doc.file_name.endswith(".txt"): return
        
        waiting_msg = await update.message.reply_text("⏳ **جاري تحميل وفحص الملف...**", parse_mode=ParseMode.MARKDOWN)
        
        file = await doc.get_file()
        content = await file.download_as_bytearray()
        lines = [c.strip() for c in content.decode("utf-8", errors="ignore").splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        
        if cat and lines:
            new_codes, dupes, all_codes = await analyze_codes(lines)
            context.user_data["pending_stock"] = {"all": all_codes, "new": new_codes, "dupes": dupes, "cat": cat} 
            
            btns = [[InlineKeyboardButton("✅ استيراد الكل (حتى المكرر)", callback_data="confirm_add_all")], [InlineKeyboardButton("✨ استيراد الجديد فقط", callback_data="confirm_add_new")]]
            if dupes: btns.append([InlineKeyboardButton("👁️ عرض الأكواد المكررة", callback_data="show_dupes_list")])
            btns.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_add_stock")])
            
            msg = f"📂 **تقرير ملف الأكواد:**\n\nإجمالي الأكواد: {len(all_codes)}\n✅ أكواد جديدة: {len(new_codes)}\n⚠️ أكواد مكررة/مسحوبة: {len(dupes)}\n\n❓ ماذا تريد أن تفعل؟"
            await waiting_msg.edit_text(msg, reply_markup=InlineKeyboardMarkup(btns))
