from importlib import import_module

from app.infrastructure.database.base import Base

for module in (
    "app.modules.auth.models",
    "app.modules.decision.models",
    "app.modules.preferences.models",
    "app.modules.choice.models",
    "app.modules.task.models",
    "app.infrastructure.amap.models",
):
    import_module(module)

metadata = Base.metadata
