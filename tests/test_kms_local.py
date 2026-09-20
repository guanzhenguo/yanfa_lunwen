from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kms.catalog import Catalog
from kms.doi import doi_from_url
from kms.storage import LocalStore, object_key, sha256_file


class DoiTests(unittest.TestCase):
    def test_springer_article(self) -> None:
        url = 'https://link.springer.com/article/10.1038/s41563-025-02367-8'
        self.assertEqual(doi_from_url(url), '10.1038/s41563-025-02367-8')

    def test_springer_chapter(self) -> None:
        url = 'https://link.springer.com/chapter/10.1007/978-3-031-90750-0_2'
        self.assertEqual(doi_from_url(url), '10.1007/978-3-031-90750-0_2')


class LocalStoreCatalogTests(unittest.TestCase):
    def test_put_and_skip_duplicate_doi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LocalStore(root=root / 'minio', bucket='papers')
            catalog = Catalog(root / 'catalog.sqlite')
            pdf = root / 'sample.pdf'
            pdf.write_bytes(b'%PDF-1.4 fake paper\n')

            digest = sha256_file(str(pdf))
            self.assertEqual(digest, sha256_file(pdf))
            key = object_key(digest)
            location = store.put_file(key, pdf)

            article = {
                'doi': '10.1038/s41563-025-02367-8',
                'url': 'https://link.springer.com/article/10.1038/s41563-025-02367-8',
                'title': 'Stabilized perovskite phases',
                'open_access': True,
                'source': 'springer',
                'storage_key': key,
                'sha256': digest,
                'file_location': location,
            }
            first_id = catalog.upsert_document(article)
            second_id = catalog.upsert_document({**article, 'title': 'Updated title'})

            self.assertEqual(first_id, second_id)
            self.assertTrue(store.exists(key))
            stored = catalog.get_by_doi(article['doi'])
            self.assertEqual(stored['title'], 'Updated title')
            self.assertEqual(stored['sha256'], digest)
            self.assertEqual(Path(location), store._path(key))

            # 同一内容再 put，不新增第二份文件
            store.put_file(key, pdf)
            papers = list((root / 'minio' / 'papers').rglob('*.pdf'))
            self.assertEqual(len(papers), 1)

            catalog.close()


class SearchTests(unittest.TestCase):
    def test_year_from_published(self) -> None:
        from kms.catalog import year_from_published

        self.assertEqual(year_from_published('23 September 2025'), 2025)
        self.assertEqual(year_from_published('2026'), 2026)
        self.assertIsNone(year_from_published(''))

    def test_filter_doi_year_oa_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Catalog(Path(tmp) / 'catalog.sqlite')
            catalog.upsert_document({
                'doi': '10.1038/s41563-025-02367-8',
                'url': 'https://link.springer.com/article/10.1038/s41563-025-02367-8',
                'title': 'Stabilized perovskite phases',
                'authors': 'Xu',
                'published': '23 September 2025',
                'open_access': True,
                'storage_key': 'ab/abc.pdf',
            })
            catalog.upsert_document({
                'doi': '10.1007/978-3-031-90750-0_2',
                'url': 'https://link.springer.com/chapter/10.1007/978-3-031-90750-0_2',
                'title': 'Perovskite Materials',
                'authors': 'Suresh',
                'published': '2026',
                'open_access': False,
            })

            by_doi = catalog.search(doi='10.1038/s41563')
            self.assertEqual(len(by_doi), 1)
            self.assertEqual(by_doi[0]['year'], 2025)

            in_2026 = catalog.search(year_from=2026, year_to=2026)
            self.assertEqual(len(in_2026), 1)
            self.assertIn('Perovskite Materials', in_2026[0]['title'])

            oa_pdf = catalog.search(oa=True, has_pdf=True)
            self.assertEqual(len(oa_pdf), 1)
            self.assertEqual(oa_pdf[0]['doi'], '10.1038/s41563-025-02367-8')

            no_pdf = catalog.search(has_pdf=False)
            self.assertEqual(len(no_pdf), 1)
            catalog.close()


class KeywordCatalogTests(unittest.TestCase):
    def test_bind_and_filter(self) -> None:
        from kms.keywords import KeywordStore

        with tempfile.TemporaryDirectory() as tmp:
            catalog = Catalog(Path(tmp) / 'catalog.sqlite')
            keys = KeywordStore(catalog)
            first = catalog.upsert_document({
                'doi': '10.1/a',
                'url': 'https://example.com/a',
                'title': 'TOPCon cell',
            })
            second = catalog.upsert_document({
                'doi': '10.1/b',
                'url': 'https://example.com/b',
                'title': 'Perovskite tandem',
            })
            keys.set_document_keywords(first, ['TOPCon', 'reliability'])
            keys.set_document_keywords(second, ['perovskite'])
            listed = {item['name']: item['paper_count'] for item in keys.list_keywords()}
            self.assertEqual(listed['TOPCon'], 1)
            only_topcon = catalog.search(keyword='TOPCon')
            self.assertEqual(len(only_topcon), 1)
            self.assertEqual(only_topcon[0]['id'], first)
            catalog.close()


class DeepSeekConfigTests(unittest.TestCase):
    def test_config_uses_deepseek_flash_for_extract(self) -> None:
        from dataclasses import replace

        from kms.ai_client import _chat_payload, _completions_url
        from kms.config import load_settings

        settings = load_settings()
        self.assertEqual(settings.ai_model, 'deepseek-flash')
        self.assertIn('api.deepseek.com', settings.ai_base_url)
        self.assertEqual(
            _completions_url(replace(settings, ai_base_url='https://api.deepseek.com')),
            'https://api.deepseek.com/v1/chat/completions',
        )
        payload = _chat_payload(
            settings,
            [{'role': 'user', 'content': 'Hello'}],
            temperature=0.1,
            json_mode=True,
        )
        self.assertEqual(payload['model'], 'deepseek-flash')
        self.assertEqual(payload['reasoning_effort'], 'high')
        self.assertEqual(payload['thinking'], {'type': 'enabled'})
        self.assertEqual(payload['response_format'], {'type': 'json_object'})


class ChineseGraphTests(unittest.TestCase):
    def test_heuristic_localizes_labels_and_relations(self) -> None:
        from kms.kg import localize_graph_heuristic, graph_triples, translate_label

        self.assertEqual(translate_label('perovskite'), '钙钛矿')
        self.assertEqual(translate_label('钙钛矿叠层'), '钙钛矿叠层')
        graph = localize_graph_heuristic({
            'nodes': [
                {'key': 'paper:1', 'label': 'TOPCon cell', 'type': 'Paper'},
                {'key': 'keyword:perovskite', 'label': 'perovskite', 'type': 'Keyword'},
            ],
            'edges': [
                {'source': 'paper:1', 'target': 'keyword:perovskite', 'type': 'HAS_KEYWORD'},
            ],
        })
        by_key = {item['key']: item for item in graph['nodes']}
        self.assertEqual(by_key['keyword:perovskite']['label_zh'], '钙钛矿')
        self.assertEqual(by_key['paper:1']['type_zh'], '论文')
        self.assertEqual(graph['edges'][0]['type_zh'], '具有关键词')
        triples = graph_triples(graph['nodes'], graph['edges'], zh=True)
        self.assertTrue(any('钙钛矿' in item and '具有关键词' in item for item in triples))

    def test_translates_existing_run_without_extract(self) -> None:
        import tempfile
        from pathlib import Path

        from kms.catalog import Catalog
        from kms.config import load_settings
        from kms.kg import KnowledgeGraph, translate_existing_graph, translate_rel

        self.assertEqual(translate_rel('has_keyword'), '具有关键词')
        self.assertEqual(translate_rel('USES_MATERIAL'), '使用材料')

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        catalog = Catalog(Path(tmp.name) / 'catalog.sqlite')
        self.addCleanup(catalog.close)
        kg = KnowledgeGraph(catalog)
        doc_id = catalog.upsert_document({
            'doi': '10.1/translate-only',
            'url': 'https://example.com/translate-only',
            'title': 'perovskite tandem solar cells',
            'published': '2025',
        })
        document = catalog.get_by_id(doc_id)
        run_id = kg.create_run(
            document,
            created_by='tester',
            model='heuristic',
            graph={
                'nodes': [
                    {'key': f'paper:{doc_id}', 'label': 'perovskite tandem solar cells', 'type': 'Paper'},
                    {'key': 'keyword:perovskite', 'label': 'perovskite', 'type': 'Keyword'},
                ],
                'edges': [
                    {
                        'source': f'paper:{doc_id}',
                        'target': 'keyword:perovskite',
                        'type': 'HAS_KEYWORD',
                    },
                ],
            },
        )
        stored = kg.graph_payload(run_id)
        self.assertFalse(any(node.get('label_zh') for node in stored['nodes']))
        self.assertFalse(any(edge.get('rel_type_zh') for edge in stored['edges']))

        settings = load_settings()
        payload = translate_existing_graph(kg, settings, doc_id, ai=False)
        by_key = {node['node_key']: node for node in payload['nodes']}
        self.assertEqual(by_key['keyword:perovskite']['label_zh'], '钙钛矿')
        self.assertEqual(by_key[f'paper:{doc_id}']['node_type_zh'], '论文')
        self.assertEqual(payload['edges'][0]['rel_type_zh'], '具有关键词')
        self.assertEqual(payload['run']['zh_status'], 'heuristic')
        self.assertTrue(any('具有关键词' in item for item in payload['triples_zh']))


class RagFusionTests(unittest.TestCase):
    def test_rrf_merges_chunk_and_graph_lists(self) -> None:
        from kms.rag import rrf_fuse, build_answer_prompt

        fused = rrf_fuse([
            ([{'chunk_id': '1:0', 'text': 'anneal', 'score': 1}], 1.0, 'bm25'),
            ([{'chunk_id': '1:0', 'text': 'anneal', 'score': 0.5, 'graph_score': 2}], 0.8, 'graph'),
            ([{'chunk_id': '2:0', 'text': 'other', 'score': 0.2}], 1.0, 'vector'),
        ])
        self.assertEqual(fused[0]['chunk_id'], '1:0')
        self.assertIn('bm25', fused[0]['fusion_sources'])
        self.assertIn('graph', fused[0]['fusion_sources'])
        self.assertGreater(fused[0]['fusion_score'], fused[1]['fusion_score'])
        prompt = build_answer_prompt('退火温度是多少', [{
            'index': 1,
            'title': 'TOPCon anneal',
            'year': 2025,
            'doi': '',
            'authors': 'Guan',
            'keywords': ['TOPCon'],
            'graph': ['退火'],
            'triples': ['论文 —包含工艺→ 退火'],
            'chunks': [{'section': 'Body', 'page_from': 1, 'page_to': 1, 'text': '400 C anneal'}],
        }])
        self.assertIn('文档 1', prompt)
        self.assertIn('400 C anneal', prompt)
        self.assertIn('用户问题：退火温度是多少', prompt)


if __name__ == '__main__':
    unittest.main()
