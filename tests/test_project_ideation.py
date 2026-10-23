import json
import random
import unittest
from unittest.mock import MagicMock

from src.agents.project_creator.ideation import IdeationPipeline
from src.agents.project_creator.ideation.catalog import DOMAINS
from src.agents.project_creator.ideation.pipeline import name_problem, parse_json, render_prompt
from src.agents.project_creator.ideation.seed import domain_saturation, pick_seed


def _candidates():
    return {"candidates": [
        {"repository_name": "smart-expense-tracker", "title": "A"},
        {"repository_name": "slo-burn-meter", "title": "B"},
        {"repository_name": "tracer-diff", "title": "C"},
    ]}


def _scores(*rows):
    return {"scores": [
        {"index": i, "novelty": n, "utility": u, "feasibility": f, "distinctiveness": d}
        for i, (n, u, f, d) in enumerate(rows)
    ]}


def _spec(**over):
    spec = {
        "repository_name": "slo-burn-meter", "title": "SLO Burn Meter", "tech_stack": "Go",
        "idea_description": "A CLI that computes multi-window SLO burn rates from Prometheus "
                            "exports so on-call engineers know when to page.",
        "problem": "p", "target_user": "sre", "architecture": "a", "interfaces": "i",
        "fixtures": "f", "test_plan": "t",
        "features": [{"name": f"F{i}", "description": "d", "acceptance": "a"} for i in range(4)],
        "roadmap_features": [{"title": f"r{i}", "objective": "o"} for i in range(8)],
        "competitors": [{"name": "a/b", "url": "u", "strengths": "s", "gaps": "g"}],
        "external_features": ["x from a/b"],
    }
    spec.update(over)
    return spec


class TestSeed(unittest.TestCase):
    def test_saturation_counts_keyword_hits(self):
        sat = domain_saturation(["my-llm-agent prompt toolkit", "other"])
        self.assertEqual(sat["AI/LLM engineering"], 1)

    def test_saturated_domain_is_rare(self):
        history = ["llm prompt agent rag"] * 30
        rng = random.Random(1)  # noqa: S311
        picks = [pick_seed(history, rng).domain for _ in range(200)]
        self.assertLess(picks.count("AI/LLM engineering"), 10)

    def test_seed_fields_and_default_rng(self):
        seed = pick_seed([])
        self.assertIn(seed.domain, {d["name"] for d in DOMAINS})
        self.assertTrue(seed.angles and seed.stacks and seed.twist)


class TestHelpers(unittest.TestCase):
    def test_parse_json(self):
        self.assertEqual(parse_json('x {"a": 1} y'), {"a": 1})
        self.assertIsNone(parse_json("nothing"))
        self.assertIsNone(parse_json("{bad json}"))
        self.assertIsNone(parse_json("[1]"))
        self.assertIsNone(parse_json(None))

    def test_name_problem(self):
        self.assertIsNotNone(name_problem("smart-app", [], False))
        self.assertIsNotNone(name_problem("", [], False))
        self.assertIsNotNone(name_problem("expense-radar", [], False))
        self.assertIsNone(name_problem("expense-radar", [], True))
        self.assertIsNotNone(name_problem("slo-burn", ["slo-burn-meter"], False))
        self.assertIsNone(name_problem("slo-burn", ["unrelated"], False))

    def test_render_prompt_includes_acceptance(self):
        out = render_prompt(_spec())
        self.assertIn("Acceptance: a", out)
        self.assertIn("### Test plan", out)


class TestPipeline(unittest.TestCase):
    def _run(self, responses, attempts=1):
        gen = MagicMock(side_effect=[r if isinstance(r, str) else json.dumps(r) for r in responses])
        rng = random.Random(0)  # noqa: S311
        pipe = IdeationPipeline(gen, MagicMock(), rng=rng, attempts=attempts)
        return pipe.run(["h"], ["existing"]), gen

    def test_happy_path_filters_generic_and_picks_best(self):
        # candidate 0 (smart-expense-tracker) is filtered before critique, pool = [slo, tracer]
        idea, gen = self._run([_candidates(), _scores((4, 4, 4, 4), (5, 5, 4, 5)), _spec()])
        self.assertEqual(idea["repository_name"], "slo-burn-meter")
        self.assertIn("### Features", idea["jules_prompt"])
        self.assertEqual(gen.call_count, 3)
        self.assertIn("tracer-diff", gen.call_args_list[1].args[0])
        self.assertNotIn("smart-expense-tracker", gen.call_args_list[1].args[0])

    def test_low_scores_rejected_then_retry_succeeds(self):
        idea, _ = self._run(
            [_candidates(), _scores((2, 5, 5, 5), (3, 2, 5, 5)),
             _candidates(), _scores((4, 4, 4, 4)), _spec()], attempts=2)
        self.assertIsNotNone(idea)

    def test_all_attempts_fail(self):
        idea, _ = self._run(["junk", "junk"], attempts=2)
        self.assertIsNone(idea)

    def test_malformed_scores_ignored(self):
        bad = {"scores": [{"index": "x"}, {"index": 9, "novelty": 5, "utility": 5,
                                            "feasibility": 5, "distinctiveness": 5}]}
        idea, _ = self._run([_candidates(), bad])
        self.assertIsNone(idea)

    def test_spec_gate_rejects_short_spec(self):
        idea, _ = self._run([_candidates(), _scores((5, 5, 5, 5)), _spec(roadmap_features=["x"])])
        self.assertIsNone(idea)

    def test_spec_gate_rejects_generic_final_name(self):
        idea, _ = self._run(
            [_candidates(), _scores((5, 5, 5, 5)), _spec(repository_name="budget-pro")])
        self.assertIsNone(idea)

    def test_spec_missing(self):
        idea, _ = self._run([_candidates(), _scores((5, 5, 5, 5)), "junk"])
        self.assertIsNone(idea)

    def test_ai_exception_is_handled(self):
        gen = MagicMock(side_effect=Exception("down"))
        pipe = IdeationPipeline(gen, MagicMock(), attempts=1)
        self.assertIsNone(pipe.run([], []))


class TestResearch(unittest.TestCase):
    def _repo(self, full, stars):
        repo = MagicMock(full_name=full, stargazers_count=stars, html_url=f"https://github.com/{full}",
                         language="Go", description="d")
        repo.get_readme.return_value.decoded_content = b"# readme"
        repo.get_contents.return_value = [MagicMock(path="main.go")]
        return repo

    def test_excludes_own_repos_and_ranks_by_stars(self):
        from src.agents.project_creator.ideation.research import MarketResearcher
        gh = MagicMock()
        gh.search_repositories.return_value = [
            self._repo("juninmd/mine", 99), self._repo("a/low", 5), self._repo("b/high", 50)]
        http = MagicMock(side_effect=Exception("offline"))
        out = MarketResearcher(gh, MagicMock(), http_get=http).research(["q"], "juninmd")
        self.assertEqual([c["name"] for c in out["competitors"]], ["b/high", "a/low"])
        self.assertEqual(out["web"], [])

    def test_web_results_parsed(self):
        from src.agents.project_creator.ideation.research import MarketResearcher, format_research
        gh = MagicMock()
        gh.search_repositories.side_effect = Exception("rate")
        resp = MagicMock(text='<a class="result__a" href="https://x.io">X <b>Tool</b></a> '
                              '<a class="result__snippet" href="#">Does things</a>')
        out = MarketResearcher(gh, MagicMock(), http_get=MagicMock(return_value=resp)).research(["q"], "o")
        self.assertEqual(out["web"][0]["title"], "X Tool")
        self.assertIn("https://x.io", format_research(out))

    def test_pipeline_feeds_research_into_spec_prompt(self):
        researcher = MagicMock()
        researcher.research.return_value = {"competitors": [], "web": [
            {"title": "RivalTool", "url": "https://r.io", "snippet": "s"}]}
        gen = MagicMock(side_effect=[json.dumps(r) for r in [
            _candidates(), _scores((5, 5, 5, 5), (5, 5, 5, 5)), {"queries": ["slo burn"]}, _spec()]])
        pipe = IdeationPipeline(gen, MagicMock(), rng=random.Random(0), attempts=1,  # noqa: S311
                                researcher=researcher, owner="juninmd")
        idea = pipe.run(["h"], ["existing"])
        researcher.research.assert_called_once_with(["slo burn"], "juninmd")
        self.assertIn("RivalTool", gen.call_args_list[-1].args[0])
        self.assertIn("### Competitive landscape", idea["jules_prompt"])
