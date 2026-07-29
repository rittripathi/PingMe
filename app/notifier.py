"""
notifier.py
------------
Sends a Telegram message to a SPECIFIC chat_id, passed in as an argument.

Unlike scripts/test_telegram.py (which hardcodes one chat_id from .env),
this takes chat_id as a function argument -- so it works for whichever
user's trigger just fired, not just you.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def send_telegram_message(chat_id: str, text: str) -> bool:
    """
    Send `text` to the given Telegram chat_id.
    Returns True if Telegram accepted the message, False otherwise.

    Note: BOT_TOKEN stays in .env because it identifies the BOT itself --
    there's only one bot. chat_id is different per user, which is why it's
    a function argument here instead of another .env value.
    """
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set. Check your .env file.")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)

    return response.status_code == 200


# ==============================================================================
# ROLE OF THIS FILE:
# Sends a Telegram message to any chat_id passed in -- reusable for every
# user, not just you. scripts/test_telegram.py stays as a one-off manual
# test; this file is what the real app logic calls going forward.
# ==============================================================================