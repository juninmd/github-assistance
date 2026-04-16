FROM python:3.12-slim

# The installer requires curl (and certificates) to download the release archive
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

# Download the latest installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin/:$PATH"

# Set the working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv sync (frozen ensures it perfectly matches uv.lock)
RUN uv sync --frozen

# Copy the rest of the application code
COPY . .

# Set PYTHONPATH so the src module is found correctly
ENV PYTHONPATH="/app"

# Command to run PR assistant
CMD ["uv", "run", "run-agent", "pr-assistant"]
