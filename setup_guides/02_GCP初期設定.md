---
date: 2026-04-21
type: セットアップ手順書
target: 木原 平
所要時間: 約15分
---

# 02. Google Cloud 初期設定（サービスアカウント作成）

## 前提
- 木原さんのGoogleアカウント（info@futurebright.co.jp 推奨）
- クレジットカード登録済み（GCP無料枠内で運用可能だが、サインアップ時に必須）

---

## STEP 1: gcloud CLI インストール（5分）

### 1-1. Homebrewで一発インストール

ターミナルで実行：

```bash
brew install --cask google-cloud-sdk
```

### 1-2. PATH通し（zshrc追記）

```bash
echo "source $(brew --prefix)/share/google-cloud-sdk/path.zsh.inc" >> ~/.zshrc
echo "source $(brew --prefix)/share/google-cloud-sdk/completion.zsh.inc" >> ~/.zshrc
source ~/.zshrc
```

### 1-3. 確認

```bash
gcloud --version
```

→ `Google Cloud SDK 5XX.0.0` 等が表示されればOK

---

## STEP 2: Google認証（2分）

```bash
gcloud auth login
```

→ ブラウザが自動で開く → **info@futurebright.co.jp** でログイン →「許可」

完了後、ターミナルに `You are now logged in as [info@futurebright.co.jp]` と表示。

---

## STEP 3: プロジェクト作成（3分）

### 3-1. プロジェクト作成

```bash
gcloud projects create futurebright-bots --name="FutureBright Bots"
```

プロジェクトID：**futurebright-bots**（以降これを使います）

### 3-2. プロジェクト設定

```bash
gcloud config set project futurebright-bots
```

### 3-3. 課金アカウント紐付け（GCPコンソールで）

🔗 https://console.cloud.google.com/billing

- 「課金アカウントのリンク」→「futurebright-bots」に紐付け
- クレジットカード未登録ならここで登録（無料枠内のため課金発生しない想定）

---

## STEP 4: Drive API 有効化（1分）

```bash
gcloud services enable drive.googleapis.com
```

→ `Operation ... finished successfully.` が出ればOK

---

## STEP 5: サービスアカウント作成（3分）

### 5-1. サービスアカウント作成

```bash
gcloud iam service-accounts create furulead-bot \
  --display-name="ふるりーどSPEED Bot"
```

### 5-2. JSONキー発行

```bash
gcloud iam service-accounts keys create ~/futurebright-sa-key.json \
  --iam-account=furulead-bot@futurebright-bots.iam.gserviceaccount.com
```

→ `~/futurebright-sa-key.json` にキーファイルが保存される

### 5-3. サービスアカウントのメール確認

```bash
echo "furulead-bot@futurebright-bots.iam.gserviceaccount.com"
```

📋 **このメールアドレスをコピーして控える**（STEP 03 で使う）

---

## STEP 6: .env に反映（1分）

ターミナルで実行（パスは自動展開されます）：

```bash
cd /Users/kiharataira/projects/claude_taira/CDO_tech/ai_agents/furulead_speed_bot

# .env がまだなければ作成
[ ! -f .env ] && cp .env.example .env

# GOOGLE_APPLICATION_CREDENTIALS 行を書き換え
sed -i '' "s|GOOGLE_APPLICATION_CREDENTIALS=.*|GOOGLE_APPLICATION_CREDENTIALS=$HOME/futurebright-sa-key.json|" .env
```

---

## 🎁 完了時：CDOへ共有

- サービスアカウントのメール：
  `furulead-bot@futurebright-bots.iam.gserviceaccount.com`
- JSONキーのパス：`~/futurebright-sa-key.json`

→ 「GCP設定完了」と伝えてください。

---

## セキュリティ注意

- `~/futurebright-sa-key.json` は**絶対にgitにコミットしない**（`.gitignore`設定済み）
- 他人に共有しない
- 紛失時は `gcloud iam service-accounts keys list` で確認し、不要なキーは `keys delete` で削除

---

## トラブルシュート

| 症状 | 対処 |
|---|---|
| `brew` コマンドが無い | https://brew.sh/ からHomebrewをインストール |
| `gcloud auth login` でブラウザ開かない | `gcloud auth login --no-launch-browser` でURL手動コピー |
| 課金アカウント未設定でAPI有効化エラー | STEP 3-3 の課金アカウント紐付けを先に完了 |
| プロジェクト名が重複 | `-001` 等サフィックス追加（例：`futurebright-bots-001`） |

---

**次のステップ**: `03_GDrive初期設定.md` に進んでください。
