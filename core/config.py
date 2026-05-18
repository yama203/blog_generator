import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def _load() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_openai_key() -> str:
    return _load().get("openai_api_key", "")


def save_openai_key(key: str) -> None:
    data = _load()
    data["openai_api_key"] = key
    _save(data)


def delete_openai_key() -> None:
    data = _load()
    data.pop("openai_api_key", None)
    _save(data)


# ── WordPress sites ────────────────────────────────────────────────────────────

def list_wordpress_sites() -> list[dict]:
    return _load().get("wordpress_sites", [])


def save_wordpress_site(site: dict) -> None:
    """Add or update a site entry (matched by name)."""
    data = _load()
    sites = data.get("wordpress_sites", [])
    for i, s in enumerate(sites):
        if s.get("name") == site["name"]:
            sites[i] = site
            data["wordpress_sites"] = sites
            _save(data)
            return
    sites.append(site)
    data["wordpress_sites"] = sites
    _save(data)


def delete_wordpress_site(name: str) -> None:
    data = _load()
    data["wordpress_sites"] = [s for s in data.get("wordpress_sites", []) if s.get("name") != name]
    _save(data)
