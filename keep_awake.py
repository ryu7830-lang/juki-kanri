# -*- coding: utf-8 -*-
"""
Streamlit無料アプリの「居眠り」対策の番人。

無料版のStreamlitアプリは12時間アクセスが無いと自動でスリープ（休止）する。
単純なURLアクセス(curl等)ではJavaScriptが動かず起こせないため、
本物のブラウザ(ヘッドレスChromium)でアプリを開く。眠っていれば
「Yes, get this app back up!」ボタンを押して起こす。

GitHub Actions から毎朝自動実行する（.github/workflows/keep-awake.yml）。
手元のMacやMac miniは一切不要（GitHubのサーバ上で動くため）。

【2026-11-14 修正】起きたかどうかの判定を作り直した。
旧版はアプリ本体（iframeの中）ではなく外枠のページを探していたため、
起きていても「確認タイムアウト」になり、しかも常に成功で終わっていた
＝本当に起こせなかった日も気づけなかった。
新版は ①タブの題名 ②iframe内の本文 のどちらかでアプリ本体を確認し、
確認できなければ終了コード1（＝GitHub上で失敗・通知が届く）で終わる。
"""
import os
import sys
from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("APP_URL", "https://ozaki-juki.streamlit.app/")

# アプリが起きているときだけタブの題名に出る語。
# app.py の st.set_page_config(page_title="重機管理") と一致させること
# （読み込み中の題名は「Streamlit」だけ・起動後は「重機管理 · Streamlit」＝2026-11-14 実機で確認）。
# 居眠り画面の題名は未確認のため、居眠り画面が出ている間は題名に関係なく「未起動」と判定する。
TITLE_KEYWORD = "重機管理"
# アプリ本体の見出し（iframeの中に描かれる）。題名で判定できない場合の予備。
BODY_KEYWORD = "重機・農機・施設管理"
# 居眠り画面の起こすボタンの文言（一部一致）。
WAKE_TEXT = "get this app back up"

# 起動を待つ上限。眠りから起きるのに1〜2分かかることがあるので余裕を持たせる。
WAIT_LIMIT_SEC = 240
CHECK_EVERY_SEC = 5


def sleep_screen_visible(page):
    """居眠り画面（起こすボタン）が出ているか。"""
    try:
        btn = page.get_by_role("button", name=WAKE_TEXT, exact=False)
        if btn.count() == 0:
            btn = page.get_by_text(WAKE_TEXT, exact=False)
        return btn.count() > 0, btn
    except Exception as e:
        print("ボタン探索でエラー（無視して続行）:", e)
        return False, None


def app_is_up(page):
    """アプリ本体が表示されているか。どの方法で確認できたかも返す。"""
    # 居眠り画面が出ている間は、題名に関係なく「まだ起きていない」と判断する
    showing_sleep, _ = sleep_screen_visible(page)
    if showing_sleep:
        return False, ""

    # 判定①: タブの題名（外枠のページに反映される）
    try:
        if TITLE_KEYWORD in page.title():
            return True, "題名"
    except Exception:
        pass

    # 判定②: iframeの中の本文（題名の仕組みが変わったときの予備）
    for frame in page.frames:
        try:
            if frame.get_by_text(BODY_KEYWORD, exact=False).count() > 0:
                return True, "本文"
        except Exception:
            continue
    return False, ""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        print(f"アプリを開く: {APP_URL}")
        page.goto(APP_URL, wait_until="load", timeout=90000)
        page.wait_for_timeout(5000)  # 初期描画を待つ

        # スリープ画面なら「Yes, get this app back up!」ボタンを押して起こす
        showing_sleep, btn = sleep_screen_visible(page)
        if showing_sleep:
            print("💤 スリープを検知 → 起こすボタンを押す")
            try:
                btn.first.click()
            except Exception as e:
                # 押せなくても下の確認で成否が決まるので、ここでは止めない
                print("起こすボタンを押せなかった（確認は続行）:", e)
        else:
            print("スリープ画面なし")

        # アプリ本体が出るまで一定間隔で確認する（上限 WAIT_LIMIT_SEC 秒）
        up, how = False, ""
        waited = 0
        while waited <= WAIT_LIMIT_SEC:
            up, how = app_is_up(page)
            if up:
                break
            page.wait_for_timeout(CHECK_EVERY_SEC * 1000)
            waited += CHECK_EVERY_SEC

        title = page.title()
        print("最終ページタイトル:", title)
        browser.close()

    if up:
        print(f"✅ アプリ本体を確認（{how}で判定・待ち{waited}秒）")
        return 0

    # 起こせなかった回は失敗で終える。GitHubが失敗として記録し通知を出すので、
    # 「止まっているのに誰も気づかない」状態を防げる（旧版はここも成功扱いだった）。
    print(f"❌ {WAIT_LIMIT_SEC}秒待ってもアプリ本体を確認できなかった（起動失敗の可能性）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
