# barney base image: Python, git, AWS CLI, barney itself.
# Build from the repo root:  docker build -f images/base/Dockerfile -t barney .
FROM python:3.12-slim

ARG TARGETARCH
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 GIT_TERMINAL_PROMPT=0

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates unzip build-essential \
 && rm -rf /var/lib/apt/lists/*

# AWS CLI v2 (handy for debugging inside the container; boto3 does the real work)
RUN arch=$([ "$TARGETARCH" = "arm64" ] && echo aarch64 || echo x86_64) \
 && curl -sSL "https://awscli.amazonaws.com/awscli-exe-linux-${arch}.zip" -o /tmp/awscli.zip \
 && unzip -q /tmp/awscli.zip -d /tmp && /tmp/aws/install && rm -rf /tmp/aws /tmp/awscli.zip

COPY pyproject.toml README.md /opt/barney/
COPY barney /opt/barney/barney
RUN pip install /opt/barney

# Git identity for commits the agent makes; override with -e or git config in the job.
RUN git config --system user.name "barney" \
 && git config --system user.email "barney@users.noreply.github.com" \
 && git config --system --add safe.directory '*'

WORKDIR /work
