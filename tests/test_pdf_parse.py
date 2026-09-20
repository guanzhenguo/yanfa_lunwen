from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kms.catalog import Catalog
from kms.pdf_parse import build_chunks, ensure_document_parse, make_pdf_bytes, parse_pdf_bytes
from kms.storage import LocalStore, object_key, sha256_file


class PdfParseTests(unittest.TestCase):
    def test_extracts_pages_and_skips_references(self) -> None:
        data = make_pdf_bytes(
            'Abstract\nPerovskite tandem solar cells with TOPCon bottom cells.\n',
            'Experimental\nThe films were annealed at 150 C for 30 min.\n',
            'References\n[1] A. Smith, Solar Energy, 2020.\n',
        )
        result = parse_pdf_bytes(data)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['page_count'], 3)
        self.assertGreaterEqual(result['chunk_count'], 1)
        self.assertIn('perovskite', result['preview'].lower())
        sections = {item['section'] for item in result['chunks']}
        self.assertTrue(sections & {'Abstract', 'Experimental', 'References', 'Body'})

    def test_empty_bytes_marked_empty(self) -> None:
        result = parse_pdf_bytes(b'%PDF-1.4 empty\n')
        self.assertIn(result['status'], {'empty', 'error'})

    def test_build_chunks_respects_target(self) -> None:
        pages = [
            {'page': 1, 'section': 'Abstract', 'text': 'A' * 2000},
            {'page': 2, 'section': 'Results', 'text': 'B' * 2000},
        ]
        chunks = build_chunks(pages, target=2500)
        self.assertGreaterEqual(len(chunks), 2)

    def test_ensure_parse_reuses_same_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LocalStore(root / 'minio', bucket='papers')
            catalog = Catalog(root / 'catalog.sqlite')
            try:
                pdf = root / 'p.pdf'
                pdf.write_bytes(make_pdf_bytes(
                    'Abstract\nContact resistivity 12 mOhm for TOPCon tandem solar cells after anneal.\n'
                ))
                digest = sha256_file(pdf)
                key = object_key(digest)
                store.put_file(key, pdf)
                doc_id = catalog.upsert_document({
                    'doi': '10.1/test',
                    'url': 'upload://test',
                    'title': 'TOPCon note',
                    'storage_key': key,
                    'sha256': digest,
                })
                row = catalog.get_by_id(doc_id)
                first = ensure_document_parse(catalog, store, row)
                second = ensure_document_parse(catalog, store, row)
                self.assertEqual(first['status'], 'ok')
                self.assertEqual(first['parsed_at'], second['parsed_at'])
                payload = catalog.parse_payload(doc_id, include_text=False)
                self.assertTrue(payload['chunks'])
                self.assertTrue(payload['chunks'][0]['preview'])
                self.assertNotIn('text', payload['chunks'][0])
                full = catalog.parse_payload(doc_id, include_text=True)
                self.assertIn('text', full['chunks'][0])
            finally:
                catalog.close()


class ExtractPromptTests(unittest.TestCase):
    def test_keywords_share_default_until_customized(self) -> None:
        from kms.kg import KnowledgeGraph, PROMPT_EXTRACT, resolve_extract_prompt

        with tempfile.TemporaryDirectory() as tmp:
            catalog = Catalog(Path(tmp) / 'catalog.sqlite')
            try:
                kg = KnowledgeGraph(catalog)
                default = kg.get_prompt(PROMPT_EXTRACT)
                prompt, name = resolve_extract_prompt(
                    kg,
                    [{'name': 'TOPCon', 'extract_prompt': '', 'extract_schema': ''}],
                )
                self.assertEqual(name, PROMPT_EXTRACT)
                self.assertEqual(prompt, default)

                custom, custom_name = resolve_extract_prompt(
                    kg,
                    [{
                        'name': 'TOPCon',
                        'extract_prompt': 'Focus on tunnel oxide.',
                        'extract_schema': '{"nodes":[{"type":"Process"}]}',
                    }],
                )
                self.assertTrue(custom_name.startswith('keyword:'))
                self.assertIn(default[:40], custom)
                self.assertIn('Focus on tunnel oxide.', custom)
                self.assertIn('Process', custom)
            finally:
                catalog.close()


if __name__ == '__main__':
    unittest.main()
