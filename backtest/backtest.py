"""
실적 미스 후 눌림목 매수 전략 백테스트 엔진

규칙 (투자자 본인의 규칙을 코드로 옮긴 것):
  1) 진입 신호: '실적 미스 후 하락'의 대용(proxy) 신호
     - 오늘 종가가 최근 20거래일 최고가(High) 대비 8% 이상 하락했고
     - 그 최고가가 최근 5거래일 안에 찍혔을 때 (= 5일 안에 급락)
     - 신호가 나온 다음 날 시가에 1차 매수 (미래 정보 사용 방지)
  2) 익절: 평균단가 대비 +X% 도달 시 전량 매도
  3) 물타기: 평균단가 대비 -X% 도달 시 같은 금액 추가 매수 (최대 2회)
  4) 손절 없음 (투자자 규칙에 손절이 없으므로). 기간 끝까지 못 팔면 '미청산'으로 평가
  X 는 7, 8, 9, 10 % 를 각각 시험한다.

자금 가정: 종목당 자본 1.0 을 3등분(1차 매수 + 물타기 2회). 쓰지 않은 돈은 현금(이자 0).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
RESULT_DIR = os.path.join(BASE, "results")

# 쉼표로 구분한 BT_TICKERS 환경변수로 종목을 바꿀 수 있음 (예: BT_TICKERS="MA,MSFT,NVDA")
TICKERS = [t.strip().upper() for t in os.environ.get("BT_TICKERS", "ABNB,AMZN,AVGO,ISRG,MA,META,NFLX,V").split(",") if t.strip()]
X_LIST = [7, 8, 9, 10]

# 기본 설정
DROP_PCT = 0.08      # 20일 고점 대비 하락폭
LOOKBACK = 20        # 고점을 찾는 기간(거래일)
WITHIN_DAYS = 5      # 고점 후 며칠 안에 떨어져야 '급락'으로 볼지
MAX_ADDS = 2         # 물타기 최대 횟수
FEE = 0.0025         # 매수/매도 각각 수수료 0.25% (국내 증권사 해외주식 수수료 수준 가정)


# ---------------------------------------------------------------- 데이터
def load_prices(ticker: str, data_dir: str = DATA_DIR) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(data_dir, f"{ticker}.csv"), parse_dates=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df[["Date", "Open", "High", "Low", "Close"]]


# ---------------------------------------------------------------- 신호
def find_signals(df: pd.DataFrame, drop: float = DROP_PCT, lookback: int = LOOKBACK,
                 within: int = WITHIN_DAYS) -> pd.Series:
    """각 날짜에 신호가 있는지(True/False). 그날 장 마감 후 알 수 있는 정보만 사용."""
    high = df["High"]
    roll_max = high.rolling(lookback, min_periods=lookback).max()
    # 최근 lookback일 중 최고가가 며칠 전이었는지 (0 = 오늘). 같은 최고가가 여러 번이면 가장 최근 날 기준
    days_since_high = high.rolling(lookback, min_periods=lookback).apply(
        lambda w: int(w[::-1].argmax()), raw=True)
    cond = (df["Close"] <= roll_max * (1 - drop)) & (days_since_high <= within)
    return cond.fillna(False).astype(bool)


# ---------------------------------------------------------------- 엔진
@dataclass
class Trade:
    entry_date: str
    exit_date: str | None
    adds: int
    invested: float          # 들어간 돈(수수료 포함)
    proceeds: float          # 회수한 돈(수수료 차감). 미청산이면 마지막 종가 기준 평가액
    pnl_pct: float           # 투입금 대비 손익률
    hold_days: int           # 달력 기준 보유일
    closed: bool             # True = 익절로 청산, False = 기간 종료 시 보유 중
    fills: list = field(default_factory=list)


def run_backtest(df: pd.DataFrame, x: float, signals: pd.Series | None = None,
                 max_adds: int = MAX_ADDS, fee: float = FEE) -> dict:
    """
    x: 익절/물타기 기준(소수, 예 0.07)
    하루에 한 가지 행동만 한다. 같은 날 물타기 선과 익절 선을 모두 건드리면
    (일봉으로는 순서를 알 수 없으므로) 보수적으로 '물타기'가 먼저 일어났다고 보고 익절은 다음 날부터 본다.
    """
    if signals is None:
        signals = find_signals(df)
    tranche = 1.0 / (max_adds + 1)
    cash, shares, cost_basis = 1.0, 0.0, 0.0   # cost_basis: 수수료 제외 순수 매입금
    adds, invested = 0, 0.0
    entry_idx = None
    fills: list = []
    trades: list[Trade] = []
    equity = []
    exposure = []   # 매일 자본 중 주식에 들어가 있는 비율
    pending_entry = False

    dates = df["Date"].dt.strftime("%Y-%m-%d").tolist()
    O, H, L, C = (df[c].tolist() for c in ("Open", "High", "Low", "Close"))
    sig = signals.tolist()

    def buy(price, i):
        nonlocal cash, shares, cost_basis, invested
        amount = min(tranche, cash)
        sh = amount / (1 + fee) / price
        cash -= amount
        shares += sh
        cost_basis += sh * price
        invested += amount
        fills.append({"date": dates[i], "side": "BUY", "price": round(price, 4)})

    for i in range(len(df)):
        acted = False
        # 1) 전날 신호 -> 오늘 시가 매수
        if pending_entry and shares == 0:
            buy(O[i], i)
            entry_idx = i
            adds = 0
            acted = True
        pending_entry = False

        # 2) 보유 중이면 물타기 / 익절 판단
        if shares > 0 and not acted:
            avg = cost_basis / shares
            add_line = avg * (1 - x)
            tp_line = avg * (1 + x)
            if adds < max_adds and L[i] <= add_line:
                price = min(O[i], add_line)          # 시가가 이미 더 낮으면 시가에 체결
                buy(price, i)
                adds += 1
            elif H[i] >= tp_line:
                price = max(O[i], tp_line)           # 시가가 이미 더 높으면 시가에 체결
                proceeds = shares * price * (1 - fee)
                cash += proceeds
                fills.append({"date": dates[i], "side": "SELL", "price": round(price, 4)})
                trades.append(Trade(dates[entry_idx], dates[i], adds, invested, proceeds,
                                    proceeds / invested - 1,
                                    (df["Date"][i] - df["Date"][entry_idx]).days, True, fills))
                shares, cost_basis, invested, adds, fills = 0.0, 0.0, 0.0, 0, []

        # 3) 오늘 종가 기준 신호 -> 내일 매수 예약 (보유 중이 아닐 때만)
        if shares == 0 and sig[i]:
            pending_entry = True

        equity.append(cash + shares * C[i])
        exposure.append(shares * C[i] / equity[-1] if equity[-1] > 0 else 0.0)

    # 기간 종료 시 미청산 포지션 평가
    if shares > 0:
        value = shares * C[-1] * (1 - fee)
        trades.append(Trade(dates[entry_idx], None, adds, invested, value, value / invested - 1,
                            (df["Date"].iloc[-1] - df["Date"][entry_idx]).days, False, fills))

    eq = pd.Series(equity, index=df["Date"])
    summary = summarize(eq, trades, df)
    summary["avg_exposure"] = float(sum(exposure) / len(exposure))
    summary["days_in_market"] = float(sum(e > 0 for e in exposure) / len(exposure))
    return {
        "equity": eq,
        "trades": trades,
        "summary": summary,
    }


def max_drawdown(eq: pd.Series) -> float:
    peak = eq.cummax()
    return float(((eq / peak) - 1).min())


def buy_and_hold(df: pd.DataFrame, fee: float = FEE) -> pd.Series:
    sh = 1.0 / (1 + fee) / df["Open"].iloc[0]
    return pd.Series(sh * df["Close"].values, index=df["Date"])


def summarize(eq: pd.Series, trades: list[Trade], df: pd.DataFrame) -> dict:
    closed = [t for t in trades if t.closed]
    open_ = [t for t in trades if not t.closed]
    bh = buy_and_hold(df)
    return {
        "trades_total": len(trades),
        "trades_closed": len(closed),
        "trades_open": len(open_),
        "win_rate": (sum(t.pnl_pct > 0 for t in trades) / len(trades)) if trades else None,
        "avg_hold_days": (sum(t.hold_days for t in trades) / len(trades)) if trades else None,
        "max_hold_days": max((t.hold_days for t in trades), default=None),
        "adds_used_trades": sum(t.adds > 0 for t in trades),
        "max_adds_trades": sum(t.adds == MAX_ADDS for t in trades),
        "open_pnl_pct": open_[0].pnl_pct if open_ else None,
        "total_return": float(eq.iloc[-1] - 1),
        "mdd": max_drawdown(eq),
        "bh_return": float(bh.iloc[-1] - 1),
        "bh_mdd": max_drawdown(bh),
    }


# ---------------------------------------------------------------- 실행
def run_all(tickers=TICKERS, x_list=X_LIST, data_dir=DATA_DIR) -> dict:
    out = {"per_ticker": {}, "portfolio": {}, "equity": {}, "bh_equity": {}, "signals": {}}
    for tk in tickers:
        df = load_prices(tk, data_dir)
        sig = find_signals(df)
        out["signals"][tk] = df["Date"][sig].dt.strftime("%Y-%m-%d").tolist()
        out["bh_equity"][tk] = buy_and_hold(df)
        for x in x_list:
            r = run_backtest(df, x / 100, sig)
            out["per_ticker"][(tk, x)] = r
            out["equity"][(tk, x)] = r["equity"]
    # 8종목 동일비중 포트폴리오 (각 종목에 자본 1/8, 리밸런싱 없음)
    bh_port = pd.concat([out["bh_equity"][t] for t in tickers], axis=1).mean(axis=1)
    out["bh_port"] = bh_port
    for x in x_list:
        port = pd.concat([out["equity"][(t, x)] for t in tickers], axis=1).mean(axis=1)
        out["portfolio"][x] = {
            "equity": port,
            "total_return": float(port.iloc[-1] - 1),
            "mdd": max_drawdown(port),
            "bh_return": float(bh_port.iloc[-1] - 1),
            "bh_mdd": max_drawdown(bh_port),
            "trades": sum(out["per_ticker"][(t, x)]["summary"]["trades_total"] for t in tickers),
            "win_rate": _pooled_win(out, tickers, x),
            "avg_hold_days": _pooled_hold(out, tickers, x),
            "avg_exposure": sum(out["per_ticker"][(t, x)]["summary"]["avg_exposure"] for t in tickers) / len(tickers),
            "open_positions": sum(out["per_ticker"][(t, x)]["summary"]["trades_open"] for t in tickers),
        }
    return out


def _all_trades(out, tickers, x):
    return [t for tk in tickers for t in out["per_ticker"][(tk, x)]["trades"]]


def _pooled_win(out, tickers, x):
    ts = _all_trades(out, tickers, x)
    return sum(t.pnl_pct > 0 for t in ts) / len(ts) if ts else None


def _pooled_hold(out, tickers, x):
    ts = _all_trades(out, tickers, x)
    return sum(t.hold_days for t in ts) / len(ts) if ts else None


def save_results(out: dict, tickers=TICKERS, x_list=X_LIST) -> None:
    os.makedirs(RESULT_DIR, exist_ok=True)
    rows, trade_rows = [], []
    for (tk, x), r in out["per_ticker"].items():
        rows.append({"ticker": tk, "x_pct": x, **r["summary"]})
        for t in r["trades"]:
            d = asdict(t)
            d.pop("fills")
            trade_rows.append({"ticker": tk, "x_pct": x, **d,
                               "fills": " | ".join(f"{f['date']} {f['side']} {f['price']}" for f in t.fills)})
    pd.DataFrame(rows).to_csv(os.path.join(RESULT_DIR, "summary_by_ticker.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(trade_rows).to_csv(os.path.join(RESULT_DIR, "trades.csv"), index=False, encoding="utf-8-sig")
    port = [{"x_pct": x, **{k: v for k, v in p.items() if k != "equity"}} for x, p in out["portfolio"].items()]
    pd.DataFrame(port).to_csv(os.path.join(RESULT_DIR, "summary_portfolio.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(RESULT_DIR, "signals.json"), "w", encoding="utf-8") as f:
        json.dump(out["signals"], f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    res = run_all()
    save_results(res)
    for x, p in res["portfolio"].items():
        print(f"X={x}%  전략 {p['total_return']*100:6.1f}%  MDD {p['mdd']*100:6.1f}%  | "
              f"단순보유 {p['bh_return']*100:6.1f}%  MDD {p['bh_mdd']*100:6.1f}%  | "
              f"거래 {p['trades']}  승률 {p['win_rate']*100:.0f}%  평균보유 {p['avg_hold_days']:.0f}일  미청산 {p['open_positions']}  평균투자비중 {p['avg_exposure']*100:.0f}%")
