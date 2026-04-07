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

If you can only run Docker on your server, use the provided `docker/` setup which packages everything into three containers.

#### File structure

```
docker/
├── docker-compose.yml
├── .env.example
├── proxy/
│   ├── Dockerfile
│   ├── config.yaml
│   └── custom_callbacks.py
├── claude/
│   └── Dockerfile
└── visualizer/
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

This starts three containers:
- **`litellm-proxy`** — the LiteLLM proxy on port 4000, logging to `/logs/traces.jsonl`
- **`claude-code`** — a container with Claude Code CLI pre-installed, already pointed at the proxy
- **`visualizer`** — the trace visualizer with web UI on port 8080

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

Traces are written to `visualizer/logs/` on the host, bind-mounted at `/logs` across all containers:

```bash
# From the claude container
docker exec claude-code cat /logs/traces.jsonl

# Or copy to your host
docker cp claude-code:/logs/traces.jsonl ./traces.jsonl

# Count logged calls
docker exec claude-code wc -l /logs/traces.jsonl
```

#### 2.6. Stop

```bash
docker compose down          # containers stop, volumes persist
docker compose down -v       # also delete workspace volume (traces persist in visualizer/logs/)
```

## Visualization

The visualizer analyzes prefix caching and substring matching hit rates across LLM request sequences, and provides an interactive web UI for exploring token reuse patterns.

Trace files are stored in `visualizer/logs/`. In the Docker setup this directory is bind-mounted to all three containers; for local usage, copy your trace files there manually.

#### File structure

```
visualizer/
├── logs/                           # Trace files go here
├── prefix_analysis.py              # Core analysis engine
├── merge_matches.py                # Merge overlapping/adjacent matches
├── jsonl_to_csv.py                 # Export matches to CSV
├── combine_jsonl.py                # Combine multiple JSONL files
├── requirements.txt                # Python dependencies
├── run_analysis.sh                 # Batch analysis script
└── visualizer/
    ├── visualize.sh                # Main entry point
    ├── convert_trace.py            # Trace format converter
    └── index.html                  # Interactive web visualizer
```

#### Install dependencies (local only)

```bash
pip install -r visualizer/requirements.txt
```

This installs `transformers`, `matplotlib`, `tqdm`, and `torch`. Docker users can skip this — the visualizer container has dependencies pre-installed.

#### Quick start

**Local:**

```bash
cp path/to/traces.jsonl ./visualizer/logs/
./visualizer/visualizer/visualize.sh ./visualizer/logs/traces.jsonl --tokenizer gpt2
```

**Docker:**

The visualizer container starts an HTTP server on port 8080. After collecting traces, run `visualize.sh` with `--analysis-only` to trigger conversion and analysis:

```bash
docker exec visualizer ./visualizer/visualize.sh /app/logs/traces_converted.jsonl --analysis-only --tokenizer gpt2
```

Then open `http://<server-ip>:8080/visualizer/index.html?file=/logs/traces.jsonl` in your browser.

The `visualize.sh` script will:
1. Auto-detect and convert the trace format if needed
2. Run prefix & substring matching analysis via `prefix_analysis.py`
3. Generate a cache hit rate plot (`*_cache_hit_rate.png`) and match log (`*_matches.jsonl`)
4. (Local only) Start a local HTTP server and open the visualizer in your browser

#### Options

| Flag | Description | Default |
|---|---|---|
| `--tokenizer NAME` | HuggingFace tokenizer model | `meta-llama/Llama-3.1-8B` |
| `--pool-sizes S1 S2 ...` | KV cache pool sizes in GB to test | `unlimited` |
| `--tokens-per-gb N` | Tokens per GB conversion factor | `8200` |
| `--output-dir DIR` | Directory for analysis outputs | same as input file |
| `--no-analysis` | Skip analysis, only open the visualizer | — |
| `--analysis-only` | Run conversion + analysis, skip server and browser | — |

**Example with multiple pool sizes:**

```bash
# Local
./visualizer/visualizer/visualize.sh visualizer/logs/traces.jsonl \
  --tokenizer gpt2 \
  --pool-sizes 1 2 4 8 unlimited \
  --output-dir ./results

# Docker
docker exec visualizer ./visualizer/visualize.sh /app/logs/traces.jsonl \
  --analysis-only --tokenizer gpt2 --pool-sizes 1 2 4 8 unlimited
```

#### Running analysis standalone

```bash
python3 visualizer/prefix_analysis.py \
  -i visualizer/logs/traces.jsonl \
  -o visualizer/logs/cache_hit_rate.png \
  --log-matches visualizer/logs/matches.jsonl \
  --tokenizer gpt2 \
  --pool-sizes 1 4 unlimited
```

#### Post-processing matches

```bash
# Merge overlapping/adjacent matches
python3 visualizer/merge_matches.py -i visualizer/logs/matches.jsonl -o visualizer/logs/merged.jsonl

# Export to CSV
python3 visualizer/jsonl_to_csv.py -i visualizer/logs/merged.jsonl -o visualizer/logs/matches.csv
```

#### Supported trace formats

The visualizer auto-detects and converts multiple trace formats:

- **Unified**: `{"input": str, "output": str, ...}` (no conversion needed)
- **OpenAI-style**: `{"messages": [...], "response": {"choices": [...]}}`
- **Claude Code raw**: `{"input_raw": {"messages": [...], "system": [...], "tools": [...]}, ...}`
- **raw_request**: `{"raw_request": {"messages": [...], "system": [...], "tools": [...]}}`

#### Web visualizer features

- **Heatmap** — visualize token frequency and reuse across requests
- **Match navigation** — jump between detected substring matches with source arrows
- **Search** — find text patterns across all traces
- **Dark / Light theme** toggle

## Acknowledgement

- [Claude Code](https://claude.ai/code) by [Anthropic](https://www.anthropic.com/) — the AI coding agent whose API calls this project intercepts and traces.
- [LiteLLM](https://github.com/BerriAI/litellm) by BerriAI — the LLM proxy that makes transparent request interception possible.
- [LMCache](https://github.com/LMCache/LMCache) — the KV cache engine for large language models. Special thanks to the original author [Kobe Chen](https://github.com/KobeGong) for his blog on [claude-code-tracing](https://github.com/kobe0938/claude-code-tracing)
- [SWE-bench Pro](https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro) by Scale AI and [SWE-bench](https://www.swebench.com/) by Princeton NLP — the software engineering benchmarks used in our tracing experiments.

