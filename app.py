# -*- coding: utf-8 -*-
"""
重機管理システム（スマホ優先・クラウド版）
- 保存先は Googleスプレッドシート（sheets_backend.py 経由）。現場のスマホからどこでも開ける。
- 残した機能: 一覧 / 詳細 / 記録追加 / 稼働日報 / 状態・期限更新 / 新規登録 / 編集 / 廃車
- 後回し（事務所向け・このスマホ版では非表示）: レポート / 部品在庫 / 写真アップロード
  → 旧フル機能は app_sqlite_backup.py に保存済み。
"""
import streamlit as st
import streamlit.components.v1 as components
import json
from datetime import date, datetime, timedelta, timezone
import pandas as pd
import altair as alt
import sheets_backend as db
import brand_colors as bc  # グラフの系列色（正本は farm/brand/brand.json）

# スマホで見やすいよう中央寄せ（横長wideにしない）
st.set_page_config(page_title="重機管理", page_icon="🚜", layout="centered",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
.stButton > button { font-size: 16px; padding: 0.6rem 1rem; }
.block-container { padding-top: 2rem; }
/* 右上のGitHub/Forkバッジ・ツールバー・デコレーション・フッターを非表示 */
[data-testid="stToolbar"] { visibility: hidden; height: 0; }
.stAppDeployButton { display: none; }
[data-testid="stDecoration"] { display: none; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
/* 右下のStreamlit製バッジは無料ホスティング層（アプリ外）にあり、CSSでは消せないため対応しない */
</style>
""", unsafe_allow_html=True)

# =====================================================
# 定数（元アプリと同じ。例示は山形・尾花沢向けに変更）
# =====================================================
CATEGORIES   = ["家畜車", "ダンプ", "トラック", "タイヤショベル", "ショベル（ユンボ）", "フォークリフト", "スピードスプレイヤー", "その他"]
STATUSES     = ["稼働中", "待機中", "整備中", "車検中", "廃車"]
RECORD_TYPES = ["定期点検", "修理", "車検", "燃料補給", "オイル交換", "タイヤ交換", "バッテリー交換", "その他"]
STATUS_ICONS = {"稼働中": "🟢", "待機中": "🔵", "整備中": "🟡", "車検中": "🟠", "廃車": "⚫", "未設定": "⚪"}
# 一覧の並び替えメニュー（機械/農機用・先頭が既定）
SORT_OPTS_MACHINE  = ["カテゴリ順", "名前順", "状態順", "配備場所順", "車検・保険が近い順", "登録が新しい順"]

# --- 農機（農業機械）用の定数 ---
# 重機と同じ machines / machine_status テーブルを共有し、machine_type 列（"重機"/"農機"）で区別する。
# カテゴリだけ農機用に差し替え、稼働状態・整備記録・稼働日報などの仕組みは重機と共通で使う。
AGRI_CATEGORIES = ["トラクター", "田植え機", "コンバイン", "乾燥機", "籾摺り・調製機",
                   "管理機・耕運機", "モア・草刈機", "ロールベーラー", "ラッピングマシン",
                   "マニュアスプレッダ", "防除機", "運搬車・軽トラ", "作業機・アタッチメント", "その他"]
FUEL_TYPES     = ["", "軽油", "ガソリン", "混合", "その他"]        # 燃料種別（免税軽油の把握とセット）
TAX_FREE_OPTS  = ["", "対象", "対象外"]                            # 農業用免税軽油の対象か
AGRI_WORK_TYPES = ["田起こし", "代掻き", "田植え", "防除", "収穫", "乾燥・調製",
                   "草刈り", "堆肥散布", "運搬", "その他"]         # 対応作業（本体タグ・稼働日報で使う）

# --- 施設（建物・設備）用の定数 ---
FACILITY_CATEGORIES   = ["牛舎", "堆肥舎", "飼料倉庫", "事務所", "機械庫", "その他"]
FACILITY_STATUSES     = ["使用中", "一部使用", "休止中", "解体予定"]
FACILITY_RECORD_TYPES = ["法定点検", "定期点検", "修繕", "設備更新", "その他"]
FACILITY_STATUS_ICONS = {"使用中": "🟢", "一部使用": "🟡", "休止中": "⚪", "解体予定": "⚫", "未設定": "⚪"}
# 一覧の並び替えメニュー（施設用・先頭が既定）
SORT_OPTS_FACILITY = ["種類順", "名前順", "状態順", "場所順", "点検期限が近い順", "登録が新しい順"]
# 法定点検の枠（ラベル, facility_statusの期限カラム名）
LEGAL_CHECKS = [("消防設備", "fire_expire"), ("電気設備", "electrical_expire"), ("浄化槽", "septic_expire")]

# 日別ページの曜日表示（月曜=0）
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


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


# Streamlit Cloud のサーバは UTC で動くため、date.today() は日本時間の朝9時まで前日を返す。
# 現場は朝に記録を付けるので、日付は必ず日本時間で判断する。
_JST = timezone(timedelta(hours=9))


def today_jst():
    """今日の日付（日本時間）。"""
    return datetime.now(_JST).date()


def days_until(d):
    s = sval(d)
    if not s:
        return None
    try:
        return (date.fromisoformat(s) - today_jst()).days
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


# 購入日として選べる範囲。古い保有機（1990年代購入）を登録できるようにするため、
# Streamlit 既定の「今日の前後10年」ではなくここで明示する
PURCHASE_MIN_DATE = date(1990, 1, 1)


def purchase_date_value(s):
    """台帳の購入日を date_input の初期値にする。範囲外の値は範囲内に丸める。

    範囲外（1990年より前・未来日）のまま value に渡すと Streamlit が例外を投げ、
    編集画面そのものが開けなくなるため。
    """
    d = parse_date(s)
    if d is None:
        return None
    return min(max(d, PURCHASE_MIN_DATE), today_jst())


def deadline_range():
    """車検・点検・保険など「期限」の入力で選べる範囲（1990年〜10年先の年末）。

    購入日と違って未来を入れる項目なので上限を先に取る。10年で切るのは
    2099年のような打ち間違いを止めるため。
    """
    return PURCHASE_MIN_DATE, date(today_jst().year + 10, 12, 31)


def deadline_value(s):
    """台帳の期限日を date_input の初期値にする。範囲外の値は範囲内に丸める。"""
    d = parse_date(s)
    if d is None:
        return None
    lo, hi = deadline_range()
    return min(max(d, lo), hi)


# --- 並び替え用のヘルパー ---
_FAR = 10 ** 9  # 期限なしを最後尾に送るための大きな残日数


def nearest_days(*dates):
    """複数の期限のうち一番近い残日数を返す。期限が一つも無ければ末尾扱い。"""
    ds = [days_until(d) for d in dates]
    ds = [x for x in ds if x is not None]
    return min(ds) if ds else _FAR


def status_rank(status, order):
    """状態を決められた並び順の番号に変換。一覧に無い値（未設定など）は末尾。"""
    return order.index(status) if status in order else len(order)


def sort_rows(rows, sort_by, status_order):
    """一覧の行を選択された基準で並び替える（機械・施設で共通）。
    期限順は各行に事前計算した r['_expire_days']（一番近い残日数）を使う。
    status_order=状態の並び順。"""
    if sort_by == "名前順":
        rows.sort(key=lambda r: r["name"])
    elif sort_by == "状態順":
        rows.sort(key=lambda r: (status_rank(r["status"], status_order), r["name"]))
    elif sort_by in ("配備場所順", "場所順"):
        rows.sort(key=lambda r: (r["location"], r["name"]))
    elif sort_by in ("車検・保険が近い順", "点検期限が近い順"):
        rows.sort(key=lambda r: r.get("_expire_days", _FAR))
    elif sort_by == "登録が新しい順":
        rows.sort(key=lambda r: -(to_int(r["id"]) or 0))
    else:  # カテゴリ順 / 種類順（既定）
        rows.sort(key=lambda r: (r["category"], r["name"]))


# =====================================================
# 画面遷移
# =====================================================
for k, v in [("page", "一覧"), ("selected_machine_id", None),
             ("mode", "machine"), ("selected_facility_id", None),
             ("edit_record_id", None)]:  # 明細（整備記録・稼働日報・施設記録）の編集対象id
    if k not in st.session_state:
        st.session_state[k] = v


def nav(page, machine_id=None, facility_id=None):
    st.session_state.page = page
    if machine_id is not None:
        st.session_state.selected_machine_id = machine_id
    if facility_id is not None:
        st.session_state.selected_facility_id = facility_id


def scroll_restore(prefix):
    """詳細から戻ってきたとき、見ていた行（{prefix}-{id}）の位置までスクロール。"""
    key = "scroll_back"
    if st.session_state.get(key):
        tgt = f"{prefix}-{st.session_state.pop(key)}"
        components.html(
            f"""<script>
            const doc = window.parent.document;
            function go() {{
                const el = doc.getElementById({json.dumps(tgt)});
                if (el) {{ el.scrollIntoView({{block: "center"}}); return true; }}
                return false;
            }}
            if (!go()) setTimeout(go, 200);
            </script>""",
            height=0,
        )


def render_delete_section(table, rid, back_page, label="この記録"):
    """明細（整備記録・稼働日報・施設記録）の削除UI。必ず st.form の外で呼ぶこと。
    現場スマホでの誤タップを防ぐため、削除→確認の2段階にしている。"""
    st.divider()
    armed = f"arm_del_{table}_{rid}"  # 記録ごとに確認状態を持ち、実行後に破棄する
    if not st.session_state.get(armed):
        if st.button(f"🗑️ {label}を削除する", key=f"del_{table}_{rid}",
                     use_container_width=True):
            st.session_state[armed] = True
            st.rerun()
    else:
        st.warning("本当に削除しますか？ 削除すると元に戻せません。")
        c1, c2 = st.columns(2)
        if c1.button("✅ はい、削除する", key=f"delyes_{table}_{rid}",
                     use_container_width=True, type="primary"):
            db.delete(table, rid)
            st.session_state.pop(armed, None)
            st.success("削除しました"); nav(back_page); st.rerun()
        if c2.button("キャンセル", key=f"delno_{table}_{rid}",
                     use_container_width=True):
            st.session_state.pop(armed, None)
            st.rerun()


# =====================================================
# ヘッダーナビ（スマホ向けに2ボタンへ削減）
# =====================================================
st.title("🚜 重機・農機・施設管理")

# 重機 / 農機 / 施設 の切替（選択中を強調）
mode = st.session_state.get("mode", "machine")
mc1, mc2, mc3 = st.columns(3)
with mc1:
    if st.button("🚜 重機", use_container_width=True,
                 type=("primary" if mode == "machine" else "secondary")):
        st.session_state.mode = "machine"; nav("一覧"); st.rerun()
with mc2:
    if st.button("🌾 農機", use_container_width=True,
                 type=("primary" if mode == "agri" else "secondary")):
        st.session_state.mode = "agri"; nav("一覧"); st.rerun()
with mc3:
    if st.button("🏢 施設", use_container_width=True,
                 type=("primary" if mode == "facility" else "secondary")):
        st.session_state.mode = "facility"; nav("施設一覧"); st.rerun()

# 重機と農機は同じ machines テーブルを machine_type で共有する。
# モードから「区別に必要な値」をここで一括導出し、以降の重機系ページで使い回す。
is_agri   = (mode == "agri")
MTYPE     = "農機" if is_agri else "重機"           # machine_type 列の値（一覧のフィルタ・新規登録で使う）
CATS      = AGRI_CATEGORIES if is_agri else CATEGORIES
UNIT      = "農機" if is_agri else "重機"
HEAD_ICON = "🌾" if is_agri else "🚜"

# モード内のナビ（重機・農機は「一覧／登録／日別／ダッシュ」の4つ。
# 日別とダッシュボードは重機・農機・施設を横断して見るページ）
if mode in ("machine", "agri"):
    n1, n2, n3, n4 = st.columns(4)
    with n1:
        if st.button("📋 一覧", use_container_width=True):
            nav("一覧"); st.rerun()
    with n2:
        if st.button("➕ 登録", use_container_width=True):
            nav("登録"); st.rerun()
    with n3:
        if st.button("📅 日別", use_container_width=True):
            nav("日別"); st.rerun()
    with n4:
        if st.button("📊 ダッシュ", use_container_width=True):
            nav("ダッシュ"); st.rerun()
else:
    n1, n2, n3 = st.columns(3)
    with n1:
        if st.button("📋 施設一覧", use_container_width=True):
            nav("施設一覧"); st.rerun()
    with n2:
        if st.button("➕ 施設を登録", use_container_width=True):
            nav("施設登録"); st.rerun()
    with n3:
        if st.button("📊 ダッシュ", use_container_width=True):
            nav("ダッシュ"); st.rerun()
st.divider()

page = st.session_state.page

# =====================================================
# 一覧
# =====================================================
if page == "一覧":
    st.subheader(f"{UNIT}一覧")
    # カテゴリはタップですぐ切り替わるボタン（ピル）型。再タップ/「すべて」で解除
    # key はモード別にして、重機↔農機を切り替えても選択状態が混ざらないようにする
    filter_cat = st.pills("カテゴリ", ["すべて"] + CATS,
                          selection_mode="single", default="すべて", key=f"fc_{mode}") or "すべて"
    c1, c2 = st.columns([3, 2])
    with c1:
        filter_status = st.selectbox("状態", ["すべて"] + STATUSES, key=f"fs_{mode}")
    with c2:
        show_disposed = st.checkbox("廃車済みも表示", value=False, key=f"fsd_{mode}")
    # 並び替え。key をモード別にして重機↔農機で選択を独立記憶させる
    sort_by = st.selectbox("並び替え", SORT_OPTS_MACHINE, key=f"sort_{mode}")

    machines = db.read("machines")
    statuses = {sval(s.get("machine_id")): s for s in db.read("machine_status")}

    # 結合＋フィルタ
    rows = []
    for m in machines:
        mid = sval(m.get("id"))
        # machine_type が今のモード（重機/農機）のものだけ。空欄は重機扱い（既存データの保険）。
        if (sval(m.get("machine_type")) or "重機") != MTYPE:
            continue
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
            # 車検・自賠責・任意保険のうち一番近い残日数（「期限が近い順」で使う）
            "_expire_days": nearest_days(s.get("next_shaken_date"),
                                         s.get("jibaiseki_expire"),
                                         s.get("insurance_expire")),
        })
    sort_rows(rows, sort_by, STATUSES)

    if not rows:
        st.info(f"該当する{UNIT}がありません。「➕ 新規登録」から追加してください。")
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
                # 各カードに不可視アンカー（戻ったときここへスクロールする目印）
                st.markdown(f'<span id="machine-{m["id"]}"></span>{disp}　{icon} {m["status"]}',
                            unsafe_allow_html=True)
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

        # 詳細から戻ってきたとき、見ていた重機の位置まで自動スクロール
        scroll_restore("machine")

# =====================================================
# 📅 日別の作業
# 「その日に何をしたか」を機械をまたいで見返すページ。
# 機械ごとの詳細（縦）だけでは日単位の全体像が分からないので、日付軸（横）で
# 稼働日報と整備記録の両方を1画面に集める。重機・農機はまとめて表示し、
# 必要なら種別で絞り込む。
# =====================================================
elif page == "日別":
    st.subheader("📅 日別の作業")

    # 表示中の日付は session_state に持つ（前日/翌日ボタンで動かすため）。
    # date_input に key を付けないのは、ボタンで書き換えた値をそのまま反映させるため。
    if "daily_date" not in st.session_state:
        st.session_state.daily_date = today_jst()

    d1, d2, d3 = st.columns([1, 2, 1])
    with d1:
        if st.button("◀ 前日", use_container_width=True):
            st.session_state.daily_date -= timedelta(days=1); st.rerun()
    with d3:
        if st.button("翌日 ▶", use_container_width=True):
            st.session_state.daily_date += timedelta(days=1); st.rerun()
    with d2:
        picked = st.date_input("日付", value=st.session_state.daily_date,
                               label_visibility="collapsed")
    if picked and picked != st.session_state.daily_date:
        st.session_state.daily_date = picked; st.rerun()

    the_day = st.session_state.daily_date
    d_str = str(the_day)
    st.caption(f"{the_day.year}年{the_day.month}月{the_day.day}日"
               f"（{WEEKDAYS[the_day.weekday()]}）"
               + ("　＝今日" if the_day == today_jst() else ""))

    all_ops = db.read("operation_logs")
    all_recs = db.read("records")

    # 「最後に作業したのいつだっけ」用のショートカット（記録のある日だけ並べる）
    rec_days = sorted({sval(o.get("operation_date")) for o in all_ops}
                      | {sval(r.get("record_date")) for r in all_recs}, reverse=True)
    rec_days = [x for x in rec_days if x][:6]
    if rec_days:
        with st.expander("🕘 記録のある日にジャンプ"):
            for i in range(0, len(rec_days), 3):
                cols = st.columns(3)
                for col, ds in zip(cols, rec_days[i:i + 3]):
                    with col:
                        if st.button(ds, key=f"jump_{ds}", use_container_width=True):
                            jumped = parse_date(ds)
                            if jumped:
                                st.session_state.daily_date = jumped; st.rerun()

    # 種別の絞り込み（既定はすべて＝重機と農機をまとめて見る）
    kind = st.pills("種別", ["すべて", "🚜 重機", "🌾 農機"], selection_mode="single",
                    default="すべて", key="daily_kind") or "すべて"

    machines = {sval(m.get("id")): m for m in db.read("machines")}

    def m_type(mid):
        """その機械が重機か農機か。空欄は重機扱い（既存データの保険）。"""
        return sval(machines.get(sval(mid), {}).get("machine_type")) or "重機"

    def m_label(mid):
        """カード見出し用の機械名（アイコン付き）。台帳から消えた機械にも耐える。"""
        m = machines.get(sval(mid))
        if not m:
            return "（台帳にない機械）"
        return f"{'🌾' if m_type(mid) == '農機' else '🚜'} {sval(m.get('name'))}"

    def keep(mid):
        if kind == "🚜 重機":
            return m_type(mid) == "重機"
        if kind == "🌾 農機":
            return m_type(mid) == "農機"
        return True

    ops = [o for o in all_ops
           if sval(o.get("operation_date")) == d_str and keep(o.get("machine_id"))]
    recs = [r for r in all_recs
            if sval(r.get("record_date")) == d_str and keep(r.get("machine_id"))]
    ops.sort(key=lambda o: m_label(o.get("machine_id")))
    recs.sort(key=lambda r: m_label(r.get("machine_id")))

    st.divider()
    if not ops and not recs:
        st.info("この日の記録はありません。")
    else:
        # その日の合計（誰がどれだけ動かしたか・いくら整備にかかったかを一目で）
        total_h = sum(to_float(o.get("duration_hours")) or 0 for o in ops)
        total_cost = sum(to_int(r.get("cost")) or 0 for r in recs)
        c1, c2, c3 = st.columns(3)
        c1.metric("日報のあった台数", f"{len({sval(o.get('machine_id')) for o in ops})}台")
        c2.metric("延べ稼働時間", f"{total_h:.1f}h" if total_h else "—")
        c3.metric("整備記録", f"{len(recs)}件")

        # --- 稼働日報 ---
        if ops:
            st.markdown(f"#### 👤 稼働日報　{len(ops)}件")
            for o in ops:
                with st.container(border=True):
                    dur = to_float(o.get("duration_hours"))
                    st.markdown(f"**{m_label(o.get('machine_id'))}**"
                                + (f"　{dur:.1f}h" if dur else ""))
                    caps = [f"オペレーター：{sval(o.get('operator')) or '未記入'}"]
                    if sval(o.get("location")):
                        caps.append(f"場所：{sval(o.get('location'))}")
                    st.caption("　|　".join(caps))
                    if sval(o.get("work_content")):
                        st.write(sval(o.get("work_content")))
                    if sval(o.get("notes")):
                        st.caption(f"メモ：{sval(o.get('notes'))}")
                    if machines.get(sval(o.get("machine_id"))):
                        if st.button("🔧 この機械の詳細", key=f"daily_op_{sval(o.get('id'))}",
                                     use_container_width=True):
                            nav("詳細", o.get("machine_id")); st.rerun()

        # --- 整備記録 ---
        if recs:
            st.markdown(f"#### 🔧 整備記録　{len(recs)}件"
                        + (f"　費用計 {fmt_price(total_cost)}" if total_cost else ""))
            for r in recs:
                with st.container(border=True):
                    st.markdown(f"**{m_label(r.get('machine_id'))}**"
                                f"　{sval(r.get('record_type'))}"
                                + (f"　{fmt_price(r.get('cost'))}" if to_int(r.get("cost")) else ""))
                    if sval(r.get("description")):
                        st.write(sval(r.get("description")))
                    caps = []
                    if sval(r.get("worker")):
                        caps.append(f"担当：{sval(r.get('worker'))}")
                    if to_int(r.get("hour_meter")):
                        caps.append(f"アワーメーター：{to_int(r.get('hour_meter')):,}h")
                    if to_float(r.get("fuel_amount")):
                        caps.append(f"給油量：{to_float(r.get('fuel_amount')):.1f}L")
                    if caps:
                        st.caption("　|　".join(caps))
                    if machines.get(sval(r.get("machine_id"))):
                        if st.button("🔧 この機械の詳細", key=f"daily_rec_{sval(r.get('id'))}",
                                     use_container_width=True):
                            nav("詳細", r.get("machine_id")); st.rerun()

# =====================================================
# 📊 ダッシュボード
# 台帳の全体像を1画面で見るページ（重機・農機・施設を横断）。
# 設計の考え方: 数字が出ない枠を隠さず「未入力」と見せる。
# 空欄のままだと期限アラートが鳴らず、修理費の部門配賦も効かないため、
# 「何を入れれば効くようになるか」が分かる形にしている。
# =====================================================
elif page == "ダッシュ":
    st.subheader("📊 ダッシュボード")

    machines  = db.read("machines")
    m_status  = {sval(s.get("machine_id")): s for s in db.read("machine_status")}
    records   = db.read("records")
    ops       = db.read("operation_logs")
    facilities = db.read("facilities")
    f_status  = {sval(s.get("facility_id")): s for s in db.read("facility_status")}
    f_records = db.read("facility_records")

    live  = [m for m in machines if to_int(m.get("is_disposed")) != 1]
    juki  = [m for m in live if (sval(m.get("machine_type")) or "重機") == "重機"]
    nouki = [m for m in live if sval(m.get("machine_type")) == "農機"]

    # --- 保有台数 ---
    c1, c2, c3 = st.columns(3)
    c1.metric("🚜 重機", f"{len(juki)}台")
    c2.metric("🌾 農機", f"{len(nouki)}台")
    c3.metric("🏢 施設", f"{len(facilities)}件")
    if len(machines) - len(live):
        st.caption(f"※廃車・売却済み {len(machines) - len(live)}台は台数に含めていません")

    # --- 🚨 期限アラート ---
    st.markdown("### 🚨 期限アラート（90日以内）")
    alerts = []
    for m in live:
        s = m_status.get(sval(m.get("id")), {})
        for label, key in [("車検", "next_shaken_date"), ("自賠責", "jibaiseki_expire"),
                           ("任意保険", "insurance_expire"), ("点検予定", "next_inspection_date")]:
            d = days_until(s.get(key))
            if d is not None and d <= 90:
                alerts.append({"対象": sval(m.get("name")), "種別": label,
                               "期限日": sval(s.get(key)), "残り日数": d})
    for f in facilities:
        s = f_status.get(sval(f.get("id")), {})
        for label, key in LEGAL_CHECKS:
            d = days_until(s.get(key))
            if d is not None and d <= 90:
                alerts.append({"対象": sval(f.get("name")), "種別": f"{label}点検",
                               "期限日": sval(s.get(key)), "残り日数": d})
    if alerts:
        st.dataframe(pd.DataFrame(alerts).sort_values("残り日数"),
                     hide_index=True, use_container_width=True)
    else:
        # 期限が1件も入っていない状態で「アラートなし」だけ出すと安心してしまうため、
        # 監視できている台数を必ず添える
        watched = sum(1 for m in live
                      if nearest_days(m_status.get(sval(m.get("id")), {}).get("next_shaken_date"),
                                      m_status.get(sval(m.get("id")), {}).get("jibaiseki_expire"),
                                      m_status.get(sval(m.get("id")), {}).get("insurance_expire")) < _FAR)
        if watched == 0:
            st.warning(f"期限が登録されている機械が0台のため、**アラートは鳴りません**（対象 {len(live)}台）。"
                       "各機械の「📍 状態・保険情報を更新する」から車検・自賠責・任意保険の期限を入れてください")
        else:
            st.success(f"90日以内に期限を迎えるものはありません（期限を監視できているのは {watched}/{len(live)}台）")

    # --- 📋 台帳の入力状況 ---
    st.markdown("### 📋 台帳の入力状況")
    st.caption("空欄が多いと、期限アラートが鳴らず、修理費を部門に振り分けるときも「要確認」になります")
    for label, key in [("配備場所", "location"), ("車検期日", "next_shaken_date"),
                       ("自賠責の期限", "jibaiseki_expire"), ("任意保険の期限", "insurance_expire")]:
        n = sum(1 for m in live if sval(m_status.get(sval(m.get("id")), {}).get(key)))
        st.progress(n / len(live) if live else 0.0, text=f"{label}：{n} / {len(live)}台")
    for label, key in LEGAL_CHECKS:
        n = sum(1 for f in facilities if sval(f_status.get(sval(f.get("id")), {}).get(key)))
        st.progress(n / len(facilities) if facilities else 0.0,
                    text=f"施設の{label}点検期限：{n} / {len(facilities)}件")

    # --- 🗂️ 保有の内訳 ---
    st.markdown("### 🗂️ 保有の内訳")
    df_m = pd.DataFrame([{
        "種別": (sval(m.get("machine_type")) or "重機"),
        "カテゴリ": sval(m.get("category")) or "未設定",
        "状態": sval(m_status.get(sval(m.get("id")), {}).get("status")) or "未設定",
        "配備場所": sval(m_status.get(sval(m.get("id")), {}).get("location")) or "未設定",
    } for m in live])
    if df_m.empty:
        st.info("機械が登録されていません")
    else:
        cat = df_m.groupby(["カテゴリ", "種別"]).size().reset_index(name="台数")
        # 色は対象（重機/農機）に固定する。絞り込みで系列が減っても色は動かさない
        kd, kr = bc.fixed_scale(["重機", "農機"], present=set(cat["種別"]))
        st.altair_chart(alt.Chart(cat).mark_bar().encode(
            x=alt.X("台数:Q", title="台数"),
            y=alt.Y("カテゴリ:N", title="", sort="-x"),
            color=alt.Color("種別:N", title="種別", scale=alt.Scale(domain=kd, range=kr)),
            tooltip=["カテゴリ", "種別", "台数"],
        ).properties(height=max(200, len(cat) * 32)), use_container_width=True)
        cc1, cc2 = st.columns(2)
        with cc1:
            st.caption("状態別")
            st.dataframe(df_m["状態"].value_counts().rename_axis("状態").reset_index(name="台数"),
                         hide_index=True, use_container_width=True)
        with cc2:
            st.caption("配備場所別")
            st.dataframe(df_m["配備場所"].value_counts().rename_axis("配備場所").reset_index(name="台数"),
                         hide_index=True, use_container_width=True)

    # --- 🔧 整備記録の動き ---
    st.markdown("### 🔧 整備記録の動き")
    names = {sval(m.get("id")): sval(m.get("name")) for m in machines}
    df_r = pd.DataFrame([{
        "機械": names.get(sval(r.get("machine_id")), "（台帳にない機械）"),
        "月": sval(r.get("record_date"))[:7],
        "種別": sval(r.get("record_type")) or "未設定",
        "費用": to_int(r.get("cost")) or 0,
        "給油量": to_float(r.get("fuel_amount")) or 0.0,
    } for r in records if sval(r.get("record_date"))])
    if df_r.empty:
        st.info("整備記録がまだありません")
    else:
        total_cost = int(df_r["費用"].sum())
        total_fuel = float(df_r["給油量"].sum())
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("記録件数", f"{len(df_r)}件")
        rc2.metric("費用の合計", f"¥{total_cost:,}" if total_cost else "未入力")
        rc3.metric("給油量の合計", f"{total_fuel:.0f}L" if total_fuel else "未入力")

        m_cnt = df_r.groupby(["月", "種別"]).size().reset_index(name="件数")
        # 整備の種別ごとに色を固定（月が変わっても同じ種別は同じ色）。
        # 凡例は実際に記録がある種別だけに絞る（色の対応は絞っても変わらない）
        td, tr = bc.fixed_scale(RECORD_TYPES + ["未設定"], present=set(m_cnt["種別"]))
        st.altair_chart(alt.Chart(m_cnt).mark_bar().encode(
            x=alt.X("月:O", title="月"),
            y=alt.Y("件数:Q", title="件数"),
            color=alt.Color("種別:N", title="種別", scale=alt.Scale(domain=td, range=tr)),
            tooltip=["月", "種別", "件数"],
        ).properties(height=260), use_container_width=True)

        if total_cost:
            top = (df_r.groupby("機械")["費用"].sum().reset_index()
                   .sort_values("費用", ascending=False).head(10))
            st.caption("費用の大きい機械 上位10")
            st.altair_chart(alt.Chart(top).mark_bar(color=bc.series(1)[0]).encode(
                x=alt.X("費用:Q", title="費用（円）"),
                y=alt.Y("機械:N", title="", sort="-x"),
                tooltip=["機械", alt.Tooltip("費用:Q", format=",")],
            ).properties(height=max(200, len(top) * 32)), use_container_width=True)
        else:
            st.info("整備記録に金額が1件も入っていないため、費用のグラフは出せません"
                    "（記録追加の「費用（円）」欄に入れると、ここに月別・機械別で出ます）")

    # --- ⏱️ 整備記録の空白 ---
    st.markdown("### ⏱️ しばらく整備記録がない機械")
    last = {}
    for r in records:
        mid, d = sval(r.get("machine_id")), sval(r.get("record_date"))
        if d and (mid not in last or d > last[mid]):
            last[mid] = d
    aged = sorted([(m, last[sval(m.get("id"))]) for m in live if sval(m.get("id")) in last],
                  key=lambda x: x[1])[:5]
    never = [m for m in live if sval(m.get("id")) not in last]
    if aged:
        st.dataframe(pd.DataFrame([{
            "機械": sval(m.get("name")), "最終の記録": d,
            "経過日数": -(days_until(d) or 0),
        } for m, d in aged]), hide_index=True, use_container_width=True)
    if never:
        st.caption(f"※整備記録が1件もない機械が {len(never)}台あります（対象 {len(live)}台）")

    # --- 👤 稼働日報 ---
    st.markdown("### 👤 稼働日報")
    df_o = pd.DataFrame([{
        "月": sval(o.get("operation_date"))[:7],
        "オペレーター": sval(o.get("operator")) or "未記入",
        "稼働時間": to_float(o.get("duration_hours")) or 0.0,
    } for o in ops if sval(o.get("operation_date"))])
    if df_o.empty:
        st.info("稼働日報がまだ1件もありません。日報が貯まると、月別の稼働時間と担当者別の実績がここに出ます")
    else:
        oc1, oc2 = st.columns(2)
        oc1.metric("日報の件数", f"{len(df_o)}件")
        oc2.metric("延べ稼働時間", f"{df_o['稼働時間'].sum():.1f}h")
        by_month = df_o.groupby("月")["稼働時間"].sum().reset_index()
        st.altair_chart(alt.Chart(by_month).mark_bar(color=bc.series(1)[0]).encode(
            x=alt.X("月:O", title="月"),
            y=alt.Y("稼働時間:Q", title="稼働時間（h）"),
            tooltip=["月", alt.Tooltip("稼働時間:Q", format=".1f")],
        ).properties(height=240), use_container_width=True)
        st.caption("オペレーター別")
        st.dataframe(df_o.groupby("オペレーター")
                     .agg(件数=("稼働時間", "size"), 稼働時間=("稼働時間", "sum"))
                     .reset_index().sort_values("稼働時間", ascending=False),
                     hide_index=True, use_container_width=True)

    # --- 🏢 施設 ---
    st.markdown("### 🏢 施設")
    if not facilities:
        st.info("施設がまだ登録されていません")
    else:
        df_f = pd.DataFrame([{
            "種類": sval(f.get("category")) or "未設定",
            "状態": sval(f_status.get(sval(f.get("id")), {}).get("status")) or "未設定",
        } for f in facilities])
        fc1, fc2 = st.columns(2)
        with fc1:
            st.caption("種類別")
            st.dataframe(df_f["種類"].value_counts().rename_axis("種類").reset_index(name="件数"),
                         hide_index=True, use_container_width=True)
        with fc2:
            st.caption("状態別")
            st.dataframe(df_f["状態"].value_counts().rename_axis("状態").reset_index(name="件数"),
                         hide_index=True, use_container_width=True)
        st.caption(f"点検・修繕の記録：{len(f_records)}件")

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
        st.session_state.scroll_back = mid  # 一覧で この重機の位置までスクロールさせる
        nav("一覧"); st.rerun()
    # この機械が農機かどうかは machine_type で判定（詳細は id で開くのでモードに依存しない）
    m_is_agri = sval(machine.get("machine_type")) == "農機"
    cur_status = sval(status.get("status")) if status else "未設定"
    icon = STATUS_ICONS.get(cur_status, "⚪")
    st.subheader(f"{'🌾' if m_is_agri else '🚜'} {sval(machine.get('name'))}")
    st.markdown(f"{icon} **{cur_status}**　|　{sval(machine.get('category'))}")
    if to_int(machine.get("is_disposed")) == 1:
        st.warning("この重機は廃車・売却済みです")

    t1, t2, t3, t4, t5 = st.tabs(["📋 基本情報", "📍 状態・保険", "🔧 整備記録", "👤 稼働日報", "🗑️ 廃車・売却"])

    def show_date(label, key):
        """期限の表示。30日以内なら残り日数を添える（基本情報・状態の両タブで使う）"""
        v = sval(status.get(key)) if status else ""
        d = days_until(v)
        extra = f"　⚠️ あと{d}日" if d is not None and d <= 30 else ""
        st.markdown(f"**{label}**：{v or '未設定'}{extra}")

    # --- 基本情報 ---
    with t1:
        for label, key in [("カテゴリ", "category"), ("メーカー", "manufacturer"),
                           ("型式・モデル", "model"), ("ナンバー", "plate_number"),
                           ("シリアル番号", "serial_number"), ("購入日", "purchase_date")]:
            st.markdown(f"**{label}**：{sval(machine.get(key)) or '未登録'}")
        st.markdown(f"**購入価格**：{fmt_price(machine.get('purchase_price'))}")
        show_date("車検期日", "next_shaken_date")
        # 農機だけの項目（作業機・対応作業・燃料・免税軽油）
        if m_is_agri:
            for label, key in [("作業機・アタッチメント", "attachments"),
                               ("対応作業", "work_types"), ("燃料", "fuel_type")]:
                st.markdown(f"**{label}**：{sval(machine.get(key)) or '未登録'}")
            st.markdown(f"**免税軽油**：{sval(machine.get('tax_free_diesel')) or '未登録'}")
        if sval(machine.get("notes")):
            st.markdown(f"**メモ**：{sval(machine.get('notes'))}")
        st.markdown("---")
        if st.button("✏️ 基本情報を編集する", use_container_width=True):
            nav("基本情報編集"); st.rerun()

    # --- 状態・保険 ---
    with t2:
        st.markdown(f"**稼働状態**：{icon} {cur_status}")
        st.markdown(f"**配備場所**：{(sval(status.get('location')) if status else '') or '未設定'}")
        if m_is_agri:
            hm = sval(status.get("hour_meter_current")) if status else ""
            st.markdown(f"**アワーメーター（現在）**：{(hm + ' h') if hm else '未登録'}")
        show_date("次回点検予定", "next_inspection_date")
        show_date("車検期日", "next_shaken_date")
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
                    # 入力ミスの訂正用：この記録の編集・削除画面へ
                    if st.button("✏️ 編集・削除", key=f"edit_rec_{sval(r.get('id'))}"):
                        st.session_state.edit_record_id = r.get("id")
                        nav("記録編集"); st.rerun()
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
                    # 入力ミスの訂正用：この日報の編集・削除画面へ
                    if st.button("✏️ 編集・削除", key=f"edit_op_{sval(o.get('id'))}"):
                        st.session_state.edit_record_id = o.get("id")
                        nav("稼働日報編集"); st.rerun()
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
                sold_date = st.date_input("処分日", value=today_jst())
                disposal_reason = st.text_input("理由", placeholder="例：老朽化、使用頻度低下")
                sold_price = st.number_input("売却価格（円）", min_value=0, step=10000, value=0)
                if st.form_submit_button("廃車・売却として登録する", type="primary"):
                    db.update("machines", mid, {
                        "is_disposed": 1, "sold_date": str(sold_date),
                        "sold_price": sold_price if sold_price > 0 else "",
                        "disposal_reason": disposal_reason or "",
                    })
                    st.success("登録しました"); nav("一覧"); st.rerun()

    # 画面下にも「一覧に戻る」（長い詳細をスクロールした後でもすぐ戻れるように）
    st.divider()
    if st.button("← 一覧に戻る", key="back_bottom", use_container_width=True):
        st.session_state.scroll_back = mid
        nav("一覧"); st.rerun()

# =====================================================
# 新規登録
# =====================================================
elif page == "登録":
    st.subheader(f"➕ {UNIT}を新規登録")
    if st.button("← 一覧に戻る"):
        nav("一覧"); st.rerun()

    with st.form("register_form", clear_on_submit=True):
        st.markdown("#### 基本情報")
        name = st.text_input(f"{UNIT}名 ＊必須",
                             placeholder=("例：トラクター1号" if is_agri else "例：4tダンプ1号"))
        category = st.selectbox("カテゴリ ＊必須", CATS)
        manufacturer = st.text_input("メーカー", placeholder=("例：クボタ" if is_agri else "例：コマツ"))
        model = st.text_input("型式・モデル", placeholder=("例：SL60" if is_agri else "例：PC30UU-5"))
        plate_number = st.text_input("ナンバー", placeholder="例：山形800 あ 1234")
        serial_number = st.text_input("シリアル番号")
        purchase_date = st.date_input("購入日", value=None,
                                      min_value=PURCHASE_MIN_DATE, max_value=today_jst())
        purchase_price = st.number_input("購入価格（円）", min_value=0, step=10000, value=0)
        # 車検期日は基本情報として入れる（保存先は machine_status＝状態・保険タブと同じ1つの値）
        _dl_lo, _dl_hi = deadline_range()
        next_shaken = st.date_input("車検期日", value=None,
                                    min_value=_dl_lo, max_value=_dl_hi,
                                    help="車検証の満了日。車検の無い機械は空欄のままで構いません")
        notes = st.text_area("メモ")

        # 農機のときだけ出す項目（作業機・対応作業・燃料・免税軽油・アワーメーター）
        attachments = fuel_type = tax_free = ""
        work_types_sel = []
        hour_meter_current = 0
        if is_agri:
            st.markdown("#### 農機の項目")
            attachments = st.text_input("作業機・アタッチメント",
                                        placeholder="例：ロータリー、ブームスプレーヤ")
            work_types_sel = st.multiselect("対応作業", AGRI_WORK_TYPES)
            fuel_type = st.selectbox("燃料", FUEL_TYPES)
            tax_free = st.selectbox("免税軽油", TAX_FREE_OPTS)
            hour_meter_current = st.number_input("アワーメーター現在値（h）",
                                                 min_value=0, step=1, value=0)

        st.markdown("#### 初期状態")
        initial_status = st.selectbox("稼働状態", STATUSES)
        initial_location = st.text_input("配備場所", placeholder="例：第1農場")
        # 車検期日は基本情報へ移したのでここには置かない（同じ値を2箇所で入力させない）
        next_inspection = st.date_input("次回点検予定日", value=None,
                                        min_value=_dl_lo, max_value=_dl_hi)

        st.markdown("#### 保険情報")
        jibaiseki_exp = st.date_input("自賠責保険 期限", value=None,
                                      min_value=_dl_lo, max_value=_dl_hi)
        insurance_exp = st.date_input("任意保険 期限", value=None,
                                      min_value=_dl_lo, max_value=_dl_hi)
        insurance_co = st.text_input("保険会社名")

        if st.form_submit_button("✅ 登録する", use_container_width=True, type="primary"):
            if not name.strip():
                st.error(f"{UNIT}名を入力してください")
            else:
                new_id = db.insert("machines", {
                    "name": name.strip(), "category": category,
                    "manufacturer": manufacturer or "", "model": model or "",
                    "purchase_date": str(purchase_date) if purchase_date else "",
                    "plate_number": plate_number or "", "serial_number": serial_number or "",
                    "purchase_price": purchase_price if purchase_price > 0 else "",
                    "notes": notes or "", "is_disposed": 0,
                    "machine_type": MTYPE,                                 # 区分（重機/農機）
                    "attachments": attachments or "",
                    "work_types": "、".join(work_types_sel) if work_types_sel else "",
                    "fuel_type": fuel_type or "",
                    "tax_free_diesel": tax_free or "",
                })
                db.insert("machine_status", {
                    "machine_id": new_id, "status": initial_status,
                    "location": initial_location or "",
                    "next_inspection_date": str(next_inspection) if next_inspection else "",
                    "next_shaken_date": str(next_shaken) if next_shaken else "",
                    "jibaiseki_expire": str(jibaiseki_exp) if jibaiseki_exp else "",
                    "insurance_expire": str(insurance_exp) if insurance_exp else "",
                    "insurance_company": insurance_co or "",
                    "hour_meter_current": hour_meter_current if hour_meter_current > 0 else "",
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
    s_is_agri = sval(machine.get("machine_type")) == "農機"
    st.subheader(f"📍 状態・保険更新：{sval(machine.get('name'))}")

    with st.form("status_form"):
        st.markdown("#### 稼働状態")
        cur = sval(status.get("status")) if status else ""
        idx = STATUSES.index(cur) if cur in STATUSES else 0
        new_status = st.selectbox("稼働状態", STATUSES, index=idx)
        new_location = st.text_input("配備場所", value=sval(status.get("location")) if status else "")
        hm_cur = 0
        if s_is_agri:
            hm_cur = st.number_input("アワーメーター現在値（h）", min_value=0, step=1,
                                     value=(to_int(status.get("hour_meter_current")) or 0) if status else 0)
        s_dl_lo, s_dl_hi = deadline_range()
        next_insp = st.date_input("次回点検予定日",
                                  value=deadline_value(status.get("next_inspection_date")) if status else None,
                                  min_value=s_dl_lo, max_value=s_dl_hi)
        next_shaken = st.date_input("車検期日",
                                    value=deadline_value(status.get("next_shaken_date")) if status else None,
                                    min_value=s_dl_lo, max_value=s_dl_hi,
                                    help="車検証の満了日。「基本情報」の車検期日と同じ項目です")

        st.markdown("#### 保険情報")
        jibaiseki_exp = st.date_input("自賠責保険 期限",
                                      value=deadline_value(status.get("jibaiseki_expire")) if status else None,
                                      min_value=s_dl_lo, max_value=s_dl_hi)
        insurance_exp = st.date_input("任意保険 期限",
                                      value=deadline_value(status.get("insurance_expire")) if status else None,
                                      min_value=s_dl_lo, max_value=s_dl_hi)
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
            if s_is_agri:
                payload["hour_meter_current"] = hm_cur if hm_cur > 0 else ""
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
        record_date = st.date_input("実施日", value=today_jst())
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
# 整備記録：編集・削除
# =====================================================
elif page == "記録編集" and st.session_state.edit_record_id:
    mid = st.session_state.selected_machine_id
    rid = st.session_state.edit_record_id
    machine = db.get("machines", mid)
    rec = db.get("records", rid)
    if not rec:  # 削除済み等で見つからなければ詳細へ戻す
        nav("詳細"); st.rerun()

    if st.button("← 詳細に戻る"):
        nav("詳細"); st.rerun()
    st.subheader(f"✏️ 整備記録の編集：{sval(machine.get('name'))}")

    cur_rt = sval(rec.get("record_type"))
    rt_idx = RECORD_TYPES.index(cur_rt) if cur_rt in RECORD_TYPES else 0
    with st.form("record_edit"):  # 追加フォームと同じ項目を既存値で初期化
        record_type = st.selectbox("記録の種類", RECORD_TYPES, index=rt_idx)
        record_date = st.date_input("実施日",
                                    value=parse_date(rec.get("record_date")) or today_jst())
        cost = st.number_input("費用（円）", min_value=0, step=1000,
                               value=to_int(rec.get("cost")) or 0)
        worker = st.text_input("担当者・整備業者", value=sval(rec.get("worker")))
        hour_meter = st.number_input("アワーメーター（h）", min_value=0, step=1,
                                     value=to_int(rec.get("hour_meter")) or 0,
                                     help="記録時点のエンジン稼働時間の累計")
        fuel_amount = st.number_input("給油量（L）", min_value=0.0, step=10.0,
                                      value=to_float(rec.get("fuel_amount")) or 0.0)
        next_scheduled = st.date_input("次回予定日",
                                       value=parse_date(rec.get("next_scheduled_date")))
        description = st.text_area("内容・詳細", value=sval(rec.get("description")))
        record_notes = st.text_area("その他メモ", value=sval(rec.get("notes")))

        if st.form_submit_button("✅ 更新する", use_container_width=True, type="primary"):
            db.update("records", rid, {
                "record_type": record_type, "record_date": str(record_date),
                "description": description or "", "cost": cost if cost > 0 else "",
                "worker": worker or "", "hour_meter": hour_meter if hour_meter > 0 else "",
                "fuel_amount": fuel_amount if fuel_amount > 0 else "",
                "next_scheduled_date": str(next_scheduled) if next_scheduled else "",
                "notes": record_notes or "",
            })
            st.success("更新しました！"); nav("詳細"); st.rerun()

    render_delete_section("records", rid, "詳細", label="この整備記録")

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
        operation_date = st.date_input("作業日", value=today_jst())
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
# 稼働日報：編集・削除
# =====================================================
elif page == "稼働日報編集" and st.session_state.edit_record_id:
    mid = st.session_state.selected_machine_id
    rid = st.session_state.edit_record_id
    machine = db.get("machines", mid)
    op = db.get("operation_logs", rid)
    if not op:  # 削除済み等で見つからなければ詳細へ戻す
        nav("詳細"); st.rerun()

    if st.button("← 詳細に戻る"):
        nav("詳細"); st.rerun()
    st.subheader(f"✏️ 稼働日報の編集：{sval(machine.get('name'))}")

    with st.form("op_edit"):  # 追加フォームと同じ項目を既存値で初期化
        operator = st.text_input("オペレーター名 ＊必須", value=sval(op.get("operator")))
        operation_date = st.date_input("作業日",
                                       value=parse_date(op.get("operation_date")) or today_jst())
        duration_hours = st.number_input("稼働時間（h）", min_value=0.0, step=0.5,
                                         value=to_float(op.get("duration_hours")) or 0.0)
        location = st.text_input("作業場所", value=sval(op.get("location")))
        work_content = st.text_area("作業内容", value=sval(op.get("work_content")))
        op_notes = st.text_area("その他メモ", value=sval(op.get("notes")))

        if st.form_submit_button("✅ 更新する", use_container_width=True, type="primary"):
            if not operator.strip():
                st.error("オペレーター名を入力してください")
            else:
                db.update("operation_logs", rid, {
                    "operator": operator.strip(),
                    "operation_date": str(operation_date),
                    "duration_hours": duration_hours if duration_hours > 0 else "",
                    "location": location or "", "work_content": work_content or "",
                    "notes": op_notes or "",
                })
                st.success("更新しました！"); nav("詳細"); st.rerun()

    render_delete_section("operation_logs", rid, "詳細", label="この稼働日報")

# =====================================================
# 基本情報編集
# =====================================================
elif page == "基本情報編集" and st.session_state.selected_machine_id:
    mid = st.session_state.selected_machine_id
    machine = db.get("machines", mid)

    if st.button("← 詳細に戻る"):
        nav("詳細"); st.rerun()
    e_is_agri = sval(machine.get("machine_type")) == "農機"
    e_cats = AGRI_CATEGORIES if e_is_agri else CATEGORIES
    e_unit = "農機" if e_is_agri else "重機"
    # 車検期日は machines ではなく machine_status にある項目なので、ここでも読み込む
    e_status = db.find_one("machine_status", "machine_id", mid)
    st.subheader(f"✏️ 基本情報を編集：{sval(machine.get('name'))}")

    with st.form("edit_form"):
        name = st.text_input(f"{e_unit}名 ＊必須", value=sval(machine.get("name")))
        cur_cat = sval(machine.get("category"))
        cat_idx = e_cats.index(cur_cat) if cur_cat in e_cats else 0
        category = st.selectbox("カテゴリ", e_cats, index=cat_idx)
        manufacturer = st.text_input("メーカー", value=sval(machine.get("manufacturer")))
        model = st.text_input("型式・モデル", value=sval(machine.get("model")))
        plate_number = st.text_input("ナンバー", value=sval(machine.get("plate_number")))
        serial_number = st.text_input("シリアル番号", value=sval(machine.get("serial_number")))
        purchase_date = st.date_input("購入日", value=purchase_date_value(machine.get("purchase_date")),
                                      min_value=PURCHASE_MIN_DATE, max_value=today_jst())
        purchase_price = st.number_input("購入価格（円）", min_value=0, step=10000,
                                         value=to_int(machine.get("purchase_price")) or 0)
        # 車検期日の保存先は machine_status（状態・保険タブと同じ1つの値を編集している）
        e_dl_lo, e_dl_hi = deadline_range()
        next_shaken = st.date_input(
            "車検期日",
            value=deadline_value(e_status.get("next_shaken_date")) if e_status else None,
            min_value=e_dl_lo, max_value=e_dl_hi,
            help="車検証の満了日。「状態・保険」タブの車検期日と同じ項目です")
        notes = st.text_area("メモ", value=sval(machine.get("notes")))

        # 農機のときだけ、農機項目も編集できるようにする
        attachments = fuel_type = tax_free = ""
        work_types_sel = []
        if e_is_agri:
            st.markdown("#### 農機の項目")
            attachments = st.text_input("作業機・アタッチメント",
                                        value=sval(machine.get("attachments")))
            cur_works = [w for w in sval(machine.get("work_types")).split("、") if w in AGRI_WORK_TYPES]
            work_types_sel = st.multiselect("対応作業", AGRI_WORK_TYPES, default=cur_works)
            cur_fuel = sval(machine.get("fuel_type"))
            fuel_type = st.selectbox("燃料", FUEL_TYPES,
                                     index=FUEL_TYPES.index(cur_fuel) if cur_fuel in FUEL_TYPES else 0)
            cur_tf = sval(machine.get("tax_free_diesel"))
            tax_free = st.selectbox("免税軽油", TAX_FREE_OPTS,
                                    index=TAX_FREE_OPTS.index(cur_tf) if cur_tf in TAX_FREE_OPTS else 0)

        if st.form_submit_button("✅ 保存する", use_container_width=True, type="primary"):
            if not name.strip():
                st.error(f"{e_unit}名を入力してください")
            else:
                payload = {
                    "name": name.strip(), "category": category,
                    "manufacturer": manufacturer or "", "model": model or "",
                    "purchase_date": str(purchase_date) if purchase_date else "",
                    "plate_number": plate_number or "", "serial_number": serial_number or "",
                    "purchase_price": purchase_price if purchase_price > 0 else "",
                    "notes": notes or "",
                }
                if e_is_agri:
                    payload.update({
                        "attachments": attachments or "",
                        "work_types": "、".join(work_types_sel) if work_types_sel else "",
                        "fuel_type": fuel_type or "",
                        "tax_free_diesel": tax_free or "",
                    })
                db.update("machines", mid, payload)
                # 車検期日だけは保存先が別表。状態レコードが無い機械なら作ってから書く
                shaken_val = str(next_shaken) if next_shaken else ""
                if e_status:
                    db.update("machine_status", e_status.get("id"),
                              {"next_shaken_date": shaken_val})
                elif shaken_val:
                    db.insert("machine_status",
                              {"machine_id": mid, "next_shaken_date": shaken_val})
                st.success("更新しました！"); nav("詳細"); st.rerun()

# =====================================================
# 🏢 施設：一覧
# =====================================================
elif page == "施設一覧":
    st.subheader("施設一覧")
    # 種類はタップ式ボタン（ピル）。再タップ/「すべて」で解除
    f_cat = st.pills("種類", ["すべて"] + FACILITY_CATEGORIES,
                     selection_mode="single", default="すべて", key="ffc") or "すべて"
    c1, c2 = st.columns([3, 2])
    with c1:
        f_status = st.selectbox("状態", ["すべて"] + FACILITY_STATUSES, key="ffs")
    with c2:
        show_removed = st.checkbox("解体・廃止も表示", value=False, key="fshow")
    sort_by = st.selectbox("並び替え", SORT_OPTS_FACILITY, key="sort_facility")

    facilities = db.read("facilities")
    fstatuses = {sval(s.get("facility_id")): s for s in db.read("facility_status")}

    rows = []
    for f in facilities:
        fid = sval(f.get("id"))
        s = fstatuses.get(fid, {})
        removed = to_int(f.get("is_disposed")) == 1
        status = sval(s.get("status")) or "未設定"
        if not show_removed and removed:
            continue
        if f_cat != "すべて" and sval(f.get("category")) != f_cat:
            continue
        if f_status != "すべて" and status != f_status:
            continue
        checks = [(lbl, s.get(col)) for lbl, col in LEGAL_CHECKS]
        checks.append((sval(s.get("other_name")) or "その他", s.get("other_expire")))
        rows.append({
            "id": fid, "name": sval(f.get("name")), "category": sval(f.get("category")),
            "removed": removed, "status": status,
            "location": sval(s.get("location")) or "未設定", "checks": checks,
            # 法定点検（消防・電気・浄化槽・その他）のうち一番近い残日数
            "_expire_days": nearest_days(*[d for _, d in checks]),
        })
    sort_rows(rows, sort_by, FACILITY_STATUSES)

    if not rows:
        st.info("該当する施設がありません。「➕ 施設を登録」から追加してください。")
    else:
        alerts = []
        for f in rows:
            for label, d in f["checks"]:
                days = days_until(d)
                if days is not None and days <= 30:
                    alerts.append(f"⚠️ **{f['name']}** の{label}点検まで **{days}日**")
        if alerts:
            with st.expander(f"🚨 点検期限アラート {len(alerts)}件", expanded=True):
                for a in alerts:
                    st.markdown(a)

        st.caption(f"全 {len(rows)} 施設")
        for f in rows:
            icon = FACILITY_STATUS_ICONS.get(f["status"], "⚪")
            with st.container(border=True):
                disp = f"~~{f['name']}~~" if f["removed"] else f"**{f['name']}**"
                st.markdown(f'<span id="facility-{f["id"]}"></span>{disp}　{icon} {f["status"]}',
                            unsafe_allow_html=True)
                st.caption(f"{f['category']}　|　場所：{f['location']}")
                for label, d in f["checks"]:
                    days = days_until(d)
                    if days is not None:
                        if days <= 30:
                            st.caption(f"⚠️ {label}点検まで{days}日")
                        elif days <= 90:
                            st.caption(f"📅 {label}点検まで{days}日")
                if st.button("詳細を見る", key=f"fb_{f['id']}", use_container_width=True):
                    nav("施設詳細", facility_id=f["id"]); st.rerun()
        scroll_restore("facility")

# =====================================================
# 🏢 施設：詳細
# =====================================================
elif page == "施設詳細" and st.session_state.selected_facility_id:
    fid = st.session_state.selected_facility_id
    facility = db.get("facilities", fid)
    if not facility:
        nav("施設一覧"); st.rerun()
    fstatus = db.find_one("facility_status", "facility_id", fid)
    frecords = db.find_all("facility_records", "facility_id", fid)
    frecords.sort(key=lambda r: sval(r.get("record_date")), reverse=True)

    if st.button("← 施設一覧に戻る"):
        st.session_state.scroll_back = fid
        nav("施設一覧"); st.rerun()
    cur_status = sval(fstatus.get("status")) if fstatus else "未設定"
    icon = FACILITY_STATUS_ICONS.get(cur_status, "⚪")
    st.subheader(f"🏢 {sval(facility.get('name'))}")
    st.markdown(f"{icon} **{cur_status}**　|　{sval(facility.get('category'))}")
    if to_int(facility.get("is_disposed")) == 1:
        st.warning("この施設は廃止・解体済みです")

    t1, t2, t3 = st.tabs(["📋 基本情報", "🔥 法定点検・状態", "🔧 点検・修繕記録"])

    with t1:
        for label, key in [("種類", "category"), ("面積(㎡)", "area"),
                           ("収容頭数", "capacity"), ("建設年月", "built_date"),
                           ("場所", "location")]:
            st.markdown(f"**{label}**：{sval(facility.get(key)) or '未登録'}")
        if sval(facility.get("notes")):
            st.markdown(f"**メモ**：{sval(facility.get('notes'))}")
        st.markdown("---")
        if st.button("✏️ 基本情報を編集する", use_container_width=True):
            nav("施設編集"); st.rerun()

    with t2:
        st.markdown(f"**状態**：{icon} {cur_status}")
        st.markdown(f"**場所**：{(sval(fstatus.get('location')) if fstatus else '') or '未設定'}")
        st.markdown("---")
        st.markdown("**法定点検の期限**")

        def show_check(label, key):
            v = sval(fstatus.get(key)) if fstatus else ""
            d = days_until(v)
            extra = f"　⚠️ あと{d}日" if d is not None and d <= 30 else ""
            st.markdown(f"・{label}：{v or '未設定'}{extra}")

        for label, col in LEGAL_CHECKS:
            show_check(label, col)
        on = sval(fstatus.get("other_name")) if fstatus else ""
        if on or (fstatus and sval(fstatus.get("other_expire"))):
            show_check(on or "その他点検", "other_expire")
        if fstatus and sval(fstatus.get("notes")):
            st.markdown(f"**メモ**：{sval(fstatus.get('notes'))}")
        st.markdown("---")
        if st.button("📍 状態・点検期限を更新する", use_container_width=True, type="primary"):
            nav("施設状態更新"); st.rerun()

    with t3:
        if st.button("➕ 記録を追加する", use_container_width=True, type="primary"):
            nav("施設記録追加"); st.rerun()
        st.markdown("---")
        if frecords:
            total_cost = sum(to_int(r.get("cost")) or 0 for r in frecords)
            c1, c2 = st.columns(2)
            c1.metric("記録件数", f"{len(frecords)}件")
            c2.metric("累計費用", fmt_price(total_cost))
            for r in frecords:
                with st.container(border=True):
                    # 日付（終了日があれば 開始〜終了 の期間表示）
                    d1 = sval(r.get("record_date"))
                    d2 = sval(r.get("end_date"))
                    dstr = f"{d1} 〜 {d2}" if d2 else d1
                    head = f"**{sval(r.get('record_type'))}**　{dstr}"
                    if sval(r.get("repair_location")):
                        head += f"　／ 箇所：{sval(r.get('repair_location'))}"
                    if to_int(r.get("cost")):
                        head += f"　{fmt_price(r.get('cost'))}"
                    st.markdown(head)
                    if sval(r.get("description")):
                        st.write(sval(r.get("description")))
                    caps = []
                    if sval(r.get("contractor_type")):
                        caps.append(f"区分：{sval(r.get('contractor_type'))}")
                    if sval(r.get("worker")):
                        caps.append(f"担当：{sval(r.get('worker'))}")
                    if sval(r.get("materials")):
                        caps.append(f"部材：{sval(r.get('materials'))}")
                    if sval(r.get("insurance")):
                        caps.append(f"保険：{sval(r.get('insurance'))}")
                    if sval(r.get("next_scheduled_date")):
                        caps.append(f"次回予定：{sval(r.get('next_scheduled_date'))}")
                    for cap in caps:
                        st.caption(cap)
                    # 入力ミスの訂正用：この記録の編集・削除画面へ
                    if st.button("✏️ 編集・削除", key=f"edit_frec_{sval(r.get('id'))}"):
                        st.session_state.edit_record_id = r.get("id")
                        nav("施設記録編集"); st.rerun()
        else:
            st.info("記録がまだありません")

    st.divider()
    if st.button("← 施設一覧に戻る", key="fback_bottom", use_container_width=True):
        st.session_state.scroll_back = fid
        nav("施設一覧"); st.rerun()

# =====================================================
# 🏢 施設：新規登録
# =====================================================
elif page == "施設登録":
    st.subheader("➕ 施設を新規登録")
    if st.button("← 施設一覧に戻る"):
        nav("施設一覧"); st.rerun()

    with st.form("f_register", clear_on_submit=True):
        st.markdown("#### 基本情報")
        name = st.text_input("施設名 ＊必須", placeholder="例：第1肥育牛舎")
        category = st.selectbox("種類 ＊必須", FACILITY_CATEGORIES)
        area = st.text_input("面積（㎡）", placeholder="例：1200")
        capacity = st.text_input("収容頭数", placeholder="例：200")
        built_date = st.text_input("建設年月", placeholder="例：2015-04")
        location = st.text_input("場所", placeholder="例：本場")
        notes = st.text_area("メモ")

        st.markdown("#### 初期状態")
        initial_status = st.selectbox("状態", FACILITY_STATUSES)

        st.markdown("#### 法定点検の期限")
        fire = st.date_input("消防設備点検 期限", value=None)
        elec = st.date_input("電気設備点検 期限", value=None)
        septic = st.date_input("浄化槽点検 期限", value=None)
        other_name = st.text_input("その他点検の名称", placeholder="例：ボイラー")
        other_exp = st.date_input("その他点検 期限", value=None)

        if st.form_submit_button("✅ 登録する", use_container_width=True, type="primary"):
            if not name.strip():
                st.error("施設名を入力してください")
            else:
                new_id = db.insert("facilities", {
                    "name": name.strip(), "category": category, "area": area or "",
                    "capacity": capacity or "", "built_date": built_date or "",
                    "location": location or "", "notes": notes or "", "is_disposed": 0,
                })
                db.insert("facility_status", {
                    "facility_id": new_id, "status": initial_status, "location": location or "",
                    "fire_expire": str(fire) if fire else "",
                    "electrical_expire": str(elec) if elec else "",
                    "septic_expire": str(septic) if septic else "",
                    "other_name": other_name or "",
                    "other_expire": str(other_exp) if other_exp else "",
                })
                st.success(f"「{name}」を登録しました！")
                nav("施設詳細", facility_id=new_id); st.rerun()

# =====================================================
# 🏢 施設：状態・点検期限の更新
# =====================================================
elif page == "施設状態更新" and st.session_state.selected_facility_id:
    fid = st.session_state.selected_facility_id
    facility = db.get("facilities", fid)
    fstatus = db.find_one("facility_status", "facility_id", fid)

    if st.button("← 詳細に戻る"):
        nav("施設詳細"); st.rerun()
    st.subheader(f"📍 状態・点検期限の更新：{sval(facility.get('name'))}")

    with st.form("f_status"):
        cur = sval(fstatus.get("status")) if fstatus else ""
        idx = FACILITY_STATUSES.index(cur) if cur in FACILITY_STATUSES else 0
        new_status = st.selectbox("状態", FACILITY_STATUSES, index=idx)
        new_location = st.text_input("場所", value=sval(fstatus.get("location")) if fstatus else "")
        st.markdown("#### 法定点検の期限")
        fire = st.date_input("消防設備点検 期限",
                             value=parse_date(fstatus.get("fire_expire")) if fstatus else None)
        elec = st.date_input("電気設備点検 期限",
                             value=parse_date(fstatus.get("electrical_expire")) if fstatus else None)
        septic = st.date_input("浄化槽点検 期限",
                               value=parse_date(fstatus.get("septic_expire")) if fstatus else None)
        other_name = st.text_input("その他点検の名称",
                                   value=sval(fstatus.get("other_name")) if fstatus else "")
        other_exp = st.date_input("その他点検 期限",
                                  value=parse_date(fstatus.get("other_expire")) if fstatus else None)
        new_notes = st.text_area("メモ", value=sval(fstatus.get("notes")) if fstatus else "")

        if st.form_submit_button("✅ 更新する", use_container_width=True, type="primary"):
            payload = {
                "status": new_status, "location": new_location or "",
                "fire_expire": str(fire) if fire else "",
                "electrical_expire": str(elec) if elec else "",
                "septic_expire": str(septic) if septic else "",
                "other_name": other_name or "",
                "other_expire": str(other_exp) if other_exp else "",
                "notes": new_notes or "",
            }
            if fstatus:
                db.update("facility_status", fstatus.get("id"), payload)
            else:
                db.insert("facility_status", {"facility_id": fid, **payload})
            st.success("更新しました！"); nav("施設詳細"); st.rerun()

# =====================================================
# 🏢 施設：点検・修繕記録の追加
# =====================================================
elif page == "施設記録追加" and st.session_state.selected_facility_id:
    fid = st.session_state.selected_facility_id
    facility = db.get("facilities", fid)

    if st.button("← 詳細に戻る"):
        nav("施設詳細"); st.rerun()
    st.subheader(f"🔧 記録追加：{sval(facility.get('name'))}")

    with st.form("f_record", clear_on_submit=True):
        record_type = st.selectbox("記録の種類", FACILITY_RECORD_TYPES)
        repair_location = st.text_input("修繕箇所", placeholder="例：屋根・給水管・換気扇")
        c1, c2 = st.columns(2)
        with c1:
            record_date = st.date_input("開始日（実施日）", value=today_jst())
        with c2:
            end_date = st.date_input("終了日（工事期間がある場合）", value=None)
        contractor_type = st.radio("区分", ["自社", "外注"], horizontal=True)
        worker = st.text_input("担当者・業者", placeholder="例：〇〇工務店 / 田中")
        materials = st.text_area("部材", placeholder="例：トタン板10枚、ビス、塗料")
        cost = st.number_input("費用（円）", min_value=0, step=1000, value=0)
        insurance = st.text_input("保険", placeholder="例：火災保険適用（30万円）/ なし")
        next_scheduled = st.date_input("次回予定日", value=None)
        description = st.text_area("内容・詳細", placeholder="例：台風で破損した屋根を補修")
        record_notes = st.text_area("その他メモ")

        if st.form_submit_button("✅ 記録を保存する", use_container_width=True, type="primary"):
            db.insert("facility_records", {
                "facility_id": fid, "record_type": record_type,
                "repair_location": repair_location or "",
                "record_date": str(record_date),
                "end_date": str(end_date) if end_date else "",
                "contractor_type": contractor_type,
                "worker": worker or "", "materials": materials or "",
                "cost": cost if cost > 0 else "", "insurance": insurance or "",
                "next_scheduled_date": str(next_scheduled) if next_scheduled else "",
                "description": description or "", "notes": record_notes or "",
            })
            st.success("記録を保存しました！"); nav("施設詳細"); st.rerun()

# =====================================================
# 🏢 施設：点検・修繕記録の編集・削除
# =====================================================
elif page == "施設記録編集" and st.session_state.edit_record_id:
    fid = st.session_state.selected_facility_id
    rid = st.session_state.edit_record_id
    facility = db.get("facilities", fid)
    rec = db.get("facility_records", rid)
    if not rec:  # 削除済み等で見つからなければ詳細へ戻す
        nav("施設詳細"); st.rerun()

    if st.button("← 詳細に戻る"):
        nav("施設詳細"); st.rerun()
    st.subheader(f"✏️ 点検・修繕記録の編集：{sval(facility.get('name'))}")

    cur_rt = sval(rec.get("record_type"))
    rt_idx = FACILITY_RECORD_TYPES.index(cur_rt) if cur_rt in FACILITY_RECORD_TYPES else 0
    cur_ct = sval(rec.get("contractor_type"))
    ct_idx = ["自社", "外注"].index(cur_ct) if cur_ct in ["自社", "外注"] else 0
    with st.form("f_record_edit"):  # 追加フォームと同じ項目を既存値で初期化
        record_type = st.selectbox("記録の種類", FACILITY_RECORD_TYPES, index=rt_idx)
        repair_location = st.text_input("修繕箇所", value=sval(rec.get("repair_location")))
        c1, c2 = st.columns(2)
        with c1:
            record_date = st.date_input("開始日（実施日）",
                                        value=parse_date(rec.get("record_date")) or today_jst())
        with c2:
            end_date = st.date_input("終了日（工事期間がある場合）",
                                     value=parse_date(rec.get("end_date")))
        contractor_type = st.radio("区分", ["自社", "外注"], horizontal=True, index=ct_idx)
        worker = st.text_input("担当者・業者", value=sval(rec.get("worker")))
        materials = st.text_area("部材", value=sval(rec.get("materials")))
        cost = st.number_input("費用（円）", min_value=0, step=1000,
                               value=to_int(rec.get("cost")) or 0)
        insurance = st.text_input("保険", value=sval(rec.get("insurance")))
        next_scheduled = st.date_input("次回予定日",
                                       value=parse_date(rec.get("next_scheduled_date")))
        description = st.text_area("内容・詳細", value=sval(rec.get("description")))
        record_notes = st.text_area("その他メモ", value=sval(rec.get("notes")))

        if st.form_submit_button("✅ 更新する", use_container_width=True, type="primary"):
            db.update("facility_records", rid, {
                "record_type": record_type,
                "repair_location": repair_location or "",
                "record_date": str(record_date),
                "end_date": str(end_date) if end_date else "",
                "contractor_type": contractor_type,
                "worker": worker or "", "materials": materials or "",
                "cost": cost if cost > 0 else "", "insurance": insurance or "",
                "next_scheduled_date": str(next_scheduled) if next_scheduled else "",
                "description": description or "", "notes": record_notes or "",
            })
            st.success("更新しました！"); nav("施設詳細"); st.rerun()

    render_delete_section("facility_records", rid, "施設詳細", label="この記録")

# =====================================================
# 🏢 施設：基本情報編集
# =====================================================
elif page == "施設編集" and st.session_state.selected_facility_id:
    fid = st.session_state.selected_facility_id
    facility = db.get("facilities", fid)

    if st.button("← 詳細に戻る"):
        nav("施設詳細"); st.rerun()
    st.subheader(f"✏️ 基本情報を編集：{sval(facility.get('name'))}")

    with st.form("f_edit"):
        name = st.text_input("施設名 ＊必須", value=sval(facility.get("name")))
        cur_cat = sval(facility.get("category"))
        cat_idx = FACILITY_CATEGORIES.index(cur_cat) if cur_cat in FACILITY_CATEGORIES else 0
        category = st.selectbox("種類", FACILITY_CATEGORIES, index=cat_idx)
        area = st.text_input("面積（㎡）", value=sval(facility.get("area")))
        capacity = st.text_input("収容頭数", value=sval(facility.get("capacity")))
        built_date = st.text_input("建設年月", value=sval(facility.get("built_date")))
        location = st.text_input("場所", value=sval(facility.get("location")))
        notes = st.text_area("メモ", value=sval(facility.get("notes")))
        removed = st.checkbox("廃止・解体済みにする（一覧から非表示）",
                              value=(to_int(facility.get("is_disposed")) == 1))

        if st.form_submit_button("✅ 保存する", use_container_width=True, type="primary"):
            if not name.strip():
                st.error("施設名を入力してください")
            else:
                db.update("facilities", fid, {
                    "name": name.strip(), "category": category, "area": area or "",
                    "capacity": capacity or "", "built_date": built_date or "",
                    "location": location or "", "notes": notes or "",
                    "is_disposed": 1 if removed else 0,
                })
                st.success("更新しました！"); nav("施設詳細"); st.rerun()

else:
    nav("施設一覧" if st.session_state.get("mode") == "facility" else "一覧"); st.rerun()
