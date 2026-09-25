import httpx

from config import settings
from notifications.base import NotificationProvider


class TelegramProvider(NotificationProvider):
    async def send(self, message: str):
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            print(f"[Telegram disabled — would send] {message}")
            return

        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": settings.telegram_chat_id, "text": message}

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
