const API_BASE = '/api/v1';

async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${url}`, {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        });
        return await response.json();
    } catch (error) {
        console.error('API请求失败:', error);
        throw error;
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function formatTime(isoString) {
    if (!isoString) return '-';
    try { return new Date(isoString).toLocaleString('zh-CN'); } catch { return isoString; }
}
