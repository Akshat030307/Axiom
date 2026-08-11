"""Content-addressed figure storage (PRD §11.4) — served only through
GET /figures/{id}/file with an ownership check, never as a static directory.
"""

import hashlib
from pathlib import Path

from app.config import get_settings

settings = get_settings()


def store_png(run_id: str, data: bytes) -> str:
    return store_image(run_id, data, "png")


def store_image(run_id: str, data: bytes, ext: str) -> str:
    sha = hashlib.sha256(data).hexdigest()
    run_dir = Path(settings.FIGURES_DIR) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{sha}.{ext}"
    path.write_bytes(data)
    return str(path)
