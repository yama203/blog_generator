import base64 as _base64
import io
import re
import zipfile
from html.parser import HTMLParser


def _md_to_html(markdown_str: str) -> str:
    import markdown as md_lib
    return md_lib.markdown(markdown_str, extensions=["extra"])


class _GutenbergBuilder(HTMLParser):
    """python-markdown の HTML 出力を Gutenberg ブロックマークアップに変換する。"""

    _BLOCK_TAGS = frozenset({"h1","h2","h3","h4","h5","h6","p","ul","ol","blockquote","pre"})
    _VOID_TAGS  = frozenset({"img","br","hr","input","meta","link","area","base","col",
                              "embed","param","source","track","wbr"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self._tag:  str | None = None
        self._buf:  list[str]  = []
        self._nest: int        = 0

    @staticmethod
    def _attr_str(attrs: list) -> str:
        parts = [f'{k}="{v}"' if v is not None else k for k, v in attrs]
        return (" " + " ".join(parts)) if parts else ""

    # ── parser callbacks ───────────────────────────────────────────────────────

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self._tag is None:
            if tag == "hr":
                self.blocks.append(
                    '<!-- wp:separator -->\n'
                    '<hr class="wp-block-separator has-alpha-channel-opacity"/>\n'
                    '<!-- /wp:separator -->'
                )
            elif tag in self._BLOCK_TAGS:
                self._tag  = tag
                self._buf  = []
                self._nest = 1
        else:
            if tag == self._tag:
                self._nest += 1
            if tag in self._VOID_TAGS:
                self._buf.append(f"<{tag}{self._attr_str(attrs)}/>")
            else:
                self._buf.append(f"<{tag}{self._attr_str(attrs)}>")

    def handle_endtag(self, tag: str) -> None:
        if self._tag is None:
            return
        if tag == self._tag:
            self._nest -= 1
            if self._nest == 0:
                self._emit(self._tag, "".join(self._buf))
                self._tag = None
                self._buf = []
                return
        self._buf.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        """XHTML 形式の自己終了タグ <img ... /> など。"""
        if self._tag is not None:
            self._buf.append(f"<{tag}{self._attr_str(attrs)}/>")

    def handle_data(self, data: str) -> None:
        if self._tag is not None:
            self._buf.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._tag is not None:
            self._buf.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._tag is not None:
            self._buf.append(f"&#{name};")

    # ── block emitter ──────────────────────────────────────────────────────────

    def _emit(self, tag: str, inner: str) -> None:
        if tag[0] == "h" and len(tag) == 2 and tag[1].isdigit():
            level = tag[1]
            self.blocks.append(
                f'<!-- wp:heading {{"level":{level}}} -->\n'
                f'<{tag} class="wp-block-heading">{inner}</{tag}>\n'
                f'<!-- /wp:heading -->'
            )

        elif tag == "p":
            img_m = re.match(r"^\s*<img\s([^>]*/?)\s*>\s*$", inner, re.DOTALL)
            if img_m:
                a    = img_m.group(1)
                src  = re.search(r'src="([^"]*)"', a)
                alt  = re.search(r'alt="([^"]*)"', a)
                self.blocks.append(
                    '<!-- wp:image -->\n'
                    '<figure class="wp-block-image">'
                    f'<img src="{src.group(1) if src else ""}" alt="{alt.group(1) if alt else ""}"/>'
                    '</figure>\n'
                    '<!-- /wp:image -->'
                )
            else:
                self.blocks.append(
                    f'<!-- wp:paragraph -->\n<p>{inner}</p>\n<!-- /wp:paragraph -->'
                )

        elif tag == "ul":
            self.blocks.append(
                f'<!-- wp:list -->\n'
                f'<ul class="wp-block-list">{inner}</ul>\n'
                f'<!-- /wp:list -->'
            )

        elif tag == "ol":
            self.blocks.append(
                f'<!-- wp:list {{"ordered":true}} -->\n'
                f'<ol class="wp-block-list">{inner}</ol>\n'
                f'<!-- /wp:list -->'
            )

        elif tag == "blockquote":
            self.blocks.append(
                f'<!-- wp:quote -->\n'
                f'<blockquote class="wp-block-quote">{inner.strip()}</blockquote>\n'
                f'<!-- /wp:quote -->'
            )

        elif tag == "pre":
            code_m = re.match(r"\s*<code[^>]*>(.*?)</code>\s*", inner, re.DOTALL)
            code   = code_m.group(1) if code_m else inner
            self.blocks.append(
                f'<!-- wp:code -->\n'
                f'<pre class="wp-block-code"><code>{code}</code></pre>\n'
                f'<!-- /wp:code -->'
            )


def _md_to_gutenberg(markdown_str: str) -> str:
    """Markdown を Gutenberg ブロックマークアップに変換する。"""
    html    = _md_to_html(markdown_str)
    builder = _GutenbergBuilder()
    builder.feed(html)
    return "\n\n".join(builder.blocks)


def _extract_images(markdown_str: str) -> tuple[str, dict[str, bytes]]:
    """base64 画像を個別ファイルとして抽出し (処理済みMarkdown, {filename: bytes}) を返す。"""
    images: dict[str, bytes] = {}
    counter = [0]

    def _replace(m: re.Match) -> str:
        alt = m.group(1)
        data_uri = m.group(2)
        b64_m = re.match(r'data:image/(\w+);base64,(.+)', data_uri, re.DOTALL)
        if not b64_m:
            return m.group(0)
        ext = b64_m.group(1)
        counter[0] += 1
        slug = re.sub(r'[^\w]', '_', alt)[:30].strip('_')
        fname = f"image_{counter[0]:02d}_{slug}.{ext}"
        images[fname] = _base64.b64decode(b64_m.group(2))
        return f"![{alt}](images/{fname})"

    processed = re.sub(
        r'!\[([^\]]*)\]\((data:image/[^\)]{20,})\)',
        _replace,
        markdown_str,
    )
    return processed, images


def _build_zip(html: str, images: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("post.html", html.encode('utf-8'))
        for fname, img_bytes in images.items():
            zf.writestr(f"images/{fname}", img_bytes)
    return buf.getvalue()


def to_wordpress_zip(title: str, markdown_str: str) -> bytes:
    """WordPress 用 ZIP。post.html + images/ を含む。"""
    processed_md, images = _extract_images(markdown_str)
    body_html = _md_to_html(processed_md)

    if images:
        instructions = (
            "    1. images/ フォルダ内の画像を WordPress メディアライブラリにアップロード\n"
            "    2. アップロード後に各画像の URL をコピー\n"
            "    3. post.html 内の src=\"images/image_XX_...\" を実際の URL に置き換える\n"
            "    4. <body>〜</body> の内容を WordPress エディターに貼り付け"
        )
    else:
        instructions = "    1. <body>〜</body> の内容を WordPress エディターに貼り付け"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <!--
    WordPress への入稿方法:
{instructions}
  -->
</head>
<body>
{body_html}
</body>
</html>"""

    return _build_zip(html, images)


def to_shopify_zip(title: str, markdown_str: str) -> bytes:
    """Shopify 用 ZIP。H1 タイトルを除去し post.html + images/ を含む。"""
    md_body = re.sub(r"^# .+\n?", "", markdown_str, count=1).strip()
    processed_md, images = _extract_images(md_body)
    body_html = _md_to_html(processed_md)

    if images:
        instructions = (
            "    1. images/ フォルダ内の画像を Shopify 管理画面 > コンテンツ > ファイル にアップロード\n"
            "    2. アップロード後に各画像の URL をコピー\n"
            "    3. post.html 内の src=\"images/image_XX_...\" を実際の URL に置き換える\n"
            "    4. Shopify 管理画面 > ブログ記事 > コンテンツの「HTML を表示」に貼り付け\n"
            "    ※ タイトルは Shopify の「タイトル」フィールドに別途入力してください。"
        )
    else:
        instructions = (
            "    1. Shopify 管理画面 > ブログ記事 > コンテンツの「HTML を表示」に貼り付け\n"
            "    ※ タイトルは Shopify の「タイトル」フィールドに別途入力してください。"
        )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <!--
    Shopify への入稿方法:
{instructions}
  -->
</head>
<body>
{body_html}
</body>
</html>"""

    return _build_zip(html, images)
