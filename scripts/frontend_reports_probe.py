from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from src.core.auth import create_access_token

BASE_URL = 'http://localhost:3000'
PATHNAME = '/reports'

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
    for i in range(3):
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
        page.on('response', lambda response: responses.append({'url': response.url, 'status': response.status}) if '/api/v1/' in response.url else None)
        page.goto(f'{BASE_URL}{PATHNAME}', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(30000)
        body = page.locator('body').inner_text(timeout=5000)
        print(f'=== attempt {i+1} ===')
        print(body[:1500])
        print(responses[:20])
        context.close()
    browser.close()
