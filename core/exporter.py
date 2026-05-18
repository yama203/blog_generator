import base64 as _base64
import io
import re
import zipfile


def _md_to_html(markdown_str: str) -> str:
    import markdown as md_lib
    return md_lib.markdown(markdown_str, extensions=["extra"])


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
