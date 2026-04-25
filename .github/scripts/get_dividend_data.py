"""
保有銘柄の配当データをyfinanceで取得し、月別配当カレンダーを生成する。

出力: data/dividend-calendar.md
  - 銘柄別配当サマリー表
  - 月別配当カレンダー（特定口座税引後 / NISA口座税引後 / 合計）

支払月の推定:
  yfinanceから取得できるのは権利落ち日（ex-dividend date）。
  日本株は権利落ち月 +3ヶ月を支払月として近似推定する。
  例: 3月末権利落ち → 6月支払、9月末権利落ち → 12月支払

実行方法:
  pip install yfinance
  python get_dividend_data.py
"""

import yfinance as yf
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# ── 保有銘柄データ（SBI証券 SaveFile.csv から生成） ──────────────────────
HOLDINGS = {
    "1605": {"name": "INPEX", "tokutei": 0, "nisa": 100},
    "1723": {"name": "日本電技", "tokutei": 120, "nisa": 0},
    "1928": {"name": "積水ハウス", "tokutei": 0, "nisa": 40},
    "1951": {"name": "エクシオグループ", "tokutei": 66, "nisa": 0},
    "2002": {"name": "日清粉G", "tokutei": 0, "nisa": 50},
    "2003": {"name": "日東富士", "tokutei": 0, "nisa": 36},
    "2124": {"name": "JAC", "tokutei": 0, "nisa": 40},
    "2169": {"name": "CDS", "tokutei": 0, "nisa": 100},
    "2296": {"name": "伊藤ハム米久HD", "tokutei": 24, "nisa": 6},
    "2317": {"name": "システナ", "tokutei": 150, "nisa": 0},
    "2391": {"name": "プラネット", "tokutei": 0, "nisa": 106},
    "2602": {"name": "日清オイリオ", "tokutei": 0, "nisa": 78},
    "3003": {"name": "ヒューリック", "tokutei": 0, "nisa": 80},
    "3076": {"name": "あいHD", "tokutei": 0, "nisa": 50},
    "3231": {"name": "野村不HD", "tokutei": 120, "nisa": 0},
    "3333": {"name": "あさひ", "tokutei": 0, "nisa": 40},
    "3482": {"name": "ロードスター", "tokutei": 301, "nisa": 0},
    "3762": {"name": "テクマト", "tokutei": 0, "nisa": 22},
    "3763": {"name": "プロシップ", "tokutei": 160, "nisa": 0},
    "3817": {"name": "SRAHD", "tokutei": 8, "nisa": 3},
    "3834": {"name": "朝日ネット", "tokutei": 0, "nisa": 180},
    "4008": {"name": "住友精化", "tokutei": 90, "nisa": 10},
    "4042": {"name": "東ソー", "tokutei": 44, "nisa": 16},
    "4206": {"name": "アイカ工", "tokutei": 0, "nisa": 20},
    "4326": {"name": "インテージHD", "tokutei": 40, "nisa": 0},
    "4401": {"name": "ADEKA", "tokutei": 0, "nisa": 20},
    "4452": {"name": "花王", "tokutei": 32, "nisa": 0},
    "4502": {"name": "武田薬", "tokutei": 2, "nisa": 48},
    "4503": {"name": "アステラス薬", "tokutei": 0, "nisa": 140},
    "4540": {"name": "ツムラ", "tokutei": 0, "nisa": 16},
    "4641": {"name": "アルプス技", "tokutei": 17, "nisa": 23},
    "4674": {"name": "クレスコ", "tokutei": 0, "nisa": 50},
    "4719": {"name": "アルファシステムズ", "tokutei": 0, "nisa": 20},
    "4732": {"name": "USS", "tokutei": 108, "nisa": 0},
    "4743": {"name": "アイティフォー", "tokutei": 0, "nisa": 20},
    "4765": {"name": "SBIGアセットM", "tokutei": 200, "nisa": 0},
    "4832": {"name": "JFE-SI", "tokutei": 36, "nisa": 0},
    "4847": {"name": "IWI", "tokutei": 0, "nisa": 100},
    "5011": {"name": "ニチレキG", "tokutei": 30, "nisa": 15},
    "5105": {"name": "TOYO TIRE", "tokutei": 34, "nisa": 0},
    "5108": {"name": "ブリヂス", "tokutei": 24, "nisa": 0},
    "5184": {"name": "ニチリン", "tokutei": 17, "nisa": 3},
    "5334": {"name": "日特殊陶", "tokutei": 27, "nisa": 0},
    "5384": {"name": "FUJIMI", "tokutei": 0, "nisa": 76},
    "5388": {"name": "クニミネ工業", "tokutei": 0, "nisa": 120},
    "6301": {"name": "コマツ", "tokutei": 20, "nisa": 16},
    "6381": {"name": "アネスト岩田", "tokutei": 0, "nisa": 70},
    "6432": {"name": "竹内製作所", "tokutei": 0, "nisa": 29},
    "6458": {"name": "新晃工業", "tokutei": 0, "nisa": 60},
    "6539": {"name": "MS-Japan", "tokutei": 0, "nisa": 85},
    "7164": {"name": "全国保証", "tokutei": 6, "nisa": 8},
    "7820": {"name": "ニホンフラッシュ", "tokutei": 0, "nisa": 200},
    "7921": {"name": "TAKARA&CO", "tokutei": 5, "nisa": 0},
    "7931": {"name": "未来工業", "tokutei": 20, "nisa": 0},
    "7943": {"name": "ニチハ", "tokutei": 28, "nisa": 0},
    "7989": {"name": "立川ブライ", "tokutei": 0, "nisa": 20},
    "7994": {"name": "オカムラ", "tokutei": 58, "nisa": 22},
    "7995": {"name": "バルカー", "tokutei": 0, "nisa": 8},
    "8001": {"name": "伊藤忠", "tokutei": 0, "nisa": 10},
    "8002": {"name": "丸紅", "tokutei": 10, "nisa": 55},
    "8053": {"name": "住友商", "tokutei": 34, "nisa": 0},
    "8058": {"name": "三菱商事", "tokutei": 0, "nisa": 60},
    "8130": {"name": "サンゲツ", "tokutei": 6, "nisa": 24},
    "8309": {"name": "三井住友トラストG", "tokutei": 0, "nisa": 33},
    "8316": {"name": "三井住友", "tokutei": 51, "nisa": 0},
    "8473": {"name": "SBI", "tokutei": 200, "nisa": 0},
    "8566": {"name": "リコーリース", "tokutei": 1, "nisa": 0},
    "8584": {"name": "ジャックス", "tokutei": 0, "nisa": 20},
    "8591": {"name": "オリックス", "tokutei": 0, "nisa": 15},
    "8593": {"name": "三菱HCキャピタル", "tokutei": 201, "nisa": 0},
    "8630": {"name": "SOMPOHD", "tokutei": 39, "nisa": 0},
    "8697": {"name": "JPX", "tokutei": 102, "nisa": 0},
    "8698": {"name": "マネックスG", "tokutei": 700, "nisa": 0},
    "8725": {"name": "MS&AD", "tokutei": 2, "nisa": 38},
    "8766": {"name": "東京海上", "tokutei": 6, "nisa": 0},
    "9057": {"name": "遠州トラック", "tokutei": 1, "nisa": 24},
    "9069": {"name": "センコーグループHD", "tokutei": 55, "nisa": 18},
    "9233": {"name": "アジア航測", "tokutei": 70, "nisa": 0},
    "9303": {"name": "住友倉", "tokutei": 43, "nisa": 0},
    "9304": {"name": "渋沢倉", "tokutei": 120, "nisa": 40},
    "9368": {"name": "キムラユニティー", "tokutei": 140, "nisa": 20},
    "9432": {"name": "NTT", "tokutei": 0, "nisa": 1600},
    "9433": {"name": "KDDI", "tokutei": 2, "nisa": 0},
    "9436": {"name": "沖縄セルラー", "tokutei": 0, "nisa": 12},
    "9513": {"name": "Jパワー", "tokutei": 23, "nisa": 0},
    "9687": {"name": "KSK", "tokutei": 0, "nisa": 14},
    "9698": {"name": "クレオ", "tokutei": 101, "nisa": 0},
    "9757": {"name": "船井総研HD", "tokutei": 0, "nisa": 100},
    "9769": {"name": "学究社", "tokutei": 5, "nisa": 36},
    "9882": {"name": "イエローハット", "tokutei": 0, "nisa": 70},
}

# 税率
TAX_TOKUTEI = 0.20315  # 特定口座
TAX_NISA    = 0.0      # NISA（日本株は非課税）

MONTHS_JA = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]


def ex_month_to_pay_month(ex_month: int) -> int:
    """権利落ち月 → 支払月（+3ヶ月の近似推定）"""
    return (ex_month + 2) % 12 + 1


def fetch_dividend_info(code: str) -> dict:
    """
    yfinanceで過去2年の配当履歴を取得し、次のdictを返す。
    {
        "pay_months": {支払月: 1株配当額, ...},  # 直近2回分
        "annual_per_share": float,
        "source": "yfinance" | "no_data",
        "ex_dates": [(date_str, amount), ...]
    }
    """
    sym = f"{code}.T"
    try:
        ticker = yf.Ticker(sym)
        divs = ticker.dividends
        if divs is None or len(divs) == 0:
            return {"pay_months": {}, "annual_per_share": 0.0,
                    "source": "no_data", "ex_dates": []}

        # 直近2年以内の配当に絞る
        now = datetime.now(timezone.utc)
        recent = [(d, float(v)) for d, v in divs.items()
                  if (now - d.to_pydatetime()).days <= 730]

        if not recent:
            return {"pay_months": {}, "annual_per_share": 0.0,
                    "source": "no_data", "ex_dates": []}

        # 権利落ち月 → 支払月 に変換してグループ集計
        # 同一支払月が複数回あれば最新1回を採用
        pay_map: dict[int, float] = {}
        for dt, amt in sorted(recent, key=lambda x: x[0]):
            ex_m = dt.to_pydatetime().month
            pay_m = ex_month_to_pay_month(ex_m)
            pay_map[pay_m] = amt  # 後のもので上書き（最新優先）

        annual = sum(pay_map.values())
        ex_dates = [(str(d.date()), round(v, 2)) for d, v in sorted(recent, key=lambda x: x[0])]

        return {
            "pay_months": pay_map,
            "annual_per_share": round(annual, 2),
            "source": "yfinance",
            "ex_dates": ex_dates,
        }

    except Exception as e:
        print(f"  [WARN] {code}: {e}", file=sys.stderr)
        return {"pay_months": {}, "annual_per_share": 0.0,
                "source": "error", "ex_dates": []}


def calc_after_tax(amount: float, is_nisa: bool) -> float:
    rate = TAX_NISA if is_nisa else TAX_TOKUTEI
    return round(amount * (1 - rate), 0)


def main():
    output_path = Path("data/dividend-calendar.md")
    output_path.parent.mkdir(exist_ok=True)

    print(f"取得開始: {len(HOLDINGS)} 銘柄", file=sys.stderr)

    results = {}  # code -> {info, per_share, pay_months, ...}

    for i, (code, h) in enumerate(sorted(HOLDINGS.items()), 1):
        print(f"  [{i:2d}/{len(HOLDINGS)}] {code} {h['name']}", file=sys.stderr)
        info = fetch_dividend_info(code)
        results[code] = {**h, **info}

    # ── 月別集計 ─────────────────────────────────────────────────────────
    monthly_tokutei_after = defaultdict(float)  # 特定口座税引後
    monthly_nisa_after    = defaultdict(float)  # NISA税引後
    monthly_tokutei_before = defaultdict(float)
    monthly_nisa_before    = defaultdict(float)

    for code, r in results.items():
        pay_months = r.get("pay_months", {})
        if not pay_months:
            continue
        for pay_m, div_per_share in pay_months.items():
            if r["tokutei"] > 0:
                gross = div_per_share * r["tokutei"]
                monthly_tokutei_before[pay_m] += gross
                monthly_tokutei_after[pay_m]  += calc_after_tax(gross, is_nisa=False)
            if r["nisa"] > 0:
                gross = div_per_share * r["nisa"]
                monthly_nisa_before[pay_m] += gross
                monthly_nisa_after[pay_m]  += gross  # NISA は非課税

    # ── Markdown 生成 ──────────────────────────────────────────────────
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"# 配当金カレンダー（yfinance取得）")
    lines.append(f"")
    lines.append(f"> 生成日時: {now_str}  ")
    lines.append(f"> 支払月は「権利落ち月 +3ヶ月」で推定。実際の入金月と1ヶ月前後ずれる場合あり。  ")
    lines.append(f"> NISA口座の日本株は非課税。特定口座は20.315%源泉徴収後の手取り額。")
    lines.append(f"")

    # ── 表A: 銘柄別サマリー ──────────────────────────────────────────
    lines.append(f"## 銘柄別サマリー")
    lines.append(f"")
    lines.append(f"| コード | 銘柄名 | 特定株数 | NISA株数 | 年間1株配当 | 推定支払月 | データ |")
    lines.append(f"|---|---|---:|---:|---:|---|---|")

    no_data_codes = []
    for code in sorted(results.keys()):
        r = results[code]
        pay_months_str = "・".join(f"{m}月" for m in sorted(r.get("pay_months", {}).keys()))
        annual = r.get("annual_per_share", 0.0)
        src = r.get("source", "no_data")
        src_mark = "✅" if src == "yfinance" else ("❓" if src == "no_data" else "⚠️")
        lines.append(f"| {code} | {r['name']} | {r['tokutei']:,} | {r['nisa']:,} | {annual:,.1f}円 | {pay_months_str or '-'} | {src_mark} |")
        if src != "yfinance":
            no_data_codes.append(f"{code}（{r['name']}）")

    lines.append(f"")

    if no_data_codes:
        lines.append(f"> ⚠️ データ未取得: {', '.join(no_data_codes)}")
        lines.append(f"> yfinanceに配当履歴がない銘柄。IRや株探で手動確認が必要。")
        lines.append(f"")

    # ── 表B: 月別サマリー ────────────────────────────────────────────
    lines.append(f"## 月別配当カレンダー")
    lines.append(f"")
    lines.append(f"| 月 | 特定(税引後) | NISA | 合計(税引後) | 合計(税引前) |")
    lines.append(f"|---|---:|---:|---:|---:|")

    total_tok_after = 0.0
    total_nisa_after = 0.0
    total_tok_before = 0.0
    total_nisa_before = 0.0

    for m in range(1, 13):
        t_after  = int(monthly_tokutei_after.get(m, 0))
        n_after  = int(monthly_nisa_after.get(m, 0))
        t_before = int(monthly_tokutei_before.get(m, 0))
        n_before = int(monthly_nisa_before.get(m, 0))
        combined_after  = t_after + n_after
        combined_before = t_before + n_before
        total_tok_after  += t_after
        total_nisa_after += n_after
        total_tok_before += t_before
        total_nisa_before += n_before
        lines.append(f"| {MONTHS_JA[m-1]} | {t_after:,} | {n_after:,} | {combined_after:,} | {combined_before:,} |")

    total_after  = int(total_tok_after + total_nisa_after)
    total_before = int(total_tok_before + total_nisa_before)
    lines.append(f"| **合計** | **{int(total_tok_after):,}** | **{int(total_nisa_after):,}** | **{total_after:,}** | **{total_before:,}** |")
    lines.append(f"")

    # ── 表C: 年間サマリー ────────────────────────────────────────────
    lines.append(f"## 年間サマリー")
    lines.append(f"")
    lines.append(f"| 項目 | 金額 |")
    lines.append(f"|---|---:|")
    lines.append(f"| 特定口座 税引前 | {int(total_tok_before):,}円 |")
    lines.append(f"| 特定口座 源泉税 | {int(total_tok_before - total_tok_after):,}円 |")
    lines.append(f"| 特定口座 税引後 | {int(total_tok_after):,}円 |")
    lines.append(f"| NISA口座（非課税） | {int(total_nisa_after):,}円 |")
    lines.append(f"| **合計 税引前** | **{total_before:,}円** |")
    lines.append(f"| **合計 税引後（手取り）** | **{total_after:,}円** |")
    lines.append(f"")

    # ── 出力 ─────────────────────────────────────────────────────────
    md = "\n".join(lines)
    output_path.write_text(md, encoding="utf-8")
    print(f"\n出力完了: {output_path}", file=sys.stderr)
    print(f"合計税引後: {total_after:,}円 / 税引前: {total_before:,}円", file=sys.stderr)

    # stdoutにも出力（GitHub Actionsでログ確認用）
    print(md)


if __name__ == "__main__":
    main()
