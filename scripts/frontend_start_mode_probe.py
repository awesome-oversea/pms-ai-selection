from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright

BASE_URL = 'http://localhost:3000'
PAGES = ['/login', '/operations', '/knowledge', '/workbench/selection', '/reports']

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    console_logs = []
    page_errors = []
    page.on('console', lambda msg: console_logs.append({'type': msg.type, 'text': msg.text}))
    page.on('pageerror', lambda exc: page_errors.append(str(exc)))

    for path in PAGES:
        page.goto(f'{BASE_URL}{path}', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(5000)
        print(f'=== {path} ===')
        print('final_url:', page.url)
        print('title:', page.title())
        print('body:', page.locator('body').inner_text(timeout=5000)[:1000])
    print('=== CONSOLE ===')
    for item in console_logs[:50]:
        print(item)
    print('=== PAGE ERRORS ===')
    for item in page_errors[:50]:
        print(item)
    browser.close()
