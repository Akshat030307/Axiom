"""HTML -> PDF via Playwright/Chromium (PRD §14) — chosen over WeasyPrint
because CSS table/print support is complete and this is the same engine
that will need to render Mermaid SVGs once diagrams exist. Chromium is
installed at image build time (see Dockerfile); never at runtime.
"""

from pathlib import Path

from playwright.async_api import async_playwright

# No page.title() default header wanted — Playwright's built-in default
# header (date + title + URL) is suppressed by supplying an explicit,
# effectively-empty header_template; only the footer carries content.
_HEADER_TEMPLATE = "<span></span>"
_FOOTER_TEMPLATE = """
<div style="font-size:8px; width:100%; text-align:center; color:#999; font-family:sans-serif;">
  Page <span class="pageNumber"></span> of <span class="totalPages"></span>
</div>
"""


async def render_pdf(html: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            await page.pdf(
                path=str(output_path),
                format="A4",
                print_background=True,
                margin={"top": "20mm", "bottom": "20mm", "left": "18mm", "right": "18mm"},
                display_header_footer=True,
                header_template=_HEADER_TEMPLATE,
                footer_template=_FOOTER_TEMPLATE,
            )
        finally:
            await browser.close()
