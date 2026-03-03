// Saleh Zone Store Engine v1.0
let pendingPurchase = null;
let ordersLoaded = false;

// تحديث واجهة المستخدم (الرصيد والاسم)
function updateUI(name, balEgp, balUsd) {
    const guestEl = document.getElementById('sidebar-guest');
    const userEl = document.getElementById('sidebar-user');
    const logoutBtn = document.getElementById('sidebar-logout-btn');

    if(guestEl) guestEl.classList.add('hidden');
    if(userEl) userEl.classList.remove('hidden');
    if(logoutBtn) logoutBtn.classList.remove('hidden');
    
    document.getElementById('sidebar-ui-name').innerText = name;
    document.getElementById('sidebar-ui-bal-egp').innerText = balEgp;
    document.getElementById('sidebar-ui-bal-usd').innerText = balUsd;
    
    // تحديث بيانات البروفايل
    if(document.getElementById('prof-name')) {
        document.getElementById('prof-name').innerText = name;
        document.getElementById('prof-email').innerText = localStorage.getItem('store_email') || 'N/A';
        document.getElementById('prof-bal-egp').innerText = balEgp;
        document.getElementById('prof-bal-usd').innerText = balUsd;
    }

    localStorage.setItem('bal_egp', balEgp);
    localStorage.setItem('bal_usd', balUsd);
}

function saveAndLogin(data) {
    localStorage.setItem('store_email', data.email);
    localStorage.setItem('store_name', data.name);
    updateUI(data.name, data.balance_egp, data.balance_usd);
    Core.closeModal('auth-modal');
    Core.showToast(`Welcome back, ${data.name}!`);
}

async function logout() { 
    await fetch('/api/store/logout', {method: 'POST'});
    localStorage.clear(); 
    location.reload(); 
}

// ================= أنظمة الحسابات =================
async function doManualLogin(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-signin');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    
    const fd = new FormData(); 
    fd.append('email', document.getElementById('signin-email').value); 
    fd.append('password', document.getElementById('signin-password').value);
    
    try {
        const res = await fetch('/api/store/login-manual', {method: 'POST', body: fd});
        const data = await res.json();
        if(data.success) { saveAndLogin(data); } 
        else { setStatus(data.msg, true); }
    } catch(err) { setStatus('Connection error!', true); }
    btn.innerHTML = originalText; btn.disabled = false;
}

async function doSignupRequest(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-signup');
    const pass = document.getElementById('signup-password').value;
    const conf = document.getElementById('signup-confirm').value;

    if(pass !== conf) { setStatus("Passwords mismatch!", true); return; }

    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData(); 
    fd.append('name', document.getElementById('signup-name').value); 
    fd.append('username', document.getElementById('signup-username').value); 
    fd.append('email', document.getElementById('signup-email').value); 
    fd.append('password', pass);
    
    try {
        const res = await fetch('/api/store/signup-request', {method: 'POST', body: fd});
        const data = await res.json();
        if(data.success) { switchAuthView('otp'); setStatus(data.msg); } 
        else { setStatus(data.msg, true); }
    } catch(err) { setStatus('Error!', true); }
    btn.innerHTML = 'Create Account'; btn.disabled = false;
}

async function doForgotPassword(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-forgot');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
    const fd = new FormData(); fd.append('email', document.getElementById('forgot-email').value);
    try { 
        const res = await fetch('/api/store/forgot-password', {method: 'POST', body: fd});
        const data = await res.json(); 
        if(data.success) { switchAuthView('reset'); setStatus(data.msg); } 
        else { setStatus(data.msg, true); }
    } catch(err) { setStatus('Error!', true); }
    btn.innerHTML = 'Send Reset Link'; btn.disabled = false;
}

// ================= الشراء والطلبات =================
function buyProduct(stock_key, pEgp, pUsd, name, iconClass) {
    const email = localStorage.getItem('store_email');
    if(!email) { openAuthModal('signin'); return; }

    const finalPrice = currentCurrency === 'EGP' ? pEgp : pUsd;
    pendingPurchase = { stock_key, price: finalPrice, currency: currentCurrency };

    document.getElementById('checkout-user-name').innerText = localStorage.getItem('store_name');
    document.getElementById('checkout-user-email').innerText = email;
    document.getElementById('checkout-item-name').innerText = name;
    if(iconClass) document.getElementById('checkout-item-icon').className = `fas ${iconClass}`;

    const priceText = finalPrice + ' ' + currentCurrency;
    const priceColorClass = currentCurrency === 'EGP' ? 'text-yellow-500' : 'text-szcyan';
    
    document.getElementById('checkout-item-price').innerText = priceText;
    document.getElementById('checkout-item-price').className = `p-4 text-right font-black text-lg ${priceColorClass}`;
    document.getElementById('checkout-total-price').innerText = priceText;
    document.getElementById('checkout-total-price').className = `text-2xl font-black ${priceColorClass}`;

    Core.openModal('checkout-modal');
}

async function confirmPurchase() {
    if(!pendingPurchase) return;
    if(!document.getElementById('terms-checkbox').checked) return alert("Please agree to the Terms.");

    const btn = document.getElementById('btn-confirm-pay');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;

    const fd = new FormData(); 
    fd.append('stock_key', pendingPurchase.stock_key); 
    fd.append('price', pendingPurchase.price); 
    fd.append('currency', pendingPurchase.currency);
    
    try {
        const res = await fetch('/api/store/buy', {method: 'POST', body: fd});
        const data = await res.json();
        if(data.success) {
            updateUI(localStorage.getItem('store_name'), 
                     data.currency === 'EGP' ? data.new_balance : localStorage.getItem('bal_egp'),
                     data.currency === 'USD' ? data.new_balance : localStorage.getItem('bal_usd'));
            ordersLoaded = false; 
            Core.closeModal('checkout-modal');
            document.getElementById('purchased-code').innerText = data.code;
            Core.openModal('success-modal');
        } else { alert(data.msg); }
    } catch(err) { alert("Error!"); }
    btn.innerHTML = 'Confirm & Pay'; btn.disabled = false;
}

// جلب سجل الطلبات للبروفايل
async function fetchMyOrders() {
    const loader = document.getElementById('orders-loading');
    const tbody = document.getElementById('orders-table-body');
    if(loader) loader.classList.remove('hidden');
    if(tbody) tbody.innerHTML = '';
    
    try {
        const res = await fetch('/api/store/my-orders');
        const data = await res.json();
        if(loader) loader.classList.add('hidden');
        
        if(data.success && data.orders.length > 0) {
            let html = '';
            data.orders.forEach(o => {
                const pColor = o.currency === 'USD' ? 'text-szcyan' : 'text-yellow-500';
                html += `
                <tr class="hover:bg-[#111] transition">
                    <td class="px-4 py-3 font-mono text-szcyan">#${o.order_id}</td>
                    <td class="px-4 py-3 text-xs text-gray-500">${o.date}</td>
                    <td class="px-4 py-3 font-bold text-white">${o.category}</td>
                    <td class="px-4 py-3 font-black ${pColor}">${o.price} <span class="text-[10px]">${o.currency}</span></td>
                    <td class="px-4 py-3"><button onclick="Core.copy('${o.code}')" class="bg-gray-900 text-szgreen border border-gray-700 px-3 py-1 rounded text-xs font-mono hover:bg-szgreen hover:text-black transition">Copy</button></td>
                </tr>`;
            });
            if(tbody) tbody.innerHTML = html;
            ordersLoaded = true;
        } else {
            if(tbody) tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500 font-bold">No history found.</td></tr>';
        }
    } catch(e) { if(loader) loader.innerHTML = 'Error.'; }
}
