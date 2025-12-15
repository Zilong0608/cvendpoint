from typing import Optional


def html_to_pdf_bytes(html: str) -> bytes:
    """Render HTML to PDF using Playwright (Chromium headless).

    Requires:
      pip install playwright
      python -m playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        raise RuntimeError("Playwright not installed. Please `pip install playwright` and `python -m playwright install chromium`.") from e

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_content(html or "", wait_until="load")
        # A4, print background to keep styles
        pdf_bytes = page.pdf(format="A4", print_background=True)
        context.close()
        browser.close()
        return pdf_bytes
