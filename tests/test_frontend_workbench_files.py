from pathlib import Path


def test_frontend_workbench_pages_exist():
    assert Path("frontend/app/page.tsx").exists()
    assert Path("frontend/app/layout.tsx").exists()
    assert Path("frontend/app/login/page.tsx").exists()
    assert Path("frontend/app/workbench/selection/page.tsx").exists()
    assert Path("frontend/app/agents/page.tsx").exists()
    assert Path("frontend/app/knowledge/page.tsx").exists()
    assert Path("frontend/app/operations/page.tsx").exists()
    assert Path("frontend/components/common/AppShell.tsx").exists()


def test_frontend_workbench_navigation_contains_multi_roles():
    content = Path("frontend/app/page.tsx").read_text(encoding="utf-8")
    assert "选品工作台" in content
    assert "Agent 平台" in content
    assert "知识库工作台" in content
    assert "运营台" in content
    assert "适用角色" in content


def test_auth_guard_has_no_hardcoded_auto_login_credentials():
    content = Path("frontend/components/common/AuthGuard.tsx").read_text(encoding="utf-8")
    assert "Audit1234" not in content
    assert "testuser" not in content
    assert "自动登录" not in content



def test_auth_guard_supports_superuser_only_routes():
    content = Path("frontend/components/common/AuthGuard.tsx").read_text(encoding="utf-8")
    assert "requireSuperuser" in content
    assert "需要管理员权限" in content


def test_middleware_protects_workbench_routes():
    content = Path("frontend/middleware.ts").read_text(encoding="utf-8")
    assert "pms_workbench_token" in content
    assert "/login" in content
    assert "/workbench/:path*" in content
    assert "/agents/:path*" in content
    assert "/reports/:path*" in content
    assert "/dashboard/:path*" in content
    assert "/competitors/:path*" in content
    assert "/trends/:path*" in content
    assert "/kpi/:path*" in content
    assert "/analyst/:path*" in content
    assert "/models/:path*" in content
    assert "/procurement/:path*" in content
    assert "/finance/:path*" in content


def test_knowledge_workbench_is_formal_operable_page():
    content = Path("frontend/app/knowledge/page.tsx").read_text(encoding="utf-8")
    assert "上传文档" in content
    assert "执行检索测试" in content
    assert "执行评测" in content
    assert "版本回滚" in content
    assert "切片预览" in content
    assert "知识源模式" in content
    assert "内外部知识库切换" in content
    assert "/knowledge/documents" in content
    assert "/knowledge/query" in content
    assert "/knowledge/evaluate" in content
    assert "/knowledge/service-mode" in content


def test_selection_workbench_contains_detail_approval_feedback_actions():
    content = Path("frontend/components/workbench/SelectionTaskTable.tsx").read_text(encoding="utf-8")
    page_content = Path("frontend/app/workbench/selection/page.tsx").read_text(encoding="utf-8")
    assert "任务详情 / 结果 / 审批 / 反馈" in content
    assert "审批通过" in content
    assert "采纳推荐" in content
    assert "审批拒绝" in content
    assert "提交反馈" in content
    assert "执行闭环" in content
    assert "同步执行反馈" in content
    assert "采纳推荐 / 采购建议" in content
    assert "执行反馈回流 / 自动再评分" in content
    assert "/bff/workbench/selection/tasks/" in content
    assert "/approve" in content
    assert "/adopt" in content
    assert "/feedback" in content
    assert "/result" in content
    assert "/execution-feedback-sync" in content
    assert "/history-case-ingest" in content
    assert "/history-cases/query" in content
    assert "/review-case-ingest" in content
    assert "/review-cases/query" in content
    assert "/close-loop" in content
    assert "/close-loop-overview" in content
    assert "闭环总览 / Profit Trace / 特征资产" in content
    assert "采纳执行状态看板" in content
    assert "历史选品案例入库 / 检索" in content
    assert "相似历史案例 / RAG复用" in content
    assert "CRM好评/差评案例 / 知识复用" in content
    assert "联合历史表现 / OMS CRM SCM WMS" in content
    assert "CRM好评/差评案例入库 / 检索" in content
    assert "similar_history_cases" in content
    assert "review_cases" in content
    assert "historical_performance" in content
    assert "入库历史案例" in content
    assert "检索历史案例" in content
    assert "入库评价案例" in content
    assert "检索评价案例" in content
    assert "execution_status" in content
    assert "Top50 推荐商品列表" in content
    assert "top_recommendations" in content
    assert "compact-table" in content
    assert "通过实时通道人工干预" in content
    assert "/bff/workbench/selection/ws" in page_content
    assert "待审批" in page_content
    assert "高风险任务" in page_content
    assert "平均 ROI" in page_content
    assert "数据来源" in page_content
    assert "ECharts趋势图 / 准确率趋势" in page_content
    assert "accuracy_trend" in page_content


def test_agent_platform_contains_log_panel():
    content = Path("frontend/app/agents/page.tsx").read_text(encoding="utf-8")
    log_panel = Path("frontend/components/agents/LogPanel.tsx").read_text(encoding="utf-8")
    workflow_debug_panel = Path("frontend/components/agents/WorkflowDebugPanel.tsx").read_text(encoding="utf-8")
    operations_panel = Path("frontend/components/agents/OperationsPanel.tsx").read_text(encoding="utf-8")
    topology_panel = Path("frontend/components/agents/TopologyPanel.tsx").read_text(encoding="utf-8")
    assert "LogPanel" in content
    assert "日志与历史" in log_panel
    assert "状态原因日志" in log_panel
    assert "重试历史日志" in log_panel
    assert "人工介入日志" in log_panel
    assert "Trace ID / Request ID" in log_panel
    assert "trace=" in log_panel
    assert "request=" in log_panel
    assert "状态回滚" in workflow_debug_panel
    assert "/rollback" in workflow_debug_panel
    assert "回滚目标节点" in workflow_debug_panel
    assert "生命周期" in operations_panel
    assert "lifecycle_summary" in operations_panel
    assert "lifecycle_actions" in operations_panel
    assert "Token/成本实时统计" in operations_panel
    assert "LangGraph DAG 可视化" in topology_panel
    assert "agent_cost_summary" in topology_panel
    assert "risk_assessment" in topology_panel
    assert "report_generation" in topology_panel



def test_dashboard_uses_unified_chart_components_and_five_chart_types():
    dashboard = Path("frontend/app/dashboard/page.tsx").read_text(encoding="utf-8")
    chart_components = Path("frontend/components/common/DashboardCharts.tsx").read_text(encoding="utf-8")
    assert "DashboardCharts" in dashboard
    assert "数据来源" in dashboard
    assert "GMV" in dashboard
    assert "完成率" in dashboard
    assert "execution_chart" in chart_components
    assert "RankingChartCard" in chart_components
    assert "ProgressChartCard" in chart_components
    assert "LineTrendCard" in chart_components
    assert "BarChartCard" in chart_components
    assert "PieLikeCard" in chart_components



def test_operations_page_exposes_real_operations_panels():
    content = Path("frontend/app/operations/page.tsx").read_text(encoding="utf-8")
    assert "/config-operations" in content
    assert "/tenant-operations" in content
    assert "/audit-operations" in content
    assert "/audit/logs" in content
    assert "/release/status" in content
    assert "/security/status" in content
    assert "/llm-governance/status" in content
    assert "GatewayGovernanceStatus" in content
    assert "MetricsDashboardStatus" in content
    assert "网关灰度与仪表板导入" in content
    assert "配置治理" in content
    assert "租户与配额" in content
    assert "审计与追踪" in content
    assert "安全与 LLM 治理" in content
    assert "网关灰度与仪表板导入" in content
    assert "外部数据联调 readiness" in content
    assert "/external-collection/readiness" in content
    assert "正式 API 就绪数" in content
    assert "本地验证来源数" in content
    assert "阻塞来源数" in content
    assert "调度与ETL" in content
    assert "业务可消费" in content
    assert "质量评分" in content
    assert "失败摘要" in content
    assert "实时推送通道" in content
    assert "验证码识别" in content
    assert "Canary 策略" in content
    assert "Grafana 导入" in content
    assert "DataPlatformStatus" in content
    assert "RealtimeStatus" in content
    assert "/data-platform/runtime" in content
    assert "/realtime/status" in content
    assert "/llm/inference/health" in content
    assert "Ray / 分布式接口" in content
    assert "GPU监控状态" in content
    assert "可观测级别" in content
    assert "告警数" in content
    assert "指标新鲜度" in content
    assert "/security/captcha-ocr" in content
    assert "执行验证码识别" in content
    assert "ETL引擎" in content
    assert "重连策略" in content
    assert "导出配额快照" in content
    assert "导出治理快照" in content
    assert "查询审计" in content


def test_app_shell_and_frontend_scripts_exist():
    shell = Path("frontend/components/common/AppShell.tsx").read_text(encoding="utf-8")
    layout = Path("frontend/app/layout.tsx").read_text(encoding="utf-8")
    login = Path("frontend/app/login/page.tsx").read_text(encoding="utf-8")
    manifest = Path("frontend/app/manifest.ts").read_text(encoding="utf-8")
    package_json = Path("frontend/package.json").read_text(encoding="utf-8")
    smoke_script = Path("scripts/frontend_smoke_check.mjs").read_text(encoding="utf-8")
    evidence_script = Path("scripts/frontend_evidence_manifest.mjs").read_text(encoding="utf-8")
    playwright_config = Path("frontend/playwright.config.ts").read_text(encoding="utf-8")
    assert "蓝图总览" in shell
    assert "企业级 AI 选品中枢" in shell
    assert "AppShell" in layout
    assert "manifest: '/manifest.webmanifest'" in layout
    assert "themeColor" in layout
    assert "/auth/oidc/discovery" in login
    assert "/auth/oidc/authorize-url" in login
    assert "SSO 登录" in login
    assert "display: 'standalone'" in manifest
    assert "background_color: '#07111f'" in manifest
    assert '"typecheck"' in package_json
    assert '"smoke"' in package_json
    assert '"e2e:smoke"' in package_json
    assert '"evidence:manifest"' in package_json
    assert "frontend-blueprint" in smoke_script
    assert "evidence_manifest.json" in evidence_script
    assert "PLAYWRIGHT_RECORD_VIDEO" in playwright_config
    assert "PLAYWRIGHT_BROWSER_CHANNEL" in playwright_config
    assert "?? 'msedge'" in playwright_config
    assert "docker compose -f docker-compose.yml up -d --build app" in playwright_config
    assert "APP_HOST_PORT=\\'8000\\'" in playwright_config
    assert "SEC_LOCAL_BOOTSTRAP_SUPERUSER_ENABLED" in playwright_config
    assert "SEC_LOCAL_BOOTSTRAP_SUPERUSER_USERNAME" in playwright_config
    assert "SEC_LOCAL_BOOTSTRAP_SUPERUSER_PASSWORD" in playwright_config
    assert "REPORT_CENTER_STATE_PATH" in playwright_config
    assert "artifacts/report_center/playwright-state.json" in playwright_config
    assert "http://127.0.0.1:8000/health" in playwright_config


def test_playwright_smoke_covers_multi_role_formal_workbenches():
    content = Path("frontend/tests/e2e/blueprint.spec.ts").read_text(encoding="utf-8")
    assert "login page performs real credential flow before entering protected workbench" in content
    assert "selection workbench smoke covers create approve feedback and close-loop actions" in content
    assert "knowledge workbench smoke covers upload query evaluate and rollback" in content
    assert "dashboard page renders profit and close-loop evidence panels" in content
    assert "reports and agent platform pages render formal secured panels" in content
    assert "operations page redirects non-superuser back to home" in content
    assert "operations page renders admin panels for superuser session" in content
    assert "page.getByPlaceholder('用户名')" in content
    assert "page.getByPlaceholder('密码')" in content
    assert "window.localStorage.getItem('pms_workbench_token')" in content
    assert "registerRealUser" in content
    assert "passthroughAuth" in content
    assert "dashboard-profit-smoke.png" in content


def test_reports_page_exposes_summary_cards_for_management_view():
    content = Path("frontend/app/reports/page.tsx").read_text(encoding="utf-8")
    assert "总 GMV" in content
    assert "平均完成率" in content
    assert "数据来源" in content
    assert "report_center_state" in content


def test_new_role_pages_cover_competitor_trend_kpi_and_analyst_views():
    competitors = Path("frontend/app/competitors/page.tsx").read_text(encoding="utf-8")
    trends = Path("frontend/app/trends/page.tsx").read_text(encoding="utf-8")
    kpi = Path("frontend/app/kpi/page.tsx").read_text(encoding="utf-8")
    analyst = Path("frontend/app/analyst/page.tsx").read_text(encoding="utf-8")
    models = Path("frontend/app/models/page.tsx").read_text(encoding="utf-8")
    procurement = Path("frontend/app/procurement/page.tsx").read_text(encoding="utf-8")
    finance = Path("frontend/app/finance/page.tsx").read_text(encoding="utf-8")
    assert "竞品监控配置与预警通知" in competitors
    assert "/competitors/monitor/run" in competitors
    assert "/competitors/analyze" in competitors
    assert "趋势榜单" in trends
    assert "/market/trends/aggregate" in trends
    assert "/market/bsr-demand-ratio" in trends
    assert "/market/forum-topics" in trends
    assert "/market/signals/rss-real" in trends
    assert "RSS 新闻热点" in trends
    assert "管理者 KPI 看板" in kpi
    assert "/bff/workbench/manager/overview" in kpi
    assert "团队绩效排名" in kpi
    assert "审批流待办" in kpi
    assert "审批通过" in kpi
    assert "审批拒绝" in kpi
    assert "准确率趋势" in kpi
    assert "分析师工作台" in analyst
    assert "/selection/accuracy-trend" in analyst
    assert "/knowledge/selection-cases/query" in analyst
    assert "/knowledge/review-cases/query" in analyst
    assert "报告定制" in analyst
    assert "/reports/templates" in analyst
    assert "/reports/generate" in analyst
    assert "生成定制报告" in analyst
    assert "下载定制报告" in analyst
    assert "模型训练 / 调优页面" in models
    assert "/llm/model-registry/default" in models
    assert "/llm/model-registry/default/publish" in models
    assert "/llm/model-registry/default/rollback" in models
    assert "采购工作台" in procurement
    assert "/integration/scm/status" in procurement
    assert "/integration/wms/status" in procurement
    assert "/integration/selection/" in procurement
    assert "财务工作台" in finance
    assert "/integration/fms/status" in finance
    assert "/integration/bi/kpis/daily/latest" in finance
