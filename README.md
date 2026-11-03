# AI Blog Generator

キーワードやタイトルを入れると、AI がブログ記事（見出し・本文・画像）を生成し、そのまま WordPress / Shopify に投稿したり、Markdown・入稿用 ZIP で書き出したりできるデスクトップ向けアプリです。中身は Python / Streamlit で、ブラウザで操作します（Mac / Windows 対応）。

> 現在のバージョンはリポジトリ直下の [`VERSION`](VERSION) を参照してください。

---

## 主な機能

| 機能 | 内容 |
| --- | --- |
| 記事の自動生成 | アウトライン（タイトル・H2 見出し）→ 各セクション本文の順に AI が執筆 |
| テキスト生成エンジン | **OpenAI（`gpt-4o-mini`）** または **Ollama（ローカル LLM）** を切り替え。Windows では OpenAI のみ |
| 画像生成 | セクションごとに OpenAI の画像モデル（`dall-e-3` / `gpt-image-1` を自動判別）で画像を生成し、見出しの直後に配置。プロンプトは自分で書くか AI に任せる |
| 生成オプション | セクション数（2〜8）、言語（日本語 / English）、文体（です・ます調、だ・である調、カジュアル など）、セクションの文字数、リッチフォーマット（太字・箇条書き・引用など）、目次の有無、追加指示 |
| 記事の修正 | AI に指示して記事を書き直す／手動で Markdown を編集する／特定セクションの画像だけ再生成・追加する |
| 記事の保存 | 生成した記事を `articles/` フォルダに Markdown として保存し、サイドバーから呼び出し・削除 |
| ダウンロード | Markdown／WordPress 用 ZIP／Shopify 用 ZIP（どちらも `post.html` + `images/` フォルダ） |
| WordPress へ直接投稿 | REST API とアプリケーションパスワードで投稿。画像はメディアライブラリへ自動アップロード。投稿タイプ・公開状態・予約投稿・ブロック（Gutenberg）／クラシック形式を選択可能。複数サイトを登録できる |
| Shopify へ直接投稿 | Admin API（カスタムアプリのアクセストークン）でブログ記事を投稿。公開／下書き、予約投稿、画像の Shopify CDN へのアップロード（`write_files` スコープが必要）に対応。複数ストアを登録できる |
| アプリ内アップデート | サイドバーの「アップデートを確認」で GitHub の最新リリースを取得し、アプリのファイルを上書き更新 |

## 使い方の流れ

1. アプリを起動すると、ブラウザで `http://localhost:8501` が開きます。
2. サイドバーで準備をします。
   - **🔑 OpenAI API キー**：入力して「保存」。テキスト生成（OpenAI 選択時）と画像生成の両方で使います。環境変数 `OPENAI_API_KEY` でも設定できます。
   - **🤖 テキスト生成**：OpenAI か Ollama を選択。Ollama の場合は使うモデルを選び、未取得なら推奨モデル（`gemma2:9b` など）をここからダウンロードできます。
   - **🎨 画像生成設定**：品質（標準／高品質）を選択。
   - 投稿したい場合は **🌐 WordPress 設定** / **🛍️ Shopify 設定** でサイトを登録します。
3. メイン画面で「タイトル」または「キーワード」（どちらか一方は必須）と各種オプションを入力します。セクションごとに見出しを指定したり、「画像を生成」にチェックを入れたりできます（空欄は AI が自動で決めます）。
4. **🚀 ブログを生成する** を押すと、アウトライン → 本文 → 画像の順に生成され、編集画面に切り替わります。
5. 編集画面でプレビュー／Markdown ソースを確認し、必要に応じて「AI で記事を修正する」「画像を再生成する」「手動で編集する」を使います。**💾 記事を保存** で `articles/` に保存されます。
6. **エクスポート** から次のどれかを選びます。
   - ダウンロード（Markdown / WordPress ZIP / Shopify ZIP）。ZIP の `post.html` 冒頭のコメントに入稿手順が書いてあります。
   - WordPress に投稿
   - Shopify に投稿

### 保存される場所

アプリのフォルダ（下記「インストール」参照）に次のファイルが作られます。どちらも `.gitignore` 済みで、アプリ内アップデートでも上書きされません。

- `config.json` … OpenAI API キー、WordPress のアプリケーションパスワード、Shopify のアクセストークンなど。**暗号化されずにそのまま保存されます**。
- `articles/` … 保存した記事（先頭に title / keywords / created のフロントマター付き Markdown。画像は base64 で埋め込み）

---

## インストール（利用者向け）

[Releases](https://github.com/yama203/blog_generator/releases) の最新版から、OS に合ったファイルをダウンロードします。Python を自分で入れる必要はありません（初回起動時に [uv](https://github.com/astral-sh/uv) が Python 3.12 と必要なパッケージを用意します）。初回セットアップにはインターネット接続が必要で、5〜10 分ほどかかることがあります。

### Mac（`AI Blog Generator.zip`）

1. ZIP を展開して `AI Blog Generator.app` を「アプリケーション」など好きな場所に置きます。
2. 初回は右クリック →「開く」→「開く」で起動します（署名されていないアプリのため）。
3. 初回起動時はダイアログが出てターミナルが開き、Python と必要なパッケージがインストールされます。完了したらもう一度 `.app` をダブルクリックします。
4. 起動するとブラウザでアプリが開きます。

補足：

- 動作要件は macOS 12 以上です。Apple Silicon / Intel の両方に対応しています（両方の uv を `.app` に同梱）。
- **起動時に Ollama がインストールされているかを確認し、入っていないと案内ダイアログを出して終了します**。OpenAI だけを使う場合でも、現状は Ollama のインストールが必要です（[ollama.com](https://ollama.com) から入手）。Ollama が起動していなければ自動で起動します。
- アプリの本体ファイルは `.app` の中に同梱されており、起動のたびに `~/Documents/AI Blog Generator` へ同期されます（`config.json` と `articles/` は同期対象外なので消えません）。設定と記事はこのフォルダにあります。
- 起動ログは `/tmp/ai_blog_generator.log` に出力されます。
- 注意（コードから読み取った推測）：`.app` は起動のたびに同梱ファイルで `~/Documents/AI Blog Generator` を上書きするため、アプリ内アップデートで更新しても次回起動時に `.app` に入っている版へ戻る可能性があります。確実に更新するには Releases から新しい `.app` を入れ直してください。

### Windows（`AI Blog Generator Setup x.y.z.exe`）

1. インストーラーを実行します。管理者権限は不要で、`%LOCALAPPDATA%\AI Blog Generator` にインストールされます（インストール先は選べません）。
2. スタートメニュー（任意でデスクトップ）のショートカット、またはインストール完了画面から起動します。
3. 初回起動時はコンソール画面で Python と必要なパッケージのセットアップが行われます。Python 3.12 が PC に入っていればそれを使い、なければ uv でインストールします。
4. 数秒後にブラウザでアプリが開きます。コンソール画面を閉じるとアプリが終了します。

補足：

- **Windows 版のテキスト生成は OpenAI のみ**です（Ollama には対応していません）。OpenAI API キーが必須です。
- アンインストールすると `.venv` と `articles/`（保存した記事）も削除されます。

---

## 開発環境での起動

Python 3.12 を想定しています（セットアップスクリプト・ランチャーがすべて 3.12 を使うため）。

### pip を使う場合

```bash
python3.12 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

### uv を使う場合

`setup.sh` は uv で Python 3.12 の用意・`.venv` の作成・パッケージのインストールをまとめて行います（uv は第 1 引数、プロジェクト直下の `.uv`、PATH の順で探します）。

```bash
bash setup.sh
```

そのあと Mac では `launcher/start_mac.command` をダブルクリックするか、`.venv` を有効にして `streamlit run app.py` で起動できます。Windows では `launcher/start_windows.bat` が `start_windows.ps1` を呼び出し、初回セットアップから起動までを行います。

### Ollama を使う場合

[Ollama](https://ollama.com) をインストールして起動しておきます。アプリは `http://localhost:11434` に接続します。モデルはアプリのサイドバーからダウンロードできます。

### 主なファイル構成

```
app.py                  Streamlit の画面（生成・編集・投稿・アップデート）
core/
  text_generator.py     アウトライン・本文・画像プロンプト生成、記事修正（Ollama / OpenAI）
  dalle_generator.py    OpenAI 画像生成（dall-e-3 / gpt-image-1）
  assembler.py          生成結果を Markdown に組み立て（画像は base64 で埋め込み）
  exporter.py           Markdown → HTML / Gutenberg ブロック変換、WordPress・Shopify 用 ZIP 作成
  wordpress_client.py   WordPress REST API への投稿
  shopify_client.py     Shopify Admin API（REST / GraphQL）への投稿・画像アップロード
  article_store.py      articles/ への記事の保存・読み込み
  config.py             config.json への設定保存
  updater.py            GitHub Releases を使ったアプリ内アップデート
launcher/               Mac / Windows 用の起動スクリプト
installer/installer.iss Windows インストーラー（Inno Setup）の定義
create_app.sh           Mac 用 .app バンドルの作成
setup.sh                uv による開発環境セットアップ
generate_icon.py        アプリアイコン（.icns / .ico）の生成
VERSION                 アプリのバージョン番号
claude.md               開発初期の構想メモ
```

> `claude.md` は開発初期の構想メモで、ローカルの画像生成（Diffusers / Flux など）を前提にしています。現在のコードでは画像生成は OpenAI の API を使っており、ローカル画像生成は実装されていません。

---

## リリースの仕組み

`.github/workflows/release.yml` が、`v` で始まるタグの push をきっかけに動きます。

1. **build-mac**（macOS）… `create_app.sh` で `AI Blog Generator.app` を作り、ZIP にする。
2. **build-windows**（Windows）… `generate_icon.py --ico` でアイコンを作り、uv（x64）をダウンロードし、Inno Setup で `installer/installer.iss` をビルドしてインストーラー（`.exe`）を作る。インストーラーのバージョンは `VERSION` から取る。
3. **release**（Ubuntu）… 上の 2 つの成果物を添付して GitHub Release を作成する。リリース名は `v<VERSION の値>`、リリースノートは GitHub の自動生成。

### `VERSION` の役割

- インストーラーのバージョンとリリース名に使われます。
- アプリ内では、`VERSION`（現在の版）と GitHub の最新リリースのタグ名（先頭の `v` を除いたもの）を比べて、アップデートの有無を判断します。
- アップデートを実行すると、そのタグのソース ZIP をダウンロードしてアプリのファイルを上書きし、最後に `VERSION` を書き換えます。`config.json`・`articles/`・`.venv/`・`launcher/` などは上書きしません。`requirements.txt` が変わっていればパッケージも入れ直します。

### リリース手順（コードから読み取った推測）

ワークフローの作りから、次の手順でリリースしていると考えられます（手順そのものはリポジトリに書かれていません）。

1. `VERSION` の番号を上げてコミットし、main に push する。
2. 同じ番号のタグ（例：`VERSION` が `1.0.25` なら `v1.0.25`）を作って push する。

```bash
git tag v1.0.25
```

```bash
git push origin v1.0.25
```

`VERSION` とタグの番号がずれると、リリース名とタグ名が食い違い、アプリ内のアップデート判定もおかしくなる（更新後も古い番号と比べ続けるなど）ので注意してください。
