import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from fastapi.testclient import TestClient
import public_api
from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.award_events import import_annotations
from global_cs_paper_awards_agent.source_listings import import_jeffhuang
from global_cs_paper_awards_agent.paper_search import paper_provenance, search_papers
from global_cs_paper_awards_agent.public_data import public_snapshot, write_public_database

ROOT = Path(__file__).resolve().parents[1]


class PaperProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / 'local.sqlite3')
        self.db.init()
        self.db.ingest(json.loads((ROOT / 'examples/sample-acl-2024.json').read_text(encoding='utf-8')))
        self.core = self.db.search(status='pending')[0]
        self.db.conn.execute("UPDATE records SET status='verified'")
        self.db.conn.commit()
        import_annotations(self.db.conn, {
            'format': 'evidom-award-annotations-v1', 'review_status': 'verified', 'records': [{
                'annotation_id': 'proof-001', 'page_id': 'page-0004', 'year': 2026,
                'official_award_name': 'AAAI Outstanding Paper Awards', 'title': 'Event Paper',
                'source_url': 'https://aaai.org/awards', 'evidence': [{'quote': 'Event Paper'}],
            }]})
        import_jeffhuang(self.db.conn, {
            'format': 'jeffhuang-listings-v1', 'review_status': 'verified',
            'source_url': 'https://jeffhuang.com/best_paper_awards/', 'rows': [
                {'source_row': 10, 'year': 2026, 'venue': 'AAAI', 'title': 'Event Paper',
                 'area_raw': 'AI', 'authors_raw': 'An Author', 'discovery_url': 'https://scholar.google.com/scholar?q=Event+Paper'},
                {'source_row': 11, 'year': self.core['year'], 'venue': self.core['acronym'],
                 'title': self.core['title'], 'authors_raw': 'Core Author'},
                {'source_row': 12, 'year': 2025, 'venue': 'FSE', 'title': 'Listing Only Paper'},
            ]})

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def record(self, title):
        return next(r for r in search_papers(self.db, {'status': 'verified'}) if r['title'] == title)

    def test_core_event_and_listing_sources_preserve_metadata_and_counts(self):
        before = len(search_papers(self.db, {'status': 'verified'}))
        event = paper_provenance(self.db.conn, self.record('Event Paper')['id'])
        source = event['listings'][0]
        self.assertEqual(source['source_row'], 10)
        self.assertEqual(source['authors_raw'], 'An Author')
        self.assertEqual(source['linked_awards'][0]['official_award_name'], 'AAAI Outstanding Paper Awards')
        self.assertIn('scholar.google.com', source['discovery_url'])
        core = paper_provenance(self.db.conn, self.core['id'])
        self.assertEqual(core['listings'][0]['linked_record_count'], 1)
        listing = paper_provenance(self.db.conn, self.record('Listing Only Paper')['id'])
        self.assertEqual(listing['listings'][0]['linked_awards'], [])
        self.assertEqual(listing['listings'][0]['linked_record_count'], 0)
        self.assertEqual(before, len(search_papers(self.db, {'status': 'verified'})))

    def test_pending_sources_and_related_awards_are_hidden_in_public_reads(self):
        event_id = self.record('Event Paper')['id']
        self.db.conn.execute("UPDATE award_events SET status='pending' WHERE official_award_name='AAAI Outstanding Paper Awards'")
        self.db.conn.commit()
        self.assertIsNone(paper_provenance(self.db.conn, event_id))
        self.assertIsNotNone(paper_provenance(self.db.conn, event_id, verified_only=False))
        self.db.conn.execute("UPDATE source_listings SET status='pending' WHERE source_row=11")
        self.db.conn.commit()
        self.assertEqual(paper_provenance(self.db.conn, self.core['id'])['listings'], [])
        self.assertEqual(paper_provenance(self.db.conn, self.core['id'], verified_only=False)['listings'][0]['status'], 'pending')

    def test_unreviewed_core_and_malformed_identifiers_are_not_disclosed(self):
        self.db.conn.execute("UPDATE records SET status='pending'")
        self.db.conn.commit()
        self.assertIsNone(paper_provenance(self.db.conn, self.core['id']))
        for key in ('event:invalid', 'event:one:two:extra', 'listing:missing', "' OR 1=1 --"):
            self.assertIsNone(paper_provenance(self.db.conn, key))

    def test_public_endpoint_works_on_read_only_database(self):
        path = self.root / 'public.sqlite3'
        write_public_database(public_snapshot(self.db), path)
        before = path.read_bytes()
        with patch('public_api.get_db', side_effect=lambda: public_api.Database(path)):
            client = TestClient(public_api.app)
            records = client.post('/api/search', json={}).json()['records']
            for record in records:
                result = client.get('/api/papers/' + quote(record['id'], safe='') + '/sources')
                self.assertEqual(result.status_code, 200)
                self.assertIn('listings', result.json())
            self.assertEqual(client.get('/api/papers/missing/sources').status_code, 404)
        self.assertEqual(before, path.read_bytes())

    def test_public_frontend_keeps_only_two_navigation_entries(self):
        public = (ROOT / 'frontend/src/PublicApp.vue').read_text(encoding='utf-8')
        self.assertNotIn('SourceListingsView', public)
        self.assertNotIn("id: 'listings'", public)
        self.assertIn("id: 'search'", public)
        self.assertIn("id: 'events'", public)
        self.assertIn('SourceListingsView', (ROOT / 'frontend/src/App.vue').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
