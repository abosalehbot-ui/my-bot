// Saleh Zone Core Engine v1.0
const Core = {
    // فتح النوافذ المنبثقة
    openModal: (id) => document.getElementById(id)?.classList.remove('hidden'),
    
    // إغلاق النوافذ
    closeModal: (id) => document.getElementById(id)?.classList.add('hidden'),
    
    // التنبيهات الذكية (Toasts)
    showToast: (msg, type = 'success') => {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const toast = document.createElement('div');
        const color = type === 'error' ? 'border-red-500' : 'border-szgreen';
        const icon = type === 'error' ? 'fa-times-circle text-red-500' : 'fa-check-circle text-szgreen';
        
        toast.className = `toast border-l-4 ${color} fade-in`;
        toast.innerHTML = `<i class="fas ${icon} text-xl"></i> <span>${msg}</span>`;
        container.appendChild(toast);
        setTimeout(() => { toast.style.animation = 'fadeOut 0.3s forwards'; setTimeout(() => toast.remove(), 300); }, 3000);
    },

    // نسخ النصوص
    copy: (text) => {
        navigator.clipboard.writeText(text);
        Core.showToast("Copied to clipboard!");
    },

    // تبديل التابات (Generic Tab Switcher)
    switchTab: (tabId, contentClass, btnClass, activeClass, inactiveClass) => {
        document.querySelectorAll(`.${contentClass}`).forEach(el => el.classList.add('hidden'));
        document.getElementById(`tab-${tabId}`)?.classList.remove('hidden');
        
        document.querySelectorAll(`.${btnClass}`).forEach(el => {
            el.classList.remove(...activeClass.split(' '));
            el.classList.add(...inactiveClass.split(' '));
        });
        const activeBtn = document.getElementById(`btn-${tabId}`);
        if (activeBtn) {
            activeBtn.classList.remove(...inactiveClass.split(' '));
            activeBtn.classList.add(...activeClass.split(' '));
        }
    }
};

// إعداد محرك الثيمات عند التحميل
document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem('sz_theme') || 'default';
    document.documentElement.setAttribute('data-theme', savedTheme);
});
