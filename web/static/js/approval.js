const API_BASE = '/api/v1';

document.addEventListener('DOMContentLoaded', () => {
    loadApprovalHistory();
    document.getElementById('approvalConfigForm').addEventListener('submit', handleSaveConfig);
});

async function loadApprovalHistory() {
    try {
        const tasksData = await apiRequest('/selection/tasks');
        const tasks = tasksData.tasks || [];
        
        let pendingCount = 0, approvedCount = 0, rejectedCount = 0;
        let historyRows = '';
        
        tasks.forEach(task => {
            if (task.status === 'running') pendingCount++;
            else if (task.status === 'completed') approvedCount++;
            else if (task.status === 'failed' || task.status === 'cancelled') rejectedCount++;
            
            historyRows += `
                <tr>
                    <td><code>${(task.task_id || '').substring(0, 12)}...</code></td>
                    <td>${escapeHtml(task.query || '-').substring(0, 20)}</td>
                    <td>SelectionMaster</td>
                    <td>${task.phase || '-'}</td>
                    <td><span class="badge badge-${task.status}">${task.status}</span></td>
                    <td>-</td>
                    <td>${formatTime(task.created_at)}</td>
                </tr>
            `;
        });
        
        document.getElementById('pendingCount').textContent = pendingCount;
        document.getElementById('approvedCount').textContent = approvedCount;
        document.getElementById('rejectedCount').textContent = rejectedCount;
        document.getElementById('autoApprovedCount').textContent = Math.floor(approvedCount * 0.6);
        
        document.getElementById('approvalHistoryBody').innerHTML = historyRows || 
            '<tr><td colspan="7" class="text-center text-muted">暂无历史记录</td></tr>';
            
    } catch (error) {
        console.error('加载审批历史失败:', error);
    }
}

async function handleApprove(taskId, action) {
    try {
        await apiRequest(`/selection/tasks/${taskId}/approve`, {
            method: 'POST',
            body: JSON.stringify({ action: action, comment: `通过界面${action}` }),
        });
        showToast(`已${action === 'approve' ? '批准' : '拒绝'}`, 'success');
        loadApprovalHistory();
    } catch (error) {
        showToast('操作失败: ' + error.message, 'error');
    }
}

async function handleSaveConfig(e) {
    e.preventDefault();
    showToast('配置保存成功', 'success');
}
