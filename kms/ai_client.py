from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import requests

from kms.config import Settings


class AiNotConfigured(RuntimeError):
    pass


class AiRequestError(RuntimeError):
    pass


def _headers(settings: Settings) -> dict[str, str]:
    return {
        'Authorization': f'Bearer {settings.ai_api_key}',
        'Content-Type': 'application/json',
    }


def _completions_url(settings: Settings) -> str:
    return settings.ai_base_url.rstrip('/') + '/chat/completions'


def chat_text(settings: Settings, messages: list[dict[str, str]]) -> str:
    if not settings.ai_ready:
        raise AiNotConfigured('AI is not configured')
    try:
        resp = requests.post(
            _completions_url(settings),
            headers=_headers(settings),
            json={
                'model': settings.ai_model,
                'temperature': 0.2,
                'messages': messages,
            },
            timeout=settings.ai_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise AiRequestError(str(exc)) from exc
    if resp.status_code >= 400:
        raise AiRequestError(f'AI HTTP {resp.status_code}: {resp.text[:400]}')
    try:
        return str(resp.json()['choices'][0]['message']['content'] or '')
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise AiRequestError('unexpected AI response') from exc


def chat_stream(settings: Settings, messages: list[dict[str, str]]) -> Iterator[str]:
    if not settings.ai_ready:
        raise AiNotConfigured('AI is not configured')
    try:
        resp = requests.post(
            _completions_url(settings),
            headers=_headers(settings),
            json={
                'model': settings.ai_model,
                'temperature': 0.2,
                'messages': messages,
                'stream': True,
            },
            timeout=(10, settings.ai_timeout_seconds),
            stream=True,
        )
    except requests.RequestException as exc:
        raise AiRequestError(str(exc)) from exc
    if resp.status_code >= 400:
        body = resp.text[:400]
        resp.close()
        raise AiRequestError(f'AI HTTP {resp.status_code}: {body}')
    try:
        yielded = False
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if line.startswith('data:'):
                line = line[5:].strip()
            if not line or line == '[DONE]':
                if line == '[DONE]':
                    break
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                delta = data['choices'][0].get('delta') or {}
                piece = delta.get('content') or ''
            except (KeyError, IndexError, TypeError):
                continue
            if piece:
                yielded = True
                yield str(piece)
        if not yielded:
            raise AiRequestError('empty stream')
    except AiRequestError:
        raise
    except requests.RequestException as exc:
        raise AiRequestError(str(exc)) from exc
    finally:
        resp.close()


def chat_json(settings: Settings, messages: list[dict[str, str]]) -> dict[str, Any]:
    if not settings.ai_ready:
        raise AiNotConfigured('AI is not configured')
    url = settings.ai_base_url.rstrip('/') + '/chat/completions'
    try:
        resp = requests.post(
            url,
            headers={
                'Authorization': f'Bearer {settings.ai_api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': settings.ai_model,
                'temperature': 0.1,
                'messages': messages,
                'response_format': {'type': 'json_object'},
            },
            timeout=settings.ai_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise AiRequestError(str(exc)) from exc
    if resp.status_code >= 400:
        raise AiRequestError(f'AI HTTP {resp.status_code}: {resp.text[:400]}')
    try:
        content = resp.json()['choices'][0]['message']['content']
    except (KeyError, IndexError, ValueError) as exc:
        raise AiRequestError('unexpected AI response') from exc
    return _loads_json(content)


def _loads_json(text: str) -> dict[str, Any]:
    text = (text or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?', '', text)
        text = re.sub(r'```$', '', text).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise AiRequestError('AI JSON must be an object')
    return data
