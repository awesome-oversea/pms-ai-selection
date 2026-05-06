from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from src.core.auth import create_access_token

BASE_URL = 'http://localhost:3000'
TARGETS = ['/operations', '/knowledge', '/workbench/selection', '/reports']

def _build_token() -> str:
    return create_access_token({
        'sub': 'frontend-admin',
        'user_id': '00000000-0000-0000-0000-000000000001',
        'is_superuser': True,
        'tenant_id': '86d1f796-7c55-57a1-ac77-2e952a2111ca',
        'tenant_key': 'default',
        'tenant_name': 'Default Tenant',
        'roles': ['tenant_admin', 'platform_admin'],
    })

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    token = _build_token()
    for target in TARGETS:
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = context.new_page()
        responses = []
        page.on('response', lambda response: responses.append((response.status, response.url)))
        context.add_cookies([{
            'name': 'pms_workbench_token',
            'value': token,
            'domain': 'localhost',
            'path': '/',
            'httpOnly': False,
            'secure': False,
            'sameSite': 'Lax',
        }])
        page.goto(f'{BASE_URL}{target}', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(5000)
        print(f'=== {target} ===')
        print('final_url:', page.url)
        print('title:', page.title())
        print('body:', page.locator('body').inner_text(timeout=5000)[:600])
        print('responses:', responses[:12])
        context.close()
    browser.close()
