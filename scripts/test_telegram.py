"""
scripts/test_telegram.py
--------------------------
A standalone script (not part of the API) to confirm your Telegram bot can
send YOU a message. Run this once during setup to prove the bot works
before anything else in the project relies on it.

How to get the two values this script needs:
  1. TELEGRAM_BOT_TOKEN -- open Telegram, search for @BotFather, send
     /newbot, and follow the prompts. You'll get a token that looks like:
     123456789:ABCdefGhIJKlmNoPQRstuVWXyz

  2. TELEGRAM_CHAT_ID -- send any message to your new bot (so it knows who
     you are), then visit this URL in your browser (replace <YOUR_TOKEN>):
     https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
     Look for "chat":{"id": ...} in the response -- that number is your
     chat ID.

Put both values in your .env file, then run:
    python scripts/test_telegram.py
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_test_message() -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in your .env file.")
        print("See the instructions at the top of this file to get both values.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "PingMe test message: if you see this, your bot is working!",
    }

    response = requests.post(url, json=payload, timeout=10)

    if response.status_code == 200:
        print("Success! Check your Telegram -- the message should have arrived.")
    else:
        print(f"Something went wrong. Telegram responded with: {response.text}")


if __name__ == "__main__":
    send_test_message()


# ==============================================================================
# ROLE OF THIS FILE:
# A one-off manual test to prove your Telegram bot token + chat ID work
# BEFORE you build any real feature on top of them. It's not part of the
# FastAPI app -- you just run it directly from your terminal.
# ==============================================================================
