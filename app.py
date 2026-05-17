import tempfile
from pathlib import Path

import streamlit as st

from core.assembler import assemble_markdown
from core.exporter import to_shopify_csv, to_shopify_html, to_wordpress_html
from core.text_generator import (
    RECOMMENDED_MODELS,
    check_ollama_connection,
    generate_image_prompt,
    generate_outline,
    generate_section,
    list_ollama_models,
    pull_model,
)

try:
    from core.dalle_generator import DalleGenerator
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

from core.config import delete_openai_key, load_openai_key, save_openai_key

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
    div[data-testid="stStatusWidget"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ──────────────────────────────────────────────────────────────
for key, default in [
    ("result_markdown", None),
    ("result_title", None),
    ("result_keywords", ""),
    ("generation_done", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Title ──────────────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">✍️ AI ブログジェネレーター</p>', unsafe_allow_html=True)
st.caption("キーワードを入力するだけで、AIがブログ記事（本文＋画像）を自動生成します。")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")

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

    # ── Model management ───────────────────────────────────────────────────────
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

    use_images = st.toggle("画像を生成する", value=False)

    image_quality = "標準"
    openai_api_key = ""

    if use_images:
        if not OPENAI_AVAILABLE:
            st.warning("openai パッケージが見つかりません。", icon="⚠️")
            use_images = False
        else:
            import os
            _saved_key = load_openai_key() or os.environ.get("OPENAI_API_KEY", "")
            openai_api_key = st.text_input(
                "OpenAI API キー",
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

    st.divider()
    if use_images:
        st.caption("💡 **料金目安**\n\n- 標準: $0.04/枚\n- 高品質(HD): $0.08/枚\n- 画像3枚の記事: $0.12〜$0.24")

# ── Input form ─────────────────────────────────────────────────────────────────
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

    # Dynamic validation hint
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

    from core.text_generator import SECTION_LENGTHS
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

with st.expander("📝 セクションの見出しを指定する（任意）"):
    st.caption("空欄のセクションは AI が自動で見出しを生成します。")
    user_sections: list[str] = []
    for _i in range(int(num_sections)):
        user_sections.append(
            st.text_input(
                f"セクション {_i + 1}",
                placeholder="空欄 → AI が自動生成",
                key=f"section_heading_{_i}",
                label_visibility="visible",
            )
        )

st.divider()

# ── Generate ───────────────────────────────────────────────────────────────────
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

    with st.status("生成中...", expanded=True) as status:
        try:
            # 1. Outline
            st.write("📋 アウトラインを生成中...")
            outline = generate_outline(
                keywords, int(num_sections), text_model, language, user_title, user_sections
            )
            title: str = outline["title"]
            sections_list: list[str] = outline["sections"]
            st.write(f"✅ タイトル決定: **{title}**")

            # 2. Section content (+ image prompts)
            sections_data: list[dict] = []
            for i, section_title in enumerate(sections_list):
                st.write(f"✏️ セクション [{i + 1}/{len(sections_list)}] 執筆中: {section_title}")
                content = generate_section(
                    title, section_title, keywords,
                    text_model, language, rich_format, section_length
                )
                img_prompt = None
                if use_images:
                    img_prompt = generate_image_prompt(section_title, content, text_model)
                sections_data.append(
                    {"heading": section_title, "content": content, "image_prompt": img_prompt, "image_path": None}
                )

            # 3. Image generation
            with tempfile.TemporaryDirectory() as tmpdir:
                if use_images:
                    if not openai_api_key:
                        raise ValueError("OpenAI API キーが入力されていません。サイドバーで設定してください。")
                    st.write("🎨 画像を生成中...")
                    img_gen = DalleGenerator(openai_api_key, image_quality)
                    for i, sec in enumerate(sections_data):
                        st.write(f"🖼️ 画像 [{i + 1}/{len(sections_data)}] 生成中...")
                        img_path = Path(tmpdir) / f"img_{i}.png"
                        img_gen.generate(sec["image_prompt"], img_path)
                        sec["image_path"] = img_path

                # 5. Assemble
                st.write("📄 Markdown を組み立て中...")
                result = assemble_markdown(title, sections_data, include_toc, language)

            st.session_state.result_markdown = result
            st.session_state.result_title = title
            st.session_state.result_keywords = keywords
            st.session_state.generation_done = True
            status.update(label="✅ 生成完了！", state="complete", expanded=False)

        except Exception as e:
            status.update(label="❌ エラーが発生しました", state="error")
            st.error(f"エラー詳細: {e}")

# ── Results ────────────────────────────────────────────────────────────────────
if st.session_state.generation_done and st.session_state.result_markdown:
    st.divider()

    raw_title = st.session_state.result_title or "blog_post"
    saved_keywords = st.session_state.result_keywords
    slug = raw_title.replace("/", "_").replace(" ", "_")
    md_str = st.session_state.result_markdown

    st.subheader("💾 ダウンロード")
    col_md, col_wp, col_sp_html, col_sp_csv = st.columns(4)

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
        wp_html = to_wordpress_html(raw_title, md_str)
        st.download_button(
            "🔵 WordPress HTML",
            data=wp_html,
            file_name=f"{slug}_wordpress.html",
            mime="text/html",
            use_container_width=True,
            help="WordPress のブロックエディター（コードエディター）またはクラシックエディター（テキストタブ）に貼り付けて使います。",
        )

    with col_sp_html:
        sp_html = to_shopify_html(raw_title, md_str)
        st.download_button(
            "🟢 Shopify HTML",
            data=sp_html,
            file_name=f"{slug}_shopify.html",
            mime="text/html",
            use_container_width=True,
            help="Shopify 管理画面 > ブログ記事 > コンテンツ欄の「HTML を表示」に貼り付けて使います。",
        )

    with col_sp_csv:
        sp_csv = to_shopify_csv(raw_title, md_str, tags=saved_keywords)
        st.download_button(
            "🟢 Shopify CSV",
            data=sp_csv,
            file_name=f"{slug}_shopify.csv",
            mime="text/csv",
            use_container_width=True,
            help="Matrixify アプリを使って Shopify に一括インポートできます。複数記事をまとめて入稿したい場合に便利です。",
        )

    st.divider()
    tab_preview, tab_raw = st.tabs(["プレビュー", "Markdown ソース"])

    with tab_preview:
        st.markdown(md_str)

    with tab_raw:
        st.text_area(
            "コピー用",
            value=md_str,
            height=400,
            label_visibility="collapsed",
        )
