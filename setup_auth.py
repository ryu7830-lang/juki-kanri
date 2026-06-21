# -*- coding: utf-8 -*-
"""
一度だけ実行する認証セットアップ。
- ~/.config/juki-kanri/oauth_client.json（デスクトップ用OAuthクライアント）を使い
- ブラウザで一度だけ「許可」してもらい
- リフレッシュトークンを ~/.config/juki-kanri/token.json に保存する。
スコープは drive.file（このアプリが作ったファイルだけ触れる最小権限）。
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

CONF_DIR = os.path.expanduser("~/.config/juki-kanri")
CLIENT_FILE = os.path.join(CONF_DIR, "oauth_client.json")
TOKEN_FILE = os.path.join(CONF_DIR, "token.json")

# このアプリが作成したスプレッドシートだけ読み書きできる最小スコープ
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def main():
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.valid:
            print("既に有効なトークンがあります。何もしません。")
            return

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
    # ローカルにサーバを立て、ブラウザを開いて同意を受け取る
    creds = flow.run_local_server(port=0, open_browser=True,
                                  authorization_prompt_message="ブラウザで許可してください: {url}")
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)
    print("認証成功。トークンを保存しました。")

if __name__ == "__main__":
    main()
