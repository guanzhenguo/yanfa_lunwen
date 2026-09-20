from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from kms.api import create_app
from kms.catalog import Catalog
from kms.chat import ChatStore, collect_turn, retrieve_context, tokenize
from kms.config import load_settings
from kms.keywords import KeywordStore
from kms.kg import KnowledgeGraph
from kms.pdf_parse import ensure_document_parse, make_pdf_bytes
from kms.storage import LocalStore, object_key, sha256_file


class ChatQaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ['KMS_STORAGE'] = 'local'
        os.environ['KMS_CATALOG'] = str(root / 'catalog.sqlite')
        os.environ['KMS_LOCAL_ROOT'] = str(root / 'minio')
        os.environ['KMS_ADMIN_PASSWORD'] = 'admin123'
        os.environ['KMS_AI_API_KEY'] = ''

        pdf = root / 'sample.pdf'
        pdf.write_bytes(make_pdf_bytes(
            'Abstract\nStabilized perovskite phases for TOPCon tandem cells. '
            'Unique marker contact resistivity 12 mOhm after 400 C anneal.\n'
        ))
        store = LocalStore(root / 'minio', bucket='papers')
        digest = sha256_file(pdf)
        key = object_key(digest)
        store.put_file(key, pdf)
        catalog = Catalog(root / 'catalog.sqlite')
        keys = KeywordStore(catalog)
        self.doc_id = catalog.upsert_document({
            'doi': '10.1038/s41563-025-02367-8',
            'url': 'https://link.springer.com/article/10.1038/s41563-025-02367-8',
            'title': 'Stabilized perovskite phases for TOPCon tandem cells',
            'authors': 'Guan',
            'published': '2025',
            'description': 'Tunnel oxide passivated contact and perovskite tandem process notes.',
            'open_access': True,
            'storage_key': key,
            'sha256': digest,
        })
        keys.set_document_keywords(self.doc_id, ['TOPCon', 'perovskite'], source='test')
        ensure_document_parse(catalog, store, catalog.get_by_id(self.doc_id))
        catalog.close()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _login(self) -> None:
        res = self.client.post(
            '/api/auth/login',
            json={'username': 'admin', 'password': 'admin123'},
        )
        self.assertEqual(res.status_code, 200)

    def test_requires_login(self) -> None:
        res = self.client.get('/api/chat/threads')
        self.assertEqual(res.status_code, 401)

    def test_retrieve_hits_keyword_and_title(self) -> None:
        settings = load_settings()
        with Catalog(settings.catalog_path) as catalog:
            sources = retrieve_context(
                catalog,
                KeywordStore(catalog),
                KnowledgeGraph(catalog),
                'TOPCon perovskite tandem',
            )
        self.assertTrue(sources)
        self.assertEqual(sources[0]['paper_id'], self.doc_id)
        self.assertIn('TOPCon', sources[0]['keywords'])

    def test_retrieve_hits_parsed_body(self) -> None:
        settings = load_settings()
        with Catalog(settings.catalog_path) as catalog:
            sources = retrieve_context(
                catalog,
                KeywordStore(catalog),
                KnowledgeGraph(catalog),
                'contact resistivity 12 mOhm',
            )
        self.assertTrue(sources)
        self.assertEqual(sources[0]['paper_id'], self.doc_id)
        self.assertIn('12 mOhm', sources[0]['snippet'])
        self.assertTrue(sources[0].get('chunks'))
        self.assertTrue(any('bm25' in (src.get('fusion_sources') or []) or 'vector' in (src.get('fusion_sources') or []) for src in sources))

    def test_retrieve_hits_chinese_graph_labels(self) -> None:
        self._login()
        extracted = self.client.post(f'/api/papers/{self.doc_id}/kg/extract')
        self.assertEqual(extracted.status_code, 200, extracted.text)
        nodes = extracted.json()['nodes']
        self.assertTrue(any((node.get('label_zh') or '') == '钙钛矿' for node in nodes))
        settings = load_settings()
        with Catalog(settings.catalog_path) as catalog:
            sources = retrieve_context(
                catalog,
                KeywordStore(catalog),
                KnowledgeGraph(catalog),
                '钙钛矿钝化工艺',
            )
        self.assertTrue(sources)
        self.assertEqual(sources[0]['paper_id'], self.doc_id)
        self.assertTrue(any('钙钛矿' in (item or '') for item in sources[0]['graph']))
        self.assertTrue(any('具有关键词' in (item or '') for item in sources[0]['triples']))
        self.assertTrue(sources[0].get('chunks'))
        blob = ' '.join(item.get('text') or '' for item in sources[0]['chunks']).lower()
        self.assertTrue(
            'perovskite' in blob or 'topcon' in blob or '12 mohm' in blob,
            blob[:240],
        )

    def test_json_chat_without_model_returns_sources(self) -> None:
        self._login()
        res = self.client.post(
            '/api/chat?stream=false',
            json={'message': 'TOPCon 钙钛矿叠层工艺怎么做'},
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body['thread_id'])
        self.assertTrue(body['sources'])
        self.assertEqual(body['sources'][0]['paper_id'], self.doc_id)
        self.assertIn('TOPCon', body['content'])
        listed = self.client.get('/api/chat/threads')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        detail = self.client.get(f"/api/chat/threads/{body['thread_id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.json()['messages']), 2)

    def test_ndjson_stream_and_new_thread(self) -> None:
        self._login()
        first = self.client.post(
            '/api/chat',
            json={'message': 'What is TOPCon passivation?'},
        )
        self.assertEqual(first.status_code, 200, first.text)
        events = [line for line in first.text.splitlines() if line.strip()]
        kinds = []
        for line in events:
            payload = __import__('json').loads(line)
            kinds.append(payload['type'])
        self.assertIn('meta', kinds)
        self.assertIn('sources', kinds)
        self.assertIn('delta', kinds)
        self.assertIn('done', kinds)

        created = self.client.post('/api/chat/threads')
        self.assertEqual(created.status_code, 200)
        thread_id = created.json()['id']
        second = self.client.post(
            f'/api/chat/threads/{thread_id}/messages?stream=false',
            json={'message': 'perovskite'},
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()['thread_id'], thread_id)

        deleted = self.client.delete(f'/api/chat/threads/{thread_id}')
        self.assertEqual(deleted.status_code, 200)
        missing = self.client.get(f'/api/chat/threads/{thread_id}')
        self.assertEqual(missing.status_code, 404)

    def test_ai_stream_uses_retrieved_context(self) -> None:
        os.environ['KMS_AI_API_KEY'] = 'sk-test'
        self._login()

        def fake_stream(_settings, messages):
            blob = messages[-1]['content']
            self.assertIn('Stabilized perovskite', blob)
            self.assertIn('文档 1', blob)
            self.assertIn('用户问题', blob)
            yield '根据 [1]，'
            yield 'TOPCon 与钙钛矿叠层相关。'

        with patch('kms.ai_client.chat_stream', side_effect=fake_stream):
            res = self.client.post(
                '/api/chat?stream=false',
                json={'message': 'TOPCon tandem'},
            )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()['ai_ready'])
        self.assertIn('根据 [1]', res.json()['content'])

    def test_tokenize_chinese_bigrams(self) -> None:
        tokens = tokenize('钙钛矿太阳能电池')
        self.assertIn('钙钛', tokens)
        self.assertIn('钛矿', tokens)

    def test_collect_turn_persists_history(self) -> None:
        settings = load_settings()
        with Catalog(settings.catalog_path) as catalog:
            store = ChatStore(catalog)
            first = collect_turn(
                store,
                catalog,
                KeywordStore(catalog),
                KnowledgeGraph(catalog),
                settings,
                user_id=1,
                thread_id=None,
                question='TOPCon',
            )
            second = collect_turn(
                store,
                catalog,
                KeywordStore(catalog),
                KnowledgeGraph(catalog),
                settings,
                user_id=1,
                thread_id=first['thread_id'],
                question='同一篇的摘要要点',
            )
            self.assertEqual(first['thread_id'], second['thread_id'])
            self.assertEqual(len(store.list_messages(first['thread_id'])), 4)


if __name__ == '__main__':
    unittest.main()
