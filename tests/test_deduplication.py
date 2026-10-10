import json
import csv
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import api
import public_api
from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.award_events import import_annotations
from global_cs_paper_awards_agent.deduplication import duplicate_preview,apply_resolutions
from global_cs_paper_awards_agent.paper_search import search_papers,search_paper_records,paper_provenance
from global_cs_paper_awards_agent.public_data import public_snapshot,write_public_database
from global_cs_paper_awards_agent.web_helpers import csv_bytes


class DuplicateTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'test.sqlite3'
        self.db=Database(self.path);self.db.init()
    def tearDown(self):
        self.db.close();self.temp.cleanup()
    def add(self,title,name='Best Paper',status='verified',identifier='a'):
        import_annotations(self.db.conn,{'format':'evidom-award-annotations-v1','review_status':status,
            'records':[{'annotation_id':identifier,'page_id':'page-0004','year':2026,
                'official_award_name':name,'title':title,'authors_raw':'An Author',
                'paper_url':'https://example.org/'+identifier,'source_url':'https://aaai.org/'+identifier,
                'evidence':[{'quote':title}],'note':None}]})
    def apply(self,auto=True,decisions=None,digest=None):
        with self.db.conn:
            self.db.conn.execute('BEGIN IMMEDIATE')
            return apply_resolutions(self.db,digest or duplicate_preview(self.db)['digest'],decisions,auto,'Tester')
    def test_multiple_awards_one_paper_and_csv_one_row(self):
        self.add('A Paper',identifier='a');self.add('A Paper','Best Student Paper',identifier='b')
        raw=search_paper_records(self.db,{'status':'verified'})
        rows=search_papers(self.db,{'status':'verified'})
        self.assertEqual(len(raw),2);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['categories'],['paper','student'])
        self.assertEqual(len(rows[0]['awards']),2);self.assertEqual(len(rows[0]['sources']),2)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(csv_bytes(rows).decode('utf-8-sig'))))),1)
        self.assertEqual(len(search_papers(self.db,{'category':'student','status':'verified'})),1)
        self.assertEqual(duplicate_preview(self.db)['group_count'],0)
    def test_auto_merge_moves_all_awards_and_backs_up(self):
        self.add("A Model's Memory",identifier='a')
        self.add('A Model’s Memory','Best Student Paper',identifier='b')
        preview=duplicate_preview(self.db)
        self.assertEqual(preview['auto_safe_groups'],1)
        result=self.apply()
        self.assertEqual(result['removed'],1);self.assertTrue(Path(result['backup']).is_file())
        with closing(sqlite3.connect(result['backup'])) as before:
            self.assertEqual(before.execute('SELECT COUNT(*) FROM award_papers').fetchone()[0],2)
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM award_papers').fetchone()[0],1)
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM award_event_papers').fetchone()[0],2)
        self.assertFalse(self.db.conn.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual(duplicate_preview(self.db)['group_count'],0)
        self.assertEqual(self.apply()['removed'],0)
    def test_user_can_choose_which_variant_and_url_to_keep(self):
        self.add("A Model's Memory",identifier='a');self.add('A Model’s Memory',identifier='b')
        group=duplicate_preview(self.db)['groups'][0]
        keep=next(r for r in group['members'] if r['title']=='A Model’s Memory')
        decision={'group_id':group['id'],'mode':'merge','keep_id':keep['id'],
                  'delete_ids':[r['id'] for r in group['members'] if r['id']!=keep['id']]}
        self.apply(False,[decision])
        remaining=self.db.conn.execute('SELECT * FROM award_papers').fetchone()
        self.assertEqual(remaining['title'],'A Model’s Memory');self.assertEqual(remaining['paper_url'],'https://example.org/b')
    def test_pending_variant_not_automatically_verified_or_merged(self):
        self.add("A Model's Memory",identifier='a');self.add('A Model’s Memory',status='pending',identifier='b')
        self.assertEqual(duplicate_preview(self.db)['auto_safe_groups'],0)
        self.assertEqual(self.apply()['removed'],0)
        g=duplicate_preview(self.db)['groups'][0]
        with self.assertRaisesRegex(ValueError,'状态不同'):
            self.apply(False,[{'group_id':g['id'],'mode':'merge','keep_id':g['members'][0]['id'],
                              'delete_ids':[g['members'][1]['id']]}])
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM award_event_papers WHERE status='pending'").fetchone()[0],1)
    def test_stale_and_invalid_requests_are_rejected(self):
        self.add("A Model's Memory",identifier='a');self.add('A Model’s Memory',identifier='b')
        preview=duplicate_preview(self.db)
        self.add('Unrelated Paper',identifier='c')
        with self.assertRaisesRegex(ValueError,'数据已变化'): self.apply(digest=preview['digest'])
        g=duplicate_preview(self.db)['groups'][0]
        with self.assertRaises(ValueError):
            self.apply(False,[{'group_id':g['id'],'mode':'delete','delete_ids':['not-a-member']}])
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM award_papers').fetchone()[0],3)
    def test_explicit_delete_removes_only_selected_entity_and_dependencies(self):
        self.add("A Model's Memory",identifier='a');self.add('A Model’s Memory',identifier='b')
        g=duplicate_preview(self.db)['groups'][0]
        removed=g['members'][0]['id'];keep=g['members'][1]['id']
        result=self.apply(False,[{'group_id':g['id'],'mode':'delete','delete_ids':[removed]}])
        self.assertEqual(result['removed'],1)
        self.assertIsNotNone(self.db.conn.execute('SELECT 1 FROM award_papers WHERE id=?',(keep,)).fetchone())
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM award_event_papers').fetchone()[0],1)
    def test_source_collision_preserves_both_original_urls_and_mappings(self):
        self.add("A Model's Memory",identifier='a');self.add('A Model’s Memory',identifier='b')
        papers=self.db.conn.execute('SELECT id FROM award_papers ORDER BY id').fetchall()
        cid=self.db.resolve('AAAI')['id']
        for i,p in enumerate(papers):
            self.db.conn.execute('INSERT INTO source_listings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (str(i),'jeffhuang',p['id'],'AAAI',cid,i,'AI','Author','https://jeffhuang.com/'+str(i),None,'verified','today'))
        self.db.conn.commit();self.apply()
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM source_listings').fetchone()[0],2)
        self.assertEqual(self.db.conn.execute('SELECT COUNT(DISTINCT paper_id) FROM source_listings').fetchone()[0],1)
        row=search_papers(self.db,{'status':'verified'})[0]
        self.assertEqual(len(paper_provenance(self.db.conn,row['id'])['listings']),2)
    def test_similar_titles_or_different_years_are_not_removed(self):
        self.add('A Memory Model',identifier='a');self.add('A Memory Model II',identifier='b')
        self.assertEqual(duplicate_preview(self.db)['group_count'],0)
        self.assertEqual(len(search_papers(self.db,{'status':'verified'})),2)
    def test_core_merge_preserves_source_evidence_and_revisions(self):
        root=Path(__file__).resolve().parents[1]
        self.db.ingest(json.loads((root/'examples/sample-acl-2024.json').read_text(encoding='utf-8')))
        original=dict(self.db.conn.execute('SELECT * FROM records').fetchone())
        other={**original,'id':'duplicate-core'}
        primary=json.loads(original['payload']);primary['publication_date']=None
        primary.pop('publication_date_evidence',None)
        self.db.conn.execute('UPDATE records SET payload=? WHERE id=?',(json.dumps(primary),original['id']))
        self.db.conn.execute('INSERT INTO records ('+','.join(other)+') VALUES ('+','.join('?' for _ in other)+')',list(other.values()))
        self.db.conn.commit()
        group=duplicate_preview(self.db)['groups'][0]
        result=self.apply(False,[{'group_id':group['id'],'mode':'merge','keep_id':original['id'],'delete_ids':[other['id']]}])
        self.assertEqual(result['removed'],1)
        remaining=dict(self.db.conn.execute('SELECT * FROM records').fetchone())
        payload=json.loads(remaining['payload']);sources=json.loads(remaining['sources'])
        self.assertEqual(payload['publication_date'],'2024-08')
        self.assertIn(payload['publication_date_evidence']['source_id'],{s['id'] for s in sources})
        self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],2)
        self.assertEqual(duplicate_preview(self.db)['group_count'],0)
    def test_public_api_counts_rows_and_does_not_expose_duplicate_management(self):
        self.add('A Paper',identifier='a');self.add('A Paper','Best Student Paper',identifier='b')
        snapshot=public_snapshot(self.db)
        path=Path(self.temp.name)/'public.sqlite3';write_public_database(snapshot,path)
        with patch('public_api.get_db',side_effect=lambda:public_api.Database(path)):
            client=TestClient(public_api.app)
            result=client.post('/api/search',json={}).json()
            self.assertEqual(result['total'],1);self.assertEqual(len(result['records']),1)
            self.assertEqual(client.get('/api/duplicates').status_code,404)
            self.assertEqual(client.post('/api/duplicates/resolve',json={}).status_code,404)
    def test_local_confirmation_and_origin_guards(self):
        self.add("A Model's Memory",identifier='a');self.add('A Model’s Memory',identifier='b')
        client=TestClient(api.app)
        with patch('api.get_db',side_effect=lambda:Database(self.path)):
            preview=client.get('/api/duplicates').json()
            body={'digest':preview['digest'],'reviewer':'Tester','auto':True,'confirmed':False}
            self.assertEqual(client.post('/api/duplicates/resolve',json=body).status_code,400)
            self.assertEqual(client.get('/api/duplicates',headers={'Origin':'https://evil.example'}).status_code,403)
            body['confirmed']=True
            self.assertEqual(client.post('/api/duplicates/resolve',json=body).json()['removed'],1)

if __name__=='__main__':unittest.main()
