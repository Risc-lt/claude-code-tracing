#!/usr/bin/env python3
"""Convert various trace JSONL formats into the unified format expected by the visualizer.

Supported input formats:
  1. Already converted: {"input": str, "output": str, ...}
  2. OpenAI-style: {"messages": [...], "response": {"choices": [...]}, ...}
  3. Claude Code raw: {"input_raw": {"messages": [...], "system": [...], "tools": [...]}, "output_raw": {...}, ...}

Output format (one per line):
  {"input": "<all input text>", "output": "<response text>", "timestamp": ..., "model": ...}
"""

import json
import argparse
import sys


def flatten_content(content):
    """Convert content (str, list of blocks, or other) to a single string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(f'[tool_use: {block.get("name", "")}({json.dumps(block.get("input", ""))})]')
                elif block.get("type") == "tool_result":
                    parts.append(f'[tool_result: {flatten_content(block.get("content", ""))}]')
                else:
                    parts.append(json.dumps(block))
            elif isinstance(block, str):
                parts.append(block)
            else:
                parts.append(str(block))
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def messages_to_string(messages, system=None, tools=None):
    """Convert a list of chat messages into a single string."""
    parts = []

    if system:
        parts.append("<system>")
        if isinstance(system, str):
            parts.append(system)
        elif isinstance(system, list):
            for item in system:
                parts.append(flatten_content(item) if isinstance(item, (str, list)) else json.dumps(item))
        parts.append("")

    if tools:
        parts.append(f"<tools> ({len(tools)} tools)")
        for t in tools:
            name = t.get("name", "unknown")
            parts.append(f"  - {name}")
        parts.append("")

    if messages:
        parts.append("<messages>")
        for msg in messages:
            role = msg.get("role", "unknown")
            content = flatten_content(msg.get("content", ""))
            parts.append(f"[{role}] {content}")
        parts.append("")

    return "\n".join(parts)


def extract_output(response_or_raw):
    """Extract output text from various response formats."""
    if isinstance(response_or_raw, str):
        return response_or_raw

    if not isinstance(response_or_raw, dict):
        return str(response_or_raw) if response_or_raw else ""

    # OpenAI format: {"choices": [{"message": {"content": ...}}]}
    choices = response_or_raw.get("choices", [])
    if choices:
        msg = choices[0].get("message", {})
        parts = []
        content = msg.get("content", "")
        if content:
            parts.append(flatten_content(content))
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            parts.append(f'[tool_call: {fn.get("name", "")}({fn.get("arguments", "")})]')
        return "\n".join(parts) if parts else json.dumps(msg)

    # Claude raw format: {"content": ..., "role": "assistant", ...}
    if "role" in response_or_raw or "content" in response_or_raw:
        parts = []
        content = response_or_raw.get("content", "")
        if content:
            parts.append(flatten_content(content))
        for tc in (response_or_raw.get("tool_calls") or []):
            fn = tc.get("function", {})
            parts.append(f'[tool_call: {fn.get("name", "")}({fn.get("arguments", "")})]')
        return "\n".join(parts) if parts else json.dumps(response_or_raw)

    return json.dumps(response_or_raw)


def convert_line(data):
    """Convert a single trace entry to the unified format."""
    # Already in the right format
    if "input" in data and isinstance(data["input"], str) and data["input"].strip():
        return {
            "input": data["input"],
            "output": data.get("output", ""),
            "timestamp": data.get("timestamp") or data.get("start_time"),
            "model": data.get("model"),
        }

    input_text = ""
    output_text = ""
    timestamp = data.get("timestamp") or data.get("start_time")
    model = data.get("model")

    # Format 3: Claude Code raw (input_raw / output_raw)
    if "input_raw" in data:
        ir = data["input_raw"]
        input_text = messages_to_string(
            ir.get("messages", []),
            system=ir.get("system"),
            tools=ir.get("tools"),
        )
        output_text = extract_output(data.get("output_raw", ""))
        model = model or ir.get("model")

    # Format 2b: raw_request — preferred over plain messages because it
    # contains the full request (system prompt, tools, messages).
    elif "raw_request" in data:
        rr = data["raw_request"]
        if isinstance(rr, str):
            try:
                rr = json.loads(rr)
            except json.JSONDecodeError:
                import ast
                rr = ast.literal_eval(rr)
        input_text = messages_to_string(
            rr.get("messages", []),
            system=rr.get("system"),
            tools=rr.get("tools"),
        )
        output_text = extract_output(data.get("response", ""))

    # Format 2: OpenAI-style (messages + response), no raw_request
    elif "messages" in data:
        input_text = messages_to_string(data["messages"])
        output_text = extract_output(data.get("response", ""))

    return {
        "input": input_text,
        "output": output_text if isinstance(output_text, str) else json.dumps(output_text),
        "timestamp": timestamp,
        "model": model,
    }


def main():
    parser = argparse.ArgumentParser(description="Convert trace JSONL to visualizer format")
    parser.add_argument("-i", "--input", required=True, help="Input JSONL file")
    parser.add_argument("-o", "--output", default=None, help="Output JSONL file (default: <input>_converted.jsonl)")
    args = parser.parse_args()

    output_path = args.output or args.input.replace(".jsonl", "_converted.jsonl")
    count = 0
    skipped = 0

    with open(args.input, "r") as fin, open(output_path, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                converted = convert_line(data)
                if not converted["input"].strip():
                    skipped += 1
                    continue
                fout.write(json.dumps(converted) + "\n")
                count += 1
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: skipping line: {e}", file=sys.stderr)
                skipped += 1

    print(f"Converted {count} entries -> {output_path}" +
          (f" (skipped {skipped})" if skipped else ""))


if __name__ == "__main__":
    main()
