# Bun + TypeScript image (replaces ./Dockerfile at cutover). Same toolchain: gitleaks, trufflehog, semgrep, Node (npm in PR clones), opencode, tokenix, skills.
FROM ghcr.io/gitleaks/gitleaks:latest AS gitleaks

FROM oven/bun:1.4-debian

# Copy gitleaks binary (platform-native — avoids hardcoded x86_64 tarball)
COPY --from=gitleaks /usr/bin/gitleaks /usr/local/bin/gitleaks

# Install system dependencies + Node.js LTS
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    tini \
    python3 \
    python3-venv \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# SAST layers for the push guard (src/utils/sast_scan.py). Each is optional at runtime:
# the guard runs whatever is installed and is fail-open. trufflehog: pinned release
# binary (arch-aware); semgrep: isolated venv so its deps never touch the app's.
# trivy is supported when present on PATH but not baked in (add it the same way).
ARG TRUFFLEHOG_VERSION=3.88.0
ARG SEMGREP_VERSION=1.185.0
RUN arch="$(dpkg --print-architecture)" \
    && curl -fsSL "https://github.com/trufflesecurity/trufflehog/releases/download/v${TRUFFLEHOG_VERSION}/trufflehog_${TRUFFLEHOG_VERSION}_linux_${arch}.tar.gz" \
       | tar -xz -C /usr/local/bin trufflehog \
    && python3 -m venv /opt/semgrep \
    && /opt/semgrep/bin/pip install --no-cache-dir "semgrep==${SEMGREP_VERSION}" \
    && ln -s /opt/semgrep/bin/semgrep /usr/local/bin/semgrep

# Install opencode v2 CLI (legacy `opencode-ai` npm line stopped at 1.19.5;
# the actively published package is @opencode/cli). Always the LATEST release (no pin).
# Docker caches this layer: bump OPENCODE_REFRESH (or --build-arg OPENCODE_REFRESH=$(date +%s))
# to re-resolve it.
# Compatibility since the bump: `opencode run --model`, `opencode models` and
# `opencode.json` config shape are unchanged in v2.
# The package ships one ~240 MB native binary per libc/CPU flavour (glibc, musl, baseline);
# this image is glibc, so drop the unused variants in the same layer (~720 MB smaller).
# Node itself stays: build_check/conflict_resolver run npm inside PR clones.
# Installed with Bun (already in the base image): the global bin lands in /usr/local/bin,
# and bun blocks the postinstall that selects the native binary, so trust it explicitly.
ARG OPENCODE_REFRESH=1
RUN export BUN_INSTALL=/usr/local \
    && bun install -g @opencode/cli@latest \
    && bun pm -g trust @opencode/cli \
    && cd "$BUN_INSTALL/install/global/node_modules/@opencode" \
    && rm -rf ./cli-*-musl ./cli-*-baseline ./cli-*-baseline-musl \
    && rm -rf "$BUN_INSTALL/install/cache" \
    && opencode --version

# tokenix: local code index exposed to opencode as an MCP server (fewer tokens spent
# reading files). Always the LATEST release (releases/latest), arch-aware, sha256-verified
# against that release's sha256sums.txt. Docker caches this layer: bump TOKENIX_REFRESH
# (or build with --no-cache / --build-arg TOKENIX_REFRESH=$(date +%s)) to re-resolve latest.
# Fail-open at runtime (TOKENIX_ENABLED, missing binary, index failure all fall back to plain opencode).
ARG TOKENIX_REFRESH=1
RUN arch="$(dpkg --print-architecture)" \
    && case "$arch" in amd64) asset=tokenix-linux-x86_64 ;; arm64) asset=tokenix-linux-aarch64 ;; *) echo "unsupported arch $arch" >&2; exit 1 ;; esac \
    && base="https://github.com/juninmd/tokenix/releases/latest/download" \
    && curl -fsSL "$base/$asset" -o /usr/local/bin/tokenix \
    && curl -fsSL "$base/sha256sums.txt" | grep " $asset\$" | sed "s| $asset| /usr/local/bin/tokenix|" | sha256sum -c - \
    && chmod +x /usr/local/bin/tokenix \
    && tokenix --version

WORKDIR /app

# Install dependencies first for caching
COPY ts/package.json ts/bun.lock ./ts/
RUN cd ts && bun install --frozen-lockfile --production

# Project (Bun runs TypeScript directly: no build step)
COPY ts ./ts
COPY config ./config
COPY .env.example ./.env.example

# Non-root user (the bun image ships uid 1000 as "bun"; keep the historical name)
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app

# Advisory code-review skills + global AGENTS.md from the LATEST default branch of
# juninmd/skills, plus the cluster LiteLLM provider. opencode auto-loads
# ~/.config/opencode/skills/<name> and ~/.config/opencode/opencode.json.
# Docker caches this layer: bump SKILLS_REFRESH (or --build-arg SKILLS_REFRESH=$(date +%s))
# to re-resolve the newest commit.
ARG SKILLS_REFRESH=1
RUN git clone --depth 1 https://github.com/juninmd/skills /tmp/skills \
    && mkdir -p /home/appuser/.config/opencode/skills \
    && cp -R /tmp/skills/.agents/skills/. /home/appuser/.config/opencode/skills/ \
    && cp /tmp/skills/.agents/AGENTS.md /home/appuser/.config/opencode/AGENTS.md \
    && rm -rf /tmp/skills \
    && mkdir -p /home/appuser/.config/opencode/agents \
    && cp /app/config/opencode-agents/*.md /home/appuser/.config/opencode/agents/ \
    && cp /app/config/opencode.json /home/appuser/.config/opencode/opencode.json \
    && chown -R appuser:appuser /home/appuser/.config

USER appuser
# cwd stays /app so relative defaults (config/*.json, data/) resolve like in the Python image

ENV OLLAMA_HOST="http://ollama.ai.svc.cluster.local:11434"
ENV NODE_ENV="production"

# tini as PID 1 reaps any process orphaned inside the container (git/node helpers outliving a killed parent).
# Only meaningful when the image runs the webhook server (port 8080); batch agent runs exit before the first probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD bun -e "const r = await fetch('http://127.0.0.1:8080/health/live', {signal: AbortSignal.timeout(3000)}); process.exit(r.ok ? 0 : 1)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "-g", "--"]

# Default command (same as the Python image: `run-agent pr-assistant`)
CMD ["bun", "ts/src/cli/run-agent.ts", "pr-assistant"]
