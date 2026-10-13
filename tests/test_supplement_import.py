import copy
import json
import tempfile
import unittest
from pathlib import Path

from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.supplement_import import import_supplement
from global_cs_paper_awards_agent.paper_search import search_papers


class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / 'awards.sqlite3')
        self.db.init()
        self.cid = self.db.resolve('ACL')['id']
        self.document = dict(format='reviewed-public-link-supplement-v1',
            review_status='verified',verification_note='Data owner confirmed all rows verified',
            source_workbook='supplement.xlsx',source_sha256='a'*64,imported_at='2026-10-09T20:00:00+08:00',
            records=[dict(conference_id=self.cid,year=2025,title='Test Paper',award_name='Best Paper',
                source_url='https://conference.example/awards',paper_url='https://publisher.example/test.pdf',
                authors_raw='Jane Author',sheet='2025',row=3)])

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_new_rows_reimport_without_duplicates_and_keep_pending_untouched(self):
        first = import_supplement(self.db,self.document)
        self.assertEqual(first['new_papers'],1)
        self.assertEqual(first['new_events'],1)
        count=self.db.conn.total_changes
        second=import_supplement(self.db,self.document)
        self.assertFalse(any(v for k,v in second.items() if k!='rows'))
        self.assertEqual(self.db.conn.total_changes,count)
        result=search_papers(self.db,{'status':'verified'})
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['paper_url'],'https://publisher.example/test.pdf')

    def test_generic_name_supplements_specific_award_without_new_event(self):
        doc=copy.deepcopy(self.document)
        doc['records'][0]['award_name']='Outstanding Paper Award – Research Track'
        import_supplement(self.db,doc)
        changed=copy.deepcopy(self.document)
        changed['source_sha256']='b'*64
        changed['records'][0]['paper_url']='https://publisher.example/new.pdf'
        stats=import_supplement(self.db,changed)
        self.assertEqual(stats['new_events'],0)
        self.assertEqual(stats['new_papers'],0)
        self.assertEqual(len(search_papers(self.db,{'status':'verified'})),1)
        self.assertEqual(self.db.conn.execute('SELECT official_award_name FROM award_events').fetchone()[0],
                         'Outstanding Paper Award – Research Track')

    def test_distinct_award_categories_survive(self):
        import_supplement(self.db,self.document)
        student=copy.deepcopy(self.document)
        student['source_sha256']='b'*64
        student['records'][0]['award_name']='Best Student Paper'
        self.assertEqual(import_supplement(self.db,student)['new_papers'],0)
        rows=search_papers(self.db,{'status':'verified'})
        self.assertEqual(set(rows[0]['categories']),{'paper','student'})
        self.assertEqual(len(rows),1)
        self.assertEqual(len(rows[0]['awards']),2)
        self.assertEqual(len(search_papers(self.db,{'status':'verified','category':'student'})),1)

    def test_multiple_awards_with_different_urls_do_not_flip_urls_on_reimport(self):
        document=copy.deepcopy(self.document)
        document['records'].append({**document['records'][0], 'row':4,
            'award_name':'Best Student Paper', 'paper_url':'https://publisher.example/alternate.pdf'})
        import_supplement(self.db,document)
        before=self.db.conn.total_changes
        stats=import_supplement(self.db,document)
        self.assertFalse(any(v for k,v in stats.items() if k!='rows'))
        self.assertEqual(before,self.db.conn.total_changes)

    def test_invalid_address_rolls_back_and_review_is_explicit(self):
        invalid=copy.deepcopy(self.document)
        invalid['records'].append({**invalid['records'][0],'row':4,'paper_url':'http://127.0.0.1/paper.pdf'})
        with self.assertRaises(ValueError):
            import_supplement(self.db,invalid)
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM award_papers').fetchone()[0],0)
        invalid=copy.deepcopy(self.document);invalid['review_status']='pending'
        with self.assertRaises(ValueError):
            import_supplement(self.db,invalid)

    def test_reviewed_title_variant_matches_existing_id_without_renaming_title(self):
        import_supplement(self.db,self.document)
        variant=copy.deepcopy(self.document)
        variant['source_sha256']='b'*64
        variant['records'][0].update(title='Test Paper (ESOP)',canonical_title='Test Paper')
        self.assertEqual(import_supplement(self.db,variant)['new_papers'],0)
        self.assertEqual(self.db.conn.execute('SELECT title FROM award_papers').fetchone()[0],'Test Paper')

    def test_catalog_aliases_reuse_existing_paper_ids(self):
        document=copy.deepcopy(self.document)
        document['records'][0]['conference_id']=self.db.resolve('SIGKDD')['id']
        import_supplement(self.db,document)
        pid=self.db.conn.execute('SELECT id FROM award_papers').fetchone()[0]
        self.db.conn.execute("UPDATE award_papers SET venue='KDD'")
        self.db.conn.commit()
        changed=copy.deepcopy(document);changed['source_sha256']='b'*64
        self.assertEqual(import_supplement(self.db,changed)['new_papers'],0)
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM award_papers').fetchone()[0],1)
        self.assertEqual(self.db.conn.execute('SELECT id FROM award_papers').fetchone()[0],pid)

    def test_unrelated_pending_records_keep_review_status_and_content(self):
        sample=Path(__file__).resolve().parents[1]/'examples/sample-acl-2024.json'
        self.db.ingest(json.loads(sample.read_text(encoding='utf-8')))
        before=[dict(r) for r in self.db.conn.execute("SELECT * FROM records WHERE status='pending'")]
        self.assertTrue(before)
        import_supplement(self.db,self.document)
        self.assertEqual(before,[dict(r) for r in self.db.conn.execute("SELECT * FROM records WHERE status='pending'")])

    def test_shared_fse_acronym_uses_conference_ids_not_alias_order(self):
        choices=[r for r in self.db.conferences() if r['acronym']=='FSE']
        self.assertEqual(len(choices),2)
        for i, conference in enumerate(choices):
            doc=copy.deepcopy(self.document)
            doc['source_sha256']=str(i+1)*64
            doc['records'][0]['conference_id']=conference['id']
            stats=import_supplement(self.db,doc)
            self.assertEqual(stats['new_papers'],1)
            self.assertEqual(import_supplement(self.db,doc)['new_papers'],0)
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM award_papers').fetchone()[0],2)
        links=self.db.conn.execute('''SELECT e.conference_id,x.paper_id FROM award_events e
            JOIN award_event_papers x ON e.id=x.event_id''').fetchall()
        self.assertEqual(len({r['conference_id'] for r in links}),2)
        self.assertEqual(len({r['paper_id'] for r in links}),2)
        results=search_papers(self.db,{'status':'verified'})
        self.assertEqual(len(results),2)
        self.assertEqual({r['conference_id'] for r in results},{r['id'] for r in choices})
        from global_cs_paper_awards_agent.public_data import public_snapshot
        snapshot=public_snapshot(self.db)
        self.assertEqual(len(snapshot['tables']['award_papers']),2)
        self.assertEqual(len(snapshot['tables']['award_events']),2)

    def test_shared_fse_acronym_core_snapshot_does_not_cross_link(self):
        from global_cs_paper_awards_agent.public_data import public_snapshot
        sample=Path(__file__).resolve().parents[1]/'examples/sample-acl-2024.json'
        choices=[r for r in self.db.conferences() if r['acronym']=='FSE']
        for conference in choices:
            bundle=json.loads(sample.read_text(encoding='utf-8'))
            bundle['conference_id']=conference['id']
            result=self.db.ingest(bundle)
            self.assertFalse(result['rejected'])
            for rid in result['record_ids']:
                self.db.review(rid,'verified','test','Synthetic fixture for conference identity')
        snapshot=public_snapshot(self.db)
        self.assertEqual(len(snapshot['tables']['award_papers']),2)
        self.assertEqual(len(snapshot['tables']['award_events']),2)
        self.assertEqual({r['conference_id'] for r in snapshot['tables']['award_events']},
                         {r['id'] for r in choices})
        self.assertEqual(len({r['paper_id'] for r in snapshot['tables']['award_event_papers']}),2)


if __name__=='__main__':
    unittest.main()
