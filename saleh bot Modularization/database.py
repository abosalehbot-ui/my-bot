import os
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from config import ADMIN_ID

# ====== 🗄️ إعدادات MongoDB ======
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abosalehlt_db_user:7_RvkParzvUeC_v@abosaleh.yhuwfdt.mongodb.net/?appName=abosaleh")
db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["salehzon_db"]

# ====== 💾 دوال مساعدة ======
async def get_user(user_id): 
    return await db.users.find_one({"_id": user_id})

async def log_activity(user_id, user_name, action):
    log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {action}"
    await db.users.update_one({"_id": user_id}, {"$push": {"logs": {"$each": [log_entry], "$slice": -500}}})

async def get_next_order_id():
    stat = await db.stats.find_one_and_update({"_id": "global_stats"}, {"$inc": {"last_order_id": 1}}, upsert=True, return_document=True)
    return stat["last_order_id"]

async def check_maintenance():
    settings = await db.settings.find_one({"_id": "config"})
    if not settings:
        await db.settings.insert_one({"_id": "config", "maintenance": False})
        return False
    return settings.get("maintenance", False)

async def get_tracked_users():
    cfg = await db.settings.find_one({"_id": "cache_config"})
    if not cfg: return [ADMIN_ID]
    tracked = cfg.get("tracked_users", [])
    if ADMIN_ID not in tracked: tracked.append(ADMIN_ID)
    return tracked

async def analyze_codes(codes):
    unique_input = []
    dupes_in_input = []
    seen = set()
    
    for c in codes:
        if c in seen: dupes_in_input.append(c)
        else:
            seen.add(c)
            unique_input.append(c)
            
    in_stock = await db.stock.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    in_map = await db.codes_map.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    
    existing_in_db = set()
    for d in in_stock + in_map:
        val = d.get("code") or d.get("_id")
        if val: existing_in_db.add(str(val))
        
    new_codes = [c for c in unique_input if c not in existing_in_db]
    db_dupes = [c for c in unique_input if c in existing_in_db]
    all_dupes = list(set(dupes_in_input + db_dupes))
    
    return new_codes, all_dupes, codes