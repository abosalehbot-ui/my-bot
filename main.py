from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import BOT_TOKEN, WEBHOOK_URL, PORT, logger
from handlers import start, cmd_help, cmd_pull, cmd_api, cmd_cache, button_handler, message_handler, document_handler, error_handler

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("pull", cmd_pull))
    app.add_handler(CommandHandler("api", cmd_api))
    app.add_handler(CommandHandler("cache", cmd_cache))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    
    app.add_error_handler(error_handler)
    
    if WEBHOOK_URL:
        logger.info(f"🚀 Bot Started with Webhook on {WEBHOOK_URL}")
        app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=WEBHOOK_URL)
    else:
        logger.info("🚀 Bot Started with Polling")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
