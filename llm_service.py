"""LLM integration — OpenAI or Anthropic with rule-based fallback."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def _env(key):
    return (os.environ.get(key) or '').strip()


def llm_configured():
    return bool(_env('OPENAI_API_KEY') or _env('ANTHROPIC_API_KEY'))


def chat_completion(messages, *, system_prompt=None, max_tokens=1200, temperature=0.35):
    """Return assistant text. Uses OpenAI first, then Anthropic, then None."""
    if _env('OPENAI_API_KEY'):
        text = _openai_chat(messages, system_prompt=system_prompt, max_tokens=max_tokens, temperature=temperature)
        if text:
            return text, 'openai'
    if _env('ANTHROPIC_API_KEY'):
        text = _anthropic_chat(messages, system_prompt=system_prompt, max_tokens=max_tokens, temperature=temperature)
        if text:
            return text, 'anthropic'
    return None, None


def _openai_chat(messages, system_prompt=None, max_tokens=1200, temperature=0.35):
    api_key = _env('OPENAI_API_KEY')
    model = _env('OPENAI_MODEL') or 'gpt-4o-mini'
    payload_messages = []
    if system_prompt:
        payload_messages.append({'role': 'system', 'content': system_prompt})
    payload_messages.extend(messages)
    body = json.dumps({
        'model': model,
        'messages': payload_messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=body,
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return (data.get('choices') or [{}])[0].get('message', {}).get('content', '').strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None


def _anthropic_chat(messages, system_prompt=None, max_tokens=1200, temperature=0.35):
    api_key = _env('ANTHROPIC_API_KEY')
    model = _env('ANTHROPIC_MODEL') or 'claude-3-5-haiku-20241022'
    body = json.dumps({
        'model': model,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'system': system_prompt or 'You are a construction project management assistant for Case PM.',
        'messages': [{'role': m['role'], 'content': m['content']} for m in messages if m.get('role') in ('user', 'assistant')],
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=body,
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        parts = data.get('content') or []
        return ''.join(p.get('text', '') for p in parts if p.get('type') == 'text').strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None
