import sys
import unittest
from unittest.mock import MagicMock

from src.agents.project_creator.ideation.catalog_mcp import catalog_history, fetch_catalog_repos

_FAKE_SERVER = (
    "import sys,json\n"
    "for l in sys.stdin:\n"
    " m=json.loads(l)\n"
    " r={'protocolVersion':'x'} if m['method']=='initialize' else "
    "{'content':[{'type':'text','text':json.dumps([{'name':'slo-meter','purpose':'p','categories':['sre']}])}]}\n"
    " print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':r}),flush=True)\n"
)


class TestCatalogMcp(unittest.TestCase):
    def test_fetch_from_stdio_server(self):
        repos = fetch_catalog_repos(MagicMock(), f"{sys.executable} -c \"{_FAKE_SERVER}\"")
        self.assertEqual([r["name"] for r in repos], ["slo-meter"])

    def test_unset_command_returns_empty(self):
        log = MagicMock()
        self.assertEqual(fetch_catalog_repos(log, ""), [])

    def test_bad_command_fails_open(self):
        self.assertEqual(fetch_catalog_repos(MagicMock(), "/nonexistent/binary"), [])

    def test_history_lines(self):
        self.assertEqual(catalog_history([{"name": "a", "purpose": "x", "categories": ["c"]}]), ["a x c"])
