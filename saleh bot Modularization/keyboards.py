from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import UC_CATEGORIES
from database import db

def get_main_keyboard(role):
    buttons = []
    if role in ["employee", "admin"]:
        buttons.append([
            InlineKeyboardButton("🎮 سحب كود (UC)", callback_data="pull_stock_menu"),
            InlineKeyboardButton("↩️ إرجاع طلب (15د)", callback_data="return_order")
        ])
    buttons.append([InlineKeyboardButton("🚀 سحب حسابات (API)", callback_data="pull_api")])
    buttons.append([InlineKeyboardButton("📋 توكناتي", callback_data="view_my_tokens")])
    buttons.append([
        InlineKeyboardButton("💳 حسابي وإحصائياتي", callback_data="my_profile"), 
        InlineKeyboardButton("📂 أرشيفي", callback_data="my_history")
    ])
    if role == "admin": 
        buttons.append([InlineKeyboardButton("♻️ سحب من المخزن (24س)", callback_data="pull_cached_api")])
        buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

async def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إدارة الموظفين والمستخدمين", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📦 إدارة المخزن", callback_data="admin_stock_menu")],
        [InlineKeyboardButton("♻️ إعدادات التخزين التلقائي", callback_data="admin_auto_cache_menu")], 
        [InlineKeyboardButton("🔍 بحث عكسي (كود)", callback_data="admin_reverse_search"), InlineKeyboardButton("📄 بحث بطلب عام", callback_data="admin_search_order")],
        [InlineKeyboardButton("📝 سجلات النظام", callback_data="admin_get_logs"), InlineKeyboardButton("🛠 الصيانة", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("🏠 خروج", callback_data="back_home")]
    ])

def auto_cache_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة آيدي للمراقبة", callback_data="add_tracked_user"), InlineKeyboardButton("🗑 إزالة آيدي", callback_data="remove_tracked_user")],
        [InlineKeyboardButton("📋 عرض القائمة", callback_data="list_tracked_users")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
    ])

def admin_users_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 بحث وتحكم فردي بالآيدي", callback_data="admin_search_manage_user")],
        [InlineKeyboardButton("➕ إضافة مستخدم", callback_data="admin_add_user_btn"), InlineKeyboardButton("🗑 حذف مستخدم", callback_data="admin_remove_user_btn")],
        [InlineKeyboardButton("📜 سجلات مستخدم", callback_data="admin_get_user_logs_btn"), InlineKeyboardButton("📋 عرض القائمة", callback_data="admin_list_users_btn")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
    ])

def stock_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 رفع ملف (.txt)", callback_data="admin_choose_cat_file"), InlineKeyboardButton("✍️ إضافة يدوي", callback_data="admin_choose_cat_manual")],
        [InlineKeyboardButton("🗑 تصفير فئة محددة", callback_data="admin_choose_cat_clear")],
        [InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]
    ])

async def categories_keyboard(action_prefix):
    buttons = []
    row = []
    for cat in UC_CATEGORIES:
        count = await db.stock.count_documents({"category": cat})
        icon = "🔴" if count == 0 else ("🟡" if count < 5 else "🟢")
        row.append(InlineKeyboardButton(f"{icon} {cat} ({count})", callback_data=f"{action_prefix}_{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    back_cb = "admin_stock_menu" if "admin" in action_prefix else "back_home"
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=back_cb)])
    return InlineKeyboardMarkup(buttons)

def success_pull_keyboard(callback_data):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 طلب آخر", callback_data=callback_data)],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
    ])

def back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]])
def admin_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للأدمن", callback_data="admin_panel")]])
def admin_users_back_btn(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للمستخدمين", callback_data="admin_users_menu")]])