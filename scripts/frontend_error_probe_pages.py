from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from src.core.auth import create_access_token

BASE_URL = 'http://localhost:3000'
PAGES = [
    ('knowledge', '/knowledge'),
    ('selection', '/workbench/selection'),
]

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
    for key, path in PAGES:
        context = browser.new_context(
            viewport={'width': 1440, 'height': 1200},
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
        page.on('response', lambda response: responses.append({'url': response.url, 'status': response.status}) if '/api/v1/' in response.url else None)
        page.on('console', lambda msg: console_logs.append({'type': msg.type, 'text': msg.text}))
        page.on('pageerror', lambda exc: page_errors.append(str(exc)))
        page.goto(f'{BASE_URL}{path}', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(15000)
        body = page.locator('body').inner_text(timeout=5000)
        print(f'=== {key} ===')
        print('url=', page.url)
        print('body=', body[:1200])
        print('responses=', responses[:20])
        print('console=', console_logs[:20])
        print('page_errors=', page_errors[:20])
        context.close()
    browser.close()
