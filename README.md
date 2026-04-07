# Claude Code Tracing

Intercept and log all LLM API calls made by Claude Code using a LiteLLM proxy with a custom JSONL logger.

## Prerequisites

- Python 3.10+
- An Anthropic API key
- Claude Code CLI installed

## Setup

### 1. Local setup

#### 1.1. Create project and install dependencies

```bash
mkdir ~/claude-code-tracing && cd ~/claude-code-tracing
python3 -m venv .venv
source .venv/bin/activate
pip install 'litellm[proxy]'
```

#### 1.2. Create `custom_callbacks.py`

```python
from litellm.integrations.custom_logger import CustomLogger
import json, datetime, os

LOG_FILE = os.path.join(os.path.dirname(__file__), "traces.jsonl")

class JSONLLogger(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "model": kwargs.get("model", ""),
                "messages": kwargs.get("messages", []),
                "response": response_obj.model_dump() if hasattr(response_obj, "model_dump") else str(response_obj),
                "start_time": str(start_time),
                "end_time": str(end_time),
                "input_tokens": response_obj.usage.prompt_tokens if hasattr(response_obj, "usage") and response_obj.usage else None,
                "output_tokens": response_obj.usage.completion_tokens if hasattr(response_obj, "usage") and response_obj.usage else None,
            }
            complete_input = kwargs.get("additional_args", {}).get("complete_input_dict", None)
            if complete_input:
                entry["raw_request"] = complete_input
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            print(f"JSONLLogger error: {e}")

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        try:
            entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "model": kwargs.get("model", ""),
                "messages": kwargs.get("messages", []),
                "error": str(response_obj),
                "status": "failure",
            }
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            print(f"JSONLLogger error: {e}")

proxy_handler_instance = JSONLLogger()
```

#### 1.3. Create `config.yaml`

```yaml
model_list:
  - model_name: claude-sonnet-4-6
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: claude-haiku-4-5
    litellm_params:
      model: anthropic/claude-haiku-4-5-20251001
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: claude-haiku-4-5-20251001
    litellm_params:
      model: anthropic/claude-haiku-4-5-20251001
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: claude-opus-4-6
    litellm_params:
      model: anthropic/claude-opus-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

litellm_settings:
  callbacks: custom_callbacks.proxy_handler_instance
```

#### 1.4. Set environment variables

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
export LITELLM_MASTER_KEY="sk-my-litellm-key"  # any string you choose
```

#### 1.5. Start the proxy

```bash
cd ~/claude-code-tracing
litellm --config config.yaml
# Proxy runs on http://0.0.0.0:4000
```

#### 1.6. Point Claude Code at the proxy

In a separate terminal:

```bash
export ANTHROPIC_BASE_URL="http://0.0.0.0:4000"
export ANTHROPIC_AUTH_TOKEN="sk-my-litellm-key"
claude
```

All Claude Code requests now flow through the proxy and are logged to `traces.jsonl`.

#### What Gets Captured

Each line in `traces.jsonl` is a JSON object containing:

| Field | Description |
|---|---|
| `timestamp` | When the log entry was written |
| `model` | Which Claude model was called |
| `messages` | Full conversation messages array (the prompt) |
| `response` | Complete model response object |
| `start_time` / `end_time` | Request timing for latency measurement |
| `input_tokens` / `output_tokens` | Token usage |
| `raw_request` | Complete input dict sent to the provider (system prompt, tools, etc.) |
| `error` | Error message (failure entries only) |
| `status` | Set to `"failure"` for failed requests |

#### Verify

```bash
# Check number of logged calls
wc -l traces.jsonl

# Pretty-print the first entry
head -1 traces.jsonl | python3 -m json.tool
```

## 2.Docker Setup (for DGX Spark / cloud servers)

If you can only run Docker on your server, use the provided `docker/` setup which packages everything into two containers.

#### File structure

```
docker/
├── docker-compose.yml
├── .env.example
├── proxy/
│   ├── Dockerfile
│   ├── config.yaml
│   └── custom_callbacks.py
└── claude/
    └── Dockerfile
```

#### 2.1. Configure your API key

```bash
cd docker/
cp .env.example .env
# Edit .env and set your real ANTHROPIC_API_KEY
```

#### 2.2. Build and start

```bash
docker compose up -d --build
```

This starts two containers:
- **`litellm-proxy`** — the LiteLLM proxy on port 4000, logging to `/data/traces.jsonl`
- **`claude-code`** — a container with Claude Code CLI pre-installed, already pointed at the proxy

#### 2.3. Run Claude Code

**Interactive mode:**

```bash
docker exec -it claude-code claude
```

**Headless mode (for automation):**

```bash
docker exec claude-code claude -p "your prompt here"
```

**Headless + Yolo (fully autonomous):**

```bash
docker exec claude-code claude --dangerously-skip-permissions -p "your prompt here"
```

#### 2.4. Clone a repo into the workspace

```bash
docker exec claude-code git clone https://github.com/some/repo.git /workspace/repo
docker exec -it -w /workspace/repo claude-code claude
```

#### 2.5. Read traces

Traces are written to a shared Docker volume. Read them from either container:

```bash
# From the claude container
docker exec claude-code cat /data/traces.jsonl

# Or copy to your host
docker cp claude-code:/data/traces.jsonl ./traces.jsonl

# Count logged calls
docker exec claude-code wc -l /data/traces.jsonl
```

#### 2.6. Stop

```bash
docker compose down          # containers stop, volumes persist
docker compose down -v       # also delete trace and workspace volumes
```

#### Tips

- **Disk**: Traces grow fast (60–400+ LLM calls per task). Periodically copy and truncate:
  ```bash
  docker cp claude-code:/data/traces.jsonl "./traces_$(date +%Y%m%d).jsonl"
  docker exec claude-code truncate -s 0 /data/traces.jsonl
  ```
- **Debug proxy**: `docker compose logs -f litellm-proxy`
- **Proxy accessible from host**: The proxy is exposed on port 4000, so you can also point a local Claude Code at `http://<dgx-ip>:4000` if needed.

## Acknowledgement

- [Claude Code](https://claude.ai/code) by [Anthropic](https://www.anthropic.com/) — the AI coding agent whose API calls this project intercepts and traces.
- [LiteLLM](https://github.com/BerriAI/litellm) by BerriAI — the LLM proxy that makes transparent request interception possible.
- [LMCache](https://github.com/LMCache/LMCache) — the KV cache engine for large language models. Special thanks to the original author [Kobe Chen](https://github.com/KobeGong) for his blog on [claude-code-tracing](https://github.com/kobe0938/claude-code-tracing)
- [SWE-bench Pro](https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro) by Scale AI and [SWE-bench](https://www.swebench.com/) by Princeton NLP — the software engineering benchmarks used in our tracing experiments.

