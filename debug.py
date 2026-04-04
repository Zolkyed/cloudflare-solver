import asyncio
import json

from browser import start_browser


DEBUG_URL = "https://tls.peet.ws/api/all"


async def _fetch_debug_payload():
    browser = await start_browser()

    try:
        page = await browser.get(DEBUG_URL)
        body_text = await page.evaluate("document.body.innerText")
        return json.loads(body_text)
    finally:
        browser.stop()


def fetch_debug_payload():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return asyncio.run(_fetch_debug_payload())
