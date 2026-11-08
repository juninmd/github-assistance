"""Credential-safe git plumbing for automated clones and pushes.

Automated agents used to clone repositories with the GitHub token embedded in
the remote URL (``https://<token>@github.com/...``). That URL persists in the
clone's ``.git/config`` and is echoed by ``git remote -v`` and in ``git``
error output, so anything the agent (an LLM child process) reads or prints can
leak the credential straight into a committed PR — observed in a PR of the
security-hardening flow where the token landed in the diff.

The helpers below keep the credential *out of persistent artifacts*:

- :func:`github_clone_url` builds a token-free remote URL — safe to persist in
  ``.git/config``, to echo in logs, and to read from inside the clone.
- :func:`auth_config_args` authenticates a single ``git`` network command
  (clone/fetch/push) via ``-c http.<url>.extraheader=...``. The override lives
  only for that invocation, so the token never lands on disk.
- :func:`scrub_env` removes secret-bearing environment variables before
  spawning the LLM child process (a chatty model can echo env values into the
  files it commits).
"""

from __future__ import annotations

import base64
import os
import re

GITHUB_HOST = "github.com"

# Environment variables that carry credentials and must not reach the LLM
# child process. Lowercase-safe matching is not needed: names are uppercase.
DEFAULT_ENV_DENY: tuple[str, ...] = (
    "ADMIN_API_TOKEN",
    "GEMINI_API_KEY",
    "GH_PAT",
    "GITHUB_TOKEN",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_WEBHOOK_SECRET",
    "JULES_API_KEY",
    "OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
)

# Named explicitly so the wildcard below does not strip it: opencode resolves
# its models through the LiteLLM proxy and needs this key to authenticate.
DEFAULT_ENV_KEEP: tuple[str, ...] = ("LITELLM_API_KEY",)

_WILDCARD = re.compile(r"(_KEY|_TOKEN|_SECRET|_PAT)$")


def _env_list(name: str) -> list[str]:
    """Read a comma-separated env var list (used for per-deployment overrides)."""
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def github_clone_url(repository: str) -> str:
    """Token-free HTTPS remote URL — safe to persist, log and echo."""
    return f"https://{GITHUB_HOST}/{repository}.git"


def auth_config_args(token: str | None = None) -> list[str]:
    """Return ``git -c`` args that authenticate one command, and only it.

    Prepended to any network-touching ``git`` invocation (clone, fetch, push).
    The basic-auth credential is the documented GitHub App pattern
    ``x-access-token:<token>``. Because the arg never touches a config file,
    the token cannot leak through ``.git/config``, ``git remote -v`` or
    rewrite-history tools such as ``git-filter-repo`` (which would otherwise
    re-embed the tainted remote URL).

    An empty ``token`` (and no ``GITHUB_TOKEN``/``GH_PAT`` in the environment)
    returns ``[]``, keeping public-repository clones and pushes unauthenticated.
    """
    token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT") or ""
    if not token:
        return []
    raw = f"x-access-token:{token}".encode()
    header = f"Authorization: Basic {base64.b64encode(raw).decode()}"
    return ["-c", f"http.https://{GITHUB_HOST}/.extraheader={header}"]


_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"x-access-token:[^@\s]+@"), "x-access-token:REDACTED@"),
    (re.compile(r"(?i)(Authorization:\s*(?:Basic|Bearer|token)\s+)\S+"), r"\1REDACTED"),
    (re.compile(r"(?i)(extraheader=)\S+(?:\s+\S+)?"), r"\1REDACTED"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "REDACTED"),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})"), "REDACTED"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "REDACTED"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S), "REDACTED"),
    (re.compile(r"(?i)\b((?:api[_-]?key|token|secret|password|passwd)\s*[=:]\s*)[\"']?[^\s\"',;]{8,}"), r"\1REDACTED"),
)


def redact_secrets(text: str | None) -> str:
    """Strip tokens and auth headers from text bound for logs, errors or PR comments."""
    out = text or ""
    for pattern, repl in _REDACTIONS:
        out = pattern.sub(repl, out)
    return out


def redact_cmd(cmd) -> str:
    """Join a command's args with every credential masked."""
    return redact_secrets(" ".join(str(a) for a in cmd)) if cmd else ""


def _denied(name: str, deny: set[str], keep: set[str]) -> bool:
    if name in keep:
        return False
    return name in deny or bool(_WILDCARD.search(name))


def scrub_env(
    env: dict[str, str] | None = None,
    *,
    extra_deny: tuple[str, ...] = (),
    extra_keep: tuple[str, ...] = (),
) -> dict[str, str]:
    """Return a copy of ``env`` (default ``os.environ``) without credentials.

    Deny-list: :data:`DEFAULT_ENV_DENY`, ``OPENCODE_ENV_DENY``, ``extra_deny``
    plus any name ending in ``_KEY``/``_TOKEN``/``_SECRET``/``_PAT``.
    Keep-list: :data:`DEFAULT_ENV_KEEP`, ``OPENCODE_ENV_KEEP`` and
    ``extra_keep`` win over every rule, so a deployment can always opt one
    variable back in (e.g. ``LITELLM_API_KEY`` for the opencode provider).
    """
    source = dict(env) if env is not None else dict(os.environ)
    deny = set(DEFAULT_ENV_DENY) | set(_env_list("OPENCODE_ENV_DENY")) | set(extra_deny)
    keep = set(DEFAULT_ENV_KEEP) | set(_env_list("OPENCODE_ENV_KEEP")) | set(extra_keep)
    return {name: value for name, value in source.items() if not _denied(name, deny, keep)}
