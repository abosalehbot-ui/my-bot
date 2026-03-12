from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, ADMIN_ID

db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["salehzon_db"]

async def get_user(user_id): 
    return await db.users.find_one({"_id": user_id})

async def log_important_action(user_id, user_name, action, details=""):
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    log_entry = f"[{time_str}] {action}"
    if details: log_entry += f"\n└ <code>{details}</code>"
    
    await db.users.update_one({"_id": user_id}, {"$push": {"logs": {"$each": [log_entry], "$slice": -50}}})
    await db.system_logs.insert_one({
        "user_id": user_id, "name": user_name, "action": action,
        "details": details, "time": time_str, "timestamp": datetime.now()
    })

# العداد الموحد للموقع والبوت
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

# دالة قراءة الفئات الديناميكية للبوت
async def get_dynamic_categories():
    cats = await db.store_categories.find().to_list(None)
    stock_keys = []
    for c in cats:
        for p in c.get("products", []):
            stock_keys.append(p["stock_key"])
    return stock_keys if stock_keys else ["60", "325", "660", "1800", "3850", "8100"]

async def analyze_codes(codes):
    unique_input, dupes_in_input, seen = [], [], set()
    for c in codes:
        if c in seen: dupes_in_input.append(c)
        else:
            seen.add(c)
            unique_input.append(c)
            
    in_stock = await db.stock.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    in_map = await db.codes_map.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    
    existing_in_db = set(str(d.get("code") or d.get("_id")) for d in in_stock + in_map)
    new_codes = [c for c in unique_input if c not in existing_in_db]
    db_dupes = [c for c in unique_input if c in existing_in_db]
    all_dupes = list(set(dupes_in_input + db_dupes))
    
    return new_codes, all_dupes, codes
