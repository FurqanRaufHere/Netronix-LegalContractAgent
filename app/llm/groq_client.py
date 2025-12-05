# from langchain.chat_models import ChatOpenAI
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

import os
from dotenv import load_dotenv
# Explicitly load .env from project root before any os.getenv calls
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
import json
import time
import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Default GROQ endpoint (OpenAI-compatible path)
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_CHAT_URL = GROQ_BASE_URL.rstrip("/") + "/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")  # override if needed
DEFAULT_TIMEOUT = 20  # seconds
MAX_RETRIES = 2
RETRY_DELAY = 1.0  # seconds


SYSTEM_PROMPT = "You are a contract risk assistant — reply in valid JSON only."

# The user prompt wrapper is in PROMPT.md but we include a helper here for runtime usage
JSON_SCHEMA_EXPLANATION = (
    "Return JSON only, with exactly these keys:\n"
    "{\n"
    '  "risk_score": int (0-5),\n'
    '  "reasons": [str],\n'
    '  "redline": str\n'
    "}\n\n"
    "Be concise. Do not include extra commentary or markdown. If you cannot assess, set risk_score to 0 and return an empty reasons array and empty redline."
)

# Langchain-based LLM call for Groq (must be after constants)
def call_groq_chat_langchain(
    user_prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 512,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Use Langchain's ChatOpenAI and PromptTemplate to call Groq LLM endpoint.
    Returns parsed JSON dict or raises ValueError.
    """
    if not GROQ_API_KEY:
        raise EnvironmentError("GROQ_API_KEY not set in environment.")

    # Langchain OpenAI-compatible chat model for Groq
    llm = ChatOpenAI(
        openai_api_key=GROQ_API_KEY,
        openai_api_base=GROQ_BASE_URL,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout=timeout,
    )

    # Prompt management
    prompt = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template("{system}"),
        HumanMessagePromptTemplate.from_template("{user}"),
    ])
    formatted_prompt = prompt.format_messages(system=system_prompt, user=user_prompt)

    # Call LLM
    response = llm(formatted_prompt)
    # Langchain returns an AIMessage with .content
    content = getattr(response, "content", None)
    if not content:
        raise ValueError("No content returned from LLM response.")
    parsed = _parse_json_strict(content)
    if parsed is None:
        raise ValueError("LLM returned non-JSON content.")
    if not isinstance(parsed, dict):
        raise ValueError("Parsed JSON is not an object.")
    return parsed


def _strip_code_fences(text: str) -> str:
    """Remove Markdown code fences if present."""
    if not text:
        return text
    text = text.strip()
    # remove triple-backtick fenced blocks around content
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        # remove first and last line (the fences)
        return "\n".join(lines[1:-1]).strip()
    return text


def _extract_first_json(text: str) -> Optional[str]:
    """
    Extract the first balanced JSON object from `text` using a stack-based approach.
    Returns the substring or None if not found.
    """
    if not text:
        return None
    start_idx = None
    stack = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if start_idx is None:
                start_idx = i
            stack += 1
        elif ch == "}":
            if stack > 0:
                stack -= 1
                if stack == 0 and start_idx is not None:
                    return text[start_idx : i + 1]
    return None


def _parse_json_strict(text: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse JSON from the string. Returns dict or None."""
    if not text:
        return None
    # Strip code fences first
    s = _strip_code_fences(text)
    # Try direct parse
    try:
        return json.loads(s)
    except Exception:
        # extract balanced JSON substring
        candidate = _extract_first_json(s)
        if candidate:
            try:
                return json.loads(candidate)
            except Exception:
                logger.debug("Failed parsing extracted JSON substring.")
        # last resort: try to find a prefix/suffix that makes valid JSON by trimming
        # (avoid complex heuristics here)
    return None


def call_groq_chat(
    user_prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 512,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = MAX_RETRIES,
) -> Dict[str, Any]:
    """
    Call the GROQ / OpenAI-compatible chat completions endpoint.
    Returns the parsed JSON dict (matching the schema) or raises a ValueError on unrecoverable failure.

    Retries on network errors or non-200 responses up to `max_retries`.
    """
    if not GROQ_API_KEY:
        raise EnvironmentError("GROQ_API_KEY not set in environment.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_exc = None
    for attempt in range(1, max_retries + 2):  # +1 for first attempt
        try:
            resp = requests.post(GROQ_CHAT_URL, headers=headers, json=payload, timeout=timeout)
            # raise for HTTP errors
            resp.raise_for_status()
            j = resp.json()
            # Typical OpenAI-compatible response: choices[0].message.content
            content = None
            if isinstance(j, dict):
                choices = j.get("choices")
                if choices and isinstance(choices, list) and len(choices) > 0:
                    # support both OpenAI style and other minor variations
                    first = choices[0]
                    if isinstance(first, dict) and "message" in first and isinstance(first["message"], dict):
                        content = first["message"].get("content") or ""
                    else:
                        # sometimes choices[0]["text"] exists
                        content = first.get("text") or ""
            if content is None:
                # fallback: try top-level "text"
                content = j.get("text") if isinstance(j, dict) else None
            if not content:
                raise ValueError("No content returned from LLM response.")

            # parse JSON safely
            parsed = _parse_json_strict(content)
            if parsed is None:
                # If parsing failed, log and raise with content for debugging
                logger.debug("LLM returned non-JSON content: %s", content[:500])
                raise ValueError("LLM returned non-JSON content.")
            # Basic validation: ensure keys exist
            if not isinstance(parsed, dict):
                raise ValueError("Parsed JSON is not an object.")
            # Return parsed; schema validation can be done by caller
            return parsed
        except Exception as e:
            # Catch any exception including network errors and treat as retryable network/request error.
            last_exc = e
            logger.warning("Network/request error on GROQ attempt %d/%d: %s", attempt, max_retries + 1, str(e))
        # Backoff before retrying
        if attempt <= max_retries:
            time.sleep(RETRY_DELAY * attempt)
    # If we get here, all attempts failed
    raise RuntimeError(f"GROQ call failed after {max_retries+1} attempts. Last error: {last_exc}")
