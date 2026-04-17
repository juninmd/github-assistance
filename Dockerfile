FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5.21 /uv /uvbin/uv
ENV PATH="/uvbin:${PATH}"

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Copy from the cache instead of linking since it's a separate volume
ENV UV_LINK_MODE=copy

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

# Create non-root user
RUN useradd -m -u 1000 appuser
USER appuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV OLLAMA_HOST="http://ollama.ai.svc.cluster.local:11434"

# Default command
CMD ["uv", "run", "run-agent", "pr-assistant"]
