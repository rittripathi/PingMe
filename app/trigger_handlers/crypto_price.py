from sqlalchemy.orm import Session

from app import models, notifier, price_service
from app.trigger_handlers.base import TriggerHandler


class CryptoPriceHandler(TriggerHandler):
    def check(self, trigger: models.Trigger, user: models.User, db: Session) -> dict:
        current_price = price_service.get_current_price(trigger.asset)
        fired = price_service.condition_met(current_price, trigger.condition, trigger.target_value)

        if fired:
            message = (
                f"PingMe alert: {trigger.asset} is now {current_price} "
                f"(condition: {trigger.condition} {trigger.target_value})"
            )
            notifier.send_telegram_message(user.telegram_chat_id, message)

        event = models.TriggerEvent(
            trigger_id=trigger.id,
            checked_value=current_price,
            fired=fired,
        )
        db.add(event)
        db.commit()

        return {
            "asset": trigger.asset,
            "current_price": current_price,
            "condition": f"{trigger.condition} {trigger.target_value}",
            "fired": fired,
        }