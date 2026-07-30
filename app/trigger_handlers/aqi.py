# app/trigger_handlers/aqi.py
from sqlalchemy.orm import Session

from app import aqi_service, models, notifier, price_service
from app.trigger_handlers.base import TriggerHandler


class AQIHandler(TriggerHandler):
    def check(self, trigger: models.Trigger, user: models.User, db: Session) -> dict:
        # trigger.asset holds a "latitude,longitude" string for this type
        current_aqi = aqi_service.get_current_aqi(trigger.asset)
        fired = price_service.condition_met(current_aqi, trigger.condition, trigger.target_value)

        if fired:
            message = (
                f"PingMe alert: AQI near {trigger.asset} is now {current_aqi} "
                f"(condition: {trigger.condition} {trigger.target_value})"
            )
            notifier.send_telegram_message(user.telegram_chat_id, message)

        event = models.TriggerEvent(trigger_id=trigger.id, checked_value=current_aqi, fired=fired)
        db.add(event)
        db.commit()

        return {
            "coordinates": trigger.asset,
            "current_aqi": current_aqi,
            "condition": f"{trigger.condition} {trigger.target_value}",
            "fired": fired,
        }


# ==============================================================================
# ROLE OF THIS FILE:
# Implements TriggerHandler for AQI triggers -- fetch, check condition,
# notify, log. Same steps as CryptoPriceHandler, different data source.
# Second proof point that the registry pattern holds up.
# ==============================================================================