from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright

from src.core.auth import create_access_token

OUTPUT_DIR = Path("artifacts/frontend_acceptance_authenticated")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:3000"
PAGES = [
    ("operations", "/operations", "运营台", True, lambda body, hits: ('治理执行摘要' in body) and any('/api/v1/auth/me' in item['url'] for item in hits)),
    ("knowledge", "/knowledge", "知识库工作台", False, lambda body, hits: ('质量与检索状态' in body) and any('/api/v1/auth/me' in item['url'] for item in hits) and any('/api/v1/knowledge/documents' in item['url'] for item in hits)),
    ("selection", "/workbench/selection", "选品工作台", False, lambda body, hits: ('正式选品工作台' in body or 'ECharts趋势图 / 准确率趋势' in body) and any('/api/v1/auth/me' in item['url'] for item in hits) and any('/api/v1/bff/workbench/selection/summary' in item['url'] for item in hits)),
    ("reports", "/reports", "报告中心", False, lambda body, hits: ('报告中心' in body) and any('/api/v1/auth/me' in item['url'] for item in hits) and any('/api/v1/reports' in item['url'] for item in hits)),
]

def _build_token(*, is_superuser: bool) -> str:
    return create_access_token(
        {
            "sub": "frontend-admin" if is_superuser else "frontend-user",
            "user_id": "00000000-0000-0000-0000-000000000001" if is_superuser else "00000000-0000-0000-0000-000000000002",
            "is_superuser": is_superuser,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": ["tenant_admin", "platform_admin"] if is_superuser else ["operator"],
        }
    )


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    results = []
    for key, path, title, require_superuser, validator in PAGES:
        token = _build_token(is_superuser=require_superuser)
        last_result = None
        for attempt in range(1, 4):
            context = browser.new_context(
                viewport={"width": 1440, "height": 1200},
                storage_state={
                    "cookies": [
                        {
                            "name": "pms_workbench_token",
                            "value": token,
                            "domain": "127.0.0.1",
                            "path": "/",
                            "httpOnly": False,
                            "secure": False,
                            "sameSite": "Lax",
                        }
                    ],
                    "origins": [
                        {
                            "origin": BASE_URL,
                            "localStorage": [
                                {"name": "pms_workbench_token", "value": token}
                            ],
                        }
                    ],
                },
            )
            page = context.new_page()
            api_hits = []
            page.on('response', lambda response: api_hits.append({'url': response.url, 'status': response.status}) if '/api/v1/' in response.url else None)
            url = f"{BASE_URL}{path}"
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)

            body_text = page.locator("body").inner_text(timeout=5000)
            if '正在校验登录态' in body_text:
                page.wait_for_timeout(10000)
                body_text = page.locator("body").inner_text(timeout=5000)

            screenshot_path = OUTPUT_DIR / f"{key}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            auth_me_hits = [item for item in api_hits if '/api/v1/auth/me' in item['url']]
            has_loading = '正在校验登录态' in body_text
            has_auth_error = '工作台鉴权失败' in body_text
            accepted = bool(validator(body_text, api_hits)) and not has_loading and not has_auth_error
            last_result = {
                "page": key,
                "url": url,
                "title": title,
                "attempt": attempt,
                "screenshot": str(screenshot_path).replace('\\', '/'),
                "has_expected_title": title in body_text,
                "auth_me_hit_count": len(auth_me_hits),
                "has_loading": has_loading,
                "has_auth_error": has_auth_error,
                "accepted": accepted,
                "body_excerpt": body_text[:500],
                "api_hits": api_hits[:20],
            }
            context.close()
            if accepted:
                break
        results.append(last_result)

    browser.close()

import json
summary_path = OUTPUT_DIR / "summary.json"
summary = {
    "accepted": all(item["accepted"] for item in results),
    "pages": results,
}
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
