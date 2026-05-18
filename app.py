import re
import tempfile
from pathlib import Path

import streamlit as st

from core.assembler import assemble_markdown
from core.exporter import to_shopify_zip, to_wordpress_zip


@st.cache_data(show_spinner=False)
def _wordpress_zip(title: str, md: str) -> bytes:
    return to_wordpress_zip(title, md)


@st.cache_data(show_spinner=False)
def _shopify_zip(title: str, md: str) -> bytes:
    return to_shopify_zip(title, md)


def _strip_images_for_edit(markdown: str) -> tuple[str, dict]:
    placeholders: dict[str, str] = {}
    counter = [0]

    def _replace(m: re.Match) -> str:
        counter[0] += 1
        key = f"IMAGE_{counter[0]}"
        placeholders[key] = m.group(0)
        return f"![{m.group(1)}]({key})"

    stripped = re.sub(r'!\[([^\]]*)\]\(data:image/[^\)]{20,}\)', _replace, markdown)
    return stripped, placeholders


def _extract_section_body(markdown: str, heading: str) -> str:
    """指定した H2 セクションのテキスト本文を返す（画像タグは除去）。"""
    parts = re.split(r'\n## ', '\n' + markdown)
    for part in parts[1:]:
        head, _, body = part.partition('\n')
        if head.strip() == heading.strip():
            return re.sub(r'!\[[^\]]*\]\([^\)]{20,}\)', '', body).strip()[:500]
    return ""


def _replace_section_image(markdown: str, heading: str, data_uri: str) -> str:
    """指定セクションの画像を差し替える（画像なしなら見出し直後に挿入）。"""
    esc = re.escape(heading)
    new_tag = f"![{heading}]({data_uri})"

    # 既存の画像を置き換え
    result, n = re.subn(
        rf'(## {esc}\n+)!\[[^\]]*\]\(data:image/[^\)]+\)',
        rf'\g<1>{new_tag}',
        markdown, count=1,
    )
    if n:
        return result

    # 画像なし → 見出し直後に挿入
    result, n = re.subn(
        rf'(## {esc}\n+)',
        rf'\g<1>{new_tag}\n\n',
        markdown, count=1,
    )
    return result if n else markdown


def _restore_images_after_edit(edited: str, placeholders: dict) -> str:
    for key, original_tag in placeholders.items():
        m = re.match(r'!\[[^\]]*\]\((data:image/[^\)]+)\)', original_tag)
        if not m:
            continue
        data_url = m.group(1)
        edited = re.sub(
            rf'!\[([^\]]*)\]\({re.escape(key)}\)',
            lambda mm, url=data_url: f'![{mm.group(1)}]({url})',
            edited,
        )
    return edited


from core.article_store import (
    delete_article,
    list_articles,
    load_article,
    save_article,
    update_article,
)
from core.text_generator import (
    RECOMMENDED_MODELS,
    SECTION_LENGTHS,
    WRITING_STYLES,
    check_ollama_connection,
    generate_image_prompt,
    generate_outline,
    generate_section,
    list_ollama_models,
    pull_model,
    revise_article,
)

try:
    from core.dalle_generator import DalleGenerator
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

from core.config import (
    delete_openai_key,
    load_openai_key,
    save_openai_key,
    list_wordpress_sites,
    save_wordpress_site,
    delete_wordpress_site,
)
from core.wordpress_client import get_post_types, publish_article, test_connection

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI ブログジェネレーター",
    page_icon="✍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-title { font-size: 2rem; font-weight: 700; margin-bottom: 0.2rem; }
    .article-title { font-size: 1.4rem; font-weight: 700; }
    div[data-testid="stStatusWidget"] { display: none; }
    section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] > div:first-child button > div {
        justify-content: flex-start; text-align: left;
    }
    section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] div:first-child button p {
        overflow: hidden; white-space: nowrap; text-overflow: ellipsis; display: block;
        font-size: 0.78rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ──────────────────────────────────────────────────────────────
for key, default in [
    ("ui_mode", "create"),       # "create" | "edit"
    ("result_markdown", None),
    ("result_title", None),
    ("result_keywords", ""),
    ("generation_done", False),
    ("saved_path", None),
    ("editing_mode", False),
    ("edit_display_md", ""),
    ("edit_image_map", {}),
    ("writing_style", list(WRITING_STYLES.keys())[0]),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")

    if st.session_state.ui_mode == "edit":
        if st.button("✍️ 新規作成", use_container_width=True):
            st.session_state.ui_mode = "create"
            st.session_state.generation_done = False
            st.session_state.result_markdown = None
            st.session_state.result_title = None
            st.session_state.result_keywords = ""
            st.session_state.saved_path = None
            st.session_state.editing_mode = False
            st.rerun()
        st.divider()

    ollama_ok = check_ollama_connection()
    if ollama_ok:
        st.success("Ollama 接続中", icon="✅")
        available_models = list_ollama_models()
        if available_models:
            text_model = st.selectbox("テキストモデル", available_models)
        else:
            st.warning("モデルがありません。下の「モデルを追加」からダウンロードしてください。", icon="⚠️")
            text_model = list(RECOMMENDED_MODELS.keys())[0]
    else:
        st.error("Ollama に接続できません。\nOllama を起動してください。", icon="❌")
        text_model = list(RECOMMENDED_MODELS.keys())[0]

    with st.expander("📥 モデルを追加"):
        already = set(list_ollama_models()) if ollama_ok else set()
        model_choice = st.selectbox(
            "モデルを選択",
            list(RECOMMENDED_MODELS.keys()),
            format_func=lambda m: (
                f"{'✅ ' if m in already else ''}{m}  —  {RECOMMENDED_MODELS[m]}"
            ),
            key="pull_model_select",
        )
        if not ollama_ok:
            st.info("Ollama が起動していないとダウンロードできません。")
        elif model_choice in already:
            st.info(f"{model_choice} はインストール済みです。")
        else:
            if st.button("⬇️ ダウンロード開始", key="pull_btn", use_container_width=True):
                with st.status(f"{model_choice} をダウンロード中...", expanded=True) as dl_status:
                    progress_bar = st.progress(0.0)
                    status_text = st.empty()
                    try:
                        for update in pull_model(model_choice):
                            msg = update.get("status", "")
                            if "total" in update and "completed" in update and update["total"] > 0:
                                pct = update["completed"] / update["total"]
                                progress_bar.progress(min(pct, 1.0))
                            status_text.caption(msg)
                        dl_status.update(label=f"✅ {model_choice} のダウンロード完了", state="complete")
                        st.rerun()
                    except Exception as e:
                        dl_status.update(label="❌ ダウンロード失敗", state="error")
                        st.error(str(e))

    st.divider()

    image_quality = "標準"
    openai_api_key = ""

    with st.expander("🎨 OpenAI 画像生成設定"):
        if not OPENAI_AVAILABLE:
            st.warning("openai パッケージが見つかりません。", icon="⚠️")
        else:
            import os
            _saved_key = load_openai_key() or os.environ.get("OPENAI_API_KEY", "")
            openai_api_key = st.text_input(
                "API キー",
                value=_saved_key,
                type="password",
                placeholder="sk-...",
                help="環境変数 OPENAI_API_KEY でも設定できます",
            )
            _key_col, _del_col = st.columns([3, 1])
            with _key_col:
                if st.button("💾 保存", key="save_key", use_container_width=True,
                             help="入力したキーをこのMacに保存します"):
                    if openai_api_key:
                        save_openai_key(openai_api_key)
                        st.success("保存しました", icon="✅")
                    else:
                        st.warning("キーが入力されていません")
            with _del_col:
                if st.button("🗑️", key="del_key", use_container_width=True,
                             help="保存されたキーを削除します"):
                    delete_openai_key()
                    st.info("削除しました")

            if _saved_key:
                st.caption("✅ 保存済みのキーを使用中")

            image_quality = st.select_slider(
                "品質",
                options=["標準", "高品質"],
                value="標準",
                help="標準: $0.04/枚 / 高品質(HD): $0.08/枚",
            )
            if st.button("🔍 接続テスト", key="test_dalle"):
                if not openai_api_key:
                    st.error("API キーを入力してください。")
                else:
                    with st.spinner("利用可能な画像モデルを確認中..."):
                        from core.dalle_generator import detect_available_model, OPENAI_IMAGE_MODELS
                        found = detect_available_model(openai_api_key)
                        if found:
                            st.success(f"✅ 利用可能モデル: `{found}`")
                        else:
                            st.error(
                                f"❌ 画像生成モデルが見つかりません。\n\n"
                                f"確認済みモデル: {', '.join(OPENAI_IMAGE_MODELS)}\n\n"
                                "OpenAI アカウントで画像生成が有効か確認してください。"
                            )

    # ── WordPress sites ────────────────────────────────────────────────────────
    st.divider()
    with st.expander("🌐 WordPress 設定"):
        _wp_sites = list_wordpress_sites()
        if _wp_sites:
            for _ws in _wp_sites:
                _wc1, _wc2 = st.columns([4, 1])
                with _wc1:
                    st.caption(f"**{_ws['name']}**  \n{_ws['url']}")
                with _wc2:
                    if st.button("🗑️", key=f"wp_del_{_ws['name']}", help="削除"):
                        delete_wordpress_site(_ws["name"])
                        st.rerun()
            st.divider()

        st.caption("サイトを追加")
        _wp_name = st.text_input("サイト名", placeholder="メインサイト", key="wp_add_name")
        _wp_url  = st.text_input("URL", placeholder="https://example.com", key="wp_add_url")
        _wp_user = st.text_input("ユーザー名", key="wp_add_user")
        _wp_pw   = st.text_input(
            "アプリケーションパスワード", type="password",
            placeholder="xxxx xxxx xxxx xxxx xxxx xxxx",
            key="wp_add_pw",
            help="WordPress 管理画面 > ユーザー > プロフィール > アプリケーションパスワード で発行。スペース込みのままペーストしてOKです。",
        )
        if st.button("追加", key="wp_add_btn", use_container_width=True):
            if _wp_name and _wp_url and _wp_user and _wp_pw:
                save_wordpress_site({
                    "name": _wp_name, "url": _wp_url,
                    "username": _wp_user, "app_password": _wp_pw,
                })
                st.success(f"「{_wp_name}」を追加しました", icon="✅")
                st.rerun()
            else:
                st.warning("すべての項目を入力してください")

    # ── Saved articles ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📂 保存済み記事")
    _articles = list_articles()
    if not _articles:
        st.caption("保存された記事はまだありません。")
    else:
        for _art in _articles:
            _date_hint = _art["created"][:10] if _art["created"] else ""
            _c1, _c2 = st.columns([5, 1])
            with _c1:
                if st.button(_art["title"], key=f"load_{_art['filename']}", use_container_width=True,
                             help=_date_hint or None):
                    _data = load_article(_art["path"])
                    st.session_state.result_markdown = _data["markdown"]
                    st.session_state.result_title = _data["title"]
                    st.session_state.result_keywords = _data["keywords"]
                    st.session_state.generation_done = True
                    st.session_state.saved_path = _art["path"]
                    st.session_state.editing_mode = False
                    st.session_state.ui_mode = "edit"
                    st.rerun()
            with _c2:
                if st.button("🗑️", key=f"del_{_art['filename']}", use_container_width=True,
                             help="削除"):
                    delete_article(_art["path"])
                    if st.session_state.saved_path == _art["path"]:
                        st.session_state.saved_path = None
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# CREATE MODE
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.ui_mode == "create":
    st.markdown('<p class="main-title">✍️ AI ブログジェネレーター</p>', unsafe_allow_html=True)
    st.caption("キーワードを入力するだけで、AIがブログ記事（本文＋画像）を自動生成します。")

    # ── Input form ─────────────────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 1])

    with col_left:
        user_title = st.text_input(
            "タイトル",
            placeholder="例：はじめての機械学習入門ガイド（空欄 → AI が自動生成）",
            help="タイトルを決めている場合はここに入力してください。空欄にすると AI がキーワードからタイトルを考えます。",
        )
        keywords = st.text_input(
            "キーワード",
            placeholder="例：Python、機械学習、初心者向け",
            help="記事のテーマとなる単語をカンマ区切りで入力してください。タイトルを入力した場合は省略できます。",
        )

        if not keywords.strip() and not user_title.strip():
            st.caption("※ キーワードまたはタイトルのどちらか一方は必須です。")
        elif not keywords.strip():
            st.caption("✅ タイトルが入力されています。キーワードは省略可能です。")
        elif not user_title.strip():
            st.caption("✅ キーワードをもとに AI がタイトルを自動生成します。")
        else:
            st.caption("✅ タイトルとキーワードの両方が入力されています。")

    with col_right:
        num_sections = st.number_input(
            "セクション数",
            min_value=2, max_value=8, value=3, step=1,
            help="記事の見出し（H2）の数です。目安: 短め=2〜3、標準=4〜5、詳細=6〜8",
        )
        language = st.selectbox("記事の言語", ["日本語", "English"])
        writing_style = st.selectbox(
            "文体",
            list(WRITING_STYLES.keys()),
            index=list(WRITING_STYLES.keys()).index(st.session_state.writing_style),
        )

        LENGTH_OPTIONS = list(SECTION_LENGTHS.keys())
        section_length = st.select_slider(
            "セクションの文字数",
            options=LENGTH_OPTIONS,
            value=LENGTH_OPTIONS[2],
            help="セクション（見出し1つ）あたりのおおよその文字数です。",
        )

        st.write("")
        rich_format = st.toggle(
            "リッチフォーマット",
            value=True,
            help="ON: 太字・箇条書き・引用ブロックを使って読みやすく整形 / OFF: シンプルな段落のみ",
        )
        include_toc = st.toggle(
            "目次を生成する",
            value=False,
            help="ON: 記事の冒頭に目次（各セクションへのリンク）を挿入します。",
        )

    with st.expander("📝 セクションの見出し・画像を指定する（任意）"):
        st.caption("見出しが空欄のセクションは AI が自動生成します。画像プロンプトも空欄なら AI が自動生成します。")
        user_sections: list[str] = []
        user_section_gen_images: list[bool] = []
        user_section_img_prompts: list[str] = []
        for _i in range(int(num_sections)):
            if _i > 0:
                st.divider()
            st.markdown(f"**セクション {_i + 1}**")
            if OPENAI_AVAILABLE:
                _h_col, _img_col = st.columns([3, 1])
                with _h_col:
                    user_sections.append(
                        st.text_input(
                            "見出し",
                            placeholder="空欄 → AI が自動生成",
                            key=f"section_heading_{_i}",
                            label_visibility="visible",
                        )
                    )
                with _img_col:
                    st.write("")
                    _gen = st.checkbox("画像を生成", value=False, key=f"section_gen_img_{_i}")
            else:
                user_sections.append(
                    st.text_input(
                        "見出し",
                        placeholder="空欄 → AI が自動生成",
                        key=f"section_heading_{_i}",
                        label_visibility="visible",
                    )
                )
                _gen = False
            user_section_gen_images.append(_gen)
            if _gen:
                user_section_img_prompts.append(
                    st.text_input(
                        "画像プロンプト（任意・英語）",
                        placeholder="空欄 → AI が自動生成",
                        key=f"section_img_prompt_{_i}",
                        label_visibility="visible",
                    )
                )
            else:
                user_section_img_prompts.append("")

    use_images = any(user_section_gen_images)

    st.divider()

    # ── Generate button ─────────────────────────────────────────────────────────
    has_input = bool(keywords.strip() or user_title.strip())

    generate_clicked = st.button(
        "🚀 ブログを生成する",
        type="primary",
        disabled=not ollama_ok or not has_input,
        use_container_width=True,
    )

    if generate_clicked and has_input:
        st.session_state.generation_done = False
        st.session_state.result_markdown = None
        st.session_state.saved_path = None
        st.session_state.editing_mode = False
        st.session_state.writing_style = writing_style

        with st.status("生成中...", expanded=True) as status:
            try:
                st.write("📋 アウトラインを生成中...")
                outline = generate_outline(
                    keywords, int(num_sections), text_model, language, user_title, user_sections
                )
                title: str = outline["title"]
                sections_list: list[str] = outline["sections"]
                st.write(f"✅ タイトル決定: **{title}**")

                sections_data: list[dict] = []
                for i, section_title in enumerate(sections_list):
                    st.write(f"✏️ セクション [{i + 1}/{len(sections_list)}] 執筆中: {section_title}")
                    content = generate_section(
                        title, section_title, keywords,
                        text_model, language, rich_format, section_length, writing_style
                    )
                    img_prompt = None
                    if use_images and i < len(user_section_gen_images) and user_section_gen_images[i]:
                        custom = user_section_img_prompts[i] if i < len(user_section_img_prompts) else ""
                        img_prompt = custom.strip() if custom.strip() else generate_image_prompt(section_title, content, text_model)
                    sections_data.append(
                        {"heading": section_title, "content": content, "image_prompt": img_prompt, "image_path": None}
                    )

                with tempfile.TemporaryDirectory() as tmpdir:
                    sections_with_images = [s for s in sections_data if s["image_prompt"]]
                    if use_images and sections_with_images:
                        if not openai_api_key:
                            raise ValueError("OpenAI API キーが入力されていません。サイドバーで設定してください。")
                        st.write("🎨 画像を生成中...")
                        img_gen = DalleGenerator(openai_api_key, image_quality)
                        img_count = 0
                        for i, sec in enumerate(sections_data):
                            if not sec["image_prompt"]:
                                continue
                            img_count += 1
                            st.write(f"🖼️ 画像 [{img_count}/{len(sections_with_images)}] 生成中: {sec['heading']}")
                            img_path = Path(tmpdir) / f"img_{i}.png"
                            img_gen.generate(sec["image_prompt"], img_path)
                            sec["image_path"] = img_path

                    st.write("📄 Markdown を組み立て中...")
                    result = assemble_markdown(title, sections_data, include_toc, language)

                st.session_state.result_markdown = result
                st.session_state.result_title = title
                st.session_state.result_keywords = keywords
                st.session_state.generation_done = True
                st.session_state.ui_mode = "edit"
                status.update(label="✅ 生成完了！", state="complete", expanded=False)
                st.rerun()

            except Exception as e:
                status.update(label="❌ エラーが発生しました", state="error")
                st.error(f"エラー詳細: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# EDIT MODE
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.ui_mode == "edit" and st.session_state.result_markdown:

    raw_title = st.session_state.result_title or "blog_post"
    saved_keywords = st.session_state.result_keywords
    slug = raw_title.replace("/", "_").replace(" ", "_")
    md_str = st.session_state.result_markdown

    # ── Header ─────────────────────────────────────────────────────────────────
    st.markdown(f'<p class="article-title">📄 {raw_title}</p>', unsafe_allow_html=True)

    st.divider()

    # ── Preview / Edit / Raw ───────────────────────────────────────────────────
    tab_preview, tab_raw = st.tabs(["プレビュー", "Markdown ソース"])

    with tab_preview:
        if st.session_state.editing_mode:
            edited_md = st.text_area(
                "編集",
                value=st.session_state.edit_display_md,
                height=600,
                label_visibility="collapsed",
                key="edit_area",
            )
            if st.session_state.edit_image_map:
                st.caption(
                    "📷 " + "　".join(
                        f"`{k}` = 画像{i+1}"
                        for i, k in enumerate(st.session_state.edit_image_map)
                    )
                )
            _save_col2, _cancel_col = st.columns(2)
            with _save_col2:
                if st.button("💾 変更を保存", type="primary", use_container_width=True, key="edit_save"):
                    restored = _restore_images_after_edit(edited_md, st.session_state.edit_image_map)
                    st.session_state.result_markdown = restored
                    st.session_state.editing_mode = False
                    if st.session_state.saved_path:
                        update_article(st.session_state.saved_path, restored)
                    st.rerun()
            with _cancel_col:
                if st.button("キャンセル", use_container_width=True, key="edit_cancel"):
                    st.session_state.editing_mode = False
                    st.rerun()
        else:
            if st.button("✏️ 編集", key="edit_btn"):
                stripped, image_map = _strip_images_for_edit(md_str)
                st.session_state.edit_display_md = stripped
                st.session_state.edit_image_map = image_map
                st.session_state.editing_mode = True
                st.rerun()
            st.markdown(md_str)

    with tab_raw:
        st.text_area(
            "コピー用",
            value=md_str,
            height=400,
            label_visibility="collapsed",
        )

    # ── Revision ───────────────────────────────────────────────────────────────
    with st.expander("✏️ AIで記事を修正する"):
        _section_headings = re.findall(r'^## (.+)$', md_str, flags=re.MULTILINE)
        _target_options = ["全体"] + [f"セクション {i+1}：{t}" for i, t in enumerate(_section_headings)]
        _revision_target = st.selectbox("修正対象", _target_options, key="revision_target")
        _section_index = None if _revision_target == "全体" else _target_options.index(_revision_target) - 1

        revision_prompt = st.text_area(
            "修正の指示",
            placeholder="例：もっと具体的な事例を追加してください\n例：簡潔にまとめてください\n例：初心者向けにわかりやすく書き直してください",
            height=100,
            label_visibility="collapsed",
        )
        if st.button("🔄 修正する", disabled=not revision_prompt.strip() or not ollama_ok):
            with st.spinner("修正中..."):
                try:
                    revised = revise_article(
                        md_str, revision_prompt, text_model, language,
                        _section_index, st.session_state.writing_style,
                    )
                    st.session_state.result_markdown = revised
                    if st.session_state.saved_path:
                        update_article(st.session_state.saved_path, revised)
                    st.rerun()
                except Exception as e:
                    st.error(f"修正に失敗しました: {e}")

    # ── Image regeneration ─────────────────────────────────────────────────────
    if OPENAI_AVAILABLE:
        with st.expander("🖼️ 画像を再生成する"):
            import os as _os
            _regen_key = load_openai_key() or _os.environ.get("OPENAI_API_KEY", "")

            if not _regen_key:
                st.info("OpenAI API キーをサイドバーで設定すると画像を再生成できます。")
            else:
                _img_sections = re.findall(r'^## (.+)$', md_str, flags=re.MULTILINE)
                if not _img_sections:
                    st.caption("セクションが見つかりません。")
                else:
                    _has_image = {
                        h: bool(re.search(
                            rf'## {re.escape(h)}\n+!\[[^\]]*\]\(data:image/',
                            md_str,
                        ))
                        for h in _img_sections
                    }

                    _img_target = st.selectbox(
                        "対象セクション",
                        _img_sections,
                        format_func=lambda h: f"{'🖼️' if _has_image[h] else '➕'} {h}",
                        key="img_regen_target",
                    )
                    st.caption("🖼️ = 既存の画像を差し替え　➕ = 新たに画像を追加")

                    _img_prompt_input = st.text_input(
                        "画像プロンプト（任意・英語）",
                        placeholder="空欄 → セクション内容から AI が自動生成",
                        key="img_regen_prompt",
                    )
                    _img_quality = st.select_slider(
                        "品質",
                        options=["標準", "高品質"],
                        value="標準",
                        key="img_regen_quality",
                        help="標準: $0.04/枚 / 高品質(HD): $0.08/枚",
                    )

                    if st.button("🔄 画像を再生成", key="img_regen_btn", type="secondary"):
                        with st.spinner("画像を生成中..."):
                            try:
                                if _img_prompt_input.strip():
                                    _final_prompt = _img_prompt_input.strip()
                                elif ollama_ok:
                                    _body = _extract_section_body(md_str, _img_target)
                                    _final_prompt = generate_image_prompt(_img_target, _body, text_model)
                                else:
                                    st.error("Ollama が起動していないためプロンプトを自動生成できません。プロンプトを直接入力してください。")
                                    st.stop()

                                _img_gen = DalleGenerator(_regen_key, _img_quality)
                                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as _tf:
                                    _tmp_path = Path(_tf.name)
                                try:
                                    _img_gen.generate(_final_prompt, _tmp_path)
                                    from core.assembler import _embed_image
                                    _new_data_uri = _embed_image(_tmp_path)
                                finally:
                                    _tmp_path.unlink(missing_ok=True)

                                _new_md = _replace_section_image(md_str, _img_target, _new_data_uri)
                                st.session_state.result_markdown = _new_md
                                if st.session_state.saved_path:
                                    update_article(st.session_state.saved_path, _new_md)
                                st.rerun()
                            except Exception as e:
                                st.error(f"画像の再生成に失敗しました: {e}")

    # ── Save to disk ───────────────────────────────────────────────────────────
    st.divider()
    _save_col, _status_col = st.columns([1, 3])
    with _save_col:
        if st.button("💾 記事を保存", use_container_width=True, type="secondary"):
            if st.session_state.saved_path:
                update_article(st.session_state.saved_path, md_str)
                _save_msg = "上書き保存しました"
            else:
                _p = save_article(raw_title, md_str, saved_keywords)
                st.session_state.saved_path = _p
                _save_msg = "保存しました"
            with _status_col:
                st.success(_save_msg, icon="✅")
    if st.session_state.saved_path:
        st.caption(f"📁 {st.session_state.saved_path}")

    # ── Download ───────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("⬇️ ダウンロード")
    col_md, col_wp, col_sp = st.columns(3)

    with col_md:
        st.download_button(
            "📄 Markdown",
            data=md_str,
            file_name=f"{slug}.md",
            mime="text/markdown",
            use_container_width=True,
            help="汎用 Markdown ファイル。Hugo や Notion などにも使えます。",
        )
    with col_wp:
        st.download_button(
            "🔵 WordPress ZIP",
            data=_wordpress_zip(raw_title, md_str),
            file_name=f"{slug}_wordpress.zip",
            mime="application/zip",
            use_container_width=True,
            help="post.html + images/ フォルダを含む ZIP。画像をメディアライブラリにアップロードし、post.html の URL を差し替えてから貼り付けてください。",
        )
    with col_sp:
        st.download_button(
            "🟢 Shopify ZIP",
            data=_shopify_zip(raw_title, md_str),
            file_name=f"{slug}_shopify.zip",
            mime="application/zip",
            use_container_width=True,
            help="post.html + images/ フォルダを含む ZIP。画像を Shopify ファイルにアップロードし、post.html の URL を差し替えてから「HTML を表示」に貼り付けてください。",
        )

    # ── WordPress publish ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("🌐 WordPress に投稿")

    _wp_sites = list_wordpress_sites()
    if not _wp_sites:
        st.info("サイドバーの「WordPress 設定」からサイトを登録してください。", icon="ℹ️")
    else:
        _wp_site_names = [s["name"] for s in _wp_sites]
        _wp_sel_col, _wp_test_col = st.columns([4, 1])
        with _wp_sel_col:
            _wp_selected_name = st.selectbox(
                "投稿先サイト", _wp_site_names, key="wp_site_select", label_visibility="collapsed"
            )
        _wp_site = next(s for s in _wp_sites if s["name"] == _wp_selected_name)
        with _wp_test_col:
            if st.button("接続テスト", key="wp_test_btn", use_container_width=True):
                with st.spinner("確認中..."):
                    _ok, _msg = test_connection(_wp_site)
                    (st.success if _ok else st.error)(_msg, icon="✅" if _ok else "❌")

        _pt_cache_key = f"wp_types_{_wp_selected_name}"
        if _pt_cache_key not in st.session_state:
            st.session_state[_pt_cache_key] = {"posts": "投稿"}

        _wp_type_col, _wp_fetch_col, _wp_status_col = st.columns([3, 1, 2])
        with _wp_fetch_col:
            st.markdown('<div style="height:1.7rem"></div>', unsafe_allow_html=True)
            if st.button("取得", key="wp_fetch_types", use_container_width=True,
                         help="サイトの投稿タイプ一覧を取得します"):
                with st.spinner("取得中..."):
                    try:
                        st.session_state[_pt_cache_key] = get_post_types(_wp_site)
                    except Exception as _e:
                        st.error(f"取得失敗: {_e}")
        with _wp_type_col:
            _available_types = st.session_state[_pt_cache_key]
            _wp_rest_base = st.selectbox(
                "投稿タイプ",
                options=list(_available_types.keys()),
                format_func=lambda k: f"{_available_types[k]}（{k}）",
                key="wp_post_type_select",
            )
        with _wp_status_col:
            _status_map = {
                "下書き": "draft",
                "公開": "publish",
                "レビュー待ち": "pending",
                "非公開": "private",
            }
            _wp_status = _status_map[st.selectbox(
                "ステータス", list(_status_map.keys()), key="wp_status_select"
            )]

        _wp_use_blocks = st.radio(
            "エディタ形式",
            ["クラシック（HTML）", "ブロック（Gutenberg）"],
            horizontal=True,
            key="wp_editor_format",
        ) == "ブロック（Gutenberg）"

        if st.button("📤 WordPress に投稿する", type="primary", key="wp_publish_btn", use_container_width=True):
            with st.spinner("投稿中... 画像をアップロードしています"):
                try:
                    _result = publish_article(_wp_site, raw_title, md_str, _wp_rest_base, _wp_status,
                                              use_blocks=_wp_use_blocks)
                    _label = {v: k for k, v in _status_map.items()}.get(_result["status"], _result["status"])
                    st.success(f"投稿しました！（{_label}）", icon="✅")
                    if _result["link"]:
                        st.markdown(f"[投稿を確認する →]({_result['link']})")
                except Exception as _e:
                    st.error(f"投稿に失敗しました: {_e}")
