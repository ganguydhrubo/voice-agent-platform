"""Every page in a real Chromium, at four widths and in both colour modes.

Logs in with the owner in .env, opens each page and fails on a console problem, a page wider than
the screen, or a missing heading. The server must already be running on port 8000.

    python tests/e2e/admin.py
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf8")
BASE = "http://localhost:8000"
SHOTS = ROOT / "docs" / "screenshots"
PUBLIC = ["/", "/faqs", "/privacy", "/login", "/forgot-password", "/nothing-here"]
ADMIN = [
    "/admin",
    "/admin/agents",
    "/admin/knowledge",
    "/admin/conversations",
    "/admin/escalations",
    "/admin/latency",
    "/admin/users",
    "/admin/audit-log",
    "/admin/system",
    "/admin/change-password",
]
WIDTHS = [375, 1366, 1440, 1920]


def env() -> dict:
    lines = (ROOT / ".env").read_text(encoding="utf8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def check(page, path: str, width: int, scheme: str, faults: list) -> None:
    page.goto(BASE + path)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(150)
    if page.locator("h1").count() == 0:
        faults.append(f"{path} {width} {scheme}: no heading")
    wide = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    if wide > 0:
        faults.append(f"{path} {width} {scheme}: {wide}px wider than the screen")
    if width in (375, 1366):
        name = path.strip("/").replace("/", "_") or "home"
        page.screenshot(path=SHOTS / f"page_{name}_{width}_{scheme}.png")


def main() -> int:
    settings = env()
    faults: list[str] = []
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for scheme in ("light", "dark"):
            for width in WIDTHS:
                context = browser.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme)
                page = context.new_page()
                page.on("pageerror", lambda error: faults.append(f"page error: {error}"))
                page.on(
                    "console",
                    lambda message: faults.append(f"console {message.text}")
                    if message.type == "error" and "404" not in message.text
                    else None,
                )
                page.on(
                    "response",
                    lambda response: faults.append(f"{response.status} {response.url}")
                    if response.status >= 400 and response.status != 404
                    else None,
                )
                for path in PUBLIC:
                    check(page, path, width, scheme, faults)
                page.goto(BASE + "/login")
                page.wait_for_load_state("networkidle")
                page.locator("input[type=email], input[name=email]").first.fill(settings["VAP_ADMIN_EMAIL"])
                page.locator("input[type=password]").first.fill(settings["VAP_ADMIN_PASSWORD"])
                page.locator("form").get_by_role("button", name="Log In").click()
                page.locator("h1", has_text="Dashboard").wait_for()
                for path in ADMIN:
                    check(page, path, width, scheme, faults)
                context.close()
                print(scheme, width, "done", flush=True)
                # The page test is quick enough to meet the server's request limit, which is doing its job.
                time.sleep(45)
        browser.close()
    print("faults:", len(faults))
    for fault in dict.fromkeys(faults):
        print("  ", fault[:200])
    return 1 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
