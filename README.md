# 重機管理システム（スマホ版）

重機（ダンプ・クレーン・ユンボ・トラクター等）を、現場のスマホから
どこでも登録・確認できる管理アプリ。

## 構成
- フロント：Streamlit（`app.py`）
- データ保管：Googleスプレッドシート（`sheets_backend.py` 経由）
- 認証：OAuthユーザートークン（scope=drive.file、このアプリが作るファイルのみ）

## 機能
一覧 / 詳細 / 整備記録 / 稼働日報 / 状態・期限（車検・自賠責・任意保険）更新 / 新規登録 / 編集 / 廃車

## デプロイ（Streamlit Community Cloud）
1. このリポジトリを Streamlit Cloud に接続し、メインファイルを `app.py` に指定
2. Secrets に以下を登録（値はローカルの `~/.config/juki-kanri/` を参照）：
   - `spreadsheet_id`
   - `[google_token]`（token.json の内容）

## ローカル起動
```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```
認証トークン等は `~/.config/juki-kanri/`（token.json / config.json）に置く。
