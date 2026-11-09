import ast
import csv
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import app
from paper_awards.database import Database
from paper_awards.snapshot import write_public_database

ROOT = Path(__file__).resolve().parents[1]

class DisplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'read-only.sqlite3'
        cls.snapshot = json.loads((ROOT / 'data/exports/public-data.json').read_text(encoding='utf-8'))
        write_public_database(cls.snapshot, cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_search_matches_snapshot_and_is_read_only(self):
        with patch('app.get_db', side_effect=lambda: Database(self.path)), TestClient(app.app) as client:
            result = client.post('/api/search', json={'status': 'all'}).json()
            self.assertEqual(result['total'], self.snapshot['publication']['paper_results'])
            self.assertTrue(all(row['status'] == 'verified' for row in result['records']))
            title = result['records'][0]['title']
            self.assertTrue(client.post('/api/search', json={'title': title}).json()['total'])
            response = client.get('/api/export/csv')
            self.assertEqual(len(list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))), result['total'])
        db = Database(self.path)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                db.conn.execute('DELETE FROM records')
        finally:
            db.close()

    def test_paper_details_can_load_linked_provenance(self):
        from urllib.parse import quote
        with patch('app.get_db', side_effect=lambda: Database(self.path)), TestClient(app.app) as client:
            record = client.post('/api/search', json={}).json()['records'][0]
            response = client.get('/api/papers/' + quote(record['id'], safe='') + '/sources')
            self.assertEqual(response.status_code, 200)
            self.assertIsInstance(response.json().get('listings'), list)
            self.assertTrue(response.json().get('awards'))

    def test_management_endpoints_do_not_exist(self):
        with TestClient(app.app) as client:
            for endpoint in ['collect-stream', 'review', 'coverage', 'llm-models', 'seeds', 'publication/start', 'runs', 'duplicates/resolve']:
                for method in [client.get, client.post]:
                    self.assertEqual(method('/api/' + endpoint).status_code, 404, endpoint)

    def test_only_display_modules_are_present(self):
        self.assertFalse((ROOT / 'api.py').exists())
        self.assertFalse((ROOT / 'global_cs_paper_awards_agent').exists())
        for name in ['CollectView.vue', 'ReviewView.vue', 'CoverageView.vue']:
            self.assertFalse((ROOT / 'frontend/src/views' / name).exists())
        for path in (ROOT / 'paper_awards').glob('*.py'):
            functions = {node.name for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))) if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
            self.assertTrue(functions.isdisjoint({'LLM', 'import_annotations', 'import_jeffhuang', 'confirm_review', 'start_publication'}))

if __name__ == '__main__':
    unittest.main()
