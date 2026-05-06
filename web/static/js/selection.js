const API_BASE = '/api/v1';

document.addEventListener('DOMContentLoaded', () => {
    loadTasks();
    
    document.getElementById('taskForm').addEventListener('submit', handleCreateTask);
    document.getElementById('statusFilter').addEventListener('change', loadTasks);
});

async function loadTasks() {
    const filter = document.getElementById('statusFilter').value;
    const url = filter ? `/selection/tasks?status=${filter}` : '/selection/tasks';
    
    try {
        const data = await apiRequest(url);
        renderTasks(data.tasks || []);
    } catch (error) {
        document.getElementById('tasksBody').innerHTML =
            '<tr><td colspan="6" class="text-center text-danger">加载失败</td></tr>';
    }
}

function renderTasks(tasks) {
    const tbody = document.getElementById('tasksBody');
    
    if (!tasks.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">暂无任务</td></tr>';
        return;
    }
    
    tbody.innerHTML = tasks.map(task => `
        <tr>
            <td><code>${task.task_id.substring(0, 16)}...</code></td>
            <td>${escapeHtml(task.query).substring(0, 30)}${task.query.length > 30 ? '...' : ''}</td>
            <td>${escapeHtml(task.category || '-')}</td>
            <td><span class="badge badge-${task.status}">${task.status}</span></td>
            <td>${formatTime(task.created_at)}</td>
            <td>
                ${task.status === 'completed'
                    ? `<a href="/results/${task.task_id}" class="btn btn-sm btn-primary">查看</a>`
                    : task.status === 'running'
                        ? `<button class="btn btn-sm btn-secondary" onclick="refreshTask('${task.task_id}')">刷新</button>`
                        : '-'}
                ${task.status === 'running' || task.status === 'created'
                    ? `<button class="btn btn-sm btn-outline" onclick="cancelTask('${task.task_id}')" style="margin-left:4px">取消</button>`
                    : ''}
            </td>
        </tr>
    `).join('');
}

async function handleCreateTask(e) {
    e.preventDefault();
    
    const submitBtn = document.getElementById('submitBtn');
    const resultDiv = document.getElementById('submitResult');
    
    submitBtn.disabled = true;
    submitBtn.textContent = '⏳ 创建中...';
    
    const formData = new FormData(e.target);
    const payload = {
        query: formData.get('query'),
        category: formData.get('category'),
        investment_budget: parseFloat(formData.get('investment_budget')) || 50000,
        target_market: formData.get('target_market'),
        auto_approve: formData.get('auto_approve') === 'on',
    };
    
    try {
        const result = await apiRequest('/selection/tasks', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        
        resultDiv.className = 'submit-result success';
        resultDiv.innerHTML = `
            <div class="success-message">
                ✅ 任务创建成功！
                <p>任务ID: <code>${result.task_id}</code></p>
                <p>状态: ${result.status}</p>
                <a href="/results/${result.task_id}" class="btn btn-sm btn-primary" style="margin-top:0.5rem">查看详情</a>
            </div>
        `;
        
        e.target.reset();
        loadTasks();
        
        setTimeout(() => {
            if (result.status === 'running' || result.status === 'completed') {
                loadTasks();
            }
        }, 3000);
        
    } catch (error) {
        resultDiv.className = 'submit-result error';
        resultDiv.innerHTML = `
            <div class="error-message">
                ❌ 创建失败: ${error.message || '未知错误'}
            </div>
        `;
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '🚀 启动选品分析';
    }
}

async function cancelTask(taskId) {
    if (!confirm('确定要取消此任务吗？')) return;
    
    try {
        await apiRequest(`/selection/tasks/${taskId}`, { method: 'DELETE' });
        showToast('任务已取消', 'success');
        loadTasks();
    } catch (error) {
        showToast('取消失败: ' + error.message, 'error');
    }
}

async function refreshTask(taskId) {
    loadTasks();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
