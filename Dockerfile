FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    psmisc \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x bin/swarm-studio bin/qwen_oracle.sh scripts/*.sh

EXPOSE 8080

ENV SWARM_PORT=8080
ENV SWARM_HOST=0.0.0.0

CMD ["python3", "bin/swarm-studio"]
