from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from kms.catalog import Catalog

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'streamlit_app.py'


class SearchPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        catalog_path = root / 'catalog.sqlite'
        os.environ['KMS_STORAGE'] = 'local'
        os.environ['KMS_CATALOG'] = str(catalog_path)
        os.environ['KMS_LOCAL_ROOT'] = str(root / 'minio')

        catalog = Catalog(catalog_path)
        catalog.upsert_document({
            'doi': '10.1038/s41563-025-02367-8',
            'url': 'https://link.springer.com/article/10.1038/s41563-025-02367-8',
            'title': 'Stabilized perovskite phases',
            'authors': 'Xu',
            'published': '23 September 2025',
            'parent': 'Nature Materials',
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
        catalog.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self) -> AppTest:
        return AppTest.from_file(str(APP), default_timeout=60).run()

    def test_lists_seeded_papers(self) -> None:
        at = self._run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.dataframe[0].value), 2)

    def test_filter_by_doi(self) -> None:
        at = self._run()
        at.text_input(key='doi').set_value('10.1038/s41563').run()
        self.assertFalse(at.exception)
        df = at.dataframe[0].value
        self.assertEqual(len(df), 1)
        self.assertIn('Stabilized perovskite phases', df['title'].iloc[0])

    def test_filter_by_year(self) -> None:
        at = self._run()
        at.number_input(key='year_from').set_value(2026).run()
        at.number_input(key='year_to').set_value(2026).run()
        self.assertFalse(at.exception)
        df = at.dataframe[0].value
        self.assertEqual(len(df), 1)
        self.assertIn('Perovskite Materials', df['title'].iloc[0])
