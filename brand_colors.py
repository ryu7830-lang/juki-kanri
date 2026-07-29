# -*- coding: utf-8 -*-
"""グラフの系列色（スカイファーム ブランド）。

**色の正本は sky本体リポジトリの `farm/brand/brand.json`（chart.categorical）**。
このアプリは別リポジトリ（ryu7830-lang/juki-kanri）として Streamlit Cloud に
デプロイされるため `from brand...` を import できず、値をここに写している。
ここで色を選ばないこと。brand.json が変わったら写し直す。
写した時点: 2026-07-29 / 検証値 CVD 14.6・通常色覚 26.6（validate_palette.py 済み）

ブランドのルール（farm/brand/README.md より）:
- 系列色は順序固定・循環させない（8つ目以降は墨・グレーに逃がす）
- 色は対象に付き、順位には付かない → domain を明示して種別ごとに固定する
- 赤は「悪い数字」の予約色。系列色に使わない
- ブランド黄 #FFD000 は面の色。文字にも系列色にも使わない
"""
import streamlit as st

# brand.json chart.categorical（順序: amber, blue, terracotta, teal, violet, green, plum）
SERIES_LIGHT = ["#B08E00", "#006BB9", "#CF5500", "#009B8F", "#7800EA", "#008D24", "#BA00B4"]
SERIES_DARK  = ["#A28300", "#007DD6", "#C65100", "#009488", "#8C41FF", "#009426", "#C800C2"]
INK   = "#242424"   # 墨（8系列目の逃がし先）
GRAY  = "#8A8A8A"   # 「未設定」用。系列ではなく欠測を表す


def _is_dark():
    """利用者の表示モード。取れなければ明るい地色とみなす（現場スマホの既定）。"""
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def series(n=None):
    """系列色を順序どおりに返す。n を指定すると先頭n色（7を超えたら墨→グレー）。"""
    base = SERIES_DARK if _is_dark() else SERIES_LIGHT
    if n is None:
        return list(base)
    extra = [INK, GRAY]
    return (list(base) + extra)[:n] if n > len(base) else list(base[:n])


def fixed_scale(all_domain, present=None):
    """対象（種別など）に色を固定するための domain/range を返す。

    色は all_domain の並び順で決め、present を渡すとその中の対象だけを返す。
    こうすると「今月は修理が無い」等で凡例が減っても、残った対象の色は動かない
    （ブランドのルール: 色は対象に付き、順位には付かない）。
    「未設定」は系列色ではなくグレー＝欠測の意味にする。"""
    palette = series() + [INK]
    domain, colors, i = [], [], 0
    for d in all_domain:
        if d == "未設定":
            c = GRAY
        else:
            c = palette[i] if i < len(palette) else GRAY
            i += 1
        if present is None or d in present:
            domain.append(d)
            colors.append(c)
    return domain, colors
