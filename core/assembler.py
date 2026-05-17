import base64
from pathlib import Path


def _embed_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{b64}"


def _build_toc(sections: list[dict], language: str = "日本語") -> str:
    label = "目次" if language == "日本語" else "Table of Contents"
    lines = [f"## {label}\n"]
    for section in sections:
        heading = section["heading"]
        # GFM anchor: lowercase, whitespace → hyphen
        import re
        anchor = re.sub(r"\s+", "-", heading.lower())
        lines.append(f"- [{heading}](#{anchor})")
    return "\n".join(lines)


def assemble_markdown(
    title: str,
    sections: list[dict],
    include_toc: bool = False,
    language: str = "日本語",
) -> str:
    """
    sections: [{"heading": str, "content": str, "image_path": Path | None}]
    Returns a self-contained Markdown string with images embedded as base64.
    """
    parts = [f"# {title}\n"]

    if include_toc:
        parts.append(f"\n{_build_toc(sections, language)}\n")

    for section in sections:
        parts.append(f"\n## {section['heading']}\n")

        img_path = section.get("image_path")
        if img_path and Path(img_path).exists():
            data_uri = _embed_image(Path(img_path))
            parts.append(f"\n![{section['heading']}]({data_uri})\n")

        parts.append(f"\n{section['content'].strip()}\n")

    return "\n".join(parts)
