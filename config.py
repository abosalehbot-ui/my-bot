import os
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO, handlers=[logging.StreamHandler()])
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("SalehZonBot")

BOT_TOKEN = os.environ.get("BOT_TOKEN") 
ADMIN_ID = 1635871816
API_BASE_URL = "https://buzzmaster.shop" 
PRODUCT_ID = "24h-nongmail"

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") 
PORT = int(os.environ.get("PORT", 8080))

# Admin auth — مكان واحد للتوكن السري
SECRET_TOKEN = os.environ.get("SECRET_TOKEN", "salehzon_secure_2026")

UC_CATEGORIES = {
    "60_UC": "ID_60",      # يمكنك تغيير الأسماء والقيم حسب حاجتك
    "325_UC": "ID_325",
    "660_UC": "ID_660",
    "1800_UC": "ID_1800"
}
