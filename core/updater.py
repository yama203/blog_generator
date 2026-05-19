import io
import zipfile
from pathlib import Path

import requests

GITHUB_REPO = "yama203/blog_generator"
GITHUB_API  = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

PROJECT_ROOT = Path(__file__).parent.parent

# Files to update (paths relative to project root)
_UPDATE_TARGETS = {
    "app.py",
    "requirements.txt",
    "core/assembler.py",
    "core/article_store.py",
    "core/config.py",
    "core/dalle_generator.py",
    "core/exporter.py",
    "core/text_generator.py",
    "core/updater.py",
    "core/wordpress_client.py",
    "generate_icon.py",
}


def get_current_version() -> str:
    try:
        return (PROJECT_ROOT / "VERSION").read_text().strip()
    except Exception:
        return "0.0.0"


def get_latest_release() -> dict | None:
    """Return {'version': '1.0.7', 'url': '...', 'notes': '...'} or None on error."""
    try:
        r = requests.get(GITHUB_API, timeout=10)
        r.raise_for_status()
        data = r.json()
        tag = data.get("tag_name", "")
        version = tag.lstrip("v")
        notes = data.get("body", "")
        zip_url = f"https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag}.zip"
        return {"version": version, "tag": tag, "zip_url": zip_url, "notes": notes}
    except Exception:
        return None


def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def is_update_available(current: str, latest: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def download_and_apply(zip_url: str, new_version: str) -> None:
    """Download source ZIP from GitHub and update files in PROJECT_ROOT."""
    r = requests.get(zip_url, timeout=120, stream=True)
    r.raise_for_status()

    data = b"".join(r.iter_content(chunk_size=65536))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # GitHub archive ZIP root is like "blog_generator-1.0.7/"
        names = zf.namelist()
        prefix = names[0].split("/")[0] + "/"

        for member in names:
            # Strip the repo-version prefix to get relative path
            rel = member[len(prefix):]
            if not rel or rel.endswith("/"):
                continue
            if rel not in _UPDATE_TARGETS:
                continue
            dest = PROJECT_ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))

    # Write new VERSION last so a partial update is retryable
    (PROJECT_ROOT / "VERSION").write_text(new_version + "\n")
