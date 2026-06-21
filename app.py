# -*- coding: utf-8 -*-
"""
重機管理システム（スマホ優先・クラウド版）
- 保存先は Googleスプレッドシート（sheets_backend.py 経由）。現場のスマホからどこでも開ける。
- 残した機能: 一覧 / 詳細 / 記録追加 / 稼働日報 / 状態・期限更新 / 新規登録 / 編集 / 廃車
- 後回し（事務所向け・このスマホ版では非表示）: レポート / 部品在庫 / 写真アップロード
  → 旧フル機能は app_sqlite_backup.py に保存済み。
"""
import streamlit as st
from datetime import date
import sheets_backend as db

# スマホで見やすいよう中央寄せ（横長wideにしない）
st.set_page_config(page_title="重機管理", page_icon="🚜", layout="centered",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
.stButton > button { font-size: 16px; padding: 0.6rem 1rem; }
.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# =====================================================
# 定数（元アプリと同じ。例示は山形・尾花沢向けに変更）
# =====================================================
CATEGORIES   = ["ダンプ", "クレーン", "ユンボ（油圧ショベル）", "トラクター", "家畜車", "ボブキャット", "その他"]
STATUSES     = ["稼働中", "待機中", "整備中", "車検中", "廃車"]
RECORD_TYPES = ["定期点検", "修理", "車検", "燃料補給", "オイル交換", "タイヤ交換", "バッテリー交換", "その他"]
STATUS_ICONS = {"稼働中": "🟢", "待機中": "🔵", "整備中": "🟡", "車検中": "🟠", "廃車": "⚫", "未設定": "⚪"}


# =====================================================
# 補助関数
# =====================================================
def to_int(v):
    try:
        s = str(v).strip()
        return int(float(s)) if s != "" else None
    except Exception:
        return None


def to_float(v):
    try:
        s = str(v).strip()
        return float(s) if s != "" else None
    except Exception:
        return None


def sval(v):
    """空欄や None を扱いやすい文字列に。"""
    s = "" if v is None else str(v)
    return s.strip()


def days_until(d):
    s = sval(d)
    if not s:
        return None
    try:
        return (date.fromisoformat(s) - date.today()).days
    except Exception:
        return None


def fmt_price(v):
    n = to_int(v)
    return f"¥{n:,}" if n else "未登録"


def parse_date(s):
    s = sval(s)
    try:
        return date.fromisoformat(s) if s else None
    except Exception:
        return None


# =====================================================
# 画面遷移
# =====================================================
for k, v in [("page", "一覧"), ("selected_machine_id", None)]:
    if k not in st.session_state:
        st.session_state[k] = v


def nav(page, machine_id=None):
    st.session_state.page = page
    if machine_id is not None:
        st.session_state.selected_machine_id = machine_id


# =====================================================
# ヘッダーナビ（スマホ向けに2ボタンへ削減）
# =====================================================
st.title("🚜 重機管理")
c1, c2 = st.columns(2)
with c1:
    if st.button("📋 一覧", use_container_width=True):
        nav("一覧"); st.rerun()
with c2:
    if st.button("➕ 新規登録", use_container_width=True):
        nav("登録"); st.rerun()
st.divider()

page = st.session_state.page

# =====================================================
# 一覧
# =====================================================
if page == "一覧":
    st.subheader("重機一覧")
    c1, c2 = st.columns(2)
    with c1:
        filter_cat = st.selectbox("カテゴリ", ["すべて"] + CATEGORIES, key="fc")
    with c2:
        filter_status = st.selectbox("状態", ["すべて"] + STATUSES, key="fs")
    show_disposed = st.checkbox("廃車済みも表示", value=False)

    machines = db.read("machines")
    statuses = {sval(s.get("machine_id")): s for s in db.read("machine_status")}

    # 結合＋フィルタ
    rows = []
    for m in machines:
        mid = sval(m.get("id"))
        s = statuses.get(mid, {})
        is_disposed = to_int(m.get("is_disposed")) == 1
        status = sval(s.get("status")) or "未設定"
        if not show_disposed and is_disposed:
            continue
        if filter_cat != "すべて" and sval(m.get("category")) != filter_cat:
            continue
        if filter_status != "すべて" and status != filter_status:
            continue
        rows.append({
            "id": mid, "name": sval(m.get("name")), "category": sval(m.get("category")),
            "plate_number": sval(m.get("plate_number")), "is_disposed": is_disposed,
            "status": status, "location": sval(s.get("location")) or "未設定",
            "next_shaken_date": s.get("next_shaken_date"),
            "jibaiseki_expire": s.get("jibaiseki_expire"),
            "insurance_expire": s.get("insurance_expire"),
        })
    rows.sort(key=lambda r: (r["category"], r["name"]))

    if not rows:
        st.info("該当する重機がありません。「➕ 新規登録」から追加してください。")
    else:
        # 期限アラート
        alerts = []
        for m in rows:
            for label, d in [("車検", m["next_shaken_date"]), ("自賠責", m["jibaiseki_expire"]),
                             ("任意保険", m["insurance_expire"])]:
                days = days_until(d)
                if days is not None and days <= 30:
                    alerts.append(f"⚠️ **{m['name']}** の{label}まで **{days}日**")
        if alerts:
            with st.expander(f"🚨 期限アラート {len(alerts)}件", expanded=True):
                for a in alerts:
                    st.markdown(a)

        st.caption(f"全 {len(rows)} 台")
        for m in rows:
            icon = STATUS_ICONS.get(m["status"], "⚪")
            with st.container(border=True):
                disp = f"~~{m['name']}~~" if m["is_disposed"] else f"**{m['name']}**"
                st.markdown(f"{disp}　{icon} {m['status']}")
                st.caption(f"{m['category']}　|　{m['plate_number'] or 'ナンバー未登録'}　|　配備：{m['location']}")
                for label, d in [("車検", m["next_shaken_date"]), ("自賠責", m["jibaiseki_expire"])]:
                    days = days_until(d)
                    if days is not None:
                        if days <= 30:
                            st.caption(f"⚠️ {label}まで{days}日")
                        elif days <= 90:
                            st.caption(f"📅 {label}まで{days}日")
                if st.button("詳細を見る", key=f"b_{m['id']}", use_container_width=True):
                    nav("詳細", m["id"]); st.rerun()

# =====================================================
# 詳細
# =====================================================
elif page == "詳細" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    machine = db.get("machines", mid)
    if not machine:
        nav("一覧"); st.rerun()
    status = db.find_one("machine_status", "machine_id", mid)
    records = db.find_all("records", "machine_id", mid)
    records.sort(key=lambda r: sval(r.get("record_date")), reverse=True)
    ops = db.find_all("operation_logs", "machine_id", mid)
    ops.sort(key=lambda o: sval(o.get("operation_date")), reverse=True)

    if st.button("← 一覧に戻る"):
        nav("一覧"); st.rerun()
    cur_status = sval(status.get("status")) if status else "未設定"
    icon = STATUS_ICONS.get(cur_status, "⚪")
    st.subheader(f"🚜 {sval(machine.get('name'))}")
    st.markdown(f"{icon} **{cur_status}**　|　{sval(machine.get('category'))}")
    if to_int(machine.get("is_disposed")) == 1:
        st.warning("この重機は廃車・売却済みです")

    t1, t2, t3, t4, t5 = st.tabs(["📋 基本情報", "📍 状態・保険", "🔧 整備記録", "👤 稼働日報", "🗑️ 廃車・売却"])

    # --- 基本情報 ---
    with t1:
        for label, key in [("カテゴリ", "category"), ("メーカー", "manufacturer"),
                           ("型式・モデル", "model"), ("ナンバー", "plate_number"),
                           ("シリアル番号", "serial_number"), ("購入日", "purchase_date")]:
            st.markdown(f"**{label}**：{sval(machine.get(key)) or '未登録'}")
        st.markdown(f"**購入価格**：{fmt_price(machine.get('purchase_price'))}")
        if sval(machine.get("notes")):
            st.markdown(f"**メモ**：{sval(machine.get('notes'))}")
        st.markdown("---")
        if st.button("✏️ 基本情報を編集する", use_container_width=True):
            nav("基本情報編集"); st.rerun()

    # --- 状態・保険 ---
    with t2:
        def show_date(label, key):
            v = sval(status.get(key)) if status else ""
            d = days_until(v)
            extra = f"　⚠️ あと{d}日" if d is not None and d <= 30 else ""
            st.markdown(f"**{label}**：{v or '未設定'}{extra}")
        st.markdown(f"**稼働状態**：{icon} {cur_status}")
        st.markdown(f"**配備場所**：{(sval(status.get('location')) if status else '') or '未設定'}")
        show_date("次回点検予定", "next_inspection_date")
        show_date("次回車検", "next_shaken_date")
        st.markdown("---")
        show_date("自賠責 期限", "jibaiseki_expire")
        show_date("任意保険 期限", "insurance_expire")
        st.markdown(f"**保険会社**：{(sval(status.get('insurance_company')) if status else '') or '未登録'}")
        if status and sval(status.get("notes")):
            st.markdown(f"**メモ**：{sval(status.get('notes'))}")
        st.markdown("---")
        if st.button("📍 状態・保険情報を更新する", use_container_width=True, type="primary"):
            nav("状態更新"); st.rerun()

    # --- 整備記録 ---
    with t3:
        if st.button("➕ 記録を追加する", use_container_width=True, type="primary"):
            nav("記録追加"); st.rerun()
        st.markdown("---")
        if records:
            total_cost = sum(to_int(r.get("cost")) or 0 for r in records)
            total_fuel = sum(to_float(r.get("fuel_amount")) or 0 for r in records)
            c1, c2, c3 = st.columns(3)
            c1.metric("記録件数", f"{len(records)}件")
            c2.metric("累計費用", fmt_price(total_cost))
            c3.metric("累計給油", f"{total_fuel:.0f}L" if total_fuel else "—")
            for r in records:
                with st.container(border=True):
                    st.markdown(f"**{sval(r.get('record_type'))}**　{sval(r.get('record_date'))}"
                                + (f"　{fmt_price(r.get('cost'))}" if to_int(r.get('cost')) else ""))
                    if sval(r.get("description")):
                        st.write(sval(r.get("description")))
                    caps = []
                    if sval(r.get("worker")):
                        caps.append(f"担当：{sval(r.get('worker'))}")
                    if to_int(r.get("hour_meter")):
                        caps.append(f"アワーメーター：{to_int(r.get('hour_meter')):,}h")
                    if to_float(r.get("fuel_amount")):
                        caps.append(f"給油量：{to_float(r.get('fuel_amount')):.1f}L")
                    if sval(r.get("next_scheduled_date")):
                        caps.append(f"次回予定：{sval(r.get('next_scheduled_date'))}")
                    for cap in caps:
                        st.caption(cap)
        else:
            st.info("記録がまだありません")

    # --- 稼働日報 ---
    with t4:
        if st.button("➕ 稼働日報を追加する", use_container_width=True, type="primary"):
            nav("操作記録追加"); st.rerun()
        st.markdown("---")
        if ops:
            total_h = sum(to_float(o.get("duration_hours")) or 0 for o in ops)
            st.metric("累計稼働時間", f"{total_h:.1f}時間")
            for o in ops:
                with st.container(border=True):
                    dur = to_float(o.get("duration_hours"))
                    st.markdown(f"**{sval(o.get('operation_date'))}**　{sval(o.get('operator'))}"
                                + (f"　{dur:.1f}h" if dur else ""))
                    if sval(o.get("work_content")):
                        st.write(sval(o.get("work_content")))
                    if sval(o.get("location")):
                        st.caption(f"作業場所：{sval(o.get('location'))}")
        else:
            st.info("稼働記録がまだありません")

    # --- 廃車・売却 ---
    with t5:
        if to_int(machine.get("is_disposed")) == 1:
            st.success("廃車・売却処理済みです")
            if sval(machine.get("sold_date")):
                st.markdown(f"**処分日：** {sval(machine.get('sold_date'))}")
            if to_int(machine.get("sold_price")):
                st.markdown(f"**売却価格：** {fmt_price(machine.get('sold_price'))}")
            if sval(machine.get("disposal_reason")):
                st.markdown(f"**理由：** {sval(machine.get('disposal_reason'))}")
            if st.button("廃車・売却を取り消す"):
                db.update("machines", mid, {"is_disposed": 0, "sold_date": "",
                                            "sold_price": "", "disposal_reason": ""})
                st.rerun()
        else:
            st.warning("廃車・売却を登録すると一覧から非表示になります（記録は残ります）")
            with st.form("disposal_form"):
                sold_date = st.date_input("処分日", value=date.today())
                disposal_reason = st.text_input("理由", placeholder="例：老朽化、使用頻度低下")
                sold_price = st.number_input("売却価格（円）", min_value=0, step=10000, value=0)
                if st.form_submit_button("廃車・売却として登録する", type="primary"):
                    db.update("machines", mid, {
                        "is_disposed": 1, "sold_date": str(sold_date),
                        "sold_price": sold_price if sold_price > 0 else "",
                        "disposal_reason": disposal_reason or "",
                    })
                    st.success("登録しました"); nav("一覧"); st.rerun()

# =====================================================
# 新規登録
# =====================================================
elif page == "登録":
    st.subheader("➕ 重機を新規登録")
    if st.button("← 一覧に戻る"):
        nav("一覧"); st.rerun()

    with st.form("register_form", clear_on_submit=True):
        st.markdown("#### 基本情報")
        name = st.text_input("重機名 ＊必須", placeholder="例：4tダンプ1号")
        category = st.selectbox("カテゴリ ＊必須", CATEGORIES)
        manufacturer = st.text_input("メーカー", placeholder="例：コマツ")
        model = st.text_input("型式・モデル", placeholder="例：PC30UU-5")
        plate_number = st.text_input("ナンバー", placeholder="例：山形800 あ 1234")
        serial_number = st.text_input("シリアル番号")
        purchase_date = st.date_input("購入日", value=None)
        purchase_price = st.number_input("購入価格（円）", min_value=0, step=10000, value=0)
        notes = st.text_area("メモ")

        st.markdown("#### 初期状態")
        initial_status = st.selectbox("稼働状態", STATUSES)
        initial_location = st.text_input("配備場所", placeholder="例：第1農場")
        next_inspection = st.date_input("次回点検予定日", value=None)
        next_shaken = st.date_input("次回車検予定日", value=None)

        st.markdown("#### 保険情報")
        jibaiseki_exp = st.date_input("自賠責保険 期限", value=None)
        insurance_exp = st.date_input("任意保険 期限", value=None)
        insurance_co = st.text_input("保険会社名")

        if st.form_submit_button("✅ 登録する", use_container_width=True, type="primary"):
            if not name.strip():
                st.error("重機名を入力してください")
            else:
                new_id = db.insert("machines", {
                    "name": name.strip(), "category": category,
                    "manufacturer": manufacturer or "", "model": model or "",
                    "purchase_date": str(purchase_date) if purchase_date else "",
                    "plate_number": plate_number or "", "serial_number": serial_number or "",
                    "purchase_price": purchase_price if purchase_price > 0 else "",
                    "notes": notes or "", "is_disposed": 0,
                })
                db.insert("machine_status", {
                    "machine_id": new_id, "status": initial_status,
                    "location": initial_location or "",
                    "next_inspection_date": str(next_inspection) if next_inspection else "",
                    "next_shaken_date": str(next_shaken) if next_shaken else "",
                    "jibaiseki_expire": str(jibaiseki_exp) if jibaiseki_exp else "",
                    "insurance_expire": str(insurance_exp) if insurance_exp else "",
                    "insurance_company": insurance_co or "",
                })
                st.success(f"「{name}」を登録しました！")
                nav("詳細", new_id); st.rerun()

# =====================================================
# 状態・保険更新
# =====================================================
elif page == "状態更新" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    machine = db.get("machines", mid)
    status = db.find_one("machine_status", "machine_id", mid)

    if st.button("← 詳細に戻る"):
        nav("詳細"); st.rerun()
    st.subheader(f"📍 状態・保険更新：{sval(machine.get('name'))}")

    with st.form("status_form"):
        st.markdown("#### 稼働状態")
        cur = sval(status.get("status")) if status else ""
        idx = STATUSES.index(cur) if cur in STATUSES else 0
        new_status = st.selectbox("稼働状態", STATUSES, index=idx)
        new_location = st.text_input("配備場所", value=sval(status.get("location")) if status else "")
        next_insp = st.date_input("次回点検予定日",
                                  value=parse_date(status.get("next_inspection_date")) if status else None)
        next_shaken = st.date_input("次回車検予定日",
                                    value=parse_date(status.get("next_shaken_date")) if status else None)

        st.markdown("#### 保険情報")
        jibaiseki_exp = st.date_input("自賠責保険 期限",
                                      value=parse_date(status.get("jibaiseki_expire")) if status else None)
        insurance_exp = st.date_input("任意保険 期限",
                                      value=parse_date(status.get("insurance_expire")) if status else None)
        insurance_co = st.text_input("保険会社",
                                     value=sval(status.get("insurance_company")) if status else "")
        new_notes = st.text_area("メモ", value=sval(status.get("notes")) if status else "")

        if st.form_submit_button("✅ 更新する", use_container_width=True, type="primary"):
            payload = {
                "status": new_status, "location": new_location or "",
                "next_inspection_date": str(next_insp) if next_insp else "",
                "next_shaken_date": str(next_shaken) if next_shaken else "",
                "jibaiseki_expire": str(jibaiseki_exp) if jibaiseki_exp else "",
                "insurance_expire": str(insurance_exp) if insurance_exp else "",
                "insurance_company": insurance_co or "", "notes": new_notes or "",
            }
            if status:
                db.update("machine_status", status.get("id"), payload)
            else:
                db.insert("machine_status", {"machine_id": mid, **payload})
            st.success("更新しました！"); nav("詳細"); st.rerun()

# =====================================================
# 記録追加
# =====================================================
elif page == "記録追加" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    machine = db.get("machines", mid)

    if st.button("← 詳細に戻る"):
        nav("詳細"); st.rerun()
    st.subheader(f"🔧 記録追加：{sval(machine.get('name'))}")

    with st.form("record_form", clear_on_submit=True):
        record_type = st.selectbox("記録の種類", RECORD_TYPES)
        record_date = st.date_input("実施日", value=date.today())
        cost = st.number_input("費用（円）", min_value=0, step=1000, value=0)
        worker = st.text_input("担当者・整備業者", placeholder="例：〇〇農機")
        hour_meter = st.number_input("アワーメーター（h）", min_value=0, step=1, value=0,
                                     help="記録時点のエンジン稼働時間の累計")
        fuel_amount = st.number_input("給油量（L）", min_value=0.0, step=10.0, value=0.0)
        next_scheduled = st.date_input("次回予定日", value=None)
        description = st.text_area("内容・詳細", placeholder="例：エンジンオイル交換・フィルター交換実施")
        record_notes = st.text_area("その他メモ")

        if st.form_submit_button("✅ 記録を保存する", use_container_width=True, type="primary"):
            db.insert("records", {
                "machine_id": mid, "record_type": record_type, "record_date": str(record_date),
                "description": description or "", "cost": cost if cost > 0 else "",
                "worker": worker or "", "hour_meter": hour_meter if hour_meter > 0 else "",
                "fuel_amount": fuel_amount if fuel_amount > 0 else "",
                "next_scheduled_date": str(next_scheduled) if next_scheduled else "",
                "notes": record_notes or "",
            })
            st.success("記録を保存しました！"); nav("詳細"); st.rerun()

# =====================================================
# 稼働日報追加
# =====================================================
elif page == "操作記録追加" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    machine = db.get("machines", mid)

    if st.button("← 詳細に戻る"):
        nav("詳細"); st.rerun()
    st.subheader(f"👤 稼働日報追加：{sval(machine.get('name'))}")

    with st.form("op_form", clear_on_submit=True):
        operator = st.text_input("オペレーター名 ＊必須", placeholder="例：田中")
        operation_date = st.date_input("作業日", value=date.today())
        duration_hours = st.number_input("稼働時間（h）", min_value=0.0, step=0.5, value=0.0)
        location = st.text_input("作業場所", placeholder="例：第1農場")
        work_content = st.text_area("作業内容", placeholder="例：牧草刈り取り作業")
        op_notes = st.text_area("その他メモ")

        if st.form_submit_button("✅ 保存する", use_container_width=True, type="primary"):
            if not operator.strip():
                st.error("オペレーター名を入力してください")
            else:
                db.insert("operation_logs", {
                    "machine_id": mid, "operator": operator.strip(),
                    "operation_date": str(operation_date),
                    "duration_hours": duration_hours if duration_hours > 0 else "",
                    "location": location or "", "work_content": work_content or "",
                    "notes": op_notes or "",
                })
                st.success("稼働日報を保存しました！"); nav("詳細"); st.rerun()

# =====================================================
# 基本情報編集
# =====================================================
elif page == "基本情報編集" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    machine = db.get("machines", mid)

    if st.button("← 詳細に戻る"):
        nav("詳細"); st.rerun()
    st.subheader(f"✏️ 基本情報を編集：{sval(machine.get('name'))}")

    with st.form("edit_form"):
        name = st.text_input("重機名 ＊必須", value=sval(machine.get("name")))
        cur_cat = sval(machine.get("category"))
        cat_idx = CATEGORIES.index(cur_cat) if cur_cat in CATEGORIES else 0
        category = st.selectbox("カテゴリ", CATEGORIES, index=cat_idx)
        manufacturer = st.text_input("メーカー", value=sval(machine.get("manufacturer")))
        model = st.text_input("型式・モデル", value=sval(machine.get("model")))
        plate_number = st.text_input("ナンバー", value=sval(machine.get("plate_number")))
        serial_number = st.text_input("シリアル番号", value=sval(machine.get("serial_number")))
        purchase_date = st.date_input("購入日", value=parse_date(machine.get("purchase_date")))
        purchase_price = st.number_input("購入価格（円）", min_value=0, step=10000,
                                         value=to_int(machine.get("purchase_price")) or 0)
        notes = st.text_area("メモ", value=sval(machine.get("notes")))

        if st.form_submit_button("✅ 保存する", use_container_width=True, type="primary"):
            if not name.strip():
                st.error("重機名を入力してください")
            else:
                db.update("machines", mid, {
                    "name": name.strip(), "category": category,
                    "manufacturer": manufacturer or "", "model": model or "",
                    "purchase_date": str(purchase_date) if purchase_date else "",
                    "plate_number": plate_number or "", "serial_number": serial_number or "",
                    "purchase_price": purchase_price if purchase_price > 0 else "",
                    "notes": notes or "",
                })
                st.success("更新しました！"); nav("詳細"); st.rerun()

else:
    nav("一覧"); st.rerun()
