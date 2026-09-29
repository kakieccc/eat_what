from datetime import datetime

from app.domain.base import Model


class UserProfile(Model):
    id: str
    username: str
    display_name: str
    created_at: datetime
