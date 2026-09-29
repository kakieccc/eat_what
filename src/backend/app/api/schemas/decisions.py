from app.api.schemas.common import ApiModel
from app.domain.decision.models import DecisionRequest


class DecisionCreateRequest(DecisionRequest):
    pass


class DecisionRunUpdateRequest(ApiModel):
    accept_changes: bool | None = None
