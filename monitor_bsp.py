"""
Monitor BSP (Bending Spoons) su Nasdaq e invia notifiche Telegram
quando vengono superate determinate soglie.

Configurazione soglie qui sotto - modificabili liberamente.
"""

import json
import os
import sys
from pathlib import Path

import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# CONFIGURAZIONE - modifica questi valori come preferisci
# ---------------------------------------------------------------------------
TICKER = "BSP"
IPO_PRICE = 29.0

DAILY_PCT_THRESHOLD = 5.0      # alert se variazione giornaliera >= 5% (in valore assoluto)
LOW_PRICE_THRESHOLD = 20.30    # alert se il prezzo scende sotto questo valore (29 - 30%)
HIGH_PRICE_THRESHOLD = 35.0    # alert se il prezzo supera questo valore
IPO_DEVIATION_PCT = 15.0       # alert se il prezzo si allontana di questa % dal prezzo IPO

STATE_FILE = Path(__file__).parent / "state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_message(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ATTENZIONE: TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID non impostati, salto invio.")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    resp = requests.post(url, data=payload, timeout=15)
    if resp.status_code != 200:
        print(f"Errore invio Telegram: {resp.status_code} {resp.text}", file=sys.stderr)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "alerted_low_price": False,
        "alerted_high_price": False,
        "alerted_ipo_deviation": False,
        "last_daily_pct_alert_date": None,
    }


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_price_data():
    ticker = yf.Ticker(TICKER)
    hist = ticker.history(period="5d", interval="1d")
    if hist.empty:
        return None

    last_close = hist["Close"].iloc[-1]

    # variazione giornaliera: confronto con la chiusura precedente se disponibile
    if len(hist) >= 2:
        prev_close = hist["Close"].iloc[-2]
        daily_pct = (last_close - prev_close) / prev_close * 100
    else:
        daily_pct = None

    return {"price": float(last_close), "daily_pct": daily_pct}


def main():
    data = get_price_data()

    if data is None:
        msg = (
            f"⚠️ Non riesco ancora a recuperare i dati per {TICKER}. "
            f"Se il titolo è appena quotato, Yahoo Finance potrebbe non averlo indicizzato: riprovo al prossimo giro."
        )
        print(msg)
        # Non manda notifica ogni volta per questo, solo log
        return

    price = data["price"]
    daily_pct = data["daily_pct"]
    ipo_deviation_pct = (price - IPO_PRICE) / IPO_PRICE * 100

    state = load_state()
    alerts = []

    # 1) Variazione % giornaliera
    if daily_pct is not None and abs(daily_pct) >= DAILY_PCT_THRESHOLD:
        alerts.append(
            f"📊 *{TICKER}*: variazione giornaliera di *{daily_pct:+.2f}%* "
            f"(soglia: ±{DAILY_PCT_THRESHOLD}%). Prezzo attuale: ${price:.2f}"
        )

    # 2) Prezzo sotto soglia bassa
    if price <= LOW_PRICE_THRESHOLD:
        if not state["alerted_low_price"]:
            alerts.append(
                f"🔴 *{TICKER}* è sceso a ${price:.2f}, sotto la soglia di ${LOW_PRICE_THRESHOLD:.2f} "
                f"(-30% dal prezzo IPO di ${IPO_PRICE:.2f})."
            )
            state["alerted_low_price"] = True
    else:
        state["alerted_low_price"] = False  # reset se torna sopra

    # 3) Prezzo sopra soglia alta
    if price >= HIGH_PRICE_THRESHOLD:
        if not state["alerted_high_price"]:
            alerts.append(
                f"🟢 *{TICKER}* ha superato ${price:.2f}, sopra la soglia di ${HIGH_PRICE_THRESHOLD:.2f}."
            )
            state["alerted_high_price"] = True
    else:
        state["alerted_high_price"] = False

    # 4) Deviazione dal prezzo IPO
    if abs(ipo_deviation_pct) >= IPO_DEVIATION_PCT:
        if not state["alerted_ipo_deviation"]:
            direction = "sopra" if ipo_deviation_pct > 0 else "sotto"
            alerts.append(
                f"📈 *{TICKER}* è ora {ipo_deviation_pct:+.2f}% {direction} il prezzo IPO "
                f"(${IPO_PRICE:.2f} → ${price:.2f})."
            )
            state["alerted_ipo_deviation"] = True
    else:
        state["alerted_ipo_deviation"] = False

    if alerts:
        message = "\n\n".join(alerts)
        send_telegram_message(message)
        print("Notifica inviata:\n", message)
    else:
        print(f"Nessun alert. Prezzo attuale {TICKER}: ${price:.2f} (daily: {daily_pct})")

    save_state(state)


if __name__ == "__main__":
    main()
