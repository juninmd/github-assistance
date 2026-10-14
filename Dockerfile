FROM ghcr.io/gitleaks/gitleaks:latest AS gitleaks

FROM python:3.13-slim

# Copy gitleaks binary (platform-native — avoids hardcoded x86_64 tarball)
COPY --from=gitleaks /usr/bin/gitleaks /usr/local/bin/gitleaks

# Install system dependencies + Node.js LTS
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    tini \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install opencode globally
RUN npm install -g opencode-ai@latest

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5.21 /uv /uvbin/uv
ENV PATH="/uvbin:${PATH}"

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Copy from the cache instead of linking since it's a separate volume
ENV UV_LINK_MODE=copy
# uv's managed CPython otherwise installs under /root/.local/share/uv (0700,
# root-only), which the non-root appuser below can never reach through the
# venv's python3 symlink. Keep it under /app so the chown further down covers it.
ENV UV_PYTHON_INSTALL_DIR=/app/.uv-python

# Install dependencies first for caching
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy the project
COPY . .

# Install the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Create non-root user and fix permissions
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod -R u+x /app/.venv/bin

# Advisory code-review skills + cluster LiteLLM provider. opencode auto-loads
# ~/.config/opencode/skills/<name> and ~/.config/opencode/opencode.json.
ARG SKILLS_REF=9788821bae9d5028cc061ed66dc9e99f71963ed6
RUN git clone --filter=blob:none --no-checkout https://github.com/juninmd/skills /tmp/skills \
    && git -C /tmp/skills fetch --depth 1 origin "${SKILLS_REF}" \
    && git -C /tmp/skills checkout --quiet FETCH_HEAD \
    && mkdir -p /home/appuser/.config/opencode/skills \
    && cp -R /tmp/skills/.agents/skills/. /home/appuser/.config/opencode/skills/ \
    && rm -rf /tmp/skills \
    && cp /app/config/opencode.json /home/appuser/.config/opencode/opencode.json \
    && chown -R appuser:appuser /home/appuser/.config

USER appuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV OLLAMA_HOST="http://ollama.ai.svc.cluster.local:11434"
ENV PYTHONUNBUFFERED="1"

# tini as PID 1: `uv` does not reap, so any process orphaned inside the container
# (git/node helpers outliving a killed parent) would pile up as zombies forever.
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]

# Default command
CMD ["uv", "run", "run-agent", "pr-assistant"]
