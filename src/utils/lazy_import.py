"""Deferred imports for heavy optional SDKs.

``litellm`` alone costs ~2.5s to import; agents that never call an LLM in a run
(for example ``pr-assistant`` with AI disabled) must not pay that on every
CronJob start. The proxy imports the real module on first attribute access and
stays patchable in tests (``patch("src.ai.litellm_client.litellm")``).
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


class LazyModule:
    """Import ``module_name`` on first attribute access."""

    def __init__(self, module_name: str, install_hint: str | None = None) -> None:
        self._module_name = module_name
        self._install_hint = install_hint or module_name.split(".", 1)[0]

    def __getattr__(self, attribute: str) -> Any:
        try:
            module = import_module(self._module_name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"{self._module_name} is required for this AI provider. "
                f"Install with `pip install {self._install_hint}`."
            ) from exc
        return getattr(module, attribute)
