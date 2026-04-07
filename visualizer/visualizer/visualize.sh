#!/bin/bash
# Usage: ./visualizer/visualize.sh [path/to/traces.jsonl] [options]
#
# Runs prefix_analysis.py on the trace file, then opens the visualizer
# in the browser with the data auto-loaded.
#
# Options:
#   --no-analysis      Skip analysis, only open the visualizer
#   --analysis-only    Run conversion + analysis, skip server and browser
#   --tokenizer NAME   HuggingFace tokenizer (default: meta-llama/Llama-3.1-8B)
#   --pool-sizes ...   Pool sizes in GB (e.g., 1 2 4 unlimited)
#   --output-dir DIR   Directory for analysis outputs (default: same as input)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${PORT:-8080}"

INPUT_FILE=""
NO_ANALYSIS=false
ANALYSIS_ONLY=false
EXTRA_ARGS=()
OUTPUT_DIR=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-analysis)
            NO_ANALYSIS=true; shift ;;
        --analysis-only)
            ANALYSIS_ONLY=true; shift ;;
        --output-dir)
            OUTPUT_DIR="$2"; shift 2 ;;
        --tokenizer|--pool-sizes|--tokens-per-gb)
            EXTRA_ARGS+=("$1" "$2"); shift 2 ;;
        -*)
            EXTRA_ARGS+=("$1"); shift ;;
        *)
            if [ -z "$INPUT_FILE" ]; then
                INPUT_FILE="$1"
            fi
            shift ;;
    esac
done

# Find an available port
while lsof -i :"$PORT" &>/dev/null; do
    PORT=$((PORT + 1))
done

URL="http://localhost:$PORT/visualizer/index.html"

if [ -n "$INPUT_FILE" ]; then
    ABS_INPUT="$(cd "$(dirname "$INPUT_FILE")" && pwd)/$(basename "$INPUT_FILE")"

    if [ ! -f "$ABS_INPUT" ]; then
        echo "Error: File not found: $INPUT_FILE"
        exit 1
    fi

    if [ -z "$OUTPUT_DIR" ]; then
        OUTPUT_DIR="$(dirname "$ABS_INPUT")"
    fi
    mkdir -p "$OUTPUT_DIR"
    BASENAME="$(basename "$INPUT_FILE" .jsonl)"

    # Auto-detect if conversion is needed (check if first line has "input" as string)
    NEEDS_CONVERT=$(python3 -c "
import json, sys
with open('$ABS_INPUT') as f:
    d = json.loads(f.readline())
    if 'input' in d and isinstance(d['input'], str) and d['input'].strip():
        print('no')
    else:
        print('yes')
" 2>/dev/null || echo "no")

    VIZ_INPUT="$ABS_INPUT"
    if [ "$NEEDS_CONVERT" = "yes" ]; then
        CONVERTED="$OUTPUT_DIR/${BASENAME}_converted.jsonl"
        echo "=== Converting trace format ==="
        python3 "$SCRIPT_DIR/convert_trace.py" -i "$ABS_INPUT" -o "$CONVERTED"
        VIZ_INPUT="$CONVERTED"
        echo ""
    fi

    # Run prefix analysis
    if [ "$NO_ANALYSIS" = false ]; then
        PLOT_OUTPUT="$OUTPUT_DIR/${BASENAME}_cache_hit_rate.png"
        MATCH_LOG="$OUTPUT_DIR/${BASENAME}_matches.jsonl"

        echo "=== Running prefix analysis ==="
        python3 "$REPO_ROOT/prefix_analysis.py" \
            -i "$VIZ_INPUT" \
            -o "$PLOT_OUTPUT" \
            --log-matches "$MATCH_LOG" \
            "${EXTRA_ARGS[@]}"

        echo ""
        echo "Analysis outputs:"
        echo "  Plot:    $PLOT_OUTPUT"
        echo "  Matches: $MATCH_LOG"
        echo ""
    fi

    # Set URL to auto-load the (possibly converted) trace file
    REL_PATH="${VIZ_INPUT#$REPO_ROOT/}"
    URL="${URL}?file=/$REL_PATH"
fi

if [ "$ANALYSIS_ONLY" = true ]; then
    echo "=== Analysis complete ==="
    exit 0
fi

echo "=== Starting visualizer ==="
echo "Server on port $PORT..."
echo "Opening: $URL"

# Start HTTP server in background from repo root
cd "$REPO_ROOT"
python3 -m http.server "$PORT" --bind "${BIND:-127.0.0.1}" &>/dev/null &
SERVER_PID=$!

# Open browser
if command -v open &>/dev/null; then
    open "$URL"
elif command -v xdg-open &>/dev/null; then
    xdg-open "$URL"
else
    echo "Open this URL in your browser: $URL"
fi

echo "Server PID: $SERVER_PID (kill with: kill $SERVER_PID)"
echo "Press Ctrl+C to stop."
trap "kill $SERVER_PID 2>/dev/null; exit" INT TERM
wait $SERVER_PID
