"""백테스트를 다시 돌리고 report.html 과 결과요약.md 를 만든다."""
import html
import os

import pandas as pd

import backtest as bt

BASE = bt.BASE
COLORS = {7: "#9ab8e8", 8: "#5b8fd9", 9: "#2f6bc4", 10: "#173f86", "bh": "#d9822b"}


def pct(v, d=1, sign=True):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return f"{v*100:+.{d}f}%" if sign else f"{v*100:.{d}f}%"


# ---------------------------------------------------------------- SVG 선 그래프
def line_chart(series: dict, colors: dict, labels: dict, height=260) -> str:
    W, H, L, R, T, B = 640, height, 46, 12, 12, 28
    allv = pd.concat(series.values())
    lo, hi = min(allv.min(), 1.0), allv.max()
    lo, hi = lo - (hi - lo) * 0.03, hi + (hi - lo) * 0.03
    idx = next(iter(series.values())).index
    n = len(idx)

    def xy(i, v):
        return L + (W - L - R) * i / (n - 1), T + (H - T - B) * (1 - (v - lo) / (hi - lo))

    out = [f'<svg viewBox="0 0 {W} {H}" role="img" class="chart">']
    # 가로 눈금
    step = 0.25 if hi - lo < 1.6 else 0.5
    g = (int(lo / step) + 1) * step
    while g < hi:
        _, y = xy(0, g)
        out.append(f'<line x1="{L}" x2="{W-R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{L-6}" y="{y+4:.1f}" class="ax" text-anchor="end">{(g-1)*100:+.0f}%</text>')
        g += step
    _, y1 = xy(0, 1.0)
    out.append(f'<line x1="{L}" x2="{W-R}" y1="{y1:.1f}" y2="{y1:.1f}" class="base"/>')
    # 연도 표시
    for yr in sorted(set(idx.year)):
        pos = [i for i, d in enumerate(idx) if d.year == yr]
        if pos and pos[0] > 0:
            x, _ = xy(pos[0], lo)
            out.append(f'<text x="{x:.1f}" y="{H-8}" class="ax" text-anchor="middle">{yr}</text>')
    for k, s in series.items():
        pts = " ".join(f"{xy(i, v)[0]:.1f},{xy(i, v)[1]:.1f}" for i, v in enumerate(s.values) if i % 3 == 0 or i == n - 1)
        w = 2.4 if k == "bh" else 1.8
        out.append(f'<polyline fill="none" stroke="{colors[k]}" stroke-width="{w}" stroke-linejoin="round" points="{pts}"><title>{html.escape(labels[k])}</title></polyline>')
        x, y = xy(n - 1, s.values[-1])
    out.append("</svg>")
    leg = "".join(f'<span><i style="background:{colors[k]}"></i>{html.escape(labels[k])} '
                  f'<b>{pct(series[k].values[-1]-1, 0)}</b></span>' for k in series)
    return "".join(out) + f'<div class="legend">{leg}</div>'


def bar_row(v, vmax, color):
    w = max(0.0, min(1.0, abs(v) / vmax)) * 100
    cls = "neg" if v < 0 else ""
    return f'<div class="bar {cls}"><span style="width:{w:.0f}%;background:{color}"></span></div>'


# ---------------------------------------------------------------- 본문
def build(res):
    T, X = bt.TICKERS, bt.X_LIST
    P = res["portfolio"]
    first = res["bh_port"].index[0].strftime("%Y-%m-%d")
    last = res["bh_port"].index[-1].strftime("%Y-%m-%d")
    total_signals = sum(len(v) for v in res["signals"].values())
    ps = {x: P[x] for x in X}
    best_x = max(X, key=lambda x: P[x]["total_return"])
    worst_x = min(X, key=lambda x: P[x]["total_return"])
    bh_r, bh_m = P[X[0]]["bh_return"], P[X[0]]["bh_mdd"]
    beat = {x: [t for t in T if res["per_ticker"][(t, x)]["summary"]["total_return"] > res["per_ticker"][(t, x)]["summary"]["bh_return"]] for x in X}
    open_tr = [(t, tr) for t in T for tr in res["per_ticker"][(t, 8)]["trades"] if not tr.closed]
    all_tr = [(t, tr) for t in T for x in X for tr in res["per_ticker"][(t, x)]["trades"]]
    wt_tk, worst_trade = min(all_tr, key=lambda a: a[1].pnl_pct)
    lg_tk, longest = max(all_tr, key=lambda a: a[1].hold_days)
    worst_trade.tk, longest.tk = wt_tk, lg_tk

    facts = {
        "period": f"{first} ~ {last}",
        "best_x": best_x, "worst_x": worst_x,
        "strat_range": f"{pct(P[worst_x]['total_return'])} ~ {pct(P[best_x]['total_return'])}",
        "bh": pct(bh_r), "bh_mdd": pct(bh_m),
        "strat_mdd_range": f"{pct(min(p['mdd'] for p in ps.values()))} ~ {pct(max(p['mdd'] for p in ps.values()))}",
        "win_range": f"{min(p['win_rate'] for p in ps.values())*100:.0f}~{max(p['win_rate'] for p in ps.values())*100:.0f}%",
        "exp_range": f"{min(p['avg_exposure'] for p in ps.values())*100:.0f}~{max(p['avg_exposure'] for p in ps.values())*100:.0f}%",
        "trades_range": f"{min(p['trades'] for p in ps.values())}~{max(p['trades'] for p in ps.values())}",
        "hold_range": f"{min(p['avg_hold_days'] for p in ps.values()):.0f}~{max(p['avg_hold_days'] for p in ps.values()):.0f}일",
        "beat": beat,
        "open_tr": open_tr,
        "worst_trade": worst_trade,
        "longest": longest,
        "signals": total_signals,
    }
    return facts


def render_html(res, f):
    T, X = bt.TICKERS, bt.X_LIST
    P = res["portfolio"]
    series = {x: P[x]["equity"] for x in X}
    series["bh"] = res["bh_port"]
    labels = {x: f"전략 X={x}%" for x in X}
    labels["bh"] = "그냥 사서 보유"
    chart = line_chart(series, COLORS, labels)

    # 포트폴리오 표
    prow = "".join(
        f"<tr><td>X={x}%</td><td class='num'>{pct(P[x]['total_return'])}</td><td class='num'>{pct(P[x]['mdd'])}</td>"
        f"<td class='num'>{P[x]['trades']}</td><td class='num'>{P[x]['win_rate']*100:.0f}%</td>"
        f"<td class='num'>{P[x]['avg_hold_days']:.0f}일</td><td class='num'>{P[x]['avg_exposure']*100:.0f}%</td></tr>"
        for x in X)
    prow += (f"<tr class='bh'><td>그냥 보유</td><td class='num'>{pct(P[X[0]]['bh_return'])}</td>"
             f"<td class='num'>{pct(P[X[0]]['bh_mdd'])}</td><td class='num'>-</td><td class='num'>-</td>"
             f"<td class='num'>5년</td><td class='num'>100%</td></tr>")

    # 종목별 카드
    cards = []
    for t in T:
        rs = {x: res["per_ticker"][(t, x)]["summary"] for x in X}
        bhv = rs[X[0]]["bh_return"]
        vmax = max([abs(bhv)] + [abs(rs[x]["total_return"]) for x in X]) or 1
        rows = "".join(
            f"<div class='br'><span class='lab'>X={x}%</span>{bar_row(rs[x]['total_return'], vmax, COLORS[x])}"
            f"<span class='val'>{pct(rs[x]['total_return'],0)}</span></div>" for x in X)
        rows += (f"<div class='br'><span class='lab'>보유</span>{bar_row(bhv, vmax, COLORS['bh'])}"
                 f"<span class='val'>{pct(bhv,0)}</span></div>")
        r8 = rs[8]
        op = res["per_ticker"][(t, 8)]["trades"]
        open_note = ""
        if r8["trades_open"]:
            o = [tr for tr in op if not tr.closed][0]
            open_note = f"<p class='warn'>현재 미청산: {o.entry_date} 진입, 물타기 {o.adds}회, 평가손익 {pct(o.pnl_pct)} ({o.hold_days}일째)</p>"
        cards.append(
            f"<div class='card'><h3>{t}</h3>{rows}"
            f"<p class='meta'>X=8% 기준: 거래 {r8['trades_total']}회 · 승률 {r8['win_rate']*100:.0f}% · 평균 {r8['avg_hold_days']:.0f}일 보유 · "
            f"최장 {r8['max_hold_days']}일 · 최대낙폭 {pct(r8['mdd'],0)} (보유 시 {pct(r8['bh_mdd'],0)})</p>{open_note}</div>")

    beat_txt = " / ".join(f"X={x}%: {len(f['beat'][x])}개" for x in X)
    wt, lg = f["worst_trade"], f["longest"]
    open_list = "".join(f"<li>{t}: {tr.entry_date} 진입, 물타기 {tr.adds}회, 평가손익 {pct(tr.pnl_pct)}</li>" for t, tr in f["open_tr"])

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>눌림목 매수 백테스트</title>
<style>
:root{{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--mut:#6b6b70;--line:#e3e3e0;--warn:#a1460b;--warnbg:#fff3e6;--ok:#1d6b3a;--okbg:#eaf6ee;--grid:#ececea}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#151517;--card:#1f1f22;--fg:#ececee;--mut:#a0a0a8;--line:#333338;--warn:#f0a66a;--warnbg:#2e2218;--ok:#7fd39b;--okbg:#18291e;--grid:#2a2a2e}}}}
:root[data-theme="dark"]{{--bg:#151517;--card:#1f1f22;--fg:#ececee;--mut:#a0a0a8;--line:#333338;--warn:#f0a66a;--warnbg:#2e2218;--ok:#7fd39b;--okbg:#18291e;--grid:#2a2a2e}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}}
main{{max-width:760px;margin:0 auto;padding:20px 16px 60px}}
h1{{font-size:22px;margin:4px 0 4px}} h2{{font-size:18px;margin:32px 0 10px;padding-top:8px;border-top:1px solid var(--line)}}
h3{{font-size:16px;margin:0 0 8px}}
.sub{{color:var(--mut);font-size:13px;margin:0 0 16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:10px 0}}
.fact{{background:var(--okbg);border-left:4px solid var(--ok)}} .guess{{background:var(--warnbg);border-left:4px solid var(--warn)}}
.fact h3{{color:var(--ok)}} .guess h3{{color:var(--warn)}}
ul{{padding-left:20px;margin:6px 0}} li{{margin:4px 0}}
.tbl{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:13px;min-width:460px}}
th,td{{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}} th{{color:var(--mut);font-weight:600}}
.num{{text-align:right;font-variant-numeric:tabular-nums}} tr.bh td{{font-weight:600}}
.chart{{width:100%;height:auto;display:block}} .grid{{stroke:var(--grid)}} .base{{stroke:var(--mut);stroke-dasharray:3 3}}
.ax{{fill:var(--mut);font-size:11px}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--mut);margin-top:6px}}
.legend i{{display:inline-block;width:12px;height:3px;vertical-align:middle;margin-right:4px;border-radius:2px}}
.legend b{{color:var(--fg)}}
.grid2{{display:grid;grid-template-columns:1fr;gap:0}} @media(min-width:640px){{.grid2{{grid-template-columns:1fr 1fr;gap:0 10px}}}}
.br{{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px}}
.lab{{width:44px;color:var(--mut)}} .val{{width:48px;text-align:right;font-variant-numeric:tabular-nums}}
.bar{{flex:1;height:10px;background:var(--grid);border-radius:5px;overflow:hidden}} .bar span{{display:block;height:100%;border-radius:5px}}
.bar.neg span{{opacity:.45;background-image:repeating-linear-gradient(45deg,transparent 0 3px,rgba(0,0,0,.35) 3px 5px)}}
.meta{{color:var(--mut);font-size:12px;margin:8px 0 0}} .warn{{color:var(--warn);font-size:12px;margin:4px 0 0}}
.note{{font-size:13px;color:var(--mut)}}
</style></head><body><main>
<h1>실적 미스 눌림목 매수 전략 백테스트</h1>
<p class="sub">8개 미국 종목 · {f['period']} 일봉 · 데이터 출처: PlayMCP UsStockInfo(야후 파이낸스 기반, 배당·분할 반영 가격) · 작성일 2026-11-04</p>

<div class="card guess"><h3>먼저 읽어 주세요</h3>
<ul><li>이 보고서는 <b>과거 데이터로 규칙을 흉내 낸 결과</b>일 뿐이며, 특정 종목의 매수·매도 추천이 아닙니다.</li>
<li>'실적 미스' 날짜·EPS 데이터를 구하지 못해 <b>"20일 고점 대비 8% 이상, 5일 안에 급락"</b>을 대신 썼습니다. 실제 실적 발표와 무관한 급락도 포함됩니다.</li></ul></div>

<h2>1. 전략 규칙 (코드로 옮긴 내용)</h2>
<div class="card"><ul>
<li><b>매수 신호</b>: 종가가 최근 20거래일 고가보다 8% 이상 낮고, 그 고가가 최근 5거래일 안에 나왔을 때 → <b>다음 날 시가</b>에 1차 매수</li>
<li><b>익절</b>: 평균단가 대비 +X% 닿으면 전량 매도</li>
<li><b>물타기</b>: 평균단가 대비 -X% 닿으면 같은 금액 추가 매수, 최대 2회</li>
<li><b>손절 없음</b> (본인 규칙에 없음). 기간 끝까지 못 판 건 마지막 날 종가로 평가</li>
<li>X = 7, 8, 9, 10% 네 가지를 각각 시험 · 종목당 돈을 3등분(1차+물타기 2회) · 쉬는 돈은 이자 0 · 수수료 매수/매도 각 0.25%</li>
<li>8종목에 돈을 똑같이 나눠 넣은 것을 '포트폴리오'로 봄. 비교 대상은 첫날 사서 끝까지 들고 있는 것(그냥 보유)</li>
</ul></div>

<h2>2. 8종목 합산 결과</h2>
<div class="card">{chart}</div>
<div class="card tbl"><table>
<tr><th>설정</th><th class="num">5년 수익률</th><th class="num">최대낙폭</th><th class="num">거래 수</th><th class="num">승률</th><th class="num">평균 보유</th><th class="num">평균 투자비중</th></tr>
{prow}</table>
<p class="note">평균 투자비중 = 전체 돈 중 실제로 주식에 들어가 있던 비율의 평균. 나머지는 현금으로 놀고 있던 돈입니다.</p></div>

<h2>3. 종목별 결과 (5년 수익률)</h2>
<p class="note">빗금 막대 = 손실. 막대 길이는 종목 안에서만 비교하세요(종목마다 눈금이 다릅니다).</p>
<div class="grid2">{''.join(cards)}</div>

<h2>4. 데이터로 확인된 사실</h2>
<div class="card fact"><h3>숫자로 확인됨</h3><ul>
<li>8종목 합산 5년 수익률: 전략 <b>{f['strat_range']}</b> (X 설정에 따라), 그냥 보유 <b>{f['bh']}</b></li>
<li>최대낙폭: 전략 {f['strat_mdd_range']}, 그냥 보유 {f['bh_mdd']}</li>
<li>거래 {f['trades_range']}회, 승률 {f['win_range']}, 평균 보유 {f['hold_range']}</li>
<li>평균 투자비중은 {f['exp_range']}에 그침 → 돈 대부분이 현금으로 쉬고 있었음</li>
<li>'그냥 보유'보다 수익률이 높았던 종목 수: {beat_txt} (8개 중)</li>
<li>가장 큰 손실 거래: {wt.tk} {html.escape(wt.entry_date)} 진입, 물타기 {wt.adds}회 후 평가손익 {pct(wt.pnl_pct)}</li>
<li>가장 오래 묶인 거래: {lg.tk} {lg.hold_days}일 ({html.escape(lg.entry_date)} ~ {html.escape(str(lg.exit_date))}, 물타기 {lg.adds}회)</li>
<li>2026-11-03 기준 아직 팔지 못한 포지션 (X=8%):<ul>{open_list}</ul></li>
</ul></div>

<h2>5. 추정 · 한계</h2>
<div class="card guess"><h3>해석할 때 주의</h3><ul>
<li><b>승률이 높은 이유</b>는 손절이 없어서입니다. 손실 중인 거래는 '진 거래'로 잡히지 않고 계속 들고 있게 되며, 기간이 끝나면 미청산으로 남습니다. 높은 승률 ≠ 안전함.</li>
<li><b>최대낙폭이 작아 보이는 이유</b>도 대부분 현금이라서입니다. 투자된 돈만 보면 물타기 후 -15~-40% 평가손실이 실제로 발생했습니다.</li>
<li>신호는 실적 발표가 아니라 가격 급락으로 대신했습니다. 실제 '실적 미스' 데이터로 하면 거래 횟수·결과가 달라질 수 있습니다.</li>
<li>'수익 나는 회사' 조건은 따로 걸러내지 않았습니다. 8종목은 투자자가 고른 목록이며, 5년 동안 크게 오른 회사들이라 결과가 좋게 나오는 쪽으로 치우쳤을 가능성(생존·선택 편향)이 있습니다.</li>
<li>일봉만 쓰므로 같은 날 물타기 선과 익절 선을 모두 지나면 순서를 알 수 없어, 보수적으로 '물타기 먼저'로 처리했습니다.</li>
<li>환율, 세금(해외주식 양도세 22%), 슬리피지는 반영하지 않았습니다. 수수료만 0.25%로 가정했습니다.</li>
<li>X 중 어느 값이 '최적'이라고 보기 어렵습니다. 거래 수가 종목당 2~15회로 적어서 차이가 우연일 수 있습니다.</li>
<li>과거 결과는 미래 수익을 보장하지 않습니다.</li>
</ul></div>
<p class="note">상세 거래 내역: results/trades.csv · 종목별 요약: results/summary_by_ticker.csv · 원본 가격: data/*.csv</p>
</main></body></html>"""


def render_md(res, f):
    T, X = bt.TICKERS, bt.X_LIST
    P = res["portfolio"]
    lines = [
        "# 결과 요약 — 실적 미스 눌림목 매수 전략 백테스트",
        "",
        f"- 기간: {f['period']} (일봉, 8종목: {', '.join(T)})",
        "- 데이터: PlayMCP UsStockInfo (야후 파이낸스 기반, 배당·분할 반영 가격)",
        "- 매수 신호: **실적 데이터 대신** '20일 고점 대비 8% 이상, 5일 안 급락' 사용",
        "- 이 문서는 과거 시뮬레이션이며 매수·매도 추천이 아닙니다.",
        "",
        "## 8종목 합산",
        "",
        "| 설정 | 5년 수익률 | 최대낙폭 | 거래 | 승률 | 평균보유 | 평균 투자비중 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for x in X:
        p = P[x]
        lines.append(f"| X={x}% | {pct(p['total_return'])} | {pct(p['mdd'])} | {p['trades']} | {p['win_rate']*100:.0f}% | {p['avg_hold_days']:.0f}일 | {p['avg_exposure']*100:.0f}% |")
    lines.append(f"| 그냥 보유 | {pct(P[X[0]]['bh_return'])} | {pct(P[X[0]]['bh_mdd'])} | - | - | 5년 | 100% |")
    lines += ["", "## 종목별 5년 수익률", "",
              "| 종목 | X=7% | X=8% | X=9% | X=10% | 그냥 보유 |", "|---|---:|---:|---:|---:|---:|"]
    for t in T:
        r = [res["per_ticker"][(t, x)]["summary"] for x in X]
        lines.append(f"| {t} | " + " | ".join(pct(s["total_return"]) for s in r) + f" | {pct(r[0]['bh_return'])} |")
    beat_txt = " / ".join(f"X={x}%: {len(f['beat'][x])}개" for x in X)
    lines += ["", "## 데이터로 확인된 사실", "",
              f"- 8종목 합산 수익률: 전략 {f['strat_range']}, 그냥 보유 {f['bh']}",
              f"- 최대낙폭: 전략 {f['strat_mdd_range']}, 그냥 보유 {f['bh_mdd']}",
              f"- 승률 {f['win_range']}, 평균 보유 {f['hold_range']}, 평균 투자비중 {f['exp_range']}",
              f"- 그냥 보유보다 나았던 종목 수(8개 중): {beat_txt}",
              f"- 가장 큰 손실 거래: {f['worst_trade'].tk} {f['worst_trade'].entry_date} 진입, 평가손익 {pct(f['worst_trade'].pnl_pct)}",
              f"- 가장 오래 묶인 거래: {f['longest'].tk} {f['longest'].hold_days}일 ({f['longest'].entry_date} ~ {f['longest'].exit_date})",
              "- 2026-11-03 기준 미청산(X=8%): " + ", ".join(f"{t} {pct(tr.pnl_pct)}" for t, tr in f["open_tr"]),
              "", "## 추정 · 한계", "",
              "- 높은 승률은 손절이 없기 때문. 손실 거래는 팔지 않고 계속 들고 있게 됨.",
              "- 작은 최대낙폭은 돈 대부분이 현금이었기 때문. 투자된 돈 기준 손실은 훨씬 큼.",
              "- 실적 미스 대신 가격 급락을 신호로 써서 실제 규칙과 다를 수 있음.",
              "- '수익 나는 회사' 필터 없음. 이미 많이 오른 8종목이라 결과가 좋게 치우쳤을 수 있음.",
              "- 환율·세금·슬리피지 미반영(수수료 0.25%만 반영). 거래 수가 적어 X별 차이는 우연일 수 있음.",
              "- 과거 결과는 미래 수익을 보장하지 않음.", ""]
    return "\n".join(lines)


def main():
    res = bt.run_all()
    bt.save_results(res)
    f = build(res)
    with open(os.path.join(BASE, "report.html"), "w", encoding="utf-8") as fh:
        fh.write(render_html(res, f))
    with open(os.path.join(BASE, "결과요약.md"), "w", encoding="utf-8") as fh:
        fh.write(render_md(res, f))
    print("report.html, 결과요약.md 생성 완료")


if __name__ == "__main__":
    main()
