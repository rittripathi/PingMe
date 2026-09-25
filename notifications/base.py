from abc import ABC, abstractmethod


class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, message: str):
        raise NotImplementedError
