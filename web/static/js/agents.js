const API_BASE = '/api/v1';

async function checkHealth(agentName) {
    const statusBar = document.getElementById(`status-${agentName}`);
    const resultDiv = document.getElementById('healthCheckResult');
    
    statusBar.style.background = '#f59e0b';
    
    try {
        const data = await apiRequest(`/agents/${agentName}/health`);
        
        statusBar.style.background = data.status === 'healthy' ? '#10b981' : '#ef4444';
        
        resultDiv.innerHTML = `
            <div class="health-card health-${data.status}">
                <h4>📡 ${data.agent_name} 健康报告</h4>
                <div class="health-checks">
                    ${Object.entries(data.checks || {}).map(([key, value]) => `
                        <div class="check-item">
                            <span class="check-label">${formatCheckName(key)}</span>
                            <span class="check-value ${value ? 'ok' : 'fail'}">
                                ${value ? '✅ 通过' : '❌ 失败'}
                            </span>
                        </div>
                    `).join('')}
                </div>
                ${data.error ? `<p class="error-text">⚠️ ${escapeHtml(data.error)}</p>` : ''}
            </div>
        `;
        
    } catch (error) {
        statusBar.style.background = '#ef4444';
        resultDiv.innerHTML = `
            <div class="health-card health-error">
                <h4>❌ 检查失败</h4>
                <p>${escapeHtml(error.message)}</p>
            </div>
        `;
    }
}

async function showDetails(agentName) {
    try {
        const data = await apiRequest(`/agents/${agentName}`);
        const section = document.getElementById('agentDetailsSection');
        const content = document.getElementById('agentDetailContent');
        
        document.getElementById('detailAgentName').textContent = agentName;
        
        content.innerHTML = `
            <div class="detail-grid">
                <div class="detail-item">
                    <span class="detail-label">Agent名称</span>
                    <span class="detail-value">${escapeHtml(data.name)}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">类型</span>
                    <span class="detail-value">${escapeHtml(data.agent_type)}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">版本</span>
                    <span class="detail-value">${escapeHtml(data.version)}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">超时时间</span>
                    <span class="detail-value">${data.timeout_seconds}s</span>
                </div>
            </div>
            
            <h4 style="margin: 1rem 0 0.5rem">能力列表</h4>
            <ul class="capability-list">
                ${(data.capabilities || []).map(c => `<li>${escapeHtml(c)}</li>`).join('') || '<li>暂无</li>'}
            </ul>
            
            <h4 style="margin: 1rem 0 0.5rem">所需输入</h4>
            <ul class="capability-list">
                ${(data.required_inputs || []).map(i => `<li><code>${escapeHtml(i)}</code></li>`).join('') || '<li>无特殊要求</li>'}
            </ul>
            
            <div style="margin-top:1rem">
                <button class="btn btn-primary" onclick="invokeAgent('${agentName}')">🧪 测试调用</button>
            </div>
        `;
        
        section.classList.remove('hidden');
        
    } catch (error) {
        console.error('获取详情失败:', error);
    }
}

async function invokeAgent(agentName) {
    try {
        const result = await apiRequest(`/agents/${agentName}/invoke`, {
            method: 'POST',
            body: JSON.stringify({ query: '测试调用', category: 'test' }),
        });
        
        alert(`调用成功!\n状态: ${result.status}\n步骤数: ${result.steps_count}\n耗时: ${result.execution_time}ms`);
        
    } catch (error) {
        alert('调用失败: ' + error.message);
    }
}

function formatCheckName(key) {
    const names = {
        initialization: '初始化',
        tools_loaded: '工具加载',
        quick_test: '快速测试',
    };
    return names[key] || key;
}

async function apiRequest(url, options = {}) {
    const response = await fetch(`${API_BASE}${url}`, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    return await response.json();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
