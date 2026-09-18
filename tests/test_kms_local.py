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


if __name__ == '__main__':
    unittest.main()
