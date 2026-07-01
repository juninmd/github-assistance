"""Tests for structured logger output safety."""
import unittest

from src.utils.logger import _safe_print


class Cp1252OnlyStream:
    encoding = "cp1252"

    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, value: str) -> int:
        value.encode(self.encoding)
        self.lines.append(value)
        return len(value)

    def flush(self) -> None:
        pass


class TestLogger(unittest.TestCase):
    def test_safe_print_replaces_unsupported_unicode(self):
        stream = Cp1252OnlyStream()

        _safe_print("health ✅ ready", stream)  # type: ignore[arg-type]

        self.assertIn("health ? ready", "".join(stream.lines))
