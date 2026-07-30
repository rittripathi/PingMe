# app/trigger_handlers/registry.py
from app.trigger_handlers.crypto_price import CryptoPriceHandler

HANDLER_REGISTRY = {
    "PRICE": CryptoPriceHandler(),
}


def get_handler(trigger_type: str):
    handler = HANDLER_REGISTRY.get(trigger_type)
    if handler is None:
        raise ValueError(f"No handler registered for trigger_type '{trigger_type}'")
    return handler