---
title: "GitLab Integration"
sidebar_position: 5
---

## Merge request diff limits

PR-Agent requires GitLab 15.7 or later and retrieves all pages from the merge request
[`/diffs` endpoint](https://docs.gitlab.com/api/merge_requests/#list-merge-request-diffs).
Pagination does not bypass GitLab's server-side diff limits. PR-Agent raises a provider
error if the returned file count disagrees with an exact `changes_count`, or that count
indicates overflow or is not ready. A file whose patch GitLab omits (`too_large`, or
`collapsed` before GitLab 19.2) is diffed locally from its two revisions instead.

The `/diffs` endpoint must be available. PR-Agent does not fall back to the deprecated
`/changes` endpoint or its raw-diff retry.

PR-Agent reads fresh merge request metadata before and after collecting the diff pages.
If the revision or file count changes during collection, it retries once, then raises a
provider error if they change again. Non-empty results also require usable base/head
references for loading file content. If the merge request moves after incremental
setup, PR-Agent falls back to a full review instead of mixing revisions.

## Optional submodule diff expansion

When `GITLAB.EXPAND_SUBMODULE_DIFFS` is enabled, PR-Agent compares submodule commits
to add child-file patches. If the comparison times out or a child patch is omitted
(`collapsed` or `too_large`), it logs a warning and skips that optional expansion.
The parent submodule gitlink remains in the merge request diff. This repository
comparison fallback is separate from the merge-request `/diffs` behavior above.

## Run as a GitLab Pipeline

You can use a pre-built Action Docker image to run PR-Agent as a GitLab pipeline. This is a simple way to get started with PR-Agent without setting up your own server.

Pipeline mode runs configured commands automatically when GitLab creates a merge request pipeline. It does not receive GitLab comment events. If you want users to invoke commands such as `/review` or `/improve` in merge request comments, deploy the [GitLab webhook server](#run-a-gitlab-webhook-server) instead and enable the **Comments** webhook trigger.

(1) Add the following file to your repository under `.gitlab-ci.yml`:

```yaml
stages:
  - pr_agent

pr_agent_job:
  stage: pr_agent
  image:
    name: pragent/pr-agent:latest
    entrypoint: [""]
  script:
    - cd /app
    - echo "Running PR Agent action step"
    - export MR_URL="$CI_MERGE_REQUEST_PROJECT_URL/merge_requests/$CI_MERGE_REQUEST_IID"
    - echo "MR_URL=$MR_URL"
    - export gitlab__url=$CI_SERVER_PROTOCOL://$CI_SERVER_FQDN
    - export gitlab__PERSONAL_ACCESS_TOKEN=$GITLAB_PERSONAL_ACCESS_TOKEN
    - export config__git_provider="gitlab"
    - export openai__key=$OPENAI_KEY
    - python -m pr_agent.cli --pr_url="$MR_URL" describe
    - python -m pr_agent.cli --pr_url="$MR_URL" review
    - python -m pr_agent.cli --pr_url="$MR_URL" improve
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
```

This script runs PR-Agent when a merge request pipeline is created, including when a merge request is opened and when new commits are pushed to its source branch. You can modify the `rules` section to run PR-Agent on different events.
You can also modify the `script` section to run different PR-Agent commands, or with different parameters by exporting different environment variables.

### CI artifact context

A file produced by an earlier job — a test report, a coverage summary, a linter or SAST output — can be handed to `/review`, `/describe` and `/improve` as extra context, so the model reviews the merge request with your pipeline's own findings in hand. Save the file as a job artifact, make the PR-Agent job depend on that job with `needs:`, and point PR-Agent at it with `ARTIFACT_PATH`. The job above runs from `/app`, so give the path in full:

```yaml
pr_agent_job:
  stage: pr_agent
  needs: ["test_job"]
  image:
    name: pragent/pr-agent:latest
    entrypoint: [""]
  script:
    - cd /app
    - export ARTIFACT_PATH="$CI_PROJECT_DIR/reports/pytest.xml"
    - export ARTIFACT_INSTRUCTIONS="These are the failing tests from this MR's pipeline. Call out any suggestion that would not fix them."
    - python -m pr_agent.cli --pr_url="$MR_URL" review
```

Setting `ARTIFACT_PATH` turns the feature on by itself. The remaining knobs — which tools receive the context, the label, the size limit — are the `[artifacts]` settings described under [CI artifact context](./github.md#ci-artifact-context) for the GitHub Action, and they apply to the CLI in the same way.

### Ignore bot-created merge requests

Dependency update bots usually use predictable source branch prefixes. Add a higher-priority `when: never` rule before the general merge request rule to skip those branches:

```yaml
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_SOURCE_BRANCH_NAME =~ /^(dependabot|renovate)\//'
      when: never
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
```

Adjust the regular expression to match the branch naming conventions used by your bots. Filtering on `CI_MERGE_REQUEST_SOURCE_BRANCH_NAME` is more reliable than `GITLAB_USER_LOGIN`, because `GITLAB_USER_LOGIN` identifies the user who started the pipeline and can change when a pipeline is run manually.

The webhook server can apply the equivalent filter to automatic merge request events through a repository-level `.pr_agent.toml` file:

```toml
[config]
ignore_pr_source_branches = ["^(dependabot|renovate)/"]
```

For all supported filters, see [Ignoring automatic commands in PRs](../usage-guide/additional_configurations.md#ignoring-automatic-commands-in-prs).

(2) Add the following masked variables to your GitLab repository (CI/CD -> Variables):

- `GITLAB_PERSONAL_ACCESS_TOKEN`: Your GitLab personal access token.

- `OPENAI_KEY`: Your OpenAI key.

Note that if your base branches are not protected, don't set the variables as `protected`, since the pipeline will not have access to them.

If your model gateway only accepts requests from a Claude Code client, see [Send completions through Claude Code](#send-completions-through-claude-code) instead of setting `OPENAI_KEY`.

> **Note**: The `$CI_SERVER_FQDN` variable is available starting from GitLab version 16.10. If you're using an earlier version, this variable will not be available. However, you can combine `$CI_SERVER_HOST` and `$CI_SERVER_PORT` to achieve the same result. Please ensure you're using a compatible version or adjust your configuration.

> **Note**: The `gitlab__SSL_VERIFY` environment variable can be used to specify the path to a custom CA certificate bundle for SSL verification. GitLab exposes the `$CI_SERVER_TLS_CA_FILE` variable, which points to the custom CA certificate file configured in your GitLab instance.
> Alternatively, SSL verification can be disabled entirely by setting `gitlab__SSL_VERIFY=false`, although this is not recommended.
> This setting affects only the GitLab API client. For certificate issues with LLM calls or git clone operations, see [Custom CA and Self-Signed Certificates](../usage-guide/custom_ca_and_self_signed_certificates.md).

## Run a GitLab webhook server

1. In GitLab create a new user and give it "Developer" role for the intended group or project.
   > **Note:** "Reporter" role is sufficient for adding comments for `/improve` or `/review` for example,
   > but "Developer" role is required to update the Merge Request description when using the `/describe` command.

2. For the user from step 1, generate a `personal_access_token` with `api` access.

3. Generate a random secret for your app, and save it for later (`shared_secret`). For example, you can use:

```bash
SHARED_SECRET=$(python -c "import secrets; print(secrets.token_hex(10))")
```

4. Clone this repository:

```bash
git clone https://github.com/the-pr-agent/pr-agent.git
```

5. Prepare variables and secrets. Skip this step if you plan on setting these as environment variables when running the agent:
    1. In the configuration file/variables:
        - Set `config.git_provider` to "gitlab"

    2. In the secrets file/variables:
        - Set your AI model key in the respective section
        - In the [gitlab] section, set `personal_access_token` (with token from step 2) and `shared_secret` (with secret from step 3)
        - **Authentication type**: Set `auth_type` to `"private_token"` to send the token in the `PRIVATE-TOKEN` header, or use the default `"oauth_token"` for the `Authorization: Bearer` header. Both are supported on GitLab.com and self-managed instances.

6. Build a Docker image for the app and optionally push it to a Docker repository. We'll use Dockerhub as an example:

```bash
docker build . -t pr-agent:gitlab_webhook --target gitlab_webhook -f docker/Dockerfile

# Optional, to push it to your own Docker repository:
docker tag pr-agent:gitlab_webhook <your-registry>/pr-agent:gitlab_webhook
docker push <your-registry>/pr-agent:gitlab_webhook
```

7. Set the environmental variables, the method depends on your docker runtime. Skip this step if you included your secrets/configuration directly in the Docker image.

```bash
CONFIG__GIT_PROVIDER=gitlab
GITLAB__PERSONAL_ACCESS_TOKEN=<personal_access_token>
GITLAB__SHARED_SECRET=<shared_secret>
GITLAB__URL=https://gitlab.com
GITLAB__AUTH_TYPE=oauth_token  # Use "private_token" for the PRIVATE-TOKEN header
OPENAI__KEY=<your_openai_api_key>
PORT=3000  # Optional: override the webhook server port
```

8. Create a webhook in your GitLab project. Set the URL to `http[s]://<PR_AGENT_HOSTNAME>/webhook`, the secret token to the generated secret from step 3, and enable the triggers `push`, `comments` and `merge request events`.

9. Test your installation by opening a merge request or commenting on a merge request using one of PR Agent's commands.

10. The webhook server runs under gunicorn with multiple worker processes. See [Sizing a self-hosted webhook server](./index.md#sizing-a-self-hosted-webhook-server) for the `GUNICORN_WORKERS` / `GUNICORN_MAX_WORKERS` knobs and memory guidance — worth reading before setting a memory limit.

## Send completions through Claude Code

Some model gateways accept requests only from a genuine [Claude Code](https://code.claude.com/docs) client, so PR-Agent cannot call the model API directly. With `config.ai_handler="claude_code"`, every AI call runs the Claude Code CLI instead. The CLI loads your `settings.json` (gateway URL, token, model) and sends the request itself. All Claude Code tools are disabled, so the model receives exactly the prompt PR-Agent built, as with a direct API call.

This works for both the pipeline and the webhook server.

### Build the image

The `gitlab_claude_code` Docker target contains PR-Agent and a pinned Claude Code CLI, and selects `config.ai_handler="claude_code"`. Build it and push it to a registry your GitLab can pull from:

```bash
docker build -f docker/Dockerfile --target gitlab_claude_code -t registry.example.com/pr-agent:gitlab-claude-code .
docker push registry.example.com/pr-agent:gitlab-claude-code
```

Add `--build-arg CLAUDE_CODE_VERSION=<version>` to pin a different CLI release, and `--platform linux/amd64` when building on an ARM machine for x86 runners.

To build inside a network with a TLS-inspecting proxy, place the proxy's CA certificate (PEM, `.crt` or `.pem`) in `docker/ca-certificates/` and pass the proxy to the build. The certificate is then trusted by every download in the build and, at runtime, by PR-Agent and the Claude Code CLI:

```bash
cp corporate-ca.crt docker/ca-certificates/
docker build -f docker/Dockerfile --target gitlab_claude_code \
  --build-arg HTTP_PROXY=http://proxy.example.com:8080 --build-arg HTTPS_PROXY=http://proxy.example.com:8080 \
  -t registry.example.com/pr-agent:gitlab-claude-code .
```

The Docker daemon pulls base images itself, so it must trust the same CA. Alternatively, build outside the internal network and bring the image in with `docker save` and `docker load`, then push it to the internal registry.

### The settings file

Claude Code reads the gateway address and credentials from its `settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://llm-gateway.example.com",
    "ANTHROPIC_AUTH_TOKEN": "<gateway token>"
  },
  "model": "<model name your gateway serves>"
}
```

`ANTHROPIC_AUTH_TOKEN` is sent as `Authorization: Bearer`; use `ANTHROPIC_API_KEY` instead if your gateway expects an `x-api-key` header. The model comes from this file (or from `claude_code.model`); `config.model` is not forwarded to the CLI.

The image reads the file from `/etc/claude-code/settings.json`. To read it from another path, set the `CLAUDE_CODE__SETTINGS_FILE` environment variable. Write the name in upper case: the image already sets it, and a lower-case `claude_code__settings_file` does not override it. All `[claude_code]` options are listed in the [configuration reference](../usage-guide/configuration_reference.md#claude_code).

### Custom CA certificates

If the gateway's certificate is signed by a private CA, or a TLS-inspecting proxy sits in between, make the CA bundle (PEM) available in the container and point `SSL_CERT_FILE` at it, as described in [Custom CA and Self-Signed Certificates](../usage-guide/custom_ca_and_self_signed_certificates.md). The Claude Code CLI ignores `SSL_CERT_FILE` and reads only `NODE_EXTRA_CA_CERTS`, so PR-Agent passes the same bundle to it under that name. To give the CLI a different bundle, set `NODE_EXTRA_CA_CERTS` yourself, in the environment or in the `env` block of `settings.json`.

In Kubernetes or OpenShift, keep the bundle in a ConfigMap and mount it:

```yaml
# Deployment container
env:
  - name: SSL_CERT_FILE
    value: /etc/pr-agent-ca/ca-bundle.crt
volumeMounts:
  - name: ca-bundle
    mountPath: /etc/pr-agent-ca
    readOnly: true
# Deployment pod spec
volumes:
  - name: ca-bundle
    configMap:
      name: corporate-ca-bundle   # kubectl create configmap corporate-ca-bundle --from-file=ca-bundle.crt
```

### In a pipeline

(1) In CI/CD -> Variables, add a variable of type **File** with the key `CLAUDE_CODE__SETTINGS_FILE`, and paste the content of your `settings.json` as its value. GitLab writes the content to a temporary file and puts that file's path in the variable, so the image picks it up without any script step. File variables cannot be masked, so never print the file in the job.

(2) Add the `GITLAB_PERSONAL_ACCESS_TOKEN` masked variable, as for the standard pipeline.

(3) Use the image in `.gitlab-ci.yml`:

```yaml
stages:
  - pr_agent

pr_agent_job:
  stage: pr_agent
  image:
    name: registry.example.com/pr-agent:gitlab-claude-code
    entrypoint: [""]
  script:
    - cd /app
    - export MR_URL="$CI_MERGE_REQUEST_PROJECT_URL/merge_requests/$CI_MERGE_REQUEST_IID"
    - export gitlab__url=$CI_SERVER_PROTOCOL://$CI_SERVER_FQDN
    - export gitlab__PERSONAL_ACCESS_TOKEN=$GITLAB_PERSONAL_ACCESS_TOKEN
    - export config__git_provider="gitlab"
    - python -m pr_agent.cli --pr_url="$MR_URL" describe
    - python -m pr_agent.cli --pr_url="$MR_URL" review
    - python -m pr_agent.cli --pr_url="$MR_URL" improve
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
```

### With the webhook server

Ready-to-use deployments are in `docker/gitlab_claude_code/`. Each needs the same three inputs, as for the [standard webhook server](#run-a-gitlab-webhook-server): the GitLab URL, a personal access token with `api` scope, and the webhook shared secret. The `settings.json` file is the fourth input. Each gunicorn worker runs up to `claude_code.max_concurrent_calls` (default 4) CLI processes at once; the examples set `GUNICORN_WORKERS=2`.

After deploying, create the GitLab webhook as in step 8 of the standard webhook server, pointing at `https://<host>/webhook`.

<details>
<summary>Docker Compose</summary>

```bash
cd docker/gitlab_claude_code
cp settings.json.example settings.json   # fill in the gateway URL, token and model
cp pr-agent.env.example pr-agent.env     # fill in the GitLab URL, token and shared secret
chmod 644 settings.json                  # the container runs as UID 10001 and must read it
PR_AGENT_IMAGE=registry.example.com/pr-agent:gitlab-claude-code docker compose up -d
```

The server listens on port 3000 (`PR_AGENT_PORT` changes it); put a TLS-terminating reverse proxy in front of it. The filled-in `settings.json` and `pr-agent.env` are git-ignored.

</details>

<details>
<summary>Kubernetes</summary>

Create the two Secrets the manifest reads:

```bash
kubectl create secret generic pr-agent-claude-code-settings --from-file=settings.json=./settings.json
kubectl create secret generic pr-agent-gitlab \
  --from-literal=GITLAB__PERSONAL_ACCESS_TOKEN=<personal access token> \
  --from-literal=GITLAB__SHARED_SECRET=<shared secret>
```

In `docker/gitlab_claude_code/kubernetes.yaml`, set the image, `GITLAB__URL`, the Ingress class and host, and the TLS Secret, then apply it:

```bash
kubectl apply -f docker/gitlab_claude_code/kubernetes.yaml
```

The pod runs as a non-root user with a read-only root file system; the CLI's state and per-call files go to `emptyDir` volumes. After you update the settings Secret, run `kubectl rollout restart deployment/pr-agent` so the new file is used everywhere at once.

</details>

<details>
<summary>OpenShift</summary>

Create the same two Secrets with `oc`:

```bash
oc create secret generic pr-agent-claude-code-settings --from-file=settings.json=./settings.json
oc create secret generic pr-agent-gitlab \
  --from-literal=GITLAB__PERSONAL_ACCESS_TOKEN=<personal access token> \
  --from-literal=GITLAB__SHARED_SECRET=<shared secret>
```

In `docker/gitlab_claude_code/openshift.yaml`, set the image and `GITLAB__URL`, then apply it:

```bash
oc apply -f docker/gitlab_claude_code/openshift.yaml
oc get route pr-agent -o jsonpath='{.spec.host}'   # the host for the GitLab webhook URL
```

The manifest sets no UID: the `restricted` SCC assigns an arbitrary one, which the image supports. The Route terminates TLS at the router.

</details>

## Deploy as a Lambda Function

Note that since AWS Lambda env vars cannot have "." in the name, you can replace each "." in an env variable with "__".<br>
For example: `GITLAB.PERSONAL_ACCESS_TOKEN` --> `GITLAB__PERSONAL_ACCESS_TOKEN`

1. Follow steps 1-5 from [Run a GitLab webhook server](#run-a-gitlab-webhook-server).
2. Build a docker image that can be used as a lambda function

    ```shell
    docker buildx build --platform=linux/amd64 . -t pr-agent:gitlab_lambda --target gitlab_lambda -f docker/Dockerfile.lambda
   ```

3. Push image to ECR

    ```shell
    docker tag pr-agent:gitlab_lambda <AWS_ACCOUNT>.dkr.ecr.<AWS_REGION>.amazonaws.com/pr-agent:gitlab_lambda
    docker push <AWS_ACCOUNT>.dkr.ecr.<AWS_REGION>.amazonaws.com/pr-agent:gitlab_lambda
    ```

4. Create a lambda function that uses the uploaded image. Set the lambda timeout to be at least 3m.
5. Configure the lambda function to have a Function URL.
6. In the environment variables of the Lambda function, specify `AZURE_DEVOPS_CACHE_DIR` to a writable location such as /tmp. (see [link](https://github.com/the-pr-agent/pr-agent/pull/450#issuecomment-1840242269))
7. Go back to steps 8-9 of [Run a GitLab webhook server](#run-a-gitlab-webhook-server) with the function URL as your Webhook URL.
    The Webhook URL would look like `https://<LAMBDA_FUNCTION_URL>/webhook`

### Using AWS Secrets Manager

For production Lambda deployments, use AWS Secrets Manager instead of environment variables:

1. Create individual secrets for each GitLab webhook with this JSON format (e.g., secret name: `project-webhook-secret-001`)

```json
{
  "gitlab_token": "glpat-xxxxxxxxxxxxxxxxxxxxxxxx",
  "token_name": "project-webhook-001"
}
```

2. Create a main configuration secret for common settings (e.g., secret name: `pr-agent-main-config`)

```json
{
  "openai.key": "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

3. Set these environment variables in your Lambda:

```bash
CONFIG__SECRET_PROVIDER=aws_secrets_manager
AWS_SECRETS_MANAGER__SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:pr-agent-main-config-AbCdEf
```

4. In your GitLab webhook configuration, set the **Secret Token** to the **Secret name** created in step 1:
   - Example: `project-webhook-secret-001`

**Important**: When using Secrets Manager, GitLab's webhook secret must be the Secrets Manager secret name.

5. Add IAM permission `secretsmanager:GetSecretValue` to your Lambda execution role
