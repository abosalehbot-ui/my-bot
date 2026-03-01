from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import BOT_TOKEN, WEBHOOK_URL, PORT, logger
from handlers import start, button_handler, message_handler, document_handler, error_handler

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # ربط جميع الدوال بالبوت
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    
    app.add_error_handler(error_handler)
    
    # تشغيل البوت
    if WEBHOOK_URL:
        logger.info(f"🚀 Bot Started with Webhook on {WEBHOOK_URL}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL
        )
    else:
        logger.info("🚀 Bot Started with Polling (Local Mode)")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()