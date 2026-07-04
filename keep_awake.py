# -*- coding: utf-8 -*-
"""
Streamlit無料アプリの「居眠り」対策の番人。

無料版のStreamlitアプリは12時間アクセスが無いと自動でスリープ（休止）する。
単純なURLアクセス(curl等)ではJavaScriptが動かず起こせないため、
本物のブラウザ(ヘッドレスChromium)でアプリを開く。眠っていれば
「Yes, get this app back up!」ボタンを押して起こす。

GitHub Actions から毎朝自動実行する（.github/workflows/keep-awake.yml）。
手元のMacやMac miniは一切不要（GitHubのサーバ上で動くため）。
"""
import os
import sys
from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("APP_URL", "https://ozaki-juki.streamlit.app/")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        print(f"アプリを開く: {APP_URL}")
        page.goto(APP_URL, wait_until="load", timeout=90000)
        page.wait_for_timeout(5000)  # 初期描画を待つ

        # スリープ画面なら「Yes, get this app back up!」ボタンを押して起こす。
        # 文言変更に耐えるよう、ボタン(role)とテキストの両方で探す。
        woke = False
        try:
            btn = page.get_by_role("button", name="get this app back up", exact=False)
            if btn.count() == 0:
                btn = page.get_by_text("get this app back up", exact=False)
            if btn.count() > 0:
                print("💤 スリープを検知 → 起こすボタンを押す")
                btn.first.click()
                woke = True
        except Exception as e:
            print("ボタン探索でエラー（無視して続行）:", e)

        if not woke:
            print("✅ スリープ画面なし（既に起動中）")

        # アプリ本体が立ち上がったか確認（タイトル「🚜 重機・農機・施設管理」の一部）。
        # スリープ画面には出ない語なので、これが見えれば起動できたと判断できる。
        try:
            page.wait_for_selector("text=重機", timeout=120000)
            print("✅ アプリ本体を確認（起動OK）")
        except Exception:
            print("⚠️ アプリ本体の確認がタイムアウト（起動が遅い/失敗の可能性）")

        print("最終ページタイトル:", page.title())
        browser.close()

    # 番人の役目は「毎朝アクセスして起こしにいく」こと。
    # 起動確認が取れなくても異常終了にはしない（次回また起こしに来るため）。
    return 0


if __name__ == "__main__":
    sys.exit(main())
