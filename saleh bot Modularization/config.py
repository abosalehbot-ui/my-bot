import os
import logging

# ====== 📝 إعداد اللوجز ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO, 
    handlers=[logging.StreamHandler()]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("SalehZonBot")

# ====== ⚙️ الإعدادات ======
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"
UC_CATEGORIES = ["60", "325", "660", "1800", "3850", "8100"]

WEBHOOK_URL = os.environ.get("WEBHOOK_URL") 
PORT = int(os.environ.get("PORT", 8080))