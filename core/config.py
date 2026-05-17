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
