"""Send a demo BUY signal to your Telegram bot to verify the token + chat id work.

Mirrors apps/api/src/telegram/telegram.service.ts `sendSignalAlert` (same HTML
layout) so what lands in your chat looks exactly like a real alert — just flagged
as a test. Use it after rotating TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.

Reads creds from the environment, falling back to the repo's .env files
(apps/api/.env then the repo-root .env). No external packages required.

Run:
    python3 scripts/test_telegram_signal.py
    python3 scripts/test_telegram_signal.py --symbol TCS        # different stock
    TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python3 scripts/test_telegram_signal.py
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo  # py3.9+
    _IST = ZoneInfo("Asia/Kolkata")
except Exception:  # pragma: no cover
    _IST = None

REPO_ROOT = Path(__file__).resolve().parents[1]
# Where TELEGRAM_* typically live (NestJS API reads them). First match wins per key.
ENV_FILES = [REPO_ROOT / "apps" / "api" / ".env", REPO_ROOT / ".env"]

HOLD_DURATION_LABELS = {
    "INTRADAY": "⏱ Intraday (exit by 15:15)",
    "SHORT_SWING": "📅 Short Swing (2-5 days)",
    "MID_SWING": "📆 Mid Swing (1-4 weeks)",
    "LONG_POSITIONAL": "🗓 Long Positional (1-6 months)",
}


def _load_env_files(keys):
    """Return {key: value} for `keys`, preferring the real environment, then the
    .env files in order. Minimal KEY=VALUE parser (handles quotes and comments)."""
    found = {k: os.getenv(k) for k in keys if os.getenv(k)}
    for path in ENV_FILES:
        if all(k in found for k in keys) or not path.exists():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key in keys and key not in found:
                val = val.strip().strip('"').strip("'")
                if val:
                    found[key] = val
    return found


def _now_ist():
    now = datetime.now(_IST) if _IST else datetime.now()
    # Roughly matches the app's en-IN toLocaleString output.
    return now.strftime("%d/%m/%Y, %I:%M:%S %p")


def build_message(signal):
    is_buy = signal["signalType"] == "BUY"
    emoji = "🟢" if is_buy else "🔴"
    risk = signal["entryPrice"] - signal["stopLoss"]
    rr = f"{abs((signal['target'] - signal['entryPrice']) / risk):.1f}" if risk else "N/A"
    hold = HOLD_DURATION_LABELS.get(signal.get("holdDuration", ""), signal.get("holdDuration") or "Unknown")
    return "\n".join([
        f"🧪 <b>TEST</b> — {emoji} <b>{signal['signalType']} SIGNAL</b>",
        "",
        f"📈 <b>Stock:</b> {signal.get('symbol', 'Unknown')}",
        f"🎯 <b>Strategy:</b> {signal['strategyName']}",
        f"{hold}",
        "",
        f"💰 <b>Entry:</b> ₹{signal['entryPrice']:.2f}",
        f"🛑 <b>Stop Loss:</b> ₹{signal['stopLoss']:.2f}",
        f"✅ <b>Target:</b> ₹{signal['target']:.2f}",
        f"📊 <b>Risk:Reward:</b> 1:{rr}",
        "",
        f"⏰ {_now_ist()}",
        "",
        "<i>This is a connectivity test, not a real trade.</i>",
    ])


def send(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def main():
    parser = argparse.ArgumentParser(description="Send a demo BUY signal to your Telegram bot.")
    parser.add_argument("--symbol", default="RELIANCE", help="Stock symbol shown in the demo signal")
    args = parser.parse_args()

    creds = _load_env_files(["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
    bot_token = creds.get("TELEGRAM_BOT_TOKEN")
    chat_id = creds.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not creds.get(k)]
        print(f"❌ Missing {', '.join(missing)} — set them in the environment or apps/api/.env")
        sys.exit(1)

    print(f"→ Bot token: …{bot_token[-6:]}   Chat id: {chat_id}")

    signal = {
        "signalType": "BUY",
        "symbol": args.symbol.upper(),
        "strategyName": "Connectivity Test",
        "entryPrice": 1000.0,
        "stopLoss": 980.0,
        "target": 1060.0,
        "holdDuration": "SHORT_SWING",
    }

    try:
        result = send(bot_token, chat_id, build_message(signal))
        print(f"✅ Sent! Telegram message_id={result.get('result', {}).get('message_id')} — check your chat.")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"❌ Telegram rejected the request (HTTP {e.code}): {body}")
        print("   401 = bad bot token · 400 'chat not found' = wrong chat id (or bot not started/added to the chat).")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to reach Telegram: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
