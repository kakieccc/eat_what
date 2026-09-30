from importlib import import_module


def register_models() -> None:
    """Load every module's tables into the shared SQLAlchemy metadata."""
    for module in ("auth", "decision", "places", "preferences", "choice", "task"):
        import_module(f"app.modules.{module}.models")
