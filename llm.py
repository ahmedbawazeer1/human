"""Model client: any OpenAI-compatible chat endpoint, default a local open-weight model.

Defaults talk to Ollama (`qwen3:4b`) on localhost. The same code works with a
llama.cpp server, vLLM, or a free hosted tier that speaks the OpenAI chat API.
No paid service is required.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

import httpx

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen3:4b"


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    seconds: float = 0.0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMClient:
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", DEFAULT_MODEL))
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", "local"))
    # USD per 1k tokens. 0 for a local model; set these only if you use a metered tier.
    cost_in_per_1k: float = field(default_factory=lambda: float(os.getenv("LLM_COST_IN_PER_1K", "0")))
    cost_out_per_1k: float = field(default_factory=lambda: float(os.getenv("LLM_COST_OUT_PER_1K", "0")))
    timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "900")))
    temperature: float = 0.3
    usage: Usage = field(default_factory=Usage)

    def cost_of(self, prompt_tokens: int, completion_tokens: int) -> float:
        return round(prompt_tokens / 1000 * self.cost_in_per_1k
                     + completion_tokens / 1000 * self.cost_out_per_1k, 6)

    def chat(self, system: str, user: str, max_tokens: int = 900, json_mode: bool = False) -> tuple[str, float]:
        """Return (text, cost_usd) for one completion."""
        # Qwen3 "thinking" is slow on CPU; the /no_think switch turns it off.
        if "qwen3" in self.model.lower():
            system = system + "\n/no_think"
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }
        if json_mode and os.getenv("LLM_JSON_MODE", "0") == "1":
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        start = time.time()
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                r = httpx.post(f"{self.base_url.rstrip('/')}/chat/completions",
                               json=payload, headers=headers, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:  # network or server error: retry with backoff
                last_err = e
                time.sleep(2 * (attempt + 1))
        else:
            raise LLMError(f"model call failed at {self.base_url} ({self.model}): {last_err}")
        text = data["choices"][0]["message"].get("content") or ""
        text = strip_thinking(text)
        u = data.get("usage") or {}
        pt = int(u.get("prompt_tokens") or len(system + user) // 4)
        ct = int(u.get("completion_tokens") or len(text) // 4)
        self.usage.prompt_tokens += pt
        self.usage.completion_tokens += ct
        self.usage.calls += 1
        self.usage.seconds += time.time() - start
        return text.strip(), self.cost_of(pt, ct)

    def chat_json(self, system: str, user: str, max_tokens: int = 900, retries: int = 2):
        """Ask for JSON and parse it; re-ask on parse failure. Returns (obj, cost)."""
        total_cost = 0.0
        prompt = user + "\n\nReturn ONLY valid JSON. No prose, no markdown fences."
        for _ in range(retries + 1):
            text, cost = self.chat(system, prompt, max_tokens=max_tokens, json_mode=True)
            total_cost += cost
            obj = extract_json(text)
            if obj is not None:
                return obj, total_cost
            self.last_bad_json = text
            dbg = os.getenv("LLM_DEBUG_FILE")
            if dbg:
                with open(dbg, "a", encoding="utf-8") as f:
                    f.write(f"--- bad JSON ({len(text)} chars)\nPROMPT TAIL: {user[-300:]!r}\nANSWER: {text!r}\n")
            prompt = user + "\n\nYour last answer was not valid JSON. Return ONLY valid JSON, shorter."
        raise LLMError("model did not return valid JSON")

    def ping(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url.rstrip('/')}/models", timeout=5,
                          headers={"Authorization": f"Bearer {self.api_key}"})
            return r.status_code == 200
        except Exception:
            return False


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def _repair(s: str) -> str:
    s = re.sub(r",\s*([}\]])", r"\1", s)            # trailing commas
    s = re.sub(r"//[^\n]*", "", s)                     # comments
    # close a truncated answer: drop the last partial item and balance brackets
    stack, in_str, esc = [], False, False
    for ch in s:
        if in_str:
            esc = (ch == "\\" and not esc)
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    if in_str:
        s += '"'
    if stack:
        s = re.sub(r",\s*\"?[^,{}\[\]]*$", "", s.rstrip())
        s += "".join(reversed(stack))
    return s


def extract_json(text: str):
    text = strip_thinking(text)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    candidates = [text]
    for open_c in ("{", "["):
        start = text.find(open_c)
        if start != -1:
            candidates.append(text[start:])
            end = text.rfind("}" if open_c == "{" else "]")
            if end > start:
                candidates.append(text[start:end + 1])
    for c in candidates:
        for variant in (c, _repair(c)):
            try:
                return json.loads(variant)
            except Exception:
                continue
    return None
