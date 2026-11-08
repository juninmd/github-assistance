"""Guardrails that keep agent flows from leaking credentials (PR #200 regression).

Regression: the security-hardening PR closed against a target repository
carried the runner's GitHub token inside generated content. The token had been
embedded in the clone remote URL and inherited through the LLM child env.
"""

import base64
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.utils.secret_scan import known_secrets, redact_text, scan_clone, scan_text
from src.utils.secure_git import auth_config_args, github_clone_url, scrub_env


class SecureGitTest(unittest.TestCase):
    def test_github_clone_url_has_no_credentials(self):
        url = github_clone_url("juninmd/steam-key-watcher")
        self.assertEqual(url, "https://github.com/juninmd/steam-key-watcher.git")

    def test_auth_config_args_use_base64_header_without_raw_token(self):
        token = "ghs_sometokenvalue012345678abcdefgh"
        args = auth_config_args(token)
        self.assertEqual(args[0], "-c")
        key, value = args[1].split("=", 1)
        self.assertEqual(key, "http.https://github.com/.extraheader")
        expected = "Authorization: Basic " + base64.b64encode(
            f"x-access-token:{token}".encode()
        ).decode()
        self.assertEqual(value, expected)
        self.assertNotIn(token, " ".join(args))

    def test_auth_config_args_empty_token_returns_no_args(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "", "GH_PAT": ""}):
            self.assertEqual(auth_config_args(), [])

    def test_auth_config_args_fall_back_to_environment(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghs_envtokenvalue0123456789abcdefgh"}):
            args = auth_config_args()
        self.assertIn("Basic", args[1])

    def test_scrub_env_removes_deny_list_and_wildcard(self):
        env = {
            "PATH": "/usr/bin",
            "GITHUB_TOKEN": "ghp_value",
            "GH_PAT": "pair",
            "TELEGRAM_BOT_TOKEN": "tok",
            "JULES_API_KEY": "key",
            "MY_SERVICE_SECRET": "x",
            "LITELLM_API_KEY": "keepme",
        }
        result = scrub_env(env)
        self.assertEqual(result, {"PATH": "/usr/bin", "LITELLM_API_KEY": "keepme"})

    def test_scrub_env_extra_keep_wins_over_wildcard(self):
        env = {"PROVIDER_API_KEY": "needed", "OTHER_TOKEN": "drop"}
        result = scrub_env(env, extra_keep=("PROVIDER_API_KEY",))
        self.assertEqual(result, {"PROVIDER_API_KEY": "needed"})


class SecretScanTest(unittest.TestCase):
    def test_scan_text_finds_github_pat(self):
        findings = scan_text("copy ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 into CI")
        rule_ids = [f["rule_id"] for f in findings]
        self.assertIn("github-pat", rule_ids)

    def test_scan_text_ignores_placeholder_examples(self):
        self.assertEqual(scan_text("GITHUB_TOKEN=ghp_your_token_here"), [])

    def test_scan_text_finds_url_embedded_credential(self):
        text = "remote add origin https://ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456@github.com/o/r.git"
        rule_ids = [f["rule_id"] for f in scan_text(text)]
        self.assertIn("url-embedded-github-cred", rule_ids)

    def test_scan_text_matches_known_secrets_exactly(self):
        token = "ghs_UNKNOWN-pattern-padding-value"
        findings = scan_text(f"token: {token}", known=[token])
        self.assertEqual([f["rule_id"] for f in findings], ["known-secret"])

    def test_known_secrets_skip_urls_and_short_values(self):
        env = {
            "GITHUB_TOKEN": "https://api.github.com",
            "MY_API_KEY": "short",
            "DEBUG_MODE": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
        }
        self.assertEqual(known_secrets(env), [])

    def test_redact_text_hides_patterns(self):
        text = "url https://ghs_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345@github.com/o/r.git leaked"
        self.assertNotIn("ghs_", redact_text(text))

    def test_scan_clone_skips_empty_and_missing_trees(self):
        self.assertEqual(scan_clone(Path("definitely-missing-dir")), [])


def _make_tree(tmp: Path, content: str) -> Path:
    (tmp / "SECURITY.md").write_text(content, encoding="utf-8")
    (tmp / ".git").mkdir()
    (tmp / ".git" / "leaky").write_text(
        "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345", encoding="utf-8"
    )
    return tmp


class ScanCloneTreeTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tree = _make_tree(Path(self._tmp.name), "token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
        self.tree_tail = Path(self._tmp.name)
        self.first = patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False)
        self.first.start()
        self.addCleanup(self.first.stop)

    def test_scan_clone_findings_have_file_rule_line(self):
        findings = scan_clone(self.tree_tail)
        self.assertTrue(findings)
        self.assertEqual(findings[0]["file"], "SECURITY.md")
        self.assertEqual(findings[0]["rule_id"], "github-pat")
        self.assertEqual(findings[0]["line"], 1)

    def test_scan_clone_never_scans_dotgit(self):
        leak_in_git = scan_clone(self.tree_tail)
        self.assertFalse(any(f["file"].startswith(".git") for f in leak_in_git))


class OpencodeRunnerGuardTest(unittest.TestCase):
    def setUp(self):
        from src.agents.opencode_runner import OpencodeRunner

        self.allowlist = MagicMock()
        self.allowlist.is_allowed.return_value = True
        self.github_client = MagicMock()
        self.runner = OpencodeRunner(
            self.allowlist, MagicMock(), self.github_client, MagicMock()
        )
        self.runner.max_attempts = 1
        OpencodeRunner._model_cache = "opencode/test-free"
        OpencodeRunner._models_cache = ["opencode/test-free"]
        git_config = patch("src.agents.utils.setup_git_config")
        git_config.start()
        self.addCleanup(git_config.stop)

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.proc_run")
    def test_clone_and_push_authenticate_via_config_args_not_url(self, mock_run, mock_tmpdir):
        mock_tmpdir.return_value.__enter__.return_value = "/tmp/repo"
        ok = subprocess.CompletedProcess(["git"], 0, "", "")
        mock_run.return_value = ok
        models = subprocess.CompletedProcess(["opencode", "models"], 0, "opencode/test-free", "")

        def side_effect(cmd, **_kwargs):
            return models if cmd[:2] == ["opencode", "models"] else ok

        mock_run.side_effect = side_effect
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghs_abc"}, clear=False):
            self.runner.run_on_repo("juninmd/repo", "do things", "Title", "agent")

        clone_cmds = [c.args[0] for c in mock_run.call_args_list if "clone" in c.args[0]]
        self.assertTrue(clone_cmds)
        clone_args = " ".join(clone_cmds[0])
        self.assertIn("https://github.com/juninmd/repo.git", clone_args)
        self.assertNotIn("ghs_abc@github.com", clone_args)
        self.assertIn("-c", clone_cmds[0])

        push_cmds = [c.args[0] for c in mock_run.call_args_list if "push" in c.args[0]]
        self.assertTrue(push_cmds)
        self.assertIn("-c", push_cmds[0])

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.proc_run")
    def test_run_on_repo_blocks_push_when_secret_found(self, mock_run, mock_tmpdir):
        mock_tmpdir.return_value.__enter__.return_value = "/tmp/repo"
        ok = subprocess.CompletedProcess(["git"], 0, "", "")
        models = subprocess.CompletedProcess(["opencode", "models"], 0, "opencode/test-free", "")
        run_ok = subprocess.CompletedProcess(["opencode"], 0, "changed files", "")

        def side_effect(cmd, **_kwargs):
            if cmd[:2] == ["opencode", "models"]:
                return models
            if "opencode" in cmd and "run" in cmd and cmd[-1] != "ping":
                return run_ok
            return ok

        mock_run.side_effect = side_effect
        finding = {"file": "SECURITY.md", "rule_id": "github-pat", "line": 3}
        with patch("src.agents.opencode_runner.scan_clone", return_value=[finding]):
            with patch.dict(os.environ, {"GITHUB_TOKEN": "ghs_abc"}, clear=False):
                result = self.runner.run_on_repo("juninmd/repo", "do things", "Title", "agent")

        self.assertEqual(result["status"], "push_blocked_secret")
        pushed = [c.args[0] for c in mock_run.call_args_list if "push" in c.args[0]]
        self.assertEqual(pushed, [])


if __name__ == "__main__":
    unittest.main()


class RedactSecretsTests(unittest.TestCase):
    def test_extraheader_cmd_is_masked(self):
        from src.utils.secure_git import auth_config_args, redact_cmd

        args = auth_config_args("ghp_" + "a" * 36)
        out = redact_cmd(["git", *args, "clone", "https://github.com/o/r.git"])
        self.assertNotIn("Basic ", out.replace("Basic REDACTED", ""))
        self.assertIn("REDACTED", out)
        self.assertIn("clone", out)

    def test_raw_tokens_masked(self):
        from src.utils.secure_git import redact_secrets

        out = redact_secrets("fail ghs_" + "b" * 36 + " Authorization: Basic eC1hY2Nlc3M=")
        self.assertNotIn("ghs_", out)
        self.assertNotIn("eC1hY2Nlc3M", out)


class RedactBroadTests(unittest.TestCase):
    def test_other_credential_shapes(self):
        from src.utils.secure_git import redact_secrets

        for raw in (
            "sk-" + "a" * 30,
            "AKIA" + "A" * 16,
            "123456789:" + "A" * 35,
            "api_key=" + "x" * 20,
            "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----",
        ):
            self.assertIn("REDACTED", redact_secrets(f"err {raw} end"), raw[:10])

    def test_plain_text_untouched(self):
        from src.utils.secure_git import redact_secrets

        self.assertEqual(redact_secrets("Pipeline falhou em web-smoke"), "Pipeline falhou em web-smoke")
