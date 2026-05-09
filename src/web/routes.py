"""
Web前端页面路由
================

提供选品系统的 Web 界面。
当前阶段通过服务层读取任务数据，避免直接依赖 endpoint 内部状态。
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.infrastructure.database import get_async_session_factory
from src.services.selection_service import SelectionTaskService

router = APIRouter(tags=["Web界面"])

BASE_DIR = Path(__file__).resolve().parents[2]
templates_dir = BASE_DIR / "web" / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render(name: str, **kw) -> HTMLResponse:
    tpl = _jinja_env.get_template(name)
    return HTMLResponse(tpl.render(**kw))


async def _get_selection_service() -> SelectionTaskService:
    session = get_async_session_factory()()
    return SelectionTaskService(session)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """仪表盘首页。"""
    service = await _get_selection_service()
    try:
        task_result = await service.list_tasks(status=None, limit=5, offset=0)
        recent_tasks = task_result["tasks"]
        total_tasks = task_result["total"]
    except Exception:
        recent_tasks = []
        total_tasks = 0
    finally:
        await service.session.close()

    return _render(
        "dashboard.html",
        request=request,
        page_title="AI选品系统 - 仪表盘",
        recent_tasks=recent_tasks,
        total_tasks=total_tasks,
    )


@router.get("/selection", response_class=HTMLResponse)
async def selection_panel(request: Request):
    """选品任务面板已切换到 Next.js 正式入口。"""
    return RedirectResponse(url="/workbench/selection", status_code=307)


@router.get("/workbench/selection", response_class=HTMLResponse)
async def selection_workbench(request: Request):
    """正式工作台入口：当前以 Next.js 工作台为主，Jinja 页面仅保留 legacy 兼容提示。"""
    return _render(
        "workbench_selection.html",
        request=request,
        page_title="正式选品工作台",
    )


@router.get("/approval", response_class=HTMLResponse)
async def approval_panel(request: Request):
    """审批管理界面已切换到 Next.js 正式入口。"""
    return RedirectResponse(url="/manager", status_code=307)


@router.get("/results/{task_id}", response_class=HTMLResponse)
async def result_view(request: Request, task_id: str):
    """选品结果展示已切换到 Next.js 正式入口。"""
    return RedirectResponse(url=f"/workbench/selection?task_id={task_id}", status_code=307)


@router.get("/agents/monitor", response_class=HTMLResponse)
async def agent_monitor(request: Request):
    """Agent监控面板已切换到 Next.js 正式入口。"""
    return RedirectResponse(url="/agents", status_code=307)


@router.get("/recommendations", response_class=HTMLResponse)
async def recommendations_page(request: Request):
    """建议池管理页面。"""
    return _render(
        "recommendations.html",
        request=request,
        page_title="AI选品系统 - 建议池管理",
    )


@router.get("/ads-optimization", response_class=HTMLResponse)
async def ads_optimization_page(request: Request):
    """广告优化页面。"""
    return _render(
        "ads_optimization.html",
        request=request,
        page_title="AI选品系统 - 广告优化",
    )


@router.get("/fba-restock", response_class=HTMLResponse)
async def fba_restock_page(request: Request):
    """FBA补货建议页面。"""
    return _render(
        "fba_restock.html",
        request=request,
        page_title="AI选品系统 - FBA补货",
    )


@router.get("/ai-insights", response_class=HTMLResponse)
async def ai_insights_page(request: Request):
    """AI洞察中心页面。"""
    return _render(
        "ai_insights.html",
        request=request,
        page_title="AI选品系统 - AI洞察",
    )
