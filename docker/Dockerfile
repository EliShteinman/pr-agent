FROM python:3.14.7-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

# litellm fetches its model cost map over the network at import time, so a
# third-party change to that map can change runtime behavior with no image
# change and no version bump. Use the map bundled with the litellm pinned in
# uv.lock so every stage (test and runtime) behaves how it was built and tested
# rather than tracking today's remote data; new models then arrive with a
# deliberate litellm bump in the lockfile.
ENV LITELLM_LOCAL_MODEL_COST_MAP=True

RUN apt-get update && apt-get install --no-install-recommends -y git curl && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
COPY docs docs
RUN uv sync --frozen --no-install-project --no-dev
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

FROM base AS github_app
COPY pr_agent pr_agent
CMD ["python", "-m", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "pr_agent/servers/gunicorn_config.py", "--forwarded-allow-ips", "*", "pr_agent.servers.github_app:app"]

FROM base AS bitbucket_app
COPY pr_agent pr_agent
CMD ["python", "pr_agent/servers/bitbucket_app.py"]

FROM base AS bitbucket_server_webhook
COPY pr_agent pr_agent
CMD ["python", "pr_agent/servers/bitbucket_server_webhook.py"]

FROM base AS github_polling
COPY pr_agent pr_agent
CMD ["python", "pr_agent/servers/github_polling.py"]

FROM base AS github_action
COPY pr_agent pr_agent
COPY github_action/entrypoint.sh /
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

FROM base AS gitlab_webhook
COPY pr_agent pr_agent
CMD ["python", "-m", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "pr_agent/servers/gunicorn_config.py", "--forwarded-allow-ips", "*", "pr_agent.servers.gitlab_webhook:app"]

# GitLab with completions sent through the Claude Code CLI (config.ai_handler="claude_code"), for
# gateways that only accept a Claude Code client. One image serves both GitLab modes: run it as is
# for the webhook server, or use it as a pipeline job image (entrypoint [""], then
# `python -m pr_agent.cli ...`). Mount the operator's settings.json at the path below, or point
# claude_code__settings_file at another one.
FROM base AS gitlab_claude_code
# Pinned so a rebuild cannot silently change the CLI; override with --build-arg CLAUDE_CODE_VERSION=x.y.z.
ARG CLAUDE_CODE_VERSION=2.1.319
ARG TARGETARCH
# The upstream install.sh resolves "latest" and installs into one user's ~/.local. Fetch the
# pinned zstd build instead, verify it against the release manifest's checksum, and install it
# where any UID can run it.
RUN set -eux; \
    apt-get update && apt-get install --no-install-recommends -y zstd && apt-get clean && rm -rf /var/lib/apt/lists/*; \
    case "${TARGETARCH:-amd64}" in \
      amd64) platform="linux-x64" ;; \
      arm64) platform="linux-arm64" ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    release="https://downloads.claude.ai/claude-code-releases/${CLAUDE_CODE_VERSION}"; \
    fetch() { curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors -o "$2" "$1"; }; \
    fetch "${release}/manifest.zst.json" /tmp/manifest.json; \
    checksum="$(python -c "import json,sys; print(json.load(open('/tmp/manifest.json'))['platforms'][sys.argv[1]]['checksum'])" "${platform}")"; \
    fetch "${release}/${platform}/claude.zst" /tmp/claude.zst; \
    echo "${checksum}  /tmp/claude.zst" | sha256sum -c -; \
    zstd -d -q /tmp/claude.zst -o /usr/local/bin/claude; \
    chmod 0755 /usr/local/bin/claude; \
    rm -f /tmp/claude.zst /tmp/manifest.json; \
    claude --version
# The CLI writes state under $HOME on every run. Platforms such as OpenShift or a Kubernetes
# GitLab runner start the container under an arbitrary UID in group 0, so HOME is group-writable.
ENV HOME=/home/claude-code
RUN mkdir -p "${HOME}" && chgrp 0 "${HOME}" && chmod 0775 "${HOME}"
# A container must not update its own CLI, and a gateway-only network has no route for telemetry.
ENV DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    CONFIG__AI_HANDLER=claude_code \
    CLAUDE_CODE__SETTINGS_FILE=/etc/claude-code/settings.json
COPY pr_agent pr_agent
CMD ["python", "-m", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "pr_agent/servers/gunicorn_config.py", "--forwarded-allow-ips", "*", "pr_agent.servers.gitlab_webhook:app"]

FROM base AS azure_devops_webhook
COPY pr_agent pr_agent
CMD ["python", "pr_agent/servers/azuredevops_server_webhook.py"]

FROM base AS gitea_app
COPY pr_agent pr_agent
CMD ["python", "-m", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "pr_agent/servers/gunicorn_config.py","pr_agent.servers.gitea_app:app"]

FROM base AS mosaico_agent
COPY pr_agent pr_agent
EXPOSE 9000
CMD ["python", "pr_agent/mosaico/server.py"]


FROM base AS test
# The base stage pins LITELLM_LOCAL_MODEL_COST_MAP for every stage; kept here
# only as documentation that the unit suite keys off the bundled cost map.
RUN uv sync --frozen --no-install-project
COPY pr_agent pr_agent
COPY tests tests
# Config the unit suite asserts against, copied file by file so an unrelated
# workflow edit does not invalidate this layer.
COPY .github/workflows/publish.yml .github/workflows/publish.yml
COPY .github/workflows/build-and-test.yaml .github/workflows/build-and-test.yaml
COPY docker/Dockerfile docker/Dockerfile
COPY docker/Dockerfile.lambda docker/Dockerfile.lambda
COPY docker/mosaico docker/mosaico
# Read by the docs guards: the URL checker, the pages that link into the docs site,
# and the packaging inputs that must ship every /help page suffix. Kept last so a
# README edit only rebuilds these final layers.
COPY scripts/check_docs_urls.py scripts/check_docs_urls.py
COPY README.md CONTRIBUTING.md SECURITY.md ./
COPY MANIFEST.in setup.py ./

FROM base AS cli
COPY pr_agent pr_agent
RUN uv sync --frozen --no-dev && ln -s /app/.venv/bin/pr-agent /usr/local/bin/pr-agent
ENTRYPOINT ["python", "pr_agent/cli.py"]
