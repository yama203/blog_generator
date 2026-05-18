import re
from datetime import datetime
from pathlib import Path

ARTICLES_DIR = Path(__file__).resolve().parent.parent / "articles"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta: dict = {}
    for line in text[3:end].strip().splitlines():
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    return meta, text[end + 4:].lstrip("\n")


def _build_frontmatter(title: str, keywords: str, created: str) -> str:
    return f"---\ntitle: {title}\nkeywords: {keywords}\ncreated: {created}\n---\n\n"


def save_article(title: str, markdown: str, keywords: str = "") -> Path:
    ARTICLES_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^\w\-]", "_", title)[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = ARTICLES_DIR / f"{ts}_{slug}.md"
    created = datetime.now().isoformat(timespec="seconds")
    path.write_text(_build_frontmatter(title, keywords, created) + markdown, encoding="utf-8")
    return path


def update_article(path: Path, markdown: str) -> None:
    meta, _ = _parse_frontmatter(Path(path).read_text(encoding="utf-8"))
    fm = _build_frontmatter(
        meta.get("title", ""), meta.get("keywords", ""), meta.get("created", "")
    )
    Path(path).write_text(fm + markdown, encoding="utf-8")


def list_articles() -> list[dict]:
    if not ARTICLES_DIR.exists():
        return []
    result = []
    for f in sorted(ARTICLES_DIR.glob("*.md"), reverse=True):
        meta, _ = _parse_frontmatter(f.read_text(encoding="utf-8"))
        result.append({
            "path": f,
            "filename": f.name,
            "title": meta.get("title", f.stem),
            "keywords": meta.get("keywords", ""),
            "created": meta.get("created", ""),
        })
    return result


def load_article(path: Path) -> dict:
    meta, body = _parse_frontmatter(Path(path).read_text(encoding="utf-8"))
    return {
        "title": meta.get("title", Path(path).stem),
        "keywords": meta.get("keywords", ""),
        "markdown": body,
    }


def delete_article(path: Path) -> None:
    Path(path).unlink(missing_ok=True)
