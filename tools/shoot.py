"""Screenshot helper (installed Edge by default):  python tools/shoot.py URL OUT.png [WIDTH HEIGHT]
Set BAZAAR_BROWSER=chrome for Google Chrome, or BAZAAR_BROWSER= (empty) for Playwright's own Chromium (playwright install chromium)."""
import os
import sys

from playwright.sync_api import sync_playwright


def main() -> None:
    url, out = sys.argv[1], sys.argv[2]
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 720
    wait = int(sys.argv[5]) if len(sys.argv) > 5 else 900
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("BAZAAR_BROWSER", "msedge") or None)
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto(url)
        pg.wait_for_timeout(wait)
        pg.screenshot(path=out)
        b.close()


if __name__ == "__main__":
    main()
