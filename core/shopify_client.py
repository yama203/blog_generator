import base64 as _b64
import re
import time

import requests

_TIMEOUT = 30
_API_VERSION = "2024-10"


def _base_url(site: dict) -> str:
    store = site["store"].strip().rstrip("/")
    if not store.startswith(("http://", "https://")):
        store = "https://" + store
    return f"{store}/admin/api/{_API_VERSION}"


def _graphql_url(site: dict) -> str:
    store = site["store"].strip().rstrip("/")
    if not store.startswith(("http://", "https://")):
        store = "https://" + store
    return f"{store}/admin/api/{_API_VERSION}/graphql.json"


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


def _graphql(site: dict, query: str, variables: dict | None = None) -> dict:
    r = requests.post(
        _graphql_url(site),
        headers={
            "X-Shopify-Access-Token": site["access_token"].strip(),
            "Content-Type": "application/json",
        },
        json={"query": query, "variables": variables or {}},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


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


# ── 画像アップロード（Staged Uploads + Files API） ────────────────────────────

def _upload_image_to_cdn(
    site: dict,
    image_bytes: bytes,
    filename: str,
    mime_type: str,
) -> str | None:
    """
    Shopify の Staged Uploads → Files API を使って画像を CDN にアップロードし、
    CDN URL を返す。失敗時は None。

    必要スコープ: write_files（カスタムアプリに追加が必要）
    """
    # Step 1: staged upload URL を取得
    staged_result = _graphql(site, """
    mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
      stagedUploadsCreate(input: $input) {
        stagedTargets {
          url
          resourceUrl
          parameters { name value }
        }
        userErrors { field message }
      }
    }
    """, {"input": [{
        "filename": filename,
        "mimeType": mime_type,
        "resource": "FILE",
        "fileSize": str(len(image_bytes)),
        "httpMethod": "POST",
    }]})

    errors = staged_result.get("data", {}).get("stagedUploadsCreate", {}).get("userErrors", [])
    if errors:
        raise ValueError(f"Staged upload エラー: {errors}")

    targets = staged_result.get("data", {}).get("stagedUploadsCreate", {}).get("stagedTargets", [])
    if not targets:
        return None

    target = targets[0]
    params = {p["name"]: p["value"] for p in target["parameters"]}

    # Step 2: S3 / GCS にアップロード（params を先、file を最後に）
    upload_r = requests.post(
        target["url"],
        data=params,
        files={"file": (filename, image_bytes, mime_type)},
        timeout=120,
    )
    upload_r.raise_for_status()

    # Step 3: Files API で Shopify に登録
    file_result = _graphql(site, """
    mutation fileCreate($files: [FileCreateInput!]!) {
      fileCreate(files: $files) {
        files {
          ... on MediaImage {
            id
            image { url }
          }
          ... on GenericFile {
            id
            url
          }
        }
        userErrors { field message }
      }
    }
    """, {"files": [{
        "originalSource": target["resourceUrl"],
        "filename": filename,
        "contentType": "IMAGE",
    }]})

    file_errors = file_result.get("data", {}).get("fileCreate", {}).get("userErrors", [])
    if file_errors:
        raise ValueError(f"fileCreate エラー: {file_errors}")

    # Step 4: CDN URL をポーリング（非同期処理のため最大 20 秒待機）
    for attempt in range(7):
        files_data = file_result.get("data", {}).get("fileCreate", {}).get("files", [])
        if files_data:
            f = files_data[0]
            cdn_url = (f.get("image") or {}).get("url") or f.get("url")
            if cdn_url:
                return cdn_url

        if attempt < 6:
            time.sleep(3)
            # files クエリで再取得
            poll_result = _graphql(site, """
            query($q: String!) {
              files(first: 1, query: $q) {
                edges {
                  node {
                    ... on MediaImage { image { url } }
                    ... on GenericFile { url }
                  }
                }
              }
            }
            """, {"q": f"filename:{filename}"})
            edges = poll_result.get("data", {}).get("files", {}).get("edges", [])
            if edges:
                node = edges[0]["node"]
                cdn_url = (node.get("image") or {}).get("url") or node.get("url")
                if cdn_url:
                    return cdn_url
            # file_result を更新して次のループへ
            file_result = {"data": {"fileCreate": {"files": [], "userErrors": []}}}

    return None


def _replace_base64_with_cdn(
    html: str,
    markdown_str: str,
    site: dict,
    progress_cb=None,
) -> tuple[str, int, int]:
    """
    HTML / Markdown 内の base64 Data URI 画像を Shopify CDN URL に差し替える。
    progress_cb(current, total, filename) で進捗通知。
    (処理後HTML, 成功枚数, 失敗枚数) を返す。
    """
    # Markdown から base64 画像を抽出（alt, ext, b64data）
    pattern = re.compile(
        r'!\[([^\]]*)\]\(data:image/(\w+);base64,([A-Za-z0-9+/=\n]+)\)',
        re.DOTALL,
    )
    matches = pattern.findall(markdown_str)
    total = len(matches)
    succeeded = 0
    failed = 0

    for i, (alt, ext, b64data) in enumerate(matches):
        filename = f"blog_image_{i+1:02d}.{ext}"
        mime_type = f"image/{ext}"
        if progress_cb:
            progress_cb(i + 1, total, filename)
        try:
            img_bytes = _b64.b64decode(b64data.replace("\n", ""))
            cdn_url = _upload_image_to_cdn(site, img_bytes, filename, mime_type)
            if cdn_url:
                # HTML 内の対応する <img> タグを CDN URL に差し替え
                # src="data:image/ext;base64,..." の部分を探して置換
                b64_prefix = b64data[:30].replace("\n", "")
                html = re.sub(
                    rf'src=["\']data:image/{re.escape(ext)};base64,{re.escape(b64_prefix)}[^"\']*["\']',
                    f'src="{cdn_url}"',
                    html,
                    count=1,
                )
                succeeded += 1
            else:
                # URL 取得失敗 → img タグを除去
                html = re.sub(
                    rf'<img[^>]*src=["\']data:image/{re.escape(ext)};base64,{re.escape(b64_prefix)}[^"\']*["\'][^>]*/?>',
                    '',
                    html,
                    count=1,
                )
                failed += 1
        except Exception:
            failed += 1

    # 残った Data URI を念のため除去
    html = re.sub(r'<img[^>]+src=["\']data:image/[^"\']{20,}["\'][^>]*/?>', '', html)

    return html, succeeded, failed


# ── 記事投稿 ─────────────────────────────────────────────────────────────────

def publish_article(
    site: dict,
    title: str,
    markdown_str: str,
    blog_id: int,
    published: bool = False,
    scheduled_at: str = "",
    upload_images: bool = False,
    progress_cb=None,
) -> dict:
    """
    Shopify ブログに記事を投稿する。
    upload_images=True のとき Staged Uploads で画像を CDN にアップロードする
    （カスタムアプリに write_files スコープが必要）。
    {"id": int, "handle": str, "published": bool,
     "images_uploaded": int, "images_failed": int, "images_removed": int} を返す。
    """
    from core.exporter import _md_to_html

    # H1 タイトルを除去
    md_body = re.sub(r'^# .+\n?', '', markdown_str, count=1).strip()
    html = _md_to_html(md_body)

    images_uploaded = 0
    images_failed = 0
    images_removed = 0

    if upload_images:
        html, images_uploaded, images_failed = _replace_base64_with_cdn(
            html, markdown_str, site, progress_cb=progress_cb
        )
    else:
        # Data URI を除去（422 回避）
        before = html.count('data:image/')
        html = re.sub(r'<img[^>]+src=["\']data:image/[^"\']{20,}["\'][^>]*/?>', '', html)
        html = re.sub(r'!\[[^\]]*\]\(data:image/[^\)]{20,}\)', '', html)
        images_removed = before - html.count('data:image/')

    article: dict = {
        "title": title,
        "body_html": html,
        "published": published,
    }

    if scheduled_at:
        article["published"] = False
        article["published_at"] = scheduled_at

    r = requests.post(
        f"{_base_url(site)}/blogs/{blog_id}/articles.json",
        headers=_headers(site),
        json={"article": article},
        timeout=60,
    )
    if not r.ok:
        try:
            err = r.json().get("errors") or r.json().get("error") or r.text[:300]
        except Exception:
            err = r.text[:300]
        raise requests.HTTPError(f"{r.status_code}: {err}", response=r)

    data = r.json().get("article", {})

    return {
        "id": data.get("id"),
        "handle": data.get("handle", ""),
        "published": data.get("published", False),
        "images_uploaded": images_uploaded,
        "images_failed": images_failed,
        "images_removed": images_removed,
    }
