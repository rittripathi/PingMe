from notifications.telegram import TelegramProvider

PROVIDERS = {
    "telegram": TelegramProvider(),
}


def get_provider(channel: str):
    try:
        return PROVIDERS[channel]
    except KeyError:
        raise ValueError(f"Unknown notification channel: {channel}")
