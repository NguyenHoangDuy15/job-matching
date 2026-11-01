import importlib

import pytest


@pytest.mark.parametrize("module", ["api", "common", "ranking", "skillkit"])
def test_module_imports(module):
    importlib.import_module(module)
