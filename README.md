# stock-alarm

## 백테스트 (backtest/)

매매 원칙(급락 후 매수 → +7~10% 매도, -7~10% 추가매수)을 과거 5년 주가로 검증합니다.

- 결과 보기: `backtest/report.html`
- 자동 실행: GitHub **Actions → Backtest → Run workflow** (매월 1일 자동 실행도 됨). 끝나면 실행 화면 아래 `backtest-report`를 내려받아 열면 됩니다.
- 종목 바꾸기: Run workflow 창의 tickers 칸에 `MA,MSFT,NVDA`처럼 입력
- 자세한 설명: `backtest/README_KO.md`
