import json
import re
from typing import Any, Dict, List, Optional

def extract_json_array(raw: str) -> Optional[List[Dict[str, Any]]]:
    """
    Robustly extracts a JSON array of objects from LLM output.
    Handles:
    - Direct JSON string
    - Markdown fenced blocks (```json ... ``` or ``` ... ```)
    - Preamble/postamble conversational text
    - Nested brackets and escaped characters
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip()

    # 1. Direct JSON parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # 2. Markdown fenced code block extraction
    fence_pattern = re.compile(r'```(?:json)?\s*(\[\s*\{.*?\}\s*\])\s*```', re.DOTALL)
    fence_matches = fence_pattern.findall(cleaned)
    for match in fence_matches:
        try:
            data = json.loads(match.strip())
            if isinstance(data, list):
                return data
        except Exception:
            continue

    # Generic fenced match
    generic_fence = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.DOTALL)
    for match in generic_fence.findall(cleaned):
        try:
            data = json.loads(match.strip())
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # 3. Outer bracket counter extraction (tracks nesting & quotes)
    bracket_candidate = _extract_outermost_brackets(cleaned, '[', ']')
    if bracket_candidate:
        try:
            data = json.loads(bracket_candidate)
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # 4. Scanning raw_decode fallback
    decoder = json.JSONDecoder()
    for idx, char in enumerate(cleaned):
        if char == '[':
            try:
                data, _ = decoder.raw_decode(cleaned[idx:])
                if isinstance(data, list):
                    return data
            except Exception:
                continue

    return None


def extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """
    Robustly extracts a JSON dictionary object from LLM output.
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip()

    # 1. Direct JSON parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Markdown fenced extraction
    fence_pattern = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)
    for match in fence_pattern.findall(cleaned):
        try:
            data = json.loads(match.strip())
            if isinstance(data, dict):
                return data
        except Exception:
            continue

    # 3. Outermost bracket counter
    bracket_candidate = _extract_outermost_brackets(cleaned, '{', '}')
    if bracket_candidate:
        try:
            data = json.loads(bracket_candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 4. Scanning raw_decode
    decoder = json.JSONDecoder()
    for idx, char in enumerate(cleaned):
        if char == '{':
            try:
                data, _ = decoder.raw_decode(cleaned[idx:])
                if isinstance(data, dict):
                    return data
            except Exception:
                continue

    return None


def _extract_outermost_brackets(text: str, open_char: str, close_char: str) -> Optional[str]:
    """Finds the substring between the first open bracket and its matching close bracket, respecting string literals."""
    in_string = False
    escape = False
    quote_char = ''
    depth = 0
    start_idx = -1

    for i, char in enumerate(text):
        if escape:
            escape = False
            continue

        if char == '\\':
            if in_string:
                escape = True
            continue

        if char in ('"', "'"):
            if not in_string:
                in_string = True
                quote_char = char
            elif quote_char == char:
                in_string = False
            continue

        if not in_string:
            if char == open_char:
                if depth == 0:
                    start_idx = i
                depth += 1
            elif char == close_char:
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start_idx != -1:
                        return text[start_idx:i+1]

    return None
