import os
import json
import requests
from datetime import datetime

# Portfolio - 기성님 미래에셋 포트폴리오
PORTFOLIO = [
    {"ticker": "SPY",  "name": "TIGER US S&P500", "shares": 19, "avg_price_krw": 26030},
    {"ticker": "MA",   "name": "Mastercard",       "shares": 1,  "avg_price_krw": 751054},
    {"ticker": "MSFT", "name": "Microsoft",        "shares": 1,  "avg_price_krw": 591073},
    {"ticker": "NVDA", "name": "NVIDIA",            "shares": 1,  "avg_price_krw": 294246},
    {"ticker": "ORCL", "name": "Oracle",            "shares": 3,  "avg_price_krw": 253250},
    {"ticker": "TSLA", "name": "Tesla",             "shares": 7,  "avg_price_krw": 565913},
    {"ticker": "UNH",  "name": "UnitedHealth",      "shares": 1,  "avg_price_krw": 518451},
]

KAKAO_ACCESS_TOKEN = os.environ["KAKAO_ACCESS_TOKEN"]
USD_TO_KRW = 1380  # 환율 (고정값, 필요시 업데이트)

def get_stock_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=3mo"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]

        current_price = meta.get("regularMarketPrice", closes[-1])
        prev_close = meta.get("previousClose", closes[-2] if len(closes) > 1 else current_price)
        change_pct = ((current_price - prev_close) / prev_close) * 100

        # RSI(14) 계산
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, 15):
                diff = closes[-i] - closes[-i-1]
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
            "52w_high": meta.get("fiftyTwoWeekHigh", 0),
            "52w_low":  meta.get("fiftyTwoWeekLow", 0),
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
    except:
        return 20.0

def rule_based_signal(stock, port):
    """Claude API 없이 규칙 기반으로 매수/매도/홀드 판단"""
    rsi = stock["rsi"]
    current_usd = stock["current_price_usd"]
    current_krw = current_usd * USD_TO_KRW
    avg_krw = port["avg_price_krw"]
    change_pct = stock["change_pct"]
    ma20 = stock["ma20"]
    ma50 = stock["ma50"]

    # 수익률 계산
    profit_pct = ((current_krw - avg_krw) / avg_krw) * 100

    signals = []
    score = 0  # 양수=매수, 음수=매도

    # 1. RSI 판단
    if rsi <= 30:
        signals.append(f"RSI {rsi:.0f} 과매도")
        score += 2
    elif rsi <= 40:
        signals.append(f"RSI {rsi:.0f} 저평가")
        score += 1
    elif rsi >= 70:
        signals.append(f"RSI {rsi:.0f} 과매수")
        score -= 2
    elif rsi >= 60:
        signals.append(f"RSI {rsi:.0f} 고평가")
        score -= 1

    # 2. 이동평균 추세
    if current_usd > ma20 > ma50:
        signals.append("MA 상승추세")
        score += 1
    elif current_usd < ma20 < ma50:
        signals.append("MA 하락추세")
        score -= 1

    # 3. 매입단가 기준 ±7~10% 판단 (핵심 전략)
    if profit_pct >= 8:
        signals.append(f"수익 +{profit_pct:.1f}% → 매도 고려")
        score -= 3
    elif profit_pct >= 7:
        signals.append(f"수익 +{profit_pct:.1f}% → 매도 접근")
        score -= 2
    elif profit_pct <= -8:
        signals.append(f"손실 {profit_pct:.1f}% → 물타기 기회")
        score += 3
    elif profit_pct <= -7:
        signals.append(f"손실 {profit_pct:.1f}% → 물타기 고려")
        score += 2

    # 4. 최종 판단
    if score >= 2:
        action = "🟢 매수"
    elif score <= -2:
        action = "🔴 매도"
    else:
        action = "🟡 홀드"

    sell_target = avg_krw * 1.08
    buy_target = avg_krw * 0.92

    return {
        "action": action,
        "score": score,
        "profit_pct": profit_pct,
        "current_krw": current_krw,
        "sell_target": sell_target,
        "buy_target": buy_target,
        "signals": signals,
    }

def build_message(portfolio_data, vix):
    today = datetime.now().strftime("%m/%d")

    if vix >= 30:
        vix_comment = f"😱 VIX {vix:.1f} 극도의 공포 → 적극 매수 기회"
    elif vix >= 25:
        vix_comment = f"😨 VIX {vix:.1f} 공포 → 매수 기회"
    elif vix >= 20:
        vix_comment = f"😰 VIX {vix:.1f} 불안 → 주의"
    else:
        vix_comment = f"😌 VIX {vix:.1f} 안정"

    lines = [f"📊 [{today}] 주식 알람", f"", vix_comment, ""]

    buy_list = []
    sell_list = []
    hold_list = []

    for item in portfolio_data:
        s = item["stock"]
        p = item["portfolio"]
        r = item["result"]
        if "error" in s:
            lines.append(f"⚠️ {p['name']}: 데이터 오류")
            continue

        emoji_change = "▲" if s["change_pct"] > 0 else "▼"
        line = (
            f"{r['action']} {p['name']}
"
            f"  현재 {r['current_krw']:,.0f}원 ({emoji_change}{abs(s['change_pct']):.1f}%)
"
            f"  수익률 {r['profit_pct']:+.1f}% | RSI {s['rsi']:.0f}
"
            f"  매도목표 {r['sell_target']:,.0f}원 | 물타기 {r['buy_target']:,.0f}원"
        )
        if "매수" in r["action"]:
            buy_list.append(line)
        elif "매도" in r["action"]:
            sell_list.append(line)
        else:
            hold_list.append(line)

    if sell_list:
        lines.append("━━ 🔴 매도 신호 ━━")
        lines.extend(sell_list)
        lines.append("")
    if buy_list:
        lines.append("━━ 🟢 매수 신호 ━━")
        lines.extend(buy_list)
        lines.append("")
    if hold_list:
        lines.append("━━ 🟡 홀드 ━━")
        lines.extend(hold_list)
        lines.append("")

    lines.append("⏰ 자동 분석 (규칙 기반)")
    return "\n".join(lines)

def send_kakao(message):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": f"Bearer {KAKAO_ACCESS_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    template = {
        "object_type": "text",
        "text": message,
        "link": {"web_url": "https://finance.yahoo.com", "mobile_web_url": "https://finance.yahoo.com"}
    }
    r = requests.post(url, headers=headers, data={"template_object": json.dumps(template)})
    return r.status_code

def main():
    print(f"[{datetime.now()}] 분석 시작")
    vix = get_vix()
    print(f"VIX: {vix:.1f}")

    portfolio_data = []
    for p in PORTFOLIO:
        sd = get_stock_data(p["ticker"])
        result = rule_based_signal(sd, p) if "error" not in sd else {}
        portfolio_data.append({"stock": sd, "portfolio": p, "result": result})
        print(f"{p['ticker']}: {sd.get('current_price_usd', 'ERR')} | {result.get('action', 'ERR')}")

    message = build_message(portfolio_data, vix)
    print("\n--- 메시지 미리보기 ---")
    print(message)

    status = send_kakao(message)
    print(f"\n카카오톡 발송: {status}")
    if status == 200:
        print("✅ 성공!")
    else:
        print(f"❌ 실패 (코드: {status})")

if __name__ == "__main__":
    main()
