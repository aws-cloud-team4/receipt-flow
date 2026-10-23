"""Thin wrapper around Bedrock Converse that asks for a single tool call and returns its input."""

import re
import time
from typing import Any

from . import aws

# Claude 5-generation models reject non-default sampling and forced tool choice (400), and think by
# default. For those we send toolChoice=auto and rely on the instruction to call the tool.
_CURRENT_GEN = re.compile(r"(haiku-5|sonnet-5|opus-5|fable|mythos)")


class ModelError(RuntimeError):
    pass


def call_tool(
    system: str,
    content: list[dict[str, Any]],
    tool_name: str,
    tool_description: str,
    schema: dict[str, Any],
    model: str,
    max_tokens: int = 1024,
) -> tuple[dict[str, Any], dict[str, int]]:
    current_gen = bool(_CURRENT_GEN.search(model))
    inference: dict[str, Any] = {"maxTokens": max_tokens if not current_gen else max(max_tokens, 4096)}
    if not current_gen:
        inference["temperature"] = 0
    started = time.perf_counter()
    resp = aws.client("bedrock-runtime").converse(
        modelId=model,
        system=[{"text": system + f"\n\n반드시 {tool_name} 도구를 한 번 호출해 결과를 기록합니다."}],
        messages=[{"role": "user", "content": content}],
        inferenceConfig=inference,
        toolConfig={
            "tools": [
                {
                    "toolSpec": {
                        "name": tool_name,
                        "description": tool_description,
                        "inputSchema": {"json": schema},
                    }
                }
            ],
            "toolChoice": {"auto": {}} if current_gen else {"tool": {"name": tool_name}},
        },
    )
    usage = {
        "input_tokens": resp["usage"]["inputTokens"],
        "output_tokens": resp["usage"]["outputTokens"],
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block:
            return block["toolUse"]["input"], usage
    raise ModelError("모델이 구조화된 결과를 반환하지 않았습니다.")
