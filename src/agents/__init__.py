"""Agents package.

Agent classes are loaded through ``src.agents.registry`` on demand. Keep this
module lightweight so importing helpers such as ``src.agents.reporting`` does
not import every agent implementation and block unrelated commands.
"""

__all__: list[str] = []
