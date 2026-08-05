"""Claude structured extraction of HRA-relevant facts from a model's paper text.
Forced tool-use call -> a fixed `literature` schema; cached by (id-free) text hash."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_STR_LIST = {"type": "array", "items": {"type": "string"}}
LITERATURE_TOOL = {
    "name": "record_model_facts",
    "description": "Record HRA-relevant facts extracted from a systems-biology model's paper.",
    "input_schema": {
        "type": "object",
        "properties": {
            "organs": _STR_LIST, "anatomical_structures": _STR_LIST, "tissues": _STR_LIST,
            "cell_types": _STR_LIST, "ftus": _STR_LIST,
            "disease": {"type": "string"}, "species": {"type": "string"},
            "model_type": {"type": "string"}, "scale": {"type": "string"},
            "key_process": {"type": "string"}, "summary": {"type": "string"},
            "candidate_uberon": _STR_LIST, "candidate_cl": _STR_LIST,
        },
        "required": ["organs", "anatomical_structures", "cell_types", "summary"],
    },
}
_MAX_CHARS = 40000  # full-text truncation budget


def _cache_get(cache_dir, key):
    if not cache_dir:
        return None
    p = Path(cache_dir) / (key + ".json")
    return json.loads(p.read_text()) if p.exists() else None


def _cache_put(cache_dir, key, value):
    if cache_dir:
        p = Path(cache_dir) / (key + ".json")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(value))
        os.replace(tmp, p)


def extract(name, abstract, fulltext, *, model="claude-haiku-4-5-20251001", client=None, cache_dir=None) -> dict:
    text = "\n\n".join(t for t in (abstract, fulltext) if t)[:_MAX_CHARS]
    if not text:
        return {}
    key = hashlib.sha256((model + "|" + (name or "") + "|" + text).encode()).hexdigest()
    cached = _cache_get(cache_dir, key)
    if cached is not None:
        return cached
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    prompt = (
        f"Model: {name}\n\nPaper text:\n{text}\n\n"
        "Extract the HRA-relevant facts using the record_model_facts tool. "
        "Only include organs/anatomical structures/cell types actually studied by the model. "
        "For candidate_uberon/candidate_cl, give CURIEs only when confident; else leave empty."
    )
    resp = client.messages.create(
        model=model, max_tokens=1024,
        tools=[LITERATURE_TOOL], tool_choice={"type": "tool", "name": "record_model_facts"},
        messages=[{"role": "user", "content": prompt}],
    )
    result = {}
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            result = dict(block.input)
            break
    _cache_put(cache_dir, key, result)
    return result
