# クラウドデプロイ手順（簡易版）

ROAS分析画面を**隅田さん・社員**が外部からアクセスできるようにする手順。

3つの選択肢を提示。**最速：A → 本番運用：B** を推奨。

---

## 🅰️ ngrok（即時公開・5分・Mac起動が必要）

**いつ使う**: 5/1の商談直前で時間がない / その場限りで試す

### セットアップ（初回のみ）

```bash
# 1. ngrok インストール
brew install ngrok

# 2. ngrok 認証トークン設定（無料アカウント作成）
# https://dashboard.ngrok.com/get-started/your-authtoken でトークン取得
ngrok config add-authtoken <YOUR_TOKEN>
```

### 起動

```bash
cd CDO_tech/ai_agents/furulead_speed_bot
bash scripts/start_ngrok.sh
```

ターミナルに表示される `Forwarding https://xxxx-xxxx.ngrok-free.app -> http://localhost:8501` の URL を隅田さんに共有。

### 注意

- **Mac起動中のみアクセス可能**（スリープすると切れる）
- 無料プランはURLが起動毎に変わる
- 共有パスワード（ADMIN_PASS）が `.env` に設定されていること

---

## 🅱️ Streamlit Community Cloud（無料・24/7・推奨）

**いつ使う**: 隅田さんが安定的にアクセスする本番運用

### 前提

- GitHub アカウント（無料）
- Streamlit Cloudアカウント（GitHub連携で即作成）

### Step 1: GitHub にコードをpush

```bash
cd CDO_tech/ai_agents/furulead_speed_bot

# 初回のみ
git init
git remote add origin https://github.com/<your-account>/furulead-roas.git

git add .
# ※.env と .streamlit/secrets.toml は .gitignore で除外済み
git commit -m "init: ROAS分析レポート Phase 1"
git push -u origin main
```

> ⚠️ **無料Streamlit Cloudは Public Repo のみ対応**。コードに秘密情報がないことを確認（`.env` / `secrets.toml` は除外済み、確認OK）。
> 完全プライベート運用したい場合はStreamlit Cloud有料プラン（月$20）か、Render/Railwayへ。

### Step 2: Streamlit Cloud でデプロイ

1. https://share.streamlit.io/ にGitHubでログイン
2. 「New app」→ リポジトリ・ブランチ・`streamlit_app.py` を選択
3. 「Advanced settings」→ Python 3.11、Secretsに `.streamlit/secrets.toml.example` の中身をコピペして値を埋める：

```toml
ANTHROPIC_API_KEY = "sk-ant-xxx"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ADMIN_PASS = "furulead_2026_xxx"
```

4. 「Deploy」クリック → 数分でビルド完了
5. URLは `https://<app-name>.streamlit.app` 形式で発行される

### Step 3: 隅田さんへ共有

- アプリURL
- ADMIN_PASS（共有パスワード）

---

## 🅲️ Cloud Run（既存 Dockerfile 流用・本格運用）

**いつ使う**: GCP環境を本格的に使う、SLAが必要

### 概要

```bash
cd CDO_tech/ai_agents/furulead_speed_bot

# 1. gcloud auth（初回のみ）
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>

# 2. Cloud Run用Dockerfile作成（後述）

# 3. デプロイ
gcloud run deploy furulead-roas \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars ANTHROPIC_API_KEY=sk-ant-xxx,ADMIN_PASS=furulead_2026_xxx
```

> 既存 `Dockerfile` は FastAPI 用（uvicorn）になっているので、Streamlit用に置き換え必要。
> 詳細手順はPhase 2 で対応予定。

---

## 🔐 セキュリティチェックリスト

デプロイ前に必ず確認：

- [ ] `.env` がリポジトリに**含まれていない**（git status で確認）
- [ ] `.streamlit/secrets.toml` がリポジトリに**含まれていない**
- [ ] `data/sessions.db` / `data/generated_reports/` がリポジトリに**含まれていない**
- [ ] `ADMIN_PASS` を強固なパスワードに設定（推測されないもの）
- [ ] `ANTHROPIC_API_KEY` のレート制限を確認（不正利用防止）

---

## 🆘 トラブルシューティング

### Streamlit Cloudで「ANTHROPIC_API_KEY not loaded」

→ Streamlit Cloud の Settings → Secrets で正しく設定されているか確認。`secrets.toml.example` のフォーマットに沿っているか確認。

### 「Module not found: anthropic」

→ `requirements.txt` がリポジトリルートに置かれているか確認。Streamlit Cloud は自動で `pip install -r requirements.txt` を実行。

### ngrok URL が頻繁に変わる

→ ngrok 有料プラン（月$8）で固定サブドメイン取得可能。または Streamlit Cloud に移行を推奨。

---

最終更新: 2026-04-29
