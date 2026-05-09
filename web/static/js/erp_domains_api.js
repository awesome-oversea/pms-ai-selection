const ERP_API_BASE = '/api/v1/erp-domains';
const TOKEN_KEY = 'pms_workbench_token';

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function authHeaders() {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
}

async function erpApiRequest(path, options = {}) {
    const response = await fetch(`${ERP_API_BASE}${path}`, {
        headers: {
            'Content-Type': 'application/json',
            ...authHeaders(),
            ...(options.headers || {}),
        },
        ...options,
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.message || data.detail || '请求失败');
    }
    return data;
}

function formatTime(isoString) {
    if (!isoString) return '-';
    try { return new Date(isoString).toLocaleString('zh-CN'); } catch { return isoString; }
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = 'position:fixed;top:20px;right:20px;padding:12px 24px;border-radius:8px;z-index:9999;animation:slideIn 0.3s ease;font-size:14px;';
    const colors = { info: '#4f46e5', success: '#10b981', error: '#ef4444', warning: '#f59e0b' };
    toast.style.background = colors[type] || colors.info;
    toast.style.color = '#fff';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

const ErpDomainsAPI = {
    async listRecommendations(params = {}) {
        const query = new URLSearchParams();
        if (params.category) query.set('category', params.category);
        if (params.target_domain) query.set('target_domain', params.target_domain);
        if (params.execution_state) query.set('execution_state', params.execution_state);
        if (params.priority) query.set('priority', params.priority);
        if (params.limit) query.set('limit', params.limit);
        if (params.offset) query.set('offset', params.offset);
        const qs = query.toString();
        return erpApiRequest(`/recommendations${qs ? '?' + qs : ''}`);
    },

    async getRecommendation(id) {
        return erpApiRequest(`/recommendations/${id}`);
    },

    async approveRecommendation(id, detail) {
        return erpApiRequest(`/recommendations/${id}/approve`, {
            method: 'POST',
            body: JSON.stringify({ detail }),
        });
    },

    async rejectRecommendation(id, reason) {
        return erpApiRequest(`/recommendations/${id}/reject`, {
            method: 'POST',
            body: JSON.stringify({ reason }),
        });
    },

    async getRecommendationStatistics() {
        return erpApiRequest('/recommendations/statistics');
    },

    async generateBidAdjustment(data) {
        return erpApiRequest('/ads/bid-adjustment', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async generateKeywordSuggestion(data) {
        return erpApiRequest('/ads/keyword-suggestion', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async generateBudgetAllocation(data) {
        return erpApiRequest('/ads/budget-allocation', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async generateRestock(data) {
        return erpApiRequest('/fba/restock', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async batchGenerateRestock(items) {
        return erpApiRequest('/fba/batch-restock', {
            method: 'POST',
            body: JSON.stringify({ items }),
        });
    },

    async generateLogisticsRisk(data) {
        return erpApiRequest('/tms/logistics-risk', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async getShippingRates(data) {
        return erpApiRequest('/tms/shipping-rates', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async assessRisk(data) {
        return erpApiRequest('/risk/assess', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async generatePricingSuggestion(data) {
        return erpApiRequest('/pricing/suggest', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async generatePriceAdjustment(data) {
        return erpApiRequest('/pricing/adjust', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async predictInventory(data) {
        return erpApiRequest('/inventory/predict', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async analyzeSentiment(data) {
        return erpApiRequest('/sentiment/analyze', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async getAIFeatureToggle(featureKey) {
        return erpApiRequest(`/sys/ai-feature/${featureKey}`);
    },

    async setAIFeatureToggle(data) {
        return erpApiRequest('/sys/ai-feature', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async submitFeedbackEvent(data) {
        return erpApiRequest('/feedback/event', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    async submitDomainEvent(data) {
        return erpApiRequest('/feedback/domain-event', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },
};
