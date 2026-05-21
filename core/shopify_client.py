import re

import requests

_TIMEOUT = 30
_API_VERSION = "2024-10"


def _base_url(site: dict) -> str:
    store = site["store"].strip().rstrip("/")
    if not store.startswith(("http://", "https://")):
        store = "https://" + store
    return f"{store}/admin/api/{_API_VERSION}"


def _headers(site: dict) -> dict:
    return {
        "X-Shopify-Access-Token": site["access_token"].strip(),
        "Content-Type": "application/json",
    }


def _body_hint(r: requests.Response) -> str:
    try:
        text = r.text.strip()
        if not text:
            return ""
        try:
            j = r.json()
            errors = j.get("errors") or j.get("error") or ""
            if errors:
                return f"Shopify メッセージ: {errors}"
        except Exception:
            pass
        return f"サーバーレスポンス（先頭）: {text[:200]}"
    except Exception:
        return ""


def test_connection(site: dict) -> tuple[bool, str]:
    """接続・認証を確認。(ok, メッセージ) を返す。"""
    url = f"{_base_url(site)}/shop.json"
    try:
        r = requests.get(url, headers=_headers(site), timeout=_TIMEOUT)
        if r.status_code == 200:
            shop = r.json().get("shop", {})
            name = shop.get("name", "")
            return True, f"接続OK（{name}）"

        hint = _body_hint(r)

        if r.status_code == 401:
            return False, (
                "HTTP 401 認証エラー\n"
                "アクセストークンが正しくありません。\n"
                "Shopify 管理画面 > アプリ管理 > カスタムアプリ から\n"
                "Admin API アクセストークンを再発行してください。\n\n"
                f"{hint}"
            )
        if r.status_code == 403:
            return False, (
                "HTTP 403 アクセス拒否\n"
                "APIスコープが不足しています。\n"
                "カスタムアプリに `write_content` スコープが付与されているか確認してください。\n\n"
                f"{hint}"
            )
        if r.status_code == 404:
            return False, (
                "HTTP 404: ストアが見つかりません\n"
                "ストアURL（例: mystore.myshopify.com）を確認してください。\n\n"
                f"アクセス先: {url}\n{hint}"
            )
        return False, f"HTTP {r.status_code}\nアクセス先: {url}\n{hint}"

    except requests.exceptions.SSLError:
        return False, "SSL エラー: HTTPS の証明書を確認してください"
    except requests.exceptions.ConnectionError:
        return False, f"接続できません\nアクセス先: {url}\nURLを確認してください"
    except Exception as e:
        return False, f"エラー: {e}"


def list_blogs(site: dict) -> list[dict]:
    """ブログ一覧を返す。[{"id": int, "title": str}]"""
    r = requests.get(
        f"{_base_url(site)}/blogs.json",
        headers=_headers(site),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return [{"id": b["id"], "title": b["title"]} for b in r.json().get("blogs", [])]


def _strip_base64_images(html: str) -> tuple[str, int]:
    """
    <img src="data:image/..."> を除去し、(処理後HTML, 除去枚数) を返す。
    Shopify は Data URI を含む body_html を 422 で拒否するため必須。
    """
    original = html
    html = re.sub(r'<img[^>]+src=["\']data:image/[^"\']{20,}["\'][^>]*/?>', '', html)
    removed = original.count('data:image/') - html.count('data:image/')
    # Markdown の画像記法が HTML 変換後に残っている場合も除去
    html = re.sub(r'!\[[^\]]*\]\(data:image/[^\)]{20,}\)', '', html)
    return html, removed


def publish_article(
    site: dict,
    title: str,
    markdown_str: str,
    blog_id: int,
    published: bool = False,
    scheduled_at: str = "",
) -> dict:
    """
    Shopify ブログに記事を投稿する。
    base64 Data URI 画像は Shopify が拒否するため除去して投稿する。
    {"id": int, "handle": str, "published": bool, "images_removed": int} を返す。
    """
    from core.exporter import _md_to_html

    # H1 タイトルを除去（Shopify の title フィールドと重複するため）
    md_body = re.sub(r'^# .+\n?', '', markdown_str, count=1).strip()
    html = _md_to_html(md_body)

    # Shopify は Data URI を含む HTML を 422 で拒否するため除去
    html, images_removed = _strip_base64_images(html)

    article: dict = {
        "title": title,
        "body_html": html,
        "published": published,
    }

    if scheduled_at:
        # 予約投稿: published=false + published_at に未来日時
        article["published"] = False
        article["published_at"] = scheduled_at

    r = requests.post(
        f"{_base_url(site)}/blogs/{blog_id}/articles.json",
        headers=_headers(site),
        json={"article": article},
        timeout=60,
    )
    if not r.ok:
        # Shopify のエラー詳細を含めて例外を raise
        try:
            err = r.json().get("errors") or r.json().get("error") or r.text[:300]
        except Exception:
            err = r.text[:300]
        r.raise_for_status()  # これで HTTPError が発生するが、上で詳細を取れなければここで止まる
        raise requests.HTTPError(f"{r.status_code}: {err}", response=r)

    data = r.json().get("article", {})

    return {
        "id": data.get("id"),
        "handle": data.get("handle", ""),
        "published": data.get("published", False),
        "images_removed": images_removed,
    }
