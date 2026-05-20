import base64 as _base64
import re

import requests

_TIMEOUT = 30


def _base_url(site: dict) -> str:
    url = site["url"].strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _auth(site: dict) -> tuple[str, str]:
    # Application Passwords are displayed with spaces ("Xxxx Xxxx ...") but
    # WordPress authenticates against the spaceless form.
    return (site["username"], site["app_password"].replace(" ", ""))


_HTACCESS_HINT = (
    "【レンタルサーバーの場合の対処法】\n"
    "FastCGI/PHP-FPM 環境では Authorization ヘッダーが PHP に届かないため\n"
    "アプリケーションパスワードが機能しません。\n"
    "WordPress の .htaccess（wp-config.php と同じディレクトリ）に\n"
    "以下を追記してください:\n\n"
    "  RewriteEngine On\n"
    "  RewriteRule .* - [E=HTTP_AUTHORIZATION:%{HTTP:Authorization}]\n\n"
    "さくらのレンタルサーバー / エックスサーバー / ロリポップ 等で有効です。"
)


def _body_hint(r: requests.Response) -> str:
    """レスポンスボディ先頭を診断用に返す。"""
    try:
        text = r.text.strip()
        if not text:
            return ""
        # JSON なら message フィールドだけ取り出す
        try:
            j = r.json()
            msg = j.get("message") or j.get("error") or ""
            if msg:
                return f"WordPress メッセージ: {msg}"
        except Exception:
            pass
        return f"サーバーレスポンス（先頭）: {text[:200]}"
    except Exception:
        return ""


def test_connection(site: dict) -> tuple[bool, str]:
    """接続・認証を確認。(ok, メッセージ) を返す。"""
    url = f"{_base_url(site)}/wp-json/wp/v2/users/me"
    try:
        r = requests.get(url, auth=_auth(site), timeout=_TIMEOUT)
        if r.status_code == 200:
            name = r.json().get("name", "")
            return True, f"接続OK（{name}）"

        hint = _body_hint(r)

        if r.status_code == 401:
            return False, (
                "HTTP 401 認証エラー\n"
                "ユーザー名またはアプリケーションパスワードが正しくありません。\n"
                "パスワードはスペースなしで入力しているか確認してください。\n\n"
                f"{_HTACCESS_HINT}\n\n{hint}"
            )
        if r.status_code == 403:
            return False, (
                "HTTP 403 アクセス拒否\n"
                "セキュリティプラグイン（Wordfence 等）または\n"
                "サーバーが REST API へのアクセスをブロックしています。\n\n"
                f"{_HTACCESS_HINT}\n\n{hint}"
            )
        if r.status_code == 404:
            return False, (
                "HTTP 404: REST API が見つかりません\n"
                "URL またはパーマリンク設定（投稿名など）を確認してください。\n\n"
                f"アクセス先: {url}\n{hint}"
            )
        return False, f"HTTP {r.status_code}\nアクセス先: {url}\n{hint}"

    except requests.exceptions.SSLError:
        return False, "SSL エラー: HTTPS の証明書を確認してください"
    except requests.exceptions.ConnectionError:
        return False, f"接続できません\nアクセス先: {url}\nURL を確認してください"
    except Exception as e:
        return False, f"エラー: {e}"


def get_post_types(site: dict) -> dict[str, str]:
    """
    REST API に公開されている投稿タイプを返す。
    {rest_base: 表示名} の辞書。
    """
    r = requests.get(
        f"{_base_url(site)}/wp-json/wp/v2/types",
        auth=_auth(site),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    result = {}
    for _slug, info in r.json().items():
        rest_base = info.get("rest_base", _slug)
        name = info.get("name", _slug)
        result[rest_base] = name
    return result


def _upload_media(base_url: str, auth: tuple, image_bytes: bytes, filename: str, mime_type: str) -> str:
    """画像をメディアライブラリにアップロードし URL を返す。"""
    r = requests.post(
        f"{base_url}/wp-json/wp/v2/media",
        auth=auth,
        headers={
            "Content-Type": mime_type,
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
        data=image_bytes,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["source_url"]


def publish_article(
    site: dict,
    title: str,
    markdown_str: str,
    rest_base: str,
    status: str,
    use_blocks: bool = False,
    scheduled_at: str = "",
) -> dict:
    """
    WordPress に記事を投稿する。
    base64 画像はメディアライブラリにアップロードして URL に差し替える。
    use_blocks=True のとき Gutenberg ブロックマークアップで投稿する。
    {"id": int, "link": str, "status": str} を返す。
    """
    from core.exporter import _md_to_html, _md_to_gutenberg

    base_url = _base_url(site)
    auth = _auth(site)
    counter = [0]

    def _replace_image(m: re.Match) -> str:
        alt = m.group(1)
        data_uri = m.group(2)
        b64_m = re.match(r'data:image/(\w+);base64,(.+)', data_uri, re.DOTALL)
        if not b64_m:
            return m.group(0)
        ext = b64_m.group(1)
        counter[0] += 1
        slug = re.sub(r'[^\w]', '_', alt, flags=re.ASCII)[:30].strip('_') or 'img'
        filename = f"image_{counter[0]:02d}_{slug}.{ext}"
        img_bytes = _base64.b64decode(b64_m.group(2))
        media_url = _upload_media(base_url, auth, img_bytes, filename, f"image/{ext}")
        return f"![{alt}]({media_url})"

    processed_md = re.sub(
        r'!\[([^\]]*)\]\((data:image/[^\)]{20,})\)',
        _replace_image,
        markdown_str,
    )

    # H1 タイトルを除去（WordPress の title フィールドと重複するため）
    md_body = re.sub(r'^# .+\n?', '', processed_md, count=1).strip()
    html = _md_to_gutenberg(md_body) if use_blocks else _md_to_html(md_body)

    payload: dict = {"title": title, "content": html, "status": status}
    if scheduled_at:
        payload["date"] = scheduled_at      # サイトのタイムゾーンで解釈される
        payload["status"] = "future"        # 予約投稿には future が必要

    r = requests.post(
        f"{base_url}/wp-json/wp/v2/{rest_base}",
        auth=auth,
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    return {"id": data["id"], "link": data.get("link", ""), "status": data["status"]}
