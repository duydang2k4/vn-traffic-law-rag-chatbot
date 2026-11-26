"""Server-side configuration and requests for Gemini, Groq, and Ollama."""

import http.client
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from urllib.parse import quote

from scripts import ROOT

GEMINI_MODEL = 'gemini-3.1-flash-lite'
GEMINI_LIMIT_MESSAGE = 'Đã chạm hạn mức Gemini. Vui lòng thử lại sau.'
GROQ_MODEL = 'openai/gpt-oss-120b'
GROQ_LIMIT_MESSAGE = 'Đã chạm hạn mức Groq. Vui lòng thử lại sau.'
OLLAMA_CLOUD_MODEL = 'gpt-oss:20b'
OLLAMA_LIMIT_MESSAGE = 'Đã chạm hạn mức Ollama Cloud. Vui lòng thử lại sau.'


class LLMError(ValueError):
    pass


def retry_delay(error, read_google_details=False):
    delays = []
    header = error.headers.get('Retry-After', '') if error.headers else ''
    if header.isascii() and header.isdecimal() and len(header) <= 10:
        delays.append(int(header))
    if read_google_details:
        try:
            details = json.loads(error.read(65536))['error']['details']
            for detail in details:
                if detail.get('@type') == 'type.googleapis.com/google.rpc.RetryInfo':
                    duration = detail['retryDelay']
                    if isinstance(duration, str) and duration.endswith('s'):
                        seconds = float(duration[:-1])
                        if math.isfinite(seconds) and seconds >= 0:
                            delays.append(seconds)
        except (ValueError, TypeError, KeyError, AttributeError, OSError, http.client.HTTPException):
            pass
    return max(1, max(delays, default=60))


class LLM:
    def __init__(self, provider, model, api_key='', *, rpm=0, rpd=0):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.rpm, self.rpd = (30, 1000) if provider == 'groq' else (rpm, rpd)
        self._lock = threading.Lock()
        self._requests = deque()
        self._retry_at = 0
        self._cloud_slots = threading.BoundedSemaphore(3)

    def _reserve_request(self, limit_message):
        with self._lock:
            now = time.monotonic()
            if now < self._retry_at:
                raise LLMError(limit_message)
            window = 86400 if self.rpd else 60
            while self._requests and now - self._requests[0] >= window:
                self._requests.popleft()
            if self.rpd and len(self._requests) >= self.rpd:
                raise LLMError(limit_message)
            if self.rpm and len(self._requests) >= self.rpm and now - self._requests[-self.rpm] < 60:
                raise LLMError(limit_message)
            if self.rpm or self.rpd:
                self._requests.append(now)

    def complete(self, messages):
        if self.provider != 'ollama-cloud':
            return self._complete(messages)
        if not self.api_key:
            raise LLMError('Thiếu OLLAMA_API_KEY trong cấu hình máy chủ.')
        with self._lock:
            if time.monotonic() < self._retry_at:
                raise LLMError(OLLAMA_LIMIT_MESSAGE)
            if not self._cloud_slots.acquire(blocking=False):
                raise LLMError(OLLAMA_LIMIT_MESSAGE)
        try:
            return self._complete(messages)
        finally:
            self._cloud_slots.release()

    def _complete(self, messages):
        headers = {'Content-Type': 'application/json'}
        payload = {'model': self.model, 'messages': messages, 'stream': False}
        timeout = 60
        limit_message = None
        if self.provider == 'gemini':
            if not self.api_key:
                raise LLMError('Thiếu GEMINI_API_KEY trong cấu hình máy chủ.')
            model = quote(self.model.removeprefix('models/'), safe='')
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
            headers['x-goog-api-key'] = self.api_key
            payload = {
                'systemInstruction': {'parts': [
                    {'text': message['content']} for message in messages if message['role'] == 'system'
                ]},
                'contents': [
                    {'role': 'user', 'parts': [{'text': message['content']}]}
                    for message in messages if message['role'] == 'user'
                ],
                'generationConfig': {'maxOutputTokens': 1024},
            }
            timeout = 30
            limit_message = GEMINI_LIMIT_MESSAGE
            self._reserve_request(limit_message)
        elif self.provider == 'groq':
            if not self.api_key:
                raise LLMError('Thiếu GROQ_API_KEY trong cấu hình máy chủ.')
            url = 'https://api.groq.com/openai/v1/chat/completions'
            headers['Authorization'] = 'Bearer ' + self.api_key
            payload.update(temperature=0, max_completion_tokens=1024,
                           reasoning_effort='low', include_reasoning=False)
            timeout = 20
            limit_message = GROQ_LIMIT_MESSAGE
            self._reserve_request(limit_message)
        elif self.provider == 'ollama-cloud':
            url = 'https://ollama.com/api/chat'
            headers['Authorization'] = 'Bearer ' + self.api_key
            payload['options'] = {'temperature': 0, 'num_predict': 1024}
            if self.model.startswith('gpt-oss:'):
                payload['think'] = 'low'
            limit_message = OLLAMA_LIMIT_MESSAGE
        else:
            url = 'http://127.0.0.1:11434/api/chat'
            payload['options'] = {'temperature': 0}

        request = urllib.request.Request(url, json.dumps(payload).encode(), headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.load(response)
            if self.provider == 'gemini':
                candidates = data.get('candidates', [])
                if not candidates or candidates[0].get('finishReason') != 'STOP':
                    raise LLMError('Gemini chưa trả lời hoàn chỉnh.')
                content = ''.join(part['text'] for part in candidates[0]['content']['parts']
                                  if 'text' in part and not part.get('thought'))
            elif self.provider == 'groq':
                choice = data['choices'][0]
                if choice['finish_reason'] != 'stop':
                    raise LLMError('Mô hình chưa trả lời hoàn chỉnh.')
                content = choice['message']['content']
            else:
                if self.provider == 'ollama-cloud' and (
                        data.get('done') is False or data.get('done_reason') == 'length'):
                    raise LLMError('Mô hình chưa trả lời hoàn chỉnh.')
                content = data['message']['content']
        except urllib.error.HTTPError as error:
            with error:
                if limit_message and error.code == 429:
                    delay = retry_delay(error, read_google_details=self.provider == 'gemini')
                    with self._lock:
                        self._retry_at = max(self._retry_at, time.monotonic() + delay)
                    raise LLMError(limit_message) from None
                raise LLMError(f'Dịch vụ mô hình trả lỗi HTTP {error.code}.') from None
        except LLMError:
            raise
        except (OSError, http.client.HTTPException):
            raise LLMError('Không nhận được phản hồi từ dịch vụ mô hình.') from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise LLMError('Phản hồi từ dịch vụ mô hình không hợp lệ.') from None
        if not isinstance(content, str):
            raise LLMError('Mô hình chưa trả lời bằng văn bản.')
        return content.strip()


def load_llm():
    """Read KEY=value settings from the project .env, with environment overrides."""
    settings = {}
    try:
        lines = (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        key, separator, value = line.strip().partition('=')
        if separator and not key.startswith('#'):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            settings[key.strip()] = value

    def setting(key, default=''):
        return os.environ.get(key, settings.get(key, default)).strip()

    def limit(key):
        value = setting(key) or '0'
        try:
            count = int(value)
            if count >= 0:
                return count
        except ValueError:
            pass
        raise LLMError(f'{key} phải là số nguyên không âm hoặc để trống.')

    provider = setting('LLM_PROVIDER').lower()
    if provider in ('', 'extractive'):
        return None
    if provider == 'gemini':
        model = setting('GEMINI_MODEL') or GEMINI_MODEL
        return LLM(provider, model, setting('GEMINI_API_KEY'),
                   rpm=limit('GEMINI_RPM'), rpd=limit('GEMINI_RPD'))
    if provider == 'groq':
        return LLM(provider, GROQ_MODEL, setting('GROQ_API_KEY'))
    if provider == 'ollama-cloud':
        model = setting('OLLAMA_CLOUD_MODEL') or OLLAMA_CLOUD_MODEL
        return LLM(provider, model, setting('OLLAMA_API_KEY'))
    if provider == 'ollama':
        model = setting('OLLAMA_MODEL')
        if not model:
            raise LLMError('Cần đặt OLLAMA_MODEL thành tên mô hình đã cài.')
        return LLM(provider, model)
    raise LLMError('LLM_PROVIDER phải là gemini, ollama-cloud, ollama, groq hoặc extractive.')
