---
date: 2026-04-21
type: セットアップ手順書
target: 木原 平
所要時間: 約10分
---

# 01. LINE公式アカウント「ふるりーどSPEED」開設手順

## 前提
- 木原さんの個人LINEアカウント（スマホで電話認証済）
- PCブラウザ（Chrome推奨）
- SMS受信可能な携帯電話

---

## STEP 1: LINE Business ID ログイン（2分）

### 1-1. ログイン画面へ

🔗 **URL**: https://account.line.biz/login

「LINEアカウントでログイン」をクリック。

### 1-2. QRコード認証

表示されたQRコードを **スマホのLINEアプリ** で読み取り。
- スマホ側で「ログイン許可」タップ
- 6桁の確認番号をPCに入力

### 1-3. 業務情報入力（初回のみ）
- 名前：木原 平
- 会社名：FutureBright株式会社
- 業種：情報通信・IT
- 国：日本
- メール：info@futurebright.co.jp

**「次へ」→「同意して登録」**

---

## STEP 2: 公式アカウント作成（3分）

ログイン後、**「LINE Official Account Manager」**（ https://manager.line.biz/ ）へ遷移。

### 2-1. 「アカウント作成」ボタン

右上「**＋ アカウントを作成**」をクリック。

### 2-2. 必要情報入力

| 項目 | 入力値 |
|---|---|
| アカウント名 | **ふるりーどSPEED** |
| メールアドレス | info@futurebright.co.jp |
| 会社・事業者名 | FutureBright株式会社 |
| 大業種 | 専門的職業／その他専門サービス |
| 小業種 | コンサルタント |
| 運用目的 | 集客／プロモーション |

「**確認**」→「**完了**」

### 2-3. プロフィール設定（あとでOK）
- アイコン画像
- カバー画像
- ステータスメッセージ
→ CMO連携で後日デザインを依頼する想定

---

## STEP 3: Messaging API 有効化（3分）

### 3-1. アカウント設定へ

LINE Official Account Manager 左メニュー「**設定**」→「**Messaging API**」

### 3-2. 「Messaging APIを利用する」クリック

### 3-3. プロバイダー選択

「**新規プロバイダーを作成**」を選択し、プロバイダー名「**FutureBright**」で作成。

### 3-4. プライバシーポリシー・利用規約URL（空欄可）

とりあえず空欄で進めてOK（後日設定可）。

### 3-5. 「**同意する**」→「**OK**」

---

## STEP 4: Channel Secret / Access Token 取得（2分）

### 4-1. LINE Developers Consoleへ遷移

上記STEP 3完了後、自動で LINE Developers Console に案内されます。
（手動の場合：https://developers.line.biz/console/ ）

### 4-2. プロバイダー「FutureBright」をクリック

### 4-3. 「ふるりーどSPEED」チャネルを選択

### 4-4. **「Basic settings」タブ**

下にスクロールし **「Channel secret」** を確認。

```
Channel secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

📋 **コピーして控える**（.envに貼り付けます）

### 4-5. **「Messaging API」タブ**

### 4-6. 最下部「**Channel access token (long-lived)**」

「**Issue**」ボタンをクリック → 発行される長文トークン

```
Channel access token: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx...
```

📋 **コピーして控える**

---

## STEP 5: Webhook URL 設定（1分・本番デプロイ後）

### 5-1. 同じ「Messaging API」タブ内

「**Webhook settings**」セクションにて：

| 項目 | 値 |
|---|---|
| Webhook URL | `https://<your-cloud-run-url>/line/webhook` |
| Use webhook | **ON** |
| Verify | （URL設定後にクリック）200 OKが出ればOK |

※ Cloud Runデプロイ前は仮URL `https://example.com/line/webhook` でOK（後で正しいものに書き換え）

---

## STEP 6: 自動応答設定（1分）

LINE Official Account Manager に戻り、**設定 → 応答設定**：

| 項目 | 設定値 |
|---|---|
| 応答モード | **Bot** |
| あいさつメッセージ | **OFF** |
| 応答メッセージ | **OFF** |
| Webhook | **ON** |

→ これで Bot が全メッセージに対応する設定完了。

---

## 🎁 完了時：木原さんからCDO（Claude）へ共有する情報

以下3点を教えてください。`.env` に設定します。

```
LINE_CHANNEL_SECRET=＜STEP 4-4 で控えた値＞
LINE_CHANNEL_ACCESS_TOKEN=＜STEP 4-6 で控えた値＞
```

→ 「LINE設定完了」と伝えていただければ、CDOがサーバ側の設定を完了します。

---

## トラブルシュート

| 症状 | 対処 |
|---|---|
| QRコードが読めない | LINEアプリ更新、カメラ権限ON |
| 「すでに登録済み」 | 旧LINE Businessアカウントがある → そのままログインで可 |
| 発行ボタンが押せない | ポップアップブロッカーをOFF |
| トークンを再発行したい | 「Channel access token」横「Issue」を再度クリック（前のは無効化される） |

---

**次のステップ**: `02_GCP初期設定.md` に進んでください。
