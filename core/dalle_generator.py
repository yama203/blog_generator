from pathlib import Path

import requests
from openai import OpenAI

# モデルごとの設定
_MODEL_CONFIG = {
    "dall-e-3": {
        "size": "1792x1024",
        "quality_map": {"標準": "standard", "高品質": "hd"},
        "supports_url": True,
    },
    "gpt-image-1": {
        "size": "1536x1024",
        "quality_map": {"標準": "medium", "高品質": "high"},
        "supports_url": False,  # gpt-image-1 は b64_json で返す
    },
}

OPENAI_IMAGE_MODELS = ["dall-e-3", "gpt-image-1"]


def detect_available_model(api_key: str) -> str | None:
    """利用可能な画像モデルを自動検出して返す。どれも使えなければ None。"""
    client = OpenAI(api_key=api_key)
    for model in OPENAI_IMAGE_MODELS:
        try:
            client.models.retrieve(model)
            return model
        except Exception:
            continue
    return None


class DalleGenerator:
    def __init__(self, api_key: str, quality: str = "標準", model: str = "auto") -> None:
        self.client = OpenAI(api_key=api_key)
        self.quality = quality
        if model == "auto":
            self.model = detect_available_model(api_key) or "dall-e-3"
        else:
            self.model = model

    def generate(self, prompt: str, output_path: Path) -> Path:
        cfg = _MODEL_CONFIG.get(self.model, _MODEL_CONFIG["dall-e-3"])
        quality_val = cfg["quality_map"].get(self.quality, list(cfg["quality_map"].values())[0])

        response = self.client.images.generate(
            model=self.model,
            prompt=prompt,
            size=cfg["size"],
            quality=quality_val,
            n=1,
        )

        if cfg["supports_url"]:
            image_url = response.data[0].url
            image_bytes = requests.get(image_url, timeout=60).content
        else:
            import base64
            image_bytes = base64.b64decode(response.data[0].b64_json)

        output_path.write_bytes(image_bytes)
        return output_path
