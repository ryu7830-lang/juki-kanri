import streamlit as st
import sqlite3
import pandas as pd
import altair as alt
from datetime import datetime, date, timedelta
import os

st.set_page_config(page_title="重機管理システム", page_icon="🚜", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.stButton > button { font-size: 16px; padding: 0.5rem 1rem; }
</style>
""", unsafe_allow_html=True)

# =====================================================
# DB設定
# =====================================================
DB_PATH    = os.path.join(os.path.dirname(__file__), "data", "machines.db")
PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "data", "photos")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS machines (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL,
        manufacturer TEXT, model TEXT, purchase_date TEXT, plate_number TEXT,
        serial_number TEXT, purchase_price INTEGER, notes TEXT, photo_path TEXT,
        sold_date TEXT, sold_price INTEGER, disposal_reason TEXT, is_disposed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime')))''')
    c.execute('''CREATE TABLE IF NOT EXISTS machine_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT, machine_id INTEGER UNIQUE,
        status TEXT DEFAULT '待機中', location TEXT,
        next_inspection_date TEXT, next_shaken_date TEXT,
        jibaiseki_expire TEXT, insurance_expire TEXT,
        insurance_company TEXT, insurance_policy_no TEXT,
        notes TEXT, updated_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (machine_id) REFERENCES machines(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT, machine_id INTEGER,
        record_type TEXT NOT NULL, record_date TEXT NOT NULL,
        description TEXT, cost INTEGER, worker TEXT,
        hour_meter INTEGER, fuel_amount REAL,
        next_scheduled_date TEXT, notes TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (machine_id) REFERENCES machines(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS operation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, machine_id INTEGER,
        operator TEXT NOT NULL, operation_date TEXT NOT NULL,
        duration_hours REAL, location TEXT, work_content TEXT, notes TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (machine_id) REFERENCES machines(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS parts_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT, part_name TEXT NOT NULL,
        category TEXT, quantity REAL NOT NULL DEFAULT 0, unit TEXT DEFAULT '個',
        min_quantity REAL DEFAULT 1, storage_location TEXT,
        compatible_machines TEXT, unit_price INTEGER, notes TEXT,
        updated_at TEXT DEFAULT (datetime('now','localtime')))''')
    conn.commit()
    # 既存DBへのカラム追加（マイグレーション）
    for table, col, col_type in [
        ("machines","photo_path","TEXT"), ("machines","sold_date","TEXT"),
        ("machines","sold_price","INTEGER"), ("machines","disposal_reason","TEXT"),
        ("machines","is_disposed","INTEGER DEFAULT 0"),
        ("machine_status","jibaiseki_expire","TEXT"), ("machine_status","insurance_expire","TEXT"),
        ("machine_status","insurance_company","TEXT"), ("machine_status","insurance_policy_no","TEXT"),
        ("records","hour_meter","INTEGER"), ("records","fuel_amount","REAL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    conn.close()
    os.makedirs(PHOTOS_DIR, exist_ok=True)

init_db()

# =====================================================
# 定数
# =====================================================
CATEGORIES     = ["ダンプ","クレーン","ユンボ（油圧ショベル）","トラクター","家畜車","ボブキャット","その他"]
STATUSES       = ["稼働中","待機中","整備中","車検中","廃車"]
RECORD_TYPES   = ["定期点検","修理","車検","燃料補給","オイル交換","タイヤ交換","バッテリー交換","その他"]
PARTS_CATS     = ["エンジン部品","油脂類","タイヤ・ゴム類","電気部品","フィルター類","その他"]
STATUS_ICONS   = {"稼働中":"🟢","待機中":"🔵","整備中":"🟡","車検中":"🟠","廃車":"⚫","未設定":"⚪"}

def days_until(d):
    try: return (date.fromisoformat(d) - date.today()).days if d else None
    except: return None

def fmt_price(v):
    return f"¥{v:,}" if v else "未登録"

def parse_date(s):
    try: return date.fromisoformat(s) if s else None
    except: return None

def save_photo(machine_id, f):
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    path = os.path.join(PHOTOS_DIR, f"{machine_id}_{f.name}")
    with open(path, "wb") as fp: fp.write(f.getbuffer())
    return path

# =====================================================
# セッション初期化
# =====================================================
for k, v in [("page","一覧"),("selected_machine_id",None),("selected_part_id",None)]:
    if k not in st.session_state: st.session_state[k] = v

def nav(page, machine_id=None, part_id=None):
    st.session_state.page = page
    if machine_id is not None: st.session_state.selected_machine_id = machine_id
    if part_id   is not None: st.session_state.selected_part_id    = part_id

# =====================================================
# ヘッダーナビ
# =====================================================
c1,c2,c3,c4,c5 = st.columns([2.5,1,1,1,1])
with c1: st.title("🚜 重機管理システム")
with c2:
    if st.button("📋 一覧", use_container_width=True): nav("一覧"); st.rerun()
with c3:
    if st.button("➕ 新規登録", use_container_width=True): nav("登録"); st.rerun()
with c4:
    if st.button("📊 レポート", use_container_width=True): nav("レポート"); st.rerun()
with c5:
    if st.button("🔧 部品在庫", use_container_width=True): nav("部品在庫"); st.rerun()
st.divider()

# =====================================================
# 重機一覧
# =====================================================
if st.session_state.page == "一覧":
    st.subheader("重機一覧")
    c1,c2,c3 = st.columns([2,2,1])
    with c1: filter_cat    = st.selectbox("カテゴリ", ["すべて"]+CATEGORIES, key="fc")
    with c2: filter_status = st.selectbox("状態",     ["すべて"]+STATUSES,   key="fs")
    with c3: show_disposed = st.checkbox("廃車済みも表示", value=False)

    conn = get_db()
    q = """SELECT m.id,m.name,m.category,m.plate_number,COALESCE(m.is_disposed,0) AS is_disposed,
               COALESCE(s.status,'未設定') AS status, COALESCE(s.location,'未設定') AS location,
               s.next_shaken_date, s.jibaiseki_expire, s.insurance_expire
           FROM machines m LEFT JOIN machine_status s ON m.id=s.machine_id WHERE 1=1"""
    params = []
    if not show_disposed: q += " AND COALESCE(m.is_disposed,0)=0"
    if filter_cat    != "すべて": q += " AND m.category=?";                     params.append(filter_cat)
    if filter_status != "すべて": q += " AND COALESCE(s.status,'未設定')=?";  params.append(filter_status)
    q += " ORDER BY m.category, m.name"
    machines = conn.execute(q, params).fetchall()
    conn.close()

    if not machines:
        st.info("重機が登録されていません。「➕ 新規登録」から追加してください。")
    else:
        # 期限アラートバナー
        alerts = []
        for m in machines:
            for label, d in [("車検",m["next_shaken_date"]),("自賠責",m["jibaiseki_expire"]),("任意保険",m["insurance_expire"])]:
                days = days_until(d)
                if days is not None and days <= 30:
                    alerts.append(f"⚠️ **{m['name']}** の{label}まで **{days}日**")
        if alerts:
            with st.expander(f"🚨 期限アラート {len(alerts)}件", expanded=True):
                for a in alerts: st.markdown(a)

        st.caption(f"全 {len(machines)} 台")
        for m in machines:
            icon = STATUS_ICONS.get(m["status"], "⚪")
            with st.container(border=True):
                col1,col2,col3 = st.columns([3,3,1])
                with col1:
                    disp = f"~~{m['name']}~~" if m["is_disposed"] else f"**{m['name']}**"
                    st.markdown(disp)
                    st.caption(f"{m['category']}　|　{m['plate_number'] or 'ナンバー未登録'}")
                with col2:
                    st.markdown(f"{icon} **{m['status']}**")
                    st.caption(f"配備場所：{m['location']}")
                    for label, d in [("車検",m["next_shaken_date"]),("自賠責",m["jibaiseki_expire"])]:
                        days = days_until(d)
                        if days is not None:
                            if days <= 30: st.caption(f"⚠️ {label}まで{days}日")
                            elif days <= 90: st.caption(f"📅 {label}まで{days}日")
                with col3:
                    if st.button("詳細", key=f"b_{m['id']}", use_container_width=True):
                        nav("詳細", m["id"]); st.rerun()

# =====================================================
# 重機詳細
# =====================================================
elif st.session_state.page == "詳細" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    conn = get_db()
    machine = conn.execute("SELECT * FROM machines WHERE id=?", (mid,)).fetchone()
    status  = conn.execute("SELECT * FROM machine_status WHERE machine_id=?", (mid,)).fetchone()
    records = conn.execute("SELECT * FROM records WHERE machine_id=? ORDER BY record_date DESC", (mid,)).fetchall()
    ops     = conn.execute("SELECT * FROM operation_logs WHERE machine_id=? ORDER BY operation_date DESC", (mid,)).fetchall()
    conn.close()

    if not machine: nav("一覧"); st.rerun()

    if st.button("← 一覧に戻る"): nav("一覧"); st.rerun()
    cur_status = status["status"] if status else "未設定"
    icon = STATUS_ICONS.get(cur_status, "⚪")
    st.subheader(f"🚜 {machine['name']}")
    st.markdown(f"{icon} **{cur_status}**　|　{machine['category']}")
    if machine["is_disposed"]: st.warning("この重機は廃車・売却済みです")

    t1,t2,t3,t4,t5 = st.tabs(["📋 基本情報","📍 状態・保険","🔧 整備記録","👤 操作記録","🗑️ 廃車・売却"])

    # --- タブ1：基本情報＋写真 ---
    with t1:
        c1,c2 = st.columns(2)
        with c1:
            for label, val in [("カテゴリ",machine["category"]),("メーカー",machine["manufacturer"]),
                                ("型式・モデル",machine["model"]),("ナンバー",machine["plate_number"])]:
                st.markdown(f"**{label}**"); st.write(val or "未登録")
        with c2:
            for label, val in [("シリアル番号",machine["serial_number"]),("購入日",machine["purchase_date"])]:
                st.markdown(f"**{label}**"); st.write(val or "未登録")
            st.markdown("**購入価格**"); st.write(fmt_price(machine["purchase_price"]))
        if machine["notes"]: st.markdown("**メモ**"); st.write(machine["notes"])

        st.markdown("---")
        st.markdown("**写真**")
        if machine["photo_path"] and os.path.exists(machine["photo_path"]):
            st.image(machine["photo_path"], width=320)
        else:
            st.caption("写真未登録")

        photo_file = st.file_uploader("写真をアップロード（JPG/PNG）", type=["jpg","jpeg","png"])
        c1,c2 = st.columns(2)
        with c1:
            if photo_file and st.button("写真を保存する", use_container_width=True):
                path = save_photo(mid, photo_file)
                conn = get_db()
                conn.execute("UPDATE machines SET photo_path=? WHERE id=?", (path, mid))
                conn.commit(); conn.close()
                st.success("写真を保存しました"); st.rerun()
        with c2:
            if st.button("✏️ 基本情報を編集する", use_container_width=True):
                nav("基本情報編集"); st.rerun()

    # --- タブ2：状態・保険 ---
    with t2:
        c1,c2 = st.columns(2)
        with c1:
            st.markdown("**稼働状態**"); st.write(f"{icon} {cur_status}")
            st.markdown("**配備場所**"); st.write(status["location"] if status and status["location"] else "未設定")
        with c2:
            st.markdown("**次回点検予定**"); st.write(status["next_inspection_date"] if status and status["next_inspection_date"] else "未設定")
            st.markdown("**次回車検**")
            shaken = status["next_shaken_date"] if status else None
            if shaken:
                d = days_until(shaken)
                st.write(f"{shaken}{'　⚠️ あと'+str(d)+'日' if d is not None and d<=30 else ''}")
            else: st.write("未設定")

        st.markdown("---")
        st.markdown("**保険情報**")
        c1,c2 = st.columns(2)
        with c1:
            st.markdown("**自賠責 期限**")
            j = status["jibaiseki_expire"] if status else None
            if j:
                d = days_until(j)
                st.write(f"{j}{'　⚠️ あと'+str(d)+'日' if d is not None and d<=30 else ''}")
            else: st.write("未登録")
        with c2:
            st.markdown("**任意保険 期限**")
            ins = status["insurance_expire"] if status else None
            if ins:
                d = days_until(ins)
                st.write(f"{ins}{'　⚠️ あと'+str(d)+'日' if d is not None and d<=30 else ''}")
            else: st.write("未登録")
            st.markdown("**保険会社**")
            st.write(status["insurance_company"] if status and status["insurance_company"] else "未登録")

        if status and status["notes"]: st.markdown("**メモ**"); st.write(status["notes"])
        if status: st.caption(f"最終更新：{status['updated_at']}")
        st.markdown("---")
        if st.button("📍 状態・保険情報を更新する", use_container_width=True):
            nav("状態更新"); st.rerun()

    # --- タブ3：整備記録 ---
    with t3:
        if st.button("➕ 記録を追加する", use_container_width=True, type="primary"):
            nav("記録追加"); st.rerun()
        st.markdown("---")
        if records:
            total_cost = sum(r["cost"] for r in records if r["cost"])
            total_fuel = sum(r["fuel_amount"] for r in records if r["fuel_amount"])
            c1,c2,c3 = st.columns(3)
            c1.metric("記録件数", f"{len(records)}件")
            c2.metric("累計費用", fmt_price(total_cost))
            c3.metric("累計給油", f"{total_fuel:.0f}L" if total_fuel else "記録なし")
            for r in records:
                with st.container(border=True):
                    col1,col2 = st.columns([3,1])
                    with col1:
                        st.markdown(f"**{r['record_type']}**　{r['record_date']}")
                        if r["description"]: st.write(r["description"])
                        caps = []
                        if r["worker"]: caps.append(f"担当：{r['worker']}")
                        if r["hour_meter"]: caps.append(f"アワーメーター：{r['hour_meter']:,}h")
                        if r["fuel_amount"]: caps.append(f"給油量：{r['fuel_amount']:.1f}L")
                        if r["next_scheduled_date"]: caps.append(f"次回予定：{r['next_scheduled_date']}")
                        for cap in caps: st.caption(cap)
                    with col2:
                        if r["cost"]: st.markdown(f"**{fmt_price(r['cost'])}**")
        else:
            st.info("記録がまだありません")

    # --- タブ4：操作記録 ---
    with t4:
        if st.button("➕ 稼働日報を追加する", use_container_width=True, type="primary"):
            nav("操作記録追加"); st.rerun()
        st.markdown("---")
        if ops:
            total_h = sum(o["duration_hours"] for o in ops if o["duration_hours"])
            st.metric("累計稼働時間", f"{total_h:.1f}時間")
            for o in ops:
                with st.container(border=True):
                    col1,col2 = st.columns([3,1])
                    with col1:
                        st.markdown(f"**{o['operation_date']}**　{o['operator']}")
                        if o["work_content"]: st.write(o["work_content"])
                        if o["location"]: st.caption(f"作業場所：{o['location']}")
                    with col2:
                        if o["duration_hours"]: st.markdown(f"**{o['duration_hours']:.1f}h**")
        else:
            st.info("稼働記録がまだありません")

    # --- タブ5：廃車・売却 ---
    with t5:
        if machine["is_disposed"]:
            st.success("廃車・売却処理済みです")
            c1,c2 = st.columns(2)
            with c1:
                if machine["sold_date"]: st.markdown(f"**処分日：** {machine['sold_date']}")
                if machine["sold_price"]: st.markdown(f"**売却価格：** {fmt_price(machine['sold_price'])}")
            with c2:
                if machine["disposal_reason"]: st.markdown(f"**理由：** {machine['disposal_reason']}")
            if st.button("廃車・売却を取り消す"):
                conn = get_db()
                conn.execute("UPDATE machines SET is_disposed=0 WHERE id=?", (mid,))
                conn.commit(); conn.close(); st.rerun()
        else:
            st.warning("廃車・売却を登録すると一覧から非表示になります（記録は残ります）")
            with st.form("disposal_form"):
                c1,c2 = st.columns(2)
                with c1:
                    sold_date       = st.date_input("処分日", value=date.today())
                    disposal_reason = st.text_input("理由", placeholder="例：老朽化、使用頻度低下")
                with c2:
                    sold_price = st.number_input("売却価格（円）", min_value=0, step=10000, value=0)
                if st.form_submit_button("廃車・売却として登録する", type="primary"):
                    conn = get_db()
                    conn.execute("UPDATE machines SET is_disposed=1,sold_date=?,sold_price=?,disposal_reason=? WHERE id=?",
                                 (str(sold_date), sold_price if sold_price>0 else None, disposal_reason or None, mid))
                    conn.commit(); conn.close()
                    st.success("登録しました"); nav("一覧"); st.rerun()

# =====================================================
# 新規登録
# =====================================================
elif st.session_state.page == "登録":
    st.subheader("➕ 重機を新規登録")
    if st.button("← 一覧に戻る"): nav("一覧"); st.rerun()

    with st.form("register_form", clear_on_submit=True):
        st.markdown("#### 基本情報")
        name     = st.text_input("重機名 ＊必須", placeholder="例：4tダンプ1号")
        category = st.selectbox("カテゴリ ＊必須", CATEGORIES)
        c1,c2 = st.columns(2)
        with c1:
            manufacturer  = st.text_input("メーカー", placeholder="例：コマツ")
            plate_number  = st.text_input("ナンバー", placeholder="例：岐阜800 あ 1234")
            purchase_date = st.date_input("購入日", value=None)
        with c2:
            model          = st.text_input("型式・モデル", placeholder="例：PC30UU-5")
            serial_number  = st.text_input("シリアル番号")
            purchase_price = st.number_input("購入価格（円）", min_value=0, step=10000, value=0)
        notes = st.text_area("メモ")

        st.markdown("#### 初期状態")
        c1,c2 = st.columns(2)
        with c1:
            initial_status  = st.selectbox("稼働状態", STATUSES)
            next_inspection = st.date_input("次回点検予定日", value=None)
        with c2:
            initial_location = st.text_input("配備場所", placeholder="例：第1農場")
            next_shaken      = st.date_input("次回車検予定日", value=None)

        st.markdown("#### 保険情報")
        c1,c2 = st.columns(2)
        with c1: jibaiseki_exp = st.date_input("自賠責保険 期限", value=None)
        with c2:
            insurance_exp = st.date_input("任意保険 期限", value=None)
            insurance_co  = st.text_input("保険会社名")

        if st.form_submit_button("✅ 登録する", use_container_width=True, type="primary"):
            if not name.strip():
                st.error("重機名を入力してください")
            else:
                conn = get_db()
                c = conn.cursor()
                c.execute("""INSERT INTO machines (name,category,manufacturer,model,purchase_date,
                             plate_number,serial_number,purchase_price,notes) VALUES (?,?,?,?,?,?,?,?,?)""",
                          (name.strip(),category,manufacturer or None,model or None,
                           str(purchase_date) if purchase_date else None,
                           plate_number or None,serial_number or None,
                           purchase_price if purchase_price>0 else None,notes or None))
                new_id = c.lastrowid
                c.execute("""INSERT INTO machine_status
                             (machine_id,status,location,next_inspection_date,next_shaken_date,
                              jibaiseki_expire,insurance_expire,insurance_company)
                             VALUES (?,?,?,?,?,?,?,?)""",
                          (new_id,initial_status,initial_location or None,
                           str(next_inspection) if next_inspection else None,
                           str(next_shaken) if next_shaken else None,
                           str(jibaiseki_exp) if jibaiseki_exp else None,
                           str(insurance_exp) if insurance_exp else None,
                           insurance_co or None))
                conn.commit(); conn.close()
                st.success(f"「{name}」を登録しました！")
                nav("詳細", new_id); st.rerun()

# =====================================================
# 状態・保険更新
# =====================================================
elif st.session_state.page == "状態更新" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    conn = get_db()
    machine = conn.execute("SELECT * FROM machines WHERE id=?", (mid,)).fetchone()
    status  = conn.execute("SELECT * FROM machine_status WHERE machine_id=?", (mid,)).fetchone()
    conn.close()

    if st.button("← 詳細に戻る"): nav("詳細"); st.rerun()
    st.subheader(f"📍 状態・保険更新：{machine['name']}")

    with st.form("status_form"):
        st.markdown("#### 稼働状態")
        c1,c2 = st.columns(2)
        with c1:
            idx = STATUSES.index(status["status"]) if status and status["status"] in STATUSES else 0
            new_status   = st.selectbox("稼働状態", STATUSES, index=idx)
            next_insp    = st.date_input("次回点検予定日", value=parse_date(status["next_inspection_date"] if status else None))
        with c2:
            new_location = st.text_input("配備場所", value=status["location"] if status else "")
            next_shaken  = st.date_input("次回車検予定日", value=parse_date(status["next_shaken_date"] if status else None))

        st.markdown("#### 保険情報")
        c1,c2 = st.columns(2)
        with c1:
            jibaiseki_exp = st.date_input("自賠責保険 期限", value=parse_date(status["jibaiseki_expire"] if status else None))
        with c2:
            insurance_exp = st.date_input("任意保険 期限", value=parse_date(status["insurance_expire"] if status else None))
            insurance_co  = st.text_input("保険会社", value=status["insurance_company"] if status and status["insurance_company"] else "")

        new_notes = st.text_area("メモ", value=status["notes"] if status else "")

        if st.form_submit_button("✅ 更新する", use_container_width=True, type="primary"):
            vals = (new_status, new_location or None,
                    str(next_insp) if next_insp else None,
                    str(next_shaken) if next_shaken else None,
                    str(jibaiseki_exp) if jibaiseki_exp else None,
                    str(insurance_exp) if insurance_exp else None,
                    insurance_co or None, new_notes or None)
            conn = get_db()
            if status:
                conn.execute("""UPDATE machine_status SET status=?,location=?,next_inspection_date=?,
                             next_shaken_date=?,jibaiseki_expire=?,insurance_expire=?,
                             insurance_company=?,notes=?,updated_at=datetime('now','localtime')
                             WHERE machine_id=?""", vals+(mid,))
            else:
                conn.execute("""INSERT INTO machine_status
                             (machine_id,status,location,next_inspection_date,next_shaken_date,
                              jibaiseki_expire,insurance_expire,insurance_company,notes)
                             VALUES (?,?,?,?,?,?,?,?,?)""", (mid,)+vals)
            conn.commit(); conn.close()
            st.success("更新しました！"); nav("詳細"); st.rerun()

# =====================================================
# 記録追加
# =====================================================
elif st.session_state.page == "記録追加" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    conn = get_db()
    machine = conn.execute("SELECT * FROM machines WHERE id=?", (mid,)).fetchone()
    conn.close()

    if st.button("← 詳細に戻る"): nav("詳細"); st.rerun()
    st.subheader(f"🔧 記録追加：{machine['name']}")

    with st.form("record_form", clear_on_submit=True):
        c1,c2 = st.columns(2)
        with c1:
            record_type    = st.selectbox("記録の種類", RECORD_TYPES)
            record_date    = st.date_input("実施日", value=date.today())
            cost           = st.number_input("費用（円）", min_value=0, step=1000, value=0)
        with c2:
            worker         = st.text_input("担当者・整備業者", placeholder="例：〇〇農機")
            next_scheduled = st.date_input("次回予定日", value=None)

        c1,c2 = st.columns(2)
        with c1: hour_meter  = st.number_input("アワーメーター（h）", min_value=0, step=1, value=0,
                                                help="記録時点のエンジン稼働時間の累計")
        with c2: fuel_amount = st.number_input("給油量（L）", min_value=0.0, step=10.0, value=0.0)

        description  = st.text_area("内容・詳細", placeholder="例：エンジンオイル交換・フィルター交換実施")
        record_notes = st.text_area("その他メモ")

        if st.form_submit_button("✅ 記録を保存する", use_container_width=True, type="primary"):
            conn = get_db()
            conn.execute("""INSERT INTO records
                (machine_id,record_type,record_date,description,cost,worker,
                 hour_meter,fuel_amount,next_scheduled_date,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (mid,record_type,str(record_date),description or None,
                 cost if cost>0 else None, worker or None,
                 hour_meter if hour_meter>0 else None,
                 fuel_amount if fuel_amount>0 else None,
                 str(next_scheduled) if next_scheduled else None,
                 record_notes or None))
            conn.commit(); conn.close()
            st.success("記録を保存しました！"); nav("詳細"); st.rerun()

# =====================================================
# 操作記録追加
# =====================================================
elif st.session_state.page == "操作記録追加" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    conn = get_db()
    machine = conn.execute("SELECT * FROM machines WHERE id=?", (mid,)).fetchone()
    conn.close()

    if st.button("← 詳細に戻る"): nav("詳細"); st.rerun()
    st.subheader(f"👤 稼働日報追加：{machine['name']}")

    with st.form("op_form", clear_on_submit=True):
        c1,c2 = st.columns(2)
        with c1:
            operator       = st.text_input("オペレーター名 ＊必須", placeholder="例：田中")
            operation_date = st.date_input("作業日", value=date.today())
        with c2:
            duration_hours = st.number_input("稼働時間（h）", min_value=0.0, step=0.5, value=0.0)
            location       = st.text_input("作業場所", placeholder="例：第1農場")
        work_content = st.text_area("作業内容", placeholder="例：牧草刈り取り作業")
        op_notes     = st.text_area("その他メモ")

        if st.form_submit_button("✅ 保存する", use_container_width=True, type="primary"):
            if not operator.strip():
                st.error("オペレーター名を入力してください")
            else:
                conn = get_db()
                conn.execute("""INSERT INTO operation_logs
                    (machine_id,operator,operation_date,duration_hours,location,work_content,notes)
                    VALUES (?,?,?,?,?,?,?)""",
                    (mid,operator.strip(),str(operation_date),
                     duration_hours if duration_hours>0 else None,
                     location or None,work_content or None,op_notes or None))
                conn.commit(); conn.close()
                st.success("稼働日報を保存しました！"); nav("詳細"); st.rerun()

# =====================================================
# 基本情報編集
# =====================================================
elif st.session_state.page == "基本情報編集" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    conn = get_db()
    machine = conn.execute("SELECT * FROM machines WHERE id=?", (mid,)).fetchone()
    conn.close()

    if st.button("← 詳細に戻る"): nav("詳細"); st.rerun()
    st.subheader(f"✏️ 基本情報を編集：{machine['name']}")

    with st.form("edit_form"):
        name     = st.text_input("重機名 ＊必須", value=machine["name"])
        cat_idx  = CATEGORIES.index(machine["category"]) if machine["category"] in CATEGORIES else 0
        category = st.selectbox("カテゴリ", CATEGORIES, index=cat_idx)
        c1,c2 = st.columns(2)
        with c1:
            manufacturer  = st.text_input("メーカー", value=machine["manufacturer"] or "")
            plate_number  = st.text_input("ナンバー", value=machine["plate_number"] or "")
            purchase_date = st.date_input("購入日", value=parse_date(machine["purchase_date"]))
        with c2:
            model          = st.text_input("型式・モデル", value=machine["model"] or "")
            serial_number  = st.text_input("シリアル番号", value=machine["serial_number"] or "")
            purchase_price = st.number_input("購入価格（円）", min_value=0, step=10000, value=machine["purchase_price"] or 0)
        notes = st.text_area("メモ", value=machine["notes"] or "")

        if st.form_submit_button("✅ 保存する", use_container_width=True, type="primary"):
            if not name.strip():
                st.error("重機名を入力してください")
            else:
                conn = get_db()
                conn.execute("""UPDATE machines SET name=?,category=?,manufacturer=?,model=?,
                             purchase_date=?,plate_number=?,serial_number=?,purchase_price=?,notes=?
                             WHERE id=?""",
                             (name.strip(),category,manufacturer or None,model or None,
                              str(purchase_date) if purchase_date else None,
                              plate_number or None,serial_number or None,
                              purchase_price if purchase_price>0 else None,
                              notes or None, mid))
                conn.commit(); conn.close()
                st.success("更新しました！"); nav("詳細"); st.rerun()

# =====================================================
# レポート
# =====================================================
elif st.session_state.page == "レポート":
    st.subheader("📊 コスト・稼働レポート")
    conn = get_db()
    twelve_ago = (date.today().replace(day=1) - timedelta(days=365)).isoformat()
    this_year  = str(date.today().year)

    # 期限アラート（90日以内）
    st.markdown("### 🚨 期限アラート（90日以内）")
    alert_rows = conn.execute("""SELECT m.name, s.next_shaken_date, s.jibaiseki_expire, s.insurance_expire
        FROM machines m LEFT JOIN machine_status s ON m.id=s.machine_id
        WHERE COALESCE(m.is_disposed,0)=0""").fetchall()
    alert_items = []
    for row in alert_rows:
        for label, d in [("車検",row["next_shaken_date"]),("自賠責保険",row["jibaiseki_expire"]),("任意保険",row["insurance_expire"])]:
            days = days_until(d)
            if days is not None and days <= 90:
                alert_items.append({"重機名":row["name"],"種別":label,"期限日":d,"残り日数":days})
    if alert_items:
        df_a = pd.DataFrame(alert_items).sort_values("残り日数")
        st.dataframe(df_a, use_container_width=True, hide_index=True)
    else:
        st.success("今後90日以内に期限を迎える車検・保険はありません")

    st.markdown("---")

    # 月別コスト
    st.markdown("### 📊 月別整備・維持コスト（過去12ヶ月）")
    df_r = pd.read_sql_query("""SELECT r.record_date, r.cost, r.record_type
        FROM records r JOIN machines m ON r.machine_id=m.id
        WHERE r.cost IS NOT NULL AND r.record_date >= ?""", conn, params=(twelve_ago,))
    if not df_r.empty:
        df_r["month"] = pd.to_datetime(df_r["record_date"]).dt.strftime("%Y-%m")
        monthly = df_r.groupby(["month","record_type"])["cost"].sum().reset_index()
        chart = alt.Chart(monthly).mark_bar().encode(
            x=alt.X("month:O", title="月", sort=None),
            y=alt.Y("cost:Q", title="費用（円）"),
            color=alt.Color("record_type:N", title="種別"),
            tooltip=["month","record_type","cost"]
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("費用の記録がまだありません")

    st.markdown("---")

    # 重機別コストランキング（今年度）
    st.markdown(f"### 🏆 重機別コストランキング（{this_year}年度）")
    df_c = pd.read_sql_query("""SELECT m.name, SUM(r.cost) AS total_cost
        FROM records r JOIN machines m ON r.machine_id=m.id
        WHERE r.cost IS NOT NULL AND r.record_date LIKE ?
        GROUP BY m.id, m.name ORDER BY total_cost DESC LIMIT 10""",
        conn, params=(f"{this_year}%",))
    if not df_c.empty:
        chart2 = alt.Chart(df_c).mark_bar().encode(
            x=alt.X("total_cost:Q", title="合計費用（円）"),
            y=alt.Y("name:N", title="重機名", sort="-x"),
            tooltip=["name", alt.Tooltip("total_cost:Q", format=",")]
        ).properties(height=max(200, len(df_c)*35))
        st.altair_chart(chart2, use_container_width=True)
    else:
        st.info(f"{this_year}年度の費用記録がありません")

    st.markdown("---")

    # 燃料消費推移
    st.markdown("### ⛽ 燃料消費量推移（月別・過去12ヶ月）")
    df_f = pd.read_sql_query("""SELECT r.record_date, r.fuel_amount
        FROM records r WHERE r.fuel_amount IS NOT NULL AND r.fuel_amount>0
        AND r.record_date >= ?""", conn, params=(twelve_ago,))
    if not df_f.empty:
        df_f["month"] = pd.to_datetime(df_f["record_date"]).dt.strftime("%Y-%m")
        fuel_m = df_f.groupby("month")["fuel_amount"].sum().reset_index()
        chart3 = alt.Chart(fuel_m).mark_line(point=True).encode(
            x=alt.X("month:O", title="月", sort=None),
            y=alt.Y("fuel_amount:Q", title="給油量（L）"),
            tooltip=["month", alt.Tooltip("fuel_amount:Q", format=".0f")]
        ).properties(height=250)
        st.altair_chart(chart3, use_container_width=True)
    else:
        st.info("燃料補給の記録がまだありません")

    st.markdown("---")

    # カテゴリ別コスト
    st.markdown("### 🗂️ カテゴリ別コスト（全期間）")
    df_cat = pd.read_sql_query("""SELECT m.category, SUM(r.cost) AS total_cost
        FROM records r JOIN machines m ON r.machine_id=m.id
        WHERE r.cost IS NOT NULL GROUP BY m.category ORDER BY total_cost DESC""", conn)
    if not df_cat.empty:
        chart4 = alt.Chart(df_cat).mark_arc(innerRadius=50).encode(
            theta=alt.Theta("total_cost:Q"),
            color=alt.Color("category:N", title="カテゴリ"),
            tooltip=["category", alt.Tooltip("total_cost:Q", format=",")]
        ).properties(height=300)
        st.altair_chart(chart4, use_container_width=True)
    else:
        st.info("費用の記録がまだありません")

    conn.close()

# =====================================================
# 部品在庫
# =====================================================
elif st.session_state.page == "部品在庫":
    st.subheader("🔧 部品在庫管理")
    c1,c2 = st.columns([3,1])
    with c2:
        if st.button("➕ 部品を追加", use_container_width=True):
            nav("部品追加"); st.rerun()

    conn = get_db()
    parts = conn.execute("SELECT * FROM parts_inventory ORDER BY category, part_name").fetchall()
    conn.close()

    if not parts:
        st.info("部品が登録されていません。「➕ 部品を追加」から追加してください。")
    else:
        low_stock = [p for p in parts if p["quantity"] <= p["min_quantity"]]
        if low_stock:
            with st.expander(f"⚠️ 在庫不足 {len(low_stock)}件", expanded=True):
                for p in low_stock:
                    st.markdown(f"・**{p['part_name']}** — 残り{p['quantity']}{p['unit']}（最低在庫：{p['min_quantity']}{p['unit']}）")

        current_cat = None
        for p in parts:
            if p["category"] != current_cat:
                current_cat = p["category"]
                st.markdown(f"#### {current_cat or 'その他'}")
            with st.container(border=True):
                c1,c2,c3 = st.columns([3,2,1])
                with c1:
                    alert = "⚠️ " if p["quantity"] <= p["min_quantity"] else ""
                    st.markdown(f"**{alert}{p['part_name']}**")
                    if p["storage_location"]: st.caption(f"保管場所：{p['storage_location']}")
                    if p["compatible_machines"]: st.caption(f"対応機種：{p['compatible_machines']}")
                with c2:
                    badge = "🔴" if p["quantity"] <= p["min_quantity"] else "🟢"
                    st.markdown(f"{badge} **{p['quantity']}{p['unit']}** 在庫")
                    if p["unit_price"]: st.caption(f"単価：{fmt_price(p['unit_price'])}")
                with c3:
                    if st.button("編集", key=f"p_{p['id']}", use_container_width=True):
                        nav("部品編集", part_id=p["id"]); st.rerun()

# =====================================================
# 部品追加
# =====================================================
elif st.session_state.page == "部品追加":
    st.subheader("➕ 部品を追加")
    if st.button("← 在庫一覧に戻る"): nav("部品在庫"); st.rerun()

    with st.form("part_form", clear_on_submit=True):
        c1,c2 = st.columns(2)
        with c1:
            part_name    = st.text_input("部品名 ＊必須", placeholder="例：エンジンオイル 10W-30")
            part_cat     = st.selectbox("カテゴリ", PARTS_CATS)
            quantity     = st.number_input("現在の在庫数", min_value=0.0, step=1.0, value=0.0)
            unit         = st.text_input("単位", value="個", placeholder="個・本・L・セット")
        with c2:
            min_quantity = st.number_input("最低在庫数（これ以下でアラート）", min_value=0.0, step=1.0, value=1.0)
            unit_price   = st.number_input("単価（円）", min_value=0, step=100, value=0)
            storage_loc  = st.text_input("保管場所", placeholder="例：整備棟 棚A-3")
            compatible   = st.text_input("対応機種", placeholder="例：PC130・4tダンプ全般")
        notes = st.text_area("メモ")

        if st.form_submit_button("✅ 登録する", use_container_width=True, type="primary"):
            if not part_name.strip():
                st.error("部品名を入力してください")
            else:
                conn = get_db()
                conn.execute("""INSERT INTO parts_inventory
                    (part_name,category,quantity,unit,min_quantity,unit_price,
                     storage_location,compatible_machines,notes)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (part_name.strip(),part_cat,quantity,unit,min_quantity,
                     unit_price if unit_price>0 else None,
                     storage_loc or None,compatible or None,notes or None))
                conn.commit(); conn.close()
                st.success(f"「{part_name}」を登録しました"); nav("部品在庫"); st.rerun()

# =====================================================
# 部品編集
# =====================================================
elif st.session_state.page == "部品編集":
    pid = st.session_state.get("selected_part_id")
    if not pid: nav("部品在庫"); st.rerun()

    conn = get_db()
    part = conn.execute("SELECT * FROM parts_inventory WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not part: nav("部品在庫"); st.rerun()

    if st.button("← 在庫一覧に戻る"): nav("部品在庫"); st.rerun()
    st.subheader(f"✏️ 部品編集：{part['part_name']}")

    with st.form("part_edit_form"):
        c1,c2 = st.columns(2)
        with c1:
            part_name    = st.text_input("部品名", value=part["part_name"])
            cat_idx      = PARTS_CATS.index(part["category"]) if part["category"] in PARTS_CATS else 0
            part_cat     = st.selectbox("カテゴリ", PARTS_CATS, index=cat_idx)
            quantity     = st.number_input("現在の在庫数", min_value=0.0, step=1.0, value=float(part["quantity"]))
            unit         = st.text_input("単位", value=part["unit"] or "個")
        with c2:
            min_quantity = st.number_input("最低在庫数", min_value=0.0, step=1.0, value=float(part["min_quantity"] or 1))
            unit_price   = st.number_input("単価（円）", min_value=0, step=100, value=part["unit_price"] or 0)
            storage_loc  = st.text_input("保管場所", value=part["storage_location"] or "")
            compatible   = st.text_input("対応機種", value=part["compatible_machines"] or "")
        notes = st.text_area("メモ", value=part["notes"] or "")

        col1,col2 = st.columns(2)
        with col1:
            if st.form_submit_button("✅ 保存する", use_container_width=True, type="primary"):
                conn = get_db()
                conn.execute("""UPDATE parts_inventory SET part_name=?,category=?,quantity=?,unit=?,
                             min_quantity=?,unit_price=?,storage_location=?,compatible_machines=?,
                             notes=?,updated_at=datetime('now','localtime') WHERE id=?""",
                             (part_name,part_cat,quantity,unit,min_quantity,
                              unit_price if unit_price>0 else None,
                              storage_loc or None,compatible or None,notes or None,pid))
                conn.commit(); conn.close()
                st.success("更新しました"); nav("部品在庫"); st.rerun()
        with col2:
            if st.form_submit_button("🗑️ 削除する", use_container_width=True):
                conn = get_db()
                conn.execute("DELETE FROM parts_inventory WHERE id=?", (pid,))
                conn.commit(); conn.close()
                st.success("削除しました"); nav("部品在庫"); st.rerun()
