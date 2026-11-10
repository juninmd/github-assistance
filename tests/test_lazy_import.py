import subprocess
import sys

import pytest

from src.utils.lazy_import import LazyModule


def test_lazy_module_defers_import_until_attribute_access():
    proxy = LazyModule("json")
    assert proxy.dumps({"a": 1}) == '{"a": 1}'


def test_lazy_module_reports_install_hint():
    proxy = LazyModule("definitely_missing_sdk.sub", install_hint="missing-sdk")
    with pytest.raises(ModuleNotFoundError, match="pip install missing-sdk"):
        _ = proxy.anything


@pytest.mark.parametrize("module", ["src.ai", "src.agents.pr_assistant.agent", "src.insight.cli"])
def test_heavy_ai_sdks_are_not_imported_eagerly(module):
    code = (
        f"import sys, {module}; "
        "heavy = {'litellm', 'google.genai', 'ollama'} & set(sys.modules); "
        "assert not heavy, heavy"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603 - fixed argv
