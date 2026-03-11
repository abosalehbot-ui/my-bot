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
    if details:
        log_entry += f"\n+ <code>{details}</code>"

    await db.users.update_one({"_id": user_id}, {"$push": {"logs": {"$each": [log_entry], "$slice": -50}}})
    await db.system_logs.insert_one({
        "user_id": user_id,
        "name": user_name,
        "action": action,
        "details": details,
        "time": time_str,
        "timestamp": datetime.now(),
    })


async def get_next_order_id():
    stat = await db.stats.find_one_and_update(
        {"_id": "global_stats"},
        {"$inc": {"last_order_id": 1}},
        upsert=True,
        return_document=True,
    )
    return stat["last_order_id"]


async def check_maintenance():
    settings = await db.settings.find_one({"_id": "config"})
    if not settings:
        await db.settings.insert_one({"_id": "config", "maintenance": False})
        return False
    return settings.get("maintenance", False)


async def get_tracked_users():
    cfg = await db.settings.find_one({"_id": "cache_config"})
    if not cfg:
        return [ADMIN_ID]
    tracked = cfg.get("tracked_users", [])
    if ADMIN_ID not in tracked:
        tracked.append(ADMIN_ID)
    return tracked


def normalize_catalog_product_channels(product):
    raw = dict(product or {})
    raw["stock_key"] = str(raw.get("stock_key") or "").strip()

    def parse_flag(value, default=True):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        lowered = str(value).strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return default

    def parse_allocation(value):
        if value in (None, ""):
            return None
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            return None
        return max(parsed, 0)

    raw["is_visible_web"] = parse_flag(raw.get("is_visible_web"), True)
    raw["is_visible_bot"] = parse_flag(raw.get("is_visible_bot"), True)
    raw["allocation_web"] = parse_allocation(raw.get("allocation_web"))
    raw["allocation_bot"] = parse_allocation(raw.get("allocation_bot"))
    return raw


async def get_bot_product_state(stock_key):
    stock_key = str(stock_key or "").strip()
    if not stock_key:
        return None

    category = await db.store_categories.find_one({"products.stock_key": stock_key}, {"products.$": 1})
    if not category or not category.get("products"):
        return None

    product = normalize_catalog_product_channels(category["products"][0])
    order_type = f"Bot Stock ({stock_key})"
    orders = await db.orders.find({"type": order_type}, {"items": 1}).to_list(None)
    sold_count = sum(len(order.get("items") or []) for order in orders)
    allocation = product.get("allocation_bot")
    remaining = None if allocation is None else max(int(allocation) - int(sold_count or 0), 0)
    return {
        "stock_key": stock_key,
        "is_visible_bot": bool(product.get("is_visible_bot", True)),
        "allocation_bot": allocation,
        "sold_count": int(sold_count),
        "remaining_bot": remaining,
    }


async def get_dynamic_categories():
    cats = await db.store_categories.find().to_list(None)
    if not cats:
        return ["60", "325", "660", "1800", "3850", "8100"]

    stock_keys = []
    order_types = []
    for category in cats:
        for product in category.get("products", []):
            normalized = normalize_catalog_product_channels(product)
            stock_key = normalized.get("stock_key")
            if not stock_key:
                continue
            stock_keys.append(stock_key)
            order_types.append(f"Bot Stock ({stock_key})")

    stock_counts = {}
    unique_stock_keys = list(dict.fromkeys(stock_keys))
    if unique_stock_keys:
        pipeline = [
            {"$match": {"category": {"$in": unique_stock_keys}}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        ]
        async for row in db.stock.aggregate(pipeline):
            stock_counts[str(row.get("_id") or "")] = int(row.get("count") or 0)

    bot_sales = {}
    if order_types:
        unique_order_types = list(dict.fromkeys(order_types))
        type_map = {
            order_type: order_type.replace("Bot Stock (", "").rstrip(")")
            for order_type in unique_order_types
        }
        orders = await db.orders.find({"type": {"$in": unique_order_types}}, {"type": 1, "items": 1}).to_list(None)
        for order in orders:
            mapped_key = type_map.get(str(order.get("type") or ""))
            if not mapped_key:
                continue
            bot_sales[mapped_key] = bot_sales.get(mapped_key, 0) + len(order.get("items") or [])

    visible = []
    for category in cats:
        for product in category.get("products", []):
            normalized = normalize_catalog_product_channels(product)
            stock_key = normalized.get("stock_key")
            if not stock_key or not normalized.get("is_visible_bot", True):
                continue
            if int(stock_counts.get(stock_key, 0) or 0) <= 0:
                continue
            allocation = normalized.get("allocation_bot")
            sold_count = int(bot_sales.get(stock_key, 0) or 0)
            if allocation is not None and sold_count >= int(allocation):
                continue
            visible.append(stock_key)

    return list(dict.fromkeys(visible))


async def analyze_codes(codes):
    unique_input, dupes_in_input, seen = [], [], set()
    for code in codes:
        if code in seen:
            dupes_in_input.append(code)
        else:
            seen.add(code)
            unique_input.append(code)

    in_stock = await db.stock.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)
    in_map = await db.codes_map.find({"$or": [{"_id": {"$in": unique_input}}, {"code": {"$in": unique_input}}]}).to_list(None)

    existing_in_db = set(str(doc.get("code") or doc.get("_id")) for doc in in_stock + in_map)
    new_codes = [code for code in unique_input if code not in existing_in_db]
    db_dupes = [code for code in unique_input if code in existing_in_db]
    all_dupes = list(set(dupes_in_input + db_dupes))

    return new_codes, all_dupes, codes

