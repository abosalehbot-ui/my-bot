// ============================================================
// Saleh Zone Store Engine v3.1 — Catalog View + Persistent Cart
// ============================================================

// ─── State ───────────────────────────────────────────────────────────────
let currentCurrency = 'EGP';
let pendingPurchase  = null;
let ordersLoaded     = false;
let _forgotEmail     = '';
let _profileLoaded   = false;
let _profileBootstrapPromise = null;
const STORE_PROFILE_TAB_KEY = 'sz_active_profile_tab';
const LEGACY_STORE_AUTH_KEYS = [
    'store_email',
    'store_name',
    'store_username',
    'store_user_id',
    'store_avatar',
    'bal_egp',
    'bal_usd',
];
const storeSession = {
    loaded: false,
    loggedIn: false,
    profile: null,
};
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

function clearNode(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
}

function setInlineStatus(el, msg = '', { iconClass = '', textClass = '' } = {}) {
    if (!el) return;
    clearNode(el);
    if (!msg) return;

    const span = document.createElement('span');
    if (textClass) span.className = textClass;
    if (iconClass) {
        const icon = document.createElement('i');
        icon.className = iconClass;
        span.appendChild(icon);
    }
    span.appendChild(document.createTextNode(msg));
    el.appendChild(span);
}

function normalizeStoreProfile(data = {}) {
    return {
        user_id: data.user_id ?? '',
        name: data.name ?? '',
        username: data.username ?? '',
        email: data.email ?? '',
        balance_egp: data.balance_egp ?? 0,
        balance_usd: data.balance_usd ?? 0,
        avatar: data.avatar ?? '',
        created_at: data.created_at ?? '',
    };
}

function getStoreProfile() {
    return storeSession.profile ? { ...storeSession.profile } : null;
}

function getStoreBalance(currency) {
    const profile = storeSession.profile;
    if (!profile) return 0;
    return profile[`balance_${String(currency || '').toLowerCase()}`] ?? 0;
}

function setStoreSession(profile) {
    if (!profile) {
        storeSession.loaded = true;
        storeSession.loggedIn = false;
        storeSession.profile = null;
        return;
    }

    storeSession.loaded = true;
    storeSession.loggedIn = true;
    storeSession.profile = normalizeStoreProfile(profile);
}

function clearLegacyAuthCache() {
    LEGACY_STORE_AUTH_KEYS.forEach(key => localStorage.removeItem(key));
}

function mergeStoreProfile(updates = {}) {
    if (!storeSession.profile) return;
    setStoreSession({ ...storeSession.profile, ...updates });
}

function applyBalanceSnapshot(balances = {}) {
    if (!storeSession.profile) return;
    mergeStoreProfile({
        balance_egp: balances.balance_egp ?? storeSession.profile.balance_egp ?? 0,
        balance_usd: balances.balance_usd ?? storeSession.profile.balance_usd ?? 0,
    });
    updateUI(storeSession.profile);
    _fillProfileUI(storeSession.profile);
}

function getProductPrice(pricesObj, currency) {
    if (!pricesObj || !currency) return null;

    const rawPrice = pricesObj[currency] ?? pricesObj[String(currency).toLowerCase()];
    if (rawPrice == null || rawPrice === '') return null;

    const numericPrice = Number(rawPrice);
    return Number.isFinite(numericPrice) ? numericPrice : null;
}

function splitCartItemsByCurrency(currency) {
    const purchasable = [];
    const unavailable = [];

    cart.forEach(item => {
        const price = getProductPrice(item.prices, currency);
        if (price == null) {
            unavailable.push(item);
            return;
        }
        purchasable.push({ item, price });
    });

    return { purchasable, unavailable };
}

function removePurchasedCartItems(results = []) {
    const purchasedCounts = new Map();
    results.forEach(result => {
        const stockKey = String(result?.stock_key || '').trim();
        if (!stockKey) return;
        purchasedCounts.set(stockKey, (purchasedCounts.get(stockKey) || 0) + 1);
    });

    cart = cart.reduce((items, item) => {
        const stockKey = String(item.stock_key || '').trim();
        const purchasedCount = purchasedCounts.get(stockKey) || 0;
        if (!purchasedCount) {
            items.push(item);
            return items;
        }

        const currentQty = Number(item.qty || 0);
        const leftoverQty = Math.max(currentQty - purchasedCount, 0);
        purchasedCounts.set(stockKey, Math.max(purchasedCount - currentQty, 0));
        if (leftoverQty > 0) {
            items.push({ ...item, qty: leftoverQty });
        }
        return items;
    }, []);
}

async function ensureStoreSessionLoaded(forceRefresh = false) {
    if (storeSession.loaded && !forceRefresh) return storeSession.loggedIn;
    if (_profileBootstrapPromise && !forceRefresh) return _profileBootstrapPromise;

    _profileBootstrapPromise = fetchAndApplyProfile(forceRefresh)
        .finally(() => { _profileBootstrapPromise = null; });
    return _profileBootstrapPromise;
}

function requireStoreAuth() {
    if (storeSession.loggedIn) return true;
    openAuthModal('signin');
    return false;
}

// ─── Modal ───────────────────────────────────────────────────────────────
function openModal(id)  { $(id)?.classList.remove('hidden'); }
function closeModal(id) { $(id)?.classList.add('hidden'); }
function openAuthModal(view) { openModal('auth-modal'); switchAuthView(view); }

// ─── Toast ───────────────────────────────────────────────────────────────
function setStatus(msg, isError = false) {
    setInlineStatus($('auth-status'), msg, {
        textClass: isError ? 'text-red-500' : 'text-szcyan',
    });
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

    if (!$('cart-modal')?.classList.contains('hidden')) {
        openCartModal();
    }
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
function updateUI(profile) {
    const currentProfile = profile ? normalizeStoreProfile(profile) : storeSession.profile;
    if (!currentProfile) {
        _applyGuestUI();
        return;
    }

    $('sidebar-guest')?.classList.add('hidden');
    $('sidebar-user')?.classList.remove('hidden');
    $('sidebar-logout-btn')?.classList.remove('hidden');

    setText('sidebar-ui-name', currentProfile.name);
    setText('sidebar-ui-bal-egp', currentProfile.balance_egp ?? '0');
    setText('sidebar-ui-bal-usd', currentProfile.balance_usd ?? '0');
    setText('sidebar-ui-username', currentProfile.username ? '@' + currentProfile.username : '');
}

// ─── Avatar Helper ───────────────────────────────────────────────────────
function _applyAvatar(src) {
    document.querySelectorAll('.avatar-placeholder').forEach(el => el.classList.toggle('hidden', !!src));
    document.querySelectorAll('.avatar-img').forEach(el => {
        if (src) { el.src = src; el.classList.remove('hidden'); }
        else el.classList.add('hidden');
    });
}

function _resetProfileUI() {
    setText('prof-name', '...');
    setText('prof-email', '...');
    setText('prof-username', '-');
    setText('prof-user-id', '');
    setText('prof-bal-egp', '0');
    setText('prof-bal-usd', '0');
    setText('prof-joined', '');
    if ($('edit-name')) $('edit-name').value = '';
    if ($('edit-username')) $('edit-username').value = '';
}

// ─── Save & Login ────────────────────────────────────────────────────────
async function saveAndLogin(data) {
    const loggedIn = await ensureStoreSessionLoaded(true);
    if (!loggedIn) {
        setStatus('Unable to confirm your session. Please try again.', true);
        return;
    }

    closeModal('auth-modal');
    Core.showToast(`Welcome, ${(getStoreProfile()?.name || data?.name || 'back')}!`);
}

function _clearAuthLocalState() {
    clearLegacyAuthCache();
}

function _applyGuestUI() {
    $('sidebar-guest')?.classList.remove('hidden');
    $('sidebar-user')?.classList.add('hidden');
    $('sidebar-logout-btn')?.classList.add('hidden');
    _applyAvatar('');
}

async function logout() {
    try {
        await fetch('/api/store/logout', { method: 'POST', credentials: 'same-origin' });
    } catch {}
    setStoreSession(null);
    _clearAuthLocalState();
    _profileLoaded = false;
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
    setStatus('Signing in...');
    const fd = new FormData();
    fd.append('credential', response.credential);
    try {
        const d = await (await fetch('/api/store/google-login', {
            method: 'POST',
            body: fd,
            credentials: 'same-origin',
        })).json();
        if (d.success) saveAndLogin(d); else setStatus(d.msg, true);
    } catch { setStatus('Error!', true); }
}

async function onTelegramAuth(user) {
    if (!user?.id || !user?.auth_date || !user?.hash) {
        setStatus('Telegram login payload is incomplete.', true);
        return;
    }

    setStatus('Signing in...');
    const fd = new FormData();
    Object.entries(user).forEach(([key, value]) => {
        if (value != null) fd.append(key, value);
    });
    try {
        const d = await (await fetch('/api/store/telegram-login', {
            method: 'POST',
            body: fd,
            credentials: 'same-origin',
        })).json();
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
async function buyProduct(stock_key, pricesObj, name, imageUrl, iconClass) {
    await ensureStoreSessionLoaded();
    if (!requireStoreAuth()) return;

    const finalPrice = getProductPrice(pricesObj, currentCurrency);
    if (finalPrice == null) {
        Core.showToast(`This item is not available in ${currentCurrency} yet.`, 'error');
        return;
    }

    pendingPurchase = { stock_key, price: finalPrice, currency: currentCurrency, imageUrl, iconClass };

    const priceText = finalPrice + ' ' + currentCurrency;
    const pColor    = currentCurrency === 'EGP' ? 'text-yellow-500'
                    : currentCurrency === 'USD' ? 'text-szcyan'
                    : 'text-szgreen';
    const profile = getStoreProfile();

    setText('checkout-user-name',  profile?.name || '');
    setText('checkout-user-email', profile?.email || '');
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
function createIdempotencyKey(prefix = 'checkout') {
    if (window.crypto?.randomUUID) {
        return `${prefix}-${window.crypto.randomUUID()}`;
    }
    return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function revealOrderCode(orderId) {
    const fd = new FormData();
    fd.append('order_id', orderId);

    const res = await fetch('/api/store/orders/reveal', {
        method: 'POST',
        body: fd,
        credentials: 'same-origin',
        cache: 'no-store',
    });
    return res.json();
}

function renderDeliveryHtml(deliveries) {
    if (!deliveries?.length) {
        return '<div class="text-xs text-gray-500">No delivery details available.</div>';
    }

    return deliveries.map((delivery) => {
        const meta = `${escapeHtml(delivery.stock_key || 'Item')} - ${escapeHtml(String(delivery.price ?? ''))} ${escapeHtml(delivery.currency || '')}`;
        if (delivery.success) {
            return `<div class="bg-black border border-szgreen/30 rounded-lg p-3 mb-2">
                <div class="text-[10px] text-gray-500 mb-1">${meta}</div>
                <div class="text-szgreen font-mono font-bold select-all break-all">${escapeHtml(delivery.code)}</div>
            </div>`;
        }

        const masked = delivery.code_masked
            ? `<div class="text-yellow-500 font-mono font-bold break-all">${escapeHtml(delivery.code_masked)}</div>`
            : '';
        return `<div class="bg-black border border-yellow-500/30 rounded-lg p-3 mb-2">
            <div class="text-[10px] text-gray-500 mb-1">${meta}</div>
            ${masked}
            <div class="text-xs text-gray-400 mt-2">${escapeHtml(delivery.msg || 'Code reveal unavailable.')}</div>
        </div>`;
    }).join('');
}

function showPurchaseSuccess(content, useHtml = false) {
    const ce = $('purchased-code');
    if (ce) {
        if (useHtml) {
            ce.innerHTML = content || 'No delivery details available.';
            ce.classList.add('text-left');
        } else {
            ce.innerText = content || '';
            ce.classList.remove('text-left');
        }
    }
    openModal('success-modal');
}

async function confirmPurchase() {
    if (!pendingPurchase) return;
    if (!$('terms-checkbox').checked) return Core.showToast('Please agree to the Terms of Service.', 'error');

    const btn = $('btn-confirm-pay'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...'; btn.disabled = true;

    const fd = new FormData();
    fd.append('stock_key', pendingPurchase.stock_key);
    fd.append('price', pendingPurchase.price);
    fd.append('currency', pendingPurchase.currency);

    try {
        const d = await (await fetch('/api/store/buy', {
            method: 'POST',
            headers: { 'Idempotency-Key': createIdempotencyKey('buy') },
            body: fd,
        })).json();

        if (d.success) {
            applyBalanceSnapshot(d.new_balances || {});
            ordersLoaded = false;
            closeModal('checkout-modal');

            try {
                const reveal = await revealOrderCode(d.order_id);
                if (reveal.success) {
                    showPurchaseSuccess(reveal.code, false);
                } else {
                    showPurchaseSuccess(renderDeliveryHtml([
                        {
                            success: false,
                            stock_key: pendingPurchase.stock_key,
                            price: pendingPurchase.price,
                            currency: pendingPurchase.currency,
                            code_masked: reveal.code_masked || d.code_masked,
                            msg: reveal.msg || 'Purchase completed, but the secure reveal step did not finish. Check your order history.',
                        },
                    ]), true);
                    if (reveal.force_logout) logout();
                }
            } catch {
                showPurchaseSuccess(renderDeliveryHtml([
                    {
                        success: false,
                        stock_key: pendingPurchase.stock_key,
                        price: pendingPurchase.price,
                        currency: pendingPurchase.currency,
                        code_masked: d.code_masked,
                        msg: 'Purchase completed, but the secure reveal request did not finish. Check your order history.',
                    },
                ]), true);
            }
        } else {
            Core.showToast(d.msg, 'error');
            if (d.force_logout) logout();
            else if (d.msg.includes('balance') || d.msg.includes('stock')) location.reload();
        }
    } catch {
        Core.showToast('An error occurred!', 'error');
    }

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
async function addToCart(stock_key, pricesObj, name, imageUrl, iconClass) {
    await ensureStoreSessionLoaded();
    if (!requireStoreAuth()) return;

    if (getProductPrice(pricesObj, currentCurrency) == null) {
        Core.showToast(`This item is not available in ${currentCurrency} yet.`, 'error');
        return;
    }

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
window.openCartModal = async function() {
    await ensureStoreSessionLoaded();
    if (!requireStoreAuth()) return;

    const container = $('cart-items-container');
    const warningEl = $('cart-currency-warning');
    const checkoutBtn = $('btn-confirm-cart');
    if (!container) return;

    if (warningEl) setInlineStatus(warningEl);

    if (cart.length === 0) {
        container.innerHTML = `
            <div class="flex flex-col items-center justify-center h-full text-gray-500 py-16">
                <i class="fas fa-shopping-cart text-6xl mb-4 opacity-30"></i>
                <p class="font-bold">Your cart is empty</p>
                <p class="text-xs mt-1 text-gray-700">Browse the store and add items</p>
            </div>`;
        const tp = $('cart-total-price');
        if (tp) { tp.innerText = '0.00 ' + currentCurrency; tp.className = 'text-2xl font-black text-szcyan'; }
        if (checkoutBtn) checkoutBtn.disabled = true;
        openModal('cart-modal');
        return;
    }

    let html  = '';
    let total = 0;
    const { purchasable, unavailable } = splitCartItemsByCurrency(currentCurrency);

    [...purchasable, ...unavailable.map(item => ({ item, price: null }))].forEach(({ item, price }) => {
        const isUnavailable = price == null;
        const itemTotal = isUnavailable ? 0 : price * item.qty;
        total += itemTotal;
        const pColor = isUnavailable
            ? 'text-red-400'
            : currentCurrency === 'EGP' ? 'text-yellow-500'
            : currentCurrency === 'USD' ? 'text-szcyan'
            : 'text-szgreen';
        const priceLabel = isUnavailable ? `Unavailable in ${currentCurrency}` : `${price} ${currentCurrency}`;
        const totalLabel = isUnavailable ? 'N/A' : itemTotal.toFixed(2);
        const stateBadge = isUnavailable
            ? '<span class="text-[10px] uppercase tracking-wide text-red-400 font-bold">Waiting for pricing</span>'
            : '<span class="text-[10px] uppercase tracking-wide text-gray-500 font-bold">Ready</span>';

        html += `
        <div class="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-black border ${isUnavailable ? 'border-red-900/40' : 'border-gray-800'} rounded-xl mb-3 hover:border-szcyan/50 transition gap-4">
            <div class="flex items-center gap-3 flex-1 min-w-0">
                <div class="w-10 h-10 rounded-lg bg-szcyan/10 border border-szcyan/20 flex items-center justify-center text-szcyan shrink-0 overflow-hidden">
                    ${item.image
                        ? `<img src="${item.image}" alt="${item.name}" class="w-full h-full object-cover">`
                        : `<i class="fas ${item.iconClass || 'fa-box'} text-sm"></i>`}
                </div>
                <div class="min-w-0">
                    <div class="flex items-center gap-2 flex-wrap">
                        <h4 class="text-white font-bold text-sm truncate">${item.name}</h4>
                        ${stateBadge}
                    </div>
                    <div class="${pColor} font-black text-sm">${priceLabel}
                        ${isUnavailable ? '' : '<span class="text-gray-500 text-[10px] font-bold uppercase ml-1">each</span>'}
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
                <div class="${pColor} font-black text-sm w-20 text-right">${totalLabel}</div>
                <button onclick="removeFromCart('${item.stock_key}')"
                    class="text-red-500 hover:text-white hover:bg-red-600 bg-red-900/20 w-9 h-9 rounded-lg flex items-center justify-center transition shrink-0">
                    <i class="fas fa-trash-alt text-xs"></i>
                </button>
            </div>
        </div>`;
    });

    container.innerHTML = html;

    if (warningEl && unavailable.length > 0) {
        setInlineStatus(warningEl, `${unavailable.length} cart item${unavailable.length === 1 ? '' : 's'} will stay in your cart until ${currentCurrency} pricing is available.`, {
            iconClass: 'fas fa-exclamation-triangle mr-1',
            textClass: 'text-yellow-500',
        });
    }

    const tColor  = currentCurrency === 'EGP' ? 'text-yellow-500'
                  : currentCurrency === 'USD' ? 'text-szcyan'
                  : 'text-szgreen';
    const totalEl = $('cart-total-price');
    if (totalEl) {
        totalEl.innerText  = total.toFixed(2) + ' ' + currentCurrency;
        totalEl.className  = `text-2xl font-black ${purchasable.length ? tColor : 'text-gray-500'}`;
    }

    if (checkoutBtn) checkoutBtn.disabled = purchasable.length === 0;
    openModal('cart-modal');
};

/**
 * confirmCartPurchase()
 * Sends all cart items to the backend checkout endpoint in one request.
 */
async function confirmCartPurchase() {
    if (cart.length === 0) return Core.showToast('Your cart is empty.', 'error');
    if (!$('cart-terms-checkbox').checked) return Core.showToast('Please agree to the Terms of Service.', 'error');

    const { purchasable, unavailable } = splitCartItemsByCurrency(currentCurrency);
    if (!purchasable.length) {
        Core.showToast(`No cart items are available in ${currentCurrency} right now.`, 'error');
        await openCartModal();
        return;
    }

    const btn = $('btn-confirm-cart'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...'; btn.disabled = true;

    const cartItems = purchasable.map(({ item, price }) => ({
        stock_key: item.stock_key,
        quantity: item.qty,
        price,
        currency: currentCurrency,
    }));

    try {
        const res = await fetch('/api/store/checkout-cart', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Idempotency-Key': createIdempotencyKey('cart'),
            },
            credentials: 'same-origin',
            body: JSON.stringify({ cart: cartItems }),
        });
        const d = await res.json();

        if (d.success) {
            const processedResults = Array.isArray(d.results) ? d.results : [];
            applyBalanceSnapshot(d.new_balances || {});
            removePurchasedCartItems(processedResults);
            _saveCart();
            updateCartUI();
            ordersLoaded = false;
            closeModal('cart-modal');

            const deliveries = await Promise.all(processedResults.map(async (result) => {
                try {
                    const reveal = await revealOrderCode(result.order_id);
                    if (reveal.success) {
                        return {
                            success: true,
                            stock_key: result.stock_key,
                            price: result.price,
                            currency: result.currency,
                            code: reveal.code,
                        };
                    }

                    return {
                        success: false,
                        stock_key: result.stock_key,
                        price: result.price,
                        currency: result.currency,
                        code_masked: reveal.code_masked || result.code_masked,
                        msg: reveal.msg || 'Code reveal unavailable.',
                        force_logout: reveal.force_logout,
                    };
                } catch {
                    return {
                        success: false,
                        stock_key: result.stock_key,
                        price: result.price,
                        currency: result.currency,
                        code_masked: result.code_masked,
                        msg: 'Purchase completed, but the secure reveal request did not finish. Check your order history.',
                    };
                }
            }));

            const remainingCount = cart.reduce((sum, item) => sum + Number(item.qty || 0), 0);
            if (remainingCount > 0) {
                Core.showToast(`${remainingCount} item${remainingCount === 1 ? '' : 's'} stayed in your cart and were not charged.`, 'success');
            } else if (unavailable.length > 0) {
                Core.showToast(`${unavailable.length} item${unavailable.length === 1 ? '' : 's'} stayed in your cart because ${currentCurrency} pricing is unavailable.`, 'success');
            }

            if (deliveries.some(item => item.force_logout)) logout();
            showPurchaseSuccess(renderDeliveryHtml(deliveries), true);
        } else {
            Core.showToast(d.msg, 'error');
            if (d.force_logout) logout();
            await openCartModal();
        }
    } catch {
        Core.showToast('An error occurred!', 'error');
        await openCartModal();
    }

    btn.innerHTML = orig; btn.disabled = false;
}

// ─── Profile Modal ───────────────────────────────────────────────────────
function _isStoreLoggedIn() {
    return storeSession.loaded && storeSession.loggedIn;
}

function _applyProfileAuthGuard() {
    const loggedIn = _isStoreLoggedIn();

    const authContent = $('profile-auth-content');
    const required = $('profile-login-required');

    if (authContent) authContent.classList.toggle('hidden', !loggedIn);
    if (required) required.classList.toggle('hidden', loggedIn);
}

async function openProfileModal(targetTab = null) {
    openModal('profile-modal');
    const loggedIn = await ensureStoreSessionLoaded();
    _applyProfileAuthGuard();
    if (!loggedIn) return;

    const allowed = ['overview', 'edit', 'security', 'history', 'support'];
    const remembered = localStorage.getItem(STORE_PROFILE_TAB_KEY) || 'overview';
    const nextTab = allowed.includes(targetTab) ? targetTab : remembered;
    _profileLoaded = true;
    switchProfileTab(nextTab);
}

function switchProfileTab(tab) {
    if (!_isStoreLoggedIn()) return;

    ['overview', 'edit', 'security', 'history', 'support'].forEach(t => {
        const panel = $('ptab-' + t);
        const btn = $('ptab-btn-' + t);

        if (panel) panel.classList.add('hidden');

        if (btn) {
            btn.classList.remove('active');
            btn.classList.add('inactive');
        }
    });

    $('ptab-' + tab)?.classList.remove('hidden');

    const activeBtn = $('ptab-btn-' + tab);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.classList.remove('inactive');
    }

    localStorage.setItem(STORE_PROFILE_TAB_KEY, tab);

    if (tab === 'overview') {
        history.replaceState(null, '', location.pathname + location.search);
    } else {
        history.replaceState(null, '', `#${tab}`);
    }

    if (tab === 'history' && !ordersLoaded) {
        fetchMyOrders();
        fetchWalletHistory();
    }

    if (tab === 'support' && !_ticketsLoaded) {
        loadMyTickets();
    }
}

function _fillProfileUI(d) {
    const profile = normalizeStoreProfile(d || {});
    setText('prof-name', profile.name);
    setText('prof-email', profile.email);
    setText('prof-username', profile.username ? '@' + profile.username : '-');
    setText('prof-user-id', profile.user_id ? '#' + profile.user_id : '');
    setText('prof-bal-egp', profile.balance_egp ?? '0');
    setText('prof-bal-usd', profile.balance_usd ?? '0');
    setText('prof-joined', profile.created_at ?? '');

    const ni = $('edit-name');
    const ui = $('edit-username');

    if (ni) ni.value = profile.name ?? '';
    if (ui) ui.value = profile.username ?? '';

    _applyAvatar(profile.avatar || '');
}

async function fetchAndApplyProfile(forceRefresh = false) {
    if (!forceRefresh && storeSession.loaded && storeSession.profile) {
        updateUI(storeSession.profile);
        _fillProfileUI(storeSession.profile);
        _applyProfileAuthGuard();
        return true;
    }

    try {
        const res = await fetch('/api/store/me', {
            method: 'GET',
            cache: 'no-store',
            credentials: 'same-origin',
        });

        const d = await res.json();
        if (!d.success) {
            setStoreSession(null);
            clearLegacyAuthCache();
            _applyGuestUI();
            _resetProfileUI();
            return false;
        }

        setStoreSession(d);
        clearLegacyAuthCache();
        updateUI(storeSession.profile);
        _fillProfileUI(storeSession.profile);
        return true;
    } catch {
        if (!storeSession.loaded) {
            setStoreSession(null);
            _applyGuestUI();
            _resetProfileUI();
        }
        return storeSession.loggedIn;
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
            if (d.success) { mergeStoreProfile({ avatar: b64 }); updateUI(storeSession.profile); _fillProfileUI(storeSession.profile); Core.showToast('Avatar updated!'); }
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
            mergeStoreProfile({ name: d.name, username: d.username });
            updateUI(storeSession.profile);
            _fillProfileUI(storeSession.profile);
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
            mergeStoreProfile({ email: d.new_email });
            updateUI(storeSession.profile);
            _fillProfileUI(storeSession.profile);
            _setFormStatus('sec-status', d.msg, false);
            $('email-change-form').reset();
            $('email-otp-step')?.classList.add('hidden');
            $('btn-email-req')?.classList.remove('hidden');
        } else _setFormStatus('sec-status', d.msg, true);
    } catch { _setFormStatus('sec-status', 'Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

function _setFormStatus(id, msg, isError) {
    setInlineStatus($(id), msg, {
        iconClass: isError ? 'fas fa-times-circle mr-1' : 'fas fa-check-circle mr-1',
        textClass: isError ? 'text-red-500' : 'text-szgreen',
    });
}

async function revealOrderFromHistory(orderId, btn) {
    if (!orderId) return;

    const originalLabel = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    try {
        const d = await revealOrderCode(orderId);
        if (d.success) {
            ordersLoaded = false;
            showPurchaseSuccess(d.code, false);
            await fetchMyOrders();
        } else {
            Core.showToast(d.msg || 'Unable to reveal this code.', 'error');
            if (d.force_logout) logout();
            ordersLoaded = false;
            await fetchMyOrders();
        }
    } catch {
        Core.showToast('Unable to reveal this code right now.', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalLabel;
        }
    }
}

async function fetchMyOrders() {
    const loader = $('orders-loading'), tbody = $('orders-table-body');
    if (loader) loader.classList.remove('hidden');
    if (tbody) tbody.innerHTML = '';
    try {
        const d = await (await fetch('/api/store/my-orders', {
            cache: 'no-store',
            credentials: 'same-origin',
        })).json();
        if (loader) loader.classList.add('hidden');
        if (d.force_logout) {
            logout();
            return;
        }
        if (d.success && d.orders.length > 0) {
            tbody.innerHTML = d.orders.map(o => {
                const pc = o.currency === 'USD' ? 'text-szcyan' : 'text-yellow-500';
                const orderId = String(o.order_id || '');
                const codeMasked = escapeHtml(o.code_masked || 'Hidden');
                const actionHtml = o.can_reveal
                    ? `<button onclick="revealOrderFromHistory('${orderId}', this)" class="bg-gray-900 text-szgreen border border-gray-700 px-3 py-1 rounded text-xs font-mono hover:bg-szgreen hover:text-black transition">Reveal Once</button>`
                    : '<span class="text-[10px] uppercase tracking-wide text-gray-500 font-bold">Revealed</span>';
                return `<tr class="hover:bg-[#111] transition">
                    <td class="px-4 py-3 font-mono text-szcyan">#${escapeHtml(orderId)}</td>
                    <td class="px-4 py-3 text-xs text-gray-500">${escapeHtml(o.date)}</td>
                    <td class="px-4 py-3 font-bold text-white">${escapeHtml(o.category)}</td>
                    <td class="px-4 py-3 font-black ${pc}">${escapeHtml(String(o.price))} <span class="text-[10px] text-gray-500">${escapeHtml(o.currency)}</span></td>
                    <td class="px-4 py-3"><div class="flex flex-wrap items-center gap-2"><span class="font-mono text-szgreen break-all">${codeMasked}</span>${actionHtml}</div></td>
                </tr>`;
            }).join('');
            ordersLoaded = true;
        } else if (tbody) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500 font-bold">No purchases found.</td></tr>';
        }
    } catch {
        if (loader) loader.innerHTML = '<span class="text-red-500">Error loading orders.</span>';
    }
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
// Support Tickets - Customer Side (transport + sanitized rendering)
// ============================================================
let _activeConvoTicketId = '';
let _ticketsLoaded = false;
let _storeChatSocket = null;
let _storeChatJoinedThread = '';
let _storeChatReconnectTimer = null;
let _storeChatConnected = false;
let _activeCustomerPresence = null;

function clearChildren(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
}

function appendTextNode(parent, tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = text ?? '';
    parent?.appendChild(el);
    return el;
}

function appendIconText(parent, iconClass, text, className = '') {
    const wrap = document.createElement('span');
    if (className) wrap.className = className;
    if (iconClass) {
        const icon = document.createElement('i');
        icon.className = iconClass;
        wrap.appendChild(icon);
        wrap.appendChild(document.createTextNode(' '));
    }
    wrap.appendChild(document.createTextNode(text ?? ''));
    parent?.appendChild(wrap);
    return wrap;
}

function setTicketStatusMessage(el, msg = '', type = 'neutral') {
    if (!el) return;
    clearChildren(el);
    if (!msg) return;

    const cls = type === 'error'
        ? 'text-red-500'
        : type === 'success'
            ? 'text-szgreen'
            : 'text-gray-400';
    const iconClass = type === 'error'
        ? 'fas fa-times-circle mr-1'
        : type === 'success'
            ? 'fas fa-check-circle mr-1'
            : 'fas fa-spinner fa-spin mr-1';

    const span = document.createElement('span');
    span.className = cls;
    const icon = document.createElement('i');
    icon.className = iconClass;
    span.appendChild(icon);
    span.appendChild(document.createTextNode(msg));
    el.appendChild(span);
}

function renderCustomerLiveStatus() {
    const host = $('convo-live-status');
    if (!host) return;

    if (!_activeConvoTicketId) {
        clearChildren(host);
        return;
    }

    let msg = 'Connecting to support...';
    let textClass = 'text-gray-500';
    let iconClass = 'fas fa-circle-notch fa-spin mr-1';

    if (_storeChatConnected) {
        if (_activeCustomerPresence?.admin_online) {
            msg = 'Support is online';
            textClass = 'text-szgreen';
            iconClass = 'fas fa-circle mr-1';
        } else {
            msg = 'Support replies will appear here when a merchant joins';
            iconClass = 'far fa-clock mr-1';
        }
    }

    setInlineStatus(host, msg, { iconClass, textClass });
}

function customerTicketStatusClasses(status) {
    return {
        open: 'text-green-400 border-green-900/40 bg-green-900/10',
        in_progress: 'text-yellow-400 border-yellow-900/40 bg-yellow-900/10',
        closed: 'text-red-400 border-red-900/40 bg-red-900/10',
    }[status] || 'text-green-400 border-green-900/40 bg-green-900/10';
}

function buildCustomerStatusBadge(status) {
    const badge = document.createElement('span');
    badge.className = `text-[10px] font-bold border px-2 py-0.5 rounded shrink-0 ${customerTicketStatusClasses(status)}`;
    badge.textContent = String(status || 'open').replace('_', ' ');
    return badge;
}

function buildCustomerTicketListItem(ticket) {
    const item = document.createElement('div');
    item.className = 'cursor-pointer bg-black border border-gray-800 rounded-xl p-3 hover:border-szcyan/50 transition group';
    item.addEventListener('click', () => openTicketConvo(ticket.ticket_id));

    const top = document.createElement('div');
    top.className = 'flex items-start justify-between gap-2 mb-1';
    item.appendChild(top);

    appendTextNode(top, 'span', 'text-white font-bold text-xs leading-tight flex-1 group-hover:text-szcyan transition', ticket.subject || 'Untitled Ticket');
    top.appendChild(buildCustomerStatusBadge(ticket.status));

    if (ticket.last_message_preview) {
        appendTextNode(item, 'p', 'text-[10px] text-gray-600 mb-1 truncate', ticket.last_message_preview);
    }

    const meta = document.createElement('div');
    meta.className = 'flex items-center justify-between text-[10px] text-gray-600 gap-2';
    item.appendChild(meta);

    appendTextNode(meta, 'span', 'font-mono', ticket.ticket_id || '');
    appendIconText(meta, 'fas fa-comments mr-1', `${Number(ticket.message_count || 0)} msg${Number(ticket.message_count || 0) !== 1 ? 's' : ''}`);
    appendTextNode(meta, 'span', '', ticket.created_at || '');

    return item;
}

function buildCustomerMessageNode(message) {
    const isAdmin = message.sender === 'admin';
    const wrap = document.createElement('div');
    wrap.className = `${isAdmin ? 'bg-szgreen/10 border-szgreen/20 ml-4' : 'bg-szcyan/10 border-szcyan/20 mr-4'} border rounded-xl p-3`;
    wrap.dataset.messageId = message.message_id || '';

    const header = document.createElement('div');
    header.className = 'flex items-center justify-between gap-3 mb-1';
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
    appendTextNode(header, 'span', 'text-[10px] text-gray-600 shrink-0', message.time || '');

    const body = document.createElement('p');
    body.className = 'text-sm text-gray-200 whitespace-pre-wrap leading-relaxed';
    body.textContent = message.message || '';
    wrap.appendChild(body);

    return wrap;
}

function renderCustomerTicketList(tickets) {
    const list = $('my-tickets-list');
    if (!list) return;
    clearChildren(list);

    if (!tickets.length) {
        appendTextNode(list, 'p', 'text-center text-gray-600 text-xs font-bold py-4', 'No tickets found. Submit your first ticket above.');
        return;
    }

    tickets.forEach(ticket => list.appendChild(buildCustomerTicketListItem(ticket)));
}

function renderCustomerConversation(thread, messages) {
    if ($('convo-subject')) $('convo-subject').innerText = thread.subject || '';

    const badgeHost = $('convo-status-badge');
    if (badgeHost) {
        clearChildren(badgeHost);
        badgeHost.appendChild(buildCustomerStatusBadge(thread.status));
    }

    const replySection = $('convo-reply-section');
    if (replySection) replySection.style.display = thread.status === 'closed' ? 'none' : '';
    renderCustomerLiveStatus();

    const msgContainer = $('convo-messages');
    if (!msgContainer) return;
    clearChildren(msgContainer);

    if (!messages.length) {
        appendTextNode(msgContainer, 'p', 'text-center text-gray-600 text-xs py-6', 'No messages yet.');
        return;
    }

    messages.forEach(message => msgContainer.appendChild(buildCustomerMessageNode(message)));
    msgContainer.scrollTop = msgContainer.scrollHeight;
}

function appendCustomerIncomingMessage(message) {
    const msgContainer = $('convo-messages');
    if (!msgContainer) return;
    const duplicate = Array.from(msgContainer.children).some(node => node.dataset?.messageId === message.message_id);
    if (duplicate) return;
    msgContainer.appendChild(buildCustomerMessageNode(message));
    msgContainer.scrollTop = msgContainer.scrollHeight;
}

function storeChatSocketUrl(role = 'customer') {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}/ws/store-chat?role=${encodeURIComponent(role)}`;
}

function sendStoreChatAction(payload) {
    if (!_storeChatSocket || _storeChatSocket.readyState !== WebSocket.OPEN) return false;
    _storeChatSocket.send(JSON.stringify(payload));
    return true;
}

function joinActiveCustomerThread() {
    if (!_activeConvoTicketId || _storeChatSocket?.readyState !== WebSocket.OPEN) return;
    _storeChatJoinedThread = _activeConvoTicketId;
    sendStoreChatAction({ action: 'join_room', thread_id: _activeConvoTicketId });
}

function scheduleStoreChatReconnect() {
    if (_storeChatReconnectTimer || !_activeConvoTicketId) return;
    _storeChatReconnectTimer = window.setTimeout(() => {
        _storeChatReconnectTimer = null;
        ensureStoreChatSocket();
    }, 1500);
}

function applyCustomerThreadStatus(thread) {
    const badgeHost = $('convo-status-badge');
    if (badgeHost) {
        clearChildren(badgeHost);
        badgeHost.appendChild(buildCustomerStatusBadge(thread.status));
    }
    const replySection = $('convo-reply-section');
    if (replySection) replySection.style.display = thread.status === 'closed' ? 'none' : '';
    renderCustomerLiveStatus();
}

function handleStoreChatSocketMessage(event) {
    let payload = null;
    try {
        payload = JSON.parse(event.data);
    } catch {
        return;
    }

    if (payload.event === 'system:connected') {
        _storeChatConnected = true;
        renderCustomerLiveStatus();
        joinActiveCustomerThread();
        return;
    }

    if (payload.event === 'system:joined') {
        if (payload.thread) applyCustomerThreadStatus(payload.thread);
        if (payload.thread_id === _activeConvoTicketId) {
            sendStoreChatAction({ action: 'mark_read', thread_id: _activeConvoTicketId });
        }
        return;
    }

    if (payload.event === 'message:new') {
        if (payload.thread_id === _activeConvoTicketId && payload.message) {
            appendCustomerIncomingMessage(payload.message);
            if (payload.thread) applyCustomerThreadStatus(payload.thread);
            if (payload.message.sender !== 'customer') {
                sendStoreChatAction({ action: 'mark_read', thread_id: payload.thread_id });
            }
        }
        loadMyTickets();
        return;
    }

    if (payload.event === 'thread:status_changed') {
        if (payload.thread_id === _activeConvoTicketId && payload.thread) {
            applyCustomerThreadStatus(payload.thread);
        }
        loadMyTickets();
        return;
    }

    if (payload.event === 'message:read') {
        if (payload.thread) applyCustomerThreadStatus(payload.thread);
        loadMyTickets();
        return;
    }

    if (payload.event === 'presence') {
        if (payload.thread_id === _activeConvoTicketId) {
            _activeCustomerPresence = payload.presence || null;
            renderCustomerLiveStatus();
        }
        return;
    }

    if (payload.event === 'error' && payload.msg) {
        Core.showToast(payload.msg, 'error');
    }
}

function ensureStoreChatSocket() {
    if (_storeChatSocket && (_storeChatSocket.readyState === WebSocket.OPEN || _storeChatSocket.readyState === WebSocket.CONNECTING)) {
        return;
    }

    _storeChatSocket = new WebSocket(storeChatSocketUrl('customer'));
    _storeChatSocket.addEventListener('open', () => {
        _storeChatConnected = true;
        renderCustomerLiveStatus();
        joinActiveCustomerThread();
    });
    _storeChatSocket.addEventListener('message', handleStoreChatSocketMessage);
    _storeChatSocket.addEventListener('close', () => {
        _storeChatConnected = false;
        _storeChatJoinedThread = '';
        renderCustomerLiveStatus();
        scheduleStoreChatReconnect();
    });
}

async function loadMyTickets() {
    const list = $('my-tickets-list');
    const loader = $('my-tickets-loading');
    if (!list) return;
    if (loader) loader.classList.remove('hidden');
    clearChildren(list);

    try {
        const d = await (await fetch('/api/store/tickets/my', {
            cache: 'no-store',
            credentials: 'same-origin',
        })).json();
        if (loader) loader.classList.add('hidden');
        if (!d.success) {
            if (d.force_logout) logout();
            renderCustomerTicketList([]);
            return;
        }
        renderCustomerTicketList(d.tickets || []);
        _ticketsLoaded = true;
    } catch {
        if (loader) loader.classList.add('hidden');
        appendTextNode(list, 'p', 'text-center text-red-500 text-xs py-4', 'Failed to load tickets.');
    }
}

async function openTicketConvo(ticketId) {
    _activeConvoTicketId = ticketId;
    _activeCustomerPresence = null;
    renderCustomerLiveStatus();
    $('support-new-ticket-section')?.classList.add('hidden');
    $('support-ticket-list-section')?.classList.add('hidden');
    const convo = $('ticket-convo-section');
    if (convo) convo.classList.remove('hidden');

    const msgContainer = $('convo-messages');
    if (msgContainer) {
        clearChildren(msgContainer);
        appendTextNode(msgContainer, 'div', 'text-center text-szcyan py-6', 'Loading conversation...');
    }

    try {
        const url = `/api/store/tickets/history?ticket_id=${encodeURIComponent(ticketId)}&page=1&limit=50`;
        const d = await (await fetch(url, { cache: 'no-store', credentials: 'same-origin' })).json();
        if (!d.success) {
            Core.showToast(d.msg || 'Ticket not found.', 'error');
            closeTicketConvo();
            return;
        }
        renderCustomerConversation(d.thread || {}, d.messages || []);
        ensureStoreChatSocket();
        if (_storeChatSocket?.readyState === WebSocket.OPEN) {
            joinActiveCustomerThread();
            sendStoreChatAction({ action: 'mark_read', thread_id: ticketId });
        }
    } catch {
        Core.showToast('Error loading ticket.', 'error');
        closeTicketConvo();
    }
}
async function submitTicket() {
    const subject = $('ticket-subject')?.value.trim();
    const message = $('ticket-message')?.value.trim();
    const statusEl = $('ticket-submit-status');

    if (!subject || !message) {
        setTicketStatusMessage(statusEl, 'Please fill in both fields.', 'error');
        return;
    }

    const btn = document.querySelector('[onclick="submitTicket()"]');
    const orig = btn?.innerHTML;
    if (btn) {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>Submitting...';
        btn.disabled = true;
    }
    setTicketStatusMessage(statusEl, 'Submitting...', 'pending');

    const fd = new FormData();
    fd.append('subject', subject);
    fd.append('message', message);

    try {
        const d = await (await fetch('/api/store/tickets/create', { method: 'POST', body: fd })).json();
        if (d.success) {
            Core.showToast(d.msg, 'success');
            if ($('ticket-subject')) $('ticket-subject').value = '';
            if ($('ticket-message')) $('ticket-message').value = '';
            setTicketStatusMessage(statusEl, d.msg, 'success');
            _ticketsLoaded = false;
            ensureStoreChatSocket();
            await loadMyTickets();
        } else {
            setTicketStatusMessage(statusEl, d.msg || 'Unable to submit ticket.', 'error');
            Core.showToast(d.msg, 'error');
            if (d.force_logout) logout();
        }
    } catch {
        setTicketStatusMessage(statusEl, 'Connection error!', 'error');
    }

    if (btn) {
        btn.innerHTML = orig;
        btn.disabled = false;
    }
}

function closeTicketConvo() {
    if (_activeConvoTicketId && _storeChatSocket?.readyState === WebSocket.OPEN) {
        sendStoreChatAction({ action: 'leave_room', thread_id: _activeConvoTicketId });
    }
    _activeConvoTicketId = '';
    _activeCustomerPresence = null;
    _storeChatJoinedThread = '';
    $('ticket-convo-section')?.classList.add('hidden');
    $('support-new-ticket-section')?.classList.remove('hidden');
    $('support-ticket-list-section')?.classList.remove('hidden');
    if ($('convo-reply-input')) $('convo-reply-input').value = '';
    setTicketStatusMessage($('convo-reply-status'));
    renderCustomerLiveStatus();
}

async function sendCustomerReply() {
    if (!_activeConvoTicketId) return;
    const input = $('convo-reply-input');
    const statusEl = $('convo-reply-status');
    const msg = input?.value.trim();
    if (!msg) {
        Core.showToast('Reply cannot be empty.', 'error');
        return;
    }

    setTicketStatusMessage(statusEl, 'Sending...', 'pending');
    ensureStoreChatSocket();
    if (sendStoreChatAction({ action: 'send_message', thread_id: _activeConvoTicketId, message: msg })) {
        if (input) input.value = '';
        setTicketStatusMessage(statusEl);
        return;
    }

    const fd = new FormData();
    fd.append('ticket_id', _activeConvoTicketId);
    fd.append('message', msg);

    try {
        const d = await (await fetch('/api/store/tickets/reply', { method: 'POST', body: fd })).json();
        if (d.success) {
            Core.showToast(d.msg, 'success');
            if (input) input.value = '';
            setTicketStatusMessage(statusEl);
            await openTicketConvo(_activeConvoTicketId);
        } else {
            setTicketStatusMessage(statusEl, d.msg || 'Unable to send reply.', 'error');
            Core.showToast(d.msg, 'error');
        }
    } catch {
        setTicketStatusMessage(statusEl, 'Connection error!', 'error');
    }
}
document.addEventListener('DOMContentLoaded', async () => {
    const theme = localStorage.getItem('sz_theme') || 'default';
    document.documentElement.setAttribute('data-theme', theme);

    _loadCart();
    updateCartUI();
    clearLegacyAuthCache();
    _resetProfileUI();
    _applyGuestUI();

    const isLoggedIn = await ensureStoreSessionLoaded(true);

    const allowed = ['overview', 'edit', 'security', 'history', 'support'];
    const hashTab = (location.hash || '').replace('#', '').trim();

    if (isLoggedIn && allowed.includes(hashTab)) {
        await openProfileModal(hashTab);
    }

    _applyProfileAuthGuard();

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


























// ============================================================
// Storefront Upgrade Overrides (Preorders, Wallet Requests, Unified Chat)
// ============================================================
const STORE_FRONT_BOOT = window.STORE_FRONT_BOOTSTRAP || {};
const STOREFRONT_PRODUCT_INDEX = {};
let walletRequestType = 'deposit';
let liveChatThreadId = '';
let liveChatSocket = null;
let liveChatConnected = false;
let liveChatPresence = null;
let liveChatMessages = [];

(function buildStorefrontIndex() {
    const categories = Array.isArray(STORE_FRONT_BOOT.categories) ? STORE_FRONT_BOOT.categories : [];
    categories.forEach((category) => {
        (category.products || []).forEach((product) => {
            STOREFRONT_PRODUCT_INDEX[product.stock_key] = {
                ...product,
                category_id: category._id,
                category_name: category.name,
                category_icon: category.icon,
                category_description: category.description,
                category_estimated_completion_time: category.estimated_completion_time,
                category_is_active: category.is_active,
            };
        });
    });
})();

function storefrontProductMeta(stockKey) {
    return STOREFRONT_PRODUCT_INDEX[String(stockKey || '').trim()] || {};
}

function setCheckoutMeta(meta = {}) {
    setText('checkout-item-description', meta.effective_description || meta.category_description || 'Product details appear here.');
    setText('checkout-item-eta', meta.effective_estimated_completion_time || meta.category_estimated_completion_time || 'Completion time appears here.');
    const manualHost = $('checkout-manual-fields');
    if (manualHost) manualHost.classList.toggle('hidden', !meta.requires_id_fulfillment);
    if (!meta.requires_id_fulfillment) {
        if ($('checkout-player-id')) $('checkout-player-id').value = '';
        if ($('checkout-player-name')) $('checkout-player-name').value = '';
        if ($('checkout-scheduled-time')) $('checkout-scheduled-time').value = '';
    }
}

buyProduct = async function buyProduct(stock_key, pricesObj, name, imageUrl, iconClass) {
    await ensureStoreSessionLoaded();
    if (!requireStoreAuth()) return;

    const meta = storefrontProductMeta(stock_key);
    if (meta && meta.effective_is_active === false) {
        Core.showToast('This item is temporarily disabled right now.', 'error');
        return;
    }

    const finalPrice = getProductPrice(pricesObj, currentCurrency);
    if (finalPrice == null) {
        Core.showToast(`This item is not available in ${currentCurrency} yet.`, 'error');
        return;
    }

    pendingPurchase = {
        stock_key,
        price: finalPrice,
        currency: currentCurrency,
        imageUrl,
        iconClass,
        name,
        requires_id_fulfillment: Boolean(meta.requires_id_fulfillment),
        effective_description: meta.effective_description || meta.category_description || '',
        effective_estimated_completion_time: meta.effective_estimated_completion_time || meta.category_estimated_completion_time || '',
    };

    const priceText = `${finalPrice} ${currentCurrency}`;
    const pColor = currentCurrency === 'EGP' ? 'text-yellow-500' : currentCurrency === 'USD' ? 'text-szcyan' : 'text-szgreen';
    const profile = getStoreProfile();

    setText('checkout-user-name', profile?.name || '');
    setText('checkout-user-email', profile?.email || '');
    setText('checkout-item-name', name);
    setCheckoutMeta(meta);

    const icon = $('checkout-item-icon');
    const img = $('checkout-item-image');
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

    const priceEl = $('checkout-item-price');
    if (priceEl) { priceEl.innerText = priceText; priceEl.className = `p-4 text-right font-black text-lg ${pColor}`; }
    const totalEl = $('checkout-total-price');
    if (totalEl) { totalEl.innerText = priceText; totalEl.className = `text-2xl font-black ${pColor}`; }

    openModal('checkout-modal');
};

confirmPurchase = async function confirmPurchase() {
    if (!pendingPurchase) return;
    if (!$('terms-checkbox').checked) {
        Core.showToast('Please agree to the Terms of Service.', 'error');
        return;
    }

    const playerId = $('checkout-player-id')?.value.trim() || '';
    const playerName = $('checkout-player-name')?.value.trim() || '';
    const scheduledTime = $('checkout-scheduled-time')?.value || '';
    if (pendingPurchase.requires_id_fulfillment && (!playerId || !playerName)) {
        Core.showToast('Player ID and Player Name are required for this item.', 'error');
        return;
    }

    const btn = $('btn-confirm-pay');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/store/checkout-cart', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'Idempotency-Key': createIdempotencyKey('checkout'),
            },
            body: JSON.stringify({
                cart: [
                    {
                        stock_key: pendingPurchase.stock_key,
                        price: pendingPurchase.price,
                        currency: pendingPurchase.currency,
                        quantity: 1,
                        player_id: playerId,
                        player_name: playerName,
                        scheduled_time: scheduledTime,
                    },
                ],
            }),
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            Core.showToast(data.msg || 'Unable to submit preorder.', 'error');
            if (data.force_logout) logout();
            return;
        }

        applyBalanceSnapshot(data.new_balances || {});
        ordersLoaded = false;
        closeModal('checkout-modal');
        showPurchaseSuccess(`Pre-order ${data.order_id || ''} submitted. State: ${String(data.delivery_state || 'preorder').replace(/_/g, ' ')}`, false);
        await fetchMyOrders();
        await fetchWalletHistory();
        if (data.has_live_chat && data.thread_id) {
            Core.showToast('Your request is live. You can chat with an agent from My Orders.', 'success');
        }
    } catch (error) {
        Core.showToast('An error occurred while submitting your preorder.', 'error');
    } finally {
        btn.innerHTML = orig;
        btn.disabled = false;
    }
};

async function cancelOrder(orderId) {
    const fd = new FormData();
    fd.append('order_id', orderId);
    const response = await fetch('/api/store/orders/cancel', {
        method: 'POST',
        body: fd,
        credentials: 'same-origin',
    });
    return response.json();
}

function orderActionButtons(order) {
    const actions = [];
    if (order.can_reveal) {
        actions.push(`<button onclick="revealOrderFromHistory('${esc(order.order_id)}', this)" class="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1 text-[11px] font-black text-szgreen transition hover:bg-szgreen hover:text-black">Reveal</button>`);
    }
    if (order.can_cancel) {
        actions.push(`<button onclick="cancelOrderFromHistory('${esc(order.order_id)}', this)" class="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-1 text-[11px] font-black text-red-200 transition hover:bg-red-500/20">Cancel & Refund</button>`);
    }
    if (order.has_live_chat) {
        actions.push(`<button onclick="openLiveChat('${esc(order.thread_id)}', ${JSON.stringify(`Order #${order.order_id}`)})" class="rounded-lg border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-black text-cyan-100 transition hover:bg-cyan-400/20">Live Chat with Agent</button>`);
    }
    return actions.join('') || '<span class="text-[10px] uppercase tracking-wide text-gray-500 font-bold">No actions</span>';
}

async function cancelOrderFromHistory(orderId, button) {
    if (!window.confirm('Cancel this order and refund it back to your wallet?')) return;
    const original = button?.innerHTML;
    if (button) { button.disabled = true; button.innerHTML = 'Cancelling...'; }
    try {
        const data = await cancelOrder(orderId);
        if (!data.success) {
            Core.showToast(data.msg || 'Unable to cancel this order.', 'error');
            if (data.force_logout) logout();
            return;
        }
        applyBalanceSnapshot(data.new_balances || {});
        Core.showToast(data.msg || 'Order cancelled and refunded.', 'success');
        ordersLoaded = false;
        await fetchMyOrders();
        await fetchWalletHistory();
    } catch (error) {
        Core.showToast('Unable to cancel this order right now.', 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = original;
        }
    }
}

fetchMyOrders = async function fetchMyOrders() {
    const loader = $('orders-loading');
    const tbody = $('orders-table-body');
    if (loader) loader.classList.remove('hidden');
    if (tbody) tbody.innerHTML = '';
    try {
        const data = await (await fetch('/api/store/my-orders', { cache: 'no-store', credentials: 'same-origin' })).json();
        if (loader) loader.classList.add('hidden');
        if (data.force_logout) { logout(); return; }
        const orders = data.orders || [];
        if (data.success && orders.length) {
            tbody.innerHTML = orders.map((order) => {
                const priceClass = order.currency === 'USD' ? 'text-szcyan' : 'text-yellow-500';
                const stateTone = order.delivery_state === 'completed' ? 'text-emerald-200 bg-emerald-400/10 border-emerald-400/20' : ['cancelled'].includes(order.delivery_state) ? 'text-red-200 bg-red-400/10 border-red-400/20' : 'text-yellow-200 bg-yellow-400/10 border-yellow-400/20';
                const detailLines = [order.product_description, order.estimated_completion_time ? `ETA: ${order.estimated_completion_time}` : '', order.player_id ? `Player ID: ${order.player_id}` : '', order.player_name ? `Player Name: ${order.player_name}` : '', order.scheduled_time ? `Scheduled: ${order.scheduled_time}` : '', order.claimed_by_name ? `Claimed by: ${order.claimed_by_name}` : ''].filter(Boolean).map((line) => `<div>${esc(line)}</div>`).join('');
                return `<tr class="hover:bg-[#111] transition"><td class="px-4 py-3 font-mono text-szcyan">#${esc(order.order_id || '')}</td><td class="px-4 py-3 text-xs text-gray-500">${esc(order.date || '')}</td><td class="px-4 py-3"><div class="font-bold text-white">${esc(order.product_name || order.category)}</div><div class="mt-1 text-[11px] text-gray-500 space-y-1">${detailLines || '<div>No extra details.</div>'}</div></td><td class="px-4 py-3"><span class="rounded-full border px-2 py-1 text-[10px] font-black ${stateTone}">${esc(String(order.delivery_state || '').replace(/_/g, ' '))}</span></td><td class="px-4 py-3 font-black ${priceClass}">${esc(String(order.price))} <span class="text-[10px] text-gray-500">${esc(order.currency)}</span></td><td class="px-4 py-3"><div class="flex flex-wrap gap-2">${orderActionButtons(order)}</div></td></tr>`;
            }).join('');
            ordersLoaded = true;
        } else if (tbody) {
            tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-8 text-center text-gray-500 font-bold">No preorder requests found.</td></tr>';
        }
    } catch (error) {
        if (loader) loader.innerHTML = '<span class="text-red-500">Error loading orders.</span>';
    }
};

function walletRequestRow(item) {
    const stateTone = item.status === 'completed' ? 'text-emerald-200 border-emerald-400/20 bg-emerald-400/10' : item.status === 'rejected' ? 'text-red-200 border-red-400/20 bg-red-400/10' : 'text-yellow-200 border-yellow-400/20 bg-yellow-400/10';
    const actions = item.has_live_chat ? `<button onclick="openLiveChat('${esc(item.thread_id)}', ${JSON.stringify(`${String(item.type || '').toUpperCase()} Request ${item.transaction_id}`)})" class="rounded-lg border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-black text-cyan-100 transition hover:bg-cyan-400/20">Live Chat with Agent</button>` : '';
    return `<div class="rounded-xl border border-gray-800 bg-[#080808] p-3"><div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between"><div><div class="text-xs font-black text-white">${esc(String(item.type || '').toUpperCase())} - ${esc(item.payment_method_name || 'Payment Method')}</div><div class="mt-1 text-[11px] text-gray-500">Requested ${esc(money(item.requested_amount, item.currency))} - Actual ${esc(money(item.actual_received_amount, item.currency))}</div></div><div class="flex flex-wrap items-center gap-2"><span class="rounded-full border px-2 py-1 text-[10px] font-black ${stateTone}">${esc(item.status || 'pending')}</span>${actions}</div></div></div>`;
}

fetchWalletHistory = async function fetchWalletHistory() {
    const list = $('wallet-history-list');
    const loader = $('wallet-loading');
    const requestsHost = $('wallet-requests-list');
    if (!list) return;
    if (loader) loader.classList.remove('hidden');
    list.innerHTML = '';
    if (requestsHost) requestsHost.innerHTML = '';
    try {
        const [ledger, requests] = await Promise.all([
            (await fetch('/api/store/wallet-history', { credentials: 'same-origin' })).json(),
            (await fetch('/api/store/wallet-requests', { credentials: 'same-origin', cache: 'no-store' })).json(),
        ]);
        if (loader) loader.classList.add('hidden');

        if (!ledger.success || !ledger.txns.length) {
            list.innerHTML = '<div class="text-center text-gray-500 text-xs py-4">No wallet ledger entries yet.</div>';
        } else {
            list.innerHTML = ledger.txns.map((t) => {
                const isPlus = Number(t.amount) >= 0;
                const amount = `${isPlus ? '+' : '-'} ${Math.abs(Number(t.amount)).toFixed(2)} ${t.currency}`;
                const amountClr = isPlus ? 'text-szgreen' : 'text-red-400';
                return `<div class="border border-gray-800 rounded-xl p-3 flex items-center justify-between gap-3 bg-[#080808]"><div><div class="text-xs font-black ${amountClr}">${amount}</div><div class="text-[11px] text-gray-300 mt-0.5">${esc(t.note || 'Wallet transaction')}</div></div><div class="text-[10px] text-gray-500 whitespace-nowrap">${esc(t.created_at || '')}</div></div>`;
            }).join('');
        }

        if (!requestsHost) return;
        if (!requests.success || !requests.transactions.length) {
            requestsHost.innerHTML = '<div class="text-center text-gray-500 text-xs py-4">No wallet requests yet.</div>';
        } else {
            requestsHost.innerHTML = requests.transactions.map(walletRequestRow).join('');
        }
    } catch (error) {
        if (loader) loader.classList.add('hidden');
        list.innerHTML = '<div class="text-center text-red-500 text-xs py-4">Failed to load wallet activity.</div>';
        if (requestsHost) requestsHost.innerHTML = '<div class="text-center text-red-500 text-xs py-4">Failed to load wallet requests.</div>';
    }
};

async function loadWalletMethods(type) {
    const host = $('wallet-request-methods');
    if (!host) return;
    host.innerHTML = '<div class="text-center text-szcyan py-6 font-bold col-span-full"><i class="fas fa-spinner fa-spin"></i></div>';
    try {
        const data = await (await fetch(`/api/store/payment-methods?request_type=${encodeURIComponent(type)}`, { credentials: 'same-origin', cache: 'no-store' })).json();
        if (!data.success) {
            host.innerHTML = '<div class="text-center text-red-400 text-sm col-span-full">Unable to load payment methods.</div>';
            return;
        }
        const methods = data.payment_methods || [];
        if (!methods.length) {
            host.innerHTML = '<div class="text-center text-gray-500 text-sm col-span-full">No payment methods are configured yet.</div>';
            return;
        }
        host.innerHTML = methods.map((method) => `<button ${method.is_active ? '' : 'disabled'} class="wallet-method-btn rounded-3xl border p-4 text-left transition ${method.is_active ? 'border-white/10 bg-white/5 hover:border-szgreen/30 hover:bg-white/10' : 'cursor-not-allowed border-red-400/15 bg-red-950/10 opacity-70'}" data-method-id="${esc(method.method_id)}"><div class="flex items-start justify-between gap-3"><div class="flex items-center gap-3"><div class="h-12 w-12 overflow-hidden rounded-2xl border border-white/10 bg-black/40 flex items-center justify-center text-szcyan">${method.image_url ? `<img src="${esc(method.image_url)}" alt="${esc(method.name)}" class="h-full w-full object-cover">` : '<i class="fas fa-wallet"></i>'}</div><div><div class="text-sm font-black text-white">${esc(method.name)}</div><div class="mt-1 text-[11px] text-gray-500">${esc(method.type)} - ${esc(method.tax_fee?.mode || 'fixed')} ${esc(String(method.tax_fee?.value ?? 0))}</div></div></div>${method.is_active ? '' : '<span class="rounded-full border border-red-400/20 bg-red-400/10 px-2 py-1 text-[10px] font-black text-red-200">Currently Disabled</span>'}</div></button>`).join('');
        $$('.wallet-method-btn', host).forEach((button) => button.addEventListener('click', () => submitWalletRequest(button.dataset.methodId)));
    } catch (error) {
        host.innerHTML = '<div class="text-center text-red-400 text-sm col-span-full">Unable to load payment methods.</div>';
    }
}

openWalletRequestModal = async function openWalletRequestModal(type) {
    await ensureStoreSessionLoaded();
    if (!requireStoreAuth()) return;
    walletRequestType = type === 'withdrawal' ? 'withdrawal' : 'deposit';
    setText('wallet-request-title', walletRequestType === 'withdrawal' ? 'Wallet Withdrawal Request' : 'Wallet Deposit Request');
    if ($('wallet-request-amount')) $('wallet-request-amount').value = '';
    $('wallet-request-modal')?.classList.remove('hidden');
    $('wallet-request-modal')?.classList.add('flex');
    await loadWalletMethods(walletRequestType);
};

closeWalletRequestModal = function closeWalletRequestModal() {
    $('wallet-request-modal')?.classList.add('hidden');
    $('wallet-request-modal')?.classList.remove('flex');
};

async function submitWalletRequest(methodId) {
    const amount = Number($('wallet-request-amount')?.value || 0);
    const currency = $('wallet-request-currency')?.value || currentCurrency || 'EGP';
    if (!amount || amount <= 0) {
        Core.showToast('Enter a valid amount first.', 'error');
        return;
    }
    const fd = new FormData();
    fd.append('type', walletRequestType);
    fd.append('payment_method_id', methodId);
    fd.append('currency', currency);
    fd.append('requested_amount', amount);
    try {
        const data = await (await fetch('/api/store/wallet/request', { method: 'POST', body: fd, credentials: 'same-origin' })).json();
        if (!data.success) {
            Core.showToast(data.msg || 'Unable to create wallet request.', 'error');
            if (data.force_logout) logout();
            return;
        }
        closeWalletRequestModal();
        Core.showToast(data.msg || 'Wallet request created.', 'success');
        await fetchWalletHistory();
        if (data.thread_id) openLiveChat(data.thread_id, `${walletRequestType.toUpperCase()} Request ${data.transaction?.transaction_id || ''}`);
    } catch (error) {
        Core.showToast('Unable to create wallet request right now.', 'error');
    }
}

function liveChatSocketUrl() {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${scheme}://${window.location.host}/ws/store-chat?role=customer`;
}

function renderLiveChatMessages() {
    const host = $('live-chat-messages');
    if (!host) return;
    if (!liveChatMessages.length) {
        host.innerHTML = '<div class="rounded-xl border border-dashed border-gray-700 bg-black/40 px-4 py-8 text-center text-sm font-bold text-gray-500">No messages yet.</div>';
        return;
    }
    host.innerHTML = liveChatMessages.map((message) => {
        const sender = String(message.sender || '').toLowerCase();
        const system = Boolean(message.is_system) || sender === 'system';
        const customer = sender === 'customer';
        const cls = system ? 'border-white/10 bg-white/5 text-gray-300' : customer ? 'ml-6 border-cyan-400/20 bg-cyan-400/10 text-cyan-50' : 'mr-6 border-emerald-400/20 bg-emerald-400/10 text-emerald-50';
        const name = system ? 'System' : (message.name || (customer ? 'You' : 'Agent'));
        return `<div class="rounded-2xl border p-3 ${cls}"><div class="mb-1 flex items-center justify-between gap-3"><span class="text-xs font-black uppercase tracking-[0.2em] ${system ? 'text-gray-300' : customer ? 'text-cyan-200' : 'text-emerald-200'}">${esc(name)}</span><span class="text-[10px] text-gray-500">${esc(message.time || '')}</span></div><div class="whitespace-pre-wrap text-sm">${esc(message.message || '')}</div></div>`;
    }).join('');
    host.scrollTop = host.scrollHeight;
}

function renderLiveChatPresence() {
    const host = $('live-chat-presence');
    if (!host) return;
    if (!liveChatThreadId) { host.textContent = 'No active chat.'; return; }
    if (!liveChatConnected) { host.textContent = 'Connecting...'; return; }
    const parts = [];
    if (liveChatPresence?.staff_online) parts.push('Agent online');
    if (liveChatPresence?.admin_online) parts.push('Admin online');
    if (liveChatPresence?.spectator_online) parts.push('Admin spectating');
    host.textContent = parts.length ? parts.join(' - ') : 'Live chat connected.';
}

function ensureLiveChatSocket() {
    if (liveChatSocket && (liveChatSocket.readyState === WebSocket.OPEN || liveChatSocket.readyState === WebSocket.CONNECTING)) return;
    liveChatSocket = new WebSocket(liveChatSocketUrl());
    liveChatSocket.addEventListener('open', () => {
        liveChatConnected = true;
        renderLiveChatPresence();
        if (liveChatThreadId) liveChatSocket.send(JSON.stringify({ action: 'join_room', thread_id: liveChatThreadId }));
    });
    liveChatSocket.addEventListener('message', (event) => {
        let payload = {};
        try { payload = JSON.parse(event.data); } catch { return; }
        if (payload.thread_id && payload.thread_id !== liveChatThreadId) return;
        if (payload.event === 'presence:update') { liveChatPresence = payload.presence || null; renderLiveChatPresence(); return; }
        if (payload.event === 'message:new' && payload.message) {
            liveChatMessages = [...liveChatMessages, payload.message];
            renderLiveChatMessages();
            if (String(payload.message.sender || '').toLowerCase() !== 'customer' && liveChatSocket?.readyState === WebSocket.OPEN) {
                liveChatSocket.send(JSON.stringify({ action: 'mark_read', thread_id: liveChatThreadId }));
            }
            return;
        }
        if (payload.event === 'system:joined' && liveChatSocket?.readyState === WebSocket.OPEN) {
            liveChatSocket.send(JSON.stringify({ action: 'mark_read', thread_id: liveChatThreadId }));
            return;
        }
        if (payload.event === 'error' && payload.msg) Core.showToast(payload.msg, 'error');
    });
    liveChatSocket.addEventListener('close', () => {
        liveChatConnected = false;
        renderLiveChatPresence();
    });
}

openLiveChat = async function openLiveChat(threadId, titleText) {
    liveChatThreadId = threadId;
    liveChatMessages = [];
    liveChatPresence = null;
    setText('live-chat-title', titleText || 'Live Chat with Agent');
    $('live-chat-modal')?.classList.remove('hidden');
    $('live-chat-modal')?.classList.add('flex');
    renderLiveChatPresence();
    renderLiveChatMessages();
    try {
        const data = await (await fetch(`/api/store/chat/history?thread_id=${encodeURIComponent(threadId)}`, { credentials: 'same-origin', cache: 'no-store' })).json();
        if (!data.success) {
            Core.showToast(data.msg || 'Unable to open chat.', 'error');
            if (data.force_logout) logout();
            return;
        }
        liveChatMessages = data.messages || [];
        renderLiveChatMessages();
        ensureLiveChatSocket();
        if (liveChatSocket?.readyState === WebSocket.OPEN) {
            liveChatSocket.send(JSON.stringify({ action: 'join_room', thread_id: threadId }));
        }
    } catch (error) {
        Core.showToast('Unable to load chat right now.', 'error');
    }
};

closeLiveChatModal = function closeLiveChatModal() {
    if (liveChatSocket?.readyState === WebSocket.OPEN && liveChatThreadId) {
        liveChatSocket.send(JSON.stringify({ action: 'leave_room', thread_id: liveChatThreadId }));
    }
    liveChatThreadId = '';
    $('live-chat-modal')?.classList.add('hidden');
    $('live-chat-modal')?.classList.remove('flex');
};

sendLiveChatMessage = async function sendLiveChatMessage() {
    const input = $('live-chat-input');
    const status = $('live-chat-status');
    const message = input?.value.trim();
    if (!message) {
        Core.showToast('Type a message first.', 'error');
        return;
    }
    if (status) status.textContent = 'Sending...';
    if (liveChatSocket?.readyState === WebSocket.OPEN) {
        liveChatSocket.send(JSON.stringify({ action: 'send_message', thread_id: liveChatThreadId, message }));
        if (input) input.value = '';
        if (status) status.textContent = '';
        return;
    }
    const fd = new FormData();
    fd.append('thread_id', liveChatThreadId);
    fd.append('message', message);
    try {
        const data = await (await fetch('/api/store/chat/reply', { method: 'POST', body: fd, credentials: 'same-origin' })).json();
        if (!data.success) {
            Core.showToast(data.msg || 'Unable to send message.', 'error');
            if (status) status.textContent = data.msg || 'Unable to send.';
            return;
        }
        if (input) input.value = '';
        if (status) status.textContent = '';
        liveChatMessages = [...liveChatMessages, data.message];
        renderLiveChatMessages();
    } catch (error) {
        if (status) status.textContent = 'Unable to send.';
        Core.showToast('Unable to send message right now.', 'error');
    }
};

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[onclick="openCartModal()"]').forEach((button) => button.classList.add('hidden'));
    if ($('cart-modal')) $('cart-modal').classList.add('hidden');
    setCheckoutMeta({});
});
