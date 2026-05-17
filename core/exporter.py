import csv
import io
import re


def _md_to_html(markdown_str: str) -> str:
    import markdown as md_lib
    return md_lib.markdown(markdown_str, extensions=["extra"])


def _url_handle(title: str) -> str:
    handle = title.lower()
    handle = re.sub(r"[^\w\s-]", "", handle)
    handle = re.sub(r"[\s_]+", "-", handle).strip("-")
    return handle or "blog-post"


def to_wordpress_html(title: str, markdown_str: str) -> str:
    """
    WordPress Classic Editor / Block Editor (HTML モード) に貼り付けられる HTML ファイル。
    画像は base64 埋め込みで自己完結しています。
    """
    body = _md_to_html(markdown_str)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <!--
    WordPress への入稿方法:
    1. WordPress 管理画面 > 投稿 > 新規追加
    2. ブロックエディター: 右上「︙」> 「コードエディター」に切り替えてこのファイルの <body> 内容を貼り付け
       クラシックエディター: 「テキスト」タブに切り替えて貼り付け
  -->
</head>
<body>
{body}
</body>
</html>"""


def to_shopify_html(title: str, markdown_str: str) -> str:
    """
    Shopify 管理画面 > ブログ記事 > HTML 編集 に貼り付けられる HTML。
    タイトルは Shopify 側のフィールドに入力するため、ここでは本文のみ出力します。
    """
    # H1 タイトル行を除去（Shopify の Title フィールドと重複するため）
    md_body = re.sub(r"^# .+\n?", "", markdown_str, count=1).strip()
    return _md_to_html(md_body)


def to_shopify_csv(title: str, markdown_str: str, tags: str = "") -> str:
    """
    Matrixify (旧 Excelify) 形式の Shopify ブログ記事インポート用 CSV。
    Shopify 管理画面にアプリをインストールして一括インポートできます。
    """
    md_body = re.sub(r"^# .+\n?", "", markdown_str, count=1).strip()
    body_html = _md_to_html(md_body)

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(["Title", "Body HTML", "Tags", "Published", "URL Handle", "Author"])
    writer.writerow([title, body_html, tags, "TRUE", _url_handle(title), ""])
    return output.getvalue()
