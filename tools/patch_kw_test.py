from pathlib import Path

p = Path('tests/test_kms_local.py')
t = p.read_text(encoding='utf-8')
old = "            catalog.close()\n\n\n\nif __name__ == '__main__':\n    unittest.main()\n"
new = """            catalog.close()


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
"""
if old not in t:
    raise SystemExit('needle missing')
p.write_text(t.replace(old, new, 1), encoding='utf-8')
print('ok')
