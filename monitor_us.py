# -*- coding: utf-8 -*-
"""monitor_us.py"""

import os
import time
import sys
import requests
import yfinance as yf
from datetime import datetime, timedelta
import pytz

# ✅ 텔레그램 알림 함수 (보안 적용)
def send_telegram_alert(message):
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    response = requests.post(url, data=payload)
    print(f"[텔레그램 응답] {response.status_code} / {response.text}")

# ✅ 뉴욕 시간 반환 (서머타임 자동 반영)
def get_ny_time():
    ny = pytz.timezone("America/New_York")
    return datetime.now(ny)

# ✅ 감시 대상 (미국 종목)
TICKERS = {
    "SOXL": "SOXL",
    "퀄컴":"QCOM",
    "DGRO": "DGRO",
    "구글": "GOOG",
    "마이크론": "MU"

}

INTERVAL_SECONDS = 60  # 1분 간격 감시

# ✅ 일일 등락률 표준편차 계산 (최대 5년치)
def get_return_std(ticker):
    df = yf.download(ticker, period="1250d", interval="1d")
    df['Return'] = df['Close'].pct_change()
    df = df.dropna()
    return float(df['Return'].std())

# ✅ 전일 종가 / 현재가
def get_prev_close_and_current_price(ticker):
    daily = yf.download(ticker, period="2d", interval="1d")
    if len(daily) < 2:
        return None, None
    prev_close = daily['Close'].iloc[-2].item()

    intraday = yf.download(ticker, period="1d", interval="1m")
    if intraday.empty:
        return None, None
    current_price = intraday['Close'].iloc[-1].item()

    return prev_close, current_price

# ✅ 감시 루프
def run_monitor():
    ny_now = get_ny_time()
    if ny_now.weekday() >= 5:  # 주말이면 종료
        send_telegram_alert("🛑 주말입니다. 감시 종료합니다.")
        sys.exit()

    send_telegram_alert("🚨 미국 주식 감시를 시작합니다!")

    thresholds = {}
    notified = {code: False for code in TICKERS}

    # ✅ 시작 시 종목별 매수 기준 알림 전송
    startup_messages = []

    for code, ticker in TICKERS.items():
        std = get_return_std(ticker)
        threshold = 2 * std
        thresholds[code] = threshold

        daily = yf.download(ticker, period="2d", interval="1d")
        if len(daily) < 2:
            startup_messages.append(f"[{code}] ❌ 전일 종가 불러오기 실패")
            continue

        prev_close = daily['Close'].iloc[-2].item()
        buy_price = prev_close * (1 - threshold)

        msg = (
            f"📊 [{code}] 매수 기준 안내\n"
            f"- 전일 종가: {prev_close:.2f}\n"
            f"- 매수 기준 등락폭: {threshold:.2%}\n"
            f"- 매수 기준가: {buy_price:.2f}"
        )
        startup_messages.append(msg)
        print(msg)

    for msg in startup_messages:
        send_telegram_alert(msg)

    print("✅ 초기 알림 전송 완료")

    # ✅ 감시 루프 시작
    while True:
        ny_now = get_ny_time()
        hour = ny_now.hour
        minute = ny_now.minute

        # ✅ 미국 시장 감시 시간 (09:30 ~ 16:00 NY 기준)
        if (hour < 9 or (hour == 9 and minute < 30)) or hour >= 16:
            send_telegram_alert("⏹️ 미국 시장 개장 시간 외입니다. 감시 종료합니다.")
            sys.exit()

        for code, ticker in TICKERS.items():
            if notified[code]:
                print(f"[{code}] ✅ 감시 완료 → 제외")
                continue

            try:
                prev_close, current_price = get_prev_close_and_current_price(ticker)
                if prev_close is None or current_price is None:
                    print(f"[{code}] 가격 수신 실패")
                    continue

                change_pct = abs((current_price - prev_close) / prev_close)
                diff = (current_price - prev_close) / prev_close
                threshold = thresholds[code]

                print(f"[{code}] 현재 등락률 변화: {change_pct:.2%} / 기준: {threshold:.2%}")

                if change_pct > threshold:
                    if prev_close > current_price:
                        msg = (
                            f"🚨 {code} 매수 타이밍\n"
                            f"전일종가: {prev_close:.2f}\n"
                            f"매수 기준가: {prev_close * (1 - threshold):.2f}\n"
                            f"변화율: {diff:.2%} < -{threshold:.2%}\n"
                            f"현재가: {current_price:.2f} (전일 대비: {current_price - prev_close:.2})"
                        )
                    else:
                        msg = (
                            f"🚨 {code} 매도 타이밍\n"
                            f"전일종가: {prev_close:.2f}\n"
                            f"매도 기준가: {prev_close * (1 + threshold):.2f}\n"
                            f"변화율: {diff:.2%} > +{threshold:.2%}\n"
                            f"현재가: {current_price:.2f} (전일 대비: +{current_price - prev_close:.2f})"
                        )
                    send_telegram_alert(msg)
                    notified[code] = True

                    if all(notified.values()):
                        send_telegram_alert("✅ 모든 감시 종목 알림 완료. 프로그램 종료.")
                        sys.exit()
                else:
                    print(f"[{code}] 변화율 정상 범위")

            except Exception as e:
                print(f"[{code}] 오류: {e}")
                send_telegram_alert(f"❌ {code} 오류: {e}")

        time.sleep(INTERVAL_SECONDS)

# ✅ 실행
try:
    run_monitor()
except SystemExit:
    pass
