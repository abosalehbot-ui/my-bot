from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import UC_CATEGORIES

def get_main_keyboard(role):
    # تم إزالة زر المرتجعات من هنا
    btns = [[InlineKeyboardButton("💳 حسابي", callback_data="my_profile")], [InlineKeyboardButton("📜 سجل عملياتي", callback_data="my_history")]]
    if role in ["admin", "employee"]:
        btns.insert(0, [InlineKeyboardButton("🚀 سحب حسابات API", callback_data="pull_api"), InlineKeyboardButton("🎮 سحب أكواد UC", callback_data="pull_stock_menu")])
    if role == "admin":
        btns.append([InlineKeyboardButton("🛠 لوحة التحكم (الأدمن)", callback_data="admin_panel")])
        btns.append([InlineKeyboardButton("♻️ سحب من التخزين (24س)", callback_data="pull_cached_api")])
    return InlineKeyboardMarkup(btns)

async def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 إدارة المخزن", callback_data="admin_stock_menu"), InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton("🔗 التوكنات المشتركة", callback_data="admin_shared_tokens_menu")],
        [InlineKeyboardButton("📜 مركز السجلات والبحث", callback_data="admin_logs_hub")],
        [InlineKeyboardButton("♻️ التخزين التلقائي (Auto Cache)", callback_data="admin_auto_cache_menu")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
    ])

def shared_tokens_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁️ عرض التوكنات", callback_data="view_shared_tokens")],
        [InlineKeyboardButton("➕ إضافة توكنات (ذكية)", callback_data="add_shared_tokens_btn")],
        [InlineKeyboardButton("🗑 تصفير التوكنات", callback_data="clear_shared_tokens")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
    ])

def admin_logs_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 البحث الشامل", callback_data="admin_global_search")],
        [InlineKeyboardButton("📝 استخراج السجلات (Logs)", callback_data="admin_get_logs")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ])

def auto_cache_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 قائمة المراقبة", callback_data="list_tracked_users")],
        [InlineKeyboardButton("➕ إضافة آيدي", callback_data="add_tracked_user"), InlineKeyboardButton("🗑 إزالة آيدي", callback_data="remove_tracked_user")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ])

def admin_users_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة مستخدم", callback_data="admin_add_user_btn"), InlineKeyboardButton("🗑 حذف مستخدم", callback_data="admin_remove_user_btn")],
        [InlineKeyboardButton("⚙️ تحكم بمستخدم", callback_data="admin_search_manage_user")],
        [InlineKeyboardButton("📜 استخراج سجلات", callback_data="admin_get_user_logs_btn")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ])

def stock_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة يدوي", callback_data="admin_choose_cat_manual"), InlineKeyboardButton("📂 رفع ذكي", callback_data="admin_choose_cat_file")],
        [InlineKeyboardButton("🗑 تصفير فئة", callback_data="admin_choose_cat_clear")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ])

async def categories_keyboard(prefix, db):
    btns, row = [], []
    for cat in UC_CATEGORIES:
        c = await db.stock.count_documents({"category": cat})
        row.append(InlineKeyboardButton(f"{cat} UC ({c})", callback_data=f"{prefix}_{cat}"))
        if len(row) == 3:
            btns.append(row)
            row = []
    if row: btns.append(row)
    btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_stock_menu" if "admin" in prefix else "back_home")])
    return InlineKeyboardMarkup(btns)

def profile_keyboard(role):
    btns = [[InlineKeyboardButton("🔑 توكناتي الشخصية", callback_data="view_my_tokens")]]
    btns.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")])
    return InlineKeyboardMarkup(btns)

def success_pull_keyboard(again_data):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 سحب مرة أخرى", callback_data=again_data)],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
    ])

def retry_keyboard(retry_data, back_data):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 محاولة أخرى", callback_data=retry_data)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=back_data)]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]])
def admin_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_stock_menu")]])
def admin_users_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_users_menu")]])
def admin_logs_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_logs_hub")]])
