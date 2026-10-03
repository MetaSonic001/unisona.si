"""LLM access for every text path (chat, analysis, memory, evals).

One OpenAI-compatible client works for every supported provider. `LLM.chat()` handles
retries, per-model quirks (reasoning settings), usage/cost logging and returns a
uniform result. Voice uses the same resolved provider/model through Pipecat.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal
from ..log import get_logger
from ..models import UsageEvent, Workspace
from .keys import ResolvedKey, resolve
from .registry import PROVIDERS, estimate_llm_cost

log = get_logger("llm")
_clients: dict[tuple[str, str], AsyncOpenAI] = {}


def client_for(base_url: str, api_key: str | None) -> AsyncOpenAI:
    k = (base_url, api_key or "none")
    if k not in _clients:
        _clients[k] = AsyncOpenAI(base_url=base_url, api_key=api_key or "not-needed", max_retries=2, timeout=45)
    return _clients[k]


def groq_client(api_key: str) -> AsyncOpenAI:
    return client_for(PROVIDERS["groq"].base_url, api_key)


def model_extra(model: str) -> dict[str, Any]:
    """Per-model request extras: keep reasoning short so replies stay fast."""
    if "gpt-oss" in model:
        return {"reasoning_effort": "low", "include_reasoning": False}
    if model.startswith("qwen/") or model.startswith("qwen-"):
        return {"reasoning_effort": "none"}
    return {}


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class ChatResult:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    raw_message: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLM:
    """A resolved LLM for one workspace: provider + model + key."""

    workspace: Workspace
    provider: str
    model: str
    key: ResolvedKey

    @property
    def available(self) -> bool:
        return self.key.ok

    @property
    def client(self) -> AsyncOpenAI:
        return client_for(self.key.base_url or PROVIDERS[self.provider].base_url, self.key.api_key)

    async def chat(self, messages: list[dict[str, Any]], *, tools: list[dict] | None = None, temperature: float = 0.3,
                   max_tokens: int = 1024, json_mode: bool = False, purpose: str = "chat", agent_id: str | None = None) -> ChatResult:
        if not self.available:
            raise LLMUnavailable(f"No API key for {self.provider}")
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": temperature,
                                  "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        extra = model_extra(self.model) if self.provider == "groq" else {}
        t0 = time.perf_counter()
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = await self.client.chat.completions.create(**kwargs, extra_body=extra or None)
                break
            except Exception as e:  # rate limits / transient errors
                last_err = e
                msg = str(e)
                if "tool_use_failed" in msg and tools and attempt == 0:
                    kwargs.pop("tools", None)
                    kwargs.pop("tool_choice", None)
                    continue
                if attempt < 2 and ("429" in msg or "503" in msg or "timeout" in msg.lower() or "500" in msg):
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                raise
        else:
            raise last_err  # type: ignore[misc]
        dt = int((time.perf_counter() - t0) * 1000)
        choice = resp.choices[0].message
        calls = []
        for tc in choice.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
        usage = resp.usage
        tin = getattr(usage, "prompt_tokens", 0) or 0
        tout = getattr(usage, "completion_tokens", 0) or 0
        cost = estimate_llm_cost(self.model, tin, tout)
        asyncio.create_task(_log_usage(self.workspace.id, self.provider, self.model, tin, tout, cost, agent_id, self.key.source))
        raw = {"role": "assistant", "content": choice.content or ""}
        if choice.tool_calls:
            raw["tool_calls"] = [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                 for tc in choice.tool_calls]
        return ChatResult(content=(choice.content or "").strip(), tool_calls=calls, model=self.model, provider=self.provider,
                          input_tokens=tin, output_tokens=tout, latency_ms=dt, cost_usd=cost, raw_message=raw)

    async def stream(self, messages: list[dict[str, Any]], *, temperature: float = 0.3, max_tokens: int = 1024,
                     agent_id: str | None = None) -> AsyncIterator[str]:
        if not self.available:
            raise LLMUnavailable(f"No API key for {self.provider}")
        extra = model_extra(self.model) if self.provider == "groq" else {}
        stream = await self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature, max_tokens=max_tokens, stream=True,
            extra_body=extra or None, stream_options={"include_usage": True},
        )
        tin = tout = 0
        async for chunk in stream:
            if chunk.usage:
                tin, tout = chunk.usage.prompt_tokens or 0, chunk.usage.completion_tokens or 0
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        asyncio.create_task(_log_usage(self.workspace.id, self.provider, self.model, tin, tout,
                                       estimate_llm_cost(self.model, tin, tout), agent_id, self.key.source))

    async def stream_chat(self, messages: list[dict[str, Any]], *, tools: list[dict] | None = None, temperature: float = 0.3,
                          max_tokens: int = 1024, agent_id: str | None = None) -> AsyncIterator[tuple[str, Any]]:
        """Stream text deltas; tool calls are accumulated and returned in the final ("done", ChatResult) event."""
        if not self.available:
            raise LLMUnavailable(f"No API key for {self.provider}")
        extra = model_extra(self.model) if self.provider == "groq" else {}
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
                                  "stream": True, "stream_options": {"include_usage": True}}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        t0 = time.perf_counter()
        try:
            stream = await self.client.chat.completions.create(**kwargs, extra_body=extra or None)
        except Exception as e:
            if "tool_use_failed" in str(e) and tools:
                kwargs.pop("tools"), kwargs.pop("tool_choice")
                stream = await self.client.chat.completions.create(**kwargs, extra_body=extra or None)
            else:
                raise
        text_parts: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        tin = tout = 0
        first_token_ms = None
        async for chunk in stream:
            if chunk.usage:
                tin, tout = chunk.usage.prompt_tokens or 0, chunk.usage.completion_tokens or 0
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                if first_token_ms is None:
                    first_token_ms = int((time.perf_counter() - t0) * 1000)
                text_parts.append(delta.content)
                yield "text", delta.content
            for tc in delta.tool_calls or []:
                slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
        parsed = []
        raw_calls = []
        for slot in calls.values():
            try:
                args = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            parsed.append({"id": slot["id"], "name": slot["name"], "arguments": args})
            raw_calls.append({"id": slot["id"], "type": "function", "function": {"name": slot["name"], "arguments": slot["arguments"] or "{}"}})
        cost = estimate_llm_cost(self.model, tin, tout)
        asyncio.create_task(_log_usage(self.workspace.id, self.provider, self.model, tin, tout, cost, agent_id, self.key.source))
        raw = {"role": "assistant", "content": "".join(text_parts)}
        if raw_calls:
            raw["tool_calls"] = raw_calls
        yield "done", ChatResult(content="".join(text_parts).strip(), tool_calls=parsed, model=self.model, provider=self.provider,
                                 input_tokens=tin, output_tokens=tout, latency_ms=first_token_ms or int((time.perf_counter() - t0) * 1000),
                                 cost_usd=cost, raw_message=raw)

    async def json(self, system: str, user: str, *, purpose: str = "analysis", max_tokens: int = 1200) -> dict[str, Any]:
        r = await self.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                            temperature=0, max_tokens=max_tokens, json_mode=True, purpose=purpose)
        text = r.content.strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            return json.loads(text[start:end + 1]) if start >= 0 and end > start else {}


async def _log_usage(ws_id: str, provider: str, model: str, tin: int, tout: int, cost: float, agent_id: str | None, source: str):
    try:
        async with SessionLocal() as db:
            db.add(UsageEvent(workspace_id=ws_id, kind="llm", provider=provider, model=model, quantity=tin + tout,
                              input_tokens=tin, output_tokens=tout, cost_usd=cost, agent_id=agent_id))
            if source == "platform":
                ws = await db.get(Workspace, ws_id)
                if ws:
                    ws.trial_llm_calls += 1
            await db.commit()
    except Exception as e:
        log.debug(f"usage log failed: {e}")


async def get_llm(db: AsyncSession, ws: Workspace, *, provider: str | None = None, model: str | None = None,
                  fast: bool = False, feature: str = "AI replies") -> LLM:
    """Pick the LLM for a workspace. Falls back across providers that have keys."""
    prefs = ws.settings.get("llm", {})
    candidates = [provider] if provider else []
    candidates += [prefs.get("provider"), "groq", "gemini", "openai", "openrouter", "cerebras", "anthropic", "mistral", "ollama"]
    seen = set()
    for p in [c for c in candidates if c and c in PROVIDERS]:
        if p in seen:
            continue
        seen.add(p)
        key = await resolve(db, ws, p, feature=feature)
        if key.ok:
            spec = PROVIDERS[p]
            if model and (provider is None or p == provider):
                chosen = model
            elif fast and spec.fast_llm:
                chosen = spec.fast_llm
            elif p == prefs.get("provider") and prefs.get("model"):
                chosen = prefs["model"]
            else:
                chosen = spec.default_llm
            return LLM(ws, p, chosen, key)
        if provider:  # explicit provider without a key: still try fallbacks
            continue
    return LLM(ws, provider or "groq", model or PROVIDERS["groq"].default_llm, ResolvedKey(provider or "groq", None, None, "none"))
