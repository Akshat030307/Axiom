"""Report markdown -> print-ready HTML (PRD §14).

Figures are out of scope for this build (no figures table/route exists
yet) — any `figure://` placeholder the synthesizer emitted renders as
plain text instead of a broken image reference. Once figures land, this
is the one place that needs to change: replace `_replace_figure_placeholders`
with a lookup that rewrites `figure://{id}` to a base64 data URI of the
stored print-variant image, matching PRD §14's original spec exactly.
"""

import re
from datetime import datetime, timezone

import bleach
from markdown_it import MarkdownIt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Evidence, ResearchRun, Source

# html=True is required for the citation-marker superscripts below to
# survive parsing — markdown-it otherwise escapes inline HTML.
_MD = MarkdownIt("commonmark", {"html": True}).enable("table")

# One or more back-to-back markers, e.g. "[2][3]" — wrapped as a single
# <sup> per PRD §14 ("citation markers rendered as superscripts").
_CITATION_MARKERS_RE = re.compile(r"((?:\[\d+\])+)")
_FIGURE_MD_RE = re.compile(r"!\[([^\]]*)\]\(figure://[^)]*\)")

_ALLOWED_TAGS = [
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
    "strong", "em", "sup", "sub", "a", "blockquote", "hr", "br",
    "code", "pre", "table", "thead", "tbody", "tr", "th", "td",
    "div", "span",
]
_ALLOWED_ATTRS = {"a": ["href"], "div": ["class"], "span": ["class"]}

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
  .sources-table td:nth-child(3) { text-align: right; font-variant-numeric: tabular-nums; }
  .sources-table td:nth-child(4) { text-align: right; font-variant-numeric: tabular-nums; }
"""


def _strip_text(value: str) -> str:
    return bleach.clean(value, tags=[], attributes={}, strip=True)


def _wrap_citation_markers(markdown: str) -> str:
    return _CITATION_MARKERS_RE.sub(r"<sup>\1</sup>", markdown)


def _replace_figure_placeholders(markdown: str) -> str:
    def _repl(m: "re.Match[str]") -> str:
        caption = _strip_text(m.group(1)) or "Figure"
        return f'<div class="figure-placeholder">{caption} — not available in this export</div>'

    return _FIGURE_MD_RE.sub(_repl, markdown)


def _render_body_html(report_markdown: str) -> str:
    processed = _wrap_citation_markers(_replace_figure_placeholders(report_markdown))
    raw_html = _MD.render(processed)
    return bleach.clean(raw_html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


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


async def render_report_html(db: AsyncSession, run: ResearchRun, report_markdown: str) -> str:
    body_html = _render_body_html(report_markdown)
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
