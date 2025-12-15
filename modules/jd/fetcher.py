import httpx
import platform
from urllib.parse import urlparse
from .schemas import ParsedJD
from .parser import parse_html_to_jd


DEFAULT_TIMEOUT = 10.0
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-AU,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
    "Referer": "https://www.seek.com.au/",
}


def fetch_and_parse(url: str, render: bool = False):
    debug = {
        "requested_url": url,
        "status_code": None,
        "final_url": None,
        "domain": urlparse(url).netloc,
        "content_length": 0,
        "notes": [],
    }
    try:
        with httpx.Client(follow_redirects=True, timeout=DEFAULT_TIMEOUT, headers=HEADERS) as client:
            # Warm-up to obtain cookies/session for the domain
            base = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
            try:
                client.get(base)
                debug["notes"].append("warmed_cookies")
            except Exception:
                pass
            resp = client.get(url)
            debug["status_code"] = resp.status_code
            debug["final_url"] = str(resp.request.url)
            if resp.status_code >= 400:
                debug["notes"].append(f"http_error_{resp.status_code}")
                html = None
                # Try rendering when caller requests it or when forbidden (common on Seek/LinkedIn)
                if render or resp.status_code == 403:
                    html = _render_page_html(url, debug)
                if html:
                    debug["notes"].append("render_ok")
                    jd = parse_html_to_jd(html, url)
                    debug["content_length"] = len(html)
                    return jd, debug
                else:
                    if render or resp.status_code == 403:
                        debug["notes"].append("render_failed")
                    return ParsedJD(), debug
            html = resp.text
            debug["content_length"] = len(html)
            jd = parse_html_to_jd(html, url)
            # Heuristic note for likely blocked content
            if not any([jd.title, jd.company, jd.responsibilities, jd.requirements]) and debug["domain"].endswith("linkedin.com"):
                debug["notes"].append("linkedin_login_or_scripted_page")
            return jd, debug
    except Exception as e:
        debug["notes"].append(f"exception:{type(e).__name__}")
        return ParsedJD(), debug


def _render_page_html(url: str, debug: dict) -> str | None:
    """Optional headless rendering via Playwright. Returns HTML or None if unavailable."""
    try:
        import asyncio
        if platform.system().lower().startswith("win"):
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
                debug["notes"].append("windows_proactor_event_loop")
            except Exception:
                pass
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        debug["notes"].append("playwright_not_installed")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS.get("User-Agent"),
                locale="en-AU",
                java_script_enabled=True,
            )
            page = context.new_page()
            page.set_default_timeout(int(DEFAULT_TIMEOUT * 1000))
            page.goto(url, wait_until="domcontentloaded")
            # Try to wait for main content; fallback to timeout
            try:
                page.wait_for_load_state("networkidle", timeout=int(DEFAULT_TIMEOUT * 1000))
            except Exception:
                pass
            html = page.content()
            context.close()
            browser.close()
            return html
    except Exception as e:
        debug["notes"].append(f"playwright_error:{type(e).__name__}")
        return None
