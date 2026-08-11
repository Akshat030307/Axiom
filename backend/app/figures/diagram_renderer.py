"""Mermaid diagram source -> SVG (PRD §11.3), rendered deterministically by
mmdc (@mermaid-js/mermaid-cli) — never by an image-generation model. The
LLM's own text (boxes/arrows/labels) is exactly what gets drawn; nothing is
reinterpreted through pixels, so there's no image-generation step to
introduce a wrong label or a misplaced box on top of whatever the model
wrote.
"""

import logging
import re
import subprocess
import tempfile
from pathlib import Path

from app.models.schemas import DiagramSpec

logger = logging.getLogger(__name__)

ALLOWED_DIAGRAM_TYPES = {"flowchart", "sequenceDiagram", "timeline", "mindmap", "quadrantChart"}
# No `click`/`href`/link directives or embedded scripting — this renders as
# a static image, nothing in it is ever meant to be interactive.
_FORBIDDEN_RE = re.compile(r"\b(click|href)\b|<script", re.IGNORECASE)
RENDER_TIMEOUT_SECONDS = 15
PUPPETEER_CONFIG_PATH = "/app/puppeteer-config.json"


class DiagramValidationError(Exception):
    pass


def _validate_source(spec: DiagramSpec) -> None:
    if spec.diagram_type not in ALLOWED_DIAGRAM_TYPES:
        raise DiagramValidationError(f"disallowed diagram_type: {spec.diagram_type!r}")
    if not spec.mermaid_source.strip():
        raise DiagramValidationError("empty mermaid_source")

    # The source must actually declare the type it claims — otherwise a
    # mismatch (model says "flowchart" but writes "sequenceDiagram" syntax)
    # fails at render time with a confusing mmdc stderr dump instead of a
    # clean, logged rejection here. "graph" is Mermaid's older alias for
    # flowchart and still common in model output.
    first_line = spec.mermaid_source.strip().splitlines()[0].strip()
    starts_with_declared_type = first_line.startswith(spec.diagram_type) or (
        spec.diagram_type == "flowchart" and first_line.startswith("graph")
    )
    if not starts_with_declared_type:
        raise DiagramValidationError(
            f"mermaid_source doesn't start with its declared diagram_type {spec.diagram_type!r}: {first_line!r}"
        )

    if _FORBIDDEN_RE.search(spec.mermaid_source):
        raise DiagramValidationError("mermaid_source contains a disallowed interactive/scripting directive")


def render_diagram_svg(spec: DiagramSpec) -> bytes:
    """Validates `spec` (allowed diagram types, declared-type/source
    agreement, no click/href/script) then shells out to mmdc in a subprocess
    with a hard timeout. Raises DiagramValidationError or a subprocess
    error/timeout on any failure — diagram_generator.py treats both as
    non-fatal, same as every other figure-producing tool in this codebase:
    drop the figure, log it, never abort the run."""
    _validate_source(spec)

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "diagram.mmd"
        output_path = Path(tmpdir) / "diagram.svg"
        input_path.write_text(spec.mermaid_source, encoding="utf-8")

        result = subprocess.run(
            [
                "mmdc",
                "-i", str(input_path),
                "-o", str(output_path),
                "-b", "white",
                "-p", PUPPETEER_CONFIG_PATH,
            ],
            capture_output=True,
            timeout=RENDER_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0 or not output_path.exists():
            stderr = result.stderr.decode("utf-8", errors="replace")[:2000]
            raise RuntimeError(f"mmdc render failed (exit {result.returncode}): {stderr}")

        return output_path.read_bytes()
