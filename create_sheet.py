# -*- coding: utf-8 -*-
"""
データ保管庫となるGoogleスプレッドシートを新規作成し、5つの表を見出し付きで用意する。
一度だけ実行。作成後はスプレッドシートIDを config.json に保存し、以後はそれを使う。
"""
import os, json
import gspread
from google.oauth2.credentials import Credentials

CONF_DIR = os.path.expanduser("~/.config/juki-kanri")
TOKEN_FILE = os.path.join(CONF_DIR, "token.json")
CONFIG_FILE = os.path.join(CONF_DIR, "config.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

SPREADSHEET_TITLE = "重機管理データ"

# 各表（タブ）の見出し。元のSQLiteのカラム構成に合わせている。
TABLES = {
    "machines": ["id","name","category","manufacturer","model","purchase_date",
                 "plate_number","serial_number","purchase_price","notes","photo_path",
                 "sold_date","sold_price","disposal_reason","is_disposed","created_at"],
    "machine_status": ["id","machine_id","status","location","next_inspection_date",
                       "next_shaken_date","jibaiseki_expire","insurance_expire",
                       "insurance_company","insurance_policy_no","notes","updated_at"],
    "records": ["id","machine_id","record_type","record_date","description","cost",
                "worker","hour_meter","fuel_amount","next_scheduled_date","notes","created_at"],
    "operation_logs": ["id","machine_id","operator","operation_date","duration_hours",
                       "location","work_content","notes","created_at"],
    "parts_inventory": ["id","part_name","category","quantity","unit","min_quantity",
                       "storage_location","compatible_machines","unit_price","notes","updated_at"],
}

def main():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    gc = gspread.authorize(creds)

    # 既に作成済みなら作り直さない
    if os.path.exists(CONFIG_FILE):
        cfg = json.load(open(CONFIG_FILE))
        if cfg.get("spreadsheet_id"):
            print("既にスプレッドシートが登録済み:", cfg["spreadsheet_id"])
            return

    sh = gc.create(SPREADSHEET_TITLE)
    print("作成:", sh.title, sh.id)

    # 各タブを作成し見出しを書き込む
    first = True
    for name, headers in TABLES.items():
        if first:
            ws = sh.sheet1
            ws.update_title(name)
            first = False
        else:
            ws = sh.add_worksheet(title=name, rows=1000, cols=len(headers))
        ws.update([headers], "A1")
        # 見出し行を太字に
        ws.format("A1:Z1", {"textFormat": {"bold": True}})
        print("  タブ準備:", name, f"({len(headers)}列)")

    # IDを保存（IDは秘密ではない）
    json.dump({"spreadsheet_id": sh.id, "spreadsheet_url": sh.url},
              open(CONFIG_FILE, "w"), ensure_ascii=False, indent=2)
    print("URL:", sh.url)
    print("config.json に保存しました")

if __name__ == "__main__":
    main()
