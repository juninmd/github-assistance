"""Agents package.

Agent classes are loaded through ``src.agents.core.registry`` on demand. Keep this
module lightweight so importing helpers such as ``src.agents.core.reporting`` does
not import every agent implementation and block unrelated commands.
"""

__all__: list[str] = []
