"""The acceptance journey in a real Chromium, with a fake microphone playing the caller's audio.

Open the site, choose Healthcare and a language, start, speak, read the transcript, follow up,
interrupt, follow up again and end. The server must already be running on port 8000.

    python tests/e2e/journey.py en hi bn
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf8")
BASE = "http://localhost:8000"
SHOTS = ROOT / "docs" / "screenshots"
LANGUAGE_LABEL = {"en": "English", "hi": "Hindi", "bn": "Bengali"}
SECONDS = {"en": 54, "hi": 62, "bn": 70}


def run(language: str) -> dict:
    wav = ROOT / "benchmarks" / "data" / "journey" / f"caller_{language}.wav"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={wav}%noloop",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )
        context = browser.new_context(viewport={"width": 1366, "height": 800})
        context.grant_permissions(["microphone"], origin=BASE)
        page = context.new_page()
        problems = []
        page.on("pageerror", lambda error: problems.append(f"page error: {error}"))
        page.on("console", lambda message: problems.append(f"console: {message.text}") if message.type == "error" else None)

        page.goto(BASE)
        page.get_by_role("button", name="Healthcare").first.click()
        page.get_by_label("Language").select_option(label=LANGUAGE_LABEL[language])
        page.get_by_role("button", name="Start Conversation").click()
        page.wait_for_url("**/talk/**")
        started = time.time()
        states = []
        last = ""
        shot = False
        while time.time() - started < SECONDS[language]:
            state = page.get_by_test_id("state").inner_text()
            if state != last:
                states.append((round(time.time() - started, 1), state))
                last = state
            if not shot and page.locator(".bubble[data-role=user]").count() >= 2 and state == "Speaking":
                page.screenshot(path=SHOTS / f"journey_{language}.png")
                shot = True
            page.wait_for_timeout(120)
        bubbles = page.eval_on_selector_all(
            ".bubble", "items => items.map(item => ({role: item.dataset.role, text: item.innerText}))"
        )
        page.screenshot(path=SHOTS / f"journey_{language}_end.png")
        page.get_by_role("button", name="End Conversation").click()
        page.get_by_text("Conversation ended").wait_for(timeout=5000)
        browser.close()
    return {"language": language, "states": states, "bubbles": bubbles, "problems": problems}


def main() -> None:
    results = []
    for language in sys.argv[1:] or ["en", "hi", "bn"]:
        result = run(language)
        results.append(result)
        print(f"\n=== {language}")
        print(" states:", result["states"])
        for bubble in result["bubbles"]:
            print(f"  {bubble['role']:6} {bubble['text']}".replace("\n", " | "))
        print(" problems:", result["problems"])
    (ROOT / "benchmarks" / "results" / "journey.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
