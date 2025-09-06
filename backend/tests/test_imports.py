import os, sys
HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import importlib
import pytest

# Modules we expect to import without side effects
MODULES = [
    "app.common.auth",
    "tenants",
    "approvals",
    "audit",
    "app.api",
    "app.api.routes",
    "native_registry.appy",
    "tribal_core",
]

@pytest.mark.parametrize("name", MODULES)
def test_imports(name):
    mod = importlib.import_module(name)
    assert mod is not None
