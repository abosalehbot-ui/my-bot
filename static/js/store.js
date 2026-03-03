// ============================================================
// Saleh Zone Store Engine v3.0 — Clean Single Source of Truth
// ============================================================

// ─── State ───────────────────────────────────────────────────────────────
let currentCurrency = 'EGP';
let pendingPurchase  = null;
let ordersLoaded     = false;
let _forgotEmail     = '';
let _profileLoaded   = false;

// ─── Helpers ─────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const setText = (id, val) => { const el = $(id); if (el) el.innerText = val ?? ''; };

// ─── Modal ───────────────────────────────────────────────────────────────
function openModal(id)  { $(id)?.classList.remove('hidden'); }
function closeModal(id) { $(id)?.classList.add('hidden'); }
function openAuthModal(view) { openModal('auth-modal'); switchAuthView(view); }

// ─── Toast ───────────────────────────────────────────────────────────────
function setStatus(msg, isError = false) {
    const el = $('auth-status');
    if (el) el.innerHTML = isError ? `<span class="text-red-500">${msg}</span>` : `<span class="text-szcyan">${msg}</span>`;
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

async function saveAndLogin(data) {
    _saveLocals(data);
    updateUI(data.name, data.balance_egp, data.balance_usd);
    _applyAvatar(data.avatar || '');
    closeModal('auth-modal');
    Core.showToast(`Welcome, ${data.name}!`);
    // Fetch full profile (includes user_id, username, avatar)
    fetchAndApplyProfile();
}

async function logout() {
    await fetch('/api/store/logout', { method: 'POST' });
    localStorage.clear();
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

// ─── Purchase Flow ───────────────────────────────────────────────────────
function buyProduct(stock_key, pEgp, pUsd, name, iconClass) {
    if (!localStorage.getItem('store_email')) { openAuthModal('signin'); toggleSidebarMobile(); return; }
    const finalPrice = currentCurrency === 'EGP' ? pEgp : pUsd;
    pendingPurchase  = { stock_key, price: finalPrice, currency: currentCurrency };
    const priceText  = finalPrice + ' ' + currentCurrency;
    const pColor     = currentCurrency === 'EGP' ? 'text-yellow-500' : 'text-szcyan';

    setText('checkout-user-name',  localStorage.getItem('store_name'));
    setText('checkout-user-email', localStorage.getItem('store_email'));
    setText('checkout-item-name',  name);
    const icon = $('checkout-item-icon'); if (icon && iconClass) icon.className = `fas ${iconClass}`;
    const pe = $('checkout-item-price');
    if (pe) { pe.innerText = priceText; pe.className = `p-4 text-right font-black text-lg ${pColor}`; }
    const te = $('checkout-total-price');
    if (te) { te.innerText = priceText; te.className = `text-2xl font-black ${pColor}`; }
    openModal('checkout-modal');
}

async function confirmPurchase() {
    if (!pendingPurchase) return;
    if (!$('terms-checkbox').checked) return alert('Please agree to the Terms of Service.');
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
            const ce = $('purchased-code'); if (ce) ce.innerText = d.code;
            openModal('success-modal');
        } else {
            alert(d.msg);
            if (d.force_logout) logout();
            else if (d.msg.includes('balance') || d.msg.includes('stock')) location.reload();
        }
    } catch { alert('An error occurred!'); }
    btn.innerHTML = orig; btn.disabled = false;
}

function copyPurchasedCode() {
    const code = $('purchased-code')?.innerText;
    if (code) Core.copy(code);
}

// ─── Profile Modal ───────────────────────────────────────────────────────
function openProfileModal() {
    openModal('profile-modal');
    switchProfileTab('overview');
    if (!_profileLoaded) { _profileLoaded = true; fetchAndApplyProfile(); }
    else _applyLocalProfile();
}

// TAB SWITCHING — uses explicit style.display instead of Tailwind hidden
// to avoid flex-1 / display:none conflicts
function switchProfileTab(tab) {
    // Panels are absolute inset-0 inside a relative wrapper — toggle hidden only
    ['overview', 'edit', 'security', 'history'].forEach(t => {
        $('ptab-'+t)?.classList.add('hidden');
        const btn = $('ptab-btn-'+t);
        if (btn) { btn.classList.remove('active'); btn.classList.add('inactive'); }
    });
    $('ptab-'+tab)?.classList.remove('hidden');
    const ab = $('ptab-btn-'+tab);
    if (ab) { ab.classList.add('active'); ab.classList.remove('inactive'); }
    if (tab === 'history' && !ordersLoaded) fetchMyOrders();
}

// ─── Profile Data ────────────────────────────────────────────────────────
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
        const d = await (await fetch('/api/store/me')).json();
        if (!d.success) return;
        _saveLocals(d);
        updateUI(d.name, d.balance_egp, d.balance_usd);
        _fillProfileUI(d);
    } catch {}
}

// ─── Avatar ──────────────────────────────────────────────────────────────
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

// ─── Edit Profile ────────────────────────────────────────────────────────
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
            setText('sidebar-ui-name',    d.name);
            setText('sidebar-ui-username', '@' + d.username);
            setText('prof-name',     d.name);
            setText('prof-username', '@' + d.username);
            _setFormStatus('edit-status', d.msg, false);
        } else _setFormStatus('edit-status', d.msg, true);
    } catch { _setFormStatus('edit-status', 'Error!', true); }
    btn.innerHTML = orig; btn.disabled = false;
}

// ─── Change Password ─────────────────────────────────────────────────────
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

// ─── Change Email ────────────────────────────────────────────────────────
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

// ─── Order History ───────────────────────────────────────────────────────
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

// ─── Init ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Apply saved theme
    const theme = localStorage.getItem('sz_theme') || 'default';
    document.documentElement.setAttribute('data-theme', theme);

    // Restore session
    const email = localStorage.getItem('store_email');
    const name  = localStorage.getItem('store_name');
    if (email && name) {
        updateUI(name, localStorage.getItem('bal_egp') || '0', localStorage.getItem('bal_usd') || '0');
        _applyAvatar(localStorage.getItem('store_avatar') || '');
        fetchAndApplyProfile(); // refresh from server
    }

    // Scroll-to-top button
    const ms = $('main-scroll'), sb = $('scrollToTopBtn');
    if (ms && sb) {
        ms.addEventListener('scroll', () => {
            const past = ms.scrollTop > 300;
            sb.classList.toggle('opacity-0',           !past);
            sb.classList.toggle('pointer-events-none', !past);
            sb.classList.toggle('translate-y-4',       !past);
            sb.classList.toggle('opacity-100',          past);
            sb.classList.toggle('translate-y-0',        past);
        });
        sb.onclick = () => ms.scrollTo({ top: 0, behavior: 'smooth' });
    }
});
