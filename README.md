# ふるりーどSPEED Bot

LINE公式アカウント「ふるりーどSPEED」Bot一式。ふるさと納税参入を検討する事業者から回答を集め、CSOレビュー経由で参入予測レポート（PDF）を自動生成・配信する。

**+ ROAS分析レポート機能（Phase 1：2026-04-29 追加）**：商談中に事業者情報を入力 → AI分析 → ROAS試算・推奨プラン入りPDFを即時生成。

## アーキテクチャ

```
[LINE] ──webhook──▶ [FastAPI app] ──▶ [SQLite]
                          │
                          └─100%到達─▶ [Chatwork通知]
                                          │
                                   [Streamlit管理画面]
                                    ├ PDF生成
                                    ├ 編集
                                    └ 承認→LINE push配信
```

## セットアップ

### 1. 依存インストール

依存は `CDO_tech/ai_agents/requirements.txt` で一元管理。

```bash
cd CDO_tech/ai_agents
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 環境変数

```bash
cp .env.example .env
# エディタで .env を開き、以下を設定:
#   LINE_CHANNEL_SECRET
#   LINE_CHANNEL_ACCESS_TOKEN
#   CHATWORK_API_TOKEN
```

### 3. DB初期化（初回のみ・自動でも作成される）

```bash
python3 -c "from app.storage import init_db; init_db()"
```

### 4. ローカル起動

#### Botサーバ
```bash
uvicorn app.main:app --reload --port 8080
```

#### 管理画面（別ターミナル）
```bash
cd admin && streamlit run streamlit_app.py
```

### 5. LINE Webhook URL登録

LINE Official Account Manager → Messaging API設定 → Webhook URL に
```
https://<your-domain>/line/webhook
```
を登録し、「Webhookの利用」をON。

ローカル開発時は [ngrok](https://ngrok.com/) でトンネリング：
```bash
ngrok http 8080
# 発行されたhttpsドメインをWebhook URLに登録
```

## ディレクトリ構成

```
furulead_speed_bot/
├── README.md                    このファイル
├── requirements.txt
├── .env.example
├── .gitignore
├── app/
│   ├── main.py                  FastAPI エントリ・LINE webhook
│   ├── questions.py             質問定義（簡易5問/詳細15問）
│   ├── scoring.py               充足度計算
│   ├── conversation.py          Step返信ロジック
│   ├── storage.py               SQLite CRUD
│   ├── notifier.py              Chatwork通知
│   └── report_generator.py      md→PDF生成
├── admin/
│   └── streamlit_app.py         CSO管理画面
├── templates/
│   ├── template_simple.md       簡易レポート雛形
│   └── template_full.md         詳細レポート雛形
└── data/
    ├── sessions.db              SQLite（自動生成）
    └── generated_pdfs/          下書きPDF保管
```

## 運用フロー

1. ユーザーが公式LINE「ふるりーどSPEED」を友だち追加
2. Botが「簡易5問」or「詳細15問」を提示
3. ユーザー回答ごとに充足度を更新・次質問を送信
4. 100%到達 → Chatworkで CSO（木原）へ通知
5. CSO が Streamlit管理画面で内容確認・PDF下書き生成
6. 内容OKなら「承認＆配信」ボタン → LINE push でPDF DLリンクを送付

## デプロイ（本番）

- **Cloud Run** または **Railway** を推奨
- 外部ストレージ：PDF配信リンクは **S3署名付きURL** or **Google Drive共有リンク**
- Cloud Run の場合、`Dockerfile` を別途作成（今後対応）

## 設計ドキュメント

- `/CSO_sales/ふるりーどSPEED/01_システム設計書.md`
- `/CSO_sales/ふるりーどSPEED/02_CDO実装依頼書.md`
- `/CSO_sales/ふるりーどSPEED/03_質問フロー詳細.md`
- `/_context/reports/furusato/20260429_CDO依頼_ROAS分析レポート生成.md`（ROAS機能の依頼書）

---

## 🎯 ROAS分析レポート機能（Phase 1）

商談中に事業者情報を入力 → AI分析 → ROAS試算・推奨プラン入りPDFを即時生成する機能。

### 起動方法

```bash
cd CDO_tech/ai_agents/furulead_speed_bot
streamlit run admin/streamlit_app.py
```

→ ブラウザで管理画面を開き、**「🎯 ROAS分析」タブ** を選択。

### 必要な環境変数

`.env` に以下が必要：

```
ANTHROPIC_API_KEY=sk-ant-xxx   # Claude API キー（Haiku 4.5 を使用）
ANTHROPIC_MODEL=claude-haiku-4-5-20251001  # 任意（デフォルト Haiku 4.5）
```

`.env` がない場合、上位の `ai_agents/.env` を自動フォールバックで読む。

### 生成物

- `data/generated_reports/roas_<事業者名>_<timestamp>/` 配下に：
  - `*.md` ：レポートMarkdown
  - `*.pdf` ：レポートPDF（A4縦・8ページ程度）
  - `radar_fit.png` ：参入適性レーダーチャート
  - `revenue_forecast.png` ：売上予測バー（保守/中位/強気・3年）
  - `product_matrix.png` ：商品ラインナップマトリクス

### レポート構成

1. エグゼクティブサマリ
2. 事業者プロファイル（強み・課題）
3. 市場ベンチマーク（カテゴリ別）
4. 参入適性スコア（8軸レーダー、10点満点）
5. 売上見込み（3シナリオ × 3年）
6. 商品ラインナップ提案（希少性×寄付額マトリクス）
7. ROAS試算（広告費・手数料・純利益・回収期間）
8. **推奨プラン**（シルバー／ゴールド／プラチナ）と比較
9. 次のアクション

### プラン定義

`data/plans.yaml` で管理。料金・サービス内容は仮データ（CSO提供待ち）。

### プラン推奨ロジック

- `fit_total < 5.0` または年商1000万未満 or 月供給<200個 → **シルバー**
- `fit_total ≥ 8.0` かつ 年商1億以上 かつ 月供給≥1000個 → **プラチナ**
- それ以外 → **ゴールド**

AIによる推奨と機械ルールの両方を出力（`_rule_based_plan` で確認可）。

### Phase 2/3 ToDo

- [ ] LINE Bot 連携（事前ヒアリング自動化）
- [ ] プラン詳細YAMLの本番化（CSO提供待ち）
- [ ] 商談時タブレット用 簡易フォーム最適化
- [ ] 楽天ふるさと市場データのRAG取り込み
- [ ] 生成PDFをGoogleドライブ自動アップロード

## テスト

```bash
# 起動確認
curl http://localhost:8080/

# DB中身確認
sqlite3 data/sessions.db "SELECT * FROM users;"
```

## 運用プレイブック

### リマインド（cron or 常駐）

```bash
# cron向け（1時間ごと）
0 * * * * cd /path/to/furulead_speed_bot && /path/to/python -m app.reminders

# 常駐（APScheduler）
python3 -m app.reminders --watch
```

### Google Drive 自動配信の初期設定

1. [Google Cloud Console](https://console.cloud.google.com/) でサービスアカウント作成
2. Drive API を有効化
3. サービスアカウントのJSONキーをダウンロード
4. Drive上で配信先フォルダを作成 → サービスアカウントのメールに「編集者」権限付与
5. `.env`に記載：
   ```
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
   GDRIVE_FOLDER_ID=1AbC...（フォルダURLから取得）
   ```

### Cloud Run デプロイ

```bash
# プロジェクトルートで実行（ai_agents配下）
cd CDO_tech/ai_agents
gcloud run deploy furulead-speed-bot \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars "LINE_CHANNEL_SECRET=xxx,LINE_CHANNEL_ACCESS_TOKEN=xxx,CHATWORK_API_TOKEN=xxx"
```

デプロイ後のURL（例：`https://furulead-speed-bot-xxx.run.app`）を
LINE Messaging APIの **Webhook URL** に `/line/webhook` を付けて登録。

### 本番SLA・運用ルーチン

| 頻度 | 作業 | 担当 |
|---|---|---|
| 随時 | Chatwork通知→Streamlit管理画面でレビュー | CSO |
| 日次 | セッション一覧確認・ブロッカー有無 | CSO |
| 週次 | CVR集計・コース別件数レポート | CSO |
| 月次 | 成果報酬算定・事業者への定例連絡 | CSO |

## 現状のTODO（未着手分）

- [x] 回答修正コマンド（「N問目修正」）— conversation.py / storage.delete_answer
- [x] 統計ダッシュボード（CVR・コース比率・日次新規）— admin/streamlit_app.py タブ3
- [ ] 本番デプロイ（Cloud Run実行）
- [ ] 相談会予約フロー（Googleカレンダー連携）
