import asyncio
import json
import random
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse
from browser import ensure_display, start_browser


@dataclass
class SolveResult:
    token: Optional[str]
    cookies: list[dict[str, str]]


def _cookie_matches_site(cookie, siteurl: str) -> bool:
    parsed = urlparse(siteurl)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False

    cookie_domain = (getattr(cookie, "domain", "") or "").lower().lstrip(".")
    if not cookie_domain:
        return False

    return hostname == cookie_domain or hostname.endswith("." + cookie_domain)


def _serialize_cookies(raw_cookies, siteurl: str) -> list[dict[str, str]]:
    cookies = []

    for cookie in raw_cookies:
        if _cookie_matches_site(cookie, siteurl):
            cookies.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                }
            )

    return cookies

async def _solve(sitekey: Optional[str], siteurl: str, timeout: int) -> SolveResult:
    browser = await start_browser()
    token: Optional[str] = None
    raw_cookies = []

    try:
        page = await browser.get(siteurl)
        if not sitekey:
            raw_cookies = await browser.cookies.get_all()
            return SolveResult(
                token=None, cookies=_serialize_cookies(raw_cookies, siteurl)
            )

        await asyncio.sleep(random.uniform(2.0, 3.0))

        # Inject widget into the live page DOM
        await page.evaluate(f"""
            (() => {{
                if (document.getElementById('_ts_box')) return;
                window._tsToken = null;
                const wrap = document.createElement('div');
                wrap.id = '_ts_box';
                wrap.style = 'position:fixed;top:20px;left:20px;z-index:2147483647;';
                document.body.appendChild(wrap);
                window._tsLoad = function () {{
                    turnstile.render('#_ts_box', {{
                        sitekey: '{sitekey}',
                        callback: function(token) {{ window._tsToken = token; }}
                    }});
                }};
                const s = document.createElement('script');
                s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=_tsLoad&render=explicit';
                s.async = true;
                document.head.appendChild(s);
            }})();
        """)

        # Give Turnstile time to load and potentially auto-complete (invisible mode)
        await asyncio.sleep(5.0)

        async def get_token() -> Optional[str]:
            return await page.evaluate("""
                (() => {
                    if (window._tsToken) return window._tsToken;
                    const inp = document.querySelector('#_ts_box [name="cf-turnstile-response"]');
                    return (inp && inp.value) ? inp.value : null;
                })()
            """)

        async def get_cf_iframe_rect() -> Optional[dict]:
            raw = await page.evaluate("""
                JSON.stringify((() => {
                    for (const f of document.querySelectorAll('iframe')) {
                        const src = f.src || f.getAttribute('src') || '';
                        if (!src.includes('challenges.cloudflare.com')) continue;
                        const r = f.getBoundingClientRect();
                        if (r.width > 50 && r.height > 20) return {x:r.x, y:r.y, w:r.width, h:r.height};
                    }
                    return null;
                })())
            """)
            if raw and raw != "null":
                return json.loads(raw)
            return None

        async def do_click(rect: Optional[dict]):
            if rect:
                cx = rect["x"] + 28 + random.uniform(-3, 3)
                cy = rect["y"] + rect["h"] / 2 + random.uniform(-3, 3)
                print(f"[solver] clicking Cloudflare iframe at ({cx:.0f}, {cy:.0f})")
            else:
                # Widget is fixed at top:20px left:20px
                cx = 20 + 28 + random.uniform(-3, 3)
                cy = 20 + 32 + random.uniform(-3, 3)
                print(
                    f"[solver] iframe not in DOM, clicking fixed position ({cx:.0f}, {cy:.0f})"
                )
            await page.mouse_move(cx - 80, cy - 20)
            await asyncio.sleep(random.uniform(0.15, 0.25))
            await page.mouse_move(cx, cy)
            await asyncio.sleep(random.uniform(0.08, 0.15))
            await page.mouse_click(cx, cy)

        # Check if already auto-solved (invisible widget)
        token = await get_token()
        if token:
            raw_cookies = await browser.cookies.get_all()
            return SolveResult(
                token=token, cookies=_serialize_cookies(raw_cookies, siteurl)
            )

        # Wait up to 10s for the visible checkbox iframe to appear
        rect = None
        for _ in range(20):
            rect = await get_cf_iframe_rect()
            if rect:
                break
            await asyncio.sleep(0.5)

        # Click loop: click, wait, retry up to 3 times
        deadline = asyncio.get_event_loop().time() + timeout
        click_count = 0
        last_click = 0.0

        while asyncio.get_event_loop().time() < deadline:
            token = await get_token()
            if token:
                break

            now = asyncio.get_event_loop().time()
            if click_count == 0 or (not token and now - last_click > 8):
                if click_count >= 3:
                    await asyncio.sleep(0.3)
                    continue
                await do_click(rect)
                last_click = asyncio.get_event_loop().time()
                click_count += 1
                # After a click, refresh iframe rect in case it moved
                await asyncio.sleep(1.0)
                rect = await get_cf_iframe_rect() or rect
                continue

            await asyncio.sleep(0.3)

        raw_cookies = await browser.cookies.get_all()
    finally:
        browser.stop()

    if not token:
        raise TimeoutError(f"Turnstile token not obtained within {timeout}s")

    return SolveResult(token=token, cookies=_serialize_cookies(raw_cookies, siteurl))


def solve(siteurl: str, sitekey: Optional[str] = None, timeout: int = 45) -> SolveResult:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return asyncio.run(_solve(sitekey, siteurl, timeout))


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print(
            json.dumps(
                {"error": "Usage: python solver.py <siteurl> [sitekey]"}
            )
        )
        sys.exit(1)

    xvfb = ensure_display()
    try:
        siteurl = sys.argv[1]
        sitekey = sys.argv[2] if len(sys.argv) > 2 else None
        result = solve(siteurl, sitekey=sitekey)

        print(json.dumps({"token": result.token, "cookies": result.cookies}))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)

    finally:
        if xvfb:
            xvfb.terminate()
