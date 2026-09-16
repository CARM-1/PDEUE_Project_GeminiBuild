import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional
from .base import BaseLLMClient, LLMResponse

class OpenAILLMClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self.endpoint = "https://api.openai.com/v1/chat/completions"

    def generate_response(
        self,
        system_prompt: str,
        user_query: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                content="OpenAI API key not configured. Set OPENAI_API_KEY environment variable.",
                provider="openai",
                model=self.model
            )

        msgs = [{"role": "system", "content": system_prompt}]
        if context:
            msgs.append({
                "role": "system",
                "content": f"""Active PDEUE Operational Context:
{json.dumps(context, indent=2)}"""
            })
        msgs.append({"role": "user", "content": user_query})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "temperature": 0.2
        }
        if tools:
            payload["tools"] = tools

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0].get("message", {})
                content = choice.get("content", "") or ""
                tool_calls = choice.get("tool_calls", [])
                action_cards = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except Exception:
                        args = {}
                    action_cards.append({
                        "action_id": f"ACT-{uuid.uuid4().hex[:8]}",
                        "action_type": fn_name or "ACTION",
                        "title": args.get("title", f"Execute {fn_name}"),
                        "description": args.get("description", "AI operation."),
                        "endpoint": args.get("endpoint", "/api/v1/operator/action"),
                        "method": args.get("method", "POST"),
                        "payload": args.get("payload", {}),
                        "destructive": args.get("destructive", False),
                        "requires_dual_control": args.get("requires_dual_control", False)
                    })
                return LLMResponse(
                    content=content,
                    action_cards=action_cards,
                    tool_calls=tool_calls,
                    provider="openai",
                    model=self.model,
                    raw_payload=data
                )
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            return LLMResponse(
                content=f"OpenAI API error ({e.code}): {err_body}",
                provider="openai",
                model=self.model
            )
        except Exception as e:
            return LLMResponse(
                content=f"Connection error to OpenAI: {str(e)}",
                provider="openai",
                model=self.model
            )
