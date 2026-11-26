#!/usr/bin/env python3
"""Capture the 3 dashboard screenshots (Day 3, step 3).

Serves dashboard/ on localhost, opens it in headless Chromium via the
Playwright install in the airdrop-agent venv, and writes:
  screenshots/1-board.png     -- the board table, top of the ranking
  screenshots/2-detail.png    -- Steakhouse (rank 1) detail view
  screenshots/3-filtered.png  -- category filter on Risk Curators

Usage: ~/workspace/airdrop-agent/.venv/bin/python scripts/shoot_dashboard.py
Screenshots are real captures of the dashboard running, not composed
images. Viewport 1280x860; full-page for the board shot so the ranking
is visible.
"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SHOTS = HERE / "screenshots"
PORT = 8931


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
        cwd=HERE / "dashboard",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{PORT}"
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=2)
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("dashboard server did not come up")

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            # 1. board
            page.goto(base + "/index.html", wait_until="networkidle")
            page.wait_for_selector("#rows tr")
            page.screenshot(path=str(SHOTS / "1-board.png"))
            # 2. detail (Steakhouse, rank 1)
            page.goto(base + "/index.html?detail=steakhouse-financial",
                      wait_until="networkidle")
            page.wait_for_selector("#detail h2")
            page.screenshot(path=str(SHOTS / "2-detail.png"))
            # 3. filtered view (category filter visibly applied)
            page.goto(base + "/index.html?category=Risk%20Curators",
                      wait_until="networkidle")
            page.wait_for_selector("#rows tr")
            page.screenshot(path=str(SHOTS / "3-filtered.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait()

    for f in sorted(SHOTS.glob("*.png")):
        print(f"{f.name}: {f.stat().st_size} bytes")


if __name__ == "__main__":
    main()
