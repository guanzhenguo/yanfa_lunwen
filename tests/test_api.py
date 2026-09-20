from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from kms.api import create_app
from kms.catalog import Catalog
from kms.pdf_parse import make_pdf_bytes
from kms.storage import LocalStore, object_key, sha256_file

PAPER_TEXT = (
    'Abstract\n'
    'Stabilized perovskite phases for TOPCon tandem solar cells. '
    'Tunnel oxide passivated contacts show contact resistivity of 12 mOhm after anneal.\n'
)


def paper_upload(name: str = 'note.pdf', text: str = PAPER_TEXT):
    return {'file': (name, make_pdf_bytes(text), 'application/pdf')}


class ApiAuthUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ['KMS_STORAGE'] = 'local'
        os.environ['KMS_CATALOG'] = str(root / 'catalog.sqlite')
        os.environ['KMS_LOCAL_ROOT'] = str(root / 'minio')
        os.environ['KMS_ADMIN_PASSWORD'] = 'admin123'
        os.environ['KMS_AI_API_KEY'] = ''

        pdf = root / 'sample.pdf'
        pdf.write_bytes(b'%PDF-1.4 test preview\n')
        store = LocalStore(root / 'minio', bucket='papers')
        digest = sha256_file(pdf)
        key = object_key(digest)
        store.put_file(key, pdf)
        catalog = Catalog(root / 'catalog.sqlite')
        self.doc_id = catalog.upsert_document({
            'doi': '10.1038/s41563-025-02367-8',
            'url': 'https://link.springer.com/article/10.1038/s41563-025-02367-8',
            'title': 'Stabilized perovskite phases',
            'published': '2025',
            'open_access': True,
            'storage_key': key,
            'sha256': digest,
        })
        catalog.close()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_requires_login(self) -> None:
        res = self.client.get('/api/papers')
        self.assertEqual(res.status_code, 401)

    def test_login_preview_upload_and_users(self) -> None:
        denied = self.client.get(f'/api/papers/{self.doc_id}/pdf')
        self.assertEqual(denied.status_code, 401)

        login = self.client.post(
            '/api/auth/login',
            json={'username': 'admin', 'password': 'admin123'},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()['role'], 'admin')

        listed = self.client.get('/api/papers', params={'doi': '10.1038/s41563'})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        pdf = self.client.get(f'/api/papers/{self.doc_id}/pdf')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.headers['content-disposition'].startswith('inline'))

        upload = self.client.post(
            '/api/papers/upload',
            data={
                'title': 'Lab process note',
                'authors': 'Guan',
                'year': '2026',
            },
            files=paper_upload('note.pdf'),
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json()['source'], 'upload')
        self.assertTrue(upload.json()['has_pdf'])

        created = self.client.post(
            '/api/users',
            json={'username': 'engineer', 'password': 'pass123', 'role': 'user'},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()['username'], 'engineer')

        users = self.client.get('/api/users')
        self.assertGreaterEqual(len(users.json()), 2)

        untitled = self.client.post(
            '/api/papers/upload',
            data={},
            files=paper_upload('TOPCon_cell_process.pdf'),
        )
        self.assertEqual(untitled.status_code, 200, untitled.text)
        self.assertEqual(untitled.json()['title'], 'TOPCon cell process')
        self.assertEqual(untitled.json()['original_filename'], 'TOPCon_cell_process.pdf')
        doc_id = untitled.json()['id']

        parsed = self.client.post(
            '/api/papers/parse-metadata',
            data={'filename': 'Perovskite_tandem_2024.pdf', 'authors': 'Guan'},
        )
        self.assertEqual(parsed.status_code, 200, parsed.text)
        self.assertIn('Perovskite tandem', parsed.json()['title'])
        self.assertEqual(parsed.json()['authors'], 'Guan')
        self.assertFalse(parsed.json()['ai_used'])

        empty_graph = self.client.get(f'/api/papers/{doc_id}/kg')
        self.assertEqual(empty_graph.status_code, 200)
        self.assertIsNone(empty_graph.json()['run'])
        self.assertEqual(empty_graph.json()['parse']['status'], 'none')

        parsed_body = self.client.post(f'/api/papers/{doc_id}/parse')
        self.assertEqual(parsed_body.status_code, 200, parsed_body.text)
        self.assertEqual(parsed_body.json()['status'], 'ok')
        self.assertGreaterEqual(parsed_body.json()['page_count'], 1)
        self.assertIn('perovskite', parsed_body.json()['preview'].lower())
        chunks = parsed_body.json().get('chunks') or []
        self.assertTrue(chunks)
        self.assertTrue(chunks[0].get('preview'))
        self.assertNotIn('text', chunks[0])

        empty_scan = self.client.post(f'/api/papers/{self.doc_id}/kg/extract')
        self.assertEqual(empty_scan.status_code, 400)

        extracted = self.client.post(f'/api/papers/{doc_id}/kg/extract')
        self.assertEqual(extracted.status_code, 200, extracted.text)
        payload = extracted.json()
        self.assertEqual(payload['run']['status'], 'pending_review')
        self.assertGreaterEqual(len(payload['nodes']), 2)
        types = {node['node_type'] for node in payload['nodes']}
        self.assertIn('Paper', types)
        self.assertIn('File', types)
        self.assertTrue(payload['neo4j']['nodes'])
        self.assertTrue(payload['neo4j']['relationships'])
        self.assertEqual(payload['parse']['status'], 'ok')
        self.assertTrue(payload.get('triples') is not None)
        self.assertEqual(payload['run']['prompt_name'], 'knowledge_extract')
        self.assertTrue(payload.get('extract', {}).get('default_prompt'))
        self.assertIn('chunks', payload['parse'])
        self.assertTrue(any(node.get('label_zh') or node.get('node_type_zh') for node in payload['nodes']))
        self.assertTrue(any(edge.get('rel_type_zh') for edge in payload['edges']))
        self.assertTrue(payload.get('triples_zh'))

        from kms.catalog import Catalog as LiveCatalog
        from kms.config import load_settings as load_live_settings

        with LiveCatalog(load_live_settings().catalog_path) as live:
            live.conn.execute("UPDATE kg_nodes SET label_zh = '', node_type_zh = ''")
            live.conn.execute("UPDATE kg_edges SET rel_type_zh = ''")
            live.conn.execute("UPDATE kg_runs SET zh_status = ''")
            live.conn.commit()

        wiped = self.client.get(f'/api/papers/{doc_id}/kg')
        self.assertEqual(wiped.status_code, 200, wiped.text)
        self.assertTrue(any(edge.get('rel_type_zh') for edge in wiped.json()['edges']))
        self.assertTrue(any(node.get('node_type_zh') for node in wiped.json()['nodes']))

        translated = self.client.post(f'/api/papers/{doc_id}/kg/translate')
        self.assertEqual(translated.status_code, 200, translated.text)
        self.assertEqual(translated.json()['run']['id'], payload['run']['id'])
        self.assertTrue(any(node.get('label_zh') or node.get('node_type_zh') for node in translated.json()['nodes']))
        self.assertTrue(any(edge.get('rel_type_zh') for edge in translated.json()['edges']))

        missing = self.client.post(f'/api/papers/{self.doc_id}/kg/translate')
        self.assertEqual(missing.status_code, 400)

        reviewed = self.client.post(
            f"/api/kg/runs/{payload['run']['id']}/review",
            json={'status': 'approved', 'note': 'ok'},
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()['run']['status'], 'approved')

        settings = self.client.get('/api/settings')
        self.assertEqual(settings.status_code, 200)
        self.assertIn('ai', settings.json())
        self.assertIn('neo4j', settings.json())

        self.client.post('/api/auth/logout')
        as_user = self.client.post(
            '/api/auth/login',
            json={'username': 'engineer', 'password': 'pass123'},
        )
        self.assertEqual(as_user.status_code, 200)
        denied_prompt = self.client.put(
            '/api/kg/prompts/knowledge_extract',
            json={'body': 'changed by user'},
        )
        self.assertEqual(denied_prompt.status_code, 403)
        denied_ai = self.client.put('/api/settings/ai', json={'model': 'blocked'})
        self.assertEqual(denied_ai.status_code, 403)

    def test_keyword_bind_filter_and_shared_prompt(self) -> None:
        login = self.client.post(
            '/api/auth/login',
            json={'username': 'admin', 'password': 'admin123'},
        )
        self.assertEqual(login.status_code, 200)

        first = self.client.post(
            '/api/papers/upload',
            data={'title': 'TOPCon passivation', 'keywords': 'TOPCon, reliability'},
            files=paper_upload('a.pdf', 'TOPCon passivation and tunnel oxide contact resistivity notes for tandem solar cells.\n'),
        )
        self.assertEqual(first.status_code, 200, first.text)
        names = [item['name'] for item in first.json()['keywords']]
        self.assertEqual(sorted(names), ['TOPCon', 'reliability'])
        first_id = first.json()['id']
        topcon_id = next(item['id'] for item in first.json()['keywords'] if item['name'] == 'TOPCon')

        second = self.client.post(
            '/api/papers/upload',
            data={'title': 'Another TOPCon note', 'keywords': 'topcon'},
            files=paper_upload('b.pdf', 'Another TOPCon note with perovskite absorber and contact resistivity measurement.\n'),
        )
        self.assertEqual(second.status_code, 200, second.text)
        second_names = [item['name'] for item in second.json()['keywords']]
        self.assertEqual(second_names, ['TOPCon'])

        filtered = self.client.get('/api/papers', params={'keyword_id': topcon_id})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual({item['id'] for item in filtered.json()}, {first_id, second.json()['id']})

        parsed = self.client.post(
            '/api/papers/parse-metadata',
            data={
                'filename': 'note.pdf',
                'description': 'Tunnel oxide passivated contact solar cells',
                'keywords': 'TOPCon',
            },
        )
        self.assertEqual(parsed.status_code, 200, parsed.text)
        self.assertEqual(parsed.json()['keywords'], ['TOPCon'])

        prompt = self.client.patch(
            f'/api/keywords/{topcon_id}',
            json={'extract_prompt': 'Focus on tunnel oxide and contact resistivity.'},
        )
        self.assertEqual(prompt.status_code, 200, prompt.text)
        self.assertTrue(prompt.json()['has_custom_prompt'])

        schema = self.client.patch(
            f'/api/keywords/{topcon_id}',
            json={'extract_schema': '{"nodes":[{"type":"Process"}]}'},
        )
        self.assertEqual(schema.status_code, 200, schema.text)
        self.assertTrue(schema.json()['has_custom_schema'])
        self.assertIn('Process', schema.json()['extract_schema'])

        listed = self.client.get('/api/keywords')
        self.assertGreaterEqual(len(listed.json()), 2)

        extracted = self.client.post(f'/api/papers/{first_id}/kg/extract')
        self.assertEqual(extracted.status_code, 200, extracted.text)
        self.assertTrue(extracted.json()['run']['prompt_name'].startswith('keyword:'))

        updated = self.client.patch(
            f'/api/papers/{first_id}/keywords',
            json={'keywords': ['TOPCon', 'perovskite']},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(
            sorted(item['name'] for item in updated.json()['keywords']),
            ['TOPCon', 'perovskite'],
        )

        self.client.post(
            '/api/users',
            json={'username': 'reader', 'password': 'pass123', 'role': 'user'},
        )
        self.client.post('/api/auth/logout')
        self.client.post(
            '/api/auth/login',
            json={'username': 'reader', 'password': 'pass123'},
        )
        denied = self.client.patch(
            f'/api/keywords/{topcon_id}',
            json={'extract_prompt': 'blocked'},
        )
        self.assertEqual(denied.status_code, 403)
        renamed = self.client.patch(
            f'/api/keywords/{topcon_id}',
            json={'name': 'TOPCon cell'},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()['name'], 'TOPCon cell')


if __name__ == '__main__':
    unittest.main()
