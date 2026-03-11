const BOOT = window.STORE_ADMIN_BOOTSTRAP || {};
const STATE = {
  tab: 'operations',
  workspace: null,
  catalog: [],
  customers: [],
  staff: [],
  methods: [],
  logs: [],
  storefront: null,
  productOptions: [],
  selected: null,
  chat: { threadId: '', readOnly: false, socket: null, connected: false, messages: [], presence: null }
};
const ORDER_STATES = ['preorder', 'pending_manual', 'scheduled', 'processing', 'completed', 'cancelled'];
const ORDER_LABELS = { preorder: 'Preorder', pending_manual: 'Pending Manual', scheduled: 'Scheduled', processing: 'Processing', completed: 'Completed', cancelled: 'Cancelled' };

const $ = (s, p = document) => p.querySelector(s);
const $$ = (s, p = document) => Array.from(p.querySelectorAll(s));
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] || c));
const money = (v, c) => `${Number(v || 0).toFixed(2)} ${String(c || '').toUpperCase()}`;
const tone = (s) => ({ completed: 'emerald', open: 'emerald', active: 'emerald', processing: 'yellow', scheduled: 'yellow', pending_manual: 'yellow', pending: 'yellow', preorder: 'yellow', in_progress: 'yellow', rejected: 'red', cancelled: 'red', closed: 'red' }[String(s || '').toLowerCase()] || 'cyan');
const pill = (text, color = 'gray') => `<span class="rounded-full border px-2 py-1 text-[10px] font-black ${color === 'emerald' ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200' : color === 'yellow' ? 'border-yellow-400/20 bg-yellow-400/10 text-yellow-200' : color === 'red' ? 'border-red-400/20 bg-red-400/10 text-red-200' : 'border-cyan-400/20 bg-cyan-400/10 text-cyan-100'}">${esc(text)}</span>`;

function toast(msg, kind = 'info') {
  const host = $('#store-admin-toast');
  if (!host || !msg) return;
  const div = document.createElement('div');
  div.className = `rounded-2xl border px-4 py-3 text-sm font-bold shadow-[0_20px_60px_rgba(0,0,0,0.35)] backdrop-blur ${kind === 'error' ? 'border-red-400/30 bg-red-400/10 text-red-200' : kind === 'success' ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : 'border-cyan-400/30 bg-cyan-400/10 text-cyan-100'}`;
  div.textContent = msg;
  host.appendChild(div);
  setTimeout(() => div.remove(), 2600);
}

async function parseRes(res) {
  let data = {};
  try { data = await res.json(); } catch { data = { success: false, msg: 'Unexpected server response.' }; }
  if (res.status === 401) {
    location.href = '/staff-login';
    throw new Error('Unauthorized');
  }
  if (!res.ok || data.success === false) throw new Error(data.msg || 'Request failed.');
  return data;
}

async function getJSON(url) {
  return parseRes(await fetch(url, { credentials: 'same-origin', cache: 'no-store' }));
}

async function postForm(url, payload) {
  const fd = new FormData();
  Object.entries(payload || {}).forEach(([k, v]) => { if (v != null) fd.append(k, v); });
  return parseRes(await fetch(url, { method: 'POST', credentials: 'same-origin', body: fd }));
}

async function postJSON(url, payload) {
  return parseRes(await fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload || {}) }));
}

function emptyCard(msg) {
  return `<div class="rounded-2xl border border-dashed border-white/10 bg-white/5 px-4 py-8 text-center text-sm font-bold text-gray-500">${esc(msg)}</div>`;
}

function setTab(name) {
  STATE.tab = name;
  $$('.store-admin-tab-btn').forEach((btn) => {
    const active = btn.dataset.adminTab === name;
    btn.className = `store-admin-tab-btn w-full rounded-2xl border px-4 py-3 text-left text-sm font-black transition ${active ? 'border-emerald-400/35 bg-emerald-400/10 text-emerald-200' : 'border-white/10 bg-white/5 text-gray-200 hover:border-white/20'}`;
  });
  $$('.store-admin-tab-panel').forEach((panel) => panel.classList.toggle('hidden', panel.id !== `store-admin-tab-${name}`));
  if (name === 'operations') loadWorkspace();
  if (name === 'inventory') loadInventory();
  if (name === 'customers') loadCustomers();
  if (name === 'storefront') loadStorefront();
  if (name === 'staff') loadStaff();
  if (name === 'wallet-config') loadWalletConfig();
}

async function logoutStaff() {
  try { await fetch('/api/store/logout', { method: 'POST', credentials: 'same-origin' }); } finally { location.href = '/staff-login'; }
}

function statCard(label, value, note, color) {
  const klass = color === 'yellow' ? 'border-yellow-400/20 bg-yellow-400/8' : color === 'emerald' ? 'border-emerald-400/20 bg-emerald-400/8' : 'border-cyan-400/20 bg-cyan-400/8';
  return `<div class="rounded-[28px] border ${klass} p-5"><p class="text-xs font-black uppercase tracking-[0.25em] text-gray-400">${esc(label)}</p><p class="mt-3 text-4xl font-black text-white">${esc(String(value))}</p><p class="mt-2 text-sm text-gray-400">${esc(note)}</p></div>`;
}

async function loadWorkspace() {
  try {
    STATE.workspace = await getJSON('/api/store/admin/workspace');
    const orders = STATE.workspace.orders || [];
    const tickets = STATE.workspace.tickets || [];
    const wallet = STATE.workspace.wallet_requests || [];
    $('#ops-stats').innerHTML = [
      statCard('Open Orders', orders.filter((o) => !['completed', 'cancelled'].includes(String(o.delivery_state || ''))).length, 'Pending operational workload', 'yellow'),
      statCard('Support Threads', tickets.length, 'Ticket conversations in unified chat', 'cyan'),
      statCard('Wallet Queue', wallet.filter((x) => String(x.status) === 'pending').length, 'Pending deposits and withdrawals', 'yellow'),
      statCard('Completed Orders', orders.filter((o) => String(o.delivery_state) === 'completed').length, 'Finished fulfillment', 'emerald'),
    ].join('');
    renderOrders();
    renderTickets();
    renderWalletQueue();
    renderDetail();
  } catch (err) {
    toast(err.message, 'error');
  }
}

function renderOrders() {
  const orders = STATE.workspace?.orders || [];
  $('#ops-orders-board').innerHTML = ORDER_STATES.map((state) => {
    const items = orders.filter((o) => String(o.delivery_state || '') === state);
    const cards = items.length ? items.map((o) => `<button class="order-card w-full rounded-2xl border border-white/10 bg-white/5 p-4 text-left transition hover:border-emerald-400/30 hover:bg-white/10" data-id="${esc(o.order_id)}"><div class="flex items-start justify-between gap-3"><div><p class="text-xs font-black uppercase tracking-[0.15em] text-gray-500">#${esc(o.order_id)}</p><h4 class="mt-1 text-sm font-black text-white">${esc(o.product_name || o.category)}</h4></div>${pill(String(o.delivery_state || '').replace(/_/g, ' '), tone(o.delivery_state))}</div><p class="mt-2 text-xs text-gray-400">${esc(o.name)} - ${esc(o.email)}</p><p class="mt-2 text-xs text-gray-500">${esc(money(o.price, o.currency))}</p><p class="mt-3 text-[11px] text-gray-500">${o.claimed_by_name ? `Claimed by ${esc(o.claimed_by_name)}` : 'Unclaimed'}</p></button>`).join('') : emptyCard('No items');
    return `<div class="rounded-[28px] border border-white/10 bg-black/35 p-4"><div class="mb-4 flex items-center justify-between gap-3"><h3 class="text-sm font-black uppercase tracking-[0.2em] text-white">${esc(ORDER_LABELS[state])}</h3><span class="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-black text-gray-300">${items.length}</span></div><div class="space-y-3">${cards}</div></div>`;
  }).join('');
  $$('.order-card', $('#ops-orders-board')).forEach((btn) => btn.addEventListener('click', () => { STATE.selected = { kind: 'order', id: btn.dataset.id }; renderDetail(); }));
}

function renderTickets() {
  const tickets = STATE.workspace?.tickets || [];
  const host = $('#ops-ticket-list');
  host.innerHTML = tickets.length ? tickets.map((t) => `<button class="ticket-card w-full rounded-2xl border border-white/10 bg-white/5 p-4 text-left transition hover:border-cyan-400/30 hover:bg-white/10" data-id="${esc(t.thread_id || t.ticket_id)}"><div class="flex items-start justify-between gap-3"><div><h4 class="text-sm font-black text-white">${esc(t.subject || 'Support Ticket')}</h4><p class="mt-1 text-xs text-gray-400">${esc(t.name || 'Customer')} - ${esc(t.email || '')}</p></div>${pill(t.status, tone(t.status))}</div><p class="mt-3 text-xs text-gray-500">${esc(t.last_message_preview || 'No messages yet.')}</p></button>`).join('') : emptyCard('No ticket threads found.');
  $$('.ticket-card', host).forEach((btn) => btn.addEventListener('click', () => { STATE.selected = { kind: 'ticket', id: btn.dataset.id }; renderDetail(); }));
}

function renderWalletQueue() {
  const items = STATE.workspace?.wallet_requests || [];
  const host = $('#ops-wallet-list');
  host.innerHTML = items.length ? items.map((w) => `<button class="wallet-card w-full rounded-2xl border border-white/10 bg-white/5 p-4 text-left transition hover:border-yellow-400/30 hover:bg-white/10" data-id="${esc(w.transaction_id)}"><div class="flex items-start justify-between gap-3"><div><h4 class="text-sm font-black text-white">${esc(String(w.type || '').toUpperCase())} - ${esc(w.payment_method_name)}</h4><p class="mt-1 text-xs text-gray-400">${esc(w.currency)} - ${esc(money(w.requested_amount, w.currency))}</p></div>${pill(w.status, tone(w.status))}</div><p class="mt-3 text-xs text-gray-500">${w.claimed_by_name ? `Claimed by ${esc(w.claimed_by_name)}` : 'Unclaimed'}</p></button>`).join('') : emptyCard('No wallet requests found.');
  $$('.wallet-card', host).forEach((btn) => btn.addEventListener('click', () => { STATE.selected = { kind: 'wallet', id: btn.dataset.id }; renderDetail(); }));
}

function selectedEntity() {
  if (!STATE.selected) return null;
  if (STATE.selected.kind === 'order') return (STATE.workspace?.orders || []).find((o) => String(o.order_id) === String(STATE.selected.id)) || null;
  if (STATE.selected.kind === 'ticket') return (STATE.workspace?.tickets || []).find((t) => String(t.thread_id || t.ticket_id) === String(STATE.selected.id)) || null;
  if (STATE.selected.kind === 'wallet') return (STATE.workspace?.wallet_requests || []).find((w) => String(w.transaction_id) === String(STATE.selected.id)) || null;
  if (STATE.selected.kind === 'spectate') return STATE.selected;
  return null;
}

function infoBox(label, value, color = 'gray') {
  return `<div class="rounded-2xl border px-3 py-3 ${color === 'emerald' ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200' : color === 'yellow' ? 'border-yellow-400/20 bg-yellow-400/10 text-yellow-200' : color === 'red' ? 'border-red-400/20 bg-red-400/10 text-red-200' : 'border-white/10 bg-white/5 text-gray-200'}"><div class="text-[10px] font-black uppercase tracking-[0.2em] text-gray-400">${esc(label)}</div><div class="mt-1 text-sm font-bold text-white">${esc(value || '-')}</div></div>`;
}

function chatShell(readOnly) {
  return `<div class="rounded-3xl border border-white/10 bg-white/5 p-4"><div class="mb-3 flex items-center justify-between gap-3 border-b border-white/10 pb-3"><div><h4 class="text-sm font-black uppercase tracking-[0.2em] text-white">Live Chat</h4><p id="staff-chat-presence" class="mt-1 text-xs text-gray-500">Connecting...</p></div>${readOnly ? '<span class="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-cyan-200">Read only</span>' : ''}</div><div id="staff-chat-messages" class="space-y-3 max-h-[22rem] overflow-y-auto pr-1"></div><div class="mt-4 ${readOnly ? 'hidden' : ''}"><textarea id="staff-chat-input" rows="3" placeholder="Send a message to the customer..." class="w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white outline-none focus:border-emerald-400/40"></textarea><div class="mt-3 flex items-center justify-between gap-3"><p id="staff-chat-status" class="text-xs font-bold text-gray-500"></p><button id="staff-chat-send" class="rounded-2xl bg-gradient-to-r from-emerald-300 via-teal-300 to-cyan-300 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-black transition hover:opacity-90">Send</button></div></div></div>`;
}
function renderDetail() {
  const title = $('#ops-detail-title');
  const subtitle = $('#ops-detail-subtitle');
  const kicker = $('#ops-detail-kicker');
  const body = $('#ops-detail-body');
  const entity = selectedEntity();
  if (!entity) {
    kicker.textContent = 'Live detail';
    title.textContent = 'Select an order, ticket, or wallet request';
    subtitle.textContent = 'The active item appears here with actions and chat.';
    body.innerHTML = emptyCard('Nothing selected yet.');
    closeChat();
    return;
  }
  if (STATE.selected.kind === 'order') {
    kicker.textContent = 'Order Workspace';
    title.textContent = `#${entity.order_id} - ${entity.product_name || entity.category}`;
    subtitle.textContent = `${entity.name} - ${entity.email}`;
    body.innerHTML = `<div class="grid gap-3 md:grid-cols-3">${infoBox('State', String(entity.delivery_state || '').replace(/_/g, ' '), tone(entity.delivery_state))}${infoBox('Price', money(entity.price, entity.currency), 'yellow')}${infoBox('Claimed By', entity.claimed_by_name || 'Unclaimed', entity.claimed_by_name ? 'emerald' : 'gray')}</div><div class="grid gap-3 md:grid-cols-2">${infoBox('ETA', entity.estimated_completion_time || 'Not set', 'cyan')}${infoBox('Scheduled', entity.scheduled_time || 'Immediate', 'gray')}</div>${entity.product_description ? `<div class="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-gray-300">${esc(entity.product_description)}</div>` : ''}${entity.requires_id_fulfillment ? `<div class="grid gap-3 md:grid-cols-2">${infoBox('Player ID', entity.player_id || 'Pending', 'cyan')}${infoBox('Player Name', entity.player_name || 'Pending', 'cyan')}</div>` : ''}<div class="flex flex-wrap gap-3"><button id="order-claim" class="rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-emerald-200 transition hover:bg-emerald-400/20">Claim Order</button><button id="order-processing" class="rounded-2xl border border-yellow-400/20 bg-yellow-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-yellow-200 transition hover:bg-yellow-400/20">Move to Processing</button><button id="order-complete" class="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-cyan-100 transition hover:bg-cyan-400/20">Complete Order</button></div>${chatShell(false)}`;
    $('#order-claim')?.addEventListener('click', async () => act(async () => postForm('/api/store/admin/orders/claim', { order_id: entity.order_id }), 'Order claimed.', () => { STATE.selected = { kind: 'order', id: entity.order_id }; }));
    $('#order-processing')?.addEventListener('click', () => act(async () => postForm('/api/store/admin/orders/status', { order_id: entity.order_id, delivery_state: 'processing' }), 'Order moved to processing.', () => { STATE.selected = { kind: 'order', id: entity.order_id }; }));
    $('#order-complete')?.addEventListener('click', () => act(async () => postForm('/api/store/admin/orders/status', { order_id: entity.order_id, delivery_state: 'completed' }), 'Order completed.', () => { STATE.selected = { kind: 'order', id: entity.order_id }; }));
    openChat(entity.thread_id, false);
  } else if (STATE.selected.kind === 'ticket') {
    kicker.textContent = 'Ticket Workspace';
    title.textContent = entity.subject || `Ticket ${entity.thread_id || entity.ticket_id}`;
    subtitle.textContent = `${entity.name || 'Customer'} - ${entity.email || ''}`;
    body.innerHTML = `<div class="grid gap-3 md:grid-cols-3">${infoBox('Status', String(entity.status || '').replace(/_/g, ' '), tone(entity.status))}${infoBox('Messages', String(entity.message_count || 0), 'cyan')}${infoBox('Assigned', entity.assigned_staff_name || 'Unassigned', entity.assigned_staff_name ? 'emerald' : 'gray')}</div><div class="flex flex-wrap gap-3"><button class="ticket-status rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-emerald-200 transition hover:bg-emerald-400/20" data-status="open">Open</button><button class="ticket-status rounded-2xl border border-yellow-400/20 bg-yellow-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-yellow-200 transition hover:bg-yellow-400/20" data-status="in_progress">In Progress</button><button class="ticket-status rounded-2xl border border-red-400/20 bg-red-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-red-200 transition hover:bg-red-400/20" data-status="closed">Close</button></div>${chatShell(false)}`;
    $$('.ticket-status', body).forEach((btn) => btn.addEventListener('click', () => act(async () => postForm('/api/store/admin/tickets/change-status', { ticket_id: entity.thread_id || entity.ticket_id, status: btn.dataset.status }), 'Ticket status updated.', () => { STATE.selected = { kind: 'ticket', id: entity.thread_id || entity.ticket_id }; })));
    openChat(entity.thread_id || entity.ticket_id, false);
  } else if (STATE.selected.kind === 'wallet') {
    kicker.textContent = 'Wallet Workspace';
    title.textContent = `${String(entity.type || '').toUpperCase()} - ${entity.payment_method_name}`;
    subtitle.textContent = `${entity.transaction_id} - ${entity.currency}`;
    body.innerHTML = `<div class="grid gap-3 md:grid-cols-3">${infoBox('Status', entity.status, tone(entity.status))}${infoBox('Requested', money(entity.requested_amount, entity.currency), 'yellow')}${infoBox('Claimed By', entity.claimed_by_name || 'Unclaimed', entity.claimed_by_name ? 'emerald' : 'gray')}</div><div class="grid gap-3 md:grid-cols-2">${infoBox('Payment Method', entity.payment_method_name || '-', 'cyan')}${infoBox('Fee Snapshot', `${entity.fee_snapshot?.mode || 'fixed'} - ${entity.fee_snapshot?.value ?? 0}`, 'gray')}</div><div class="rounded-2xl border border-white/10 bg-white/5 p-4"><label class="mb-2 block text-xs font-black uppercase tracking-[0.2em] text-gray-400">Actual amount received / sent</label><input id="wallet-amount" type="number" step="0.01" min="0" value="${esc(String(entity.actual_received_amount || entity.requested_amount || 0))}" class="w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white outline-none focus:border-emerald-400/40"><p class="mt-2 text-xs text-gray-500">Deposits credit actual minus fee. Withdrawals debit the requested amount and keep this field for audit.</p></div><div class="flex flex-wrap gap-3"><button id="wallet-claim" class="rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-emerald-200 transition hover:bg-emerald-400/20">Claim Request</button><button id="wallet-confirm" class="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-cyan-100 transition hover:bg-cyan-400/20">Confirm Transaction</button><button id="wallet-reject" class="rounded-2xl border border-red-400/20 bg-red-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-red-200 transition hover:bg-red-400/20">Reject</button></div>${chatShell(false)}`;
    $('#wallet-claim')?.addEventListener('click', () => act(async () => postForm('/api/store/admin/wallet-requests/claim', { transaction_id: entity.transaction_id }), 'Wallet request claimed.', async () => { STATE.selected = { kind: 'wallet', id: entity.transaction_id }; await loadWalletConfig(); }));
    $('#wallet-confirm')?.addEventListener('click', () => {
      const amt = Number($('#wallet-amount')?.value || 0);
      if (!amt || amt <= 0) { toast('Enter the exact actual amount first.', 'error'); return; }
      act(async () => postForm('/api/store/admin/wallet-requests/confirm', { transaction_id: entity.transaction_id, actual_received_amount: amt }), 'Wallet request confirmed.', async () => { STATE.selected = { kind: 'wallet', id: entity.transaction_id }; await loadWalletConfig(); });
    });
    $('#wallet-reject')?.addEventListener('click', () => { if (confirm('Reject this wallet request?')) act(async () => postForm('/api/store/admin/wallet-requests/reject', { transaction_id: entity.transaction_id }), 'Wallet request rejected.', async () => { STATE.selected = { kind: 'wallet', id: entity.transaction_id }; await loadWalletConfig(); }); });
    openChat(entity.thread_id, false);
  } else if (STATE.selected.kind === 'spectate') {
    kicker.textContent = 'Spectate Chat';
    title.textContent = entity.title || 'Chat Spectate';
    subtitle.textContent = entity.subtitle || 'Read-only live admin view.';
    body.innerHTML = `<div class="grid gap-3 md:grid-cols-2">${infoBox('Thread', entity.threadId || '-', 'cyan')}${infoBox('Mode', 'Admin Spectate', 'yellow')}</div><div class="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">This is a read-only live view. You can monitor the conversation and watch incoming messages in real time.</div>${chatShell(true)}`;
    openChat(entity.threadId, true);
  }
  bindChatCompose();
}

async function act(fn, successMsg, after) {
  try {
    await fn();
    toast(successMsg, 'success');
    await loadWorkspace();
    if (after) await after();
    renderDetail();
  } catch (err) {
    toast(err.message, 'error');
  }
}

function chatUrl(readOnly) {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  return readOnly && BOOT.isStaffAdmin ? `${scheme}://${location.host}/ws/store-chat?role=spectator&spectate=1` : `${scheme}://${location.host}/ws/store-chat?role=${encodeURIComponent(BOOT.staffRole || 'employee')}`;
}

function closeChat() {
  if (STATE.chat.socket) { try { STATE.chat.socket.close(); } catch {} }
  STATE.chat = { threadId: '', readOnly: false, socket: null, connected: false, messages: [], presence: null };
}

function renderPresence() {
  const host = $('#staff-chat-presence');
  if (!host) return;
  if (!STATE.chat.threadId) { host.textContent = 'No active thread.'; return; }
  if (!STATE.chat.connected) { host.textContent = 'Connecting to live chat...'; return; }
  const p = STATE.chat.presence || {};
  const bits = [];
  if (p.customer_online) bits.push('Customer online');
  if (p.staff_online) bits.push('Staff online');
  if (p.admin_online) bits.push('Admin online');
  if (p.spectator_online) bits.push('Spectator watching');
  host.textContent = bits.length ? bits.join(' - ') : 'Live chat connected.';
}

function renderChatMessages() {
  const host = $('#staff-chat-messages');
  if (!host) return;
  if (!STATE.chat.messages.length) { host.innerHTML = emptyCard('No chat messages yet.'); return; }
  host.innerHTML = STATE.chat.messages.map((m) => {
    const sender = String(m.sender || '').toLowerCase();
    const system = Boolean(m.is_system) || sender === 'system';
    const customer = sender === 'customer';
    const cls = system ? 'border-white/10 bg-white/5 text-gray-300' : customer ? 'ml-6 border-cyan-400/20 bg-cyan-400/10 text-cyan-50' : 'mr-6 border-emerald-400/20 bg-emerald-400/10 text-emerald-50';
    const name = system ? 'System' : (m.name || (customer ? 'Customer' : 'Staff'));
    return `<div class="rounded-2xl border p-3 ${cls}"><div class="mb-1 flex items-center justify-between gap-3"><span class="text-xs font-black uppercase tracking-[0.2em] ${system ? 'text-gray-300' : customer ? 'text-cyan-200' : 'text-emerald-200'}">${esc(name)}</span><span class="text-[10px] text-gray-500">${esc(m.time || '')}</span></div><div class="whitespace-pre-wrap text-sm">${esc(m.message || '')}</div></div>`;
  }).join('');
  host.scrollTop = host.scrollHeight;
}

function sendChat(payload) {
  if (!STATE.chat.socket || STATE.chat.socket.readyState !== WebSocket.OPEN) return false;
  STATE.chat.socket.send(JSON.stringify(payload));
  return true;
}

function ensureChatSocket(readOnly) {
  if (STATE.chat.socket && (STATE.chat.socket.readyState === WebSocket.OPEN || STATE.chat.socket.readyState === WebSocket.CONNECTING)) return;
  STATE.chat.socket = new WebSocket(chatUrl(readOnly));
  STATE.chat.socket.addEventListener('open', () => {
    STATE.chat.connected = true;
    renderPresence();
    if (STATE.chat.threadId) sendChat({ action: 'join_room', thread_id: STATE.chat.threadId });
  });
  STATE.chat.socket.addEventListener('message', (event) => {
    let p = {};
    try { p = JSON.parse(event.data); } catch { return; }
    if (p.thread_id && p.thread_id !== STATE.chat.threadId) return;
    if (p.event === 'presence:update') { STATE.chat.presence = p.presence || null; renderPresence(); return; }
    if (p.event === 'message:new' && p.message) { STATE.chat.messages = [...STATE.chat.messages, p.message]; renderChatMessages(); if (!STATE.chat.readOnly && String(p.message.sender || '').toLowerCase() === 'customer') sendChat({ action: 'mark_read', thread_id: STATE.chat.threadId }); return; }
    if (p.event === 'system:joined') { renderPresence(); sendChat({ action: 'mark_read', thread_id: STATE.chat.threadId }); return; }
    if (p.event === 'error' && p.msg) toast(p.msg, 'error');
  });
  STATE.chat.socket.addEventListener('close', () => { STATE.chat.connected = false; renderPresence(); });
}

async function openChat(threadId, readOnly) {
  STATE.chat.threadId = threadId;
  STATE.chat.readOnly = readOnly;
  STATE.chat.messages = [];
  STATE.chat.presence = null;
  renderPresence();
  renderChatMessages();
  try {
    const data = await getJSON(`/api/store/admin/chat/history?thread_id=${encodeURIComponent(threadId)}`);
    STATE.chat.messages = data.messages || [];
    renderChatMessages();
    ensureChatSocket(readOnly);
    if (STATE.chat.socket?.readyState === WebSocket.OPEN) sendChat({ action: 'join_room', thread_id: threadId });
  } catch (err) { toast(err.message, 'error'); }
}

function bindChatCompose() {
  $('#staff-chat-send')?.addEventListener('click', async () => {
    const input = $('#staff-chat-input');
    const status = $('#staff-chat-status');
    const msg = input?.value.trim();
    if (!msg) { toast('Type a message first.', 'error'); return; }
    if (status) status.textContent = 'Sending...';
    if (sendChat({ action: 'send_message', thread_id: STATE.chat.threadId, message: msg })) { input.value = ''; if (status) status.textContent = ''; return; }
    try {
      await postForm('/api/store/admin/chat/reply', { thread_id: STATE.chat.threadId, message: msg });
      input.value = '';
      if (status) status.textContent = '';
      const data = await getJSON(`/api/store/admin/chat/history?thread_id=${encodeURIComponent(STATE.chat.threadId)}`);
      STATE.chat.messages = data.messages || [];
      renderChatMessages();
    } catch (err) { if (status) status.textContent = err.message || 'Unable to send.'; toast(err.message, 'error'); }
  });
}

async function loadInventory() {
  try { const data = await getJSON('/api/store/admin/catalog'); STATE.catalog = data.categories || []; renderInventory(); } catch (err) { toast(err.message, 'error'); }
}

function renderInventory() {
  const host = $('#inventory-list');
  if (!host) return;
  if (!STATE.catalog.length) { host.innerHTML = emptyCard('No catalog categories found.'); return; }
  host.innerHTML = STATE.catalog.map((c) => `<section class="rounded-[28px] border border-white/10 bg-white/5 p-5"><div class="mb-4 flex flex-col gap-3 border-b border-white/10 pb-4 lg:flex-row lg:items-start lg:justify-between"><div><h3 class="text-2xl font-black text-white">${esc(c.name)}</h3><p class="mt-1 text-sm text-gray-400">${esc(c.description || 'No category description yet.')}</p><p class="mt-1 text-xs text-gray-500">ETA: ${esc(c.estimated_completion_time || 'Not set')} - ${c.is_active ? 'Active' : 'Temporarily Disabled'}</p></div><form class="category-meta grid gap-3 rounded-2xl border border-white/10 bg-black/35 p-4 lg:min-w-[360px]" data-cat="${esc(c.category_id || c._id)}"><textarea name="description" rows="3" class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-emerald-400/40" placeholder="Category description">${esc(c.description || '')}</textarea><input name="estimated_completion_time" type="text" value="${esc(c.estimated_completion_time || '')}" placeholder="Estimated completion time" class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-emerald-400/40"><label class="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-gray-200"><input name="is_active" type="checkbox" ${c.is_active ? 'checked' : ''} class="h-4 w-4 rounded border-white/20 bg-black/40 accent-emerald-300"> Category active</label><button type="submit" class="rounded-2xl bg-gradient-to-r from-emerald-300 via-teal-300 to-cyan-300 px-4 py-3 text-xs font-black uppercase tracking-[0.2em] text-black transition hover:opacity-90">Save Category Meta</button></form></div><div class="space-y-4">${(c.products || []).map((p) => `<article class="rounded-3xl border border-white/10 bg-black/35 p-4"><div class="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between"><div><h4 class="text-lg font-black text-white">${esc(p.name)}</h4><p class="mt-1 text-xs text-gray-500">${esc(p.stock_key)} - Web stock ${esc(String(p.effective_web_available ?? 0))} - Total stock ${esc(String(p.stock_available ?? 0))}</p></div><div class="flex flex-wrap gap-2 text-xs font-black">${pill(p.is_active ? 'Active' : 'Disabled', p.is_active ? 'emerald' : 'red')}${pill(p.requires_id_fulfillment ? 'ID Fulfillment' : 'Standard Preorder', p.requires_id_fulfillment ? 'yellow' : 'cyan')}</div></div><div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]"><form class="product-meta space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4" data-cat="${esc(c.category_id || c._id)}" data-key="${esc(p.stock_key)}"><textarea name="description" rows="3" class="w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white outline-none focus:border-emerald-400/40" placeholder="Product description">${esc(p.description || '')}</textarea><input name="estimated_completion_time" type="text" value="${esc(p.estimated_completion_time || '')}" placeholder="Estimated completion time" class="w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white outline-none focus:border-emerald-400/40"><label class="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-gray-200"><input name="is_active" type="checkbox" ${p.is_active ? 'checked' : ''} class="h-4 w-4 rounded border-white/20 bg-black/40 accent-emerald-300"> Product active</label><label class="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-gray-200"><input name="requires_id_fulfillment" type="checkbox" ${p.requires_id_fulfillment ? 'checked' : ''} class="h-4 w-4 rounded border-white/20 bg-black/40 accent-yellow-300"> Requires player ID fulfillment</label><button type="submit" class="w-full rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-xs font-black uppercase tracking-[0.2em] text-emerald-100 transition hover:bg-emerald-400/20">Save Product Meta</button></form><form class="product-channel space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4" data-cat="${esc(c.category_id || c._id)}" data-key="${esc(p.stock_key)}"><div class="grid gap-3 md:grid-cols-2"><label class="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-gray-200"><input name="is_visible_web" type="checkbox" ${p.is_visible_web ? 'checked' : ''} class="h-4 w-4 rounded border-white/20 bg-black/40 accent-cyan-300"> Visible on web</label><label class="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-gray-200"><input name="is_visible_bot" type="checkbox" ${p.is_visible_bot ? 'checked' : ''} class="h-4 w-4 rounded border-white/20 bg-black/40 accent-cyan-300"> Visible on bot</label></div><div class="grid gap-3 md:grid-cols-2"><input name="allocation_web" type="number" min="0" value="${esc(p.allocation_web ?? '')}" placeholder="Web allocation" class="rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/40"><input name="allocation_bot" type="number" min="0" value="${esc(p.allocation_bot ?? '')}" placeholder="Bot allocation" class="rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/40"></div><div class="rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-xs text-gray-400">Prices: ${(p.prices ? Object.entries(p.prices).map(([code, val]) => `${esc(code)} ${esc(String(val))}`).join(' - ') : 'None')}</div><button type="submit" class="w-full rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-xs font-black uppercase tracking-[0.2em] text-cyan-100 transition hover:bg-cyan-400/20">Save Visibility & Allocation</button></form></div></article>`).join('')}</div></section>`).join('');
  $$('.category-meta', host).forEach((f) => f.addEventListener('submit', async (e) => { e.preventDefault(); try { await postForm('/api/store/admin/catalog/category-meta', { cat_id: f.dataset.cat, description: f.elements.description.value, estimated_completion_time: f.elements.estimated_completion_time.value, is_active: f.elements.is_active.checked }); toast('Category meta saved.', 'success'); await loadInventory(); } catch (err) { toast(err.message, 'error'); } }));
  $$('.product-meta', host).forEach((f) => f.addEventListener('submit', async (e) => { e.preventDefault(); try { await postForm('/api/store/admin/catalog/product-meta', { cat_id: f.dataset.cat, stock_key: f.dataset.key, description: f.elements.description.value, estimated_completion_time: f.elements.estimated_completion_time.value, is_active: f.elements.is_active.checked, requires_id_fulfillment: f.elements.requires_id_fulfillment.checked }); toast('Product meta saved.', 'success'); await loadInventory(); } catch (err) { toast(err.message, 'error'); } }));
  $$('.product-channel', host).forEach((f) => f.addEventListener('submit', async (e) => { e.preventDefault(); try { await postForm('/api/store/admin/catalog/product-channel', { cat_id: f.dataset.cat, stock_key: f.dataset.key, is_visible_web: f.elements.is_visible_web.checked, is_visible_bot: f.elements.is_visible_bot.checked, allocation_web: f.elements.allocation_web.value, allocation_bot: f.elements.allocation_bot.value }); toast('Product visibility updated.', 'success'); await loadInventory(); } catch (err) { toast(err.message, 'error'); } }));
}
async function loadCustomers() {
  try {
    const data = await getJSON('/api/store/admin/customers');
    STATE.customers = data.customers || [];
    $('#customers-table-body').innerHTML = STATE.customers.length ? STATE.customers.map((c) => `<tr><td class="px-4 py-3"><div class="font-black text-white">${esc(c.name || '-')}</div><div class="text-xs text-gray-500">@${esc(c.username || '-')}</div></td><td class="px-4 py-3 text-xs text-gray-300">${esc(c.email || '')}</td><td class="px-4 py-3">${pill(c.role, tone(c.role))}</td><td class="px-4 py-3 text-yellow-200">${esc(String(c.balance_egp ?? 0))}</td><td class="px-4 py-3 text-cyan-200">${esc(String(c.balance_usd ?? 0))}</td><td class="px-4 py-3 text-xs ${c.is_banned ? 'text-red-300' : 'text-emerald-300'}">${c.is_banned ? 'Banned' : 'Active'}</td></tr>`).join('') : `<tr><td colspan="6" class="px-4 py-8 text-center text-gray-500">No customers found.</td></tr>`;
  } catch (err) { toast(err.message, 'error'); }
}

async function loadStorefront() {
  try {
    const data = await getJSON('/api/store/admin/storefront-config');
    STATE.storefront = data.config || { hero_banners: [], how_it_works: { title: '', subtitle: '', steps: [] }, best_sellers: [] };
    STATE.productOptions = data.product_options || [];
    $('#storefront-hero-banners').value = (STATE.storefront.hero_banners || []).join('\n');
    $('#storefront-how-title').value = STATE.storefront.how_it_works?.title || '';
    $('#storefront-how-subtitle').value = STATE.storefront.how_it_works?.subtitle || '';
    const steps = (STATE.storefront.how_it_works?.steps || []).slice(); while (steps.length < 3) steps.push({ title: '', description: '', icon: 'fa-circle' });
    $('#storefront-how-steps').innerHTML = steps.map((s, i) => `<div class="storefront-step rounded-3xl border border-white/10 bg-white/5 p-4"><p class="mb-3 text-xs font-black uppercase tracking-[0.2em] text-gray-400">Step ${i + 1}</p><input data-field="title" type="text" value="${esc(s.title || '')}" placeholder="Step title" class="mb-3 w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white outline-none focus:border-emerald-400/40"><textarea data-field="description" rows="3" placeholder="Step description" class="mb-3 w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white outline-none focus:border-emerald-400/40">${esc(s.description || '')}</textarea><input data-field="icon" type="text" value="${esc(s.icon || 'fa-circle')}" placeholder="Font Awesome icon" class="w-full rounded-2xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white outline-none focus:border-emerald-400/40"></div>`).join('');
    $('#storefront-best-sellers').innerHTML = STATE.productOptions.map((o) => `<option value="${esc(o.stock_key)}" ${(STATE.storefront.best_sellers || []).includes(o.stock_key) ? 'selected' : ''}>${esc(o.category_name)} - ${esc(o.product_name)} (${esc(o.stock_key)})</option>`).join('');
  } catch (err) { toast(err.message, 'error'); }
}

function storefrontPayload() {
  return {
    hero_banners: $('#storefront-hero-banners').value.split(/\r?\n/).map((v) => v.trim()).filter(Boolean),
    how_it_works: {
      title: $('#storefront-how-title').value.trim(),
      subtitle: $('#storefront-how-subtitle').value.trim(),
      steps: $$('.storefront-step').map((node) => ({ title: $('[data-field="title"]', node)?.value.trim() || '', description: $('[data-field="description"]', node)?.value.trim() || '', icon: $('[data-field="icon"]', node)?.value.trim() || 'fa-circle' })).filter((s) => s.title || s.description)
    },
    best_sellers: Array.from($('#storefront-best-sellers').selectedOptions || []).map((opt) => opt.value)
  };
}

async function loadStaff() {
  try {
    const data = await getJSON('/api/store/admin/staff');
    STATE.staff = data.staff || [];
    const host = $('#staff-list');
    host.innerHTML = STATE.staff.length ? STATE.staff.map((m) => `<div class="rounded-3xl border border-white/10 bg-white/5 p-4"><div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"><div><h3 class="text-lg font-black text-white">${esc(m.name || m.email)}</h3><p class="mt-1 text-sm text-gray-400">${esc(m.email || '')} - ${esc(m.role || '')}</p></div><div class="flex flex-wrap gap-2 text-xs font-black">${pill(`${m.active_claimed_orders || 0} active orders`, 'yellow')}${pill(`${m.assigned_tickets || 0} tickets`, 'cyan')}${pill(`${m.active_wallet_requests || 0} wallet`, 'emerald')}</div></div><div class="mt-4 flex justify-end"><button class="staff-remove rounded-2xl border border-red-400/20 bg-red-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-red-200 transition hover:bg-red-400/20" data-email="${esc(m.email || '')}">Remove Role</button></div></div>`).join('') : emptyCard('No elevated staff accounts found.');
    $$('.staff-remove', host).forEach((btn) => btn.addEventListener('click', async () => { if (!confirm(`Remove elevated access from ${btn.dataset.email}?`)) return; try { await postForm('/api/store/admin/staff/remove', { email: btn.dataset.email }); toast('Staff role removed.', 'success'); await loadStaff(); } catch (err) { toast(err.message, 'error'); } }));
  } catch (err) { toast(err.message, 'error'); }
}

async function loadWalletConfig() {
  try {
    const [methods, logs] = await Promise.all([getJSON('/api/store/admin/payment-methods'), getJSON('/api/store/admin/wallet-logs')]);
    STATE.methods = methods.payment_methods || [];
    STATE.logs = logs.transactions || [];
    const list = $('#payment-method-list');
    list.innerHTML = STATE.methods.length ? STATE.methods.map((m) => `<div class="rounded-3xl border border-white/10 bg-white/5 p-4"><div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"><div><h3 class="text-lg font-black text-white">${esc(m.name)}</h3><p class="mt-1 text-sm text-gray-400">${esc(m.type)} - ${m.is_active ? 'Active' : 'Disabled'} - ${esc(m.tax_fee?.mode || 'fixed')} ${esc(String(m.tax_fee?.value ?? 0))}</p></div><div class="flex flex-wrap gap-2"><button class="method-edit rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-cyan-100 transition hover:bg-cyan-400/20" data-id="${esc(m.method_id)}">Edit</button><button class="method-delete rounded-2xl border border-red-400/20 bg-red-400/10 px-4 py-2 text-xs font-black uppercase tracking-[0.2em] text-red-200 transition hover:bg-red-400/20" data-id="${esc(m.method_id)}">Delete</button></div></div></div>`).join('') : emptyCard('No payment methods configured yet.');
    $$('.method-edit', list).forEach((btn) => btn.addEventListener('click', () => { const m = STATE.methods.find((x) => String(x.method_id) === String(btn.dataset.id)); if (!m) return; const form = $('#payment-method-form'); form.elements.method_id.value = m.method_id; form.elements.name.value = m.name || ''; form.elements.image_url.value = m.image_url || ''; form.elements.type.value = m.type || 'both'; form.elements.is_active.value = String(Boolean(m.is_active)); form.elements.tax_fee_mode.value = m.tax_fee?.mode || 'fixed'; form.elements.tax_fee_value.value = m.tax_fee?.value ?? 0; form.scrollIntoView({ behavior: 'smooth', block: 'start' }); }));
    $$('.method-delete', list).forEach((btn) => btn.addEventListener('click', async () => { if (!confirm('Delete this payment method?')) return; try { await postForm('/api/store/admin/payment-methods/delete', { method_id: btn.dataset.id }); toast('Payment method deleted.', 'success'); await loadWalletConfig(); } catch (err) { toast(err.message, 'error'); } }));
    const body = $('#wallet-logs-body');
    body.innerHTML = STATE.logs.length ? STATE.logs.map((w) => `<tr><td class="px-4 py-3"><div class="font-black text-white">${esc(w.transaction_id)}</div><div class="text-xs text-gray-500">${esc(w.type)} - ${esc(w.payment_method_name)}</div></td><td class="px-4 py-3"><div class="font-bold text-white">${esc(w.claimed_by_name || w.agent_name || 'Pending')}</div><div class="text-xs text-gray-500">${esc(w.currency)}</div></td><td class="px-4 py-3 text-xs text-gray-300"><div>Requested: ${esc(money(w.requested_amount, w.currency))}</div><div>Actual: ${esc(money(w.actual_received_amount, w.currency))}</div><div>Fee: ${esc(money(w.fee_amount, w.currency))}</div></td><td class="px-4 py-3">${pill(w.status, tone(w.status))}</td><td class="px-4 py-3 text-xs text-gray-300">${esc(w.agent_name || w.agent_id || 'Pending')}</td><td class="px-4 py-3"><button class="log-spectate rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-cyan-100 transition hover:bg-cyan-400/20" data-thread="${esc(w.thread_id)}" data-title="${esc(String(w.type || '').toUpperCase())} ${esc(w.transaction_id)}">Spectate</button></td></tr>`).join('') : `<tr><td colspan="6" class="px-4 py-8 text-center text-gray-500">No wallet logs found.</td></tr>`;
    $$('.log-spectate', body).forEach((btn) => btn.addEventListener('click', () => { setTab('operations'); STATE.selected = { kind: 'spectate', threadId: btn.dataset.thread, title: btn.dataset.title, subtitle: 'Live admin-only spectate mode for wallet chat.' }; renderDetail(); }));
  } catch (err) { toast(err.message, 'error'); }
}

document.addEventListener('DOMContentLoaded', () => {
  $$('.store-admin-tab-btn').forEach((btn) => btn.addEventListener('click', () => setTab(btn.dataset.adminTab)));
  $('#store-admin-logout')?.addEventListener('click', logoutStaff);
  $('#ops-refresh')?.addEventListener('click', loadWorkspace);
  $('#inventory-refresh')?.addEventListener('click', loadInventory);
  $('#customers-refresh')?.addEventListener('click', loadCustomers);
  $('#staff-refresh')?.addEventListener('click', loadStaff);
  $('#wallet-config-refresh')?.addEventListener('click', loadWalletConfig);
  $('#wallet-logs-refresh')?.addEventListener('click', loadWalletConfig);
  $('#storefront-config-form')?.addEventListener('submit', async (e) => { e.preventDefault(); try { await postJSON('/api/store/admin/storefront-config', storefrontPayload()); toast('Storefront configuration saved.', 'success'); await loadStorefront(); } catch (err) { toast(err.message, 'error'); } });
  $('#staff-save-form')?.addEventListener('submit', async (e) => { e.preventDefault(); const f = e.currentTarget; try { await postForm('/api/store/admin/staff/save', { name: f.elements.name.value, username: f.elements.username.value, email: f.elements.email.value, password: f.elements.password.value, role: f.elements.role.value }); f.reset(); toast('Staff access saved.', 'success'); await loadStaff(); } catch (err) { toast(err.message, 'error'); } });
  $('#payment-method-form')?.addEventListener('submit', async (e) => { e.preventDefault(); const f = e.currentTarget; try { await postForm('/api/store/admin/payment-methods/save', { method_id: f.elements.method_id.value, name: f.elements.name.value, image_url: f.elements.image_url.value, type: f.elements.type.value, is_active: f.elements.is_active.value, tax_fee_mode: f.elements.tax_fee_mode.value, tax_fee_value: f.elements.tax_fee_value.value }); f.reset(); toast('Payment method saved.', 'success'); await loadWalletConfig(); } catch (err) { toast(err.message, 'error'); } });
  setTab('operations');
});
