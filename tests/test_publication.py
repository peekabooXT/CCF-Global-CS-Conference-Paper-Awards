import hashlib
import io
import json
import os
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.award_events import import_annotations
from global_cs_paper_awards_agent.source_listings import import_jeffhuang
from global_cs_paper_awards_agent.public_data import public_snapshot, write_public_database, review_preview, confirm_review
from global_cs_paper_awards_agent.publication import build_files, _publish, init_journal, history, LOCK
from global_cs_paper_awards_agent.public_release import release_bytes, public_module_bytes
from scripts import public_receiver as receiver
import api
import public_api

ROOT = Path(__file__).resolve().parents[1]


class PublicationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root/'local.sqlite3'); self.db.init()
        self.bundle = json.loads((ROOT/'examples/sample-acl-2024.json').read_text(encoding='utf-8'))
        self.db.ingest(self.bundle)

    def tearDown(self):
        self.db.close(); self.temp.cleanup()

    def review(self):
        preview = review_preview(self.db)
        with self.db.conn:
            confirm_review(self.db,preview['digest'],'Test Reviewer','Checked sources')

    def add_sources(self):
        import_annotations(self.db.conn,{'format':'evidom-award-annotations-v1','records':[{
            'annotation_id':'test-001','page_id':'page-0004','year':2026,'official_award_name':'Outstanding Paper Awards',
            'title':'Event Paper','source_url':'https://aaai.org/awards','evidence':[{'quote':'Event Paper'}],'note':None}]})
        import_jeffhuang(self.db.conn,{'format':'jeffhuang-listings-v1','source_url':'https://jeffhuang.com/best_paper_awards/',
            'rows':[{'source_row':1,'year':2025,'venue':'AAAI','area_raw':'AI','title':'Listing Paper','authors_raw':'A. Author','discovery_url':None}]})

    def test_review_requires_current_digest_and_valid_sources(self):
        old = review_preview(self.db)
        self.add_sources()
        with self.assertRaisesRegex(ValueError,'变化'):
            confirm_review(self.db,old['digest'],'Reviewer','')
        with self.assertRaises(ValueError): confirm_review(self.db,review_preview(self.db)['digest'],'','')
        self.db.conn.execute("UPDATE award_event_papers SET evidence='[]'"); self.db.conn.commit()
        preview = review_preview(self.db)
        self.assertTrue(preview['errors'])
        with self.assertRaises(ValueError): confirm_review(self.db,preview['digest'],'Reviewer','')
        self.assertEqual(self.db.search(status='pending')[0]['status'],'pending')

    def test_snapshot_has_all_reviewed_sources_but_no_local_management_data(self):
        self.add_sources(); self.review()
        snapshot = public_snapshot(self.db)
        self.assertEqual(set(snapshot['tables']),receiver.TABLES)
        self.assertEqual(len(snapshot['tables']['records']),1)
        self.assertEqual(len(snapshot['tables']['award_events']),2)
        self.assertEqual(len(snapshot['tables']['source_listings']),1)
        self.assertIsNone(snapshot['tables']['records'][0]['reviewer'])
        path=self.root/'public.sqlite3';write_public_database(snapshot,path)
        receiver.validate_database(path)
        with patch.dict(os.environ,{'AWARDS_PUBLIC_DB':str(path)}):
            client=TestClient(public_api.app)
            result=client.post('/api/search',json={'status':'all'}).json()
            self.assertEqual(result['total'],3)
            self.assertTrue(all(r['status']=='verified' for r in result['records']))
            self.assertEqual(client.get('/api/award-events').json()['total'],2)
            self.assertEqual(client.get('/api/source-listings').json()['total'],1)
            for url in ('/api/collect-stream','/api/review','/api/coverage','/api/llm-models','/api/seeds','/api/publication/start','/api/runs'):
                self.assertEqual(client.post(url,json={}).status_code,404)
                self.assertEqual(client.get(url).status_code,404)
        db=public_api.Database(path)
        with self.assertRaises(sqlite3.OperationalError): db.conn.execute('DELETE FROM records')
        self.assertFalse(hasattr(db,'review')); db.close()

    def test_pending_and_rejected_do_not_publish(self):
        self.add_sources()
        self.db.conn.execute("UPDATE source_listings SET status='rejected'");self.db.conn.commit()
        snapshot=public_snapshot(self.db)
        self.assertFalse(snapshot['tables']['records'])
        self.assertFalse(snapshot['tables']['award_events'])
        self.assertFalse(snapshot['tables']['source_listings'])

    @unittest.skipUnless((ROOT/'frontend/dist-public/index.html').exists(), 'Build the public frontend first')
    def test_public_frontend_contains_no_management_endpoints(self):
        content='\n'.join(p.read_text(encoding='utf-8') for p in (ROOT/'frontend/dist-public/assets').glob('*.js'))
        for endpoint in ('publication/start','collect-stream','llm-models','seeds/lookup','runs/delete','mark-coverage',"'/review'",'"/review"'):
            self.assertNotIn(endpoint,content)

    def test_timestamps_and_names_match_all_indexes(self):
        self.add_sources();self.review()
        snapshot=public_snapshot(self.db,published_at='2026-10-08T12:00:00+08:00')
        files=build_files(self.db,snapshot)
        for name in ('AWARDS.md','docs/awards/BY_YEAR.md','docs/awards/BY_CATEGORY.md','docs/awards/BY_AWARD.md'):
            self.assertIn(snapshot['publication']['published_at'],files[name].decode())
            self.assertIn('Outstanding Paper Awards',files[name].decode())
        self.assertEqual(json.loads(files['data/exports/publication.json']),snapshot['publication'])

    def test_package_is_public_only_and_receiver_rejects_unsafe_files(self):
        self.review();snapshot=public_snapshot(self.db)
        fake=self.root/'package';(fake/'frontend/dist-public').mkdir(parents=True)
        (fake/'frontend/dist-public/index.html').write_text('<html></html>')
        for name in ('public_api.py','requirements-public.txt','data/conferences.json'):
            path=fake/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
        import shutil
        shutil.copytree(ROOT/'global_cs_paper_awards_agent',fake/'global_cs_paper_awards_agent',ignore=shutil.ignore_patterns('__pycache__'))
        archive=release_bytes(fake,snapshot,{})
        dest=self.root/'extracted';dest.mkdir();receiver.unpack(archive,dest);receiver.validate_database(dest/'data/public.sqlite3')
        self.assertFalse((dest/'api.py').exists());self.assertFalse((dest/'global_cs_paper_awards_agent/llm.py').exists())
        self.assertNotIn('def import_annotations',(dest/'global_cs_paper_awards_agent/award_events.py').read_text(encoding='utf-8'))
        self.assertNotIn('def import_jeffhuang',(dest/'global_cs_paper_awards_agent/source_listings.py').read_text(encoding='utf-8'))
        for name in ('../escape','api.py','data/local-publish-config.json','frontend/dist/assets/../../api.py'):
            self.assertFalse(receiver.allowed(name))
        bad=io.BytesIO()
        with tarfile.open(fileobj=bad,mode='w:gz') as a:
            e=tarfile.TarInfo('public_api.py');e.type=tarfile.SYMTYPE;e.linkname='/etc/passwd';a.addfile(e)
        with self.assertRaises(ValueError): receiver.unpack(bad.getvalue(),self.root/'bad')

    def test_local_api_requires_human_confirmation_and_rejects_other_origin(self):
        client=TestClient(api.app)
        with patch('api.get_db',side_effect=lambda:Database(self.root/'local.sqlite3')):
            preview=client.get('/api/publication/preview').json()
            body={'digest':preview['digest'],'reviewer':'Reviewer','confirm_review':False}
            self.assertEqual(client.post('/api/publication/start',json=body).status_code,400)
            self.assertEqual(client.get('/api/publication/preview',headers={'Origin':'https://attacker.example'}).status_code,403)

    def test_server_restart_failure_rolls_back_previous_release(self):
        root=self.root/'server';(root/'releases').mkdir(parents=True)
        old=root/'releases/old';old.mkdir();(root/'current').symlink_to(old,target_is_directory=True)
        content=b'example'
        def unpack(_,destination):
            (destination/'data').mkdir()
            (destination/'data/publication.json').write_text(json.dumps({'release_id':'a'*32,'published_at':'today'}))
        def switch(target):
            (root/'current').unlink()
            (root/'current').symlink_to(target,target_is_directory=True)
        with patch.object(receiver,'ROOT',root),patch.object(receiver,'switch',side_effect=switch),patch.object(receiver,'unpack',side_effect=unpack),patch.object(receiver,'validate_database'),patch.object(receiver,'wait_ready',side_effect=ValueError('failed')),patch.object(receiver,'restart') as restart:
            with self.assertRaisesRegex(ValueError,'恢复上一版'):receiver.publish(content,hashlib.sha256(content).hexdigest())
            self.assertEqual((root/'current').resolve(),old)
            self.assertEqual(restart.call_count,2)

    def test_github_failure_and_server_partial_are_recorded(self):
        for server_fail in (False,True):
            init_journal(self.db)
            job=('b' if server_fail else 'a')*32
            self.db.conn.execute('INSERT INTO publication_runs VALUES (?,?,?,NULL,?)',(job,'preflight','today','{}'));self.db.conn.commit()
            request={'digest':review_preview(self.db)['digest'],'reviewer':'Tester','note':'','allow_empty':False}
            (self.root/'frontend/dist-public').mkdir(parents=True,exist_ok=True);(self.root/'frontend/dist-public/index.html').write_text('ok')
            with patch('global_cs_paper_awards_agent.publication.ROOT',self.root),patch('global_cs_paper_awards_agent.publication.load_config',return_value={}),patch('global_cs_paper_awards_agent.publication.GitDataPublisher') as git,patch('global_cs_paper_awards_agent.publication.ServerPublisher') as server,patch('global_cs_paper_awards_agent.publication.release_bytes',return_value=b'archive'):
                git.return_value.publish.side_effect=None if server_fail else ValueError('GitHub refused')
                git.return_value.publish.return_value={'commit_sha':'abc','commit_url':'https://github.com/test'}
                server.return_value.publish.side_effect=ValueError('Server refused')
                LOCK.acquire();_publish(self.root/'local.sqlite3',job,request)
            row=self.db.conn.execute('SELECT status,finished_at FROM publication_runs WHERE id=?',(job,)).fetchone()
            self.assertEqual(row['status'],'partial' if server_fail else 'failed');self.assertTrue(row['finished_at'])

    def test_complete_publication_records_both_destinations_and_updates_times(self):
        init_journal(self.db);job='c'*32
        self.db.conn.execute('INSERT INTO publication_runs VALUES (?,?,?,NULL,?)',(job,'preflight','today','{}'));self.db.conn.commit()
        (self.root/'frontend/dist-public').mkdir(parents=True);(self.root/'frontend/dist-public/index.html').write_text('ok')
        request={'digest':review_preview(self.db)['digest'],'reviewer':'Tester','note':'Checked','allow_empty':False}
        with patch('global_cs_paper_awards_agent.publication.ROOT',self.root),patch('global_cs_paper_awards_agent.publication.load_config',return_value={}),patch('global_cs_paper_awards_agent.publication.GitDataPublisher') as git,patch('global_cs_paper_awards_agent.publication.ServerPublisher') as server,patch('global_cs_paper_awards_agent.publication.release_bytes',return_value=b'archive'):
            git.return_value.publish.return_value={'commit_sha':'abc','commit_url':'https://github.com/test'}
            git.return_value.sync_local_checkout.return_value={'updated':True}
            server.return_value.publish.return_value={'ok':True,'release_id':job}
            LOCK.acquire();_publish(self.root/'local.sqlite3',job,request)
        row=history(self.db)[0]
        self.assertEqual(row['status'],'completed');self.assertTrue(row['finished_at'])
        self.assertEqual(row['details']['server']['release_id'],job)
        output=self.root/'data/publications'/job
        stamp=row['details']['publication']['published_at']
        self.assertIn(stamp,(output/'AWARDS.md').read_text(encoding='utf-8'))
        self.assertEqual(len(self.db.search(status='pending')),0)

    def test_management_migration_is_idempotent_and_keeps_original_timestamps(self):
        from scripts.import_management_backup import migrate
        self.db.conn.execute("INSERT INTO runs(conference_id,year,started_at,finished_at,status,details) VALUES (?,?,?,?,'failed','{}')",
            (self.bundle['conference_id'],2024,'2026-09-01T12:00:00','2026-09-01T12:01:00'));self.db.conn.commit()
        target=self.root/'workbench.sqlite3'
        first=migrate(self.root/'local.sqlite3',target);second=migrate(self.root/'local.sqlite3',target)
        self.assertEqual(first['inserted_records'],1);self.assertTrue(second['already_imported'])
        db=Database(target)
        try:
            self.assertEqual(db.conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)
            self.assertEqual(db.conn.execute('SELECT started_at FROM runs').fetchone()[0],'2026-09-01T12:00:00')
        finally:db.close()
