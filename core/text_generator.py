import json
import re

import requests

OLLAMA_BASE_URL = "http://localhost:11434"
REQUEST_TIMEOUT = 300


RECOMMENDED_MODELS: dict[str, str] = {
    "gemma2:9b":    "軽量・高速（推奨）　約 5GB",
    "qwen2.5:14b":  "高品質・バランス型　約 9GB",
    "qwen2.5:32b":  "最高品質・低速　　 約 20GB",
    "llama3.1:8b":  "汎用・軽量　　　　 約 5GB",
}


def check_ollama_connection() -> bool:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def list_ollama_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def pull_model(model_name: str):
    """Stream download progress for an Ollama model. Yields dict per line."""
    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/pull",
        json={"name": model_name, "stream": True},
        stream=True,
        timeout=3600,
    )
    r.raise_for_status()
    for line in r.iter_lines():
        if line:
            yield json.loads(line)


def unload_model(model: str) -> None:
    """Free the model from Ollama memory — call before image generation."""
    try:
        requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=10,
        )
    except Exception:
        pass


def _generate(prompt: str, model: str, keep_alive: int = 300) -> str:
    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False, "keep_alive": keep_alive},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["response"]


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\n?(.*?)\n?```", r"\1", text, flags=re.DOTALL).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])
    raise ValueError(f"JSONが見つかりませんでした: {text[:300]}")


def generate_outline(
    keywords: str,
    num_sections: int,
    model: str,
    language: str = "日本語",
    user_title: str = "",
    user_sections: list[str] | None = None,
) -> dict:
    fixed = [s.strip() for s in (user_sections or [])]
    # Pad to num_sections if shorter
    fixed += [""] * (num_sections - len(fixed))
    fixed = fixed[:num_sections]

    # Skip AI entirely when everything is provided
    if user_title.strip() and all(fixed):
        return {"title": user_title.strip(), "sections": fixed}

    lang = "in Japanese" if language == "日本語" else "in English"
    title_instruction = (
        f'Use exactly this title (do not change it): "{user_title}"'
        if user_title.strip()
        else "Create an appropriate title"
    )

    if any(fixed):
        section_lines = "\n".join(
            f'  {i+1}: "{s}" ← use exactly as-is' if s else f"  {i+1}: (create this)"
            for i, s in enumerate(fixed)
        )
        section_instruction = f"Sections (some are pre-defined, use them exactly):\n{section_lines}"
    else:
        section_instruction = f"Create {num_sections} section titles"

    prompt = f"""You are a professional blog writer. Create a blog outline {lang}.

Keywords: {keywords}
{section_instruction}
Title instruction: {title_instruction}

Output ONLY this JSON, no other text:
{{
  "title": "blog title here",
  "sections": ["section 1 title", "section 2 title"]
}}
The sections array must have exactly {num_sections} items."""
    return _extract_json(_generate(prompt, model))


SECTION_LENGTHS: dict[str, str] = {
    "短め（約200字）":    "50-80 words",
    "やや短め（約400字）": "150-200 words",
    "標準（約600字）":    "300-500 words",
    "やや長め（約900字）": "500-700 words",
    "詳細（約1300字）":   "700-1000 words",
}


def generate_section(
    title: str,
    section_title: str,
    keywords: str,
    model: str,
    language: str = "日本語",
    rich_format: bool = True,
    section_length: str = "標準（約600字）",
) -> str:
    lang = "in Japanese" if language == "日本語" else "in English"
    word_range = SECTION_LENGTHS.get(section_length, "300-500 words")
    format_instruction = (
        """Format using Markdown to improve readability:
- Use **bold** to highlight key terms and important concepts
- Use bullet lists (- item) or numbered lists for enumerations and steps
- Use > blockquotes for key takeaways or notable quotes
- Keep paragraphs short (2-4 sentences each)"""
        if rich_format
        else "Write in plain paragraphs only. Do not use any Markdown formatting (no bold, no lists, no blockquotes)."
    )
    prompt = f"""You are a professional blog writer. Write engaging section content {lang}.

Blog title: {title}
Section: {section_title}
Keywords: {keywords}

Write {word_range}. Output only the content text, no headings.
{format_instruction}"""
    return _generate(prompt, model).strip()


def generate_image_prompt(section_title: str, content: str, model: str) -> str:
    style_instruction = """Rules:
- Output ONLY the prompt, no explanation
- Write a natural English sentence describing the scene (not keyword lists)
- Include: main subject, setting, lighting, mood, visual style
- Maximum 50 words
- Prefer objects, environments, and concepts over people; if people are needed keep faces small or out of frame
- Example: "A sleek laptop on a wooden desk bathed in warm morning light, with a steaming coffee cup beside it, clean and minimal workspace aesthetic"
"""

    prompt = f"""Create an image generation prompt in English for this blog section.

Section: {section_title}
Content preview: {content[:300]}

{style_instruction}"""
    return _generate(prompt, model).strip().strip('"').strip("'")
