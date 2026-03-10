import io
import re
import httpx
import traceback
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_ID, API_BASE_URL, PRODUCT_ID, logger
from database import db, get_user, check_maintenance, get_tracked_users, get_next_order_id, analyze_codes, log_important_action, get_dynamic_categories, get_bot_product_state
from keyboards import (get_main_keyboard, admin_keyboard, auto_cache_keyboard, 
                       admin_users_keyboard, stock_manage_keyboard, categories_keyboard, 
                       success_pull_keyboard, back_btn, admin_back_btn, admin_users_back_btn, 
                       profile_keyboard, admin_logs_keyboard, admin_logs_back_btn, retry_keyboard,
                       shared_tokens_keyboard)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("âŒ Ø­Ø¯Ø« Ø®Ø·Ø£:", exc_info=context.error)
    tb_string = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    log_file = io.BytesIO(tb_string.encode('utf-8'))
    log_file.name = f"Crash_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        if update and hasattr(update, 'effective_message') and update.effective_message:
            await context.bot.send_document(chat_id=ADMIN_ID, document=log_file, caption="ðŸš¨ <b>Ø­Ø¯Ø« Ø®Ø·Ø£ Ø¨Ø±Ù…Ø¬ÙŠ ØºÙŠØ± Ù…ØªÙˆÙ‚Ø¹!</b>", parse_mode=ParseMode.HTML)
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
        return await reply_func("âš ï¸ <b>Ù„Ø§ ÙŠÙˆØ¬Ø¯ ØªÙˆÙƒÙ†Ø§Øª ÙƒØ§ÙÙŠØ©!</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
        
    tokens_to_use = personal_to_use + shared_to_use
    waiting_msg = await reply_func(f"â³ <b>Ø¬Ø§Ø±ÙŠ Ø§Ù„Ø³Ø­Ø¨ Ø¨Ø§Ø³ØªØ®Ø¯Ø§Ù… {len(tokens_to_use)} ØªÙˆÙƒÙ†...</b>", parse_mode=ParseMode.HTML)
    
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
                    token_logs_updates.append(f"âœ… Ù†Ø¬Ø§Ø­ | {short_t} | {a['email']}")
                else:
                    token_logs_updates.append(f"âŒ ÙØ´Ù„ | {short_t} | {r.get('message', 'Ù…Ø¬Ù‡ÙˆÙ„')}")
            except Exception as e:
                token_logs_updates.append(f"âš ï¸ Ø®Ø·Ø£ | {short_t}")

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
        await db.users.update_one({"_id": uid}, {"$push": {"history": f"ðŸš€ Ø·Ù„Ø¨ <code>#{order_id}</code>"}, "$inc": {"stats.api": len(accs)}})
        await log_important_action(uid, user["name"], f"ðŸš€ Ø³Ø­Ø¨ {len(accs)} Ø­Ø³Ø§Ø¨ API (Ø·Ù„Ø¨ #{order_id})", " | ".join(raw_accs))
        
        context.user_data["pending_topup_qty"] = len(accs)
        btns = [
            [InlineKeyboardButton("âœ… ØªÙ… Ø§Ù„Ø´Ø­Ù† (Ø¯Ù†)", callback_data="topup_done"), InlineKeyboardButton("âŒ Ù…ØªÙ…ØªØ´ (Ù…Ø´ÙƒÙ„Ø©)", callback_data="topup_failed")],
            [InlineKeyboardButton(f"ðŸ”„ Ø³Ø­Ø¨ Ø­Ø³Ø§Ø¨ Ø¢Ø®Ø± ({qty})", callback_data="pull_api_again")],
            [InlineKeyboardButton("ðŸ”™ Ø§Ù„Ù‚Ø§Ø¦Ù…Ø© Ø§Ù„Ø±Ø¦ÙŠØ³ÙŠØ©", callback_data="back_home")]
        ]
        display_txt = "\nâ”â”â”â”â”â”â”â”â”â”â”â”\n".join(accs)
        await waiting_msg.edit_text(f"âœ… <b>ØªÙ… Ø§Ù„Ø³Ø­Ø¨ Ø¨Ù†Ø¬Ø§Ø­ (Ø·Ù„Ø¨ <code>#{order_id}</code>):</b>\n\n{display_txt}", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btns))
    else:
        btns = [[InlineKeyboardButton(f"ðŸ”„ Ù…Ø­Ø§ÙˆÙ„Ø© Ø£Ø®Ø±Ù‰ ({qty})", callback_data="pull_api_again")], [InlineKeyboardButton("ðŸ”™ Ø§Ù„Ù‚Ø§Ø¦Ù…Ø© Ø§Ù„Ø±Ø¦ÙŠØ³ÙŠØ©", callback_data="back_home")]]
        await waiting_msg.edit_text("âŒ <b>ÙØ´Ù„ Ø§Ù„Ø³Ø­Ø¨ Ù…Ù† Ø§Ù„ØªÙˆÙƒÙ†Ø§Øª.</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btns))

async def process_stock_pull(uid, reply_func, user, cat, count, context):
    bot_state = await get_bot_product_state(cat)
    if bot_state and not bot_state.get("is_visible_bot", True):
        return await reply_func("<b>This stock is not available for bot pulls.</b>", parse_mode=ParseMode.HTML, reply_markup=back_btn())

    remaining_bot = None if not bot_state else bot_state.get("remaining_bot")
    if remaining_bot is not None and int(remaining_bot) < count:
        return await reply_func(f"<b>Only {remaining_bot} bot allocation slots remain for {cat}.</b>", parse_mode=ParseMode.HTML, reply_markup=back_btn())

    if await db.stock.count_documents({"category": cat}) < count:
        return await reply_func("<b>Not enough stock is available in this category.</b>", parse_mode=ParseMode.HTML, reply_markup=back_btn())

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
        await db.users.update_one({"_id": uid}, {"$push": {"history": f"Stock pull <code>#{order_id}</code>"}, "$inc": {"stats.stock": len(pulled_codes)}})
        await log_important_action(uid, user["name"], f"Pulled {len(pulled_codes)} stock code(s) ({cat}) - Order #{order_id}", " | ".join(pulled_codes))

        individual = "\n".join([f"- <code>{code}</code>" for code in pulled_codes])
        bulk = "\n".join(pulled_codes)
        msg = (
            f"<b>Stock pull completed for {cat}.</b> (Order <code>#{order_id}</code>)\n\n"
            f"<b>Individual codes:</b>\n{individual}\n\n"
            f"<b>Plain list:</b>\n<code>{bulk}</code>"
        )
        return await reply_func(msg, parse_mode=ParseMode.HTML, reply_markup=success_pull_keyboard(f"pull_cat_{cat}"))


async def process_cache_pull(uid, reply_func, user, qty, context):
    await db.cached_accounts.delete_many({"added_at": {"$lt": datetime.now() - timedelta(hours=24)}})
    available = await db.cached_accounts.count_documents({})
    if qty > available: return await reply_func(f"âš ï¸ <b>Ø§Ù„ÙƒÙ…ÙŠØ© ØºÙŠØ± ÙƒØ§ÙÙŠØ©!</b> Ø§Ù„Ù…ØªØ§Ø­: <code>{available}</code>", parse_mode=ParseMode.HTML, reply_markup=back_btn())
        
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
        await log_important_action(uid, user["name"], f"â™»ï¸ Ø³Ø­Ø¨ {len(pulled_accs)} Ø­Ø³Ø§Ø¨ ØªØ®Ø²ÙŠÙ† (24Ø³)", " | ".join(raw_accs_for_log))
        msg = "\nâ”â”â”â”â”â”â”â”â”â”â”â”\n".join(pulled_accs)
        return await reply_func(f"âœ… <b>Ø³Ø­Ø¨ {len(pulled_accs)} Ø­Ø³Ø§Ø¨:</b>\n\n{msg}", parse_mode=ParseMode.HTML, reply_markup=retry_keyboard("pull_cached_api", "back_home"))

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user or user["role"] not in ["admin", "employee"]: return
    help_text = """âš¡ <b>Ø§Ù„Ø£ÙˆØ§Ù…Ø± Ø§Ù„Ø³Ø±ÙŠØ¹Ø© Ù„ØªØ³Ø±ÙŠØ¹ Ø§Ù„Ø´ØºÙ„:</b>\n\nðŸŽ® <b>Ø³Ø­Ø¨ Ø£ÙƒÙˆØ§Ø¯:</b>\n<code>/pull [Ø§Ù„ÙØ¦Ø©] [Ø§Ù„Ø¹Ø¯Ø¯]</code>\nÙ…Ø«Ø§Ù„: <code>/pull 60_uc 5</code>\n\nðŸš€ <b>Ø³Ø­Ø¨ Ø­Ø³Ø§Ø¨Ø§Øª API:</b>\n<code>/api [Ø§Ù„Ø¹Ø¯Ø¯]</code>"""
    if user["role"] == "admin": help_text += "\n\nâ™»ï¸ <b>Ø³Ø­Ø¨ ØªØ®Ø²ÙŠÙ† (24Ø³):</b>\n<code>/cache [Ø§Ù„Ø¹Ø¯Ø¯]</code>\n\nðŸ“‚ <b>Ø§Ù„Ø±ÙØ¹ Ø§Ù„Ø°ÙƒÙŠ:</b>\nØ£Ø±Ø³Ù„ Ø£ÙŠ Ù…Ù„Ù <code>.txt</code> ÙˆØ³ÙŠØªØ¹Ø±Ù Ø¹Ù„ÙŠÙ‡ Ø§Ù„Ø¨ÙˆØª."
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def cmd_pull(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user or user["role"] not in ["admin", "employee"]: return
    if len(context.args) != 2: return await update.message.reply_text("âŒ <b>Ø§Ø³ØªØ®Ø¯Ù…:</b> <code>/pull 60_uc 5</code>", parse_mode=ParseMode.HTML)
    cat, count_str = context.args
    
    stock_keys = await get_dynamic_categories()
    if cat not in stock_keys or not count_str.isdigit() or int(count_str) <= 0: 
        return await update.message.reply_text("âŒ <b>ÙØ¦Ø© ØºÙŠØ± ØµØ§Ù„Ø­Ø© Ø£Ùˆ Ø¹Ø¯Ø¯ ØºÙŠØ± ØµØ­ÙŠØ­.</b>", parse_mode=ParseMode.HTML)
    await process_stock_pull(uid, update.message.reply_text, user, cat, int(count_str), context)

async def cmd_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user: return
    if not context.args or not context.args[0].isdigit() or int(context.args[0]) <= 0: return await update.message.reply_text("âŒ <b>Ø§Ø³ØªØ®Ø¯Ù…:</b> <code>/api 2</code>", parse_mode=ParseMode.HTML)
    qty = int(context.args[0])
    context.user_data["last_api_count"] = qty
    await process_api_pull(uid, update.message.reply_text, user, qty, context)

async def cmd_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user or user["role"] != "admin": return
    if not context.args or not context.args[0].isdigit() or int(context.args[0]) <= 0: return await update.message.reply_text("âŒ <b>Ø§Ø³ØªØ®Ø¯Ù…:</b> <code>/cache 5</code>", parse_mode=ParseMode.HTML)
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
    if not user: return await update.message.reply_text("â›” ØºÙŠØ± Ù…Ø³Ø¬Ù„.")
    if user.get("name") != name: await db.users.update_one({"_id": user_id}, {"$set": {"name": name}})

    role = user.get("role", "user")
    maint_msg = "\nâš ï¸ <b>Ø§Ù„Ù†Ø¸Ø§Ù… ÙÙŠ ÙˆØ¶Ø¹ Ø§Ù„ØµÙŠØ§Ù†Ø©</b>" if await check_maintenance() else ""
    stats_msg = ""
    if role in ["admin", "employee"]:
        stock_count = await db.stock.count_documents({})
        cache_count = await db.cached_accounts.count_documents({})
        stats_msg = f"\n\nðŸ“Š <b>Ù†Ø¸Ø±Ø© Ø³Ø±ÙŠØ¹Ø©:</b>\nðŸ“¦ Ø§Ù„Ù…Ø®Ø²Ù†: <code>{stock_count}</code> ÙƒÙˆØ¯\nâ™»ï¸ Ø§Ù„ØªØ®Ø²ÙŠÙ† Ø§Ù„ØªÙ„Ù‚Ø§Ø¦ÙŠ: <code>{cache_count}</code> Ø­Ø³Ø§Ø¨"

    await update.message.reply_text(f"ðŸ‘‹ Ø£Ù‡Ù„Ø§Ù‹ <b>{name}</b>\nðŸ”¹ Ø§Ù„Ø±ØªØ¨Ø©: {role}{maint_msg}{stats_msg}", reply_markup=get_main_keyboard(role), parse_mode=ParseMode.HTML)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    user = await get_user(uid)
    if not user: return
    role = user.get("role", "user")

    if await check_maintenance() and role != "admin": 
        await query.answer()
        return await query.edit_message_text("âš ï¸ <b>Ø§Ù„ØµÙŠØ§Ù†Ø© Ø¬Ø§Ø±ÙŠØ©...</b>", parse_mode=ParseMode.HTML)
    
    if data == "back_home":
        context.user_data.clear()
        await query.answer()
        return await query.edit_message_text("ðŸ  Ø§Ù„Ù‚Ø§Ø¦Ù…Ø© Ø§Ù„Ø±Ø¦ÙŠØ³ÙŠØ©:", reply_markup=get_main_keyboard(role))

    if data == "topup_done":
        qty = context.user_data.get("pending_topup_qty", 0)
        if qty > 0:
            await db.users.update_one({"_id": uid}, {"$inc": {"stats.topups": qty}})
            context.user_data.pop("pending_topup_qty", None)
        await query.answer("âœ… ØªÙ… Ø§Ø­ØªØ³Ø§Ø¨ Ø§Ù„Ø´Ø­Ù†Ø© Ø¨Ù†Ø¬Ø§Ø­!", show_alert=True)
        new_btns = [[InlineKeyboardButton("ðŸ”„ Ø³Ø­Ø¨ Ø­Ø³Ø§Ø¨ Ø¢Ø®Ø±", callback_data="pull_api_again")], [InlineKeyboardButton("ðŸ”™ Ø§Ù„Ù‚Ø§Ø¦Ù…Ø© Ø§Ù„Ø±Ø¦ÙŠØ³ÙŠØ©", callback_data="back_home")]]
        return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_btns))

    if data == "topup_failed":
        context.user_data.pop("pending_topup_qty", None)
        await query.answer("âŒ ØªÙ… Ø§Ù„Ø¥Ù„ØºØ§Ø¡ØŒ Ù„Ù… ÙŠØªÙ… Ø§Ø­ØªØ³Ø§Ø¨ Ù‡Ø°Ù‡ Ø§Ù„Ø´Ø­Ù†Ø©.", show_alert=True)
        new_btns = [[InlineKeyboardButton("ðŸ”„ Ø³Ø­Ø¨ Ø­Ø³Ø§Ø¨ Ø¢Ø®Ø±", callback_data="pull_api_again")], [InlineKeyboardButton("ðŸ”™ Ø§Ù„Ù‚Ø§Ø¦Ù…Ø© Ø§Ù„Ø±Ø¦ÙŠØ³ÙŠØ©", callback_data="back_home")]]
        return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_btns))

    if data == "pull_cached_api" and role == "admin":
        await query.answer()
        await db.cached_accounts.delete_many({"added_at": {"$lt": datetime.now() - timedelta(hours=24)}})
        count = await db.cached_accounts.count_documents({})
        if count == 0: return await query.edit_message_text("ðŸ“­ <b>Ø§Ù„Ù…Ø®Ø²Ù† ÙØ§Ø±Øº</b>.", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
        context.user_data["state"] = "waiting_cached_api_count"
        return await query.edit_message_text(f"â™»ï¸ <b>Ø§Ù„Ù…ØªØ§Ø­ Ø§Ù„Ø¢Ù†:</b> <code>{count}</code> Ø­Ø³Ø§Ø¨\n\nðŸ”¢ <b>Ø£Ø±Ø³Ù„ Ø§Ù„Ø¹Ø¯Ø¯:</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

    if data == "admin_logs_hub" and role == "admin":
        await query.answer()
        context.user_data.clear()
        return await query.edit_message_text("ðŸ“œ <b>Ù…Ø±ÙƒØ² Ø§Ù„Ø³Ø¬Ù„Ø§Øª ÙˆØ§Ù„Ø¨Ø­Ø«</b>", reply_markup=admin_logs_keyboard(), parse_mode=ParseMode.HTML)

    if data == "admin_shared_tokens_menu" and role == "admin":
        await query.answer()
        doc = await db.settings.find_one({"_id": "shared_tokens"})
        count = len(doc.get("tokens", [])) if doc else 0
        return await query.edit_message_text(f"ðŸ”— <b>Ø¥Ø¯Ø§Ø±Ø© Ø§Ù„ØªÙˆÙƒÙ†Ø§Øª Ø§Ù„Ù…Ø´ØªØ±ÙƒØ©</b>\n\nØ§Ù„Ø¹Ø¯Ø¯ Ø§Ù„Ø­Ø§Ù„ÙŠ: <code>{count}</code> ØªÙˆÙƒÙ†", reply_markup=shared_tokens_keyboard(), parse_mode=ParseMode.HTML)

    if data == "view_shared_tokens" and role == "admin":
        await query.answer()
        doc = await db.settings.find_one({"_id": "shared_tokens"})
        tokens = doc.get("tokens", []) if doc else []
        if not tokens: return await query.edit_message_text("ðŸ“­ <b>Ù„Ø§ ÙŠÙˆØ¬Ø¯ ØªÙˆÙƒÙ†Ø§Øª.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)
        txt = "\n".join([f"<code>{t}</code>" for t in tokens[:100]])
        return await query.edit_message_text(f"ðŸ“‹ <b>Ø§Ù„ØªÙˆÙƒÙ†Ø§Øª:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)

    if data == "add_shared_tokens_btn" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_shared_tokens"
        return await query.edit_message_text("ðŸ“ <b>Ø£Ø±Ø³Ù„ Ø§Ù„ØªÙˆÙƒÙ†Ø§Øª:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)

    if data == "clear_shared_tokens" and role == "admin":
        await query.answer()
        await db.settings.update_one({"_id": "shared_tokens"}, {"$set": {"tokens": []}}, upsert=True)
        return await query.edit_message_text("ðŸ—‘ <b>ØªÙ… ØªØµÙÙŠØ± Ø§Ù„ØªÙˆÙƒÙ†Ø§Øª.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)

    if data == "admin_global_search" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_global_search"
        return await query.edit_message_text("ðŸ” <b>Ø§Ù„Ø¨Ø­Ø« Ø§Ù„Ø´Ø§Ù…Ù„:</b>\n\nØ£Ø±Ø³Ù„ (<code>ÙƒÙˆØ¯</code> / <code>Ø±Ù‚Ù… Ø·Ù„Ø¨</code> / <code>Ø¢ÙŠØ¯ÙŠ Ù…Ø³ØªØ®Ø¯Ù…</code>)", reply_markup=admin_logs_back_btn(), parse_mode=ParseMode.HTML)

    if data == "admin_auto_cache_menu" and role == "admin":
        await query.answer()
        return await query.edit_message_text("â™»ï¸ <b>Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§Ù„ØªØ®Ø²ÙŠÙ† Ø§Ù„ØªÙ„Ù‚Ø§Ø¦ÙŠ</b>", reply_markup=auto_cache_keyboard(), parse_mode=ParseMode.HTML)

    if data == "list_tracked_users" and role == "admin":
        await query.answer()
        tracked = await get_tracked_users()
        txt = "\n".join([f"ðŸ†” <code>{t}</code>" for t in tracked])
        return await query.edit_message_text(f"ðŸ“‹ <b>Ù‚Ø§Ø¦Ù…Ø© Ø§Ù„Ù…Ø±Ø§Ù‚Ø¨Ø©:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_auto_cache_menu")]]), parse_mode=ParseMode.HTML)

    if data == "add_tracked_user" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_add_tracked"
        return await query.edit_message_text("âœï¸ <b>Ø£Ø±Ø³Ù„ Ø§Ù„Ø¢ÙŠØ¯ÙŠ Ø§Ù„Ù…Ø±Ø§Ø¯ Ø¥Ø¶Ø§ÙØªÙ‡:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_auto_cache_menu")]]), parse_mode=ParseMode.HTML)

    if data == "remove_tracked_user" and role == "admin":
        await query.answer()
        context.user_data["state"] = "waiting_remove_tracked"
        return await query.edit_message_text("ðŸ—‘ <b>Ø£Ø±Ø³Ù„ Ø§Ù„Ø¢ÙŠØ¯ÙŠ Ø§Ù„Ù…Ø±Ø§Ø¯ Ø¥Ø²Ø§Ù„ØªÙ‡:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_auto_cache_menu")]]), parse_mode=ParseMode.HTML)

    if data == "my_profile":
        await query.answer()
        t_count = len(user.get("tokens", []))
        st = user.get("stats", {"api": 0, "stock": 0, "topups": 0})
        msg = f"ðŸ’³ <b>Ø­Ø³Ø§Ø¨Ùƒ:</b>\nðŸ‘¤ Ø§Ù„Ø§Ø³Ù…: {user.get('name')}\nðŸŽ– Ø§Ù„Ø±ØªØ¨Ø©: {role}\nðŸ”‘ ØªÙˆÙƒÙ†Ø§Øª: <code>{t_count}</code>\n\nðŸ›’ <b>Ø§Ù„Ø³Ø­ÙˆØ¨Ø§Øª:</b>\nðŸŽ® Ø£ÙƒÙˆØ§Ø¯: <code>{st.get('stock',0)}</code>\nðŸš€ API: <code>{st.get('api',0)}</code>\nâš¡ Ø´Ø­Ù†Ø§Øª: <code>{st.get('topups', 0)}</code>"
        return await query.edit_message_text(msg, reply_markup=profile_keyboard(role), parse_mode=ParseMode.HTML)

    if data == "view_my_tokens":
        await query.answer()
        tokens = user.get("tokens", [])
        txt = "\n".join([f"ðŸ”‘ <code>{t[:8]}...{t[-4:]}</code>" for t in tokens]) if tokens else "ðŸ“­ Ù„Ø§ ÙŠÙˆØ¬Ø¯ ØªÙˆÙƒÙ†Ø§Øª."
        btns = [[InlineKeyboardButton("âž• Ø¥Ø¶Ø§ÙØ© ØªÙˆÙƒÙ†", callback_data="add_tokens")], [InlineKeyboardButton("ðŸ“œ Ø³Ø¬Ù„ Ø§Ù„ØªÙˆÙƒÙ†Ø§Øª", callback_data="view_token_logs")]]
        if tokens: btns.append([InlineKeyboardButton("ðŸ—‘ Ø­Ø°Ù Ø¬Ù…ÙŠØ¹ ØªÙˆÙƒÙ†Ø§ØªÙŠ", callback_data="clear_tokens")])
        btns.append([InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="my_profile")])
        return await query.edit_message_text(f"ðŸ“‹ <b>ØªÙˆÙƒÙ†Ø§ØªÙƒ ({len(tokens)}):</b>\n\n{txt}" if tokens else txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    if data == "view_token_logs":
        await query.answer()
        logs = user.get("token_logs", [])
        if not logs: return await query.edit_message_text("ðŸ“­ Ù„Ø§ ÙŠÙˆØ¬Ø¯ Ø³Ø¬Ù„.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)
        txt = "\n".join(logs[-30:])
        return await query.edit_message_text(f"ðŸ“œ <b>Ø³Ø¬Ù„ Ø§Ù„ØªÙˆÙƒÙ†Ø§Øª:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)

    if data == "clear_tokens":
        await query.answer()
        await db.users.update_one({"_id": uid}, {"$set": {"tokens": []}})
        return await query.edit_message_text("ðŸ—‘ <b>ØªÙ… Ø­Ø°Ù Ø§Ù„ØªÙˆÙƒÙ†Ø§Øª.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)

    if data == "add_tokens":
        await query.answer()
        context.user_data["state"] = "waiting_tokens"
        return await query.edit_message_text("ðŸ“ <b>Ø£Ø±Ø³Ù„ Ø§Ù„ØªÙˆÙƒÙ†Ø§Øª:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="view_my_tokens")]]), parse_mode=ParseMode.HTML)

    if data == "my_history":
        await query.answer()
        hist = user.get("history", [])
        txt = "\n".join([f"<code>{h}</code>" for h in hist[-10:]]) if hist else "ðŸ“‚ Ø£Ø±Ø´ÙŠÙÙƒ ÙØ§Ø±Øº."
        btns = [[InlineKeyboardButton("ðŸ” Ø§Ù„Ø¨Ø­Ø« Ø¹Ù† Ø·Ù„Ø¨", callback_data="check_order_id")]]
        if role in ["admin", "employee"]: btns.append([InlineKeyboardButton("â†©ï¸ Ø¥Ø±Ø¬Ø§Ø¹ Ø·Ù„Ø¨", callback_data="return_order")])
        btns.append([InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="my_profile")])
        return await query.edit_message_text(f"ðŸ“‚ <b>Ø¢Ø®Ø± 10 Ø¹Ù…Ù„ÙŠØ§Øª:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    if data == "check_order_id":
        await query.answer()
        context.user_data["state"] = "waiting_order_id"
        return await query.edit_message_text("ðŸ” <b>Ø£Ø±Ø³Ù„ Ø±Ù‚Ù… Ø§Ù„Ø·Ù„Ø¨:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø§Ù„Ø¹ÙˆØ¯Ø© Ù„Ù„Ø£Ø±Ø´ÙŠÙ", callback_data="my_history")]]), parse_mode=ParseMode.HTML)

    if data == "return_order" and role in ["admin", "employee"]:
        await query.answer()
        context.user_data["state"] = "waiting_return_order_id"
        return await query.edit_message_text("â†©ï¸ <b>Ø£Ø±Ø³Ù„ Ø±Ù‚Ù… Ø§Ù„Ø·Ù„Ø¨ Ø§Ù„Ù…Ø±Ø§Ø¯ Ø¥Ø±Ø¬Ø§Ø¹Ù‡:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹ Ù„Ù„Ø£Ø±Ø´ÙŠÙ", callback_data="my_history")]]), parse_mode=ParseMode.HTML)

    if data == "pull_stock_menu" and role in ["admin", "employee"]: 
        await query.answer()
        return await query.edit_message_text("ðŸŽ® <b>Ø§Ø®ØªØ± Ø§Ù„ÙØ¦Ø© Ù„Ù„Ø³Ø­Ø¨:</b>", reply_markup=await categories_keyboard("pull_cat", db), parse_mode=ParseMode.HTML)
    
    if data.startswith("pull_cat_") and role in ["admin", "employee"]:
        await query.answer()
        cat = data.split("pull_cat_")[-1]
        context.user_data["state"] = "waiting_stock_count"
        context.user_data["target_pull_cat"] = cat
        return await query.edit_message_text(f"ðŸ”¢ <b>Ø£Ø±Ø³Ù„ Ø§Ù„Ø¹Ø¯Ø¯ Ù„Ù€ {cat}:</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

    if data == "pull_api":
        await query.answer()
        tokens = user.get("tokens", [])
        shared_doc = await db.settings.find_one({"_id": "shared_tokens"})
        shared_tokens = shared_doc.get("tokens", []) if shared_doc else []
        
        if not tokens and (role == "user" or not shared_tokens):
             return await query.edit_message_text("âš ï¸ <b>Ù„Ø§ ÙŠÙˆØ¬Ø¯ ØªÙˆÙƒÙ†Ø§Øª!</b> Ø£Ø¶Ù ØªÙˆÙƒÙ† Ø£ÙˆÙ„Ø§Ù‹.", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
             
        context.user_data["state"] = "waiting_api_count"
        return await query.edit_message_text("ðŸ”¢ <b>Ø£Ø±Ø³Ù„ Ø¹Ø¯Ø¯ Ø§Ù„Ø­Ø³Ø§Ø¨Ø§Øª Ù„Ø³Ø­Ø¨Ù‡Ø§:</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

    if data == "pull_api_again":
        await query.answer()
        qty = context.user_data.get("last_api_count", 1)
        await process_api_pull(uid, query.message.reply_text, user, qty, context)
        return

    if data == "admin_panel" and role == "admin":
        await query.answer()
        st = await db.stock.count_documents({})
        return await query.edit_message_text(f"ðŸ›  <b>Ø§Ù„Ø£Ø¯Ù…Ù†</b>\nðŸ“¦ Ø§Ù„Ù…Ø®Ø²Ù†: <code>{st}</code>", reply_markup=await admin_keyboard(), parse_mode=ParseMode.HTML)
    
    if data == "admin_stock_menu" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("ðŸ“¦ <b>Ø§Ù„Ù…Ø®Ø²Ù†:</b>", reply_markup=stock_manage_keyboard(), parse_mode=ParseMode.HTML)
    
    if data == "admin_choose_cat_manual" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("ðŸ”¢ <b>Ø§Ø®ØªØ± Ø§Ù„ÙØ¦Ø© Ù„Ù„Ø¥Ø¶Ø§ÙØ© Ø§Ù„ÙŠØ¯ÙˆÙŠØ©:</b>", reply_markup=await categories_keyboard("admin_add_manual", db), parse_mode=ParseMode.HTML)
    
    if data == "admin_choose_cat_file" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("ðŸ“‚ <b>Ø§Ù„Ø±ÙØ¹ Ø§Ù„Ø°ÙƒÙŠ:</b>\nØ£Ø±Ø³Ù„ Ù…Ù„Ù <code>.txt</code> Ù‡Ù†Ø§ Ù…Ø¨Ø§Ø´Ø±Ø©.", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)
    
    if data == "admin_choose_cat_clear" and role == "admin": 
        await query.answer()
        return await query.edit_message_text("ðŸ—‘ <b>Ø§Ø®ØªØ± Ø§Ù„ÙØ¦Ø© Ù„ØªØµÙÙŠØ±Ù‡Ø§:</b>", reply_markup=await categories_keyboard("admin_clear_cat", db), parse_mode=ParseMode.HTML)

    if data.startswith("admin_add_manual_") and role == "admin":
        await query.answer()
        cat = data.split("admin_add_manual_")[-1]
        context.user_data["state"] = "adding_stock_manual"
        context.user_data["target_cat"] = cat
        return await query.edit_message_text(f"âœï¸ <b>Ø£Ø±Ø³Ù„ Ø£ÙƒÙˆØ§Ø¯ {cat}:</b>", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)

    if data.startswith("admin_clear_cat_") and role == "admin":
        await query.answer()
        cat = data.split("admin_clear_cat_")[-1]
        await db.stock.delete_many({"category": cat})
        return await query.edit_message_text(f"ðŸ—‘ <b>ØªÙ… ØªØµÙÙŠØ± ÙØ¦Ø© {cat} Ø¨Ù†Ø¬Ø§Ø­.</b>", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)

    if data.startswith("smart_cat_") and role == "admin":
        await query.answer()
        cat = data.split("smart_cat_")[-1]
        lines = context.user_data.get("smart_upload_lines")
        if not lines: return await query.edit_message_text("âŒ Ø£Ø±Ø³Ù„ Ø§Ù„Ù…Ù„Ù Ù…Ø¬Ø¯Ø¯Ø§Ù‹.")
        await query.edit_message_text("â³ <b>Ø¬Ø§Ø±ÙŠ Ø§Ù„ÙØ­Øµ...</b>", parse_mode=ParseMode.HTML)
        new_codes, dupes, all_codes = await analyze_codes(lines)
        context.user_data["pending_stock"] = {"all": all_codes, "new": new_codes, "dupes": dupes, "cat": cat} 
        btns = [[InlineKeyboardButton("âœ… Ø§Ø³ØªÙŠØ±Ø§Ø¯ Ø§Ù„ÙƒÙ„", callback_data="confirm_add_all")], [InlineKeyboardButton("âœ¨ Ø§Ø³ØªÙŠØ±Ø§Ø¯ Ø§Ù„Ø¬Ø¯ÙŠØ¯", callback_data="confirm_add_new")]]
        if dupes: btns.append([InlineKeyboardButton("ðŸ‘ï¸ Ø¹Ø±Ø¶ Ø§Ù„Ù…ÙƒØ±Ø±", callback_data="show_dupes_list")])
        btns.append([InlineKeyboardButton("âŒ Ø¥Ù„ØºØ§Ø¡", callback_data="cancel_add_stock")])
        msg = f"ðŸ“‚ <b>ØªÙ‚Ø±ÙŠØ± Ø§Ù„Ø±ÙØ¹ ({cat}):</b>\nØ¥Ø¬Ù…Ø§Ù„ÙŠ: <code>{len(all_codes)}</code>\nâœ… Ø¬Ø¯ÙŠØ¯: <code>{len(new_codes)}</code>\nâš ï¸ Ù…ÙƒØ±Ø±: <code>{len(dupes)}</code>"
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
            await log_important_action(uid, user["name"], f"ðŸ“¥ Ø¥Ø¶Ø§ÙØ© {len(docs)} ÙƒÙˆØ¯ Ù„ÙØ¦Ø© {pending['cat']}")

        context.user_data.clear()
        btns = [[InlineKeyboardButton("âž• Ø¥Ø¶Ø§ÙØ© Ø§Ù„Ù…Ø²ÙŠØ¯", callback_data="admin_choose_cat_manual")], [InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_stock_menu")]]
        return await query.edit_message_text(f"âœ… <b>ØªÙ… Ø¥Ø¶Ø§ÙØ© Ø§Ù„Ø£ÙƒÙˆØ§Ø¯ Ø¨Ù†Ø¬Ø§Ø­.</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
        
    if data == "show_dupes_list" and role == "admin":
        pending = context.user_data.get("pending_stock")
        if not pending or not pending.get("dupes"): return await query.answer("Ù„Ø§ ÙŠÙˆØ¬Ø¯!", show_alert=True)
        dupes_list = pending["dupes"]
        txt = "\n".join([f"<code>{d}</code>" for d in dupes_list[:50]])
        if len(dupes_list) > 50: txt += f"\n... Ùˆ {len(dupes_list)-50} Ø£Ø®Ø±Ù‰."
        await query.answer() 
        return await query.message.reply_text(f"âš ï¸ <b>Ø§Ù„Ù…ÙƒØ±Ø± ({len(dupes_list)}):</b>\n\n{txt}", parse_mode=ParseMode.HTML)

    if data in ["file_shared_tokens", "file_personal_tokens"] and role in ["admin", "employee"]:
        await query.answer()
        lines = context.user_data.get("smart_upload_lines", [])
        valid_tokens = [re.split(r'[;:\s\|]', l)[0].strip() for l in lines if len(re.split(r'[;:\s\|]', l)[0].strip()) > 15]
        
        if not valid_tokens: return await query.edit_message_text("âŒ <b>Ù„Ø§ ÙŠÙˆØ¬Ø¯ ØªÙˆÙƒÙ†Ø§Øª ØµØ§Ù„Ø­Ø©!</b>", parse_mode=ParseMode.HTML)
            
        if data == "file_shared_tokens" and role == "admin":
            await db.settings.update_one({"_id": "shared_tokens"}, {"$push": {"tokens": {"$each": valid_tokens}}}, upsert=True)
            msg = f"âœ… ØªÙ… Ø¥Ø¶Ø§ÙØ© <code>{len(valid_tokens)}</code> ØªÙˆÙƒÙ† Ù…Ø´ØªØ±Ùƒ."
        else:
            await db.users.update_one({"_id": uid}, {"$push": {"tokens": {"$each": valid_tokens}}})
            msg = f"âœ… ØªÙ… Ø¥Ø¶Ø§ÙØ© <code>{len(valid_tokens)}</code> ØªÙˆÙƒÙ† Ø´Ø®ØµÙŠ."
            
        context.user_data.clear()
        return await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=back_btn())

    if data == "cancel_add_stock" and role == "admin":
        await query.answer()
        context.user_data.clear()
        return await query.edit_message_text("âŒ <b>ØªÙ… Ø§Ù„Ø¥Ù„ØºØ§Ø¡.</b>", reply_markup=admin_back_btn(), parse_mode=ParseMode.HTML)

    if data == "admin_users_menu" and role == "admin":
        await query.answer()
        context.user_data.clear()
        c = await db.users.count_documents({})
        msg = f"ðŸ‘¥ <b>Ø¥Ø¯Ø§Ø±Ø© Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…ÙŠÙ†</b> (<code>{c}</code>)\n\n"
        async for u in db.users.find().sort("_id", -1).limit(20):
             ic = "ðŸ‘®â€â™‚ï¸" if u.get('role') == "admin" else "ðŸ‘¤" if u.get('role') == "employee" else "ðŸ†•"
             msg += f"{ic} <code>{u['_id']}</code> | {u.get('name', 'Ø¨Ø¯ÙˆÙ† Ø§Ø³Ù…')}\n"
        return await query.edit_message_text(msg, reply_markup=admin_users_keyboard(), parse_mode=ParseMode.HTML)

    if data in ["admin_add_user_btn", "admin_remove_user_btn", "admin_search_manage_user", "admin_get_user_logs_btn"] and role == "admin":
        await query.answer()
        states = {
            "admin_add_user_btn": ("waiting_add_user_id", "âœï¸ <b>Ø£Ø±Ø³Ù„ Ø§Ù„Ø¢ÙŠØ¯ÙŠ Ù„Ù„Ø¥Ø¶Ø§ÙØ©:</b>"),
            "admin_remove_user_btn": ("waiting_remove_user_id", "ðŸ—‘ <b>Ø£Ø±Ø³Ù„ Ø§Ù„Ø¢ÙŠØ¯ÙŠ Ù„Ù„Ø­Ø°Ù:</b>"),
            "admin_search_manage_user": ("waiting_manage_user_id", "ðŸ” <b>Ø£Ø±Ø³Ù„ Ø§Ù„Ø¢ÙŠØ¯ÙŠ Ù„Ù„ØªØ­ÙƒÙ…:</b>"),
            "admin_get_user_logs_btn": ("waiting_user_logs_id", "ðŸ“œ <b>Ø£Ø±Ø³Ù„ Ø§Ù„Ø¢ÙŠØ¯ÙŠ Ù„Ù„Ø³Ø¬Ù„Ø§Øª:</b>")
        }
        context.user_data["state"] = states[data][0]
        return await query.edit_message_text(states[data][1], reply_markup=admin_users_back_btn(), parse_mode=ParseMode.HTML)

    if data.startswith("manage_clear_tokens_") and role == "admin":
        tid = int(data.split("_")[-1])
        await db.users.update_one({"_id": tid}, {"$set": {"tokens": []}})
        return await query.answer("âœ… ØªÙ… Ø§Ù„ØªØµÙÙŠØ±", show_alert=True)
        
    if data.startswith("manage_switch_role_") and role == "admin":
        tid = int(data.split("_")[-1])
        target = await get_user(tid)
        if target and target["_id"] != ADMIN_ID:
            nr = "employee" if target["role"] == "user" else "user"
            await db.users.update_one({"_id": tid}, {"$set": {"role": nr}})
            return await query.answer(f"âœ… Ø£ØµØ¨Ø­: {nr}", show_alert=True)
        return await query.answer("âŒ Ù„Ø§ ÙŠÙ…ÙƒÙ† ØªØ¹Ø¯ÙŠÙ„Ù‡", show_alert=True)
        
    if data.startswith("manage_clear_logs_") and role == "admin":
        tid = int(data.split("_")[-1])
        await db.users.update_one({"_id": tid}, {"$set": {"logs": [], "history": [], "token_logs": []}})
        return await query.answer("âœ… ØªÙ… Ø§Ù„Ù…Ø³Ø­", show_alert=True)

    if data.startswith("set_role_") and role == "admin":
        await query.answer()
        new_uid = context.user_data.get("new_user_id")
        if not new_uid: return
        r = "employee" if data == "set_role_employee" else "user"
        await db.users.insert_one({"_id": new_uid, "role": r, "name": "User", "tokens": [], "history": [], "logs": [], "token_logs": [], "stats": {"api":0,"stock":0,"topups":0}})
        context.user_data.clear()
        return await query.edit_message_text(f"âœ… ØªÙ… Ø¥Ø¶Ø§ÙØ© <code>{new_uid}</code> ÙƒØ±ØªØ¨Ø© <b>{r}</b>.", reply_markup=retry_keyboard("admin_add_user_btn", "admin_users_menu"), parse_mode=ParseMode.HTML)

    if data == "admin_get_logs" and role == "admin":
        await query.answer()
        await query.edit_message_text("â³ <b>Ø¬Ø§Ø±ÙŠ Ø¬Ù„Ø¨ Ø§Ù„Ø³Ø¬Ù„Ø§Øª...</b>", parse_mode=ParseMode.HTML)
        logs = await db.system_logs.find().sort("timestamp", -1).limit(15).to_list(length=15)
        if not logs: return await query.edit_message_text("ðŸ“­ Ù„Ø§ ØªÙˆØ¬Ø¯ Ø³Ø¬Ù„Ø§Øª.", reply_markup=admin_logs_back_btn(), parse_mode=ParseMode.HTML)
        rep = "ðŸ“ <b>Ø£Ø­Ø¯Ø« Ø§Ù„Ø¹Ù…Ù„ÙŠØ§Øª:</b>\n\n"
        for l in logs: rep += f"ðŸ‘¤ <b>{l['name']}</b> | â± {l['time']}\nðŸ”¹ {l['action']}\nâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€\n"
        btns = [[InlineKeyboardButton("ðŸ”„ ØªØ­Ø¯ÙŠØ«", callback_data="admin_get_logs")], [InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_logs_hub")]]
        return await query.edit_message_text(rep, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    uid = update.effective_user.id
    txt = update.message.text.strip()
    state = context.user_data.get("state")
    
    user = await get_user(uid)
    if not user: return
    role = user.get("role", "user")
    
    if not state: return await update.message.reply_text("ðŸ’¡ ÙŠØ±Ø¬Ù‰ Ø§Ø®ØªÙŠØ§Ø± Ø¹Ù…Ù„ÙŠØ© Ø£ÙˆÙ„Ø§Ù‹.", reply_markup=back_btn())

    if state == "waiting_add_tracked" and role == "admin":
        if not txt.isdigit(): return
        await db.settings.update_one({"_id": "cache_config"}, {"$addToSet": {"tracked_users": int(txt)}}, upsert=True)
        context.user_data.clear()
        return await update.message.reply_text(f"âœ… ØªÙ… Ø§Ù„Ø¥Ø¶Ø§ÙØ©.", reply_markup=retry_keyboard("add_tracked_user", "admin_auto_cache_menu"))

    elif state == "waiting_remove_tracked" and role == "admin":
        if not txt.isdigit(): return
        await db.settings.update_one({"_id": "cache_config"}, {"$pull": {"tracked_users": int(txt)}}, upsert=True)
        context.user_data.clear()
        return await update.message.reply_text(f"ðŸ—‘ ØªÙ… Ø§Ù„Ø¥Ø²Ø§Ù„Ø©.", reply_markup=retry_keyboard("remove_tracked_user", "admin_auto_cache_menu"))

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
                    res_msg = f"ðŸ“„ <b>Ø·Ù„Ø¨ Ø¨ÙˆØª <code>#{txt}</code></b>\nðŸ‘¤ Ø¨ÙˆØ§Ø³Ø·Ø©: <code>{order['user']}</code>\nâ¬‡ï¸ Ø§Ù„Ø¹Ù†Ø§ØµØ±:\n{items_str}"
                else:
                    res_msg = f"ðŸ›’ <b>Ø·Ù„Ø¨ Ù…ØªØ¬Ø± <code>#{txt}</code></b>\nðŸ‘¤ Ø¨ÙˆØ§Ø³Ø·Ø©: <code>{order['name']}</code>\nâ¬‡ï¸ Ø§Ù„ÙƒÙˆØ¯:\n<code>{order['code']}</code>"
                return await update.message.reply_text(res_msg, reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)
            
            if is_bot_order:
                target = await get_user(int(txt))
                if target:
                    msg = f"ðŸ‘¤ <b>Ø§Ù„Ø§Ø³Ù…:</b> {target.get('name')}\nðŸ†” <code>{target['_id']}</code>\nðŸŽ– <b>Ø§Ù„Ø±ØªØ¨Ø©:</b> {target['role']}"
                    return await update.message.reply_text(msg, reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)

        records = await db.codes_map.find({"$or": [{"_id": txt}, {"code": txt}]}).to_list(None)
        in_stock = await db.stock.count_documents({"$or": [{"_id": txt}, {"code": txt}]})
        
        if not records and in_stock == 0:
            await update.message.reply_text("âŒ <b>Ù„Ø§ ØªÙˆØ¬Ø¯ Ù†ØªØ§Ø¦Ø¬!</b>", reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)
        else:
            msg = f"ðŸ” <b>Ø§Ù„ÙƒÙˆØ¯:</b> <code>{txt}</code>\nðŸ“¦ Ø¨Ø§Ù„Ù…Ø®Ø²Ù† Ø­Ø§Ù„ÙŠØ§Ù‹: <code>{in_stock}</code>\n\n"
            if records:
                for i, r in enumerate(records, 1):
                    msg += f"--- Ø³Ø­Ø¨Ø© {i} ---\nðŸ‘¤ {r['name']} ({r.get('source', 'Bot')})\nðŸ“… {r['time']}\nðŸ“¦ Ø·Ù„Ø¨: <code>{r.get('order_id')}</code>\n\n"
            await update.message.reply_text(msg, reply_markup=retry_keyboard("admin_global_search", "admin_logs_hub"), parse_mode=ParseMode.HTML)
        context.user_data.clear()

    elif state == "waiting_order_id":
        order = await db.orders.find_one({"_id": int(txt) if txt.isdigit() else txt})
        if not order: order = await db.store_orders.find_one({"_id": txt})
        
        if order and (order.get("user_id") == uid or role == "admin"):
            if "items" in order:
                items_str = "\n".join([f"<code>{i}</code>" for i in order["items"]])
                res_msg = f"ðŸ“„ <b>Ø§Ù„Ø·Ù„Ø¨ <code>#{txt}</code></b>\nðŸ“… {order['date']}\nâ¬‡ï¸ Ø§Ù„Ø¹Ù†Ø§ØµØ±:\n{items_str}"
            else:
                res_msg = f"ðŸ›’ <b>Ø·Ù„Ø¨ Ù…ØªØ¬Ø± <code>#{txt}</code></b>\nðŸ“… {order['date']}\nâ¬‡ï¸ Ø§Ù„ÙƒÙˆØ¯:\n<code>{order['code']}</code>"
        else: res_msg = "âŒ Ø§Ù„Ø·Ù„Ø¨ ØºÙŠØ± Ù…ÙˆØ¬ÙˆØ¯."
        context.user_data.clear()
        return await update.message.reply_text(res_msg, reply_markup=retry_keyboard("check_order_id", "my_history"), parse_mode=ParseMode.HTML)

    elif state == "waiting_return_order_id":
        order = await db.orders.find_one({"_id": int(txt) if txt.isdigit() else txt})
        if not order: order = await db.store_orders.find_one({"_id": txt})
        
        if not order or (order.get("user_id") != uid and role != "admin"): 
            return await update.message.reply_text("âŒ Ø§Ù„Ø·Ù„Ø¨ ØºÙŠØ± Ù…ÙˆØ¬ÙˆØ¯.", reply_markup=back_btn())
            
        order_time = datetime.strptime(order['date'], "%Y-%m-%d %H:%M:%S" if "items" in order else "%Y-%m-%d %H:%M")
        if (datetime.now() - order_time).total_seconds() > 900 and role != "admin":
            return await update.message.reply_text("â³ <b>Ø§Ù†ØªÙ‡Øª Ù…Ù‡Ù„Ø© Ø§Ù„Ø¥Ø±Ø¬Ø§Ø¹ (15 Ø¯Ù‚ÙŠÙ‚Ø©).</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)
            
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
        return await update.message.reply_text(f"âœ… <b>ØªÙ… Ø¥Ø±Ø¬Ø§Ø¹ Ø§Ù„Ø·Ù„Ø¨ <code>#{txt}</code> Ø¨Ù†Ø¬Ø§Ø­!</b>", reply_markup=back_btn(), parse_mode=ParseMode.HTML)

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
            msg = f"âœ… ØªÙ… Ø¥Ø¶Ø§ÙØ© <code>{len(valid)}</code> ØªÙˆÙƒÙ†."
        else: msg = "âŒ Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙˆÙƒÙ†Ø§Øª ØµØ§Ù„Ø­Ø©."
        context.user_data.clear()
        return await update.message.reply_text(msg, reply_markup=retry_keyboard("add_tokens", "view_my_tokens"), parse_mode=ParseMode.HTML)

    elif state == "waiting_shared_tokens" and role == "admin":
        valid = [re.split(r'[;:\s\|]', l)[0].strip() for l in txt.splitlines() if len(re.split(r'[;:\s\|]', l)[0].strip()) > 15]
        if valid: 
            await db.settings.update_one({"_id": "shared_tokens"}, {"$push": {"tokens": {"$each": valid}}}, upsert=True)
            msg = f"âœ… ØªÙ… Ø¥Ø¶Ø§ÙØ© <code>{len(valid)}</code> ØªÙˆÙƒÙ† Ù…Ø´ØªØ±Ùƒ."
        else: msg = "âŒ Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙˆÙƒÙ†Ø§Øª ØµØ§Ù„Ø­Ø©."
        context.user_data.clear()
        return await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Ø±Ø¬ÙˆØ¹", callback_data="admin_shared_tokens_menu")]]), parse_mode=ParseMode.HTML)

    elif state == "waiting_add_user_id" and role == "admin":
        if not txt.isdigit(): return
        new_uid = int(txt)
        if await get_user(new_uid): return await update.message.reply_text("âš ï¸ Ù…ÙˆØ¬ÙˆØ¯ Ø¨Ø§Ù„ÙØ¹Ù„!", reply_markup=retry_keyboard("admin_add_user_btn", "admin_users_menu"))
        context.user_data["new_user_id"] = new_uid
        btns = [[InlineKeyboardButton("Ù…ÙˆØ¸Ù ðŸ‘¤", callback_data="set_role_employee")], [InlineKeyboardButton("Ù…Ø³ØªØ®Ø¯Ù… Ø¹Ø§Ø¯ÙŠ ðŸ†•", callback_data="set_role_user")]]
        return await update.message.reply_text(f"ðŸ‘¤ <b>Ø§Ø®ØªØ± Ø§Ù„Ø±ØªØ¨Ø©:</b> <code>{new_uid}</code>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

    elif state == "waiting_remove_user_id" and role == "admin":
        if txt.isdigit():
            await db.users.delete_one({"_id": int(txt)})
            context.user_data.clear()
            return await update.message.reply_text(f"ðŸ—‘ ØªÙ… Ø§Ù„Ø­Ø°Ù.", reply_markup=retry_keyboard("admin_remove_user_btn", "admin_users_menu"))

    elif state == "waiting_manage_user_id" and role == "admin":
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target:
            btns = [[InlineKeyboardButton("ðŸ—‘ ØªØµÙÙŠØ± ØªÙˆÙƒÙ†Ø§Øª", callback_data=f"manage_clear_tokens_{target['_id']}"), InlineKeyboardButton("ðŸ”„ ØªØºÙŠÙŠØ± Ø±ØªØ¨Ø©", callback_data=f"manage_switch_role_{target['_id']}")]]
            await update.message.reply_text(f"ðŸ‘¤ <b>{target.get('name')}</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
        context.user_data.clear()

    elif state == "waiting_user_logs_id" and role == "admin":
        if not txt.isdigit(): return
        target = await get_user(int(txt))
        if target and target.get("logs"):
            await update.message.reply_text(f"ðŸ“œ <b>Ø³Ø¬Ù„Ø§Øª:</b>\n\n" + "\n\n".join(target["logs"][-15:]), reply_markup=retry_keyboard("admin_get_user_logs_btn", "admin_users_menu"), parse_mode=ParseMode.HTML)
        context.user_data.clear()

    elif state == "adding_stock_manual" and role == "admin":
        lines = [c.strip() for c in txt.splitlines() if c.strip()]
        cat = context.user_data.get("target_cat")
        if cat and lines:
            waiting_msg = await update.message.reply_text("â³ <b>Ø¬Ø§Ø±ÙŠ Ø§Ù„ÙØ­Øµ...</b>", parse_mode=ParseMode.HTML)
            new_codes, dupes, all_codes = await analyze_codes(lines)
            context.user_data["pending_stock"] = {"all": all_codes, "new": new_codes, "dupes": dupes, "cat": cat} 
            btns = [[InlineKeyboardButton("âœ… Ø¥Ø¶Ø§ÙØ© Ø§Ù„ÙƒÙ„", callback_data="confirm_add_all")], [InlineKeyboardButton("âœ¨ Ø¥Ø¶Ø§ÙØ© Ø§Ù„Ø¬Ø¯ÙŠØ¯", callback_data="confirm_add_new")]]
            return await waiting_msg.edit_text(f"ðŸ“Š <b>Ø§Ù„ØªÙ‚Ø±ÙŠØ±:</b>\nØ¥Ø¬Ù…Ø§Ù„ÙŠ: {len(all_codes)} | Ø¬Ø¯ÙŠØ¯: {len(new_codes)}", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user or user["role"] not in ["admin", "employee"]: return
    
    doc = update.message.document
    if not doc.file_name.endswith(".txt"): return
    
    waiting_msg = await update.message.reply_text("â³ <b>Ø¬Ø§Ø±ÙŠ Ø§Ù„Ù‚Ø±Ø§Ø¡Ø©...</b>", parse_mode=ParseMode.HTML)
    file = await doc.get_file()
    content = await file.download_as_bytearray()
    lines = [c.strip() for c in content.decode("utf-8", errors="ignore").splitlines() if c.strip()]
    if not lines: return await waiting_msg.edit_text("âŒ Ø§Ù„Ù…Ù„Ù ÙØ§Ø±Øº!")
    
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
        btns.append([InlineKeyboardButton("ðŸ”‘ Ø§Ø³ØªØ®Ø±Ø§Ø¬ ØªÙˆÙƒÙ†Ø§Øª (Ù…Ø´ØªØ±ÙƒØ©)", callback_data="file_shared_tokens")])
        
    btns.append([InlineKeyboardButton("ðŸ” Ø§Ø³ØªØ®Ø±Ø§Ø¬ ØªÙˆÙƒÙ†Ø§Øª (Ø´Ø®ØµÙŠØ©)", callback_data="file_personal_tokens")])
    btns.append([InlineKeyboardButton("âŒ Ø¥Ù„ØºØ§Ø¡", callback_data="cancel_add_stock")])
    
    await waiting_msg.edit_text(f"ðŸ“‚ <b>Ù…Ù„Ù (<code>{len(lines)}</code> Ø³Ø·Ø±)</b>\nðŸŽ¯ <b>Ù…Ø§Ø°Ø§ ØªØ±ÙŠØ¯ Ø£Ù† ØªÙØ¹Ù„ØŸ</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)



