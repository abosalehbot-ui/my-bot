// ============================================================
// Saleh Zone Store Engine v3.1 — Catalog View + Persistent Cart
// ============================================================

// ─── State ───────────────────────────────────────────────────────────────
let currentCurrency = 'EGP';
let pendingPurchase  = null;
let ordersLoaded     = false;
let _forgotEmail     = '';
let _profileLoaded   = false;
const STORE_PROFILE_TAB_KEY = 'sz_active_profile_tab';

// ─── Cart State — persisted in localStorage under 'sz_cart' ──────────────
let cart = [];

function _saveCart() {
    try { localStorage.setItem('sz_cart', JSON.stringify(cart)); } catch {}
}

function _loadCart() {
    try { cart = JSON.parse(localStorage.getItem('sz_cart') || '[]'); } catch { cart = []; }
}

// ─── Helpers ─────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const setText = (id, val) => { const el = $(id); if (el) el.innerText = val ?? ''; };
const escapeHtml = (val) => String(val ?? '').replace(/[&<>"']/g, (ch) => {
    if (ch === '&') return '&amp;';
    if (ch === '<') return '&lt;';
    if (ch === '>') return '&gt;';
    if (ch === '"') return '&quot;';
    return '&#39;';
});

// ─── Modal ───────────────────────────────────────────────────────────────
function openModal(id)  { $(id)?.classList.remove('hidden'); }
function closeModal(id) { $(id)?.classList.add('hidden'); }
function openAuthModal(view) { openModal('auth-modal'); switchAuthView(view); }

// ─── Toast ───────────────────────────────────────────────────────────────
function setStatus(msg, isError = false) {
    const el = $('auth-status');
    if (el) el.innerHTML = isError ? `<span class="text-red-500">${escapeHtml(msg)}</span>` : `<span class="text-szcyan">${escapeHtml(msg)}</span>`;
}

// ─── Theme ───────────────────────────────────────────────────────────────
function setTheme(name) {
    document.documentElement.setAttribute('data-theme', name);
    localStorage.setItem('sz_theme', name);
    $('theme-drop')?.classList.add('hidden');
}

// ─── Sidebar ─────────────────────────────────────────────────────────────
function toggleSidebar() {
    $('sz-sidebar')?.classList.toggle('-translate-x-full');
    $('sidebar-backdrop')?.classList.toggle('hidden');
}
function toggleSidebarMobile() { if (window.innerWidth < 768) toggleSidebar(); }

// ─── Currency ────────────────────────────────────────────────────────────
function toggleCurrency() {
    currentCurrency = $('currency-toggle').value;
    document.querySelectorAll('.price-display').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll(`.${currentCurrency.toLowerCase()}-price`).forEach(el => el.classList.remove('hidden'));
}

// ─── Auth View Switcher ──────────────────────────────────────────────────
function switchAuthView(view) {
    document.querySelectorAll('.auth-view').forEach(el => el.classList.add('hidden'));
    $(view + '-view')?.classList.remove('hidden');
    if ($('auth-status')) $('auth-status').innerHTML = '';

    const cfg = {
        signin: { title: 'Login',          social: true  },
        signup: { title: 'Create Account', social: true  },
        otp:    { title: 'Verify Email',   social: false },
        forgot: { title: 'Reset Password', social: false },
        reset:  { title: 'New Password',   social: false },
    }[view];

    if (cfg) {
        setText('modal-title', cfg.title);
        $('social-section')?.classList.toggle('hidden', !cfg.social);
    }
}

// ─── UI Update ───────────────────────────────────────────────────────────
function updateUI(name, balEgp, balUsd) {
    $('sidebar-guest')?.classList.add('hidden');
    $('sidebar-user')?.classList.remove('hidden');
    $('sidebar-logout-btn')?.classList.remove('hidden');

    setText('sidebar-ui-name',    name);
    setText('sidebar-ui-bal-egp', balEgp ?? '0');
    setText('sidebar-ui-bal-usd', balUsd ?? '0');

    const uname = localStorage.getItem('store_username');
    setText('sidebar-ui-username', uname ? '@' + uname : '');

    localStorage.setItem('bal_egp', balEgp ?? '0');
    localStorage.setItem('bal_usd', balUsd ?? '0');
}

// ─── Avatar Helper ───────────────────────────────────────────────────────
function _applyAvatar(src) {
    document.querySelectorAll('.avatar-placeholder').forEach(el => el.classList.toggle('hidden', !!src));
    document.querySelectorAll('.avatar-img').forEach(el => {
        if (src) { el.src = src; el.classList.remove('hidden'); }
        else el.classList.add('hidden');
    });
}

// ─── Save & Login ────────────────────────────────────────────────────────
function _saveLocals(data) {
    localStorage.setItem('store_email',    data.email    ?? '');
    localStorage.setItem('store_name',     data.name     ?? '');
    localStorage.setItem('store_username', data.username ?? '');
    localStorage.setItem('store_user_id',  data.user_id  ?? '');
    localStorage.setItem('store_avatar',   data.avatar   ?? '');
    localStorage.setItem('bal_egp',        data.balance_egp ?? 0);
    localStorage.setItem('bal_usd',        data.balance_usd ?? 0);
}

function _clearAuthLocals() {
    STORE_AUTH_KEYS.forEach(k => localStorage.removeItem(k));
}

async function saveAndLogin(data) {
    _saveLocals(data);
    updateUI(data.name, data.balance_egp, data.balance_usd);
    _applyAvatar(data.avatar || '');
    closeModal('auth-modal');
    Core.showToast(`Welcome, ${data.name}!`);
    fetchAndApplyProfile();
}

function _clearAuthLocalState() {
    [
        'store_email',
        'store_name',
        'store_username',
        'store_user_id',
        'store_avatar',
        'bal_egp',
        'bal_usd',
        STORE_PROFILE_TAB_KEY,
    ].forEach(k => localStorage.removeItem(k));
}

function _applyGuestUI() {
    $('sidebar-guest')?.classList.remove('hidden');
    $('sidebar-user')?.classList.add('hidden');
    $('sidebar-logout-btn')?.classList.add('hidden');
}

async function logout() {
    await fetch('/api/store/logout', { method: 'POST' });
    _clearAuthLocals();
    location.reload();
}

// ─── Auth: Manual Login ──────────────────────────────────────────────────
async function doManualLogin(e) {
    e.preventDefault();
    const btn = $('btn-signin'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('email',    $('signin-email').value);
    fd.append('password', $('signin-password').value);
    try {
        const d = await (await fetch('/api/store/login-manual', { method: 'POST', body: fd })).json();
        if (d.success) saveAndLogin(d); else setStatus(d.msg, true);
    } catch { setStatus('Connection error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

// ─── Auth: Signup ────────────────────────────────────────────────────────
async function doSignupRequest(e) {
    e.preventDefault();
    const pass = $('signup-password').value, conf = $('signup-confirm').value;
    if (pass !== conf) return setStatus('Passwords do not match!', true);
    const btn = $('btn-signup'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('name',     $('signup-name').value);
    fd.append('username', $('signup-username').value);
    fd.append('email',    $('signup-email').value);
    fd.append('password', pass);
    try {
        const d = await (await fetch('/api/store/signup-request', { method: 'POST', body: fd })).json();
        if (d.success) { switchAuthView('otp'); setStatus(d.msg); } else setStatus(d.msg, true);
    } catch { setStatus('Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

// ─── Auth: Verify OTP ───────────────────────────────────────────────────
async function doVerifyOTP(e) {
    e.preventDefault();
    const btn = $('btn-verify'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('email', $('signup-email').value);
    fd.append('code',  $('verify-otp').value);
    try {
        const d = await (await fetch('/api/store/signup-verify', { method: 'POST', body: fd })).json();
        if (d.success) saveAndLogin(d); else setStatus(d.msg, true);
    } catch { setStatus('Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

// ─── Auth: Forgot Password ───────────────────────────────────────────────
async function doForgotPassword(e) {
    e.preventDefault();
    _forgotEmail = $('forgot-email').value;
    const btn = $('btn-forgot'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData(); fd.append('email', _forgotEmail);
    try {
        const d = await (await fetch('/api/store/forgot-password', { method: 'POST', body: fd })).json();
        if (d.success) { switchAuthView('reset'); setStatus(d.msg); } else setStatus(d.msg, true);
    } catch { setStatus('Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

// ─── Auth: Reset Password ────────────────────────────────────────────────
async function doResetPassword(e) {
    e.preventDefault();
    const btn = $('btn-reset'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('email',        _forgotEmail);
    fd.append('code',         $('reset-otp').value);
    fd.append('new_password', $('reset-new-password').value);
    try {
        const d = await (await fetch('/api/store/reset-password', { method: 'POST', body: fd })).json();
        if (d.success) { _forgotEmail = ''; switchAuthView('signin'); setStatus(d.msg); }
        else setStatus(d.msg, true);
    } catch { setStatus('Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

// ─── Auth: Google & Telegram ─────────────────────────────────────────────
async function handleGoogleResponse(response) {
    setStatus('<i class="fas fa-spinner fa-spin"></i>');
    const fd = new FormData(); fd.append('credential', response.credential);
    try {
        const d = await (await fetch('/api/store/google-login', { method: 'POST', body: fd })).json();
        if (d.success) saveAndLogin(d); else setStatus(d.msg, true);
    } catch { setStatus('Error!', true); }
}

async function onTelegramAuth(user) {
    setStatus('<i class="fas fa-spinner fa-spin"></i>');
    const fd = new FormData();
    fd.append('tg_id', user.id); fd.append('name', user.first_name); fd.append('username', user.username || '');
    try {
        const d = await (await fetch('/api/store/telegram-login', { method: 'POST', body: fd })).json();
        if (d.success) saveAndLogin(d); else setStatus(d.msg, true);
    } catch { setStatus('Error!', true); }
}

// ─── Catalog / Products View Switcher ────────────────────────────────────

/**
 * showCategory(catId)
 * Hides the catalog grid and reveals the products for the chosen category.
 */
function showCategory(catId) {
    // Hide all per-category product sections
    document.querySelectorAll('[id^="cat-products-"]').forEach(el => el.classList.add('hidden'));

    // Reveal the selected one
    const target = $('cat-products-' + catId);
    if (target) target.classList.remove('hidden');

    // Swap views
    $('catalog-view')?.classList.add('hidden');
    $('products-view')?.classList.remove('hidden');

    // Scroll to top of content area
    $('main-scroll')?.scrollTo({ top: 0, behavior: 'smooth' });
}

/**
 * backToCatalog()
 * Returns to the category cards grid.
 */
function backToCatalog() {
    $('products-view')?.classList.add('hidden');
    $('catalog-view')?.classList.remove('hidden');
    $('main-scroll')?.scrollTo({ top: 0, behavior: 'smooth' });
}

// ─── Purchase Flow (Buy Now) ─────────────────────────────────────────────

/**
 * buyProduct(stock_key, pricesObj, name, imageUrl, iconClass)
 * Opens the Buy Now confirmation modal with correct product details.
 */
function buyProduct(stock_key, pricesObj, name, imageUrl, iconClass) {
    if (!localStorage.getItem('store_email')) { openAuthModal('signin'); return; }

    const finalPrice = (pricesObj && pricesObj[currentCurrency] != null)
        ? pricesObj[currentCurrency]
        : (pricesObj && pricesObj['EGP'] != null ? pricesObj['EGP'] : 0);

    pendingPurchase = { stock_key, price: finalPrice, currency: currentCurrency, imageUrl, iconClass };

    const priceText = finalPrice + ' ' + currentCurrency;
    const pColor    = currentCurrency === 'EGP' ? 'text-yellow-500'
                    : currentCurrency === 'USD' ? 'text-szcyan'
                    : 'text-szgreen';

    setText('checkout-user-name',  localStorage.getItem('store_name'));
    setText('checkout-user-email', localStorage.getItem('store_email'));
    setText('checkout-item-name',  name);

    const icon = $('checkout-item-icon');
    const img  = $('checkout-item-image');
    if (imageUrl) {
        if (img) { img.src = imageUrl; img.classList.remove('hidden'); }
        if (icon) icon.classList.add('hidden');
    } else {
        if (img) { img.src = ''; img.classList.add('hidden'); }
        if (icon) {
            icon.className = `fas ${iconClass || 'fa-box'}`;
            icon.classList.remove('hidden');
        }
    }

    const pe = $('checkout-item-price');
    if (pe) { pe.innerText = priceText; pe.className = `p-4 text-right font-black text-lg ${pColor}`; }

    const te = $('checkout-total-price');
    if (te) { te.innerText = priceText; te.className = `text-2xl font-black ${pColor}`; }

    openModal('checkout-modal');
}

/**
 * confirmPurchase()
 * Submits the single-item Buy Now order to the server.
 */
async function confirmPurchase() {
    if (!pendingPurchase) return;
    if (!$('terms-checkbox').checked) return Core.showToast('Please agree to the Terms of Service.', 'error');

    const btn = $('btn-confirm-pay'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...'; btn.disabled = true;

    const fd = new FormData();
    fd.append('stock_key', pendingPurchase.stock_key);
    fd.append('price',     pendingPurchase.price);
    fd.append('currency',  pendingPurchase.currency);

    try {
        const d = await (await fetch('/api/store/buy', { method: 'POST', body: fd })).json();
        if (d.success) {
            const newEgp = d.currency === 'EGP' ? d.new_balance : localStorage.getItem('bal_egp');
            const newUsd = d.currency === 'USD' ? d.new_balance : localStorage.getItem('bal_usd');
            updateUI(localStorage.getItem('store_name'), newEgp, newUsd);
            ordersLoaded = false;
            closeModal('checkout-modal');
            const ce = $('purchased-code');
            if (ce) { ce.innerText = d.code; ce.classList.remove('text-left'); }
            openModal('success-modal');
        } else {
            Core.showToast(d.msg, 'error');
            if (d.force_logout) logout();
            else if (d.msg.includes('balance') || d.msg.includes('stock')) location.reload();
        }
    } catch { Core.showToast('An error occurred!', 'error'); }

    btn.innerHTML = orig; btn.disabled = false;
}

function copyPurchasedCode() {
    const code = $('purchased-code')?.innerText;
    if (code) Core.copy(code);
}

// ─── Cart System ─────────────────────────────────────────────────────────

/**
 * addToCart(stock_key, pricesObj, name, imageUrl, iconClass)
 * Adds an item (or increments qty) and persists the cart to localStorage.
 */
function addToCart(stock_key, pricesObj, name, imageUrl, iconClass) {
    if (!localStorage.getItem('store_email')) { openAuthModal('signin'); return; }

    const existing = cart.find(i => i.stock_key === stock_key);
    if (existing) {
        existing.qty += 1;
    } else {
        cart.push({ stock_key, prices: pricesObj, name, image: imageUrl || '', iconClass, qty: 1 });
    }
    _saveCart();
    updateCartUI();
    Core.showToast(`${name} added to cart!`, 'success');
}

function removeFromCart(stock_key) {
    cart = cart.filter(i => i.stock_key !== stock_key);
    _saveCart();
    updateCartUI();
    // Refresh the open cart modal if it's visible
    if (!$('cart-modal')?.classList.contains('hidden')) openCartModal();
}

function increaseCartQty(stock_key) {
    const item = cart.find(i => i.stock_key === stock_key);
    if (item) { item.qty++; _saveCart(); updateCartUI(); openCartModal(); }
}

function decreaseCartQty(stock_key) {
    const item = cart.find(i => i.stock_key === stock_key);
    if (item) {
        item.qty--;
        if (item.qty <= 0) removeFromCart(stock_key);
        else { _saveCart(); updateCartUI(); openCartModal(); }
    }
}

// Also exposed via window for HTML inline references
function changeCartQty(stock_key, delta) {
    if (delta > 0) increaseCartQty(stock_key);
    else decreaseCartQty(stock_key);
}

function updateCartUI() {
    const count = cart.reduce((sum, item) => sum + item.qty, 0);
    const cm = $('cart-count-mobile');
    const cd = $('cart-count-desktop');
    if (cm) cm.innerText = count;
    if (cd) cd.innerText = count;
}

/**
 * openCartModal()
 * Renders current cart items and opens the modal.
 */
window.openCartModal = function() {
    if (!localStorage.getItem('store_email')) { openAuthModal('signin'); return; }

    const container = $('cart-items-container');
    if (!container) return;

    if (cart.length === 0) {
        container.innerHTML = `
            <div class="flex flex-col items-center justify-center h-full text-gray-500 py-16">
                <i class="fas fa-shopping-cart text-6xl mb-4 opacity-30"></i>
                <p class="font-bold">Your cart is empty</p>
                <p class="text-xs mt-1 text-gray-700">Browse the store and add items</p>
            </div>`;
        const tp = $('cart-total-price');
        if (tp) { tp.innerText = '0.00 ' + currentCurrency; tp.className = 'text-2xl font-black text-szcyan'; }
        openModal('cart-modal');
        return;
    }

    let html  = '';
    let total = 0;

    cart.forEach(item => {
        const price     = (item.prices && item.prices[currentCurrency] != null)
                        ? item.prices[currentCurrency]
                        : (item.prices && item.prices['EGP'] != null ? item.prices['EGP'] : 0);
        const itemTotal = price * item.qty;
        total += itemTotal;
        const pColor    = currentCurrency === 'EGP' ? 'text-yellow-500'
                        : currentCurrency === 'USD' ? 'text-szcyan'
                        : 'text-szgreen';

        html += `
        <div class="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-black border border-gray-800 rounded-xl mb-3 hover:border-szcyan/50 transition gap-4">
            <div class="flex items-center gap-3 flex-1 min-w-0">
                <div class="w-10 h-10 rounded-lg bg-szcyan/10 border border-szcyan/20 flex items-center justify-center text-szcyan shrink-0 overflow-hidden">
                    ${item.image
                        ? `<img src="${item.image}" alt="${item.name}" class="w-full h-full object-cover">`
                        : `<i class="fas ${item.iconClass || 'fa-box'} text-sm"></i>`}
                </div>
                <div class="min-w-0">
                    <h4 class="text-white font-bold text-sm truncate">${item.name}</h4>
                    <div class="${pColor} font-black text-sm">${price} ${currentCurrency}
                        <span class="text-gray-500 text-[10px] font-bold uppercase ml-1">each</span>
                    </div>
                </div>
            </div>
            <div class="flex items-center justify-between sm:justify-end gap-3 w-full sm:w-auto">
                <div class="flex items-center bg-[#050505] border border-gray-700 rounded-lg overflow-hidden h-9">
                    <button onclick="decreaseCartQty('${item.stock_key}')"
                        class="w-9 h-full flex items-center justify-center text-gray-400 hover:text-white hover:bg-gray-800 transition">
                        <i class="fas fa-minus text-xs"></i>
                    </button>
                    <span class="w-10 text-center text-white font-bold text-sm">${item.qty}</span>
                    <button onclick="increaseCartQty('${item.stock_key}')"
                        class="w-9 h-full flex items-center justify-center text-gray-400 hover:text-white hover:bg-gray-800 transition">
                        <i class="fas fa-plus text-xs"></i>
                    </button>
                </div>
                <div class="${pColor} font-black text-sm w-20 text-right">${itemTotal.toFixed(2)}</div>
                <button onclick="removeFromCart('${item.stock_key}')"
                    class="text-red-500 hover:text-white hover:bg-red-600 bg-red-900/20 w-9 h-9 rounded-lg flex items-center justify-center transition shrink-0">
                    <i class="fas fa-trash-alt text-xs"></i>
                </button>
            </div>
        </div>`;
    });

    container.innerHTML = html;

    const tColor  = currentCurrency === 'EGP' ? 'text-yellow-500'
                  : currentCurrency === 'USD' ? 'text-szcyan'
                  : 'text-szgreen';
    const totalEl = $('cart-total-price');
    if (totalEl) {
        totalEl.innerText  = total.toFixed(2) + ' ' + currentCurrency;
        totalEl.className  = `text-2xl font-black ${tColor}`;
    }

    openModal('cart-modal');
};

/**
 * confirmCartPurchase()
 * Sends all cart items to the backend checkout endpoint in one request.
 */
async function confirmCartPurchase() {
    if (cart.length === 0) return Core.showToast('Your cart is empty.', 'error');
    if (!$('cart-terms-checkbox').checked) return Core.showToast('Please agree to the Terms of Service.', 'error');

    const btn = $('btn-confirm-cart'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...'; btn.disabled = true;

    const cartItems = cart.map(item => ({
        stock_key: item.stock_key,
        quantity:  item.qty,
        price:     (item.prices && item.prices[currentCurrency] != null)
                    ? item.prices[currentCurrency]
                    : (item.prices && item.prices['EGP'] != null ? item.prices['EGP'] : 0),
        currency:  currentCurrency,
    }));

    try {
        const res = await fetch('/api/store/checkout-cart', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ cart: cartItems }),
        });
        const d = await res.json();

        if (d.success) {
            const newEgp = d.new_balances?.balance_egp ?? localStorage.getItem('bal_egp');
            const newUsd = d.new_balances?.balance_usd ?? localStorage.getItem('bal_usd');
            updateUI(localStorage.getItem('store_name'), newEgp, newUsd);
            localStorage.setItem('bal_egp', newEgp ?? '0');
            localStorage.setItem('bal_usd', newUsd ?? '0');

            // Clear cart
            cart = [];
            _saveCart();
            updateCartUI();
            ordersLoaded = false;
            closeModal('cart-modal');

            const successItems = d.results.filter(r => r.status === 'Success');
            const failedItems  = d.results.filter(r => r.status === 'Failed');

            let codesHtml = successItems.map(r =>
                `<div class="bg-black border border-szgreen/30 rounded-lg p-3 mb-2">
                    <div class="text-[10px] text-gray-500 mb-1">${r.stock_key} · ${r.price} ${r.currency}</div>
                    <div class="text-szgreen font-mono font-bold select-all">${r.code}</div>
                 </div>`
            ).join('');

            if (failedItems.length > 0) {
                codesHtml += `<div class="mt-3 border-t border-gray-800 pt-3">
                    <p class="text-xs text-red-400 font-bold mb-2"><i class="fas fa-exclamation-triangle mr-1"></i>Failed items (${failedItems.length}):</p>
                    ${failedItems.map(r => `<div class="text-xs text-gray-500">${r.stock_key}: ${r.msg}</div>`).join('')}
                </div>`;
            }

            const ce = $('purchased-code');
            if (ce) { ce.innerHTML = codesHtml || 'No successful items.'; ce.classList.add('text-left'); }
            openModal('success-modal');
        } else {
            Core.showToast(d.msg, 'error');
            if (d.force_logout) logout();
        }
    } catch { Core.showToast('An error occurred!', 'error'); }

    btn.innerHTML = orig; btn.disabled = false;
}

// ─── Profile Modal ───────────────────────────────────────────────────────
function _isStoreLoggedIn() {
    return !!localStorage.getItem('store_email');
}

function _applyProfileAuthGuard() {
    const authContent = $('profile-auth-content');
    const required    = $('profile-login-required');
    const loggedIn    = _isStoreLoggedIn();
    if (authContent) authContent.classList.toggle('hidden', !loggedIn);
    if (required) required.classList.toggle('hidden', loggedIn);
}

function openProfileModal() {
    openModal('profile-modal');
    _applyProfileAuthGuard();
    if (!_isStoreLoggedIn()) return;

    const remembered = localStorage.getItem(STORE_PROFILE_TAB_KEY) || 'overview';
    switchProfileTab(remembered);
    if (!_profileLoaded) { _profileLoaded = true; fetchAndApplyProfile(); }
    else _applyLocalProfile();
}

function switchProfileTab(tab) {
    if (!_isStoreLoggedIn()) return;
    ['overview', 'edit', 'security', 'history', 'support'].forEach(t => {
        $('ptab-' + t)?.classList.add('hidden');
        const btn = $('ptab-btn-' + t);
        if (!panel) console.warn(`[profile] Missing panel element: ptab-${t}`);
        else panel.classList.add('hidden');
        if (!btn) console.warn(`[profile] Missing tab button element: ptab-btn-${t}`);
        else {
            btn.classList.remove('active');
            btn.classList.add('inactive');
        }
    });
    $('ptab-' + tab)?.classList.remove('hidden');
    const ab = $('ptab-btn-' + tab);
    if (ab) { ab.classList.add('active'); ab.classList.remove('inactive'); }

    localStorage.setItem(STORE_PROFILE_TAB_KEY, tab);
    if (tab === 'overview') history.replaceState(null, '', location.pathname + location.search);
    else history.replaceState(null, '', `#${tab}`);

    if (tab === 'history' && !ordersLoaded) {
        fetchMyOrders();
        fetchWalletHistory();
    }
    if (tab === 'support' && !_ticketsLoaded) loadMyTickets();
}

function _applyLocalProfile() {
    _fillProfileUI({
        name:        localStorage.getItem('store_name'),
        email:       localStorage.getItem('store_email'),
        username:    localStorage.getItem('store_username'),
        user_id:     localStorage.getItem('store_user_id'),
        avatar:      localStorage.getItem('store_avatar'),
        balance_egp: localStorage.getItem('bal_egp'),
        balance_usd: localStorage.getItem('bal_usd'),
    });
}

function _fillProfileUI(d) {
    setText('prof-name',     d.name);
    setText('prof-email',    d.email);
    setText('prof-username', d.username ? '@' + d.username : '—');
    setText('prof-user-id',  d.user_id ? '#' + d.user_id : '');
    setText('prof-bal-egp',  d.balance_egp ?? '0');
    setText('prof-bal-usd',  d.balance_usd ?? '0');
    setText('prof-joined',   d.created_at  ?? '');
    const ni = $('edit-name'), ui = $('edit-username');
    if (ni) ni.value = d.name     ?? '';
    if (ui) ui.value = d.username ?? '';
    _applyAvatar(d.avatar || '');
}

async function fetchAndApplyProfile() {
    try {
        const d = await (await fetch('/api/store/me', { cache: 'no-store' })).json();
        _serverAuthKnown = true;
        _serverLoggedIn = !!d.success;

        if (!d.success) {
            _clearAuthLocals();
            return false;
        }
        _saveLocals(d);
        updateUI(d.name, d.balance_egp, d.balance_usd);
        _fillProfileUI(d);
        return true;
    } catch {
        return _isStoreLoggedIn();
    } finally {
        _applyProfileAuthGuard();
    }
}

function triggerAvatarUpload() { $('avatar-file-input')?.click(); }

async function handleAvatarChange(input) {
    const file = input.files[0]; if (!file) return;
    if (file.size > 1_000_000) return Core.showToast('Max 1MB!', 'error');
    const reader = new FileReader();
    reader.onload = async e => {
        const b64 = e.target.result;
        _applyAvatar(b64);
        const fd = new FormData(); fd.append('avatar_b64', b64);
        try {
            const d = await (await fetch('/api/store/upload-avatar', { method: 'POST', body: fd })).json();
            if (d.success) { localStorage.setItem('store_avatar', b64); Core.showToast('Avatar updated!'); }
            else Core.showToast(d.msg, 'error');
        } catch { Core.showToast('Upload failed!', 'error'); }
    };
    reader.readAsDataURL(file);
}

async function doUpdateProfile(e) {
    e.preventDefault();
    const btn = $('btn-update-profile'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('name',     $('edit-name').value);
    fd.append('username', $('edit-username').value);
    try {
        const d = await (await fetch('/api/store/update-profile', { method: 'POST', body: fd })).json();
        if (d.success) {
            localStorage.setItem('store_name',     d.name);
            localStorage.setItem('store_username', d.username);
            setText('sidebar-ui-name',     d.name);
            setText('sidebar-ui-username', '@' + d.username);
            setText('prof-name',     d.name);
            setText('prof-username', '@' + d.username);
            _setFormStatus('edit-status', d.msg, false);
        } else _setFormStatus('edit-status', d.msg, true);
    } catch { _setFormStatus('edit-status', 'Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

async function doChangePassword(e) {
    e.preventDefault();
    const np = $('sec-new-pass').value, cp = $('sec-conf-pass').value;
    if (np !== cp) return _setFormStatus('sec-status', 'Passwords do not match!', true);
    const btn = $('btn-change-pass'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('current_password', $('sec-curr-pass').value);
    fd.append('new_password',     np);
    try {
        const d = await (await fetch('/api/store/change-password', { method: 'POST', body: fd })).json();
        if (d.success) { $('pass-change-form').reset(); _setFormStatus('sec-status', d.msg, false); }
        else _setFormStatus('sec-status', d.msg, true);
    } catch { _setFormStatus('sec-status', 'Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

async function doChangeEmailRequest(e) {
    e.preventDefault();
    const btn = $('btn-email-req'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData(); fd.append('new_email', $('sec-new-email').value);
    try {
        const d = await (await fetch('/api/store/change-email-request', { method: 'POST', body: fd })).json();
        if (d.success) {
            _setFormStatus('sec-status', d.msg, false);
            $('email-otp-step')?.classList.remove('hidden');
            btn.classList.add('hidden');
        } else _setFormStatus('sec-status', d.msg, true);
    } catch { _setFormStatus('sec-status', 'Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

async function doChangeEmailVerify(e) {
    e.preventDefault();
    const btn = $('btn-email-verify'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData(); fd.append('code', $('sec-email-otp').value);
    try {
        const d = await (await fetch('/api/store/change-email-verify', { method: 'POST', body: fd })).json();
        if (d.success) {
            localStorage.setItem('store_email', d.new_email);
            setText('prof-email', d.new_email);
            _setFormStatus('sec-status', d.msg, false);
            $('email-change-form').reset();
            $('email-otp-step')?.classList.add('hidden');
            $('btn-email-req')?.classList.remove('hidden');
        } else _setFormStatus('sec-status', d.msg, true);
    } catch { _setFormStatus('sec-status', 'Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

function _setFormStatus(id, msg, isError) {
    const el = $(id);
    if (!el) return;
    el.innerHTML = isError
        ? `<span class="text-red-500"><i class="fas fa-times-circle mr-1"></i>${msg}</span>`
        : `<span class="text-szgreen"><i class="fas fa-check-circle mr-1"></i>${msg}</span>`;
}

async function fetchMyOrders() {
    const loader = $('orders-loading'), tbody = $('orders-table-body');
    if (loader) loader.classList.remove('hidden');
    if (tbody)  tbody.innerHTML = '';
    try {
        const d = await (await fetch('/api/store/my-orders')).json();
        if (loader) loader.classList.add('hidden');
        if (d.success && d.orders.length > 0) {
            tbody.innerHTML = d.orders.map(o => {
                const pc = o.currency === 'USD' ? 'text-szcyan' : 'text-yellow-500';
                const sc = String(o.code).replace(/'/g, "\\'");
                return `<tr class="hover:bg-[#111] transition">
                    <td class="px-4 py-3 font-mono text-szcyan">#${o.order_id}</td>
                    <td class="px-4 py-3 text-xs text-gray-500">${o.date}</td>
                    <td class="px-4 py-3 font-bold text-white">${o.category}</td>
                    <td class="px-4 py-3 font-black ${pc}">${o.price} <span class="text-[10px] text-gray-500">${o.currency}</span></td>
                    <td class="px-4 py-3"><button onclick="Core.copy('${sc}')" class="bg-gray-900 text-szgreen border border-gray-700 px-3 py-1 rounded text-xs font-mono hover:bg-szgreen hover:text-black transition">Copy</button></td>
                </tr>`;
            }).join('');
            ordersLoaded = true;
        } else if (tbody) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500 font-bold">No purchases found.</td></tr>';
        }
    } catch { if (loader) loader.innerHTML = '<span class="text-red-500">Error loading orders.</span>'; }
}


async function fetchWalletHistory() {
    const list = $('wallet-history-list');
    const loader = $('wallet-loading');
    if (!list) return;
    if (loader) loader.classList.remove('hidden');
    list.innerHTML = '';
    try {
        const d = await (await fetch('/api/store/wallet-history')).json();
        if (loader) loader.classList.add('hidden');
        if (!d.success || !d.txns.length) {
            list.innerHTML = '<div class="text-center text-gray-500 text-xs py-4">No wallet transactions yet.</div>';
            return;
        }
        list.innerHTML = d.txns.map(t => {
            const isPlus = Number(t.amount) >= 0;
            const amount = `${isPlus ? '+' : '-'} ${Math.abs(Number(t.amount)).toFixed(2)} ${t.currency}`;
            const amountClr = isPlus ? 'text-szgreen' : 'text-red-400';
            return `<div class="border border-gray-800 rounded-xl p-3 flex items-center justify-between gap-3 bg-[#080808]">
                <div>
                    <div class="text-xs font-black ${amountClr}">${amount}</div>
                    <div class="text-[11px] text-gray-300 mt-0.5">${t.note || 'Wallet transaction'}</div>
                </div>
                <div class="text-[10px] text-gray-500 whitespace-nowrap">${t.created_at || ''}</div>
            </div>`;
        }).join('');
    } catch {
        if (loader) loader.classList.add('hidden');
        list.innerHTML = '<div class="text-center text-red-500 text-xs py-4">Failed to load wallet ledger.</div>';
    }
}

// ============================================================
// Support Tickets — Customer Side (unchanged from v3.0)
// ============================================================
let _activeConvoTicketId = '';
let _ticketsLoaded       = false;

async function submitTicket() {
    const subject  = $('ticket-subject')?.value.trim();
    const message  = $('ticket-message')?.value.trim();
    const statusEl = $('ticket-submit-status');

    if (!subject || !message) {
        if (statusEl) statusEl.innerHTML = '<span class="text-red-500">Please fill in both fields.</span>';
        return;
    }

    const btn  = document.querySelector('[onclick="submitTicket()"]');
    const orig = btn?.innerHTML;
    if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>Submitting...'; btn.disabled = true; }
    if (statusEl) statusEl.innerHTML = '';

    const fd = new FormData();
    fd.append('subject', subject);
    fd.append('message', message);

    try {
        const d = await (await fetch('/api/store/tickets/create', { method: 'POST', body: fd })).json();
        if (d.success) {
            Core.showToast(d.msg, 'success');
            if ($('ticket-subject')) $('ticket-subject').value = '';
            if ($('ticket-message')) $('ticket-message').value = '';
            if (statusEl) statusEl.innerHTML = `<span class="text-szgreen"><i class="fas fa-check-circle mr-1"></i>${d.msg}</span>`;
            _ticketsLoaded = false;
            await loadMyTickets();
        } else {
            if (statusEl) statusEl.innerHTML = `<span class="text-red-500">${escapeHtml(d.msg)}</span>`;
            Core.showToast(d.msg, 'error');
            if (d.force_logout) logout();
        }
    } catch {
        if (statusEl) statusEl.innerHTML = '<span class="text-red-500">Connection error!</span>';
    }
    if (btn) { btn.innerHTML = orig; btn.disabled = false; }
}

async function loadMyTickets() {
    const list   = $('my-tickets-list');
    const loader = $('my-tickets-loading');
    if (!list) return;
    if (loader) loader.classList.remove('hidden');
    list.innerHTML = '';
    try {
        const d = await (await fetch('/api/store/tickets/my')).json();
        if (loader) loader.classList.add('hidden');
        if (!d.success || !d.tickets.length) {
            list.innerHTML = '<p class="text-center text-gray-600 text-xs font-bold py-4">No tickets found. Submit your first ticket above.</p>';
            return;
        }
        const statusColors = {
            open:        'text-green-400 border-green-900/40 bg-green-900/10',
            in_progress: 'text-yellow-400 border-yellow-900/40 bg-yellow-900/10',
            closed:      'text-red-400   border-red-900/40   bg-red-900/10',
        };
        list.innerHTML = d.tickets.map(t => {
            const sc       = statusColors[t.status] || statusColors.open;
            const msgCount = (t.messages || []).length;
            const lastMsg  = t.messages?.[t.messages.length - 1]?.message?.substring(0, 60) || '';
            return `<div onclick="openTicketConvo('${t.ticket_id}')"
                        class="cursor-pointer bg-black border border-gray-800 rounded-xl p-3 hover:border-szcyan/50 transition group">
                <div class="flex items-start justify-between gap-2 mb-1">
                    <span class="text-white font-bold text-xs leading-tight flex-1 group-hover:text-szcyan transition">${t.subject}</span>
                    <span class="text-[10px] font-bold border px-2 py-0.5 rounded shrink-0 ${sc}">${(t.status || 'open').replace('_', ' ')}</span>
                </div>
                ${lastMsg ? `<p class="text-[10px] text-gray-600 mb-1 truncate">${lastMsg}${lastMsg.length >= 60 ? '...' : ''}</p>` : ''}
                <div class="flex items-center justify-between text-[10px] text-gray-600">
                    <span class="font-mono">${t.ticket_id}</span>
                    <span><i class="fas fa-comments mr-1"></i>${msgCount} msg${msgCount !== 1 ? 's' : ''}</span>
                    <span>${t.created_at}</span>
                </div>
            </div>`;
        }).join('');
        _ticketsLoaded = true;
    } catch {
        if (loader) loader.classList.add('hidden');
        if (list) list.innerHTML = '<p class="text-center text-red-500 text-xs py-4">Failed to load tickets.</p>';
    }
}

async function openTicketConvo(ticketId) {
    _activeConvoTicketId = ticketId;
    $('support-new-ticket-section')?.classList.add('hidden');
    $('support-ticket-list-section')?.classList.add('hidden');
    const convo = $('ticket-convo-section');
    if (convo) convo.classList.remove('hidden');
    if ($('convo-messages')) $('convo-messages').innerHTML = '<div class="text-center text-szcyan py-6"><i class="fas fa-spinner fa-spin text-2xl"></i></div>';

    try {
        const d = await (await fetch('/api/store/tickets/my')).json();
        const ticket = d.tickets?.find(t => t.ticket_id === ticketId);
        if (!ticket) { Core.showToast('Ticket not found.', 'error'); closeTicketConvo(); return; }

        if ($('convo-subject')) $('convo-subject').innerText = ticket.subject;

        const statusColors = {
            open:        'text-green-400 border-green-900/40 bg-green-900/10',
            in_progress: 'text-yellow-400 border-yellow-900/40 bg-yellow-900/10',
            closed:      'text-red-400   border-red-900/40   bg-red-900/10',
        };
        const sc     = statusColors[ticket.status] || statusColors.open;
        const sLabel = (ticket.status || 'open').replace('_', ' ');
        if ($('convo-status-badge')) {
            $('convo-status-badge').innerHTML = `<span class="text-[10px] font-bold border px-2 py-0.5 rounded ${sc}">${sLabel}</span>`;
        }

        // Hide reply input if ticket is closed
        const replySection = $('convo-reply-section');
        if (replySection) replySection.style.display = ticket.status === 'closed' ? 'none' : '';

        const msgs         = ticket.messages || [];
        const msgContainer = $('convo-messages');
        if (!msgs.length) {
            msgContainer.innerHTML = '<p class="text-center text-gray-600 text-xs py-6">No messages yet.</p>';
            return;
        }
        msgContainer.innerHTML = msgs.map(m => {
            const isAdmin = m.sender === 'admin';
            const wrapCls = isAdmin ? 'bg-szgreen/10 border-szgreen/20 ml-4' : 'bg-szcyan/10 border-szcyan/20 mr-4';
            const nameClr = isAdmin ? 'text-szgreen' : 'text-szcyan';
            const icon    = isAdmin ? '<i class="fas fa-shield-alt ml-1 text-[10px]"></i>' : '';
            return `<div class="${wrapCls} border rounded-xl p-3">
                <div class="flex items-center justify-between gap-3 mb-1">
                    <span class="text-xs font-black ${nameClr}">${m.name}${icon}</span>
                    <span class="text-[10px] text-gray-600 shrink-0">${m.time}</span>
                </div>
                <p class="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">${m.message}</p>
            </div>`;
        }).join('');
        msgContainer.scrollTop = msgContainer.scrollHeight;
    } catch { Core.showToast('Error loading ticket.', 'error'); closeTicketConvo(); }
}

function closeTicketConvo() {
    _activeConvoTicketId = '';
    $('ticket-convo-section')?.classList.add('hidden');
    $('support-new-ticket-section')?.classList.remove('hidden');
    $('support-ticket-list-section')?.classList.remove('hidden');
    if ($('convo-reply-input'))  $('convo-reply-input').value  = '';
    if ($('convo-reply-status')) $('convo-reply-status').innerHTML = '';
}

async function sendCustomerReply() {
    if (!_activeConvoTicketId) return;
    const input    = $('convo-reply-input');
    const statusEl = $('convo-reply-status');
    const msg      = input?.value.trim();
    if (!msg) { Core.showToast('Reply cannot be empty.', 'error'); return; }

    if (statusEl) statusEl.innerHTML = '<span class="text-gray-400"><i class="fas fa-spinner fa-spin mr-1"></i>Sending...</span>';
    const fd = new FormData();
    fd.append('ticket_id', _activeConvoTicketId);
    fd.append('message',   msg);

    try {
        const d = await (await fetch('/api/store/tickets/reply', { method: 'POST', body: fd })).json();
        if (d.success) {
            Core.showToast(d.msg, 'success');
            if (input) input.value = '';
            if (statusEl) statusEl.innerHTML = '';
            await openTicketConvo(_activeConvoTicketId); // refresh messages
        } else {
            if (statusEl) statusEl.innerHTML = `<span class="text-red-500">${escapeHtml(d.msg)}</span>`;
            Core.showToast(d.msg, 'error');
        }
    } catch {
        if (statusEl) statusEl.innerHTML = '<span class="text-red-500">Connection error!</span>';
    }
}

// ─── DOMContentLoaded ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    // Apply saved theme
    const theme = localStorage.getItem('sz_theme') || 'default';
    document.documentElement.setAttribute('data-theme', theme);

    // Restore cart from localStorage — must happen before updateCartUI()
    _loadCart();
    updateCartUI();

   // Optimistic UI restore before server confirmation
const email = localStorage.getItem('store_email');
const name  = localStorage.getItem('store_name');

if (email && name) {
  updateUI(
    name,
    localStorage.getItem('bal_egp') || '0',
    localStorage.getItem('bal_usd') || '0'
  );
  _applyAvatar(localStorage.getItem('store_avatar') || '');
}

const isLoggedIn = await fetchAndApplyProfile();

// Deep-link profile tab via hash
const allowed = ['overview', 'edit', 'security', 'history', 'support'];
const hashTab = (location.hash || '').replace('#', '').trim();
const initialTab = allowed.includes(hashTab)
  ? hashTab
  : (localStorage.getItem(STORE_PROFILE_TAB_KEY) || 'overview');

// افتح المودال لو السيرفر أكد إن المستخدم داخل
// أو لو عندك optimistic auth من localStorage
if ((isLoggedIn || (email && name)) && allowed.includes(initialTab)) {
  openProfileModal();
  switchProfileTab(initialTab);
}

// طبّق الجارد بعد ما تظبط الـ state
_applyProfileAuthGuard();

    // Scroll-to-top button
    const ms = $('main-scroll'), sb = $('scrollToTopBtn');
    if (ms && sb) {
        ms.addEventListener('scroll', () => {
            const past = ms.scrollTop > 300;
            sb.classList.toggle('opacity-0', !past);
            sb.classList.toggle('pointer-events-none', !past);
            sb.classList.toggle('translate-y-4', !past);
            sb.classList.toggle('opacity-100', past);
            sb.classList.toggle('translate-y-0', past);
        });
        sb.onclick = () => ms.scrollTo({ top: 0, behavior: 'smooth' });
    }
});
