"""Verify headless chromium actually launches in this container (ASCII only)."""
import asyncio
import sys

sys.path.insert(0, "/app/backend")

from playwright.async_api import async_playwright  # noqa: E402


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<h1>ok</h1>")
        title = await page.evaluate("document.querySelector('h1').textContent")
        await browser.close()
        print("chromium launch OK, evaluate:", title)


asyncio.run(main())
