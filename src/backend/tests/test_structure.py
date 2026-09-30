import ast
import importlib
import pkgutil
from pathlib import Path

import app.modules
from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.registry import register_models


def test_modules_import_and_register_all_tables():
    for module in pkgutil.walk_packages(app.modules.__path__, app.modules.__name__ + "."):
        importlib.import_module(module.name)
    register_models()
    assert len(Base.metadata.tables) == 15
    assert {"users", "decision_runs", "tasks", "place_candidates", "place_choices"} <= set(
        Base.metadata.tables
    )
    # Resolve every ForeignKey after all module-owned tables have been registered.
    for table in Base.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            assert foreign_key.column.table.name in Base.metadata.tables


def test_services_rules_workflow_and_routers_do_not_import_orm():
    root = Path(app.modules.__path__[0])
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if path.stem not in {"router", "service"} and not {"service", "rules", "workflow"} & set(
            relative.parts
        ):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            modules = []
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            for module in modules:
                assert not module.startswith("sqlalchemy"), relative
                assert not (module.startswith("app.modules.") and module.endswith(".models")), (
                    relative
                )
                if path.stem == "router":
                    assert ".repository" not in module and not module.endswith(".ports"), relative
