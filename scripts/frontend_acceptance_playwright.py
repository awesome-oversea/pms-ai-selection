from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path("artifacts/frontend_acceptance")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:3000"
PAGES = [
    ("operations", "/operations", "运营台"),
    ("knowledge", "/knowledge", "知识库工作台"),
    ("selection", "/workbench/selection", "选品工作台"),
    ("reports", "/reports", "报告中心"),
]

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1200})

    for key, path, title in PAGES:
        url = f"{BASE_URL}{path}"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        screenshot_path = OUTPUT_DIR / f"{key}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        body_text = page.locator("body").inner_text(timeout=5000)
        results.append(
            {
                "page": key,
                "url": url,
                "title": title,
                "screenshot": str(screenshot_path).replace('\\', '/'),
                "has_expected_title": title in body_text,
                "body_excerpt": body_text[:400],
            }
        )

    browser.close()

import json
summary_path = OUTPUT_DIR / "summary.json"
summary = {
    "accepted": all(item["has_expected_title"] for item in results),
    "pages": results,
}
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
