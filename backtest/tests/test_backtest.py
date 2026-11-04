"""엔진 규칙이 의도대로 동작하는지 작은 가짜 가격표로 확인하는 테스트"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backtest as bt  # noqa: E402


def make_df(rows):
    """rows: [(open, high, low, close), ...]"""
    dates = pd.bdate_range("2024-01-01", periods=len(rows))
    return pd.DataFrame({"Date": dates, "Open": [r[0] for r in rows], "High": [r[1] for r in rows],
                         "Low": [r[2] for r in rows], "Close": [r[3] for r in rows]})


def sig_at(df, idx):
    s = pd.Series(False, index=df.index)
    for i in idx:
        s.iloc[i] = True
    return s


def flat(p, n):
    return [(p, p, p, p)] * n


# ---------------- 신호
def test_signal_fires_on_quick_8pct_drop():
    rows = flat(100, 25) + [(100, 100, 91, 91)]          # 고점 100 -> 종가 91 (-9%)
    s = bt.find_signals(make_df(rows))
    assert s.iloc[-1]
    assert not s.iloc[:-1].any()


def test_signal_not_fired_on_small_drop():
    rows = flat(100, 25) + [(100, 100, 93, 93)]          # -7% 는 기준 미달
    assert not bt.find_signals(make_df(rows)).any()


def test_signal_not_fired_when_high_is_old():
    # 고점이 10일 전 -> '5일 안의 급락' 아님
    rows = flat(90, 15) + [(100, 100, 100, 100)] + flat(95, 9) + [(91, 91, 91, 91)]
    s = bt.find_signals(make_df(rows))
    assert not s.iloc[-1]


def test_signal_needs_full_lookback():
    rows = flat(100, 5) + [(100, 100, 80, 80)]           # 20일 데이터가 없으면 신호 없음
    assert not bt.find_signals(make_df(rows)).any()


# ---------------- 진입 / 익절
def test_entry_next_open_and_take_profit():
    rows = flat(100, 3) + [(100, 108, 99, 107)]
    df = make_df(rows)
    r = bt.run_backtest(df, 0.07, sig_at(df, [1]), fee=0)
    t = r["trades"][0]
    assert t.entry_date == str(df["Date"][2].date())       # 신호 다음 날 시가
    assert t.closed and t.adds == 0
    assert t.pnl_pct == pytest.approx(0.07)
    # 자본의 1/3만 투입 -> 전체 수익률은 7%/3
    assert r["summary"]["total_return"] == pytest.approx(0.07 / 3)


def test_take_profit_gap_up_fills_at_open():
    rows = flat(100, 3) + [(120, 121, 119, 120)]
    df = make_df(rows)
    t = bt.run_backtest(df, 0.07, sig_at(df, [1]), fee=0)["trades"][0]
    assert t.pnl_pct == pytest.approx(0.20)


# ---------------- 물타기
def test_average_down_then_exit_from_new_average():
    rows = flat(100, 3) + [(100, 100, 93, 94)] + [(94, 104, 94, 103)]
    df = make_df(rows)
    r = bt.run_backtest(df, 0.07, sig_at(df, [1]), fee=0)
    t = r["trades"][0]
    assert t.adds == 1
    # 같은 금액으로 100, 93 매수 -> 평균단가 = 조화평균
    avg = 2 / (1 / 100 + 1 / 93)
    assert t.closed
    assert t.pnl_pct == pytest.approx(0.07)
    assert any(f["price"] == pytest.approx(round(avg * 1.07, 4), abs=1e-3) for f in t.fills if f["side"] == "SELL")


def test_max_two_adds():
    rows = flat(100, 3) + [(100, 100, 50, 50)] * 5 + [(40, 40, 40, 40)] * 3
    df = make_df(rows)
    r = bt.run_backtest(df, 0.07, sig_at(df, [1]), fee=0)
    t = r["trades"][0]
    assert t.adds == 2
    assert not t.closed                          # 손절 규칙 없음 -> 끝까지 보유
    assert sum(f["side"] == "BUY" for f in t.fills) == 3
    assert t.invested == pytest.approx(1.0)


def test_add_and_tp_same_day_does_add_only():
    rows = flat(100, 3) + [(100, 110, 90, 100)]
    df = make_df(rows)
    t = bt.run_backtest(df, 0.07, sig_at(df, [1]), fee=0)["trades"][0]
    assert t.adds == 1 and not t.closed


# ---------------- 기타
def test_no_signal_no_trade():
    df = make_df(flat(100, 30))
    r = bt.run_backtest(df, 0.07, fee=0)
    assert r["trades"] == []
    assert r["summary"]["total_return"] == pytest.approx(0)


def test_fee_reduces_return():
    rows = flat(100, 3) + [(100, 108, 99, 107)]
    df = make_df(rows)
    a = bt.run_backtest(df, 0.07, sig_at(df, [1]), fee=0)["summary"]["total_return"]
    b = bt.run_backtest(df, 0.07, sig_at(df, [1]), fee=0.0025)["summary"]["total_return"]
    assert b < a


def test_max_drawdown():
    eq = pd.Series([1.0, 1.2, 0.9, 1.3, 1.04])
    assert bt.max_drawdown(eq) == pytest.approx(-0.25)


def test_reentry_after_exit():
    rows = flat(100, 3) + [(100, 108, 99, 107), (107, 107, 107, 107), (100, 100, 100, 100), (100, 108, 100, 108)]
    df = make_df(rows)
    r = bt.run_backtest(df, 0.07, sig_at(df, [1, 4]), fee=0)
    assert len(r["trades"]) == 2 and all(t.closed for t in r["trades"])


def test_no_lookahead_signal_on_last_day():
    rows = flat(100, 4)
    df = make_df(rows)
    r = bt.run_backtest(df, 0.07, sig_at(df, [3]), fee=0)
    assert r["trades"] == []                     # 마지막 날 신호는 다음 날이 없으므로 매수 불가


@pytest.mark.skipif(not os.path.exists(os.path.join(bt.DATA_DIR, "AMZN.csv")), reason="실데이터 없음")
def test_real_data_loads():
    df = bt.load_prices("AMZN")
    assert len(df) > 1000
    assert (df["High"] >= df["Low"]).all()
    assert df["Date"].is_monotonic_increasing
