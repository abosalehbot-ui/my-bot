<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Saleh Zone</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <script>tailwind.config={theme:{extend:{colors:{szgreen:'#7dfc89',szcyan:'#5eead4',darkbg:'#050505',panelbg:'#111'}}}}</script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
        body { font-family: 'Cairo', sans-serif; background-color: #050505; color: #d1d5db; scroll-behavior: smooth; }
        ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: #050505; } ::-webkit-scrollbar-thumb { background: #333; border-radius: 10px; transition: 0.3s; } ::-webkit-scrollbar-thumb:hover { background: #7dfc89; box-shadow: 0 0 10px #7dfc89; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } } .fade-in { animation: fadeIn 0.5s ease-out forwards; }
        @keyframes pulseGlow { 0% { box-shadow: 0 0 10px rgba(125,252,137,0.2); } 50% { box-shadow: 0 0 20px rgba(125,252,137,0.5); transform: scale(1.02); } 100% { box-shadow: 0 0 10px rgba(125,252,137,0.2); } } .btn-glow { transition: all 0.3s ease; } .btn-glow:hover { animation: pulseGlow 1.5s infinite; }
        
        /* === تصميم أيقونات السوشيال (زي Uiverse بالظبط) === */
        .social-btn {
            position: relative;
            width: 45px;
            height: 45px;
            display: flex;
            justify-content: center;
            align-items: center;
            border-radius: 8px;
            background-color: transparent;
            cursor: pointer;
            transition: background-color 0.3s;
            overflow: hidden;
        }
        .social-btn:hover { background-color: rgba(255,255,255,0.05); }
        .social-btn svg {
            width: 22px;
            height: 22px;
            fill: #9ca3af; /* لون رمادي خفيف */
            transition: fill 0.3s, transform 0.3s;
            position: absolute;
            pointer-events: none;
            z-index: 1;
        }
        /* الألوان عند الوقوف بالماوس */
        .social-btn.google:hover svg { fill: #7dfc89; transform: scale(1.1); }
        .social-btn.telegram:hover svg { fill: #5eead4; transform: scale(1.1); }

        /* حاوية الأزرار الأصلية الشفافة (عشان نخدع المتصفح) */
        .click-overlay {
            position: absolute;
            inset: 0;
            z-index: 10;
            opacity: 0.01; /* شفاف تماماً بس قابل للضغط */
            display: flex;
            justify-content: center;
            align-items: center;
        }
        /* تكبير الإطار المخفي عشان يغطي الأيقونة كلها */
        .click-overlay iframe, .click-overlay > div { transform: scale(2.5); cursor: pointer; }
    </style>
    <script src="https://accounts.google.com/gsi/client" async defer></script>
</head>
<body class="flex items-center justify-center min-h-screen bg-darkbg relative overflow-hidden selection:bg-szgreen selection:text-black">

    <div class="absolute -top-40 -right-40 w-96 h-96 bg-szgreen/10 rounded-full blur-[100px] pointer-events-none"></div>
    <div class="absolute -bottom-40 -left-40 w-96 h-96 bg-szcyan/10 rounded-full blur-[100px] pointer-events-none"></div>

    <div class="w-[320px] bg-[#111827] p-8 rounded-xl shadow-2xl relative z-10 border border-gray-800 fade-in backdrop-blur-sm">
        <p class="text-center text-2xl font-black text-white mb-6">Login</p>
        
        <form class="space-y-4" onsubmit="event.preventDefault(); alert('Manual login is disabled. Please use Google or Telegram below.');">
            <div class="text-sm">
                <label class="block text-gray-400 mb-1">Username</label>
                <input type="text" name="username" placeholder="" class="w-full rounded-md border border-gray-700 bg-[#111827] px-4 py-3 text-gray-200 outline-none focus:border-szgreen transition-colors">
            </div>
            <div class="text-sm">
                <label class="block text-gray-400 mb-1">Password</label>
                <input type="password" name="password" placeholder="" class="w-full rounded-md border border-gray-700 bg-[#111827] px-4 py-3 text-gray-200 outline-none focus:border-szcyan transition-colors">
                <div class="flex justify-end mt-2 mb-4">
                    <a href="#" class="text-xs text-gray-400 hover:text-szcyan hover:underline transition-colors">Forgot Password ?</a>
                </div>
            </div>
            <button class="w-full bg-gradient-to-r from-szgreen to-szcyan text-black py-3 rounded-md font-bold uppercase tracking-wide btn-glow">Sign in</button>
        </form>

        <div class="flex items-center pt-6 pb-2">
            <div class="h-px flex-1 bg-gray-700"></div>
            <p class="px-3 text-sm text-gray-400">Login with social accounts</p>
            <div class="h-px flex-1 bg-gray-700"></div>
        </div>

        <div class="flex justify-center gap-4 mt-4">
            
            <div id="g_id_onload" data-client_id="{{ client_id }}" data-context="signin" data-ux_mode="popup" data-callback="handleGoogleResponse" data-auto_prompt="false"></div>
            
            <div class="social-btn google" aria-label="Log in with Google">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
                    <path d="M16.318 13.714v5.484h9.078c-0.37 2.354-2.745 6.901-9.078 6.901-5.458 0-9.917-4.521-9.917-10.099s4.458-10.099 9.917-10.099c3.109 0 5.193 1.318 6.38 2.464l4.339-4.182c-2.786-2.599-6.396-4.182-10.719-4.182-8.844 0-16 7.151-16 16s7.156 16 16 16c9.234 0 15.365-6.49 15.365-15.635 0-1.052-0.115-1.854-0.255-2.651z"></path>
                </svg>
                <div class="click-overlay">
                    <div class="g_id_signin" data-type="icon" data-shape="circle" data-theme="filled_black" data-text="signin_with" data-size="large"></div>
                </div>
            </div>

            <div class="social-btn telegram" aria-label="Log in with Telegram">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
                    <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a58.14 58.14 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
                </svg>
                <div class="click-overlay">
                    <script async src="https://telegram.org/js/telegram-widget.js?22" data-telegram-login="salehmailbot" data-size="large" data-onauth="onTelegramAuth(user)" data-request-access="write"></script>
                </div>
            </div>

        </div>

        <div id="login-status" class="text-xs font-bold text-center text-szcyan mt-4 h-4"></div>

        <p class="text-center text-xs text-gray-500 mt-6">
            Don't have an account? <a href="#" class="text-gray-200 hover:text-szgreen hover:underline font-bold transition">Sign up</a>
        </p>
    </div>

    <script>
        document.addEventListener("DOMContentLoaded", () => {
            if(localStorage.getItem('store_email')) { window.location.href = '/'; }
        });

        function saveAndRedirect(data) {
            localStorage.setItem('store_email', data.email);
            localStorage.setItem('store_name', data.name);
            localStorage.setItem('store_balance', data.balance);
            window.location.href = '/';
        }

        async function handleGoogleResponse(response) {
            const statusDiv = document.getElementById('login-status');
            statusDiv.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying Google account...';
            const fd = new FormData(); fd.append('credential', response.credential);
            try {
                const res = await fetch('/api/store/google-login', {method: 'POST', body: fd});
                const data = await res.json();
                if(data.success) { saveAndRedirect(data); } else { statusDiv.innerHTML = `<span class="text-red-500">${data.msg}</span>`; }
            } catch(err) { statusDiv.innerHTML = '<span class="text-red-500">Connection error.</span>'; }
        }

        async function onTelegramAuth(user) {
            const statusDiv = document.getElementById('login-status');
            statusDiv.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying Telegram account...';
            
            const fd = new FormData();
            fd.append('tg_id', user.id);
            fd.append('name', user.first_name + (user.last_name ? ' ' + user.last_name : ''));
            fd.append('username', user.username || '');

            try {
                const res = await fetch('/api/store/telegram-login', {method: 'POST', body: fd});
                const data = await res.json();
                if(data.success) { saveAndRedirect(data); } else { statusDiv.innerHTML = `<span class="text-red-500">${data.msg}</span>`; }
            } catch(err) { statusDiv.innerHTML = '<span class="text-red-500">Connection error.</span>'; }
        }
    </script>
</body>
</html>
