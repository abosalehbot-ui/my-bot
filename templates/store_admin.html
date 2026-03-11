<!DOCTYPE html>
<html lang="en" data-theme="default">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Saleh Zone | Store Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <script>
        tailwind.config = { theme: { extend: { colors: {
            szgreen:'var(--theme-primary)', szcyan:'var(--theme-secondary)', darkbg:'#050505', panelbg:'#111'
        }}}}
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
        :root{--theme-primary:#7dfc89;--theme-secondary:#5eead4}
        html[data-theme="synthwave"]{--theme-primary:#a855f7;--theme-secondary:#f97316}
        html[data-theme="sith"]{--theme-primary:#ef4444;--theme-secondary:#dc2626}
        html[data-theme="vip"]{--theme-primary:#eab308;--theme-secondary:#facc15}
        body{font-family:'Cairo',sans-serif;background:#050505;color:#d1d5db}
        ::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:#333;border-radius:10px}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        .fade-in{animation:fadeIn .3s ease-out forwards}
        @keyframes fadeOut{to{opacity:0;transform:translateY(-8px)}}
        #toast-container .toast{display:flex;align-items:center;gap:10px;background:#111;border-radius:10px;padding:10px 16px;color:#fff;font-weight:700;font-size:13px;min-width:200px;box-shadow:0 4px 20px rgba(0,0,0,.6)}
        .tab-btn{color:#6b7280;border-bottom:2px solid transparent;transition:.2s}
        .tab-btn.active{color:var(--theme-primary);border-bottom-color:var(--theme-primary)}
        .badge-egp{background:#78350f22;color:#eab308;border:1px solid #78350f44}
        .badge-usd{background:#0e4a4422;color:#5eead4;border:1px solid #0e4a4444}
        .detail-modal-tab{display:none}
        .detail-modal-tab.show{display:block}
        .ticket-filter-btn.active{background:rgba(125,252,137,0.1);color:var(--theme-primary);border-color:rgba(125,252,137,0.2)}
    </style>
</head>
<body class="min-h-screen">
<div id="toast-container" class="fixed top-4 right-4 z-[200] flex flex-col gap-2 pointer-events-none"></div>

<header class="bg-panelbg border-b border-gray-800 px-6 py-4 flex items-center justify-between sticky top-0 z-30">
    <div class="flex items-center gap-3">
        <a href="/admin" class="text-gray-500 hover:text-white transition text-sm"><i class="fas fa-arrow-left mr-1"></i>Dashboard</a>
        <span class="text-gray-700">|</span>
        <span class="font-black text-white">Store <span class="text-szgreen">Admin</span></span>
    </div>
    <div class="flex items-center gap-3 text-xs font-bold">
        <span class="bg-szgreen/10 text-szgreen border border-szgreen/20 px-3 py-1 rounded-full">
            <i class="fas fa-users mr-1"></i>{{ store_customers|length }} Customers
        </span>
        <span class="bg-szcyan/10 text-szcyan border border-szcyan/20 px-3 py-1 rounded-full">
            <i class="fas fa-receipt mr-1"></i>{{ store_orders|length }} Orders
        </span>
        {% if open_tickets %}
        <span class="bg-red-500/10 text-red-400 border border-red-500/20 px-3 py-1 rounded-full">
            <i class="fas fa-headset mr-1"></i>{{ open_tickets|length }} Open Tickets
        </span>
        {% endif %}
        <a href="/logout" class="text-red-500 hover:text-red-400 ml-1"><i class="fas fa-power-off"></i></a>
    </div>
</header>

{% set total_egp = namespace(v=0) %}{% set total_usd = namespace(v=0) %}
{% set today = namespace(egp=0, usd=0, sales=0) %}
{% for o in store_orders %}
  {% if o.currency == 'EGP' %}{% set total_egp.v = total_egp.v + o.price %}{% endif %}
  {% if o.currency == 'USD' %}{% set total_usd.v = total_usd.v + o.price %}{% endif %}
{% endfor %}
<div class="grid grid-cols-2 md:grid-cols-4 gap-4 p-6 max-w-7xl mx-auto">
    <div class="bg-panelbg border border-gray-800 rounded-xl p-4">
        <div class="text-xs text-gray-500 uppercase mb-1">Customers</div>
        <div class="text-2xl font-black text-white">{{ store_customers|length }}</div>
    </div>
    <div class="bg-panelbg border border-gray-800 rounded-xl p-4">
        <div class="text-xs text-gray-500 uppercase mb-1">Total Orders</div>
        <div class="text-2xl font-black text-white">{{ store_orders|length }}</div>
    </div>
    <div class="bg-panelbg border border-yellow-500/20 rounded-xl p-4">
        <div class="text-xs text-gray-500 uppercase mb-1">Revenue EGP</div>
        <div class="text-2xl font-black text-yellow-500">{{ "%.0f"|format(total_egp.v) }}</div>
    </div>
    <div class="bg-panelbg border border-szcyan/20 rounded-xl p-4">
        <div class="text-xs text-gray-500 uppercase mb-1">Revenue USD</div>
        <div class="text-2xl font-black text-szcyan">{{ "%.2f"|format(total_usd.v) }}</div>
    </div>
</div>

<div class="max-w-7xl mx-auto px-6">
    <div class="flex gap-5 border-b border-gray-800 mb-6">
        <button onclick='switchMainTab("customers")' id="main-tab-btn-customers" class="tab-btn active pb-3 font-bold text-sm">
            <i class="fas fa-users mr-1"></i>Customers
        </button>
        <button onclick='switchMainTab("orders")' id="main-tab-btn-orders" class="tab-btn pb-3 font-bold text-sm">
            <i class="fas fa-receipt mr-1"></i>Orders
        </button>
        <button onclick='switchMainTab("inventory")' id="main-tab-btn-inventory" class="tab-btn pb-3 font-bold text-sm">
            <i class="fas fa-boxes-stacked mr-1"></i>Inventory
        </button>
        <button onclick='switchMainTab("support")' id="main-tab-btn-support" class="tab-btn pb-3 font-bold text-sm relative">
            <i class="fas fa-headset mr-1"></i>Support
            {% if open_tickets %}
            <span class="absolute -top-1 -right-3 bg-red-500 text-white text-[9px] font-black px-1.5 py-0.5 rounded-full">{{ open_tickets|length }}</span>
            {% endif %}
        </button>
    </div>

    <!-- â”€â”€ Customers Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
    <div id="main-tab-customers">
        <div class="flex items-center gap-3 mb-4">
            <div class="relative flex-1 max-w-sm">
                <i class="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm"></i>
                <input id="search-customers" oninput="filterRows('search-customers','customer-row')" placeholder="Search name / email / username..."
                    class="w-full bg-panelbg border border-gray-700 rounded-lg pl-9 pr-4 py-2 text-sm text-gray-200 outline-none focus:border-szgreen">
            </div>
        </div>
        <div class="overflow-x-auto border border-gray-800 rounded-xl bg-panelbg">
            <table class="w-full text-sm text-left">
                <thead class="bg-black text-gray-500 uppercase text-[10px]">
                    <tr>
                        <th class="px-4 py-3">Avatar</th>
                        <th class="px-4 py-3">Name / Username</th>
                        <th class="px-4 py-3">Email</th>
                        <th class="px-4 py-3">Status</th>
                        <th class="px-4 py-3">EGP</th>
                        <th class="px-4 py-3">USD</th>
                        <th class="px-4 py-3">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-800">
                    {% for c in store_customers %}
                    <tr class="hover:bg-black/30 transition customer-row" data-search="{{ c.name|lower }} {{ c.email|lower }} {{ c.get('username','')|lower }}">
                        <td class="px-4 py-3">
                            {% if c.avatar %}
                            <img src="{{ c.avatar }}" class="w-9 h-9 rounded-full object-cover border border-gray-700">
                            {% else %}
                            <div class="w-9 h-9 rounded-full bg-gray-900 border border-gray-700 flex items-center justify-center text-gray-500"><i class="fas fa-user text-xs"></i></div>
                            {% endif %}
                        </td>
                        <td class="px-4 py-3">
                            <div class="font-bold text-white">{{ c.name }}</div>
                            <div class="text-xs text-gray-500">{% if c.get('username') %}@{{ c.username }}{% else %}<span class="text-red-500/70 italic">no username</span>{% endif %}</div>
                        </td>
                        <td class="px-4 py-3 font-mono text-xs text-szcyan">{{ c.email }}</td>
                        <td class="px-4 py-3">
                            {% if c.get('is_banned', false) %}
                            <span class="text-[10px] bg-red-900/40 text-red-400 px-2 py-1 rounded font-bold">Banned</span>
                            {% else %}
                            <span class="text-[10px] bg-szgreen/20 text-szgreen px-2 py-1 rounded font-bold">Active</span>
                            {% endif %}
                        </td>
                        <td class="px-4 py-3"><span class="badge-egp px-2 py-1 rounded text-xs font-black">{{ c.balance_egp or 0 }}</span></td>
                        <td class="px-4 py-3"><span class="badge-usd px-2 py-1 rounded text-xs font-black">{{ c.balance_usd or 0 }}</span></td>
                        <td class="px-4 py-3">
                            <button onclick='openCustomerModal({{ c | tojson | forceescape }})'
                                class="bg-szgreen/10 text-szgreen border border-szgreen/20 px-3 py-1 rounded text-xs font-bold hover:bg-szgreen hover:text-black transition">
                                <i class="fas fa-pen mr-1"></i>Manage
                            </button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <!-- â”€â”€ Orders Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
    <div id="main-tab-orders" style="display:none">
        <div class="flex items-center gap-3 mb-4">
            <div class="relative flex-1 max-w-sm">
                <i class="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm"></i>
                <input id="search-orders" oninput="filterRows('search-orders','order-row')" placeholder="Search email / order ID..."
                    class="w-full bg-panelbg border border-gray-700 rounded-lg pl-9 pr-4 py-2 text-sm text-gray-200 outline-none focus:border-szgreen">
            </div>
        </div>

        <div class="mb-4 bg-panelbg border border-gray-800 rounded-xl p-4">
            <h3 class="text-sm font-black text-white mb-2"><i class="fas fa-undo-alt text-red-400 mr-2"></i>Bulk Returns</h3>
            <p class="text-xs text-gray-500 mb-2">Paste one order ID per line (e.g. 12345S).</p>
            <textarea id="bulk-return-ids" rows="4" class="w-full bg-black border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 outline-none focus:border-szgreen resize-y" placeholder="12345S&#10;12346S"></textarea>
            <div class="mt-3 flex items-center gap-2">
                <button onclick='confirmBulkReturns()' class="bg-red-900/20 text-red-400 border border-red-900/30 px-4 py-2 rounded-lg text-sm font-bold hover:bg-red-900/40 transition"><i class="fas fa-play mr-1"></i>Process Bulk Returns</button>
                <span id="bulk-return-status" class="text-xs font-bold text-gray-500"></span>
            </div>
        </div>
        <div class="overflow-x-auto border border-gray-800 rounded-xl bg-panelbg">
            <table class="w-full text-sm text-left whitespace-nowrap">
                <thead class="bg-black text-gray-500 uppercase text-[10px]">
                    <tr>
                        <th class="px-4 py-3">Order</th>
                        <th class="px-4 py-3">Customer</th>
                        <th class="px-4 py-3">Email</th>
                        <th class="px-4 py-3">Package</th>
                        <th class="px-4 py-3">Price</th>
                        <th class="px-4 py-3">Date</th>
                        <th class="px-4 py-3">Code</th>
                        <th class="px-4 py-3">Return</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-800">
                    {% for o in store_orders %}
                    <tr class="hover:bg-black/30 transition order-row" data-search="{{ o.email|lower }} {{ o._id|lower }}">
                        <td class="px-4 py-3 font-mono text-szcyan font-bold">#{{ o._id }}</td>
                        <td class="px-4 py-3 font-bold text-white">{{ o.name }}</td>
                        <td class="px-4 py-3 text-xs text-gray-400 font-mono">{{ o.email }}</td>
                        <td class="px-4 py-3 text-gray-300">{{ o.category }}</td>
                        <td class="px-4 py-3">
                            {% if o.currency == 'EGP' %}<span class="badge-egp px-2 py-1 rounded text-xs font-black">{{ o.price }} EGP</span>
                            {% else %}<span class="badge-usd px-2 py-1 rounded text-xs font-black">{{ o.price }} USD</span>{% endif %}
                        </td>
                        <td class="px-4 py-3 text-xs text-gray-500">{{ o.date }}</td>
                        <td class="px-4 py-3">
                            <button onclick='copyText({{ o.code | tojson | forceescape }})'
                                class="bg-gray-900 text-szgreen border border-gray-700 px-3 py-1 rounded text-xs font-mono hover:bg-szgreen hover:text-black transition">
                                <i class="fas fa-copy mr-1"></i>Copy
                            </button>
                        </td>
                        <td class="px-4 py-3">
                            <button onclick='returnOrder({{ o._id | tojson | forceescape }})'
                                class="bg-red-900/20 text-red-400 border border-red-900/30 px-3 py-1 rounded text-xs font-bold hover:bg-red-900/40 transition">
                                <i class="fas fa-undo mr-1"></i>Return
                            </button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <!-- â”€â”€ Support Tickets Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
    <div id="main-tab-inventory" style="display:none">
        <div class="bg-panelbg border border-gray-800 rounded-xl p-4 mb-4">
            <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div>
                    <div class="text-sm font-black text-white"><i class="fas fa-boxes-stacked text-szgreen mr-2"></i>Inventory & Categories</div>
                    <div class="text-xs text-gray-500 mt-1">Control storefront and bot visibility plus per-channel allocation without touching the Master Dashboard.</div>
                </div>
                <button type="button" onclick="loadInventoryCatalog(true)" class="bg-szcyan/10 text-szcyan border border-szcyan/20 px-4 py-2 rounded-lg text-sm font-bold hover:bg-szcyan hover:text-black transition">
                    <i class="fas fa-rotate mr-1"></i>Refresh Inventory
                </button>
            </div>
            <div id="inventory-status" class="text-xs font-bold mt-3 min-h-[1rem]"></div>
        </div>
        <div id="inventory-loading" class="hidden text-center py-8 text-szcyan">
            <i class="fas fa-spinner fa-spin text-2xl mb-2"></i><br>Loading inventory...
        </div>
        <div id="inventory-catalog" class="space-y-4"></div>
    </div>

    <div id="main-tab-support" style="display:none">

        <!-- Ticket Detail Modal -->
        <div id="ticket-detail-modal" class="fixed inset-0 bg-black/90 z-[60] hidden flex items-center justify-center p-4 backdrop-blur-sm">
            <div class="w-full max-w-2xl bg-panelbg border border-gray-800 rounded-2xl shadow-2xl flex flex-col max-h-[90vh]">
                <div class="flex items-center justify-between p-5 border-b border-gray-800 shrink-0 bg-[#0a0a0a] rounded-t-2xl">
                    <div class="flex-1 min-w-0 pr-4">
                        <div id="tdm-ticket-id" class="font-black text-szcyan text-xs mb-0.5"></div>
                        <div id="tdm-subject" class="font-black text-white text-base leading-tight truncate"></div>
                        <div id="tdm-customer-info" class="text-[10px] text-gray-500 mt-0.5 font-mono"></div>
                        <div id="tdm-live-status" class="text-[10px] text-gray-500 mt-1 min-h-[1rem]"></div>
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                        <select id="tdm-status-select" onchange="adminChangeTicketStatus()" class="bg-black border border-gray-700 text-xs font-bold text-gray-300 rounded-lg px-3 py-2 outline-none focus:border-szgreen cursor-pointer">
                            <option value="open">ðŸŸ¢ Open</option>
                            <option value="in_progress">ðŸŸ¡ In Progress</option>
                            <option value="closed">ðŸ”´ Closed</option>
                        </select>
                        <button onclick="closeTicketModal()" class="text-gray-500 hover:text-red-500 transition p-1"><i class="fas fa-times text-xl"></i></button>
                    </div>
                </div>
                <div id="tdm-messages" class="flex-1 overflow-y-auto p-5 space-y-3 bg-darkbg min-h-[200px]"></div>
                <div class="p-4 border-t border-gray-800 bg-panelbg rounded-b-2xl shrink-0">
                    <div id="tdm-reply-status" class="text-xs font-bold text-center h-4 mb-2"></div>
                    <div class="flex gap-2">
                        <textarea id="tdm-reply-input" rows="2" placeholder="Type your reply as Support Team..."
                            class="flex-1 bg-black border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200 outline-none focus:border-szgreen resize-none"></textarea>
                        <button onclick="adminSendTicketReply()"
                            class="bg-gradient-to-b from-szgreen to-szcyan text-black font-black px-5 rounded-xl hover:opacity-90 transition shrink-0 flex items-center justify-center">
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Ticket Filters & Search -->
        <div class="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-4">
            <div class="relative flex-1 max-w-sm">
                <i class="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm"></i>
                <input id="search-tickets" oninput="filterRows('search-tickets','ticket-row')" placeholder="Search subject / email..."
                    class="w-full bg-panelbg border border-gray-700 rounded-lg pl-9 pr-4 py-2 text-sm text-gray-200 outline-none focus:border-szgreen">
            </div>
            <div class="flex gap-2 text-xs font-bold flex-wrap">
                <button onclick="filterTicketsByStatus('all')"         id="tf-all"          class="ticket-filter-btn active px-3 py-1.5 rounded-lg border border-gray-700 text-gray-400 hover:border-szgreen transition">All ({{ support_tickets|length }})</button>
                <button onclick="filterTicketsByStatus('open')"        id="tf-open"         class="ticket-filter-btn px-3 py-1.5 rounded-lg border border-gray-700 text-gray-400 hover:border-szgreen transition">Open</button>
                <button onclick="filterTicketsByStatus('in_progress')" id="tf-in_progress"  class="ticket-filter-btn px-3 py-1.5 rounded-lg border border-gray-700 text-gray-400 hover:border-szgreen transition">In Progress</button>
                <button onclick="filterTicketsByStatus('closed')"      id="tf-closed"       class="ticket-filter-btn px-3 py-1.5 rounded-lg border border-gray-700 text-gray-400 hover:border-szgreen transition">Closed</button>
            </div>
        </div>

        <!-- Tickets Table -->
        <div class="overflow-x-auto border border-gray-800 rounded-xl bg-panelbg">
            <table class="w-full text-sm text-left">
                <thead class="bg-black text-gray-500 uppercase text-[10px]">
                    <tr>
                        <th class="px-4 py-3">ID</th>
                        <th class="px-4 py-3">Customer</th>
                        <th class="px-4 py-3">Subject</th>
                        <th class="px-4 py-3">Status</th>
                        <th class="px-4 py-3">Messages</th>
                        <th class="px-4 py-3">Date</th>
                        <th class="px-4 py-3">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-800">
                    {% for t in support_tickets %}
                    <tr class="hover:bg-black/30 transition ticket-row" data-search="{{ t.subject|lower }} {{ t.email|lower }} {{ t.name|lower }}" data-status="{{ t.status }}">
                        <td class="px-4 py-3 font-mono text-szcyan font-bold text-xs">{{ t.ticket_id }}</td>
                        <td class="px-4 py-3">
                            <div class="font-bold text-white text-xs">{{ t.name }}</div>
                            <div class="text-[10px] text-gray-500 font-mono">{{ t.email }}</div>
                        </td>
                        <td class="px-4 py-3 text-gray-300 max-w-[220px] truncate text-xs">{{ t.subject }}</td>
                        <td class="px-4 py-3">
                            {% if t.status == 'open' %}
                            <span class="bg-green-900/20 text-green-400 border border-green-900/30 px-2 py-0.5 rounded text-[10px] font-bold uppercase">Open</span>
                            {% elif t.status == 'in_progress' %}
                            <span class="bg-yellow-900/20 text-yellow-400 border border-yellow-900/30 px-2 py-0.5 rounded text-[10px] font-bold uppercase">In Progress</span>
                            {% else %}
                            <span class="bg-red-900/20 text-red-400 border border-red-900/30 px-2 py-0.5 rounded text-[10px] font-bold uppercase">Closed</span>
                            {% endif %}
                        </td>
                        <td class="px-4 py-3 text-gray-400 text-xs">{{ t.message_count if t.message_count is defined else (t.messages | length if t.messages else 0) }}</td>
                        <td class="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">{{ t.created_at }}</td>
                        <td class="px-4 py-3">
                            <button onclick="openTicketModal('{{ t.ticket_id }}')"
                                class="bg-szcyan/10 text-szcyan border border-szcyan/20 px-3 py-1 rounded text-xs font-bold hover:bg-szcyan hover:text-black transition whitespace-nowrap">
                                <i class="fas fa-comments mr-1"></i>View
                            </button>
                        </td>
                    </tr>
                    {% else %}
                    <tr><td colspan="7" class="px-4 py-12 text-center text-gray-600 font-bold">
                        <i class="fas fa-headset text-4xl mb-3 block opacity-30"></i>No support tickets yet.
                    </td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

</div>

<!-- â”€â”€ Customer Detail Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
<div id="customer-modal" class="fixed inset-0 bg-black/90 z-50 hidden flex items-center justify-center p-4 backdrop-blur-sm">
    <div class="w-full max-w-xl bg-panelbg border border-gray-800 rounded-2xl shadow-2xl fade-in flex flex-col max-h-[92vh]">

        <div class="flex items-center justify-between p-5 border-b border-gray-800 shrink-0">
            <div class="flex items-center gap-3">
                <div class="w-11 h-11 rounded-full bg-gray-900 border border-gray-700 overflow-hidden flex items-center justify-center" id="cm-avatar-wrap">
                    <i class="fas fa-user text-gray-500 cm-avatar-placeholder"></i>
                    <img class="cm-avatar-img w-full h-full object-cover hidden" id="cm-avatar-img" src="" alt="">
                </div>
                <div>
                    <div class="font-black text-white text-base" id="cm-name">â€”</div>
                    <div class="text-xs text-gray-500 font-mono" id="cm-email">â€”</div>
                </div>
            </div>
            <button onclick="closeCustomerModal()" class="text-gray-500 hover:text-red-500 transition"><i class="fas fa-times text-xl"></i></button>
        </div>

        <div class="flex border-b border-gray-800 shrink-0 px-4 gap-4 overflow-x-auto">
            <button onclick="switchDetailTab('info')" id="dt-btn-info" class="tab-btn active py-3 text-xs font-bold whitespace-nowrap">
                <i class="fas fa-id-card mr-1"></i>Wallet & Controls
            </button>
            <button onclick="switchDetailTab('edit')" id="dt-btn-edit" class="tab-btn py-3 text-xs font-bold whitespace-nowrap">
                <i class="fas fa-edit mr-1"></i>Edit Profile
            </button>
            <button onclick="switchDetailTab('avatar')" id="dt-btn-avatar" class="tab-btn py-3 text-xs font-bold whitespace-nowrap">
                <i class="fas fa-image mr-1"></i>Avatar
            </button>
            <button onclick="switchDetailTab('orders')" id="dt-btn-orders" class="tab-btn py-3 text-xs font-bold whitespace-nowrap">
                <i class="fas fa-receipt mr-1"></i>Orders
            </button>
        </div>

        <div class="flex-1 overflow-y-auto p-5 min-h-0">

            <div id="dt-info" class="detail-modal-tab show space-y-4">
                <div id="cm-status" class="text-xs font-bold text-center h-4"></div>

                <div class="bg-black border border-gray-800 rounded-xl p-4 space-y-3 text-sm">
                    <div class="grid grid-cols-2 gap-3 pb-3 border-b border-gray-800">
                        <div>
                            <div class="text-[10px] text-gray-500 uppercase">User ID</div>
                            <div class="text-white font-mono font-bold" id="cm-uid">â€”</div>
                        </div>
                        <div>
                            <div class="text-[10px] text-gray-500 uppercase">Username</div>
                            <div class="text-szcyan font-bold" id="cm-username">â€”</div>
                        </div>
                        <div>
                            <div class="text-[10px] text-gray-500 uppercase">Joined</div>
                            <div class="text-gray-300 text-xs" id="cm-joined">â€”</div>
                        </div>
                        <div>
                            <div class="text-[10px] text-gray-500 uppercase">Orders</div>
                            <div class="text-white font-bold" id="cm-orders-count">â€”</div>
                        </div>
                    </div>
                    
                    <div class="text-xs text-gray-500 uppercase font-bold mt-2">Current Wallets</div>
                    <div id="cm-balances-container" class="grid grid-cols-2 gap-3"></div>
                </div>

                <div class="bg-black border border-gray-800 rounded-xl p-4">
                    <div class="text-xs text-gray-500 uppercase font-bold mb-3">Adjust Balance (Add custom currency!)</div>
                    <div class="flex gap-2 mb-2">
                        <input type="text" id="bal-currency" list="currency-list" placeholder="Currency (EGP, USD, SAR...)" 
                               class="flex-1 bg-[#0a0a0a] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white uppercase outline-none focus:border-szgreen" value="EGP">
                        <datalist id="currency-list">
                            <option value="EGP">
                            <option value="USD">
                        </datalist>
                        <select id="bal-action" class="flex-1 bg-[#0a0a0a] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-szgreen">
                            <option value="add">âž• Add</option>
                            <option value="sub">âž– Subtract</option>
                        </select>
                    </div>
                    <div class="flex gap-2">
                        <input type="number" id="bal-amount" min="0" step="0.01" placeholder="Amount..."
                            class="flex-1 bg-[#0a0a0a] border border-gray-700 rounded-lg px-4 py-2 text-sm text-white outline-none focus:border-szgreen">
                        <button onclick="submitBalance()" id="bal-btn"
                            class="bg-szgreen text-black font-bold px-4 py-2 rounded-lg text-sm hover:opacity-90 transition">
                            Apply Balance
                        </button>
                    </div>
                </div>

                <div class="border border-red-900/40 rounded-xl p-4">
                    <div class="text-xs text-red-400 uppercase font-bold mb-3"><i class="fas fa-exclamation-triangle mr-1"></i>Account Controls</div>
                    <div class="grid grid-cols-2 gap-3 mb-3">
                        <button onclick="toggleCustomerStatus('ban')" id="cm-btn-ban" class="w-full bg-orange-900/20 text-orange-400 border border-orange-900/30 py-2 rounded-lg text-xs font-bold hover:bg-orange-900/40 transition">
                            <i class="fas fa-ban mr-1"></i>Suspend Account
                        </button>
                        <button onclick="toggleCustomerStatus('freeze')" id="cm-btn-freeze" class="w-full bg-blue-900/20 text-blue-400 border border-blue-900/30 py-2 rounded-lg text-xs font-bold hover:bg-blue-900/40 transition">
                            <i class="fas fa-snowflake mr-1"></i>Freeze Balance
                        </button>
                    </div>
                    <button onclick="deleteCustomer()" class="w-full bg-red-900/20 text-red-400 border border-red-900/30 py-2 rounded-lg text-sm font-bold hover:bg-red-900/40 transition">
                        <i class="fas fa-trash mr-2"></i>Delete Customer Account
                    </button>
                </div>
            </div>

            <div id="dt-edit" class="detail-modal-tab space-y-4">
                <div id="cm-edit-status" class="text-xs font-bold text-center h-4"></div>
                <form onsubmit="adminUpdateProfile(event)" class="space-y-3">
                    <div>
                        <label class="text-xs text-gray-500 uppercase font-bold block mb-1">Full Name</label>
                        <input type="text" id="cm-edit-name" required
                            class="w-full bg-black border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-200 outline-none focus:border-szgreen transition">
                    </div>
                    <div>
                        <label class="text-xs text-gray-500 uppercase font-bold block mb-1">Username</label>
                        <div class="relative">
                            <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm font-bold">@</span>
                            <input type="text" id="cm-edit-username" required minlength="3" maxlength="20"
                                class="w-full bg-black border border-gray-700 rounded-lg pl-8 pr-4 py-2.5 text-sm text-gray-200 outline-none focus:border-szgreen transition">
                        </div>
                        <p class="text-[10px] text-gray-600 mt-1">3-20 chars Â· letters/numbers/_ only</p>
                    </div>
                    <div>
                        <label class="text-xs text-gray-500 uppercase font-bold block mb-1">New Password <span class="text-gray-600">(leave blank to keep)</span></label>
                        <input type="password" id="cm-edit-password" minlength="8" placeholder="Min 8 characters..."
                            class="w-full bg-black border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-200 outline-none focus:border-szcyan transition">
                    </div>
                    <button type="submit" id="cm-edit-btn"
                        class="w-full bg-gradient-to-r from-szgreen to-szcyan text-black py-2.5 rounded-xl font-black uppercase text-sm hover:opacity-90 transition">
                        Save Changes
                    </button>
                </form>
                <div class="border-t border-gray-800 pt-4">
                    <div class="text-xs text-gray-500 uppercase font-bold mb-2"><i class="fas fa-envelope mr-1"></i>Change Email (sends OTP to new email)</div>
                    <div class="flex gap-2">
                        <input type="email" id="cm-new-email" placeholder="new@email.com"
                            class="flex-1 bg-black border border-gray-700 rounded-lg px-4 py-2 text-sm text-gray-200 outline-none focus:border-szgreen transition">
                        <button onclick="adminEmailRequest()" id="cm-email-req-btn"
                            class="bg-szcyan text-black font-bold px-4 py-2 rounded-lg text-sm hover:opacity-90 transition whitespace-nowrap">
                            Send OTP
                        </button>
                    </div>
                    <div id="cm-email-otp-row" class="hidden flex gap-2 mt-2">
                        <input type="text" id="cm-email-otp" maxlength="6" placeholder="6-digit code"
                            class="flex-1 bg-black border border-gray-700 rounded-lg px-4 py-2 text-sm text-szgreen text-center tracking-widest font-black outline-none focus:border-szgreen">
                        <button onclick="adminEmailVerify()"
                            class="bg-szgreen text-black font-bold px-4 py-2 rounded-lg text-sm hover:opacity-90 transition whitespace-nowrap">
                            Verify
                        </button>
                    </div>
                </div>
            </div>

            <div id="dt-avatar" class="detail-modal-tab space-y-4 text-center">
                <div class="flex flex-col items-center gap-4">
                    <div class="w-28 h-28 rounded-full bg-gray-900 border-2 border-gray-700 overflow-hidden flex items-center justify-center">
                        <i class="fas fa-user text-5xl text-gray-600 cm-avatar-placeholder-big" id="cm-big-placeholder"></i>
                        <img id="cm-big-avatar" class="w-full h-full object-cover hidden" src="" alt="">
                    </div>
                    <div>
                        <p class="text-xs text-gray-500 mb-3">Upload a new avatar for this customer Â· JPG/PNG Â· Max 1MB</p>
                        <label class="cursor-pointer bg-szcyan/10 text-szcyan border border-szcyan/30 px-5 py-2 rounded-lg text-sm font-bold hover:bg-szcyan hover:text-black transition">
                            <i class="fas fa-upload mr-2"></i>Choose Image
                            <input type="file" id="admin-avatar-input" accept="image/*" class="hidden" onchange="adminAvatarUpload(this)">
                        </label>
                    </div>
                    <button onclick="adminRemoveAvatar()" class="text-xs text-red-400 hover:text-red-300 transition">
                        <i class="fas fa-trash mr-1"></i>Remove Avatar
                    </button>
                    <div id="cm-avatar-status" class="text-xs font-bold h-4"></div>
                </div>
            </div>

            <div id="dt-orders" class="detail-modal-tab">
                <div id="cm-orders-loading" class="text-center py-6 text-szcyan hidden">
                    <i class="fas fa-spinner fa-spin text-2xl mb-2"></i><br>Loading...
                </div>
                <div class="overflow-x-auto border border-gray-800 rounded-xl bg-black">
                    <table class="w-full text-xs text-left whitespace-nowrap">
                        <thead class="bg-[#111] text-gray-500 uppercase text-[9px]">
                            <tr>
                                <th class="px-3 py-2">Order</th>
                                <th class="px-3 py-2">Package</th>
                                <th class="px-3 py-2">Price</th>
                                <th class="px-3 py-2">Date</th>
                                <th class="px-3 py-2">Code</th>
                            </tr>
                        </thead>
                        <tbody id="cm-orders-tbody" class="divide-y divide-gray-800 text-gray-300"></tbody>
                    </table>
                </div>
            </div>

        </div>
    </div>
</div>

<script src="/static/js/core.js"></script>
<script>
// â”€â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const $ = id => document.getElementById(id);
const setText = (id, v) => { const e=$(id); if(e) e.innerText=v??''; };

function clearNode(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
}

function createNode(tag, className = '', text = null) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== null && text !== undefined) node.textContent = String(text);
    return node;
}

function setButtonContent(button, label, iconClass = '') {
    if (!button) return;
    clearNode(button);
    if (iconClass) {
        const icon = createNode('i', `fas ${iconClass}`);
        if (label) icon.classList.add('mr-1');
        button.appendChild(icon);
    }
    if (label) button.appendChild(createNode('span', '', label));
}

async function fetchJsonOrThrow(url, options = {}, meta = {}) {
    const requestOptions = Object.assign({ credentials: 'same-origin', cache: 'no-store' }, options || {});
    const response = await fetch(url, requestOptions);
    const contentType = response.headers.get('content-type') || '';
    let payload;

    if (contentType.includes('application/json')) {
        payload = await response.json();
    } else {
        const text = await response.text();
        payload = { success: response.ok, msg: text };
    }

    if (!response.ok) throw new Error(payload?.msg || `Request failed (${response.status})`);
    if (!meta.allowFailurePayload && payload && payload.success === false) {
        throw new Error(payload.msg || 'Request failed.');
    }
    return payload;
}

function setInlineStatus(element, msg, isError = false) {
    if (!element) return;
    clearNode(element);
    if (!msg) return;
    const wrapper = createNode('span', `${isError ? 'text-red-500' : 'text-szgreen'} inline-flex items-center gap-1`);
    const icon = createNode('i', `fas ${isError ? 'fa-times-circle' : 'fa-check-circle'}`);
    const text = createNode('span', '', msg);
    wrapper.append(icon, text);
    element.appendChild(wrapper);
}

function showToast(msg, type='success') {
    const c = $('toast-container');
    if (!c) return;
    const t = createNode('div', `toast border-l-4 ${type==='error' ? 'border-red-500' : 'border-szgreen'} fade-in`);
    const icon = createNode('i', `fas ${type==='error' ? 'fa-times-circle text-red-500' : 'fa-check-circle text-szgreen'} text-base`);
    const text = createNode('span', '', msg || 'Done');
    t.append(icon, text);
    c.appendChild(t);
    setTimeout(() => {
        t.style.animation = 'fadeOut 0.3s forwards';
        setTimeout(() => t.remove(), 300);
    }, 3000);
}

function copyText(txt) {
    navigator.clipboard.writeText(String(txt ?? ''));
    showToast('Copied!');
}

function filterRows(inputId, rowClass) {
    const q = $(inputId).value.toLowerCase();
    document.querySelectorAll('.'+rowClass).forEach(r=>{
        const matchSearch = r.dataset.search.includes(q);
        const matchStatus = r.dataset.status === undefined || _ticketStatusFilter === 'all' || r.dataset.status === _ticketStatusFilter;
        r.style.display = (matchSearch && matchStatus) ? '' : 'none';
    });
}

// â”€â”€â”€ Main Tabs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const ADMIN_TAB_KEY = 'sz_admin_active_tab';
let _confirmResolver = null;

function switchMainTab(tab) {
    const tabs = ['customers', 'orders', 'inventory', 'support'];
    tabs.forEach(t => {
        const el = $('main-tab-' + t);
        const btn = $('main-tab-btn-' + t);
        if (el) el.style.display = t === tab ? 'block' : 'none';
        if (btn) btn.classList.toggle('active', t === tab);
    });
    localStorage.setItem(ADMIN_TAB_KEY, tab);
    history.replaceState(null, '', `#${tab}`);
    if (tab === 'inventory') loadInventoryCatalog();
}

function showConfirmModal(message, title='Confirm Action') {
    const modal = $('confirm-modal');
    if (!modal) return Promise.resolve(false);
    setText('confirm-title', title);
    setText('confirm-message', message);
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    return new Promise(resolve => { _confirmResolver = resolve; });
}

function closeConfirmModal(result) {
    const modal = $('confirm-modal');
    if (modal) { modal.classList.add('hidden'); modal.classList.remove('flex'); }
    if (_confirmResolver) {
        const resolve = _confirmResolver;
        _confirmResolver = null;
        resolve(!!result);
    }
}

// â”€â”€â”€ Customer Modal State â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
let _cEmail = '', _cOrdersLoaded = false;
let _cIsBanned = false, _cIsFrozen = false;

function switchDetailTab(tab) {
    ['info','edit','avatar','orders'].forEach(t => {
        const el=$('dt-'+t), btn=$('dt-btn-'+t);
        if(el) el.classList.toggle('show', t===tab);
        if(btn) btn.classList.toggle('active', t===tab);
    });
    if(tab==='orders' && !_cOrdersLoaded) loadCustomerOrders();
}

function openCustomerModal(c) {
    _cEmail = c.email || '';
    _cOrdersLoaded = false;
    _cIsBanned = c.is_banned || false;
    _cIsFrozen = c.balance_frozen || false;

    setText('cm-name',  c.name);
    setText('cm-email', c.email);

    const img = $('cm-avatar-img'), big = $('cm-big-avatar');
    const bigPh = $('cm-big-placeholder');
    if (c.avatar) {
        img.src = c.avatar; img.classList.remove('hidden');
        big.src = c.avatar; big.classList.remove('hidden');
        document.querySelectorAll('.cm-avatar-placeholder').forEach(e=>e.classList.add('hidden'));
        if(bigPh) bigPh.classList.add('hidden');
    } else {
        img.classList.add('hidden'); big.classList.add('hidden');
        document.querySelectorAll('.cm-avatar-placeholder').forEach(e=>e.classList.remove('hidden'));
        if(bigPh) bigPh.classList.remove('hidden');
    }

    setText('cm-uid',      c.user_id ? '#'+c.user_id : 'â€”');
    setText('cm-username', c.username ? '@'+c.username : 'â€” (none)');
    setText('cm-joined',   c.created_at || 'â€”');
    
    const orderCount = document.querySelectorAll('.order-row[data-search*="'+c.email.toLowerCase()+'"]').length;
    setText('cm-orders-count', orderCount + ' orders');

    renderBalances(c);
    updateStatusButtons();

    const en=$('cm-edit-name'), eu=$('cm-edit-username'), ep=$('cm-edit-password');
    if(en) en.value = c.name;
    if(eu) eu.value = c.username || '';
    if(ep) ep.value = '';

    ['cm-status','cm-edit-status','cm-avatar-status'].forEach(id => { const el = $(id); if (el) clearNode(el); });
    $('cm-email-otp-row')?.classList.add('hidden');
    $('cm-email-req-btn')?.classList.remove('hidden');
    if($('cm-new-email')) $('cm-new-email').value='';

    switchDetailTab('info');
    $('customer-modal').classList.remove('hidden');
}

function closeCustomerModal() { $('customer-modal').classList.add('hidden'); }
$('customer-modal')?.addEventListener('click', e => { if(e.target===$('customer-modal')) closeCustomerModal(); });

function renderBalances(data) {
    const container = $('cm-balances-container');
    if (!container) return;
    clearNode(container);
    let hasBal = false;
    for (const key in data) {
        if (!key.startsWith('balance_')) continue;
        hasBal = true;
        const cur = key.split('_')[1].toUpperCase();
        let color = 'text-white';
        let border = 'border-gray-700';
        if (cur === 'EGP') { color = 'text-yellow-500'; border = 'border-yellow-500/20'; }
        if (cur === 'USD') { color = 'text-szcyan'; border = 'border-szcyan/20'; }
        const card = createNode('div', `bg-gray-900 border ${border} rounded-lg p-3 text-center`);
        card.appendChild(createNode('div', 'text-[10px] text-gray-500 mb-1', `${cur} Balance`));
        card.appendChild(createNode('div', `${color} font-black text-xl`, data[key] ?? 0));
        container.appendChild(card);
    }
    if (!hasBal) {
        container.appendChild(createNode('div', 'col-span-2 text-center text-gray-500 text-xs py-2', 'No balance records'));
    }
}

function updateStatusButtons() {
    const btnBan = $('cm-btn-ban');
    const btnFreeze = $('cm-btn-freeze');
    if (!btnBan || !btnFreeze) return;
    if (_cIsBanned) {
        setButtonContent(btnBan, 'Unban Account', 'fa-check-circle');
        btnBan.className = 'w-full bg-szgreen/20 text-szgreen border border-szgreen/30 py-2 rounded-lg text-sm font-bold hover:bg-szgreen/40 transition';
    } else {
        setButtonContent(btnBan, 'Suspend Account', 'fa-ban');
        btnBan.className = 'w-full bg-orange-900/20 text-orange-400 border border-orange-900/30 py-2 rounded-lg text-sm font-bold hover:bg-orange-900/40 transition';
    }
    if (_cIsFrozen) {
        setButtonContent(btnFreeze, 'Unfreeze Balance', 'fa-unlock');
        btnFreeze.className = 'w-full bg-szgreen/20 text-szgreen border border-szgreen/30 py-2 rounded-lg text-sm font-bold hover:bg-szgreen/40 transition';
    } else {
        setButtonContent(btnFreeze, 'Freeze Balance', 'fa-snowflake');
        btnFreeze.className = 'w-full bg-blue-900/20 text-blue-400 border border-blue-900/30 py-2 rounded-lg text-sm font-bold hover:bg-blue-900/40 transition';
    }
}

async function toggleCustomerStatus(action) {
    if(!(await showConfirmModal(`Are you sure you want to ${action} this account?`, 'Confirm Status Change'))) return;
    const fd = new FormData();
    fd.append('email', _cEmail);
    fd.append('action', action);
    try {
        const d = await (await fetch('/api/store/admin/toggle-status', {method:'POST', body:fd})).json();
        if (d.success) {
            showToast(d.msg);
            if (action === 'ban') _cIsBanned = d.new_status;
            if (action === 'freeze') _cIsFrozen = d.new_status;
            updateStatusButtons();
        } else showToast(d.msg, 'error');
    } catch { showToast('Error!', 'error'); }
}

// â”€â”€â”€ Balance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function submitBalance() {
    const amount = parseFloat($('bal-amount').value);
    if (!amount || amount <= 0) return showToast('Enter a valid amount', 'error');
    const currency = $('bal-currency').value.trim();
    if (!currency) return showToast('Enter a valid currency', 'error');
    const action = $('bal-action').value;
    const btn = $('bal-btn');
    const orig = btn?.dataset.label || btn?.textContent.trim() || 'Apply Balance';
    if (btn) {
        btn.dataset.label = orig;
        btn.disabled = true;
        setButtonContent(btn, '', 'fa-spinner fa-spin');
    }
    const fd = new FormData();
    fd.append('email', _cEmail);
    fd.append('amount', amount);
    fd.append('action', action);
    fd.append('currency', currency);
    try {
        const d = await (await fetch('/api/store/manage_balance',{method:'POST',body:fd})).json();
        if (d.success) {
            showToast(d.msg);
            const newVal = await (await fetch('/api/store/customer-info?email=' + encodeURIComponent(_cEmail))).json();
            if (newVal.success) renderBalances(newVal);
            $('bal-amount').value = '';
        } else {
            showToast(d.msg,'error');
        }
    } catch {
        showToast('Error!','error');
    }
    if (btn) {
        setButtonContent(btn, orig);
        btn.disabled = false;
    }
}

// â”€â”€â”€ Admin Edit Profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function adminUpdateProfile(e) {
    e.preventDefault();
    const btn = $('cm-edit-btn');
    const orig = btn?.dataset.label || btn?.textContent.trim() || 'Save Changes';
    if (btn) {
        btn.dataset.label = orig;
        btn.disabled = true;
        setButtonContent(btn, '', 'fa-spinner fa-spin');
    }
    const fd = new FormData();
    fd.append('email', _cEmail);
    fd.append('name', $('cm-edit-name').value);
    fd.append('username', $('cm-edit-username').value);
    const pw = $('cm-edit-password').value;
    if (pw) fd.append('new_password', pw);
    try {
        const d = await (await fetch('/api/store/admin/update-customer',{method:'POST',body:fd})).json();
        if (d.success) {
            showToast(d.msg);
            setText('cm-name', d.name);
            setText('cm-username', '@' + d.username);
            $('cm-edit-password').value = '';
            setFormStatus('cm-edit-status', d.msg, false);
        } else {
            setFormStatus('cm-edit-status', d.msg, true);
        }
    } catch {
        setFormStatus('cm-edit-status','Error!',true);
    }
    if (btn) {
        setButtonContent(btn, orig);
        btn.disabled = false;
    }
}

// â”€â”€â”€ Admin Email Change â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function adminEmailRequest() {
    const btn=$('cm-email-req-btn'), orig=btn.innerText;
    btn.innerText='...'; btn.disabled=true;
    const fd=new FormData(); fd.append('email',_cEmail); fd.append('new_email',$('cm-new-email').value);
    try {
        const d=await(await fetch('/api/store/admin/email-request',{method:'POST',body:fd})).json();
        if(d.success){ $('cm-email-otp-row').classList.remove('hidden'); btn.classList.add('hidden'); showToast(d.msg); }
        else showToast(d.msg,'error');
    } catch { showToast('Error!','error'); }
    btn.innerText=orig; btn.disabled=false;
}

async function adminEmailVerify() {
    const fd=new FormData(); fd.append('email',_cEmail); fd.append('code',$('cm-email-otp').value);
    try {
        const d=await(await fetch('/api/store/admin/email-verify',{method:'POST',body:fd})).json();
        if(d.success){
            _cEmail=d.new_email;
            setText('cm-email',d.new_email);
            showToast(d.msg);
            $('cm-email-otp-row').classList.add('hidden');
            $('cm-email-req-btn').classList.remove('hidden');
            $('cm-new-email').value='';
        } else showToast(d.msg,'error');
    } catch { showToast('Error!','error'); }
}

// â”€â”€â”€ Avatar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function adminAvatarUpload(input) {
    const file=input.files[0]; if(!file) return;
    if(file.size>1_000_000) return showToast('Max 1MB!','error');
    const reader=new FileReader();
    reader.onload=async e=>{
        const b64=e.target.result;
        const fd=new FormData(); fd.append('email',_cEmail); fd.append('avatar_b64',b64);
        try {
            const d=await(await fetch('/api/store/admin/set-avatar',{method:'POST',body:fd})).json();
            if(d.success){
                $('cm-avatar-img').src=b64; $('cm-avatar-img').classList.remove('hidden');
                $('cm-big-avatar').src=b64; $('cm-big-avatar').classList.remove('hidden');
                document.querySelectorAll('.cm-avatar-placeholder').forEach(e=>e.classList.add('hidden'));
                $('cm-big-placeholder')?.classList.add('hidden');
                setFormStatus('cm-avatar-status',d.msg,false);
            } else setFormStatus('cm-avatar-status',d.msg,true);
        } catch { setFormStatus('cm-avatar-status','Error!',true); }
    };
    reader.readAsDataURL(file);
}

async function adminRemoveAvatar() {
    if(!(await showConfirmModal('Remove this customer avatar?', 'Confirm Avatar Removal'))) return;
    const fd=new FormData(); fd.append('email',_cEmail); fd.append('avatar_b64','');
    try {
        const d=await(await fetch('/api/store/admin/set-avatar',{method:'POST',body:fd})).json();
        if(d.success){
            $('cm-avatar-img').classList.add('hidden'); $('cm-big-avatar').classList.add('hidden');
            document.querySelectorAll('.cm-avatar-placeholder').forEach(e=>e.classList.remove('hidden'));
            $('cm-big-placeholder')?.classList.remove('hidden');
            showToast('Avatar removed');
        } else showToast(d.msg,'error');
    } catch { showToast('Error!','error'); }
}

// â”€â”€â”€ Customer Orders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function appendCustomerOrdersEmptyRow(tbody, message) {
    if (!tbody) return;
    const row = createNode('tr');
    const cell = createNode('td', 'px-3 py-6 text-center text-gray-500', message);
    cell.colSpan = 5;
    row.appendChild(cell);
    tbody.appendChild(row);
}

function buildCustomerOrderRow(order) {
    const row = createNode('tr', 'hover:bg-[#111] transition');
    const orderCell = createNode('td', 'px-3 py-2 font-mono text-szcyan', `#${order.order_id}`);
    const categoryCell = createNode('td', 'px-3 py-2 font-bold text-white', order.category || 'Unknown');
    const priceCell = createNode('td', 'px-3 py-2');
    const priceWrap = createNode('div', `font-black ${order.currency === 'USD' ? 'text-szcyan' : 'text-yellow-500'}`);
    priceWrap.appendChild(createNode('span', '', order.price ?? 0));
    priceWrap.appendChild(document.createTextNode(' '));
    priceWrap.appendChild(createNode('span', 'text-[10px] text-gray-500', order.currency || 'EGP'));
    priceCell.appendChild(priceWrap);
    const dateCell = createNode('td', 'px-3 py-2 text-gray-500', order.date || order.created_at || '');
    const codeCell = createNode('td', 'px-3 py-2');
    const copyBtn = createNode('button', 'bg-gray-900 text-szgreen border border-gray-700 px-2 py-1 rounded text-[10px] font-mono hover:bg-szgreen hover:text-black transition', 'Copy');
    const codeToCopy = String(order.code || order.code_masked || '');
    if (!codeToCopy) {
        copyBtn.disabled = true;
        copyBtn.classList.add('opacity-50', 'cursor-not-allowed');
    } else {
        copyBtn.addEventListener('click', () => copyText(codeToCopy));
    }
    codeCell.appendChild(copyBtn);
    row.append(orderCell, categoryCell, priceCell, dateCell, codeCell);
    return row;
}

async function loadCustomerOrders() {
    const tbody = $('cm-orders-tbody');
    const loader = $('cm-orders-loading');
    if (loader) loader.classList.remove('hidden');
    clearNode(tbody);
    try {
        const d = await fetchJsonOrThrow('/api/store/admin/customer-orders?email=' + encodeURIComponent(_cEmail));
        if (loader) loader.classList.add('hidden');
        const orders = Array.isArray(d.orders) ? d.orders : [];
        if (!orders.length) {
            appendCustomerOrdersEmptyRow(tbody, 'No orders found.');
            _cOrdersLoaded = true;
            return;
        }
        orders.forEach(order => tbody.appendChild(buildCustomerOrderRow(order)));
        _cOrdersLoaded = true;
    } catch (error) {
        if (loader) loader.classList.add('hidden');
        appendCustomerOrdersEmptyRow(tbody, error.message || 'Failed to load orders.');
        showToast(error.message || 'Failed to load orders.', 'error');
    }
}

// â”€â”€â”€ Delete Customer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function deleteCustomer() {
    if(!(await showConfirmModal(`Delete account for ${_cEmail}? This cannot be undone.`, 'Confirm Delete'))) return;
    const fd=new FormData(); fd.append('email',_cEmail);
    try {
        const d=await(await fetch('/api/store/admin/delete-customer',{method:'POST',body:fd})).json();
        if(d.success){ showToast(d.msg); closeCustomerModal(); setTimeout(()=>location.reload(),1200); }
        else showToast(d.msg,'error');
    } catch { showToast('Error!','error'); }
}

// â”€â”€â”€ Return Order â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function returnOrder(orderId) {
    if(!(await showConfirmModal(`Return order #${orderId}? The code will go back to stock.`, 'Confirm Return'))) return;
    await returnOrderNow(orderId);
}

async function returnOrderNow(orderId) {
    const fd = new FormData();
    fd.append('order_id', orderId);
    try {
        const d = await fetchJsonOrThrow('/api/store/admin/return-order', {
            method: 'POST',
            body: fd,
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        showToast(d.msg || 'Order returned to stock!');
        localStorage.setItem(ADMIN_TAB_KEY, 'orders');
        location.reload();
    } catch (error) {
        showToast(error.message || 'Error returning order.', 'error');
    }
}

async function confirmBulkReturns() {
    const raw = $('bulk-return-ids')?.value || '';
    const ids = raw.split(/\n|,/).map(v => v.trim()).filter(Boolean);
    if (!ids.length) { showToast('Paste at least one order ID', 'error'); return; }
    if (!(await showConfirmModal(`Process ${ids.length} return(s)?`, 'Confirm Bulk Returns'))) return;

    const fd = new FormData();
    fd.append('order_ids', ids.join('\n'));
    const status = $('bulk-return-status');
    setInlineStatus(status, 'Processing bulk returns...', false);
    try {
        const d = await fetchJsonOrThrow('/api/store/admin/return-orders-bulk', { method:'POST', body:fd }, { allowFailurePayload: true });
        const processed = Number(d.processed || 0);
        const failed = Number(d.failed || 0);
        const errors = Array.isArray(d.errors) ? d.errors : [];
        let message = d.msg || `Processed ${processed} returns, ${failed} failed.`;
        if (failed > 0 && errors.length) message += ` Errors: ${errors.join('; ')}`;
        setInlineStatus(status, message, d.success === false);
        if (processed > 0) {
            showToast(d.msg || 'Bulk returns processed.');
            localStorage.setItem(ADMIN_TAB_KEY, 'orders');
            setTimeout(() => location.reload(), 900);
            return;
        }
        showToast(message, 'error');
    } catch (error) {
        setInlineStatus(status, error.message || 'Bulk return failed.', true);
        showToast(error.message || 'Bulk return failed.', 'error');
    }
}

// â”€â”€â”€ Support Tickets â€” Admin â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
let _inventoryLoaded = false;
let _inventoryLoading = false;

function formatInventoryCount(value, unlimited) {
    if (unlimited) return 'Unlimited';
    return String(value ?? 0);
}

function createMetricCard(label, value, role, accentClass = 'text-white') {
    const card = createNode('div', 'bg-[#0a0a0a] border border-gray-800 rounded-lg px-3 py-2');
    card.appendChild(createNode('div', 'text-[10px] uppercase text-gray-500 mb-1', label));
    const valueNode = createNode('div', `${accentClass} font-black text-sm`, value);
    valueNode.dataset.role = role;
    card.appendChild(valueNode);
    return card;
}

function createInventoryInput(label, input) {
    const wrap = createNode('label', 'bg-[#0a0a0a] border border-gray-800 rounded-lg px-3 py-2 flex flex-col gap-2');
    wrap.appendChild(createNode('span', 'text-[10px] uppercase text-gray-500 font-bold', label));
    wrap.appendChild(input);
    return wrap;
}

function updateInventoryRow(row, product) {
    if (!row || !product) return;
    const setRoleText = (role, value) => {
        const node = row.querySelector(`[data-role="${role}"]`);
        if (node) node.textContent = value;
    };

    row.dataset.catId = product.category_id || row.dataset.catId || '';
    row.dataset.stockKey = product.stock_key || row.dataset.stockKey || '';
    setRoleText('product-name', product.name || product.stock_key || 'Unnamed Product');
    setRoleText('product-key', product.stock_key || '');
    setRoleText('stock-count', String(product.stock_count ?? 0));
    setRoleText('web-sold', String(product.web_sold ?? 0));
    setRoleText('bot-sold', String(product.bot_sold ?? 0));
    setRoleText('remaining-web', formatInventoryCount(product.remaining_web, product.web_unlimited));
    setRoleText('remaining-bot', formatInventoryCount(product.remaining_bot, product.bot_unlimited));

    const webToggle = row.querySelector('[data-role="is-visible-web"]');
    const botToggle = row.querySelector('[data-role="is-visible-bot"]');
    const webAllocation = row.querySelector('[data-role="allocation-web"]');
    const botAllocation = row.querySelector('[data-role="allocation-bot"]');
    if (webToggle) webToggle.checked = !!product.is_visible_web;
    if (botToggle) botToggle.checked = !!product.is_visible_bot;
    if (webAllocation) webAllocation.value = product.allocation_web ?? '';
    if (botAllocation) botAllocation.value = product.allocation_bot ?? '';
}

function buildInventoryProductRow(category, product) {
    const row = createNode('div', 'bg-black border border-gray-800 rounded-xl p-4 space-y-4');
    row.dataset.productRow = 'true';
    row.dataset.catId = category.cat_id || '';
    row.dataset.stockKey = product.stock_key || '';

    const top = createNode('div', 'flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4');
    const titleWrap = createNode('div', 'min-w-0');
    const nameNode = createNode('div', 'font-black text-white text-sm', product.name || product.stock_key || 'Unnamed Product');
    nameNode.dataset.role = 'product-name';
    const keyNode = createNode('div', 'text-[11px] text-gray-500 font-mono mt-1', product.stock_key || '');
    keyNode.dataset.role = 'product-key';
    titleWrap.append(nameNode, keyNode);
    top.appendChild(titleWrap);

    const metrics = createNode('div', 'grid grid-cols-2 md:grid-cols-5 gap-2 xl:min-w-[520px]');
    metrics.appendChild(createMetricCard('Live Stock', product.stock_count ?? 0, 'stock-count', 'text-white'));
    metrics.appendChild(createMetricCard('Web Sold', product.web_sold ?? 0, 'web-sold', 'text-szgreen'));
    metrics.appendChild(createMetricCard('Bot Sold', product.bot_sold ?? 0, 'bot-sold', 'text-szcyan'));
    metrics.appendChild(createMetricCard('Web Remaining', formatInventoryCount(product.remaining_web, product.web_unlimited), 'remaining-web', 'text-szgreen'));
    metrics.appendChild(createMetricCard('Bot Remaining', formatInventoryCount(product.remaining_bot, product.bot_unlimited), 'remaining-bot', 'text-szcyan'));
    top.appendChild(metrics);
    row.appendChild(top);

    const controls = createNode('div', 'grid md:grid-cols-4 gap-3');

    const webToggle = createNode('input', 'h-4 w-4 rounded border-gray-700 bg-black text-szgreen focus:ring-szgreen');
    webToggle.type = 'checkbox';
    webToggle.dataset.role = 'is-visible-web';
    const webWrap = createNode('label', 'bg-[#0a0a0a] border border-gray-800 rounded-lg px-3 py-2 flex items-center justify-between gap-3');
    const webLabel = createNode('div', 'flex flex-col');
    webLabel.append(createNode('span', 'text-[10px] uppercase text-gray-500 font-bold', 'Visible on Web'));
    webLabel.append(createNode('span', 'text-xs text-gray-300', 'Storefront listing'));
    webWrap.append(webLabel, webToggle);
    controls.appendChild(webWrap);

    const botToggle = createNode('input', 'h-4 w-4 rounded border-gray-700 bg-black text-szcyan focus:ring-szcyan');
    botToggle.type = 'checkbox';
    botToggle.dataset.role = 'is-visible-bot';
    const botWrap = createNode('label', 'bg-[#0a0a0a] border border-gray-800 rounded-lg px-3 py-2 flex items-center justify-between gap-3');
    const botLabel = createNode('div', 'flex flex-col');
    botLabel.append(createNode('span', 'text-[10px] uppercase text-gray-500 font-bold', 'Visible on Bot'));
    botLabel.append(createNode('span', 'text-xs text-gray-300', 'Telegram pulls'));
    botWrap.append(botLabel, botToggle);
    controls.appendChild(botWrap);

    const webAllocation = createNode('input', 'w-full bg-black border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 outline-none focus:border-szgreen');
    webAllocation.type = 'number';
    webAllocation.min = '0';
    webAllocation.placeholder = 'Unlimited';
    webAllocation.dataset.role = 'allocation-web';
    controls.appendChild(createInventoryInput('Web Allocation', webAllocation));

    const botAllocation = createNode('input', 'w-full bg-black border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 outline-none focus:border-szcyan');
    botAllocation.type = 'number';
    botAllocation.min = '0';
    botAllocation.placeholder = 'Unlimited';
    botAllocation.dataset.role = 'allocation-bot';
    controls.appendChild(createInventoryInput('Bot Allocation', botAllocation));
    row.appendChild(controls);

    const footer = createNode('div', 'flex flex-col sm:flex-row sm:items-center gap-3');
    const saveBtn = createNode('button', 'bg-gradient-to-r from-szgreen to-szcyan text-black px-4 py-2 rounded-lg text-sm font-black hover:opacity-90 transition', 'Save Product Settings');
    saveBtn.type = 'button';
    saveBtn.addEventListener('click', () => saveInventoryProduct(saveBtn));
    const statusNode = createNode('div', 'text-xs font-bold min-h-[1rem]');
    statusNode.dataset.role = 'save-status';
    footer.append(saveBtn, statusNode);
    row.appendChild(footer);

    updateInventoryRow(row, product);
    return row;
}

function renderInventoryCatalog(categories) {
    const host = $('inventory-catalog');
    if (!host) return;
    clearNode(host);

    if (!Array.isArray(categories) || !categories.length) {
        const empty = createNode('div', 'bg-panelbg border border-gray-800 rounded-xl px-5 py-10 text-center text-gray-500');
        empty.appendChild(createNode('i', 'fas fa-box-open text-3xl mb-3 block opacity-40'));
        empty.appendChild(createNode('div', 'font-bold', 'No store categories available.'));
        host.appendChild(empty);
        return;
    }

    categories.forEach(category => {
        const card = createNode('section', 'bg-panelbg border border-gray-800 rounded-2xl overflow-hidden');
        const header = createNode('div', 'px-5 py-4 border-b border-gray-800 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3');
        const titleWrap = createNode('div', 'min-w-0');
        titleWrap.appendChild(createNode('div', 'font-black text-white text-sm', category.name || 'Unnamed Category'));
        titleWrap.appendChild(createNode('div', 'text-[11px] text-gray-500 mt-1', `${category.product_count || 0} product(s) • Web visible: ${category.visible_web_count || 0} • Bot visible: ${category.visible_bot_count || 0}`));
        header.appendChild(titleWrap);
        const iconWrap = createNode('div', 'text-szgreen text-sm font-bold flex items-center gap-2');
        iconWrap.appendChild(createNode('i', `fas ${category.icon || 'fa-boxes-stacked'}`));
        iconWrap.appendChild(createNode('span', '', 'Channel Controls'));
        header.appendChild(iconWrap);
        card.appendChild(header);

        const body = createNode('div', 'p-4 space-y-4');
        const products = Array.isArray(category.products) ? category.products : [];
        if (!products.length) {
            body.appendChild(createNode('div', 'text-sm text-gray-500 text-center py-6', 'This category has no products yet.'));
        } else {
            products.forEach(product => body.appendChild(buildInventoryProductRow(category, product)));
        }
        card.appendChild(body);
        host.appendChild(card);
    });
}

async function loadInventoryCatalog(forceRefresh = false) {
    if (_inventoryLoading) return;
    if (_inventoryLoaded && !forceRefresh) return;

    const loader = $('inventory-loading');
    const status = $('inventory-status');
    if (loader) loader.classList.remove('hidden');
    setInlineStatus(status, forceRefresh ? 'Refreshing inventory...' : 'Loading inventory...', false);
    _inventoryLoading = true;

    try {
        const data = await fetchJsonOrThrow('/api/store/admin/catalog');
        renderInventoryCatalog(data.categories || []);
        _inventoryLoaded = true;
        setInlineStatus(status, `Loaded ${Array.isArray(data.categories) ? data.categories.length : 0} categories.`, false);
    } catch (error) {
        setInlineStatus(status, error.message || 'Failed to load inventory.', true);
        showToast(error.message || 'Failed to load inventory.', 'error');
    } finally {
        _inventoryLoading = false;
        if (loader) loader.classList.add('hidden');
    }
}

async function saveInventoryProduct(button) {
    const row = button?.closest('[data-product-row="true"]');
    if (!row) return;

    const statusNode = row.querySelector('[data-role="save-status"]');
    const originalLabel = button.dataset.label || button.textContent.trim() || 'Save Product Settings';
    button.dataset.label = originalLabel;
    button.disabled = true;
    setButtonContent(button, '', 'fa-spinner fa-spin');
    setInlineStatus(statusNode, 'Saving channel settings...', false);

    const form = new FormData();
    form.append('cat_id', row.dataset.catId || '');
    form.append('stock_key', row.dataset.stockKey || '');
    form.append('is_visible_web', row.querySelector('[data-role="is-visible-web"]')?.checked ? 'true' : 'false');
    form.append('is_visible_bot', row.querySelector('[data-role="is-visible-bot"]')?.checked ? 'true' : 'false');
    form.append('allocation_web', row.querySelector('[data-role="allocation-web"]')?.value.trim() || '');
    form.append('allocation_bot', row.querySelector('[data-role="allocation-bot"]')?.value.trim() || '');

    try {
        const data = await fetchJsonOrThrow('/api/store/admin/catalog/product-channel', { method: 'POST', body: form });
        if (data.product) updateInventoryRow(row, data.product);
        setInlineStatus(statusNode, data.msg || 'Saved.', false);
        showToast(data.msg || 'Product settings updated.');
    } catch (error) {
        setInlineStatus(statusNode, error.message || 'Failed to save product settings.', true);
        showToast(error.message || 'Failed to save product settings.', 'error');
    } finally {
        setButtonContent(button, originalLabel);
        button.disabled = false;
    }
}

let _activeTicketId = '';
let _ticketStatusFilter = 'all';
let _adminChatSocket = null;
let _adminChatReconnectTimer = null;
let _adminChatJoinedThread = '';
let _activeAdminThread = null;
let _activeAdminPresence = null;
let _adminChatConnected = false;

function clearSupportNode(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
}

function appendSupportText(parent, tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = text ?? '';
    parent?.appendChild(el);
    return el;
}

function setAdminMessagesLoading() {
    const container = $('tdm-messages');
    if (!container) return;
    clearSupportNode(container);
    const wrap = document.createElement('div');
    wrap.className = 'flex items-center justify-center py-12 text-szcyan';
    const icon = document.createElement('i');
    icon.className = 'fas fa-spinner fa-spin text-3xl';
    wrap.appendChild(icon);
    container.appendChild(wrap);
}

function setAdminReplyStatus(msg = '', type = 'neutral') {
    const statusEl = $('tdm-reply-status');
    if (!statusEl) return;
    clearSupportNode(statusEl);
    if (!msg) return;

    const span = document.createElement('span');
    const icon = document.createElement('i');

    if (type === 'error') {
        span.className = 'text-red-500';
        icon.className = 'fas fa-times-circle mr-1';
    } else if (type === 'success') {
        span.className = 'text-szgreen';
        icon.className = 'fas fa-check-circle mr-1';
    } else {
        span.className = 'text-gray-400';
        icon.className = 'fas fa-spinner fa-spin mr-1';
    }

    span.appendChild(icon);
    span.appendChild(document.createTextNode(msg));
    statusEl.appendChild(span);
}

function adminTicketStatusClasses(status) {
    return {
        open: 'bg-green-900/20 text-green-400 border border-green-900/30',
        in_progress: 'bg-yellow-900/20 text-yellow-400 border border-yellow-900/30',
        closed: 'bg-red-900/20 text-red-400 border border-red-900/30',
    }[status] || 'bg-green-900/20 text-green-400 border border-green-900/30';
}

function buildAdminStatusBadge(status) {
    const badge = document.createElement('span');
    badge.className = `px-2 py-0.5 rounded text-[10px] font-bold uppercase ${adminTicketStatusClasses(status)}`;
    badge.textContent = String(status || 'open').replace('_', ' ');
    return badge;
}

function buildAdminMessageNode(message) {
    const isAdmin = message.sender === 'admin';
    const wrap = document.createElement('div');
    wrap.className = `${isAdmin ? 'ml-8 bg-szgreen/10 border-szgreen/20' : 'mr-8 bg-szcyan/10 border-szcyan/20'} border rounded-xl p-3`;
    wrap.dataset.messageId = message.message_id || '';

    const header = document.createElement('div');
    header.className = 'flex items-center justify-between gap-3 mb-1.5';
    wrap.appendChild(header);

    const name = document.createElement('span');
    name.className = `text-xs font-black ${isAdmin ? 'text-szgreen' : 'text-szcyan'}`;
    name.textContent = message.name || (isAdmin ? 'Support Team' : 'Customer');
    if (isAdmin) {
        const icon = document.createElement('i');
        icon.className = 'fas fa-shield-alt ml-1 text-[10px]';
        name.appendChild(icon);
    }
    header.appendChild(name);
    appendSupportText(header, 'span', 'text-[10px] text-gray-600 shrink-0', message.time || '');

    const body = document.createElement('p');
    body.className = 'text-sm text-gray-200 whitespace-pre-wrap leading-relaxed';
    body.textContent = message.message || '';
    wrap.appendChild(body);

    return wrap;
}

function renderAdminTicketMessages(messages) {
    const container = $('tdm-messages');
    if (!container) return;
    clearSupportNode(container);

    if (!messages.length) {
        appendSupportText(container, 'p', 'text-center text-gray-600 py-10 font-bold', 'No messages yet.');
        return;
    }

    messages.forEach(message => container.appendChild(buildAdminMessageNode(message)));
    container.scrollTop = container.scrollHeight;
}

function appendAdminIncomingMessage(message) {
    const container = $('tdm-messages');
    if (!container) return;
    const duplicate = Array.from(container.children).some(node => node.dataset?.messageId === message.message_id);
    if (duplicate) return;
    container.appendChild(buildAdminMessageNode(message));
    container.scrollTop = container.scrollHeight;
}

function adminChatSocketUrl() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/store-chat?role=admin`;
}

function sendAdminChatAction(payload) {
    if (!_adminChatSocket || _adminChatSocket.readyState !== WebSocket.OPEN) return false;
    _adminChatSocket.send(JSON.stringify(payload));
    return true;
}

function joinActiveAdminThread() {
    if (!_activeTicketId || _adminChatSocket?.readyState !== WebSocket.OPEN) return;
    _adminChatJoinedThread = _activeTicketId;
    sendAdminChatAction({ action: 'join_room', thread_id: _activeTicketId });
}

function scheduleAdminChatReconnect() {
    if (_adminChatReconnectTimer || !_activeTicketId) return;
    _adminChatReconnectTimer = window.setTimeout(() => {
        _adminChatReconnectTimer = null;
        ensureAdminChatSocket();
    }, 1500);
}

function findAdminTicketRow(ticketId) {
    return Array.from(document.querySelectorAll('.ticket-row')).find(row => {
        const firstCell = row.querySelector('td');
        return (firstCell?.textContent || '').replace(/^#/, '').trim() === ticketId;
    });
}

function updateAdminTicketRow(thread) {
    if (!thread?.ticket_id) return;
    const row = findAdminTicketRow(thread.ticket_id);
    if (!row) return;

    row.dataset.status = thread.status || 'open';
    const cells = row.querySelectorAll('td');
    if (cells[3]) {
        clearSupportNode(cells[3]);
        cells[3].appendChild(buildAdminStatusBadge(thread.status));
    }
    if (cells[4]) cells[4].textContent = String(Number(thread.message_count || 0));
    if (cells[5]) cells[5].textContent = thread.last_message_at || thread.created_at || '';
}

function renderActiveAdminMeta() {
    if (!_activeAdminThread) {
        setText('tdm-customer-info', '');
        return;
    }

    const parts = [];
    if (_activeAdminThread.name) parts.push(_activeAdminThread.name);
    if (_activeAdminThread.email) parts.push(_activeAdminThread.email);
    setText('tdm-customer-info', parts.join(' · '));
}

function renderAdminLiveStatus() {
    const host = $('tdm-live-status');
    if (!host) return;

    if (!_activeTicketId) {
        clearSupportNode(host);
        return;
    }

    let msg = 'Connecting to live chat...';
    let textClass = 'text-gray-500';
    let iconClass = 'fas fa-circle-notch fa-spin mr-1';

    if (_adminChatConnected) {
        if (_activeAdminPresence?.customer_online) {
            msg = 'Customer is online';
            textClass = 'text-szgreen';
            iconClass = 'fas fa-circle mr-1';
        } else {
            msg = 'Merchant channel connected';
            iconClass = 'far fa-clock mr-1';
        }
    }

    setAdminReplyStatus();
    clearSupportNode(host);
    const span = document.createElement('span');
    span.className = textClass;
    const icon = document.createElement('i');
    icon.className = iconClass;
    span.appendChild(icon);
    span.appendChild(document.createTextNode(msg));
    host.appendChild(span);
}

function applyAdminThreadState(thread) {
    if (!thread) return;
    _activeAdminThread = thread;
    if (_activeTicketId && thread.ticket_id === _activeTicketId) {
        setText("tdm-ticket-id", "#" + (thread.ticket_id || ""));
        setText("tdm-subject", thread.subject || "");
        if ($("tdm-status-select")) $("tdm-status-select").value = thread.status || "open";
        renderActiveAdminMeta();
        renderAdminLiveStatus();
    }
    updateAdminTicketRow(thread);
}

function applyAdminPresence(threadId, presence) {
    if (threadId !== _activeTicketId) return;
    _activeAdminPresence = presence || null;
    renderActiveAdminMeta();
    renderAdminLiveStatus();
}

function handleAdminChatSocketMessage(event) {
    let payload = null;
    try {
        payload = JSON.parse(event.data);
    } catch {
        return;
    }

    if (payload.event === 'system:connected') {
        _adminChatConnected = true;
        renderAdminLiveStatus();
        joinActiveAdminThread();
        return;
    }

    if (payload.event === 'system:joined') {
        if (payload.thread) applyAdminThreadState(payload.thread);
        if (payload.thread_id === _activeTicketId) {
            sendAdminChatAction({ action: 'mark_read', thread_id: _activeTicketId });
        }
        return;
    }

    if (payload.event === 'message:new') {
        if (payload.thread) applyAdminThreadState(payload.thread);
        if (payload.thread_id === _activeTicketId && payload.message) {
            appendAdminIncomingMessage(payload.message);
            if (payload.message.sender !== 'admin') {
                sendAdminChatAction({ action: 'mark_read', thread_id: payload.thread_id });
            }
        }
        return;
    }

    if (payload.event === 'message:read') {
        if (payload.thread) applyAdminThreadState(payload.thread);
        return;
    }

    if (payload.event === 'thread:status_changed') {
        if (payload.thread) applyAdminThreadState(payload.thread);
        return;
    }

    if (payload.event === 'presence') {
        applyAdminPresence(payload.thread_id, payload.presence);
        return;
    }

    if (payload.event === 'error' && payload.msg) {
        setAdminReplyStatus(payload.msg, 'error');
        showToast(payload.msg, 'error');
    }
}

function ensureAdminChatSocket() {
    if (_adminChatSocket && (_adminChatSocket.readyState === WebSocket.OPEN || _adminChatSocket.readyState === WebSocket.CONNECTING)) {
        return;
    }

    _adminChatSocket = new WebSocket(adminChatSocketUrl());
    _adminChatSocket.addEventListener('open', () => {
        _adminChatConnected = true;
        renderAdminLiveStatus();
        joinActiveAdminThread();
    });
    _adminChatSocket.addEventListener('message', handleAdminChatSocketMessage);
    _adminChatSocket.addEventListener('close', () => {
        _adminChatConnected = false;
        _adminChatJoinedThread = '';
        _activeAdminPresence = null;
        renderAdminLiveStatus();
        scheduleAdminChatReconnect();
    });
}

async function openTicketModal(ticketId) {
    const previousTicketId = _activeTicketId;
    if (previousTicketId && previousTicketId !== ticketId && _adminChatSocket?.readyState === WebSocket.OPEN) {
        sendAdminChatAction({ action: "leave_room", thread_id: previousTicketId });
    }

    _activeTicketId = ticketId;
    _activeAdminPresence = null;
    renderAdminLiveStatus();
    const modal = $("ticket-detail-modal");
    if (!modal) return;
    modal.classList.remove("hidden");
    if ($("tdm-reply-input")) $("tdm-reply-input").value = "";
    setAdminReplyStatus();
    setAdminMessagesLoading();

    try {
        const url = `/api/store/admin/tickets/history?ticket_id=${encodeURIComponent(ticketId)}&page=1&limit=50`;
        const d = await (await fetch(url, { cache: "no-store", credentials: "same-origin" })).json();
        if (!d.success) {
            showToast(d.msg || "Failed to load ticket!", "error");
            closeTicketModal();
            return;
        }
        applyAdminThreadState(d.thread || { ticket_id: ticketId });
        renderAdminTicketMessages(d.messages || []);
        ensureAdminChatSocket();
        if (_adminChatSocket?.readyState === WebSocket.OPEN) {
            joinActiveAdminThread();
            sendAdminChatAction({ action: "mark_read", thread_id: ticketId });
        }
    } catch {
        showToast("Failed to load ticket!", "error");
        closeTicketModal();
    }
}

function closeTicketModal() {
    if (_activeTicketId && _adminChatSocket?.readyState === WebSocket.OPEN) {
        sendAdminChatAction({ action: "leave_room", thread_id: _activeTicketId });
    }
    $("ticket-detail-modal")?.classList.add("hidden");
    _activeTicketId = "";
    _adminChatJoinedThread = "";
    _activeAdminThread = null;
    _activeAdminPresence = null;
    renderAdminLiveStatus();
    if ($("tdm-reply-input")) $("tdm-reply-input").value = "";
    setAdminReplyStatus();
}
$('ticket-detail-modal')?.addEventListener('click', e => { if (e.target === $('ticket-detail-modal')) closeTicketModal(); });

async function adminSendTicketReply() {
    if (!_activeTicketId) return;
    const input = $('tdm-reply-input');
    const msg = input?.value.trim();
    if (!msg) {
        showToast('Reply cannot be empty.', 'error');
        return;
    }

    setAdminReplyStatus('Sending...', 'pending');
    ensureAdminChatSocket();
    if (sendAdminChatAction({ action: 'send_message', thread_id: _activeTicketId, message: msg })) {
        if (input) input.value = '';
        setAdminReplyStatus();
        return;
    }

    const fd = new FormData();
    fd.append('ticket_id', _activeTicketId);
    fd.append('message', msg);

    try {
        const d = await (await fetch('/api/store/admin/tickets/reply', {
            method: 'POST',
            body: fd,
            credentials: 'same-origin',
        })).json();
        if (!d.success) {
            setAdminReplyStatus(d.msg || 'Error sending reply!', 'error');
            showToast(d.msg || 'Error sending reply!', 'error');
            return;
        }
        if (input) input.value = '';
        setAdminReplyStatus();
        if (d.thread) applyAdminThreadState(d.thread);
        if (d.message) appendAdminIncomingMessage(d.message);
        showToast(d.msg || 'Reply sent!');
    } catch {
        setAdminReplyStatus('Error sending reply!', 'error');
    }
}

async function adminChangeTicketStatus() {
    if (!_activeTicketId) return;
    const status = $('tdm-status-select')?.value || 'open';
    const fd = new FormData();
    fd.append('ticket_id', _activeTicketId);
    fd.append('status', status);
    try {
        const d = await (await fetch('/api/store/admin/tickets/change-status', {
            method: 'POST',
            body: fd,
            credentials: 'same-origin',
        })).json();
        if (!d.success) {
            showToast(d.msg || 'Error!', 'error');
            return;
        }
        if (d.thread) applyAdminThreadState(d.thread);
        showToast(d.msg || 'Status updated.');
    } catch {
        showToast('Error!', 'error');
    }
}
function filterTicketsByStatus(status) {
    _ticketStatusFilter = status;
    // Update button styles
    document.querySelectorAll('.ticket-filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    const active = $('tf-' + status);
    if (active) active.classList.add('active');
    // Filter rows
    document.querySelectorAll('.ticket-row').forEach(row => {
        const rowStatus = row.dataset.status || '';
        const searchQ   = $('search-tickets')?.value.toLowerCase() || '';
        const matchSearch = row.dataset.search.includes(searchQ);
        const matchStatus = status === 'all' || rowStatus === status;
        row.style.display = (matchSearch && matchStatus) ? '' : 'none';
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const hashTab = (location.hash || '').replace('#', '').trim();
    const allowed = ['customers', 'orders', 'inventory', 'support'];
    const saved = localStorage.getItem(ADMIN_TAB_KEY) || 'customers';
    const tab = allowed.includes(hashTab) ? hashTab : (allowed.includes(saved) ? saved : 'customers');
    switchMainTab(tab);

    $('confirm-modal')?.addEventListener('click', e => {
        if (e.target === $('confirm-modal')) closeConfirmModal(false);
    });
});

function setFormStatus(id, msg, isError) {
    const el = $(id);
    if (!el) return;
    setInlineStatus(el, msg, !!isError);
}
</script>

<div id="confirm-modal" class="fixed inset-0 bg-black/80 hidden z-[80] items-center justify-center p-4">
    <div class="w-full max-w-md bg-panelbg border border-gray-800 rounded-2xl p-5">
        <h3 class="text-white font-black text-lg mb-2" id="confirm-title">Confirm Action</h3>
        <p class="text-gray-300 text-sm mb-4" id="confirm-message">Are you sure?</p>
        <div class="flex justify-end gap-2">
            <button onclick='closeConfirmModal(false)' class="px-4 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 transition text-sm font-bold">Cancel</button>
            <button onclick='closeConfirmModal(true)' id="confirm-ok-btn" class="px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-500 transition text-sm font-bold">Confirm</button>
        </div>
    </div>
</div>

</body>
</html>























