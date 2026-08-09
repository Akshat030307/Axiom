"""Report markdown -> print-ready HTML (PRD §14). `figure://{id}` markers
are rewritten to base64 data URIs of the stored chart PNG, so the PDF
needs no network access and no auth to render — exactly PRD §14's spec.
"""

import base64
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import bleach
from markdown_it import MarkdownIt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Evidence, Figure, ResearchRun, Source

logger = logging.getLogger(__name__)

# html=True is required for the citation-marker superscripts below to
# survive parsing — markdown-it otherwise escapes inline HTML.
_MD = MarkdownIt("commonmark", {"html": True}).enable("table")

# One or more back-to-back markers, e.g. "[2][3]" — wrapped as a single
# <sup> per PRD §14 ("citation markers rendered as superscripts").
_CITATION_MARKERS_RE = re.compile(r"((?:\[\d+\])+)")
_FIGURE_MD_RE = re.compile(r"!\[([^\]]*)\]\(figure://([^)]*)\)")

_ALLOWED_TAGS = [
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
    "strong", "em", "sup", "sub", "a", "blockquote", "hr", "br",
    "code", "pre", "table", "thead", "tbody", "tr", "th", "td",
    "div", "span", "figure", "figcaption", "img",
]
_ALLOWED_ATTRS = {
    "a": ["href"],
    "div": ["class"],
    "span": ["class"],
    "img": ["src", "alt"],
}

_PAGE_CSS = """
  body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
         color: #1a1a1a; font-size: 11pt; line-height: 1.55; }
  h1.report-title { font-size: 20pt; margin: 0 0 4pt; }
  p.report-meta { color: #666; font-size: 9pt; margin: 0 0 24pt; text-transform: capitalize; }
  h1, h2, h3 { color: #111; line-height: 1.3; page-break-after: avoid; }
  h2 { font-size: 14pt; margin-top: 22pt; border-bottom: 1px solid #ddd; padding-bottom: 4pt; }
  h3 { font-size: 12pt; margin-top: 16pt; }
  p { margin: 0 0 10pt; }
  ul, ol { margin: 0 0 10pt; padding-left: 20pt; }
  li { margin-bottom: 4pt; }
  sup { color: #555; font-size: 8pt; }
  blockquote { border-left: 3px solid #ccc; margin: 10pt 0; padding: 2pt 12pt; color: #444; }
  table { border-collapse: collapse; width: 100%; margin: 8pt 0 16pt; font-size: 9.5pt; }
  th, td { border: 1px solid #ddd; padding: 5pt 8pt; text-align: left; }
  th { background: #f4f4f4; }
  .figure-placeholder { border: 1px dashed #bbb; color: #888; padding: 14pt; text-align: center;
                         margin: 10pt 0; font-size: 9pt; }
  figure { margin: 14pt 0; page-break-inside: avoid; text-align: center; }
  figure img { max-width: 100%; }
  figcaption { color: #666; font-size: 8.5pt; margin-top: 4pt; }
  .sources-table td:nth-child(3) { text-align: right; font-variant-numeric: tabular-nums; }
  .sources-table td:nth-child(4) { text-align: right; font-variant-numeric: tabular-nums; }
"""


def _strip_text(value: str) -> str:
    return bleach.clean(value, tags=[], attributes={}, strip=True)


def _wrap_citation_markers(markdown: str) -> str:
    return _CITATION_MARKERS_RE.sub(r"<sup>\1</sup>", markdown)


def _figure_data_uri(figure: Figure) -> str | None:
    try:
        data = Path(figure.file_path).read_bytes()
    except OSError as exc:
        logger.warning("html_renderer: could not read figure file %s: %s", figure.file_path, exc)
        return None
    return f"data:{figure.mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def _inline_figures(markdown: str, figures_by_id: dict[str, Figure]) -> str:
    """Rewrites `figure://{id}` to a base64 data URI (PRD §14) so the PDF
    needs no network access and no auth to render. A reference to an id
    that isn't a real, readable figure falls back to plain text — the
    synthesizer already strips unknown ids before persisting the report, so
    this only fires for a figure file that's gone missing on disk."""

    def _repl(m: "re.Match[str]") -> str:
        caption = _strip_text(m.group(1)) or "Figure"
        figure = figures_by_id.get(m.group(2))
        data_uri = _figure_data_uri(figure) if figure else None
        if data_uri is None:
            return f'<div class="figure-placeholder">{caption} — not available in this export</div>'
        return f'<figure><img src="{data_uri}" alt="{caption}"><figcaption>{caption}</figcaption></figure>'

    return _FIGURE_MD_RE.sub(_repl, markdown)


def _render_body_html(report_markdown: str, figures_by_id: dict[str, Figure]) -> str:
    processed = _wrap_citation_markers(_inline_figures(report_markdown, figures_by_id))
    raw_html = _MD.render(processed)
    return bleach.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=["http", "https", "mailto", "data"],
        strip=True,
    )


async def _render_sources_table(db: AsyncSession, run_id) -> str:
    """A complete, credibility-annotated source list (PRD §14). Built from
    `sources` directly rather than parsed out of the report markdown's own
    numbered Sources section — that section's marker-to-row correspondence
    matters for the reader following an in-body [n], so it's left as the
    model/synthesizer wrote it (plain numbered list, rendered normally by
    _render_body_html above); this is a separate, additional appendix."""
    rows = (
        await db.execute(
            select(Source, func.count(Evidence.id).label("evidence_count"))
            .outerjoin(Evidence, Evidence.source_id == Source.id)
            .where(Source.run_id == run_id)
            .group_by(Source.id)
            .order_by(Source.credibility_score.desc().nulls_last())
        )
    ).all()
    if not rows:
        return "<p>No sources recorded.</p>"

    lines = [
        '<table class="sources-table"><thead><tr>'
        "<th>Source</th><th>Domain</th><th>Credibility</th><th>Evidence items</th>"
        "</tr></thead><tbody>"
    ]
    for source, evidence_count in rows:
        title = _strip_text(source.title or source.url)
        domain = _strip_text(source.domain or "")
        score = f"{source.credibility_score:.2f}" if source.credibility_score is not None else "—"
        lines.append(f"<tr><td>{title}</td><td>{domain}</td><td>{score}</td><td>{evidence_count}</td></tr>")
    lines.append("</tbody></table>")
    return "\n".join(lines)


async def _fetch_figures_by_id(db: AsyncSession, run_id) -> dict[str, Figure]:
    rows = (await db.scalars(select(Figure).where(Figure.run_id == run_id))).all()
    return {str(row.id): row for row in rows}


async def render_report_html(db: AsyncSession, run: ResearchRun, report_markdown: str) -> str:
    figures_by_id = await _fetch_figures_by_id(db, run.id)
    body_html = _render_body_html(report_markdown, figures_by_id)
    sources_html = await _render_sources_table(db, run.id)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    query = _strip_text(run.query)
    mode = _strip_text(run.mode)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{query}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<h1 class="report-title">{query}</h1>
<p class="report-meta">{mode} research &bull; generated {generated_at}</p>
{body_html}
<h2>Sources (by credibility)</h2>
{sources_html}
</body>
</html>"""
