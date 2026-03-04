// ============================================================
// Saleh Zone Store Engine v4.1 — Fully Integrated
// ============================================================

let currentCurrency = 'EGP';
let pendingPurchase = null;
let cart = JSON.parse(localStorage.getItem('sz_cart') || '[]');

const $ = id => document.getElementById(id);
function openModal(id) { $(id)?.classList.remove('hidden'); }
function closeModal(id) { $(id)?.classList.add('hidden'); }

// --- Navigation & Sidebar ---
function toggleSidebar() {
    $('sz-sidebar')?.classList.toggle('-translate-x-full');
    $('sidebar-backdrop')?.classList.toggle('hidden');
}
function toggleSidebarMobile() { if (window.innerWidth < 768) toggleSidebar(); }

function openCategory(catId) {
    $('categories-view')?.classList.add('hidden');
    $('products-view')?.classList.remove('hidden');
    document.querySelectorAll('.cat-prod-grid').forEach(el => el.classList.add('hidden'));
    $('prod-grid-' + catId)?.classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function closeCategory() {
    $('products-view')?.classList.add('hidden');
    $('categories-view')?.classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleCurrency() {
    currentCurrency = $('currency-toggle').value;
    document.querySelectorAll('.price-display').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll(`.price-${currentCurrency}`).forEach(el => el.classList.remove('hidden'));
    updateCartUI(); 
}

function setTheme(name) {
    document.documentElement.setAttribute('data-theme', name);
    localStorage.setItem('sz_theme', name);
    $('theme-drop')?.classList.add('hidden');
}

// --- Authentication ---
function switchAuthView(view) {
    document.querySelectorAll('.auth-view').forEach(el => el.classList.add('hidden'));
    $(view + '-view')?.classList.remove('hidden');
    if ($('auth-status')) $('auth-status').innerText = '';
    const titles = { 'signin': 'Login', 'signup': 'Create Account', 'verify': 'Verification' };
    if ($('modal-title')) $('modal-title').innerText = titles[view] || 'Auth';
}

function openAuthModal(view) {
    openModal('auth-modal');
    switchAuthView(view);
}

async function doManualLogin(e) {
    e.preventDefault();
    const btn = $('btn-signin'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('email', $('signin-email').value);
    fd.append('password', $('signin-password').value);
    try {
        const res = await (await fetch('/api/store/login-manual', { method: 'POST', body: fd })).json();
        if (res.success) {
            localStorage.setItem('store_email', res.email);
            localStorage.setItem('store_name', res.name);
            Core.showToast("Login Successful!", "success");
            setTimeout(() => window.location.reload(), 1000);
        } else { Core.showToast(res.msg, "error"); }
    } catch { Core.showToast("Connection error", "error"); }
    btn.innerHTML = orig; btn.disabled = false;
}

async function doSignupRequest(e) {
    e.preventDefault();
    const btn = $('btn-signup'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('name', $('signup-name').value);
    fd.append('username', $('signup-username').value);
    fd.append('email', $('signup-email').value);
    fd.append('password', $('signup-password').value);
    try {
        const res = await (await fetch('/api/store/signup-request', { method: 'POST', body: fd })).json();
        if (res.success) {
            if($('v-email-show')) $('v-email-show').innerText = $('signup-email').value;
            if($('verify-email')) $('verify-email').value = $('signup-email').value;
            switchAuthView('verify');
            Core.showToast("Code Sent to Email!", "success");
        } else { Core.showToast(res.msg, "error"); }
    } catch { Core.showToast('Network error', "error"); }
    btn.innerHTML = orig; btn.disabled = false;
}

async function doSignupVerify(e) {
    e.preventDefault();
    const btn = $('btn-verify'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('email', $('verify-email').value);
    fd.append('code', $('verify-code').value);
    try {
        const res = await (await fetch('/api/store/signup-verify', { method: 'POST', body: fd })).json();
        if (res.success) {
            localStorage.setItem('store_email', res.email);
            localStorage.setItem('store_name', res.name);
            Core.showToast("Account Created Successfully!", "success");
            setTimeout(() => location.reload(), 1000);
        } else { Core.showToast(res.msg, "error"); }
    } catch { Core.showToast('Network error', "error"); }
    btn.innerHTML = orig; btn.disabled = false;
}

async function handleGoogleResponse(response) {
    Core.showToast("Verifying Google...", "success");
    const fd = new FormData(); fd.append('credential', response.credential);
    try {
        const res = await (await fetch('/api/store/google-login', {method: 'POST', body: fd})).json();
        if(res.success) {
            localStorage.setItem('store_email', res.email);
            localStorage.setItem('store_name', res.name);
            setTimeout(() => window.location.reload(), 1000);
        } else { Core.showToast(res.msg, 'error'); }
    } catch { Core.showToast('Connection error', 'error'); }
}

async function onTelegramAuth(user) {
    Core.showToast("Verifying Telegram...", "success");
    const fd = new FormData();
    fd.append('tg_id', user.id);
    fd.append('name', user.first_name + (user.last_name ? ' ' + user.last_name : ''));
    fd.append('username', user.username || '');
    try {
        const res = await (await fetch('/api/store/telegram-login', {method: 'POST', body: fd})).json();
        if(res.success) { 
            localStorage.setItem('store_email', res.email);
            localStorage.setItem('store_name', res.name);
            setTimeout(() => window.location.reload(), 1000); 
        } else { Core.showToast(res.msg, 'error'); }
    } catch { Core.showToast('Connection error', 'error'); }
}

async function logout() {
    try { await fetch('/api/store/logout', { method: 'POST' }); localStorage.clear(); window.location.reload(); } 
    catch { Core.showToast("Logout failed", "error"); }
}

// --- Cart System ---
function toggleCartDrawer() {
    const drawer = $('cart-drawer'), backdrop = $('cart-drawer-backdrop');
    if (drawer.classList.contains('translate-x-full')) {
        drawer.classList.remove('translate-x-full');
        backdrop.classList.remove('hidden');
        updateCartUI();
    } else {
        drawer.classList.add('translate-x-full');
        backdrop.classList.add('hidden');
    }
}

function addToCart(stock_key, prices_json, name, iconClass) {
    if (!localStorage.getItem('store_email')) { openAuthModal('signin'); return; }
    const existing = cart.find(i => i.stock_key === stock_key && i.currency === currentCurrency);
    if (existing) { existing.quantity += 1; } 
    else { cart.push({ stock_key, price: prices_json[currentCurrency] || 0, currency: currentCurrency, name, iconClass, quantity: 1, prices_json }); }
    localStorage.setItem('sz_cart', JSON.stringify(cart));
    updateCartUI();
    Core.showToast(`Added to Cart`, 'success');
}

function removeFromCart(index) {
    cart.splice(index, 1);
    localStorage.setItem('sz_cart', JSON.stringify(cart));
    updateCartUI();
}

function adjustCartQty(index, delta) {
    if (cart[index].quantity + delta > 0) {
        cart[index].quantity += delta;
        localStorage.setItem('sz_cart', JSON.stringify(cart));
        updateCartUI();
    }
}

function updateCartUI() {
    cart.forEach(item => {
        item.currency = currentCurrency;
        item.price = item.prices_json[currentCurrency] || 0;
    });
    localStorage.setItem('sz_cart', JSON.stringify(cart));

    const c = $('cart-items-container');
    let totalQty = cart.reduce((s, i) => s + i.quantity, 0);
    let totalPrice = cart.reduce((s, i) => s + (i.price * i.quantity), 0);

    [$('desktop-cart-badge'), $('mobile-cart-badge')].forEach(b => {
        if (b) { b.innerText = totalQty; totalQty > 0 ? b.classList.remove('hidden') : b.classList.add('hidden'); }
    });

    if ($('cart-total-price')) $('cart-total-price').innerText = `${totalPrice.toFixed(2)} ${currentCurrency}`;

    if (cart.length === 0) {
        if (c) c.innerHTML = `<div class="text-center text-gray-500 py-10 fade-in"><i class="fas fa-shopping-cart text-3xl mb-3 opacity-20 block"></i> Your cart is empty.</div>`;
        return;
    }

    if (c) c.innerHTML = cart.map((item, idx) => `
        <div class="bg-black border border-gray-800 rounded-xl p-3 flex gap-3 items-center fade-in relative">
            <div class="w-12 h-12 rounded-lg bg-gray-900 border border-gray-700 flex items-center justify-center text-szcyan shrink-0"><i class="fas ${item.iconClass}"></i></div>
            <div class="flex-1 min-w-0">
                <h4 class="text-white font-bold text-sm truncate">${item.name}</h4>
                <div class="text-[10px] text-szcyan font-mono mt-0.5">${item.price} ${item.currency}</div>
            </div>
            <div class="flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-lg p-1 shrink-0">
                <button onclick="adjustCartQty(${idx}, -1)" class="w-6 h-6 flex justify-center items-center text-gray-400 hover:text-white bg-black rounded"><i class="fas fa-minus text-[10px]"></i></button>
                <span class="text-xs font-bold text-white w-4 text-center">${item.quantity}</span>
                <button onclick="adjustCartQty(${idx}, 1)" class="w-6 h-6 flex justify-center items-center text-gray-400 hover:text-white bg-black rounded"><i class="fas fa-plus text-[10px]"></i></button>
            </div>
            <button onclick="removeFromCart(${idx})" class="absolute -top-2 -right-2 bg-red-900 text-white w-5 h-5 rounded-full flex justify-center items-center text-[10px] hover:bg-red-500 shadow-md transition"><i class="fas fa-times"></i></button>
        </div>
    `).join('');
}

async function checkoutCart() {
    if (cart.length === 0) return Core.showToast('Cart is empty', 'error');
    const email = localStorage.getItem('store_email');
    if (!email) { toggleCartDrawer(); openAuthModal('signin'); return; }

    const btn = $('btn-cart-checkout'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...'; btn.disabled = true;

    try {
        const res = await fetch('/api/store/checkout-cart', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cart: cart })
        });
        const data = await res.json();
        if (data.success) {
            let successCodes = data.results.filter(r => r.status === 'Success');
            let failedCodes = data.results.filter(r => r.status === 'Failed');

            if (successCodes.length > 0) {
                let codesHtml = successCodes.map(r => `<div class="bg-black p-2 rounded border border-gray-800 break-all mb-1 font-mono text-sm">${r.name}: <span class="text-szgreen">${r.code}</span></div>`).join('');
                $('purchased-code').innerHTML = codesHtml;
                $('purchased-code').classList.remove('tracking-wider', 'text-lg');
                cart = cart.filter(cItem => !successCodes.some(sc => sc.name === cItem.stock_key));
                updateCartUI();
                if(data.new_balances) updateUIDynamic(localStorage.getItem('store_name'), data.new_balances);
                toggleCartDrawer();
                openModal('success-modal');
            }
            if (failedCodes.length > 0) Core.showToast(`${failedCodes.length} items failed`, 'error');
            else if (successCodes.length > 0) Core.showToast(`Checkout successful!`, 'success');
        } else { Core.showToast(data.msg || "Error", "error"); }
    } catch { Core.showToast("Network error", "error"); }
    btn.innerHTML = orig; btn.disabled = false;
}

// --- Direct Buy ---
function buyProductDynamic(stock_key, prices_json, name, iconClass) {
    if (!localStorage.getItem('store_email')) { openAuthModal('signin'); return; }
    const finalPrice = prices_json[currentCurrency] || 0;
    pendingPurchase = { stock_key, price: finalPrice, currency: currentCurrency };

    const priceText = finalPrice + ' ' + currentCurrency;
    const pClass = currentCurrency === 'EGP' ? 'text-yellow-500' : 'text-szcyan';

    if($('checkout-item-price')) {
        $('checkout-item-price').className = `p-4 text-right font-black text-lg ${pClass}`;
        $('checkout-item-price').innerText = priceText;
    }
    if($('checkout-total-price')) {
        $('checkout-total-price').innerText = priceText;
        $('checkout-total-price').className = `text-2xl font-black ${pClass}`;
    }
    if($('checkout-user-name')) $('checkout-user-name').innerText = localStorage.getItem('store_name');
    if($('checkout-user-email')) $('checkout-user-email').innerText = localStorage.getItem('store_email');
    if($('checkout-item-name')) $('checkout-item-name').innerText = name;

    openModal('checkout-modal');
}

async function confirmPurchase() {
    if (!pendingPurchase) return;
    const btn = $('btn-confirm-pay'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...'; btn.disabled = true;

    const fd = new FormData();
    fd.append('stock_key', pendingPurchase.stock_key);
    fd.append('price', pendingPurchase.price);
    fd.append('currency', pendingPurchase.currency);

    try {
        const res = await (await fetch('/api/store/buy', { method: 'POST', body: fd })).json();
        if (res.success) {
            closeModal('checkout-modal');
            if($('purchased-code')) {
                $('purchased-code').innerHTML = res.code;
                $('purchased-code').className = "text-lg font-mono text-szgreen tracking-wider select-all";
            }
            const bals = {}; bals[res.currency] = res.new_balance;
            updateUIDynamic(localStorage.getItem('store_name'), bals);
            openModal('success-modal');
        } else { Core.showToast(res.msg, "error"); if (res.force_logout) logout(); }
    } catch { Core.showToast("Network error", "error"); }
    btn.innerHTML = orig; btn.disabled = false;
}

function copyPurchasedCode() {
    const text = $('purchased-code')?.innerText;
    if(text) { navigator.clipboard.writeText(text); Core.showToast("Copied!", "success"); }
}

// --- Profile & Account ---
function updateUIDynamic(name, balances) {
    if($('sidebar-ui-name')) $('sidebar-ui-name').innerText = name;
    for (const [curr, val] of Object.entries(balances)) {
        const el = $(`sidebar-ui-bal-${curr.toLowerCase()}`);
        if (el) el.innerText = val;
        const profEl = $(`prof-bal-${curr.toLowerCase()}`);
        if (profEl) profEl.innerText = val;
    }
} // <--- تم إصلاح الكارثة وإضافة قوس الإغلاق هنا!

function openProfileModal() {
    if($('prof-name')) $('prof-name').innerText = localStorage.getItem('store_name');
    if($('prof-email')) $('prof-email').innerText = localStorage.getItem('store_email');
    if($('edit-name')) $('edit-name').value = localStorage.getItem('store_name') || '';

    const avImg = $('prof-avatar-img'), avIcon = $('prof-avatar-icon');
    const editImg = $('edit-avatar-preview'), editIcon = $('edit-avatar-icon');
    
    if (localStorage.getItem('store_avatar')) {
        if(avImg) { avImg.src = localStorage.getItem('store_avatar'); avImg.classList.remove('hidden'); }
        if(avIcon) avIcon.classList.add('hidden');
        if(editImg) { editImg.src = localStorage.getItem('store_avatar'); editImg.classList.remove('hidden'); }
        if(editIcon) editIcon.classList.add('hidden');
    }
    openModal('profile-modal');
}

function previewAvatar(input) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const img = $('edit-avatar-preview');
            const icon = $('edit-avatar-icon');
            if(img) { img.src = e.target.result; img.classList.remove('hidden'); }
            if(icon) { icon.classList.add('hidden'); }
        }
        reader.readAsDataURL(input.files[0]);
    }
}

async function doChangePassword(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData();
    fd.append('old_password', $('edit-old-pass').value);
    fd.append('new_password', $('edit-new-pass').value);
    try {
        const res = await (await fetch('/api/store/change-password', { method: 'POST', body: fd })).json();
        if (res.success) {
            Core.showToast(res.msg, 'success');
            $('edit-old-pass').value = '';
            $('edit-new-pass').value = '';
        } else { Core.showToast(res.msg, 'error'); }
    } catch { Core.showToast('Network Error!', 'error'); }
    btn.innerHTML = orig; btn.disabled = false;
}

async function doUpdateProfile(e) {
    e.preventDefault();
    const name = $('edit-name').value;
    const avatarFile = $('edit-avatar').files ? $('edit-avatar').files[0] : null;

    try {
        const fd1 = new FormData(); fd1.append('name', name);
        await fetch('/api/store/update-profile', { method: 'POST', body: fd1 });
        if (avatarFile) {
            const fd2 = new FormData(); fd2.append('avatar', avatarFile);
            await fetch('/api/store/update-avatar', { method: 'POST', body: fd2 });
        }
        localStorage.setItem('store_name', name);
        Core.showToast("Profile Updated!");
        setTimeout(() => location.reload(), 1000);
    } catch { Core.showToast("Error updating profile", "error"); }
}

async function doChangeEmailRequest(e) {
    e.preventDefault();
    const newEmail = $('edit-new-email').value;
    const btn = e.target.querySelector('button'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData(); fd.append('new_email', newEmail);
    try {
        const res = await (await fetch('/api/store/change-email-request', { method: 'POST', body: fd })).json();
        if (res.success) {
            Core.showToast(res.msg);
            $('email-change-form')?.classList.add('hidden');
            $('email-verify-form')?.classList.remove('hidden');
        } else { Core.showToast(res.msg, 'error'); }
    } catch { Core.showToast('Error!', 'error'); }
    btn.innerHTML = orig; btn.disabled = false;
}

async function doChangeEmailVerify(e) {
    e.preventDefault();
    const newEmail = $('edit-new-email').value, code = $('edit-email-code').value;
    const btn = e.target.querySelector('button'), orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData(); fd.append('new_email', newEmail); fd.append('code', code);
    try {
        const res = await (await fetch('/api/store/change-email-verify', { method: 'POST', body: fd })).json();
        if (res.success) {
            Core.showToast('Email changed successfully!');
            localStorage.setItem('store_email', newEmail);
            setTimeout(() => location.reload(), 1000);
        } else { Core.showToast(res.msg, 'error'); }
    } catch { Core.showToast('Error!', 'error'); }
    btn.innerHTML = orig; btn.disabled = false;
}

async function fetchMyOrders() {
    const tbody = $('orders-table-body'), loader = $('orders-loading');
    if(tbody) tbody.innerHTML = '';
    if(loader) loader.classList.remove('hidden');
    try {
        const res = await (await fetch('/api/store/my-orders')).json();
        if(loader) loader.classList.add('hidden');
        if (res.success && res.orders.length > 0) {
            if(tbody) tbody.innerHTML = res.orders.map(o => `
                <tr class="hover:bg-gray-900 transition">
                    <td class="px-4 py-3 font-mono text-szcyan">#${o.order_id}</td>
                    <td class="px-4 py-3 text-xs text-gray-500">${new Date(o.date).toLocaleString()}</td>
                    <td class="px-4 py-3 font-bold text-white">${o.category}</td>
                    <td class="px-4 py-3 text-[10px]"><span class="bg-gray-800 px-2 py-1 rounded border border-gray-700">${o.price} ${o.currency}</span></td>
                    <td class="px-4 py-3 font-mono text-szgreen select-all">${o.code}</td>
                </tr>
            `).join('');
        } else {
            if(tbody) tbody.innerHTML = `<tr><td colspan="5" class="py-8 text-center text-gray-500">No purchases found.</td></tr>`;
        }
    } catch {
        if(loader) loader.classList.add('hidden');
        if(tbody) tbody.innerHTML = `<tr><td colspan="5" class="py-8 text-center text-red-500">Error loading orders.</td></tr>`;
    }
}

// --- Core Extenders for missing HTML calls ---
Core.initGoogleLogin = function() {
    Core.showToast("Please click exactly on the Google button.", "error");
};
Core.initTelegramLogin = function() {
    Core.showToast("Please click exactly on the Telegram button.", "error");
};

// --- Init ---
document.addEventListener("DOMContentLoaded", () => {
    updateCartUI();
    if($('sidebar-user') && localStorage.getItem('store_email')) {
        $('sidebar-guest')?.classList.add('hidden');
        $('sidebar-user')?.classList.remove('hidden');
        $('sidebar-logout-btn')?.classList.remove('hidden');
        if($('sidebar-ui-name')) $('sidebar-ui-name').innerText = localStorage.getItem('store_name');
    }
});
