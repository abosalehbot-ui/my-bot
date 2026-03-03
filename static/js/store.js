// ============================================================
// Saleh Zone Store Engine v2.0
// Single source of truth — no logic duplication with HTML
// ============================================================

// ─── State ───────────────────────────────────────────────
let currentCurrency = 'EGP';
let pendingPurchase  = null;
let ordersLoaded     = false;
let _forgotEmail     = '';   // Kept in memory for the reset-password step

// ─── Modal Helpers ───────────────────────────────────────
function openModal(id)  { document.getElementById(id)?.classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id)?.classList.add('hidden'); }
function openAuthModal(view) { openModal('auth-modal'); switchAuthView(view); }

// ─── Status Message ──────────────────────────────────────
function setStatus(msg, isError = false) {
    const el = document.getElementById('auth-status');
    if (el) el.innerHTML = isError
        ? `<span class="text-red-500">${msg}</span>`
        : `<span class="text-szcyan">${msg}</span>`;
}

// ─── Auth View Switcher ──────────────────────────────────
function switchAuthView(view) {
    document.querySelectorAll('.auth-view').forEach(el => el.classList.add('hidden'));
    document.getElementById(view + '-view')?.classList.remove('hidden');
    document.getElementById('auth-status').innerHTML = '';

    const views = {
        signin: { title: 'Login',          social: true  },
        signup: { title: 'Create Account', social: true  },
        otp:    { title: 'Verify Email',   social: false },
        forgot: { title: 'Reset Password', social: false },
        reset:  { title: 'New Password',   social: false },
    };

    const cfg    = views[view];
    const title  = document.getElementById('modal-title');
    const social = document.getElementById('social-section');
    if (cfg) {
        if (title)  title.innerText = cfg.title;
        if (social) social.classList.toggle('hidden', !cfg.social);
    }
}

// ─── Theme ───────────────────────────────────────────────
function setTheme(name) {
    document.documentElement.setAttribute('data-theme', name);
    localStorage.setItem('sz_theme', name);
    document.getElementById('theme-drop')?.classList.add('hidden');
}

// ─── Sidebar ─────────────────────────────────────────────
function toggleSidebar() {
    document.getElementById('sz-sidebar')?.classList.toggle('-translate-x-full');
    document.getElementById('sidebar-backdrop')?.classList.toggle('hidden');
}
function toggleSidebarMobile() {
    if (window.innerWidth < 768) toggleSidebar();
}

// ─── Currency Toggle ─────────────────────────────────────
function toggleCurrency() {
    currentCurrency = document.getElementById('currency-toggle').value;
    document.querySelectorAll('.price-display').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll(`.${currentCurrency.toLowerCase()}-price`).forEach(el => el.classList.remove('hidden'));
}

// ─── UI Updates ──────────────────────────────────────────
function updateUI(name, balEgp, balUsd) {
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.innerText = val; };

    document.getElementById('sidebar-guest')?.classList.add('hidden');
    document.getElementById('sidebar-user')?.classList.remove('hidden');
    document.getElementById('sidebar-logout-btn')?.classList.remove('hidden');

    set('sidebar-ui-name',    name);
    set('sidebar-ui-bal-egp', balEgp ?? '0');
    set('sidebar-ui-bal-usd', balUsd ?? '0');
    set('prof-name',    name);
    set('prof-email',   localStorage.getItem('store_email') || 'N/A');
    set('prof-bal-egp', balEgp ?? '0');
    set('prof-bal-usd', balUsd ?? '0');

    localStorage.setItem('bal_egp', balEgp ?? '0');
    localStorage.setItem('bal_usd', balUsd ?? '0');
}

function saveAndLogin(data) {
    localStorage.setItem('store_email', data.email);
    localStorage.setItem('store_name',  data.name);
    updateUI(data.name, data.balance_egp, data.balance_usd);
    closeModal('auth-modal');
    Core.showToast(`Welcome, ${data.name}!`);
}

async function logout() {
    await fetch('/api/store/logout', { method: 'POST' });
    localStorage.clear();
    location.reload();
}

// ─── Auth: Login ─────────────────────────────────────────
async function doManualLogin(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-signin');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    btn.disabled  = true;

    const fd = new FormData();
    fd.append('email',    document.getElementById('signin-email').value);
    fd.append('password', document.getElementById('signin-password').value);

    try {
        const res  = await fetch('/api/store/login-manual', { method: 'POST', body: fd });
        const data = await res.json();
        if (data.success) saveAndLogin(data);
        else setStatus(data.msg, true);
    } catch { setStatus('Connection error!', true); }

    btn.innerHTML = orig;
    btn.disabled  = false;
}

// ─── Auth: Signup ────────────────────────────────────────
async function doSignupRequest(e) {
    e.preventDefault();
    const pass = document.getElementById('signup-password').value;
    const conf = document.getElementById('signup-confirm').value;
    if (pass !== conf) { setStatus('Passwords do not match!', true); return; }

    const btn  = document.getElementById('btn-signup');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    btn.disabled  = true;

    const fd = new FormData();
    fd.append('name',     document.getElementById('signup-name').value);
    fd.append('username', document.getElementById('signup-username').value);
    fd.append('email',    document.getElementById('signup-email').value);
    fd.append('password', pass);

    try {
        const res  = await fetch('/api/store/signup-request', { method: 'POST', body: fd });
        const data = await res.json();
        if (data.success) { switchAuthView('otp'); setStatus(data.msg); }
        else setStatus(data.msg, true);
    } catch { setStatus('Error!', true); }

    btn.innerHTML = orig;
    btn.disabled  = false;
}

// ─── Auth: OTP Verify ────────────────────────────────────
async function doVerifyOTP(e) {
    e.preventDefault();
    const btn  = document.getElementById('btn-verify');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    btn.disabled  = true;

    const fd = new FormData();
    fd.append('email', document.getElementById('signup-email').value);
    fd.append('code',  document.getElementById('verify-otp').value);

    try {
        const res  = await fetch('/api/store/signup-verify', { method: 'POST', body: fd });
        const data = await res.json();
        if (data.success) saveAndLogin(data);
        else setStatus(data.msg, true);
    } catch { setStatus('Error!', true); }

    btn.innerHTML = orig;
    btn.disabled  = false;
}

// ─── Auth: Forgot Password ───────────────────────────────
async function doForgotPassword(e) {
    e.preventDefault();
    const btn  = document.getElementById('btn-forgot');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    btn.disabled  = true;

    // Save email in memory — reset step uses this, not the DOM field
    _forgotEmail = document.getElementById('forgot-email').value;

    const fd = new FormData();
    fd.append('email', _forgotEmail);

    try {
        const res  = await fetch('/api/store/forgot-password', { method: 'POST', body: fd });
        const data = await res.json();
        if (data.success) { switchAuthView('reset'); setStatus(data.msg); }
        else setStatus(data.msg, true);
    } catch { setStatus('Error!', true); }

    btn.innerHTML = orig;
    btn.disabled  = false;
}

// ─── Auth: Reset Password ────────────────────────────────
async function doResetPassword(e) {
    e.preventDefault();
    const btn  = document.getElementById('btn-reset');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    btn.disabled  = true;

    const fd = new FormData();
    fd.append('email',        _forgotEmail);   // Uses in-memory email — no DOM dependency
    fd.append('code',         document.getElementById('reset-otp').value);
    fd.append('new_password', document.getElementById('reset-new-password').value);

    try {
        const res  = await fetch('/api/store/reset-password', { method: 'POST', body: fd });
        const data = await res.json();
        if (data.success) {
            _forgotEmail = '';
            switchAuthView('signin');
            setStatus(data.msg);
        } else setStatus(data.msg, true);
    } catch { setStatus('Error!', true); }

    btn.innerHTML = orig;
    btn.disabled  = false;
}

// ─── Auth: Google & Telegram ─────────────────────────────
async function handleGoogleResponse(response) {
    setStatus('<i class="fas fa-spinner fa-spin"></i>');
    const fd = new FormData();
    fd.append('credential', response.credential);
    try {
        const res  = await fetch('/api/store/google-login', { method: 'POST', body: fd });
        const data = await res.json();
        if (data.success) saveAndLogin(data);
        else setStatus(data.msg, true);
    } catch { setStatus('Error!', true); }
}

async function onTelegramAuth(user) {
    setStatus('<i class="fas fa-spinner fa-spin"></i>');
    const fd = new FormData();
    fd.append('tg_id',    user.id);
    fd.append('name',     user.first_name);
    fd.append('username', user.username || '');
    try {
        const res  = await fetch('/api/store/telegram-login', { method: 'POST', body: fd });
        const data = await res.json();
        if (data.success) saveAndLogin(data);
        else setStatus(data.msg, true);
    } catch { setStatus('Error!', true); }
}

// ─── Purchase Flow ───────────────────────────────────────
function buyProduct(stock_key, pEgp, pUsd, name, iconClass) {
    const email = localStorage.getItem('store_email');
    if (!email) { openAuthModal('signin'); toggleSidebarMobile(); return; }

    const finalPrice      = currentCurrency === 'EGP' ? pEgp : pUsd;
    pendingPurchase       = { stock_key, price: finalPrice, currency: currentCurrency };

    const priceText       = finalPrice + ' ' + currentCurrency;
    const priceColorClass = currentCurrency === 'EGP' ? 'text-yellow-500' : 'text-szcyan';

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.innerText = val; };
    set('checkout-user-name',  localStorage.getItem('store_name'));
    set('checkout-user-email', email);
    set('checkout-item-name',  name);

    const iconEl = document.getElementById('checkout-item-icon');
    if (iconEl && iconClass) iconEl.className = `fas ${iconClass}`;

    const priceEl = document.getElementById('checkout-item-price');
    if (priceEl) { priceEl.innerText = priceText; priceEl.className = `p-4 text-right font-black text-lg ${priceColorClass}`; }

    const totalEl = document.getElementById('checkout-total-price');
    if (totalEl) { totalEl.innerText = priceText; totalEl.className = `text-2xl font-black ${priceColorClass}`; }

    openModal('checkout-modal');
}

async function confirmPurchase() {
    if (!pendingPurchase) return;
    if (!document.getElementById('terms-checkbox').checked) {
        return alert('Please agree to the Terms of Service.');
    }

    const btn  = document.getElementById('btn-confirm-pay');
    const orig = btn.innerHTML;   // Always restore original HTML
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    btn.disabled  = true;

    const fd = new FormData();
    fd.append('stock_key', pendingPurchase.stock_key);
    fd.append('price',     pendingPurchase.price);
    fd.append('currency',  pendingPurchase.currency);

    try {
        const res  = await fetch('/api/store/buy', { method: 'POST', body: fd });
        const data = await res.json();

        if (data.success) {
            const newEgp = data.currency === 'EGP' ? data.new_balance : localStorage.getItem('bal_egp');
            const newUsd = data.currency === 'USD' ? data.new_balance : localStorage.getItem('bal_usd');
            updateUI(localStorage.getItem('store_name'), newEgp, newUsd);
            ordersLoaded = false;
            closeModal('checkout-modal');
            const codeEl = document.getElementById('purchased-code');
            if (codeEl) codeEl.innerText = data.code;
            openModal('success-modal');
        } else {
            alert(data.msg);
            if (data.force_logout) logout();
            else if (data.msg.includes('balance') || data.msg.includes('stock')) location.reload();
        }
    } catch { alert('An error occurred during purchase!'); }

    btn.innerHTML = orig;
    btn.disabled  = false;
}

function copyPurchasedCode() {
    const code = document.getElementById('purchased-code')?.innerText;
    if (code) Core.copy(code);
}

// ─── Profile Modal ───────────────────────────────────────
function openProfileModal() {
    openModal('profile-modal');
    switchProfileTab('overview');
}

function switchProfileTab(tab) {
    ['overview', 'history'].forEach(t => {
        document.getElementById(`ptab-${t}`)?.classList.add('hidden');
        const btn = document.getElementById(`ptab-btn-${t}`);
        if (btn) btn.className = 'pb-3 px-2 font-bold text-sm text-gray-500 hover:text-gray-300 transition border-b-2 border-transparent';
    });

    document.getElementById(`ptab-${tab}`)?.classList.remove('hidden');
    const activeBtn = document.getElementById(`ptab-btn-${tab}`);
    if (activeBtn) activeBtn.className = 'pb-3 px-2 font-bold text-sm text-szgreen border-b-2 border-szgreen transition';

    if (tab === 'history' && !ordersLoaded) fetchMyOrders();
}

// ─── Order History ───────────────────────────────────────
async function fetchMyOrders() {
    const loader = document.getElementById('orders-loading');
    const tbody  = document.getElementById('orders-table-body');
    if (loader) loader.classList.remove('hidden');
    if (tbody)  tbody.innerHTML = '';

    try {
        const res  = await fetch('/api/store/my-orders');
        const data = await res.json();
        if (loader) loader.classList.add('hidden');

        if (data.success && data.orders.length > 0) {
            const html = data.orders.map(o => {
                const pColor   = o.currency === 'USD' ? 'text-szcyan' : 'text-yellow-500';
                const safeCode = String(o.code).replace(/'/g, "\\'");
                return `
                <tr class="hover:bg-[#111] transition">
                    <td class="px-4 py-3 font-mono text-szcyan">#${o.order_id}</td>
                    <td class="px-4 py-3 text-xs text-gray-500">${o.date}</td>
                    <td class="px-4 py-3 font-bold text-white">${o.category}</td>
                    <td class="px-4 py-3 font-black ${pColor}">${o.price} <span class="text-[10px] text-gray-500">${o.currency}</span></td>
                    <td class="px-4 py-3">
                        <button onclick="Core.copy('${safeCode}')"
                                class="bg-gray-900 text-szgreen border border-gray-700 px-3 py-1 rounded text-xs font-mono hover:bg-szgreen hover:text-black transition">
                            Copy
                        </button>
                    </td>
                </tr>`;
            }).join('');
            if (tbody) tbody.innerHTML = html;
            ordersLoaded = true;
        } else {
            if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500 font-bold">No purchases found.</td></tr>';
        }
    } catch {
        if (loader) loader.innerHTML = '<span class="text-red-500">Error loading orders. Please try again.</span>';
    }
}

// ─── Init ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Restore session from localStorage
    const email = localStorage.getItem('store_email');
    const name  = localStorage.getItem('store_name');
    if (email && name) {
        updateUI(name, localStorage.getItem('bal_egp') || '0', localStorage.getItem('bal_usd') || '0');
    }

    // Scroll-to-top button
    const mainScroll = document.getElementById('main-scroll');
    const scrollBtn  = document.getElementById('scrollToTopBtn');
    if (mainScroll && scrollBtn) {
        mainScroll.addEventListener('scroll', () => {
            const past = mainScroll.scrollTop > 300;
            scrollBtn.classList.toggle('opacity-0',           !past);
            scrollBtn.classList.toggle('pointer-events-none', !past);
            scrollBtn.classList.toggle('translate-y-4',       !past);
            scrollBtn.classList.toggle('opacity-100',          past);
            scrollBtn.classList.toggle('translate-y-0',        past);
        });
        scrollBtn.onclick = () => mainScroll.scrollTo({ top: 0, behavior: 'smooth' });
    }
});
