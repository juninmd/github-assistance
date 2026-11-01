import json
import random
import unittest
from unittest.mock import MagicMock

from src.agents.project_creator.ideation import IdeationPipeline
from src.agents.project_creator.ideation.catalog import DOMAINS
from src.agents.project_creator.ideation.pipeline import name_problem, parse_json, render_prompt
from src.agents.project_creator.ideation.portfolio import Portfolio, build_portfolio
from src.agents.project_creator.ideation.prompts import critique_prompt, diverge_prompt
from src.agents.project_creator.ideation.seed import domain_saturation, pick_seed, prefer_stacks


def _candidates():
    return {"candidates": [
        {"repository_name": "smart-expense-tracker", "title": "A"},
        {"repository_name": "slo-burn-meter", "title": "B"},
        {"repository_name": "tracer-diff", "title": "C"},
    ]}


def _scores(*rows):
    """Rows are (novelty, utility, feasibility, distinctiveness); fit defaults to 5 unless a 5th value is given."""
    return {"scores": [
        {"index": i, "novelty": r[0], "utility": r[1], "fit": r[4] if len(r) > 4 else 5,
         "feasibility": r[2], "distinctiveness": r[3]}
        for i, r in enumerate(rows)
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
        bad = {"scores": [{"index": "x"}, {"index": 9, "novelty": 5, "utility": 5, "fit": 5,
                                            "feasibility": 5, "distinctiveness": 5}]}
        idea, _ = self._run([_candidates(), bad])
        self.assertIsNone(idea)

    def test_low_fit_is_rejected_even_with_high_total(self):
        # 5/5/5/5 but the owner would never use it: fit=3 must veto the candidate
        idea, _ = self._run([_candidates(), _scores((5, 5, 5, 5, 3), (5, 5, 5, 5, 3))])
        self.assertIsNone(idea)

    def test_gate_boundaries_total_and_fit(self):
        # total 18 (< 19) with fit 4 rejected; total 19 with fit 4 accepted
        idea, _ = self._run([_candidates(), _scores((4, 4, 3, 3, 4), (4, 4, 3, 3, 4)), _spec()])
        self.assertIsNone(idea)
        idea, _ = self._run([_candidates(), _scores((4, 4, 3, 4, 4), (4, 4, 3, 4, 4)), _spec()])
        self.assertIsNotNone(idea)

    def test_out_of_range_scores_are_clamped(self):
        idea, _ = self._run([_candidates(), _scores((9, 9, 9, 9, 3), (9, 9, 9, 9, 3))])
        self.assertIsNone(idea)  # fit clamps to 3 < MIN_FIT

    def test_portfolio_reaches_diverge_and_critique_prompts(self):
        portfolio = Portfolio(exemplars=["whyslow (TypeScript): HTTP phase diagnostics"],
                              generated=["retainer-burnrate-tracker"], languages=["TypeScript"])
        gen = MagicMock(side_effect=[json.dumps(r) for r in [
            _candidates(), _scores((4, 4, 4, 4), (5, 5, 4, 5)), _spec()]])
        IdeationPipeline(gen, MagicMock(), rng=random.Random(0), attempts=1).run(  # noqa: S311
            ["h"], ["existing"], portfolio)
        for call in gen.call_args_list[:2]:
            self.assertIn("whyslow (TypeScript)", call.args[0])
            self.assertIn("retainer-burnrate-tracker", call.args[0])

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


def _named(name, description="", language=None, archived=False, fork=False):
    repo = MagicMock(description=description, language=language, archived=archived, fork=fork)
    repo.name = name  # MagicMock(name=...) would name the mock, not set the attribute
    return repo


class TestPortfolio(unittest.TestCase):
    def test_splits_hand_built_from_autonomous_and_skips_forks_archived(self):
        repos = [
            _named("whyslow", description="HTTP phase diagnostics: DNS, TCP, TLS", language="TypeScript"),
            _named("zplint", description="Fast linter for Pawn plugins", language="Rust"),
            _named("retainer-tracker", description="Burn rate. | 🤖 Criado de forma autônoma pelo agente",
                   language="Go"),
            _named("old", description="Archived project with a description", language="Java", archived=True),
            _named("forked", description="A fork of something popular here", language="C", fork=True),
            _named("agar", description="", language="JavaScript"),
            _named("infra", description="Dockerfile-only deployment glue", language="Dockerfile"),
        ]
        profile = build_portfolio(repos)
        self.assertEqual([e.split(" ")[0] for e in profile.exemplars], ["whyslow", "zplint", "infra"])
        self.assertEqual(profile.generated, ["retainer-tracker"])
        self.assertNotIn("Go", profile.languages)  # autonomous repos do not shape the owner's stack
        self.assertNotIn("Dockerfile", profile.languages)
        self.assertEqual(set(profile.languages), {"TypeScript", "Rust", "JavaScript"})

    def test_skips_other_owners_and_flattens_descriptions(self):
        mine = _named("mine", description="Line one\n- fake: injected bullet", language="Rust")
        mine.owner.login = "JuninMD"
        theirs = _named("team-repo", description="Team project from a collaborator", language="Java")
        theirs.owner.login = "some-org"
        profile = build_portfolio([mine, theirs], "juninmd")
        self.assertEqual(profile.languages, ["Rust"])
        self.assertEqual(len(profile.exemplars), 1)
        self.assertNotIn("\n", profile.exemplars[0])

    def test_created_repo_description_is_classified_as_generated(self):
        # couples the notice written by the agent to the marker read by build_portfolio
        from src.agents.project_creator.agent import ProjectCreatorAgent
        user = MagicMock()
        agent = MagicMock(target_owner="juninmd")
        agent.github_client.g.get_user.return_value = user
        ProjectCreatorAgent._create_github_repo(agent, "r", "x" * 400)
        description = user.create_repo.call_args.kwargs["description"]
        repo = _named("r", description=description, language="Go")
        self.assertEqual(build_portfolio([repo]).generated, ["r"])

    def test_tolerates_non_string_attributes(self):
        profile = build_portfolio([MagicMock()])
        self.assertEqual(profile, Portfolio())

    def test_prefer_stacks_puts_owned_language_first_and_keeps_rest(self):
        stacks = ["Go + chi", "Python + FastAPI", "Node.js + TypeScript"]
        self.assertEqual(prefer_stacks(stacks, ["TypeScript"])[0], "Node.js + TypeScript")
        self.assertEqual(prefer_stacks(stacks, ["Cobol"]), stacks)
        self.assertEqual(prefer_stacks(stacks, ["JavaScript"])[0], "Node.js + TypeScript")
        self.assertEqual(sorted(prefer_stacks(stacks, ["Python"])), sorted(stacks))

    def test_pick_seed_leads_with_owner_language(self):
        portfolio = Portfolio(languages=["Rust"])
        for i in range(30):
            seed = pick_seed([], random.Random(i), portfolio)  # noqa: S311
            if any("rust" in s.lower() for s in seed.stacks):
                self.assertIn("rust", seed.stacks[0].lower())

    def test_prompts_without_portfolio_are_unchanged_in_shape(self):
        seed = pick_seed([], random.Random(0))  # noqa: S311
        self.assertNotIn("Owner portfolio", diverge_prompt(seed, [], 3))
        self.assertNotIn("Owner portfolio", critique_prompt([{"repository_name": "x"}], []))
        self.assertIn('"fit"', critique_prompt([{"repository_name": "x"}], []))
