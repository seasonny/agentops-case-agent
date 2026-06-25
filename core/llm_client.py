import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from core.logging import log_warning

SUPPORTED_PROVIDERS = frozenset({"openai", "gemini"})

_PROVIDER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "api_key_env_fallbacks": ["GOOGLE_API_KEY"],
        "model": "gemini-3.1-flash-lite",
    },
}


def _normalize_provider(llm_config: Dict[str, Any]) -> str:
    return str(llm_config.get("provider", "openai")).strip().lower()


def _api_key_env_candidates(llm_config: Dict[str, Any]) -> List[str]:
    provider = _normalize_provider(llm_config)
    defaults = _PROVIDER_DEFAULTS.get(provider, {})
    if llm_config.get("api_key_env"):
        return [str(llm_config["api_key_env"])]
    candidates = [defaults.get("api_key_env", "OPENAI_API_KEY")]
    candidates.extend(defaults.get("api_key_env_fallbacks", []))
    return candidates


def _resolve_api_key(llm_config: Dict[str, Any]) -> Tuple[Optional[str], str]:
    candidates = _api_key_env_candidates(llm_config)
    for env_name in candidates:
        value = os.getenv(env_name, "").strip()
        if value:
            return value, env_name
    return None, candidates[0]


def _provider_package_available(provider: str) -> bool:
    try:
        if provider == "openai":
            import openai  # noqa: F401
        elif provider == "gemini":
            from google import genai  # noqa: F401
        else:
            return False
    except ImportError:
        return False
    return True


def _resolved_model(llm_config: Dict[str, Any]) -> str:
    provider = _normalize_provider(llm_config)
    defaults = _PROVIDER_DEFAULTS.get(provider, {})
    return str(llm_config.get("model") or defaults.get("model", "gpt-4o-mini"))


def _looks_like_google_api_key(api_key: str) -> bool:
    return api_key.startswith("AIza")


def _looks_like_openai_api_key(api_key: str) -> bool:
    return api_key.startswith("sk-")


def validate_provider_key_match(llm_config: Dict[str, Any]) -> Optional[str]:
    """Return a warning message if API key format does not match provider."""
    api_key, env_name = _resolve_api_key(llm_config)
    if not api_key:
        return None
    provider = _normalize_provider(llm_config)
    if provider == "openai" and _looks_like_google_api_key(api_key):
        return (
            f"環境變數 {env_name} 看起來是 Google/Gemini API key（AIza...），"
            f"但 config 的 llm.provider 為 openai。"
            f"請改為 \"provider\": \"gemini\" 並使用 GEMINI_API_KEY，"
            f"或改用 OpenAI 的 sk-... key。"
        )
    if provider == "gemini" and _looks_like_openai_api_key(api_key):
        return (
            f"環境變數 {env_name} 看起來是 OpenAI API key（sk-...），"
            f"但 llm.provider 為 gemini。請確認 provider 與 key 一致。"
        )
    return None


def is_llm_available(llm_config: Dict[str, Any]) -> bool:
    provider = _normalize_provider(llm_config)
    if provider not in SUPPORTED_PROVIDERS:
        return False
    api_key, _ = _resolve_api_key(llm_config)
    if not api_key:
        return False
    return _provider_package_available(provider)


def require_llm(llm_config: Dict[str, Any]) -> None:
    mismatch = validate_provider_key_match(llm_config)
    if mismatch:
        log_warning("llm_provider_key_mismatch", hint=mismatch)

    if is_llm_available(llm_config):
        return

    provider = _normalize_provider(llm_config)
    env_candidates = _api_key_env_candidates(llm_config)
    env_hint = " 或 ".join(env_candidates)

    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        log_warning(
            "llm_required",
            hint=(
                f"不支援的 LLM provider: {provider!r}。"
                f"請在 config 的 llm.provider 設定為其中之一：{supported}。"
            ),
        )
        return

    if not _provider_package_available(provider):
        package_hint = "openai" if provider == "openai" else "google-genai"
        log_warning(
            "llm_required",
            hint=(
                f"Agent 需要 LLM（provider={provider}）才能進行 triage、解讀、撰寫回覆與收斂判斷。"
                f"請安裝套件 pip install {package_hint}，並設定環境變數 {env_hint}。"
            ),
        )
        return

    log_warning(
        "llm_required",
        hint=(
            f"Agent 需要 LLM（provider={provider}）才能進行 triage、解讀、撰寫回覆與收斂判斷。"
            f"請設定環境變數 {env_hint}。"
        ),
    )


def parse_json_response(content: str) -> Optional[Dict[str, Any]]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _chat_openai_json(
    llm_config: Dict[str, Any],
    *,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> Optional[Dict[str, Any]]:
    try:
        from openai import OpenAI
    except ImportError:
        log_warning("openai_package_missing")
        return None

    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    base_url = llm_config.get("base_url")
    if base_url:
        client_kwargs["base_url"] = str(base_url)

    model = _resolved_model(llm_config)
    temperature = llm_config.get("temperature", 0)

    try:
        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        return parse_json_response(content)
    except Exception as exc:
        log_warning("llm_request_failed", provider="openai", error=str(exc))
        return None


def _chat_gemini_json(
    llm_config: Dict[str, Any],
    *,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> Optional[Dict[str, Any]]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log_warning("google_genai_package_missing")
        return None

    model = _resolved_model(llm_config)
    temperature = llm_config.get("temperature", 0)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        content = getattr(response, "text", None) or ""
        return parse_json_response(content)
    except Exception as exc:
        log_warning("llm_request_failed", provider="gemini", error=str(exc))
        return None


def _chat_openai_text(
    llm_config: Dict[str, Any],
    *,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> Optional[str]:
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    base_url = llm_config.get("base_url")
    if base_url:
        client_kwargs["base_url"] = str(base_url)

    model = _resolved_model(llm_config)
    temperature = llm_config.get("temperature", 0.2)

    try:
        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip() or None
    except Exception as exc:
        log_warning("llm_text_request_failed", provider="openai", error=str(exc))
        return None


def _chat_gemini_text(
    llm_config: Dict[str, Any],
    *,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> Optional[str]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    model = _resolved_model(llm_config)
    temperature = llm_config.get("temperature", 0.2)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
            ),
        )
        content = getattr(response, "text", None) or ""
        return content.strip() or None
    except Exception as exc:
        log_warning("llm_text_request_failed", provider="gemini", error=str(exc))
        return None


def chat_json(
    llm_config: Dict[str, Any],
    *,
    system_prompt: str,
    user_prompt: str,
) -> Optional[Dict[str, Any]]:
    provider = _normalize_provider(llm_config)
    if not is_llm_available(llm_config):
        _, env_name = _resolve_api_key(llm_config)
        log_warning("llm_api_key_missing", provider=provider, env=env_name)
        return None

    if provider not in SUPPORTED_PROVIDERS:
        log_warning("unsupported_llm_provider", provider=provider)
        return None

    api_key, _ = _resolve_api_key(llm_config)
    if not api_key:
        return None

    if provider == "openai":
        return _chat_openai_json(
            llm_config,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    if provider == "gemini":
        return _chat_gemini_json(
            llm_config,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    return None


def chat_text(
    llm_config: Dict[str, Any],
    *,
    system_prompt: str,
    user_prompt: str,
) -> Optional[str]:
    provider = _normalize_provider(llm_config)
    if not is_llm_available(llm_config):
        return None

    if provider not in SUPPORTED_PROVIDERS:
        return None

    api_key, _ = _resolve_api_key(llm_config)
    if not api_key:
        return None

    if provider == "openai":
        return _chat_openai_text(
            llm_config,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    if provider == "gemini":
        return _chat_gemini_text(
            llm_config,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    return None
