from pathlib import Path

from PIL import Image

from seo_agent.db import LedgerError


def generate_cover(title: str, category: str, output: Path) -> dict[str, object]:
    del title, category
    data_dir = Path(__import__("os").environ["VEDICWAY_SEO_DATA_DIR"]).resolve()
    target = output.resolve()
    try:
        target.relative_to(data_dir)
    except ValueError as exc:
        raise LedgerError("Media path must stay inside agent data") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 630), (55, 32, 79)).save(target, "WEBP")
    return {"path": str(target), "width": 1200, "height": 630}
