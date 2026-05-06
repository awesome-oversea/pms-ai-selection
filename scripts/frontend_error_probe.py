from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from src.core.auth import create_access_token

BASE_URL = 'http://127.0.0.1:3000'
PAGES = ['/knowledge', '/workbench/selection', '/reports']

def _build_token() -> str:
    return create_access_token({
        'sub': 'frontend-user',
        'user_id': '00000000-0000-0000-0000-000000000002',
        'is_superuser': False,
        'tenant_id': '86d1f796-7c55-57a1-ac77-2e952a2111ca',
        'tenant_key': 'default',
        'tenant_name': 'Default Tenant',
        'roles': ['operator'],
    })

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for path in PAGES:
        context = browser.new_context(viewport={'width': 1440, 'height': 1200})
        page = context.new_page()
        console_logs = []
        page_errors = []
        responses = []
        page.on('console', lambda msg: console_logs.append({'type': msg.type, 'text': msg.text}))
        page.on('pageerror', lambda exc: page_errors.append(str(exc)))
        page.on('response', lambda response: responses.append({'url': response.url, 'status': response.status}) if '/api/v1/' in response.url else None)
        token = _build_token()
        context.add_cookies([{'name': 'pms_workbench_token', 'value': token, 'url': BASE_URL, 'httpOnly': False, 'secure': False, 'sameSite': 'Lax'}])
        page.goto(f'{BASE_URL}/login', wait_until='domcontentloaded', timeout=60000)
        page.evaluate("(token) => window.localStorage.setItem('pms_workbench_token', token)", token)
        page.goto(f'{BASE_URL}{path}', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(10000)
        print(f'===PAGE {path}===')
        print(page.locator('body').inner_text(timeout=5000)[:1000])
        print('---RESPONSES---')
        for item in responses:
            print(item)
        print('---CONSOLE---')
        for item in console_logs:
            print(item)
        print('---PAGEERRORS---')
        for item in page_errors:
            print(item)
        context.close()
    browser.close()
