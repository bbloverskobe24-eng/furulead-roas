---
date: 2026-04-21
type: セットアップ手順書
target: 木原 平
所要時間: 約3分
---

# 03. Google Drive 配信フォルダ設定

## 前提
- `02_GCP初期設定.md` 完了済み
- サービスアカウントのメール：`furulead-bot@futurebright-bots.iam.gserviceaccount.com`

---

## STEP 1: 配信用フォルダ作成（1分）

### 1-1. Google Driveへログイン

🔗 https://drive.google.com/

**info@futurebright.co.jp** でログイン。

### 1-2. 新規フォルダ作成

- 左上「**＋ 新規**」→「**フォルダ**」
- フォルダ名：**ふるりーどSPEED_配信**
- 「作成」クリック

### 1-3. 推奨：親フォルダに移動

マイドライブ直下でもOKですが、整理のため以下を推奨：

```
マイドライブ/
  └── FutureBright_業務/
       └── ふるりーどSPEED_配信/   ← ここに移動
```

---

## STEP 2: サービスアカウントに権限付与（1分）

### 2-1. フォルダを右クリック → 「共有」

### 2-2. 「ユーザーやグループを追加」欄に貼り付け

```
furulead-bot@futurebright-bots.iam.gserviceaccount.com
```

→ Google上に該当ユーザーが見つからない風の警告が出ますが、**「とにかく送信」または「追加」** を選択

### 2-3. 権限を「**編集者**」に設定

### 2-4. 「通知」チェックを**OFF**にして「**送信**」または「**共有**」

---

## STEP 3: フォルダID取得（30秒）

### 3-1. フォルダをダブルクリックで開く

### 3-2. URL から ID を抽出

ブラウザのアドレスバー：

```
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456
                                         ↑ この部分がフォルダID
```

📋 **コピーして控える**

---

## STEP 4: .env に反映（30秒）

ターミナルで実行：

```bash
cd /Users/kiharataira/projects/claude_taira/CDO_tech/ai_agents/furulead_speed_bot

# GDRIVE_FOLDER_ID を書き換え（"1AbC..."の部分を実IDに置き換えて実行）
FOLDER_ID="貼り付けたフォルダID"
sed -i '' "s|GDRIVE_FOLDER_ID=.*|GDRIVE_FOLDER_ID=$FOLDER_ID|" .env
```

---

## STEP 5: 動作確認（30秒）

```bash
cd /Users/kiharataira/projects/claude_taira/CDO_tech/ai_agents/furulead_speed_bot
source .env && python3 -c "
from app.uploader import upload
# テスト用PDFを適当なPDFでアップロード
import glob
pdfs = glob.glob('data/generated_pdfs/*.pdf')
if pdfs:
    url = upload(pdfs[0])
    print('✅ アップロード成功:', url)
else:
    print('テスト用PDFがありません。先に test_flow.py を実行してください')
"
```

→ `✅ アップロード成功: https://drive.google.com/file/d/xxx/view` が表示されればOK

---

## 🎁 完了時：CDOへ共有

- GDrive配信フォルダ：設定完了
- アップロードテスト：成功

→ 「GDrive設定完了」と伝えてください。
これで本番デプロイ可能な状態です。

---

## トラブルシュート

| 症状 | 対処 |
|---|---|
| 権限付与エラー「このドメインは許可されていません」 | Google Workspaceの外部共有設定を確認（管理者のみ変更可） |
| アップロードで`403 forbidden` | サービスアカウントにフォルダの「編集者」権限付与を再確認 |
| アップロードで`ModuleNotFoundError` | `pip install -r CDO_tech/ai_agents/requirements.txt` |

---

## 3セットアップ完了後のチェックリスト

以下が揃っていれば本番デプロイ可能です：

- [ ] LINE_CHANNEL_SECRET 設定済み
- [ ] LINE_CHANNEL_ACCESS_TOKEN 設定済み
- [ ] GOOGLE_APPLICATION_CREDENTIALS 設定済み（JSONキー配置済み）
- [ ] GDRIVE_FOLDER_ID 設定済み
- [ ] CHATWORK_API_TOKEN 設定済み（既存の木原さんトークン流用可）
- [ ] アップロードテスト成功

**すべて完了したら、CDO（Claude）に「3手順完了」とお伝えください。**
Cloud Runへ1コマンドで本番デプロイします。
