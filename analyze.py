import os
import json
import requests
from datetime import datetime

PORTFOLIO = [
    {"ticker": "SPY",  "name": "TIGER-SP500", "shares": 19, "avg_krw": 26030},
    {"ticker": "MA",   "name": "Mastercard",  "shares": 1,  "avg_krw": 751054},
    {"ticker": "MSFT", "name": "Microsoft",   "shares": 1,  "avg_krw": 591073},
    {"ticker": "NVDA", "name": "NVIDIA",      "shares": 1,  "avg_krw": 294246},
    {"ticker": "ORCL", "name": "Oracle",      "shares": 3,  "avg_krw": 253250},
    {"ticker": "TSLA", "name": "Tesla",       "shares": 7,  "avg_krw": 565913},
    {"ticker": "UNH",  "name": "UnitedHealth","shares": 1,  "avg_krw": 518451},
]

KAKAO_ACCESS_TOKEN = os.environ["KAKAO_ACCESS_TOKEN"]
USD_KRW = 1380


def get_stock(ticker):
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker + "?interval=1d&range=3mo"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        d = r.json()["chart"]["result"][0]
        meta = d["meta"]
        closes = [c for c in d["indicators"]["quote"][0]["close"] if c]
        price = meta.get("regularMarketPrice", closes[-1])
        prev = meta.get("previousClose", closes[-2] if len(closes) > 1 else price)
        chg = (price - prev) / prev * 100
        if len(closes) >= 15:
            g = [max(closes[-i]-closes[-i-1],0) for i in range(1,15)]
            l = [max(closes[-i-1]-closes[-i],0) for i in range(1,15)]
            ag, al = sum(g)/14, sum(l)/14
            rsi = 100 if al==0 else 100-(100/(1+ag/al))
        else:
            rsi = 50
        ma20 = sum(closes[-20:])/min(20,len(closes))
        ma50 = sum(closes[-50:])/min(50,len(closes))
        return {"ok":True,"price":price,"chg":chg,"rsi":rsi,"ma20":ma20,"ma50":ma50}
    except Exception as e:
        return {"ok":False,"err":str(e)}


def get_vix():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:
        return 20.0


def signal(s, p):
    rsi = s["rsi"]
    price_krw = s["price"] * USD_KRW
    avg = p["avg_krw"]
    profit = (price_krw - avg) / avg * 100
    score = 0
    if rsi <= 30: score += 2
    elif rsi <= 40: score += 1
    elif rsi >= 70: score -= 2
    elif rsi >= 60: score -= 1
    if s["price"] > s["ma20"] > s["ma50"]: score += 1
    elif s["price"] < s["ma20"] < s["ma50"]: score -= 1
    if profit >= 8: score -= 3
    elif profit >= 7: score -= 2
    elif profit <= -8: score += 3
    elif profit <= -7: score += 2
    if score >= 2: act = "BUY"
    elif score <= -2: act = "SELL"
    else: act = "HOLD"
    return {"act":act,"profit":profit,"price_krw":price_krw,"sell":avg*1.08,"buy":avg*0.92}


def send_kakao(msg):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    tmpl = {"object_type":"text","text":msg,"link":{"web_url":"https://finance.yahoo.com","mobile_web_url":"https://finance.yahoo.com"}}
    r = requests.post(url,
        headers={"Authorization":"Bearer "+KAKAO_ACCESS_TOKEN,"Content-Type":"application/x-www-form-urlencoded"},
        data={"template_object":json.dumps(tmpl)})
    return r.status_code


def main():
    print("start: " + str(datetime.now()))
    vix = get_vix()
    print("VIX: " + str(vix))
    today = datetime.now().strftime("%m/%d")
    lines = ["[" + today + "] Stock Alarm", ""]
    if vix >= 30: lines.append("VIX " + str(round(vix,1)) + " EXTREME FEAR - BUY OPPORTUNITY")
    elif vix >= 25: lines.append("VIX " + str(round(vix,1)) + " FEAR - BUY OPPORTUNITY")
    elif vix >= 20: lines.append("VIX " + str(round(vix,1)) + " ANXIETY")
    else: lines.append("VIX " + str(round(vix,1)) + " CALM")
    lines.append("")
    sell_l, buy_l, hold_l = [], [], []
    for p in PORTFOLIO:
        s = get_stock(p["ticker"])
        if not s["ok"]:
            lines.append("ERR: " + p["name"])
            continue
        sg = signal(s, p)
        arrow = "+" if s["chg"] >= 0 else ""
        entry = (
            "[" + sg["act"] + "] " + p["name"] + "\n" +
            "  " + "{:,.0f}".format(sg["price_krw"]) + "KRW (" + arrow + str(round(s["chg"],1)) + "%)\n" +
            "  profit:" + str(round(sg["profit"],1)) + "% RSI:" + str(round(s["rsi"],0)) + "\n" +
            "  sell>" + "{:,.0f}".format(sg["sell"]) + " buy<" + "{:,.0f}".format(sg["buy"])
        )
        print(p["ticker"] + " -> " + sg["act"])
        if sg["act"] == "BUY": buy_l.append(entry)
        elif sg["act"] == "SELL": sell_l.append(entry)
        else: hold_l.append(entry)
    if sell_l: lines += ["-- SELL --"] + sell_l + [""]
    if buy_l: lines += ["-- BUY --"] + buy_l + [""]
    if hold_l: lines += ["-- HOLD --"] + hold_l + [""]
    lines.append("auto-analysis")
    msg = "\n".join(lines)
    print(msg)
    code = send_kakao(msg)
    print("kakao: " + str(code))


if __name__ == "__main__":
    main()
