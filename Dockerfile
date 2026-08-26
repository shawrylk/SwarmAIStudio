FROM python:3.12-slim

WORKDIR /app

# System deps: git for the GitHub Desktop suite + autonomous loop commits,
# curl for the container healthcheck, psmisc/procps for process helpers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    psmisc \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching.
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# App source.
COPY . .
RUN chmod +x bin/swarm bin/qwen_oracle.sh scripts/*.sh

# The autonomous loop makes real git commits; git refuses without an identity
# and treats bind-mounted repos owned by another uid as "dubious". Set sane
# container defaults (override at runtime if you like).
RUN git config --system user.name  "Swarm AI Studio" \
 && git config --system user.email "swarm@localhost" \
 && git config --system --add safe.directory '*'

EXPOSE 8080

ENV SWARM_PORT=8080 \
    SWARM_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8080/api/repos || exit 1

CMD ["python3", "bin/swarm", "web"]
