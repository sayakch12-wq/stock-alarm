import os
import json
import requests
import anthropic
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

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
KAKAO_ACCESS_TOKEN = os.environ["KAKAO_ACCESS_TOKEN"]

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
            "current_price": current_price,
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

def analyze_with_claude(portfolio_data, vix):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    lines = []
    for item in portfolio_data:
        if "error" not in item["stock"]:
            s = item["stock"]
            p = item["portfolio"]
            lines.append(
                f"- {p['name']}({p['ticker']}): RSI={s['rsi']:.1f}, "
                f"변동={s['change_pct']:.2f}%, "
                f"MA20대비={'위' if s['current_price'] > s['ma20'] else '아래'}, "
                f"매입단가(원)={p['avg_price_krw']:,}"
            )
    prompt = f"""날짜: {datetime.now().strftime('%Y-%m-%d')}
VIX: {vix:.1f} {'(공포-매수기회)' if vix > 25 else '(보통)' if vix > 15 else '(탐욕-주의)'}

포트폴리오:
{chr(10).join(lines)}

전략: RSI<30=매수, RSI>70=매도, 매입가+7~10%=매도, 매입가-7~10%=물타기
각 종목 매수/매도/홀드 + 이유를 한국어 이모지로 간결하게. 마지막에 오늘의 핵심 1~2가지 요약."""

    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

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
    print(f"VIX: {vix}")
    portfolio_data = []
    for p in PORTFOLIO:
        sd = get_stock_data(p["ticker"])
        portfolio_data.append({"stock": sd, "portfolio": p})
        print(f"{p['ticker']}: {sd.get('current_price', 'ERR')}")
    analysis = analyze_with_claude(portfolio_data, vix)
    today = datetime.now().strftime("%m/%d")
    message = f"📊 [{today}] 주식 알람\n\n{analysis}\n\n⏰ Claude 자동분석"
    status = send_kakao(message)
    print(f"카카오톡: {status}")

if __name__ == "__main__":
    main()
