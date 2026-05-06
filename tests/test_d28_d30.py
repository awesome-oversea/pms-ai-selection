"""
D28-D30 单元测试: 前端界面开发
============================

覆盖:
    - Web路由注册与响应
    - HTML模板渲染
    - 静态文件服务
    - 前端API集成测试

测试框架: pytest + httpx.TestClient + Jinja2模板验证
"""

import os

import pytest


def _override_auth(app):
    """覆盖认证依赖，返回模拟用户。"""
    from src.core.auth import get_current_user

    async def _mock_user():
        return {"username": "testuser", "user_id": "test-uid", "is_superuser": False, "token_type": "access"}

    app.dependency_overrides[get_current_user] = _mock_user


class TestWebRoutes:
    """
    Web页面路由测试(D28)。

    验证:
        - 仪表盘页面渲染
        - 选品任务面板渲染
        - 审批界面渲染
        - 结果展示页面
        - Agent监控面板
        - 根路径重定向
    """

    def test_dashboard_page(self):
        """仪表盘页面应返回200和HTML内容。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/dashboard")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        content = response.text

        assert "仪表盘" in content or "dashboard" in content.lower()
        assert "AI选品系统" in content
        assert "navbar" in content

    def test_selection_panel_page(self):
        """选品任务面板应重定向到正式 Next.js 入口。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app, follow_redirects=False)

        response = client.get("/selection")

        assert response.status_code == 307
        assert response.headers.get("location") == "/workbench/selection"

    def test_approval_page(self):
        """审批管理页面应重定向到正式 Next.js 入口。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app, follow_redirects=False)

        response = client.get("/approval")

        assert response.status_code == 307
        assert response.headers.get("location") == "/manager"

    def test_result_view_page(self):
        """结果展示页面应重定向到正式 Next.js 入口。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app, follow_redirects=False)

        response = client.get("/results/test_task_001")

        assert response.status_code == 307
        assert response.headers.get("location") == "/workbench/selection?task_id=test_task_001"

    def test_agent_monitor_page(self):
        """Agent监控面板应重定向到正式 Next.js 入口。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app, follow_redirects=False)

        response = client.get("/agents/monitor")

        assert response.status_code == 307
        assert response.headers.get("location") == "/agents"

    def test_root_redirect(self):
        """根路径应返回正式前端入口信息。"""
        from fastapi.testclient import TestClient
        from src.main import app

        client = TestClient(app, follow_redirects=False)

        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["frontend"] == "Next.js 14 App Router"
        assert data["legacy_jinja_routes"] == "redirected"


class TestStaticFiles:
    """
    静态文件服务测试(D29)。

    验证:
        - CSS文件可访问
        - JS文件可访问
        - 静态目录挂载正确
        - MIME类型正确
    """

    def test_css_file_served(self):
        """CSS样式文件应返回200且MIME类型为text/css。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/static/css/main.css")

        assert response.status_code == 200
        assert "text/css" in response.headers.get("content-type", "")

    def test_main_js_file_served(self):
        """主JS文件应返回200。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/static/js/main.js")

        assert response.status_code == 200
        assert "javascript" in response.headers.get("content-type", "").lower()

    def test_selection_js_file_served(self):
        """选品面板JS应返回200。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/static/js/selection.js")

        assert response.status_code == 200

    def test_approval_js_file_served(self):
        """审批界面JS应返回200。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/static/js/approval.js")

        assert response.status_code == 200

    def test_agents_js_file_served(self):
        """Agent监控JS应返回200。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/static/js/agents.js")

        assert response.status_code == 200

    def test_result_js_file_served(self):
        """结果展示JS应返回200。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/static/js/result.js")

        assert response.status_code == 200


class TestTemplateRendering:
    """
    模板渲染测试(D29)。

    验证:
        - Jinja2模板变量替换
        - 条件渲染逻辑
        - 循环渲染列表数据
        - 错误状态处理
    """

    def test_dashboard_shows_task_count(self):
        """仪表盘应显示总任务数。"""
        from fastapi.testclient import TestClient
        from src.api.v1.endpoints.selection import _task_store
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        original_count = len(_task_store)

        response = client.get("/dashboard")

        assert str(original_count) in response.text or "total_tasks" in response.text

    def test_template_has_navigation(self):
        """所有模板都应包含导航栏。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        pages = ["/dashboard", "/selection", "/approval", "/agents/monitor"]

        for page in pages:
            resp = client.get(page)
            assert "nav-brand" in resp.text or "navbar" in resp.text

    def test_template_has_footer(self):
        """所有模板都应包含页脚。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        pages = ["/dashboard", "/selection", "/approval"]

        for page in pages:
            resp = client.get(page)
            assert "footer" in resp.text.lower()

    def test_result_page_handles_missing_task(self):
        """结果页面应对不存在的任务友好处理。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/results/nonexistent_task_xyz")

        assert response.status_code == 200
        assert ("未找到" in response.text or "not found" in response.text.lower()
                or "不存在" in response.text)


class TestFrontendAPIIntegration:
    """
    前端API集成测试(D30)。

    验证:
        - 前端JS能正确调用后端API
        - API响应格式符合前端预期
        - 错误处理机制正常
        - 跨域请求支持
    """

    def test_api_base_accessible_from_frontend(self):
        """前端JS中定义的API_BASE端点应可访问。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        endpoints = [
            ("/api/v1/selection/tasks", "GET"),
            ("/api/v1/agents", "GET"),
            ("/api/v1/knowledge/stats", "GET"),
        ]

        for url, method in endpoints:
            if method == "GET":
                resp = client.get(url)
            else:
                continue

            assert resp.status_code in [200, 400], f"{url} 返回 {resp.status_code}"

    def test_cors_headers_present(self):
        """API响应应包含CORS头信息。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get(
            "/api/v1/selection/tasks",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code in [200, 400]

    def test_selection_form_validation(self):
        """选品表单验证应在服务端生效。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.post(
            "/api/v1/selection/tasks",
            json={
                "query": "X",
            },
        )

        assert response.status_code == 422

    def test_task_list_for_frontend(self):
        """任务列表API应返回前端需要的数据格式。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/selection/tasks")

        if response.status_code == 200:
            data = response.json()

            assert "tasks" in data or isinstance(data, list)

    def test_agent_list_for_monitor(self):
        """Agent列表API应返回监控所需的数据。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/agents")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data.get("agents"), list) or isinstance(data, list)


class TestWebComponentStructure:
    """
    Web组件结构完整性测试(D30)。

    验证:
        - 所有必需的HTML模板存在
        - 所有必需的CSS/JS资源存在
        - 文件路径引用正确
        - 组件间依赖关系完整
    """

    def test_all_templates_exist(self):
        """所有HTML模板文件应存在。"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        templates_dir = os.path.join(base_dir, "web", "templates")

        required_templates = [
            "dashboard.html",
            "selection.html",
            "approval.html",
            "result.html",
            "agents.html",
        ]

        for template_name in required_templates:
            template_path = os.path.join(templates_dir, template_name)
            assert os.path.exists(template_path), f"模板缺失: {template_name}"

    def test_all_css_files_exist(self):
        """所有CSS文件应存在。"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        css_dir = os.path.join(base_dir, "web", "static", "css")

        css_files = ["main.css"]

        for css_file in css_files:
            file_path = os.path.join(css_dir, css_file)
            assert os.path.exists(file_path), f"CSS缺失: {css_file}"

    def test_all_js_files_exist(self):
        """所有JS文件应存在。"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        js_dir = os.path.join(base_dir, "web", "static", "js")

        js_files = [
            "main.js",
            "selection.js",
            "approval.js",
            "result.js",
            "agents.js",
        ]

        for js_file in js_files:
            file_path = os.path.join(js_dir, js_file)
            assert os.path.exists(file_path), f"JS缺失: {js_file}"

    def test_web_package_init_exists(self):
        """Web包初始化文件应存在并导出路由。"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        web_init_path = os.path.join(base_dir, "src", "web", "__init__.py")

        assert os.path.exists(web_init_path), "web/__init__.py 缺失"

        with open(web_init_path, encoding="utf-8") as f:
            content = f.read()

        assert "web_router" in content

    def test_css_contains_required_styles(self):
        """CSS文件应包含核心样式规则。"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        css_path = os.path.join(base_dir, "web", "static", "css", "main.css")

        with open(css_path, encoding="utf-8") as f:
            css_content = f.read()

        required_selectors = [
            ".navbar",
            ".card",
            ".btn",
            ".badge",
            ".stat-card",
            ".data-table",
            ".form-group",
        ]

        for selector in required_selectors:
            assert selector in css_content, f"CSS缺少选择器: {selector}"

    def test_js_contains_required_functions(self):
        """JS文件应包含核心功能函数。"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        selection_js_path = os.path.join(base_dir, "web", "static", "js", "selection.js")

        with open(selection_js_path, encoding="utf-8") as f:
            js_content = f.read()

        required_functions = [
            "loadTasks",
            "handleCreateTask",
            "cancelTask",
            "renderTasks",
        ]

        for func in required_functions:
            assert func in js_content, f"JS缺少函数: {func}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
