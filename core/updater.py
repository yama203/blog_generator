import io
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

GITHUB_REPO = "yama203/blog_generator"
GITHUB_API  = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

PROJECT_ROOT = Path(__file__).parent.parent

# Paths (relative to project root) that must never be overwritten by an update
_SKIP_PREFIXES = (
    "articles/",
    ".venv/",
    ".python/",
    ".uv",
    "uv.exe",
    "__pycache__/",
    "config.json",
    ".DS_Store",
    ".git/",
    ".claude/",
    "launcher/",
    "AI Blog Generator.app/",
)


def get_current_version() -> str:
    try:
        return (PROJECT_ROOT / "VERSION").read_text().strip()
    except Exception:
        return "0.0.0"


def get_latest_release() -> dict | None:
    """Return {'version': '1.0.9', 'zip_url': '...', 'notes': '...'} or None on error."""
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


def _should_skip(rel: str) -> bool:
    return any(rel.startswith(p) for p in _SKIP_PREFIXES)


def download_and_apply(zip_url: str, new_version: str) -> bool:
    """Download source ZIP and update all files except protected ones.

    Returns True if requirements.txt changed (caller should prompt restart).
    """
    r = requests.get(zip_url, timeout=120, stream=True)
    r.raise_for_status()

    old_reqs = (PROJECT_ROOT / "requirements.txt").read_text() if (PROJECT_ROOT / "requirements.txt").exists() else ""

    data = b"".join(r.iter_content(chunk_size=65536))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        # GitHub archive root is like "blog_generator-1.0.9/"
        prefix = names[0].split("/")[0] + "/"

        for member in names:
            rel = member[len(prefix):]
            if not rel or rel.endswith("/"):
                continue
            if _should_skip(rel):
                continue
            dest = PROJECT_ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))

    # Write new VERSION last so a partial update is retryable
    (PROJECT_ROOT / "VERSION").write_text(new_version + "\n")

    new_reqs = (PROJECT_ROOT / "requirements.txt").read_text() if (PROJECT_ROOT / "requirements.txt").exists() else ""
    reqs_changed = old_reqs != new_reqs
    if reqs_changed:
        _install_requirements()
    return reqs_changed


def _install_requirements() -> None:
    """Run uv pip install (or pip install) for updated requirements."""
    reqs = PROJECT_ROOT / "requirements.txt"
    uv = PROJECT_ROOT / ".uv"
    if uv.exists():
        cmd = [str(uv), "pip", "install", "-r", str(reqs)]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(reqs), "--quiet"]
    subprocess.run(cmd, check=False)
