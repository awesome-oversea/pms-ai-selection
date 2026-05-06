const API_BASE = '/api/v1';
const TOKEN_KEY = 'pms_workbench_token';

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
}

function authHeaders() {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
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
    return data.data || data;
}

async function login() {
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.message || payload.detail || '登录失败');
    }
    const data = payload.data || payload;
    setToken(data.access_token);
    document.getElementById('authStatus').textContent = `已登录：${username}`;
    await loadWorkbench();
}

async function loadSummary() {
    try {
        const data = await apiRequest('/bff/workbench/selection/summary');
        document.getElementById('totalTasks').textContent = data.total;
        document.getElementById('completedTasks').textContent = data.by_status.completed || 0;
        document.getElementById('runningTasks').textContent = data.by_status.running || 0;
        document.getElementById('failedTasks').textContent = data.by_status.failed || 0;
        document.getElementById('successRate').textContent = data.success_rate ? data.success_rate + '%' : '0%';
        document.getElementById('goDecisionRate').textContent = data.go_decision_rate ? data.go_decision_rate + '%' : '0%';
    } catch (error) {
        console.error('加载汇总失败:', error);
        document.getElementById('totalTasks').textContent = '0';
        document.getElementById('completedTasks').textContent = '0';
        document.getElementById('runningTasks').textContent = '0';
        document.getElementById('failedTasks').textContent = '0';
        document.getElementById('successRate').textContent = '0%';
        document.getElementById('goDecisionRate').textContent = '0%';
    }
}

function setupTemplateButtons() {
    const templates = {
        'templateElectronics': {
            query: '智能蓝牙耳机',
            category: 'electronics',
            target_market: 'US',
            investment_budget: 50000,
            priority: 'normal',
            auto_approve: false
        },
        'templateHomeGarden': {
            query: '智能花园浇水系统',
            category: 'home_garden',
            target_market: 'US',
            investment_budget: 30000,
            priority: 'normal',
            auto_approve: false
        },
        'templateBeauty': {
            query: '天然有机护肤品',
            category: 'beauty',
            target_market: 'EU',
            investment_budget: 20000,
            priority: 'normal',
            auto_approve: false
        },
        'templateSports': {
            query: '便携式运动相机',
            category: 'sports',
            target_market: 'US',
            investment_budget: 40000,
            priority: 'normal',
            auto_approve: false
        }
    };

    Object.keys(templates).forEach(templateId => {
        const button = document.getElementById(templateId);
        if (button) {
            button.addEventListener('click', () => {
                const template = templates[templateId];
                document.getElementById('query').value = template.query;
                document.getElementById('category').value = template.category;
                document.getElementById('market').value = template.target_market;
                document.getElementById('budget').value = template.investment_budget;
                document.getElementById('priority').value = template.priority;
                document.getElementById('autoApprove').checked = template.auto_approve;
                showMessage('已加载任务模板', 'success');
            });
        }
    });
}

function showMessage(message, type = 'success') {
    const result = document.getElementById('createResult');
    result.className = `submit-result ${type}`;
    result.textContent = message;
    result.classList.remove('hidden');
    setTimeout(() => {
        result.classList.add('hidden');
    }, 3000);
}

function getStatusBadge(status) {
    const statusMap = {
        'completed': { class: 'badge-success', text: '已完成' },
        'running': { class: 'badge-warning', text: '运行中' },
        'pending': { class: 'badge-info', text: '待处理' },
        'failed': { class: 'badge-danger', text: '失败' },
        'cancelled': { class: 'badge-danger', text: '已取消' }
    };
    const config = statusMap[status] || { class: 'badge-info', text: status };
    return `<span class="badge ${config.class}">${config.text}</span>`;
}

async function loadTasks() {
    try {
        const statusFilter = document.getElementById('statusFilter').value;
        const url = statusFilter ? `/bff/workbench/selection/tasks?status=${statusFilter}` : '/bff/workbench/selection/tasks';
        const data = await apiRequest(url);
        const tbody = document.getElementById('workbenchTasksBody');
        const tasks = data.tasks || [];
        if (!tasks.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">暂无任务</td></tr>';
            return;
        }
        tbody.innerHTML = tasks.map(task => `
            <tr>
                <td><code>${task.task_id.slice(0, 12)}...</code></td>
                <td>${task.query}</td>
                <td>${task.target_market}</td>
                <td>${getStatusBadge(task.status)}</td>
                <td>${task.phase || '-'}</td>
                <td>${task.created_at || '-'}</td>
                <td>
                    <button class="btn btn-outline btn-sm" onclick="viewTask('${task.task_id}')">查看</button>
                    ${task.status === 'pending' ? `<button class="btn btn-outline btn-sm" onclick="cancelTask('${task.task_id}')">取消</button>` : ''}
                </td>
            </tr>
        `).join('');
    } catch (error) {
        const tbody = document.getElementById('workbenchTasksBody');
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">加载任务失败：${error.message}</td></tr>`;
    }
}

async function loadWorkbench() {
    if (!getToken()) {
        document.getElementById('authStatus').textContent = '未登录';
        return;
    }
    await loadSummary();
    await loadTasks();
}

async function createTask(event) {
    event.preventDefault();
    const form = new FormData(event.target);
    const payload = {
        query: form.get('query'),
        category: form.get('category'),
        target_market: form.get('target_market'),
        investment_budget: Number(form.get('investment_budget') || 50000),
        auto_approve: form.get('auto_approve') === 'on',
        priority: form.get('priority') || 'normal'
    };
    try {
        const data = await apiRequest('/bff/workbench/selection/tasks', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        document.getElementById('createResult').className = 'submit-result success';
        document.getElementById('createResult').textContent = `任务创建成功：${data.task_id}`;
        event.target.reset();
        await loadWorkbench();
    } catch (error) {
        const result = document.getElementById('createResult');
        result.className = 'submit-result error';
        result.textContent = `创建失败：${error.message}`;
    }
}

async function viewTask(taskId) {
    try {
        const task = await apiRequest(`/bff/workbench/selection/tasks/${taskId}`);
        const modalBody = document.getElementById('taskModalBody');
        
        // 构建阶段指示器
        const phases = ['data_collection', 'market_analysis', 'product_planning', 'commercial_evaluation'];
        const phaseNames = ['数据收集', '市场分析', '产品规划', '商业评估'];
        const phaseHTML = phases.map((phase, index) => {
            let phaseClass = 'phase-pending';
            if (task.phase === phase) {
                phaseClass = 'phase-current';
            } else if (phases.indexOf(task.phase) > index) {
                phaseClass = 'phase-completed';
            }
            return `<div class="phase-item ${phaseClass}">${phaseNames[index]}</div>`;
        }).join('');
        
        // 构建任务详情
        modalBody.innerHTML = `
            <div style="margin-bottom: 1rem;">
                <h4>基本信息</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1rem;">
                    <div><strong>任务ID:</strong> ${task.task_id}</div>
                    <div><strong>查询关键词:</strong> ${task.query}</div>
                    <div><strong>目标市场:</strong> ${task.target_market}</div>
                    <div><strong>投资预算:</strong> $${task.investment_budget}</div>
                    <div><strong>优先级:</strong> ${task.priority}</div>
                    <div><strong>状态:</strong> ${getStatusBadge(task.status)}</div>
                    <div><strong>创建时间:</strong> ${task.created_at}</div>
                    <div><strong>完成时间:</strong> ${task.completed_at || '未完成'}</div>
                </div>
            </div>
            
            <div style="margin-bottom: 1rem;">
                <h4>执行阶段</h4>
                <div class="phase-indicator">
                    ${phaseHTML}
                </div>
            </div>
            
            ${task.result ? `
                <div style="margin-bottom: 1rem;">
                    <h4>执行结果</h4>
                    <div style="background: #f8f9fa; padding: 1rem; border-radius: 4px; margin-top: 1rem;">
                        <strong>决策结果:</strong> ${task.go_no_go_decision || '无'}
                        ${task.go_no_go ? `<br><strong>决策详情:</strong> ${JSON.stringify(task.go_no_go, null, 2)}` : ''}
                    </div>
                </div>
            ` : ''}
            
            ${task.error ? `
                <div style="margin-bottom: 1rem;">
                    <h4>错误信息</h4>
                    <div class="submit-result error">${task.error}</div>
                </div>
            ` : ''}
        `;
        
        // 显示模态框
        document.getElementById('taskModal').style.display = 'block';
    } catch (error) {
        alert(`查看任务失败：${error.message}`);
    }
}

async function cancelTask(taskId) {
    if (!confirm('确定要取消这个任务吗？')) {
        return;
    }
    try {
        await apiRequest(`/bff/workbench/selection/tasks/${taskId}/cancel`, {
            method: 'POST'
        });
        await loadTasks();
        alert('任务已取消');
    } catch (error) {
        alert(`取消任务失败：${error.message}`);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // 登录按钮
    document.getElementById('loginBtn').addEventListener('click', async () => {
        try {
            await login();
        } catch (error) {
            document.getElementById('authStatus').textContent = `登录失败：${error.message}`;
        }
    });
    
    // 退出按钮
    document.getElementById('logoutBtn').addEventListener('click', () => {
        clearToken();
        document.getElementById('authStatus').textContent = '已退出';
        document.getElementById('summaryPanel').textContent = '请先登录后加载汇总';
        document.getElementById('workbenchTasksBody').innerHTML = '<tr><td colspan="7" class="loading">请先登录</td></tr>';
    });
    
    // 表单提交
    document.getElementById('workbenchTaskForm').addEventListener('submit', async (event) => {
        try {
            await createTask(event);
        } catch (error) {
            const result = document.getElementById('createResult');
            result.className = 'submit-result error';
            result.textContent = `创建失败：${error.message}`;
        }
    });
    
    // 状态过滤
    document.getElementById('statusFilter').addEventListener('change', loadTasks);
    
    // 刷新按钮
    document.getElementById('refreshBtn').addEventListener('click', loadTasks);
    
    // 模态框关闭
    document.querySelector('.close').addEventListener('click', () => {
        document.getElementById('taskModal').style.display = 'none';
    });
    
    // 点击模态框外部关闭
    window.addEventListener('click', (event) => {
        const modal = document.getElementById('taskModal');
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // 初始化任务模板按钮
    setupTemplateButtons();
    
    // 初始化加载
    loadWorkbench().catch(() => {});
});
