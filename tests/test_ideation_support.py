import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from src.agents.project_creator.ideation import (
    IdeationConfig,
    apply_scaffold,
    run_ideation,
    topics_for,
)
from src.agents.project_creator.ideation.catalog import DEFAULT_PATH
from src.agents.project_creator.ideation.ci_templates import ci_workflow, detect_stack
from src.agents.project_creator.ideation.feedback import ROOT_TOPIC, collect_signals
from src.agents.project_creator.ideation.memory import IdeaMemory
from src.agents.project_creator.ideation.scaffold import build_files
from src.agents.project_creator.ideation.similar import make_searcher

NOTICE = "autonomous-notice"
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def _repo(topics, age_days, pulls, desc=NOTICE, name="r"):
    repo = MagicMock()
    repo.name, repo.description = name, desc
    repo.created_at = NOW - timedelta(days=age_days)
    repo.get_topics.return_value = topics
    repo.get_pulls.return_value = pulls
    return repo


def _pr(merged=False, state="closed"):
    pr = MagicMock()
    pr.merged_at = NOW if merged else None
    pr.state = state
    return pr


class TestSimilar(unittest.TestCase):
    def test_search_returns_total_and_top(self):
        client, log = MagicMock(), MagicMock()
        items = [MagicMock(full_name=f"o/r{i}", stargazers_count=i, description=None) for i in range(5)]
        results = MagicMock(totalCount=42)
        results.__iter__.return_value = iter(items)
        client.g.search_repositories.return_value = results
        total, found = make_searcher(client, log)(["slo", " ", "burn"])
        self.assertEqual(total, 42)
        self.assertEqual([f["name"] for f in found], ["o/r0", "o/r1", "o/r2"])
        self.assertEqual(found[0]["description"], "")
        self.assertIn("slo burn in:name", client.g.search_repositories.call_args.kwargs["query"])

    def test_empty_terms_and_failure(self):
        client, log = MagicMock(), MagicMock()
        search = make_searcher(client, log)
        self.assertEqual(search([]), (0, []))
        client.g.search_repositories.assert_not_called()
        client.g.search_repositories.side_effect = Exception("rate limit")
        self.assertEqual(search(["x"]), (0, []))
        log.assert_called_once()


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "sub" / "mem.json")
        self.mem = IdeaMemory(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_and_read_back(self):
        attempts = [{"domain": "d", "archetype": "a", "chosen": "proj",
                     "rejected": [{"name": "bad", "reason": "low score"}, {"reason": "no name"}]}]
        self.mem.record(attempts)
        self.mem.record([])  # no-op
        self.assertEqual(self.mem.rejected_names(), ["bad"])
        recent = self.mem.recent_choices()
        self.assertEqual(recent[0]["domain"], "d")
        self.assertEqual(recent[0]["age_days"], 0)

    def test_unchosen_attempts_not_in_recent_and_dedup(self):
        self.mem.record([{"domain": "d", "archetype": "a", "chosen": None,
                          "rejected": [{"name": "x"}, {"name": "x"}]}])
        self.assertEqual(self.mem.recent_choices(), [])
        self.assertEqual(self.mem.rejected_names(), ["x"])

    def test_corrupt_and_wrong_shape_files(self):
        Path(self.path).parent.mkdir(parents=True)
        Path(self.path).write_text("{not json")
        self.assertEqual(self.mem.rejected_names(), [])
        Path(self.path).write_text('{"a": 1}')
        self.assertEqual(self.mem.recent_choices(), [])
        Path(self.path).write_text(json.dumps([{"at": "garbage", "attempts": []}, {"attempts": []}]))
        self.assertEqual(self.mem.recent_choices(), [])

    def test_write_failure_is_logged(self):
        log = MagicMock()
        bad = IdeaMemory("/proc/forbidden/mem.json", log)
        bad.record([{"domain": "d"}])
        log.assert_called_once()

    def test_default_log_is_silent(self):
        IdeaMemory("/proc/forbidden/mem.json").record([{"domain": "d"}])


class TestFeedback(unittest.TestCase):
    def test_topics_for(self):
        self.assertEqual(topics_for(None), [ROOT_TOPIC])
        self.assertEqual(
            topics_for({"domain": "AI/LLM engineering", "archetype": "HTTP API service"}),
            [ROOT_TOPIC, "domain-ai-llm-engineering", "shape-http-api-service"],
        )

    def test_outcomes_and_recent(self):
        topics = ["autonomous-project", "domain-games-play", "shape-cli-tool"]
        repos = [
            _repo(topics, 10, [_pr(merged=True)]),
            _repo(topics, 10, [_pr(state="open")]),
            _repo(topics, 10, []),
            _repo(topics, 1, []),  # too young for a verdict, still counts as recent
            _repo(["unrelated"], 10, []),  # no seed topics
            _repo(topics, 10, [], desc="human repo"),  # not autonomous
        ]
        sig = collect_signals(repos, NOTICE, MagicMock(), NOW)
        self.assertEqual([o["score"] for o in sig.outcomes], [1.0, 0.5, 0.0])
        self.assertEqual(sig.outcomes[0]["domain"], "games & play")
        self.assertEqual(sig.outcomes[0]["archetype"], "CLI tool")
        self.assertEqual(len(sig.recent), 4)
        self.assertEqual(min(r["age_days"] for r in sig.recent), 1)

    def test_repo_failure_is_logged_and_skipped(self):
        bad = _repo([], 5, [])
        bad.get_topics.side_effect = Exception("403")
        log = MagicMock()
        sig = collect_signals([bad], NOTICE, log, NOW)
        self.assertEqual((sig.outcomes, sig.recent), ([], []))
        log.assert_called_once()

    def test_description_none_is_not_autonomous(self):
        repo = _repo(["autonomous-project"], 5, [], desc=None)
        self.assertEqual(collect_signals([repo], NOTICE, MagicMock(), NOW).recent, [])


class TestCi(unittest.TestCase):
    def test_detect_stack(self):
        cases = {"Python + FastAPI": "python", "Go CLI": "go", "Go + chi": "go",
                 "Node.js + TypeScript": "node", "Rust + Ratatui": "rust",
                 "machine learning": None, "": None}
        for text, expected in cases.items():
            self.assertEqual(detect_stack(text), expected, text)

    def test_workflow_has_no_schedule(self):
        for stack in ("Python", "TypeScript", "Go", "Rust"):
            wf = ci_workflow(stack)
            self.assertIn("pull_request", wf)
            self.assertNotIn("schedule", wf)
            self.assertNotIn("cron", wf)
            yaml.safe_load(wf)
        self.assertIsNone(ci_workflow("Cobol"))


class TestScaffold(unittest.TestCase):
    SPEC = {"repository_name": "x", "title": "X", "tech_stack": "Python", "jules_prompt": "BODY",
            "idea_description": "desc"}

    def test_build_files(self):
        files = build_files(self.SPEC, "juninmd", NOW)
        self.assertIn("Copyright (c) 2026 juninmd", files["LICENSE"])
        self.assertIn("BODY", files["docs/SPEC.md"])
        self.assertIn(".github/workflows/ci.yml", files)

    def test_no_ci_and_title_fallback(self):
        files = build_files({"repository_name": "x"}, "o")
        self.assertNotIn(".github/workflows/ci.yml", files)
        self.assertTrue(files["docs/SPEC.md"].startswith("# x"))

    def test_apply_scaffold_skips_failures(self):
        repo, log = MagicMock(), MagicMock()
        repo.create_file.side_effect = [None, Exception("exists"), None, None, None]
        created = apply_scaffold(repo, self.SPEC, "o", log)
        self.assertEqual(len(created), 4)
        log.assert_called_once()
        self.assertEqual(repo.create_file.call_args.kwargs, {"branch": "master"})


class TestRuntime(unittest.TestCase):
    def _run(self, cfg, github=None):
        github = github or MagicMock()
        with patch("src.agents.project_creator.ideation.runtime.IdeationPipeline") as pipe_cls, \
             patch("src.agents.project_creator.ideation.runtime.get_ai_client") as get_client:
            pipe_cls.return_value.run.return_value = {"repository_name": "x"}
            pipe_cls.return_value.report = [{"domain": "d", "archetype": "a", "chosen": "x",
                                             "rejected": [{"name": "old"}]}]
            idea = run_ideation(MagicMock(), github, ["h"], ["n"], NOTICE, MagicMock(), cfg)
        return idea, pipe_cls, get_client

    def test_wires_everything_and_logs_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = IdeationConfig(memory_path=f"{tmp}/m.json", critic_model="alt", similar_search=True)
            idea, pipe_cls, get_client = self._run(cfg)
            self.assertEqual(idea, {"repository_name": "x"})
            get_client.assert_called_once_with(provider="litellm", model="alt")
            kwargs = pipe_cls.call_args.kwargs
            self.assertIs(kwargs["critic"], get_client.return_value.generate)
            self.assertIsNotNone(kwargs["search"])
            self.assertEqual(IdeaMemory(cfg.memory_path).rejected_names(), ["old"])

    def test_without_critic_search_and_with_repo_load_failure(self):
        github = MagicMock()
        github.get_user_repos.side_effect = Exception("boom")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict("os.environ", {}, clear=True):
            cfg = IdeationConfig(memory_path=f"{tmp}/m.json", similar_search=False)
            _, pipe_cls, get_client = self._run(cfg, github)
        get_client.assert_not_called()
        self.assertIsNone(pipe_cls.call_args.kwargs["critic"])
        self.assertIsNone(pipe_cls.call_args.kwargs["search"])

    def test_config_defaults_from_env(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict("os.environ", {"IDEATION_MEMORY_PATH": f"{tmp}/m.json"}):
            idea, *_ = self._run(None)
        self.assertIsNotNone(idea)


class TestBundledCatalogFile(unittest.TestCase):
    def test_yaml_parses(self):
        self.assertIn("domains", yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8")))
