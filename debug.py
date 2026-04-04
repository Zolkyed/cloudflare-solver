import asyncio
import json

from browser import start_browser


DEBUG_URL = "https://tls.peet.ws/api/all"


async def _fetch_debug_payload() -> dict:
    browser = await start_browser()

    try:
        page = await browser.get(DEBUG_URL)
        await asyncio.sleep(0.5)

        raw_json = await page.evaluate("""
            (() => {
                const pre = document.querySelector("pre");
                return (pre ? pre.textContent : document.body.textContent).trim();
            })()
        """)

        if not isinstance(raw_json, str):
            raise RuntimeError(
                f"Browser returned unexpected payload type: "
                f"{type(raw_json).__name__} -> {raw_json!r}"
            )
    finally:
        return json.loads(raw_json)


def fetch_debug_payload() -> dict:
    return asyncio.run(_fetch_debug_payload())


if __name__ == "__main__":
    payload = fetch_debug_payload()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
