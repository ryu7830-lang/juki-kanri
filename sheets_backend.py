# -*- coding: utf-8 -*-
"""
データ層：Googleスプレッドシートを「表（テーブル）」として読み書きする部品。
元はSQLiteだった保存先を、現場スマホからどこでも開けるようSheetsに置き換えるためのもの。

設計の要点:
- 認証は OAuthユーザートークン（scope=drive.file＝このアプリが作ったファイルだけ）。
  ローカルは ~/.config/juki-kanri/、クラウド(Streamlit)は st.secrets から読む。
- 読み取りは st.cache_data で短時間キャッシュ（SheetsのAPI制限対策）。書き込み後はキャッシュを消す。
- id は SQLite の自動採番の代わりに「既存の最大id+1」で採番する。
- 値は全部いったん文字列で受け取り（数値の自動変換でシリアル番号等が壊れるのを防ぐ）、
  必要なところで int/float に直す（app側のヘルパーで対応）。
"""
import os
import json
import streamlit as st
import gspread
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CONF_DIR = os.path.expanduser("~/.config/juki-kanri")


# ---------- 認証・接続 ----------
def _secret(key):
    """st.secrets を安全に参照（ローカルで secrets.toml が無くてもエラーにしない）。"""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return None


def _credentials():
    # クラウド(Streamlit Cloud)では st.secrets に入れた値を使う
    tok = _secret("google_token")
    if tok:
        return Credentials.from_authorized_user_info(dict(tok), SCOPES)
    # ローカルでは token.json を使う
    return Credentials.from_authorized_user_file(
        os.path.join(CONF_DIR, "token.json"), SCOPES)


def _spreadsheet_id():
    sid = _secret("spreadsheet_id")
    if sid:
        return sid
    cfg = json.load(open(os.path.join(CONF_DIR, "config.json")))
    return cfg["spreadsheet_id"]


@st.cache_resource
def _spreadsheet():
    """gspreadの接続は重いので1回だけ作って使い回す。"""
    gc = gspread.authorize(_credentials())
    return gc.open_by_key(_spreadsheet_id())


def _ws(table):
    return _spreadsheet().worksheet(table)


# ---------- 読み取り（キャッシュ付き） ----------
@st.cache_data(ttl=15)
def read(table):
    """表の全行を辞書のリストで返す。値はすべて文字列（空欄は ''）。15秒キャッシュ。"""
    ws = _ws(table)
    # numericise_ignore=['all'] で全列を文字列のまま受け取る（数値自動変換による破壊を防ぐ）
    return ws.get_all_records(numericise_ignore=["all"], default_blank="")


def clear_cache():
    """書き込み後に呼ぶ。次の読み取りで最新が反映される。"""
    read.clear()


@st.cache_data(ttl=600)
def headers(table):
    """見出し行（列の並び）。ほぼ変わらないので長めにキャッシュ。"""
    return _ws(table).row_values(1)


# ---------- 補助 ----------
def _to_int(v):
    try:
        return int(str(v).strip())
    except Exception:
        return None


def next_id(table):
    rows = read(table)
    ids = [_to_int(r.get("id")) for r in rows]
    ids = [i for i in ids if i is not None]
    return (max(ids) + 1) if ids else 1


def get(table, id):
    """id で1件取得。なければ None。"""
    for r in read(table):
        if str(r.get("id")) == str(id):
            return r
    return None


def find_one(table, field, value):
    """指定フィールドが一致する最初の1件。なければ None。"""
    for r in read(table):
        if str(r.get(field)) == str(value):
            return r
    return None


def find_all(table, field, value):
    """指定フィールドが一致する全件。"""
    return [r for r in read(table) if str(r.get(field)) == str(value)]


def _row_index(ws, id):
    """シート上の行番号（1始まり・見出しは1行目）を id から探す。なければ None。"""
    col_a = ws.col_values(1)  # A列（id列）。先頭は見出し。
    for i, v in enumerate(col_a):
        if i == 0:
            continue  # 見出し行はスキップ
        if str(v) == str(id):
            return i + 1  # col_valuesは0始まり、シート行番号は1始まり
    return None


def _cell(v):
    return "" if v is None else v


# ---------- 書き込み ----------
def insert(table, data):
    """1行追加。id は自動採番して返す。"""
    ws = _ws(table)
    hdrs = ws.row_values(1)
    new_id = next_id(table)
    data = {**data, "id": new_id}
    row = [_cell(data.get(h, "")) for h in hdrs]
    ws.append_row(row, value_input_option="RAW")
    clear_cache()
    return new_id


def update(table, id, data):
    """id の行を更新。既存値に data を上書きマージして書き戻す。"""
    ws = _ws(table)
    hdrs = ws.row_values(1)
    target = _row_index(ws, id)
    if target is None:
        return False
    current = get(table, id) or {}
    merged = {**current, **data, "id": id}
    row = [_cell(merged.get(h, "")) for h in hdrs]
    last_col = chr(ord("A") + len(hdrs) - 1)  # 列数ぶんの範囲（A〜）
    ws.update(values=[row], range_name=f"A{target}:{last_col}{target}",
              value_input_option="RAW")
    clear_cache()
    return True


def delete(table, id):
    """id の行を削除。"""
    ws = _ws(table)
    target = _row_index(ws, id)
    if target is None:
        return False
    ws.delete_rows(target)
    clear_cache()
    return True
