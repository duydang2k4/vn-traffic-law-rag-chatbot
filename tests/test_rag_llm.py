import io
import json
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.rag.baseline_rag import generate
from scripts.rag.llm import (
    GEMINI_MODEL, GROQ_LIMIT_MESSAGE, GROQ_MODEL, OLLAMA_CLOUD_MODEL,
    LLM, LLMError, load_llm,
)


class RagLLMTests(unittest.TestCase):
    @patch('scripts.rag.llm.urllib.request.urlopen')
    def test_citations_allow_intro_line_within_a_sourced_paragraph(self, urlopen):
        urlopen.side_effect = [
            self.completion('What the source says:\nThe original rule [1].'),
            self.completion('Uncited paragraph.\n\nThe original rule [1].'),
        ]
        self.assertEqual(generate(self.llm, 'Question?', self.hits),
                         'What the source says:\nThe original rule [1].')
        with self.assertRaises(LLMError):
            generate(self.llm, 'Question?', self.hits)

    def setUp(self):
        self.llm = LLM('groq', GROQ_MODEL, 'test-key')
        self.hits = [{
            'number': 'Test document', 'edition': 'original', 'annex': None,
            'article': '1', 'clause': None, 'point': None, 'parents': [],
            'text': 'Example evidence.',
        }]

    def completion(self, content):
        return io.BytesIO(json.dumps({'choices': [{
            'finish_reason': 'stop', 'message': {'content': content},
        }]}).encode())

    def ollama_completion(self):
        return io.BytesIO(b'{"done":true,"done_reason":"stop",'
                          b'"message":{"content":"From the evidence [1]"}}')

    def gemini_completion(self, finish='STOP'):
        return io.BytesIO(json.dumps({'candidates': [{
            'finishReason': finish, 'content': {'parts': [
                {'text': 'Internal thought', 'thought': True},
                {'text': 'From the evidence '}, {'text': '[1]'},
            ]},
        }]}).encode())

    @patch('scripts.rag.llm.urllib.request.urlopen')
    def test_gemini_uses_api_key_and_only_accepts_complete_visible_text(self, urlopen):
        with patch.dict('os.environ', {'LLM_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'gemini-test-key',
                                       'GEMINI_MODEL': '', 'GEMINI_RPM': '10', 'GEMINI_RPD': '100'}):
            gemini = load_llm()
        self.assertEqual((gemini.rpm, gemini.rpd), (10, 100))
        urlopen.side_effect = [self.gemini_completion(), self.gemini_completion('MAX_TOKENS')]
        self.assertEqual(generate(gemini, 'Question?', self.hits), 'From the evidence [1]')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url,
                         f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent')
        self.assertEqual(request.get_header('X-goog-api-key'), 'gemini-test-key')
        payload = json.loads(request.data)
        self.assertIn('[1]', payload['systemInstruction']['parts'][0]['text'])
        self.assertIn('Example evidence.', payload['contents'][0]['parts'][0]['text'])
        with self.assertRaises(LLMError):
            generate(gemini, 'Question?', self.hits)

    @patch('scripts.rag.llm.time.monotonic')
    @patch('scripts.rag.llm.urllib.request.urlopen')
    def test_gemini_cooldown_uses_retry_info_from_response(self, urlopen, now):
        gemini = LLM('gemini', GEMINI_MODEL, 'test-key')
        body = {'error': {'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo',
                                       'retryDelay': '42.5s'}]}}
        urlopen.side_effect = [
            HTTPError('https://example.com', 429, 'Limited', Message(),
                      io.BytesIO(json.dumps(body).encode())),
            self.gemini_completion(),
        ]
        now.return_value = 100
        with self.assertRaises(LLMError):
            generate(gemini, 'Question?', self.hits)
        now.return_value = 142
        with self.assertRaises(LLMError):
            generate(gemini, 'Question?', self.hits)
        self.assertEqual(urlopen.call_count, 1)
        now.return_value = 142.5
        self.assertEqual(generate(gemini, 'Question?', self.hits), 'From the evidence [1]')

    @patch('scripts.rag.llm.urllib.request.urlopen')
    def test_ollama_cloud_uses_api_key_and_native_chat_response(self, urlopen):
        with patch.dict('os.environ', {'LLM_PROVIDER': 'ollama-cloud',
                                       'OLLAMA_API_KEY': 'cloud-test-key',
                                       'OLLAMA_CLOUD_MODEL': 'gpt-oss:20b'}):
            cloud = load_llm()
        urlopen.return_value = self.ollama_completion()
        self.assertEqual(generate(cloud, 'Question?', self.hits), 'From the evidence [1]')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'https://ollama.com/api/chat')
        self.assertEqual(request.get_header('Authorization'), 'Bearer cloud-test-key')
        payload = json.loads(request.data)
        self.assertEqual(payload['model'], OLLAMA_CLOUD_MODEL)
        self.assertFalse(payload['stream'])
        self.assertIn('Example evidence.', payload['messages'][1]['content'])

    @patch('scripts.rag.llm.urllib.request.urlopen')
    def test_ollama_cloud_limits_concurrent_requests_and_releases_slots(self, urlopen):
        cloud = LLM('ollama-cloud', OLLAMA_CLOUD_MODEL, 'test-key')

        def request(*args, **kwargs):
            if urlopen.call_count < 3:
                cloud.complete([])
            elif urlopen.call_count == 3:
                with self.assertRaises(LLMError):
                    cloud.complete([])
            return self.ollama_completion()

        urlopen.side_effect = request
        cloud.complete([])
        self.assertEqual(urlopen.call_count, 3)
        cloud.complete([])
        self.assertEqual(urlopen.call_count, 4)

    @patch('scripts.rag.llm.urllib.request.urlopen')
    def test_groq_request_contains_evidence_and_requires_valid_citations(self, urlopen):
        urlopen.side_effect = [self.completion('From the evidence [1]'),
                               self.completion('From the evidence [2]')]
        self.assertEqual(generate(self.llm, 'Question?', self.hits), 'From the evidence [1]')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
        payload = json.loads(request.data)
        self.assertEqual(payload['model'], GROQ_MODEL)
        self.assertIn('[1] Test document', payload['messages'][1]['content'])
        self.assertIn('Example evidence.', payload['messages'][1]['content'])
        with self.assertRaises(LLMError):
            generate(self.llm, 'Question?', self.hits)

    @patch('scripts.rag.llm.time.monotonic')
    @patch('scripts.rag.llm.urllib.request.urlopen')
    def test_rate_limit_honors_retry_after_without_retrying(self, urlopen, now):
        cloud = LLM('ollama-cloud', OLLAMA_CLOUD_MODEL, 'test-key')
        for llm, response in ((self.llm, self.completion('From the evidence [1]')),
                              (cloud, self.ollama_completion())):
            with self.subTest(provider=llm.provider):
                now.return_value = 100
                headers = Message()
                headers['Retry-After'] = '90'
                urlopen.reset_mock()
                urlopen.side_effect = [
                    HTTPError('https://example.com', 429, 'Limited', headers, io.BytesIO()),
                    response,
                ]
                with self.assertRaises(LLMError):
                    llm.complete([])
                now.return_value = 189
                with self.assertRaises(LLMError):
                    llm.complete([])
                self.assertEqual(urlopen.call_count, 1)
                now.return_value = 190
                self.assertEqual(llm.complete([]), 'From the evidence [1]')

    @patch('scripts.rag.llm.time.monotonic')
    def test_local_request_limits(self, now):
        now.return_value = 1
        for _ in range(30):
            self.llm._reserve_request(GROQ_LIMIT_MESSAGE)
        with self.assertRaises(LLMError):
            self.llm._reserve_request(GROQ_LIMIT_MESSAGE)
        for request in range(970):
            now.return_value = 61 + request // 30 * 60
            self.llm._reserve_request(GROQ_LIMIT_MESSAGE)
        now.return_value += 60
        with self.assertRaises(LLMError):
            self.llm._reserve_request(GROQ_LIMIT_MESSAGE)
