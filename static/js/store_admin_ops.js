const BOOT = window.STORE_ADMIN_BOOTSTRAP || {};
const TAB_KEY = 'saleh_zone_store_admin_tab';
const STATE = {
  allowedTabs: Array.isArray(BOOT.allowedTabs) && BOOT.allowedTabs.length ? BOOT.allowedTabs : ['orders', 'support', 'inventory'],
  tab: 'orders',
  workspace: null,
  catalog: [],
  customers: [],
  storefront: null,
  productOptions: [],
  staff: [],
  methods: [],
  logs: [],
  ticketFilter: 'all',
  modal: { kind: '', id: '', threadId: '', readOnly: false },
  chat: { threadId: '', readOnly: false, socket: null, connected: false, messages: [], presence: null }
};

const $ = (id) => document.getElementById(id);
const $$ = (selector, parent = document) => Array.from(parent.querySelectorAll(selector));
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char] || char));
const labelize = (value) => String(value || '').replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()) || '-';
const money = (value, currency) => `${Number(value || 0).toFixed(2)} ${String(currency || '').toUpperCase()}`;
const toneClass = (value) => {
  const key = String(value || '').toLowerCase();
  if (['open', 'active', 'completed'].includes(key)) return 'open';
  if (['pending', 'pending_manual', 'scheduled', 'processing', 'preorder', 'in_progress'].includes(key)) return 'pending';
  if (['closed', 'cancelled', 'rejected', 'disabled'].includes(key)) return 'closed';
  return 'open';
};

function showToast(message, kind = 'info') {
  const host = $('toast-container');
  if (!host || !message) return;
  const div = document.createElement('div');
  const palette = kind === 'error'
    ? 'border border-red-500/30 text-red-300'
    : kind === 'success'
      ? 'border border-szgreen/30 text-szgreen'
      : 'border border-szcyan/30 text-szcyan';
  div.className = `toast ${palette}`;
  div.innerHTML = `<i class="fas ${kind === 'error' ? 'fa-circle-xmark' : kind === 'success' ? 'fa-circle-check' : 'fa-circle-info'}"></i><span>${esc(message)}</span>`;
  host.appendChild(div);
  setTimeout(() => div.remove(), 2800);
}

async function parseRes(res) {
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = { success: false, msg: 'Unexpected server response.' };
  }
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
  const form = new FormData();
  Object.entries(payload || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null) form.append(key, value);
  });
  return parseRes(await fetch(url, { method: 'POST', credentials: 'same-origin', body: form }));
}

async function postJSON(url, payload) {
  return parseRes(await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  }));
}

async function uploadStoreImage(file, statusEl) {
  if (!file) return null;
  if (statusEl) statusEl.textContent = 'Uploading...';
  try {
    const form = new FormData();
    form.append('file', file);
    const data = await parseRes(await fetch('/api/store/admin/upload-image', {
      method: 'POST', credentials: 'same-origin', body: form
    }));
    if (statusEl) statusEl.textContent = '';
    showToast('Image uploaded successfully!', 'success');
    return data.url || null;
  } catch (error) {
    if (statusEl) statusEl.textContent = error.message || 'Upload failed';
    showToast(error.message || 'Upload failed', 'error');
    return null;
  }
}

function statusChip(value) {
  const label = labelize(value);
  return `<span class="status-chip ${toneClass(value)} ${esc(String(value || '').toLowerCase())}">${esc(label)}</span>`;
}

function emptyRow(colspan, message) {
  return `<tr><td colspan="${colspan}" class="px-4 py-10 text-center text-gray-600 font-bold">${esc(message)}</td></tr>`;
}

function infoTile(label, value) {
  return `<div class="bg-black border border-gray-800 rounded-xl p-3"><div class="text-[10px] text-gray-500 uppercase">${esc(label)}</div><div class="mt-1 text-sm font-bold text-white break-words">${esc(value || '-')}</div></div>`;
}

function safeTab(tab) {
  return STATE.allowedTabs.includes(tab) ? tab : STATE.allowedTabs[0] || 'orders';
}

function updateHeaderStats() {
  const orders = STATE.workspace?.orders || [];
  const tickets = STATE.workspace?.tickets || [];
  const wallet = STATE.workspace?.wallet_requests || [];
  const openOrders = orders.filter((order) => !['completed', 'cancelled'].includes(String(order.delivery_state || ''))).length;
  const processingOrders = orders.filter((order) => String(order.delivery_state || '') === 'processing').length;
  const completedOrders = orders.filter((order) => String(order.delivery_state || '') === 'completed').length;
  const openTickets = tickets.filter((ticket) => String(ticket.status || 'open') !== 'closed').length;
  const pendingWallet = wallet.filter((item) => String(item.status || '') === 'pending').length;

  if ($('orders-open-count')) $('orders-open-count').textContent = String(openOrders);
  if ($('orders-processing-count')) $('orders-processing-count').textContent = String(processingOrders);
  if ($('orders-completed-count')) $('orders-completed-count').textContent = String(completedOrders);
  if ($('orders-wallet-count')) $('orders-wallet-count').textContent = String(pendingWallet);
  if ($('summary-orders')) $('summary-orders').textContent = String(orders.length || BOOT.storeStats?.order_count || 0);
  if ($('summary-tickets')) $('summary-tickets').textContent = String(openTickets);
  if ($('summary-wallet')) $('summary-wallet').textContent = String(pendingWallet);
  if ($('header-order-count')) $('header-order-count').textContent = String(orders.length || BOOT.storeStats?.order_count || 0);
  if ($('header-ticket-count')) $('header-ticket-count').textContent = String(openTickets);
  if ($('header-wallet-count')) $('header-wallet-count').textContent = String(pendingWallet);
  if ($('summary-customers') && STATE.customers.length) $('summary-customers').textContent = String(STATE.customers.length);
  if ($('header-customer-count') && STATE.customers.length) $('header-customer-count').textContent = String(STATE.customers.length);
}

async function setTab(tab, options = {}) {
  const nextTab = safeTab(tab);
  STATE.tab = nextTab;
  ['customers', 'orders', 'support', 'inventory', 'storefront', 'staff', 'wallet'].forEach((name) => {
    const panel = $(`main-tab-${name}`);
    const button = $(`main-tab-btn-${name}`);
    const active = name === nextTab;
    if (panel) panel.classList.toggle('active', active);
    if (button) button.classList.toggle('active', active);
  });
  if (!options.skipState) {
    localStorage.setItem(TAB_KEY, nextTab);
    history.replaceState(null, '', `#${nextTab}`);
  }

  if (nextTab === 'orders' || nextTab === 'support') await loadWorkspace();
  if (nextTab === 'inventory') await loadInventory();
  if (nextTab === 'customers' && BOOT.isStaffAdmin) await loadCustomers();
  if (nextTab === 'storefront' && BOOT.isStaffAdmin) await loadStorefront();
  if (nextTab === 'staff' && BOOT.isStaffAdmin) await loadStaff();
  if (nextTab === 'wallet' && BOOT.isStaffAdmin) await loadWalletConfig();
}

async function logoutStaff() {
  try {
    await fetch('/api/store/logout', { method: 'POST', credentials: 'same-origin' });
  } finally {
    location.href = '/staff-login';
  }
}

function orderEntity(orderId) {
  return (STATE.workspace?.orders || []).find((order) => String(order.order_id) === String(orderId)) || null;
}

function ticketEntity(threadId) {
  return (STATE.workspace?.tickets || []).find((ticket) => String(ticket.thread_id || ticket.ticket_id) === String(threadId)) || null;
}

function walletEntity(transactionId) {
  return (STATE.workspace?.wallet_requests || []).find((item) => String(item.transaction_id) === String(transactionId)) || STATE.logs.find((item) => String(item.transaction_id) === String(transactionId)) || null;
}

function renderOrdersTable() {
  const host = $('orders-table-body');
  if (!host) return;
  const query = String($('search-orders')?.value || '').trim().toLowerCase();
  const orders = (STATE.workspace?.orders || []).filter((order) => {
    if (!query) return true;
    return [order.order_id, order.email, order.name, order.product_name, order.category].join(' ').toLowerCase().includes(query);
  });
  if (!orders.length) {
    host.innerHTML = emptyRow(8, 'No managed orders found.');
    return;
  }
  host.innerHTML = orders.map((order) => {
    const canManage = !['completed', 'cancelled'].includes(String(order.delivery_state || ''));
    return `
      <tr class="hover:bg-black/30 transition">
        <td class="px-4 py-3 font-mono text-szcyan font-bold text-xs">#${esc(order.order_id)}</td>
        <td class="px-4 py-3"><div class="font-bold text-white">${esc(order.name || '-')}</div><div class="text-[10px] text-gray-500 font-mono">${esc(order.email || '')}</div></td>
        <td class="px-4 py-3"><div class="font-bold text-white">${esc(order.product_name || order.category || '-')}</div><div class="text-[10px] text-gray-500">${esc(order.estimated_completion_time || 'No ETA')}</div></td>
        <td class="px-4 py-3">${String(order.currency || '').toUpperCase() === 'USD' ? `<span class="badge-usd px-2 py-1 rounded text-xs font-black">${esc(money(order.price, order.currency))}</span>` : `<span class="badge-egp px-2 py-1 rounded text-xs font-black">${esc(money(order.price, order.currency))}</span>`}</td>
        <td class="px-4 py-3">${statusChip(order.delivery_state)}</td>
        <td class="px-4 py-3 text-xs text-gray-400">${esc(order.claimed_by_name || 'Unclaimed')}</td>
        <td class="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">${esc(order.date || order.updated_at || '-')}</td>
        <td class="px-4 py-3"><button class="legacy-btn ${canManage ? 'legacy-btn-soft' : 'legacy-btn-cyan'} py-2 px-3 text-[10px] order-open-btn" data-order-id="${esc(order.order_id)}"><i class="fas fa-comments"></i>${canManage ? 'Manage' : 'View'}</button></td>
      </tr>`;
  }).join('');
  $$('.order-open-btn', host).forEach((button) => {
    button.addEventListener('click', () => openThreadModal('order', button.dataset.orderId));
  });
}

function renderWalletRequestsTable() {
  const host = $('wallet-requests-body');
  if (!host) return;
  const items = STATE.workspace?.wallet_requests || [];
  if (!items.length) {
    host.innerHTML = emptyRow(7, 'No wallet requests found.');
    return;
  }
  host.innerHTML = items.map((item) => `
    <tr class="hover:bg-black/30 transition">
      <td class="px-4 py-3 font-mono text-szcyan font-bold text-xs">${esc(item.transaction_id)}</td>
      <td class="px-4 py-3"><div class="font-bold text-white">${esc(item.user_name || item.name || 'Customer')}</div><div class="text-[10px] text-gray-500 font-mono">${esc(item.user_email || item.email || '')}</div></td>
      <td class="px-4 py-3 text-gray-300">${esc(String(item.type || '').toUpperCase())} · ${esc(item.payment_method_name || '-')}</td>
      <td class="px-4 py-3">${String(item.currency || '').toUpperCase() === 'USD' ? `<span class="badge-usd px-2 py-1 rounded text-xs font-black">${esc(money(item.requested_amount, item.currency))}</span>` : `<span class="badge-egp px-2 py-1 rounded text-xs font-black">${esc(money(item.requested_amount, item.currency))}</span>`}</td>
      <td class="px-4 py-3">${statusChip(item.status)}</td>
      <td class="px-4 py-3 text-xs text-gray-400">${esc(item.claimed_by_name || item.agent_name || 'Unclaimed')}</td>
      <td class="px-4 py-3"><button class="legacy-btn legacy-btn-cyan py-2 px-3 text-[10px] wallet-open-btn" data-transaction-id="${esc(item.transaction_id)}"><i class="fas fa-comments"></i>Manage</button></td>
    </tr>`).join('');
  $$('.wallet-open-btn', host).forEach((button) => {
    button.addEventListener('click', () => openThreadModal('wallet', button.dataset.transactionId));
  });
}

function renderSupportFilters() {
  const tickets = STATE.workspace?.tickets || [];
  const counts = {
    all: tickets.length,
    open: tickets.filter((ticket) => String(ticket.status || 'open') === 'open').length,
    in_progress: tickets.filter((ticket) => String(ticket.status || '') === 'in_progress').length,
    closed: tickets.filter((ticket) => String(ticket.status || '') === 'closed').length
  };
  ['all', 'open', 'in_progress', 'closed'].forEach((status) => {
    const button = $(`tf-${status}`);
    if (!button) return;
    const label = status === 'all' ? 'All' : labelize(status);
    button.textContent = `${label} (${counts[status] || 0})`;
    button.classList.toggle('active', STATE.ticketFilter === status);
  });
}

function renderSupportTable() {
  const host = $('support-table-body');
  if (!host) return;
  const query = String($('search-tickets')?.value || '').trim().toLowerCase();
  let tickets = STATE.workspace?.tickets || [];
  if (STATE.ticketFilter !== 'all') tickets = tickets.filter((ticket) => String(ticket.status || 'open') === STATE.ticketFilter);
  if (query) {
    tickets = tickets.filter((ticket) => [ticket.subject, ticket.email, ticket.name, ticket.thread_id, ticket.ticket_id].join(' ').toLowerCase().includes(query));
  }
  renderSupportFilters();
  if (!tickets.length) {
    host.innerHTML = emptyRow(7, 'No support conversations match the current filter.');
    return;
  }
  host.innerHTML = tickets.map((ticket) => `
    <tr class="hover:bg-black/30 transition">
      <td class="px-4 py-3 font-mono text-szcyan font-bold text-xs">${esc(ticket.thread_id || ticket.ticket_id)}</td>
      <td class="px-4 py-3"><div class="font-bold text-white text-xs">${esc(ticket.name || 'Customer')}</div><div class="text-[10px] text-gray-500 font-mono">${esc(ticket.email || '')}</div></td>
      <td class="px-4 py-3 text-gray-300 max-w-[280px] truncate text-xs">${esc(ticket.subject || 'Support Thread')}</td>
      <td class="px-4 py-3">${statusChip(ticket.status)}</td>
      <td class="px-4 py-3 text-gray-400 text-xs">${esc(String(ticket.message_count || 0))}</td>
      <td class="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">${esc(ticket.last_message_at || ticket.created_at || '-')}</td>
      <td class="px-4 py-3"><button class="legacy-btn legacy-btn-cyan py-2 px-3 text-[10px] support-open-btn" data-thread-id="${esc(ticket.thread_id || ticket.ticket_id)}"><i class="fas fa-comments"></i>View</button></td>
    </tr>`).join('');
  $$('.support-open-btn', host).forEach((button) => {
    button.addEventListener('click', () => openThreadModal('ticket', button.dataset.threadId));
  });
}

async function loadWorkspace() {
  try {
    STATE.workspace = await getJSON('/api/store/admin/workspace');
    renderOrdersTable();
    renderWalletRequestsTable();
    renderSupportTable();
    updateHeaderStats();
    if ($('ticket-detail-modal') && !$('ticket-detail-modal').classList.contains('hidden') && ['order', 'ticket', 'wallet'].includes(STATE.modal.kind)) {
      const entity = STATE.modal.kind === 'order' ? orderEntity(STATE.modal.id) : STATE.modal.kind === 'ticket' ? ticketEntity(STATE.modal.id) : walletEntity(STATE.modal.id);
      if (entity) renderThreadModal(STATE.modal.kind, entity, STATE.modal.readOnly);
    }
  } catch (error) {
    showToast(error.message, 'error');
  }
}

async function loadCustomers() {
  if (!BOOT.isStaffAdmin) return;
  try {
    const data = await getJSON('/api/store/admin/customers');
    STATE.customers = data.customers || [];
    const host = $('customers-table-body');
    if (!host) return;
    const query = String($('search-customers')?.value || '').trim().toLowerCase();
    const rows = STATE.customers.filter((customer) => {
      if (!query) return true;
      return [customer.name, customer.email, customer.username].join(' ').toLowerCase().includes(query);
    });
    host.innerHTML = rows.length ? rows.map((customer) => `
      <tr class="hover:bg-black/30 transition">
        <td class="px-4 py-3"><div class="font-bold text-white">${esc(customer.name || '-')}</div><div class="text-[10px] text-gray-500">@${esc(customer.username || '-')}</div></td>
        <td class="px-4 py-3 font-mono text-xs text-szcyan">${esc(customer.email || '')}</td>
        <td class="px-4 py-3">${statusChip(customer.role || 'customer')}</td>
        <td class="px-4 py-3"><span class="badge-egp px-2 py-1 rounded text-xs font-black">${esc(String(customer.balance_egp ?? 0))}</span></td>
        <td class="px-4 py-3"><span class="badge-usd px-2 py-1 rounded text-xs font-black">${esc(String(customer.balance_usd ?? 0))}</span></td>
        <td class="px-4 py-3 text-xs ${customer.is_banned ? 'text-red-400' : 'text-szgreen'}">${customer.is_banned ? 'Banned' : 'Active'}</td>
      </tr>`).join('') : emptyRow(6, 'No customers found.');
    updateHeaderStats();
  } catch (error) {
    showToast(error.message, 'error');
  }
}
async function loadInventory() {
  try {
    const data = await getJSON('/api/store/admin/catalog');
    STATE.catalog = data.categories || [];
    renderInventory();
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function renderInventory() {
  const host = $('inventory-list');
  if (!host) return;
  if (!STATE.catalog.length) {
    host.innerHTML = '<div class="section-card p-8 text-center text-gray-500 font-bold">No catalog categories found.</div>';
    return;
  }
  host.innerHTML = STATE.catalog.map((category) => {
    const categoryId = category.category_id || category.cat_id || category.id || '';
    return `
      <section class="section-card p-5">
        <div class="mb-4 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <h3 class="text-white text-xl font-black">${esc(category.name || '-')}</h3>
            <p class="text-sm text-gray-400 mt-1">${esc(category.description || 'No category description yet.')}</p>
            <p class="text-xs text-gray-500 mt-1">ETA: ${esc(category.estimated_completion_time || 'Not set')} · ${category.is_active ? 'Active' : 'Disabled'} · ${esc(String(category.product_count || 0))} products</p>
          </div>
          <form class="category-meta section-card p-4 xl:w-[360px]" data-cat-id="${esc(categoryId)}">
            <label class="text-xs text-gray-500 uppercase font-bold block mb-1">Description</label>
            <textarea name="description" rows="3" class="legacy-input resize-y mb-3">${esc(category.description || '')}</textarea>
            <label class="text-xs text-gray-500 uppercase font-bold block mb-1">Estimated completion time</label>
            <input name="estimated_completion_time" type="text" value="${esc(category.estimated_completion_time || '')}" class="legacy-input mb-3">
            <label class="flex items-center gap-3 rounded-lg border border-gray-800 bg-black px-4 py-3 text-sm text-gray-200 mb-3"><input name="is_active" type="checkbox" ${category.is_active ? 'checked' : ''} class="accent-green-400"> Category active</label>
            <button type="submit" class="legacy-btn legacy-btn-primary w-full"><i class="fas fa-floppy-disk"></i>Save Category</button>
          </form>
        </div>
        <div class="space-y-4">
          ${(category.products || []).map((product) => `
            <article class="rounded-2xl border border-gray-800 bg-black p-4">
              <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between mb-4">
                <div>
                  <h4 class="text-white font-black text-lg">${esc(product.name || product.stock_key)}</h4>
                  <p class="text-xs text-gray-500 mt-1 font-mono">${esc(product.stock_key)} · Web ${esc(String(product.effective_web_available ?? 0))} · Total ${esc(String(product.stock_count ?? 0))}</p>
                </div>
                <div class="flex flex-wrap gap-2">${statusChip(product.effective_is_active ? 'active' : 'disabled')}${statusChip(product.requires_id_fulfillment ? 'pending_manual' : 'preorder')}</div>
              </div>
              <div class="grid gap-4 xl:grid-cols-2">
                <form class="product-meta section-card p-4" data-cat-id="${esc(categoryId)}" data-stock-key="${esc(product.stock_key)}">
                  <label class="text-xs text-gray-500 uppercase font-bold block mb-1">Description</label>
                  <textarea name="description" rows="3" class="legacy-input resize-y mb-3">${esc(product.description || '')}</textarea>
                  <label class="text-xs text-gray-500 uppercase font-bold block mb-1">Estimated completion time</label>
                  <input name="estimated_completion_time" type="text" value="${esc(product.estimated_completion_time || '')}" class="legacy-input mb-3">
                  <label class="flex items-center gap-3 rounded-lg border border-gray-800 bg-[#0a0a0a] px-4 py-3 text-sm text-gray-200 mb-3"><input name="is_active" type="checkbox" ${product.is_active ? 'checked' : ''} class="accent-green-400"> Product active</label>
                  <label class="flex items-center gap-3 rounded-lg border border-gray-800 bg-[#0a0a0a] px-4 py-3 text-sm text-gray-200 mb-3"><input name="requires_id_fulfillment" type="checkbox" ${product.requires_id_fulfillment ? 'checked' : ''} class="accent-yellow-400"> Requires ID fulfillment</label>
                  <button type="submit" class="legacy-btn legacy-btn-soft w-full"><i class="fas fa-floppy-disk"></i>Save Product Meta</button>
                </form>
                <form class="product-channel section-card p-4" data-cat-id="${esc(categoryId)}" data-stock-key="${esc(product.stock_key)}">
                  <div class="grid gap-3 md:grid-cols-2 mb-3">
                    <label class="flex items-center gap-3 rounded-lg border border-gray-800 bg-[#0a0a0a] px-4 py-3 text-sm text-gray-200"><input name="is_visible_web" type="checkbox" ${product.is_visible_web ? 'checked' : ''} class="accent-cyan-400"> Visible on web</label>
                    <label class="flex items-center gap-3 rounded-lg border border-gray-800 bg-[#0a0a0a] px-4 py-3 text-sm text-gray-200"><input name="is_visible_bot" type="checkbox" ${product.is_visible_bot ? 'checked' : ''} class="accent-cyan-400"> Visible on bot</label>
                  </div>
                  <div class="grid gap-3 md:grid-cols-2 mb-3">
                    <input name="allocation_web" type="number" min="0" value="${esc(product.allocation_web ?? '')}" placeholder="Web allocation" class="legacy-input">
                    <input name="allocation_bot" type="number" min="0" value="${esc(product.allocation_bot ?? '')}" placeholder="Bot allocation" class="legacy-input">
                  </div>
                  <div class="rounded-xl border border-gray-800 bg-[#0a0a0a] px-4 py-3 text-xs text-gray-400 mb-3">Prices: ${product.prices ? esc(Object.entries(product.prices).map(([code, amount]) => `${code} ${amount}`).join(' · ')) : 'None'}</div>
                  <button type="submit" class="legacy-btn legacy-btn-cyan w-full"><i class="fas fa-sliders"></i>Save Visibility</button>
                </form>
              </div>
            </article>`).join('')}
        </div>
      </section>`;
  }).join('');

  $$('.category-meta', host).forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await postForm('/api/store/admin/catalog/category-meta', {
          cat_id: form.dataset.catId,
          description: form.elements.description.value,
          estimated_completion_time: form.elements.estimated_completion_time.value,
          is_active: form.elements.is_active.checked
        });
        showToast('Category details updated.', 'success');
        await loadInventory();
      } catch (error) {
        showToast(error.message, 'error');
      }
    });
  });

  $$('.product-meta', host).forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await postForm('/api/store/admin/catalog/product-meta', {
          cat_id: form.dataset.catId,
          stock_key: form.dataset.stockKey,
          description: form.elements.description.value,
          estimated_completion_time: form.elements.estimated_completion_time.value,
          is_active: form.elements.is_active.checked,
          requires_id_fulfillment: form.elements.requires_id_fulfillment.checked
        });
        showToast('Product details updated.', 'success');
        await loadInventory();
      } catch (error) {
        showToast(error.message, 'error');
      }
    });
  });

  $$('.product-channel', host).forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await postForm('/api/store/admin/catalog/product-channel', {
          cat_id: form.dataset.catId,
          stock_key: form.dataset.stockKey,
          is_visible_web: form.elements.is_visible_web.checked,
          is_visible_bot: form.elements.is_visible_bot.checked,
          allocation_web: form.elements.allocation_web.value,
          allocation_bot: form.elements.allocation_bot.value
        });
        showToast('Channel settings updated.', 'success');
        await loadInventory();
      } catch (error) {
        showToast(error.message, 'error');
      }
    });
  });
}

async function loadStorefront() {
  if (!BOOT.isStaffAdmin) return;
  try {
    const data = await getJSON('/api/store/admin/storefront-config');
    STATE.storefront = data.config || { hero_banners: [], how_it_works: { title: '', subtitle: '', steps: [] }, best_sellers: [] };
    STATE.productOptions = data.product_options || [];
    if ($('storefront-hero-banners')) $('storefront-hero-banners').value = (STATE.storefront.hero_banners || []).join('\n');
    if ($('storefront-how-title')) $('storefront-how-title').value = STATE.storefront.how_it_works?.title || '';
    if ($('storefront-how-subtitle')) $('storefront-how-subtitle').value = STATE.storefront.how_it_works?.subtitle || '';
    const steps = (STATE.storefront.how_it_works?.steps || []).slice();
    while (steps.length < 3) steps.push({ title: '', description: '', icon: 'fa-circle' });
    const stepHost = $('storefront-how-steps');
    if (stepHost) {
      stepHost.innerHTML = steps.map((step, index) => `
        <div class="section-card p-4 storefront-step">
          <div class="text-xs text-gray-500 uppercase font-bold mb-3">Step ${index + 1}</div>
          <input data-field="title" type="text" value="${esc(step.title || '')}" placeholder="Step title" class="legacy-input mb-3">
          <textarea data-field="description" rows="3" placeholder="Step description" class="legacy-input resize-y mb-3">${esc(step.description || '')}</textarea>
          <input data-field="icon" type="text" value="${esc(step.icon || 'fa-circle')}" placeholder="Font Awesome icon" class="legacy-input">
        </div>`).join('');
    }
    const bestSellers = $('storefront-best-sellers');
    if (bestSellers) {
      bestSellers.innerHTML = STATE.productOptions.map((option) => `<option value="${esc(option.stock_key)}" ${(STATE.storefront.best_sellers || []).includes(option.stock_key) ? 'selected' : ''}>${esc(option.category_name)} - ${esc(option.product_name)} (${esc(option.stock_key)})</option>`).join('');
    }
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function storefrontPayload() {
  return {
    hero_banners: String($('storefront-hero-banners')?.value || '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
    how_it_works: {
      title: String($('storefront-how-title')?.value || '').trim(),
      subtitle: String($('storefront-how-subtitle')?.value || '').trim(),
      steps: $$('.storefront-step').map((node) => ({
        title: String(node.querySelector('[data-field="title"]')?.value || '').trim(),
        description: String(node.querySelector('[data-field="description"]')?.value || '').trim(),
        icon: String(node.querySelector('[data-field="icon"]')?.value || 'fa-circle').trim() || 'fa-circle'
      })).filter((step) => step.title || step.description)
    },
    best_sellers: Array.from($('storefront-best-sellers')?.selectedOptions || []).map((option) => option.value)
  };
}

async function loadStaff() {
  if (!BOOT.isStaffAdmin) return;
  try {
    const data = await getJSON('/api/store/admin/staff');
    STATE.staff = data.staff || [];
    const host = $('staff-list');
    if (!host) return;
    host.innerHTML = STATE.staff.length ? STATE.staff.map((member) => `
      <div class="section-card p-4">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h3 class="text-lg font-black text-white">${esc(member.name || member.email)}</h3>
            <p class="mt-1 text-sm text-gray-400">${esc(member.email || '')} · ${esc(labelize(member.role || 'employee'))}</p>
          </div>
          <div class="flex flex-wrap gap-2 text-xs font-black">
            <span class="badge-egp px-2 py-1 rounded">${esc(String(member.active_claimed_orders || 0))} Active Orders</span>
            <span class="badge-usd px-2 py-1 rounded">${esc(String(member.assigned_tickets || 0))} Tickets</span>
            <span class="status-chip pending">${esc(String(member.active_wallet_requests || 0))} Wallet</span>
          </div>
        </div>
        <div class="mt-4 flex justify-end"><button class="legacy-btn legacy-btn-red staff-remove-btn" data-email="${esc(member.email || '')}"><i class="fas fa-user-xmark"></i>Remove Role</button></div>
      </div>`).join('') : '<div class="section-card p-8 text-center text-gray-500 font-bold">No elevated staff accounts found.</div>';
    $$('.staff-remove-btn', host).forEach((button) => {
      button.addEventListener('click', async () => {
        if (!confirm(`Remove elevated access from ${button.dataset.email}?`)) return;
        try {
          await postForm('/api/store/admin/staff/remove', { email: button.dataset.email });
          showToast('Staff role removed.', 'success');
          await loadStaff();
        } catch (error) {
          showToast(error.message, 'error');
        }
      });
    });
  } catch (error) {
    showToast(error.message, 'error');
  }
}

async function loadWalletConfig() {
  if (!BOOT.isStaffAdmin) return;
  try {
    const [methodsData, logsData] = await Promise.all([
      getJSON('/api/store/admin/payment-methods'),
      getJSON('/api/store/admin/wallet-logs')
    ]);
    STATE.methods = methodsData.payment_methods || [];
    STATE.logs = logsData.transactions || [];
    renderWalletMethods();
    renderWalletLogs();
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function renderWalletMethods() {
  const host = $('payment-method-list');
  if (!host) return;
  host.innerHTML = STATE.methods.length ? STATE.methods.map((method) => `
    <div class="section-card p-4">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h3 class="text-lg font-black text-white">${esc(method.name || '-')}</h3>
          <p class="mt-1 text-sm text-gray-400">${esc(labelize(method.type || 'both'))} · ${method.is_active ? 'Active' : 'Disabled'} · ${esc(String(method.tax_fee?.value ?? 0))} ${esc(method.tax_fee?.mode || 'fixed')}</p>
        </div>
        <div class="flex gap-2 flex-wrap">
          <button class="legacy-btn legacy-btn-cyan method-edit-btn" data-method-id="${esc(method.method_id)}"><i class="fas fa-pen"></i>Edit</button>
          <button class="legacy-btn legacy-btn-red method-delete-btn" data-method-id="${esc(method.method_id)}"><i class="fas fa-trash"></i>Delete</button>
        </div>
      </div>
    </div>`).join('') : '<div class="section-card p-8 text-center text-gray-500 font-bold">No payment methods configured yet.</div>';

  $$('.method-edit-btn', host).forEach((button) => {
    button.addEventListener('click', () => {
      const method = STATE.methods.find((item) => String(item.method_id) === String(button.dataset.methodId));
      const form = $('payment-method-form');
      if (!method || !form) return;
      form.elements.method_id.value = method.method_id || '';
      form.elements.name.value = method.name || '';
      form.elements.image_url.value = method.image_url || '';
      form.elements.type.value = method.type || 'both';
      form.elements.is_active.value = String(Boolean(method.is_active));
      form.elements.tax_fee_mode.value = method.tax_fee?.mode || 'fixed';
      form.elements.tax_fee_value.value = method.tax_fee?.value ?? 0;
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  $$('.method-delete-btn', host).forEach((button) => {
    button.addEventListener('click', async () => {
      if (!confirm('Delete this payment method?')) return;
      try {
        await postForm('/api/store/admin/payment-methods/delete', { method_id: button.dataset.methodId });
        showToast('Payment method deleted.', 'success');
        await loadWalletConfig();
      } catch (error) {
        showToast(error.message, 'error');
      }
    });
  });
}

function renderWalletLogs() {
  const host = $('wallet-logs-body');
  if (!host) return;
  host.innerHTML = STATE.logs.length ? STATE.logs.map((item) => `
    <tr class="hover:bg-black/30 transition">
      <td class="px-4 py-3"><div class="font-black text-white">${esc(item.transaction_id)}</div><div class="text-xs text-gray-500">${esc(labelize(item.type || 'wallet'))} · ${esc(item.payment_method_name || '-')}</div></td>
      <td class="px-4 py-3"><div class="font-bold text-white">${esc(item.claimed_by_name || item.agent_name || 'Pending')}</div><div class="text-xs text-gray-500">${esc(item.currency || '')}</div></td>
      <td class="px-4 py-3 text-xs text-gray-300"><div>Requested: ${esc(money(item.requested_amount, item.currency))}</div><div>Actual: ${esc(money(item.actual_received_amount, item.currency))}</div><div>Fee: ${esc(money(item.fee_amount, item.currency))}</div></td>
      <td class="px-4 py-3">${statusChip(item.status)}</td>
      <td class="px-4 py-3 text-xs text-gray-300">${esc(item.agent_name || item.agent_id || 'Pending')}</td>
      <td class="px-4 py-3"><button class="legacy-btn legacy-btn-cyan wallet-log-chat-btn" data-transaction-id="${esc(item.transaction_id)}"><i class="fas fa-eye"></i>Spectate</button></td>
    </tr>`).join('') : emptyRow(6, 'No wallet logs found.');
  $$('.wallet-log-chat-btn', host).forEach((button) => {
    button.addEventListener('click', () => {
      const item = STATE.logs.find((entry) => String(entry.transaction_id) === String(button.dataset.transactionId));
      if (!item) return;
      openThreadModal('wallet', item.transaction_id, { readOnly: true, entity: item });
    });
  });
}
function currentModalEntity(kind, id) {
  if (kind === 'order') return orderEntity(id);
  if (kind === 'ticket') return ticketEntity(id);
  if (kind === 'wallet') return walletEntity(id);
  return null;
}

function modalActionButton(id, label, kind) {
  const klass = kind === 'danger' ? 'legacy-btn-red' : kind === 'cyan' ? 'legacy-btn-cyan' : kind === 'yellow' ? 'legacy-btn-yellow' : 'legacy-btn-soft';
  return `<button id="${id}" class="legacy-btn ${klass}">${label}</button>`;
}

function renderThreadModal(kind, entity, readOnly = false) {
  if (!entity) return;
  STATE.modal = {
    kind,
    id: kind === 'ticket' ? String(entity.thread_id || entity.ticket_id) : kind === 'order' ? String(entity.order_id) : String(entity.transaction_id),
    threadId: kind === 'ticket' ? String(entity.thread_id || entity.ticket_id) : kind === 'order' ? String(entity.thread_id || `order_${entity.order_id}`) : String(entity.thread_id || `wallet_${entity.transaction_id}`),
    readOnly
  };
  const modal = $('ticket-detail-modal');
  if (!modal) return;

  $('tdm-ticket-id').textContent = kind === 'order' ? `#${entity.order_id}` : kind === 'wallet' ? entity.transaction_id : (entity.thread_id || entity.ticket_id);
  $('tdm-subject').textContent = kind === 'order'
    ? `${entity.product_name || entity.category || 'Order'}${entity.requires_id_fulfillment ? ' · ID Fulfillment' : ''}`
    : kind === 'wallet'
      ? `${labelize(entity.type || 'wallet')} · ${entity.payment_method_name || 'Request'}`
      : (entity.subject || 'Support Ticket');
  $('tdm-customer-info').textContent = kind === 'wallet'
    ? `${entity.user_name || entity.name || 'Customer'} · ${entity.user_email || entity.email || ''}`
    : `${entity.name || 'Customer'} · ${entity.email || ''}`;
  $('tdm-context-badge').textContent = kind === 'order' ? 'Order Chat' : kind === 'wallet' ? (readOnly ? 'Wallet Spectate' : 'Wallet Chat') : 'Support Chat';
  $('tdm-context-badge').className = `status-chip ${kind === 'order' ? 'pending' : kind === 'wallet' ? 'closed' : 'open'}`;

  const statusSelect = $('tdm-status-select');
  const actions = $('tdm-actions');
  const walletControls = $('tdm-wallet-controls');
  const replyWrap = $('tdm-reply-wrap');
  const meta = $('tdm-meta-grid');
  if (statusSelect) {
    statusSelect.classList.toggle('hidden', kind !== 'ticket' || readOnly);
    statusSelect.value = String(entity.status || 'open');
  }
  if (walletControls) walletControls.classList.toggle('hidden', !(kind === 'wallet' && !readOnly));
  if (replyWrap) replyWrap.classList.toggle('hidden', readOnly);

  if (kind === 'ticket') {
    meta.innerHTML = [
      infoTile('Status', labelize(entity.status || 'open')),
      infoTile('Messages', String(entity.message_count || 0)),
      infoTile('Assigned', entity.assigned_staff_name || 'Unassigned'),
      infoTile('Updated', entity.last_message_at || entity.created_at || '-')
    ].join('');
    actions.innerHTML = readOnly ? '<span class="text-xs text-gray-500 font-bold">Admin spectate mode enabled for this support thread.</span>' : '';
  } else if (kind === 'order') {
    meta.innerHTML = [
      infoTile('State', labelize(entity.delivery_state || 'preorder')),
      infoTile('Price', money(entity.price, entity.currency)),
      infoTile('Claimed By', entity.claimed_by_name || 'Unclaimed'),
      infoTile('ETA', entity.estimated_completion_time || 'Not set'),
      infoTile('Scheduled', entity.scheduled_time || 'Immediate'),
      infoTile('Player', entity.player_id ? `${entity.player_id}${entity.player_name ? ` · ${entity.player_name}` : ''}` : 'Not required')
    ].join('');
    actions.innerHTML = readOnly ? '<span class="text-xs text-gray-500 font-bold">Admin spectate mode enabled for this order thread.</span>' : `${modalActionButton('tdm-order-claim', '<i class="fas fa-hand"></i>Claim Order', 'soft')}${modalActionButton('tdm-order-processing', '<i class="fas fa-gears"></i>Move to Processing', 'yellow')}${modalActionButton('tdm-order-complete', '<i class="fas fa-check"></i>Complete Order', 'cyan')}`;
    $('tdm-order-claim')?.addEventListener('click', async () => runAndRefresh(async () => postForm('/api/store/admin/orders/claim', { order_id: entity.order_id }), 'Order claimed.', kind, entity.order_id));
    $('tdm-order-processing')?.addEventListener('click', async () => runAndRefresh(async () => postForm('/api/store/admin/orders/status', { order_id: entity.order_id, delivery_state: 'processing' }), 'Order moved to processing.', kind, entity.order_id));
    $('tdm-order-complete')?.addEventListener('click', async () => runAndRefresh(async () => postForm('/api/store/admin/orders/status', { order_id: entity.order_id, delivery_state: 'completed' }), 'Order completed.', kind, entity.order_id));
  } else if (kind === 'wallet') {
    meta.innerHTML = [
      infoTile('Status', labelize(entity.status || 'pending')),
      infoTile('Requested', money(entity.requested_amount, entity.currency)),
      infoTile('Claimed By', entity.claimed_by_name || entity.agent_name || 'Unclaimed'),
      infoTile('Method', entity.payment_method_name || '-'),
      infoTile('Fee', `${entity.fee_snapshot?.mode || 'fixed'} · ${entity.fee_snapshot?.value ?? 0}`),
      infoTile('Audit Amount', money(entity.actual_received_amount || entity.requested_amount, entity.currency))
    ].join('');
    if ($('tdm-wallet-amount')) $('tdm-wallet-amount').value = String(entity.actual_received_amount || entity.requested_amount || 0);
    actions.innerHTML = readOnly ? '<span class="text-xs text-gray-500 font-bold">Admin spectate mode enabled for this wallet thread.</span>' : `${modalActionButton('tdm-wallet-claim', '<i class="fas fa-hand"></i>Claim Request', 'soft')}${modalActionButton('tdm-wallet-confirm', '<i class="fas fa-check"></i>Confirm Transaction', 'cyan')}${modalActionButton('tdm-wallet-reject', '<i class="fas fa-ban"></i>Reject', 'danger')}`;
    $('tdm-wallet-claim')?.addEventListener('click', async () => runAndRefresh(async () => postForm('/api/store/admin/wallet-requests/claim', { transaction_id: entity.transaction_id }), 'Wallet request claimed.', kind, entity.transaction_id));
    $('tdm-wallet-confirm')?.addEventListener('click', async () => {
      const amount = Number($('tdm-wallet-amount')?.value || 0);
      if (!amount || amount <= 0) {
        showToast('Enter the exact actual amount first.', 'error');
        return;
      }
      await runAndRefresh(async () => postForm('/api/store/admin/wallet-requests/confirm', { transaction_id: entity.transaction_id, actual_received_amount: amount }), 'Wallet request confirmed.', kind, entity.transaction_id);
    });
    $('tdm-wallet-reject')?.addEventListener('click', async () => {
      if (!confirm('Reject this wallet request?')) return;
      await runAndRefresh(async () => postForm('/api/store/admin/wallet-requests/reject', { transaction_id: entity.transaction_id }), 'Wallet request rejected.', kind, entity.transaction_id);
    });
  }

  $('tdm-messages').innerHTML = '<div class="flex items-center justify-center py-12 text-szcyan"><i class="fas fa-spinner fa-spin text-3xl"></i></div>';
  $('tdm-reply-status').textContent = '';
  $('tdm-reply-input').value = '';
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  openChat(STATE.modal.threadId, readOnly);
}

function openThreadModal(kind, id, options = {}) {
  const entity = options.entity || currentModalEntity(kind, id);
  if (!entity) {
    showToast('Unable to load the requested thread.', 'error');
    return;
  }
  renderThreadModal(kind, entity, Boolean(options.readOnly));
}

function closeThreadModal() {
  const modal = $('ticket-detail-modal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
  closeChat();
  STATE.modal = { kind: '', id: '', threadId: '', readOnly: false };
}

async function runAndRefresh(action, successMessage, kind, id) {
  try {
    await action();
    showToast(successMessage, 'success');
    await loadWorkspace();
    if (kind === 'wallet' && BOOT.isStaffAdmin) await loadWalletConfig();
    const entity = currentModalEntity(kind, id);
    if (entity) renderThreadModal(kind, entity, false);
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function chatUrl(readOnly) {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  return readOnly && BOOT.isStaffAdmin ? `${scheme}://${location.host}/ws/store-chat?role=spectator&spectate=1` : `${scheme}://${location.host}/ws/store-chat?role=${encodeURIComponent(BOOT.staffRole || 'employee')}`;
}

function closeChat() {
  if (STATE.chat.socket) {
    try { STATE.chat.socket.close(); } catch (_) { }
  }
  STATE.chat = { threadId: '', readOnly: false, socket: null, connected: false, messages: [], presence: null };
}

function renderPresence() {
  const host = $('tdm-chat-presence');
  if (!host) return;
  if (!STATE.chat.threadId) {
    host.textContent = '';
    return;
  }
  if (!STATE.chat.connected) {
    host.textContent = 'Connecting to live chat...';
    return;
  }
  const presence = STATE.chat.presence || {};
  const parts = [];
  if (presence.customer_online) parts.push('Customer online');
  if (presence.staff_online) parts.push('Staff online');
  if (presence.admin_online) parts.push('Admin online');
  if (presence.spectator_online) parts.push('Spectator watching');
  host.textContent = parts.join(' · ') || 'Live chat connected.';
}

function renderChatMessages() {
  const host = $('tdm-messages');
  if (!host) return;
  if (!STATE.chat.messages.length) {
    host.innerHTML = '<div class="py-10 text-center text-gray-600 font-bold">No chat messages yet.</div>';
    return;
  }
  host.innerHTML = STATE.chat.messages.map((message) => {
    const sender = String(message.sender || '').toLowerCase();
    const isSystem = Boolean(message.is_system) || sender === 'system';
    const isCustomer = sender === 'customer';
    const wrapperClass = isSystem ? 'bg-panelbg border-gray-800 text-gray-300' : isCustomer ? 'bg-szcyan/10 border-szcyan/20 text-szcyan ml-6' : 'bg-szgreen/10 border-szgreen/20 text-szgreen mr-6';
    const name = isSystem ? 'System' : (message.name || (isCustomer ? 'Customer' : 'Staff'));
    return `<div class="rounded-2xl border p-3 ${wrapperClass}"><div class="mb-1 flex items-center justify-between gap-3"><span class="text-xs font-black uppercase tracking-[0.15em]">${esc(name)}</span><span class="text-[10px] text-gray-500">${esc(message.time || '')}</span></div><div class="whitespace-pre-wrap text-sm ${isSystem ? 'text-gray-300' : 'text-white'}">${esc(message.message || '')}</div></div>`;
  }).join('');
  host.scrollTop = host.scrollHeight;
}

function sendSocketPayload(payload) {
  if (!STATE.chat.socket || STATE.chat.socket.readyState !== WebSocket.OPEN) return false;
  STATE.chat.socket.send(JSON.stringify(payload));
  return true;
}

function ensureChatSocket(readOnly) {
  if (STATE.chat.socket && STATE.chat.readOnly !== readOnly) closeChat();
  if (STATE.chat.socket && (STATE.chat.socket.readyState === WebSocket.OPEN || STATE.chat.socket.readyState === WebSocket.CONNECTING)) return;
  STATE.chat.socket = new WebSocket(chatUrl(readOnly));
  STATE.chat.socket.addEventListener('open', () => {
    STATE.chat.connected = true;
    renderPresence();
    if (STATE.chat.threadId) sendSocketPayload({ action: 'join_room', thread_id: STATE.chat.threadId });
  });
  STATE.chat.socket.addEventListener('message', (event) => {
    let payload = {};
    try { payload = JSON.parse(event.data); } catch (_) { return; }
    if (payload.thread_id && payload.thread_id !== STATE.chat.threadId) return;
    if (payload.event === 'presence:update') {
      STATE.chat.presence = payload.presence || null;
      renderPresence();
      return;
    }
    if (payload.event === 'message:new' && payload.message) {
      STATE.chat.messages = [...STATE.chat.messages, payload.message];
      renderChatMessages();
      if (!STATE.chat.readOnly && String(payload.message.sender || '').toLowerCase() === 'customer') {
        sendSocketPayload({ action: 'mark_read', thread_id: STATE.chat.threadId });
      }
      return;
    }
    if (payload.event === 'system:joined') {
      renderPresence();
      sendSocketPayload({ action: 'mark_read', thread_id: STATE.chat.threadId });
      return;
    }
    if (payload.event === 'error' && payload.msg) showToast(payload.msg, 'error');
  });
  STATE.chat.socket.addEventListener('close', () => {
    STATE.chat.connected = false;
    renderPresence();
  });
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
    if (STATE.chat.socket?.readyState === WebSocket.OPEN) sendSocketPayload({ action: 'join_room', thread_id: threadId });
  } catch (error) {
    showToast(error.message, 'error');
  }
}

async function sendChatMessage() {
  const input = $('tdm-reply-input');
  const status = $('tdm-reply-status');
  if (!input) return;
  const message = input.value.trim();
  if (!message) {
    showToast('Reply cannot be empty.', 'error');
    return;
  }
  if (status) status.textContent = 'Sending...';
  if (sendSocketPayload({ action: 'send_message', thread_id: STATE.chat.threadId, message })) {
    input.value = '';
    if (status) status.textContent = '';
    return;
  }
  try {
    await postForm('/api/store/admin/chat/reply', { thread_id: STATE.chat.threadId, message });
    input.value = '';
    if (status) status.textContent = '';
    const history = await getJSON(`/api/store/admin/chat/history?thread_id=${encodeURIComponent(STATE.chat.threadId)}`);
    STATE.chat.messages = history.messages || [];
    renderChatMessages();
  } catch (error) {
    if (status) status.textContent = error.message || 'Unable to send.';
    showToast(error.message, 'error');
  }
}

async function changeTicketStatus() {
  if (STATE.modal.kind !== 'ticket' || STATE.modal.readOnly) return;
  const statusSelect = $('tdm-status-select');
  if (!statusSelect) return;
  try {
    await postForm('/api/store/admin/tickets/change-status', { ticket_id: STATE.modal.id, status: statusSelect.value });
    showToast('Ticket status updated.', 'success');
    await loadWorkspace();
    const entity = ticketEntity(STATE.modal.id);
    if (entity) renderThreadModal('ticket', entity, false);
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function bindSearchAndFilters() {
  $('search-orders')?.addEventListener('input', renderOrdersTable);
  $('search-customers')?.addEventListener('input', loadCustomers);
  $('search-tickets')?.addEventListener('input', renderSupportTable);
  $$('[data-ticket-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      STATE.ticketFilter = button.dataset.ticketFilter || 'all';
      renderSupportTable();
    });
  });
}

function bindGlobalActions() {
  $$('[data-admin-tab]').forEach((button) => button.addEventListener('click', () => setTab(button.dataset.adminTab)));
  $('store-admin-logout')?.addEventListener('click', logoutStaff);
  $('orders-refresh')?.addEventListener('click', loadWorkspace);
  $('support-refresh')?.addEventListener('click', loadWorkspace);
  $('inventory-refresh')?.addEventListener('click', loadInventory);
  $('customers-refresh')?.addEventListener('click', loadCustomers);
  $('staff-refresh')?.addEventListener('click', loadStaff);
  $('wallet-config-refresh')?.addEventListener('click', loadWalletConfig);
  $('wallet-logs-refresh')?.addEventListener('click', loadWalletConfig);
  $('tdm-close')?.addEventListener('click', closeThreadModal);
  $('ticket-detail-modal')?.addEventListener('click', (event) => { if (event.target === $('ticket-detail-modal')) closeThreadModal(); });
  $('tdm-send-btn')?.addEventListener('click', sendChatMessage);
  $('tdm-reply-input')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendChatMessage();
    }
  });
  $('tdm-status-select')?.addEventListener('change', changeTicketStatus);
  $('storefront-config-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await postJSON('/api/store/admin/storefront-config', storefrontPayload());
      showToast('Storefront configuration saved.', 'success');
      await loadStorefront();
    } catch (error) {
      showToast(error.message, 'error');
    }
  });
  $('staff-save-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await postForm('/api/store/admin/staff/save', {
        name: form.elements.name.value,
        username: form.elements.username.value,
        email: form.elements.email.value,
        password: form.elements.password.value,
        role: form.elements.role.value
      });
      form.reset();
      showToast('Staff access saved.', 'success');
      await loadStaff();
    } catch (error) {
      showToast(error.message, 'error');
    }
  });
  /* ── Image upload wiring ─────────────────────────── */
  $('hero-banner-file')?.addEventListener('change', async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const url = await uploadStoreImage(file, $('hero-banner-upload-status'));
    if (url) {
      const textarea = $('storefront-hero-banners');
      if (textarea) {
        const current = textarea.value.trim();
        textarea.value = current ? current + '\n' + url : url;
      }
    }
    event.target.value = '';
  });
  $('payment-method-image-file')?.addEventListener('change', async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const url = await uploadStoreImage(file, $('payment-method-upload-status'));
    if (url) {
      const form = $('payment-method-form');
      if (form) form.elements.image_url.value = url;
    }
    event.target.value = '';
  });

  $('payment-method-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await postForm('/api/store/admin/payment-methods/save', {
        method_id: form.elements.method_id.value,
        name: form.elements.name.value,
        image_url: form.elements.image_url.value,
        type: form.elements.type.value,
        is_active: form.elements.is_active.value,
        tax_fee_mode: form.elements.tax_fee_mode.value,
        tax_fee_value: form.elements.tax_fee_value.value
      });
      form.reset();
      showToast('Payment method saved.', 'success');
      await loadWalletConfig();
    } catch (error) {
      showToast(error.message, 'error');
    }
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  bindSearchAndFilters();
  bindGlobalActions();
  const requestedTab = safeTab((location.hash || '').replace('#', '') || localStorage.getItem(TAB_KEY) || 'orders');
  await setTab(requestedTab, { skipState: false });
  if (BOOT.isStaffAdmin && requestedTab !== 'customers') loadCustomers().catch(() => { });
});
