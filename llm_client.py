"""
llm_client.py — one small client for Claude, ChatGPT and Gemini.

Shared with Causal Loop Colab and SFD Studio (this copy adds a timeout option): standard library only (no SDKs), retries
when a provider is busy (429/5xx/529), a longer timeout, light "thinking"
for Gemini, and plain-language error messages.

cfg = {"provider": "anthropic" | "openai" | "gemini", "key": "...", "model": "..."}
complete(cfg, system, user, max_tokens, want_json) -> (text, None) or (None, error)
"""

import json
import re
import time
import urllib.error
import urllib.request

PROVIDERS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (ChatGPT)",
    "gemini": "Google (Gemini)",
}

DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-7",
    "openai": "gpt-4o",
    "gemini": "gemini-3.5-flash-lite",
}

KEY_PLACEHOLDER = {"anthropic": "sk-ant-…", "openai": "sk-…", "gemini": "AIza…"}

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# ------------------------------------------------------------------ transport
# Status codes that mean "busy, try again": rate limits (429), server errors,
# Google's "high demand" (503) and Anthropic's "overloaded" (529).
RETRY_CODES = {429, 500, 502, 503, 504, 529}
RETRY_WAITS = (2, 5)          # seconds to wait before the 2nd and 3rd attempts
TIMEOUT = 40                  # seconds per attempt


def _post_once(url, headers, body, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url, headers, body, timeout=TIMEOUT):
    """POST with retries when the provider is busy. A timed-out request is
    retried once; a busy response (429/5xx) up to twice, after short waits."""
    timeouts = 0
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            return _post_once(url, headers, body, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_CODES or attempt == len(RETRY_WAITS):
                raise
        except (TimeoutError, OSError) as exc:
            if not _is_timeout(exc):
                raise
            timeouts += 1
            if timeouts > 1 or attempt == len(RETRY_WAITS):
                raise
        time.sleep(RETRY_WAITS[attempt])


def _is_timeout(exc):
    return isinstance(exc, TimeoutError) or "timed out" in str(exc).lower()


def _error_text(exc):
    if isinstance(exc, urllib.error.HTTPError):
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            err = detail.get("error")
            msg = err.get("message") if isinstance(err, dict) else (err or str(exc))
        except Exception:
            msg = str(exc)
        if exc.code in RETRY_CODES:
            return ("The AI service is very busy right now. Try again in a few minutes, "
                    "or choose a different model in the sidebar. "
                    f"(Provider said: {exc.code} — {msg})")
        return f"API error ({exc.code}): {msg}"
    if _is_timeout(exc):
        return ("The AI service took too long to answer. It is probably busy — try "
                "again in a few minutes, or choose a different model in the sidebar.")
    return f"Could not reach the AI: {exc}"


def _gemini_thinking(model):
    """Keep thinking light: these are short, simple replies, and heavy
    thinking makes Gemini slow enough to time out. Gemini 2.x models take a
    token budget; Gemini 3 and later take a thinking level."""
    m = model.lower()
    if m.startswith("gemini-2"):
        return {"thinkingBudget": 0} if "flash" in m else None
    return {"thinkingLevel": "low"}


def _gemini(model, key, system, user, max_tokens, want_json, timeout=TIMEOUT):
    gen = {"maxOutputTokens": max(max_tokens, 2048)}
    thinking = _gemini_thinking(model)
    if thinking:
        gen["thinkingConfig"] = thinking
    if want_json:
        gen["responseMimeType"] = "application/json"
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen}
    url = GEMINI_URL.format(model=model)
    try:
        return _post(url, {"x-goog-api-key": key}, body, timeout)
    except urllib.error.HTTPError as exc:
        # A model that rejects this thinking setting: retry once without it.
        if exc.code == 400 and "thinkingConfig" in gen:
            gen.pop("thinkingConfig")
            return _post(url, {"x-goog-api-key": key}, body, timeout)
        raise


def complete(cfg, system, user, max_tokens=300, want_json=False, timeout=TIMEOUT):
    """One system + user exchange. Returns (text, None) or (None, error).
    `timeout` (seconds per attempt) can be raised for long answers."""
    provider = cfg["provider"]
    model = (cfg.get("model") or "").strip() or DEFAULT_MODELS[provider]
    key = cfg["key"]
    try:
        if provider == "anthropic":
            data = _post(ANTHROPIC_URL,
                         {"x-api-key": key, "anthropic-version": "2023-06-01"},
                         {"model": model, "max_tokens": max_tokens, "system": system,
                          "messages": [{"role": "user", "content": user}]}, timeout)
            text = "".join(b.get("text", "") for b in data.get("content", [])
                           if b.get("type") == "text")
        elif provider == "openai":
            body = {"model": model, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}]}
            if want_json:
                body["response_format"] = {"type": "json_object"}
            data = _post(OPENAI_URL, {"Authorization": f"Bearer {key}"}, body, timeout)
            text = data["choices"][0]["message"]["content"] or ""
        else:  # gemini
            data = _gemini(model, key, system, user, max_tokens, want_json, timeout)
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        text = (text or "").strip()
        return (text, None) if text else (None, "Empty response from the AI.")
    except Exception as exc:
        return None, _error_text(exc)


def complete_json(cfg, system, user, max_tokens=400, timeout=TIMEOUT):
    text, err = complete(cfg, system, user, max_tokens=max_tokens, want_json=True,
                         timeout=timeout)
    if err:
        return None, err
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None, "The AI did not return JSON."
    try:
        return json.loads(m.group(0)), None
    except json.JSONDecodeError:
        return None, "The AI's reply could not be read."


def test_connection(cfg):
    text, err = complete(cfg, "Reply with the single word OK.", "Ping", max_tokens=5)
    return err is None, err
