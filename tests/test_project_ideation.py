import json
import random
import unittest
from unittest.mock import MagicMock, patch

from src.agents.project_creator.ideation import IdeationConfig, IdeationPipeline
from src.agents.project_creator.ideation.catalog import _validate, load_catalog
from src.agents.project_creator.ideation.rules import (
    crowd_penalty,
    name_problem,
    parse_json,
    render_prompt,
)
from src.agents.project_creator.ideation.seed import Signals, domain_saturation, pick_seed


def _rng(n=0):
    return random.Random(n)  # noqa: S311


def _candidates():
    return {"candidates": [
        {"repository_name": "smart-expense-tracker", "title": "A"},
        {"repository_name": "slo-burn-meter", "title": "B", "search_terms": ["slo", "burn"]},
        {"repository_name": "tracer-diff", "title": "C", "search_terms": "bad"},
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
        "roadmap_features": ["r1", "r2", "r3", "r4"],
    }
    spec.update(over)
    return spec


class TestCatalog(unittest.TestCase):
    def test_bundled_catalog_is_valid(self):
        cat = load_catalog()
        self.assertGreaterEqual(len(cat.domains), 15)
        self.assertTrue(cat.archetypes and cat.twists)

    def test_validate_rejects_bad_shapes(self):
        good = {"domains": [{"name": "d", "keywords": [], "angles": ["a"], "weight": 1}],
                "archetypes": [{"name": "a", "description": "x", "stacks": ["Go"]}],
                "twists": ["t"]}
        self.assertEqual(_validate(good).twists, ["t"])
        for bad in (
            [], {**good, "domains": []}, {**good, "twists": []},
            {**good, "archetypes": [{"name": "a"}]},
        ):
            with self.assertRaises(ValueError):
                _validate(bad)

    def test_override_path_and_fallback(self):
        missing = load_catalog("/nonexistent/catalog.yaml")
        self.assertEqual(missing.domains, load_catalog().domains)
        with patch.dict("os.environ", {"IDEATION_CATALOG_PATH": "/nonexistent.yaml"}):
            self.assertTrue(load_catalog().domains)


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            cfg = IdeationConfig.from_env()
        self.assertEqual((cfg.candidates, cfg.attempts, cfg.min_score), (5, 3, 15))
        self.assertTrue(cfg.similar_search and cfg.scaffold)
        self.assertIsNone(cfg.critic_model)

    def test_overrides_clamped_and_invalid_ignored(self):
        env = {"IDEATION_CANDIDATES": "99", "IDEATION_ATTEMPTS": "abc", "IDEATION_MIN_SCORE": "18",
               "IDEATION_SIMILAR_SEARCH": "false", "IDEATION_CRITIC_MODEL": " other ",
               "IDEATION_MEMORY_PATH": "/tmp/m.json", "IDEATION_SCAFFOLD": "0"}
        with patch.dict("os.environ", env, clear=True):
            cfg = IdeationConfig.from_env()
        self.assertEqual((cfg.candidates, cfg.attempts, cfg.min_score), (10, 3, 18))
        self.assertFalse(cfg.similar_search or cfg.scaffold)
        self.assertEqual((cfg.critic_model, cfg.memory_path), ("other", "/tmp/m.json"))


class TestSeed(unittest.TestCase):
    def test_saturation_counts_keyword_hits(self):
        sat = domain_saturation(["my-llm-agent prompt toolkit", "other"])
        self.assertEqual(sat["AI/LLM engineering"], 1)

    def test_saturated_domain_is_rare(self):
        history = ["llm prompt agent rag"] * 30
        rng = _rng(1)
        picks = [pick_seed(history, rng).domain for _ in range(200)]
        self.assertLess(picks.count("AI/LLM engineering"), 10)

    def test_default_rng_and_fields(self):
        seed = pick_seed([])
        self.assertTrue(seed.angles and seed.stacks and seed.twist)

    def test_cooldown_suppresses_recent_domain_and_shape(self):
        signals = Signals(recent=[{"domain": "developer tooling", "archetype": "CLI tool",
                                   "age_days": 1}])
        rng = _rng(2)
        picks = [pick_seed([], rng, signals) for _ in range(400)]
        rng = _rng(2)
        base = [pick_seed([], rng) for _ in range(400)]
        self.assertLess(sum(p.domain == "developer tooling" for p in picks),
                        sum(p.domain == "developer tooling" for p in base))
        self.assertLess(sum(p.archetype == "CLI tool" for p in picks),
                        sum(p.archetype == "CLI tool" for p in base))

    def test_old_recent_entries_do_not_cool_down(self):
        signals = Signals(recent=[{"domain": "developer tooling", "age_days": 90}])
        r1, r2 = _rng(3), _rng(3)
        picks = [pick_seed([], r1, signals).domain for _ in range(300)]
        base = [pick_seed([], r2).domain for _ in range(300)]
        self.assertEqual(picks, base)

    def test_failed_outcomes_make_domain_rarer_and_wins_commoner(self):
        fails = Signals(outcomes=[{"domain": "games & play", "score": 0.0}] * 5)
        wins = Signals(outcomes=[{"domain": "games & play", "score": 1.0}] * 5)

        def count(sig):
            rng = _rng(4)
            return sum(pick_seed([], rng, sig).domain == "games & play" for _ in range(1500))

        self.assertLess(count(fails), count(Signals()))
        self.assertGreater(count(wins), count(Signals()))


class TestRules(unittest.TestCase):
    def test_parse_json(self):
        self.assertEqual(parse_json('x {"a": 1} y'), {"a": 1})
        for bad in ("nothing", "{bad json}", "[1]", None):
            self.assertIsNone(parse_json(bad))

    def test_name_problem(self):
        self.assertIsNotNone(name_problem("smart-app", [], False))
        self.assertIsNotNone(name_problem("", [], False))
        self.assertIsNotNone(name_problem("expense-radar", [], False))
        self.assertIsNone(name_problem("expense-radar", [], True))
        self.assertIsNotNone(name_problem("slo-burn", ["slo-burn-meter"], False))
        self.assertIsNone(name_problem("slo-burn", ["unrelated"], False))

    def test_crowd_penalty(self):
        self.assertEqual([crowd_penalty(n) for n in (0, 19, 20, 99, 100, 5000)], [0, 0, 1, 1, 2, 2])

    def test_render_prompt(self):
        out = render_prompt(_spec())
        self.assertIn("Acceptance: a", out)
        self.assertIn("### Test plan", out)


class TestPipeline(unittest.TestCase):
    def _run(self, responses, attempts=1, **kwargs):
        gen = MagicMock(side_effect=[r if isinstance(r, str) else json.dumps(r) for r in responses])
        pipe = IdeationPipeline(gen, MagicMock(), rng=_rng(0),
                                config=IdeationConfig(attempts=attempts), **kwargs)
        return pipe.run(["h"], ["existing"]), gen, pipe

    def test_happy_path_filters_generic_and_picks_best(self):
        idea, gen, pipe = self._run([_candidates(), _scores((4, 4, 4, 4), (5, 5, 4, 5)), _spec()])
        self.assertEqual(idea["repository_name"], "slo-burn-meter")
        self.assertEqual(idea["seed"].keys(), {"domain", "archetype"})
        self.assertIn("### Features", idea["jules_prompt"])
        self.assertNotIn("smart-expense-tracker", gen.call_args_list[1].args[0])
        self.assertEqual(pipe.report[0]["chosen"], "slo-burn-meter")
        self.assertEqual(pipe.report[0]["rejected"][0]["name"], "smart-expense-tracker")

    def test_low_scores_rejected_then_retry_succeeds(self):
        idea, _, pipe = self._run(
            [_candidates(), _scores((2, 5, 5, 5), (3, 2, 5, 5)),
             _candidates(), _scores((4, 4, 4, 4)), _spec()], attempts=2)
        self.assertIsNotNone(idea)
        self.assertEqual(len(pipe.report), 2)
        self.assertIsNone(pipe.report[0]["chosen"])

    def test_all_attempts_fail(self):
        idea, _, pipe = self._run(["junk", "junk"], attempts=2)
        self.assertIsNone(idea)
        self.assertEqual(len(pipe.report), 2)

    def test_malformed_scores_ignored(self):
        bad = {"scores": [{"index": "x"}, {"index": 9, "novelty": 5, "utility": 5,
                                            "feasibility": 5, "distinctiveness": 5}]}
        idea, _, _ = self._run([_candidates(), bad])
        self.assertIsNone(idea)

    def test_spec_gate_failures(self):
        for spec in (_spec(roadmap_features=["x"]), _spec(repository_name="budget-pro"), "junk"):
            idea, _, pipe = self._run([_candidates(), _scores((5, 5, 5, 5)), spec])
            self.assertIsNone(idea)
        self.assertEqual(pipe.report[0]["rejected"][-1]["reason"], "spec gate")

    def test_malformed_candidates_are_skipped(self):
        junk = {"candidates": ["text", {"title": "no name"}]}
        idea, _, _ = self._run([junk])
        self.assertIsNone(idea)

    def test_ai_exception_is_handled(self):
        pipe = IdeationPipeline(MagicMock(side_effect=Exception("down")), MagicMock(),
                                config=IdeationConfig(attempts=1))
        self.assertIsNone(pipe.run([], []))

    def test_independent_critic_scores_and_search_enriches(self):
        search = MagicMock(return_value=(7, [{"name": "o/r", "stars": 1, "description": ""}]))
        critic = MagicMock(return_value=json.dumps(_scores((4, 4, 4, 4), (4, 4, 4, 4))))
        gen = MagicMock(side_effect=[json.dumps(_candidates()), json.dumps(_spec())])
        pipe = IdeationPipeline(gen, MagicMock(), rng=_rng(0), config=IdeationConfig(attempts=1),
                                critic=critic, search=search)
        self.assertIsNotNone(pipe.run([], []))
        self.assertEqual(gen.call_count, 2)  # critique went to the critic, not the generator
        prompt = critic.call_args.args[0]
        self.assertIn("public_similar", prompt)
        self.assertIn('"public_matches": 7', prompt)
        search.assert_any_call(["slo", "burn"])
        search.assert_any_call([])  # non-list search_terms degrade to an empty query

    def test_crowded_space_lowers_distinctiveness_below_threshold(self):
        search = MagicMock(return_value=(500, []))  # penalty 2
        # 4+4+4+4=16 passes alone; distinctiveness 4-2 -> total 14 < 15
        idea, _, _ = self._run([_candidates(), _scores((4, 4, 4, 4), (4, 4, 4, 4))],
                               search=search)
        self.assertIsNone(idea)

    def test_previously_rejected_names_are_filtered(self):
        signals = Signals(rejected=["slo-burn-meter", "tracer-diff"])
        idea, gen, pipe = self._run([_candidates()], signals=signals)
        self.assertIsNone(idea)
        self.assertIn("never propose again", gen.call_args_list[0].args[0])
        reasons = {r["reason"] for r in pipe.report[0]["rejected"]}
        self.assertIn("previously rejected", reasons)
