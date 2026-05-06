from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from src.core.auth import create_access_token

BASE_URL = 'http://localhost:3000'
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
    token = _build_token()
    for path in PAGES:
        context = browser.new_context(
            viewport={'width': 1280, 'height': 900},
            storage_state={
                'cookies': [{
                    'name': 'pms_workbench_token',
                    'value': token,
                    'domain': 'localhost',
                    'path': '/',
                    'httpOnly': False,
                    'secure': False,
                    'sameSite': 'Lax',
                }],
                'origins': [{
                    'origin': BASE_URL,
                    'localStorage': [{'name': 'pms_workbench_token', 'value': token}],
                }],
            },
        )
        page = context.new_page()
        responses = []
        console_logs = []
        page_errors = []
        page.on('response', lambda response: responses.append({'status': response.status, 'url': response.url}) if ('/_next/' in response.url or '/api/v1/' in response.url) else None)
        page.on('console', lambda msg: console_logs.append({'type': msg.type, 'text': msg.text}))
        page.on('pageerror', lambda exc: page_errors.append(str(exc)))
        page.goto(f'{BASE_URL}{path}', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(15000)
        print(f'=== {path} ===')
        print('body:', page.locator('body').inner_text(timeout=5000)[:1200])
        print('responses:')
        for item in responses[:40]:
            print(item)
        print('console:')
        for item in console_logs[:20]:
            print(item)
        print('page_errors:')
        for item in page_errors[:20]:
            print(item)
        context.close()
    browser.close()
