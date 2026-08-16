from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from app import models

class TriggerHandler(ABC):
    @abstractmethod
    def check(self, trigger: models.Trigger, user: models.User, db: Session) -> dict:
        """Run this trigger's check, notify if it fired, log a TriggerEvent, 
        return the same summary dict shape the API already returns."""
        ...