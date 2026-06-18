# api/routes_ai.py
"""
AI-assisted diagnostic endpoints.

POST /api/ai/diagnose-scanner-error
  Accepts an error context (scanner name, error message, surrounding logs)
  and returns a plain-text diagnostic summary.

NOTE: The actual AI call is a stub until the AI provider settings are fully
wired up. When ready, replace the stub body with a real provider call using
the api_key and ai_provider from Settings.
"""

from aiohttp import web
from core.primitives.settings import SettingsManager
from core.primitives.security import decrypt, is_encrypted

STUB_ADVICE: dict[str, str] = {
    "vulture":  "Vulture did not find a valid Python interpreter. Make sure vulture is installed in the project virtual environment: `pip install vulture`.",
    "bandit":   "Bandit could not parse the target. Check that the project_path points to valid Python source files and that bandit is installed: `pip install bandit`.",
    "safety":   "Safety timed out during dependency resolution. This can happen with circular dependencies or a slow PyPI mirror. Try running with `force_rescan: true` to clear the cache, or increase the scanner timeout in the Scanners tab.",
}

GENERIC_ADVICE = (
    "The scanner encountered an unexpected error. "
    "Check that the required tool is installed in the project virtual environment and that "
    "the project_path points to the correct directory. "
    "Review the full error message above for additional details."
)


async def diagnose_scanner_error(request: web.Request) -> web.Response:
    """
    POST /api/ai/diagnose-scanner-error

    Request JSON:
      {
        "scanner_name":  "safety",
        "error_message": "TimeoutError: Scanner timed out after 120s",
        "context_logs":  ["...", "..."]   // optional
      }

    Response JSON:
      { "analysis": "..." }
    Or, when AI is disabled:
      { "error": "AI is not enabled" }  (HTTP 503)
    """
    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    settings = workspace.global_settings

    if not settings.ai_enabled:
        return web.json_response(
            {"error": "AI diagnostics are not enabled. Enable AI in the Settings tab and provide an API key."},
            status=503,
        )

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    scanner_name  = str(body.get("scanner_name", "")).strip().lower()
    error_message = str(body.get("error_message", "")).strip()

    if not scanner_name or not error_message:
        return web.json_response({"error": "scanner_name and error_message are required"}, status=400)

    raw_key = settings.api_key or ""
    api_key = decrypt(raw_key) if is_encrypted(raw_key) else raw_key

    # If no API key is configured, fall back to canned stub advice rather than
    # making a real call that will fail with 401.
    if not api_key or api_key == "***":
        analysis = STUB_ADVICE.get(scanner_name, GENERIC_ADVICE)
        return web.json_response({"analysis": analysis})

    context = "\n".join(body.get("context_logs", []))[-2000:]
    prompt = (
        f"Analyze the following scanner error and provide a concise, plain-text "
        f"diagnostic summary and suggested fix:\n"
        f"Scanner: {scanner_name}\nError: {error_message}\nContext:\n{context}"
    )

    provider = settings.ai_provider
    model    = settings.ai_model
    endpoint = settings.ai_custom_endpoint

    try:
        if provider == "claude":
            analysis = await _gen_claude(api_key, model, prompt)
        elif provider == "gemini":
            analysis = await _gen_gemini(api_key, model, prompt)
        elif provider == "ollama":
            analysis = await _gen_ollama(endpoint or "http://localhost:11434", settings.ai_local_model or model, prompt)
        elif provider == "custom":
            analysis = await _gen_custom(endpoint, api_key, prompt)
        else:
            analysis = STUB_ADVICE.get(scanner_name, GENERIC_ADVICE)
    except Exception as e:
        analysis = f"AI diagnostic failed: {str(e)}"

    return web.json_response({"analysis": analysis})

import time

# In-memory session usage tracker (resets on server restart)
_usage = {"requests": 0, "total_tokens": 0, "last_used": None, "estimated_cost": 0.0}

async def test_connection(request: web.Request) -> web.Response:
    """
    Test a provider connection. Sends a minimal request and measures latency.
    Does NOT use the stored API key — uses the key from the request body.
    This allows testing before saving.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    provider  = (body.get("provider") or "").strip()
    model     = (body.get("model") or "").strip()
    api_key   = (body.get("api_key") or "").strip()
    endpoint  = (body.get("endpoint") or "").strip()

    if not provider:
        return web.json_response({"success": False, "error": "provider is required"}, status=400)

    start = time.monotonic()

    try:
        if provider == "claude":
            result = await _test_claude(api_key, model)
        elif provider == "gemini":
            result = await _test_gemini(api_key, model)
        elif provider == "ollama":
            result = await _test_ollama(endpoint or "http://localhost:11434", model)
        elif provider == "custom":
            result = await _test_custom(endpoint, api_key)
        else:
            return web.json_response({"success": False, "error": f"Unknown provider: {provider}"}, status=400)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

    latency_ms = int((time.monotonic() - start) * 1000)
    return web.json_response({
        "success": result.get("success", False),
        "latency_ms": latency_ms,
        "model": model,
        "provider": provider,
        "quota_remaining": result.get("quota_remaining"),
        "error": result.get("error"),
    })


async def get_usage(request: web.Request) -> web.Response:
    """Return session AI usage statistics."""
    return web.json_response(_usage)


async def get_ollama_models(request: web.Request) -> web.Response:
    """Fetch locally available Ollama models from the Ollama API."""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:11434/api/tags", timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return web.json_response({"available": True, "models": models})
                return web.json_response({"available": False, "models": [], "error": f"HTTP {resp.status}"})
    except Exception as e:
        return web.json_response({"available": False, "models": [], "error": str(e)})


# ── Provider test helpers ─────────────────────────────────────────────────────

async def _test_claude(api_key: str, model: str) -> dict:
    if not api_key or api_key == "***":
        return {"success": False, "error": "No API key provided"}
    import aiohttp
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model or "claude-haiku-4-3",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "ping"}],
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status in (200, 400):
                    # 400 is fine — it means the key is valid but the request was bad
                    return {"success": True}
                body = await resp.text()
                return {"success": False, "error": f"HTTP {resp.status}: {body[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _test_gemini(api_key: str, model: str) -> dict:
    if not api_key or api_key == "***":
        return {"success": False, "error": "No API key provided"}
    import aiohttp
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model or 'gemini-2.0-flash'}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": "ping"}]}]}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status in (200, 400):
                    return {"success": True}
                body = await resp.text()
                return {"success": False, "error": f"HTTP {resp.status}: {body[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _test_ollama(endpoint: str, model: str) -> dict:
    import aiohttp
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{endpoint}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return {"success": True}
                return {"success": False, "error": f"Ollama returned HTTP {resp.status}"}
    except Exception as e:
        return {"success": False, "error": f"Cannot reach Ollama: {e}"}


async def _test_custom(endpoint: str, api_key: str) -> dict:
    if not endpoint:
        return {"success": False, "error": "Endpoint URL is required"}
    import aiohttp
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(endpoint, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return {"success": resp.status < 500}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── Generative functions ──────────────────────────────────────────────────────

async def _gen_claude(api_key: str, model: str, prompt: str) -> str:
    import aiohttp
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model or "claude-haiku-4-3",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with aiohttp.ClientSession() as s:
        async with s.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()
            if resp.status == 200:
                return data.get("content", [{"text": "No content"}])[0].get("text", "No content")
            return f"Error HTTP {resp.status}: {data.get('error', {}).get('message', 'Unknown')}"

async def _gen_gemini(api_key: str, model: str, prompt: str) -> str:
    import aiohttp
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model or 'gemini-2.0-flash'}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()
            if resp.status == 200:
                return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{"text": "No content"}])[0].get("text", "No content")
            return f"Error HTTP {resp.status}: {data.get('error', {}).get('message', 'Unknown')}"

async def _gen_ollama(endpoint: str, model: str, prompt: str) -> str:
    import aiohttp
    payload = {"model": model or "llama3:latest", "prompt": prompt, "stream": False}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{endpoint}/api/generate", json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("response", "No response")
            return f"Ollama HTTP {resp.status}"

async def _gen_custom(endpoint: str, api_key: str, prompt: str) -> str:
    import aiohttp
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"model": "custom", "messages": [{"role": "user", "content": prompt}]}
    async with aiohttp.ClientSession() as s:
        async with s.post(endpoint, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", str(data))
            return f"Custom HTTP {resp.status}"

