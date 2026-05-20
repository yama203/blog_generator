import json
import re

import requests

OLLAMA_BASE_URL = "http://localhost:11434"
REQUEST_TIMEOUT = 300

OPENAI_TEXT_MODEL = "gpt-4o-mini"


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


def _generate_openai(prompt: str, api_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=OPENAI_TEXT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        timeout=REQUEST_TIMEOUT,
    )
    return response.choices[0].message.content or ""


def _llm(prompt: str, model: str, text_engine: str = "ollama",
         openai_api_key: str = "", keep_alive: int = 300) -> str:
    """Unified LLM call: routes to Ollama or OpenAI based on text_engine."""
    if text_engine == "openai":
        return _generate_openai(prompt, openai_api_key)
    return _generate(prompt, model, keep_alive)


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
    additional_instructions: str = "",
    text_engine: str = "ollama",
    openai_api_key: str = "",
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

    extra = f"\nAdditional instructions: {additional_instructions.strip()}" if additional_instructions.strip() else ""
    prompt = f"""You are a professional blog writer. Create a blog outline {lang}.

Keywords: {keywords}
{section_instruction}
Title instruction: {title_instruction}{extra}

Output ONLY this JSON, no other text:
{{
  "title": "blog title here",
  "sections": ["section 1 title", "section 2 title"]
}}
The sections array must have exactly {num_sections} items."""
    return _extract_json(_llm(prompt, model, text_engine, openai_api_key))


SECTION_LENGTHS: dict[str, str] = {
    "短め（約200字）":    "50-80 words",
    "やや短め（約400字）": "150-200 words",
    "標準（約600字）":    "300-500 words",
    "やや長め（約900字）": "500-700 words",
    "詳細（約1300字）":   "700-1000 words",
}

WRITING_STYLES: dict[str, str] = {
    "丁寧（です・ます調）":        "Use polite, professional tone throughout (です・ます調 for Japanese). Consistent formal-yet-approachable register. Never mix in だ・である endings.",
    "フレンドリー（です・ます調）": "Use warm, friendly tone throughout (やわらかいです・ます調 for Japanese). Encouraging and approachable like a knowledgeable friend. Keep です・ます endings; avoid stiff expressions.",
    "解説・論文調（だ・である調）": "Use authoritative, informational tone throughout (だ・である調 for Japanese). Clear and confident like a journalist or textbook. No です・ます endings.",
    "カジュアル（話し言葉風）":     "Use casual, conversational tone throughout. Write as if speaking directly to the reader using natural, informal expressions.",
}


RICH_ELEMENTS: dict[str, str] = {
    "bold":       "Use **bold** to highlight key terms and important concepts",
    "bullet":     "Use bullet lists (- item) for enumerations and feature lists",
    "numbered":   "Use numbered lists (1. item) for steps and ordered content",
    "blockquote": "Use > blockquotes for key takeaways or notable quotes",
    "code":       "Use `inline code` or ```code blocks``` for technical terms and snippets",
}


def generate_section(
    title: str,
    section_title: str,
    keywords: str,
    model: str,
    language: str = "日本語",
    rich_format: bool = True,
    section_length: str = "標準（約600字）",
    writing_style: str = "丁寧（です・ます調）",
    additional_instructions: str = "",
    rich_elements: set[str] | None = None,
    text_engine: str = "ollama",
    openai_api_key: str = "",
) -> str:
    lang = "in Japanese" if language == "日本語" else "in English"
    word_range = SECTION_LENGTHS.get(section_length, "300-500 words")
    style_instr = WRITING_STYLES.get(writing_style, list(WRITING_STYLES.values())[0])

    if not rich_format or not rich_elements:
        format_instruction = "Write in plain paragraphs only. Do not use any Markdown formatting (no bold, no lists, no blockquotes)."
    else:
        rules = "\n".join(f"- {RICH_ELEMENTS[k]}" for k in RICH_ELEMENTS if k in rich_elements)
        forbidden = [RICH_ELEMENTS[k] for k in RICH_ELEMENTS if k not in rich_elements]
        forbid_str = (" Do NOT use: " + ", ".join(
            k.replace("bold", "bold/**")
             .replace("bullet", "bullet lists")
             .replace("numbered", "numbered lists")
             .replace("blockquote", "blockquotes")
             .replace("code", "code blocks")
            for k in RICH_ELEMENTS if k not in rich_elements
        ) + ".") if forbidden else ""
        format_instruction = f"Format using Markdown to improve readability:\n{rules}\n- Keep paragraphs short (2-4 sentences each).{forbid_str}"
    extra = f"\nAdditional instructions: {additional_instructions.strip()}" if additional_instructions.strip() else ""
    prompt = f"""You are a professional blog writer. Write engaging section content {lang}.

Blog title: {title}
Section: {section_title}
Keywords: {keywords}
Tone/Style: {style_instr}{extra}

Write {word_range}. Output only the content text, no headings.
{format_instruction}"""
    return _llm(prompt, model, text_engine, openai_api_key).strip()


def generate_image_prompt(section_title: str, content: str, model: str,
                          text_engine: str = "ollama", openai_api_key: str = "") -> str:
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
    return _llm(prompt, model, text_engine, openai_api_key).strip().strip('"').strip("'")


def _strip_images(markdown: str) -> tuple[str, dict]:
    """Replace base64 image tags with short placeholders to keep LLM context small."""
    placeholders: dict[str, str] = {}

    def _replace(m: re.Match) -> str:
        key = f"__IMG_{len(placeholders)}__"
        placeholders[key] = m.group(0)
        return key

    stripped = re.sub(r'!\[[^\]]*\]\(data:image/[^\)]{20,}\)', _replace, markdown)
    return stripped, placeholders


def _restore_images(markdown: str, placeholders: dict) -> str:
    for key, original in placeholders.items():
        markdown = markdown.replace(key, original)
    return markdown


def _extract_heading_images(markdown: str) -> dict[str, list[str]]:
    """Return {heading: [img_tag, ...]} for each ## section that has images."""
    result: dict[str, list[str]] = {}
    parts = re.split(r'\n(?=## )', "\n" + markdown)
    for part in parts[1:]:
        head, _, body = part.strip().partition("\n")
        imgs = re.findall(r'!\[[^\]]*\]\(data:image/[^\)]{20,}\)', body)
        if imgs:
            result[head.strip()] = imgs
    return result


def _reinsert_heading_images(markdown: str, heading_images: dict[str, list[str]]) -> str:
    """Re-insert images immediately after their respective ## headings."""
    for heading, imgs in heading_images.items():
        img_block = "\n\n".join(imgs)
        markdown = re.sub(
            rf'({re.escape(heading)}\n)',
            rf'\1\n{img_block}\n\n',
            markdown, count=1,
        )
    return markdown


def _parse_sections(markdown: str) -> tuple[str, list[dict]]:
    """Split markdown into (preamble, [{heading, body}, ...]) on ## boundaries."""
    parts = re.split(r'\n(?=## )', "\n" + markdown)
    preamble = parts[0].strip()
    sections = []
    for part in parts[1:]:
        head, _, body = part.strip().partition("\n")
        sections.append({"heading": head, "body": body.strip()})
    return preamble, sections


def _assemble_sections(preamble: str, sections: list[dict]) -> str:
    parts = [preamble] if preamble else []
    for sec in sections:
        parts.append(f"\n{sec['heading']}\n\n{sec['body']}")
    return "\n".join(parts)


def revise_article(
    markdown: str,
    instruction: str,
    model: str,
    language: str = "日本語",
    section_index: int | None = None,
    writing_style: str = "丁寧（です・ます調）",
    text_engine: str = "ollama",
    openai_api_key: str = "",
) -> str:
    lang = "in Japanese" if language == "日本語" else "in English"
    style_instr = WRITING_STYLES.get(writing_style, list(WRITING_STYLES.values())[0])

    # Save image positions keyed by heading before stripping
    heading_images = _extract_heading_images(markdown)
    stripped, _ = _strip_images(markdown)

    if section_index is not None:
        preamble, sections = _parse_sections(stripped)
        if section_index >= len(sections):
            raise ValueError(f"セクション {section_index + 1} が存在しません")
        target = sections[section_index]
        # Send only text body (no image placeholders) to LLM
        text_only_body = re.sub(r'__IMG_\d+__', '', target['body']).strip()
        prompt = f"""You are a professional blog editor. Revise ONLY the section content below {lang} based on the instruction. Output ONLY the revised content (no heading, no explanation).

Instruction: {instruction}
Tone/Style to maintain: {style_instr}

Section heading: {target['heading']}
Current content:
{text_only_body}"""
        revised_body = _llm(prompt, model, text_engine, openai_api_key).strip()
        sections[section_index]["body"] = revised_body
        result = _assemble_sections(preamble, sections)
    else:
        prompt = f"""You are a professional blog editor. Revise the article below {lang} based on the instruction. Output ONLY the complete revised article in Markdown. No explanation, no preamble.

Instruction: {instruction}
Tone/Style to maintain: {style_instr}

Article:
{stripped}"""
        result = _llm(prompt, model, text_engine, openai_api_key).strip()

    return _reinsert_heading_images(result, heading_images)
