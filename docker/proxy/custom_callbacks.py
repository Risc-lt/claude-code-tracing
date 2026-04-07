from litellm.integrations.custom_logger import CustomLogger
import json, datetime, os

LOG_FILE = "/logs/traces.jsonl"


def _safe_dump(obj):
    """Serialize obj to a JSON-safe dict, handling circular references."""
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:
            pass
    try:
        json.dumps(obj, default=str)
        return obj
    except (ValueError, TypeError):
        return str(obj)


class JSONLLogger(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "model": kwargs.get("model", ""),
                "messages": kwargs.get("messages", []),
                "response": _safe_dump(response_obj),
                "start_time": str(start_time),
                "end_time": str(end_time),
                "input_tokens": response_obj.usage.prompt_tokens if hasattr(response_obj, "usage") and response_obj.usage else None,
                "output_tokens": response_obj.usage.completion_tokens if hasattr(response_obj, "usage") and response_obj.usage else None,
            }
            complete_input = kwargs.get("additional_args", {}).get("complete_input_dict", None)
            if complete_input:
                entry["raw_request"] = _safe_dump(complete_input)
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
