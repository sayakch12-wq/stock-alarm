import os
import json
import requests
from datetime import datetime

PORTFOLIO = [
    {"ticker": "SPY",  "name": "TIGER S&P500", "shares": 19, "avg_price_krw": 26030},
    {"ticker": "MA",   "name": "Mastercard",    "shares": 1,  "avg_price_krw": 751054},
    {"ticker": "MSFT", "name": "Microsoft",     "shares": 1,  "avg_price_krw": 591073},
    {"ticker": "NVDA", "name": "NVIDIA",         "shares": 1,  "avg_price_krw": 294246},
    {"ticker": "ORCL", "name": "Oracle",         "shares": 3,  "avg_price_krw": 253250},
    {"ticker": "TSLA", "name": "Tesla",          "shares": 7,  "avg_price_krw": 565913},
    {"ticker": "UNH",  "name": "UnitedHealth",   "shares": 1,  "avg_price_krw": 518451},
]

KAKAO_ACCESS_TOKEN = os.environ["KAKAO_ACCESS_TOKEN"]
USD_TO_KRW = 1380


def get_stock_data(ticker):
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker + "?interval=1d&range=3mo"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]

        current_price = meta.get("regularMarketPrice", closes[-1])
        prev_close = meta.get("previousClose", closes[-2] if len(closes) > 1 else current_price)
        change_pct = ((current_price - prev_close) / prev_close) * 100

        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, 15):
                diff = closes[-i] - closes[-i - 1]
                gains.append(diff if diff >= 0 else 0)
                losses.append(abs(diff) if diff < 0 else 0)
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            rsi = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
        else:
            rsi = 50

        ma20 = sum(closes[-20:]) / min(20, len(closes))
        ma50 = sum(closes[-50:]) / min(50, len(closes))

        return {
            "ticker": ticker,
            "current_price_usd": current_price,
            "change_pct": change_pct,
            "rsi": rsi,
            "ma20": ma20,
            "ma50": ma50,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def get_vix():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception:
        return 20.0


def rule_based_signal(stock, port):
    rsi = stock["rsi"]
    current_usd = stock["current_price_usd"]
    current_krw = current_usd * USD_TO_KRW
    avg_krw = port["avg_price_krw"]
    change_pct = stock["change_pct"]
    ma20 = stock["ma20"]
    ma50 = stock["ma50"]

    profit_pct = ((current_krw - avg_krw) / avg_krw) * 100
    signals = []
    score = 0

    if rsi <= 30:
        signals.append("RSI %.0f oversold" % rsi)
        score += 2
    elif rsi <= 40:
        signals.append("RSI %.0f low" % rsi)
        score += 1
    elif rsi >= 70:
        signals.append("RSI %.0f overbought" % rsi)
        score -= 2
    elif rsi >= 60:
        signals.append("RSI %.0f high" % rsi)
        score -= 1

    if current_usd > ma20 > ma50:
        signals.append("MA uptrend")
        score += 1
    elif current_usd < ma20 < ma50:
        signals.append("MA downtrend")
        score -= 1

    if profit_pct >= 8:
        signals.append("+%.1f%% sell target" % profit_pct)
        score -= 3
    elif profit_pct >= 7:
        signals.append("+%.1f%% near sell" % profit_pct)
        score -= 2
    elif profit_pct <= -8:
        signals.append("%.1f%% avg down" % profit_pct)
        score += 3
    elif profit_pct <= -7:
        signals.append("%.1f%% near avg down" % profit_pct)
        score += 2

    if score >= 2:
        action = "BUY"
        emoji = "매수"
    elif score <= -2:
        action = "SELL"
        emoji = "매도"
    else:
        action = "HOLD"
        emoji = "홀드"

    sell_target = avg_krw * 1.08
    buy_target = avg_krw * 0.92

    return {
        "action": action,
        "emoji": emoji,
        "score": score,
        "profit_pct": profit_pct,
        "current_krw": current_krw,
        "sell_target": sell_target,
        "buy_target": buy_target,
        "signals": signals,
        "change_pct": change_pct,
    }


def build_message(portfolio_data, vix):
    today = datetime.now().strftime("%m/%d")

    if vix >= 30:
        vix_line = "VIX %.1f - 극도의 공포 (매수 기회)" % vix
    elif vix >= 25:
        vix_line = "VIX %.1f - 공포 (매수 기회)" % vix
    elif vix >= 20:
        vix_line = "VIX %.1f - 불안 (주의)" % vix
    else:
        vix_line = "VIX %.1f - 안정" % vix

    lines = ["[%s] 주식 알람" % today, "", vix_line, ""]

    sell_list = []
    buy_list = []
    hold_list = []

    for item in portfolio_data:
        s = item["stock"]
        p = item["portfolio"]
        r = item["result"]
        if "error" in s:
            lines.append("[오류] " + p["name"])
            continue

        chg = r["change_pct"]
        arrow = "+" if chg >= 0 else ""
        line = (
            "[%s] %s
" % (r["emoji"], p["name"]) +
            "  현재 %s원 (%s%.1f%%)
" % ("{:,.0f}".format(r["current_krw"]), arrow, chg) +
            "  수익 %+.1f%% | RSI %.0f
" % (r["profit_pct"], s["rsi"]) +
            "  매도목표 %s원 | 물타기 %s원" % (
                "{:,.0f}".format(r["sell_target"]),
                "{:,.0f}".format(r["buy_target"])
            )
        )
        if r["action"] == "BUY":
            buy_list.append(line)
        elif r["action"] == "SELL":
            sell_list.append(line)
        else:
            hold_list.append(line)

    if sell_list:
        lines.append("--- 매도 신호 ---")
        lines.extend(sell_list)
        lines.append("")
    if buy_list:
        lines.append("--- 매수 신호 ---")
        lines.extend(buy_list)
        lines.append("")
    if hold_list:
        lines.append("--- 홀드 ---")
        lines.extend(hold_list)
        lines.append("")

    lines.append("자동 분석 (규칙 기반)")
    return "\n".join(lines)


def send_kakao(message):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": "Bearer " + KAKAO_ACCESS_TOKEN,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    template = {
        "object_type": "text",
        "text": message,
        "link": {
            "web_url": "https://finance.yahoo.com",
            "mobile_web_url": "https://finance.yahoo.com",
        },
    }
    r = requests.post(url, headers=headers, data={"template_object": json.dumps(template)})
    return r.status_code


def main():
    print("Analysis started: " + str(datetime.now()))
    vix = get_vix()
    print("VIX: %.1f" % vix)

    portfolio_data = []
    for p in PORTFOLIO:
        sd = get_stock_data(p["ticker"])
        result = rule_based_signal(sd, p) if "error" not in sd else {}
        portfolio_data.append({"stock": sd, "portfolio": p, "result": result})
        price = sd.get("current_price_usd", "ERR")
        action = result.get("emoji", "ERR")
        print("%s: %s -> %s" % (p["ticker"], price, action))

    message = build_message(portfolio_data, vix)
    print("\n--- message preview ---")
    print(message)

    status = send_kakao(message)
    print("\nKakaoTalk status: %d" % status)
    if status == 200:
        print("OK!")
    else:
        print("FAILED: %d" % status)


if __name__ == "__main__":
    main()
