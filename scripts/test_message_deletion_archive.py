"""Tests for deleted message archive and backup purge behavior."""
import os
import sqlite3
import tempfile
import unittest
import zipfile


class MessageDeletionArchiveTests(unittest.TestCase):
    def test_internal_permanent_delete_archives_before_removal(self):
        from app import app, User
        from scripts.simulate_security_harness import _login_client
        from message_deletion_archive import count_pending_archive, list_pending_archive_items

        with app.app_context():
            arch = User.query.filter_by(email='test@arch.com').first()
            self.assertIsNotNone(arch)
            with app.test_client() as client:
                _login_client(client, arch, app)
                client.get('/email?tab=internal')
                with client.session_transaction() as sess:
                    token = sess.get('casepm_csrf_token')
                headers = {'X-CSRF-Token': token, 'Content-Type': 'application/json'}
                subject_token = f'archive test {int(__import__("time").time() * 1000)}'
                sent = client.post('/api/internal-messages', json={
                    'to': ['admin@casepm.local'],
                    'subject': subject_token,
                    'body': '<p>archive me</p>',
                    'project_id': 1,
                }, headers=headers)
                self.assertEqual(sent.status_code, 200, sent.get_json())
                listed = client.get('/api/internal-messages').get_json()
                sent_row = next(r for r in listed if r.get('folder') == 'sent' and r.get('subject') == subject_token)
                msg_id = sent_row['id']
                pending_before = count_pending_archive()
                trashed = client.delete(f'/api/internal-messages/{msg_id}', headers=headers)
                self.assertEqual(trashed.status_code, 200)
                self.assertFalse(trashed.get_json().get('permanent'))
                deleted = client.delete(f'/api/internal-messages/{msg_id}', headers=headers)
                self.assertEqual(deleted.status_code, 200)
                self.assertTrue(deleted.get_json().get('permanent'))
                self.assertFalse(any(r.get('id') == msg_id for r in client.get('/api/internal-messages').get_json()))
                self.assertGreater(count_pending_archive(), pending_before)
                archived = [i for i in list_pending_archive_items() if i.get('source') == 'internal' and str(i.get('original_id')) == str(msg_id)]
                self.assertEqual(len(archived), 1)
                self.assertEqual(archived[0]['payload'].get('subject'), subject_token)

    def test_email_trash_delete_archives_removed_messages(self):
        from app import app, User
        from scripts.simulate_security_harness import _login_client
        from message_deletion_archive import list_pending_archive_items

        with app.app_context():
            user = User.query.filter_by(email='admin@casepm.local').first()
            self.assertIsNotNone(user)
            with app.test_client() as client:
                token = _login_client(client, user, app)
                client.get('/email?tab=internal')
                with client.session_transaction() as sess:
                    token = sess.get('casepm_csrf_token') or token
                headers = {'X-CSRF-Token': token, 'Content-Type': 'application/json'}
                client.put('/api/email/mailbox', json={'messages': [], 'meta': {}}, headers=headers)
                msg_id = f'mail-archive-test-{int(__import__("time").time() * 1000)}'
                msg = {
                    'id': msg_id,
                    'folder': 'trash',
                    'subject': 'Trash delete archive test',
                    'from': 'Sender',
                    'fromEmail': 'sender@example.com',
                    'to': ['test@arch.com'],
                    'preview': 'preview',
                    'body': '<p>body</p>',
                    'date': '2026-07-24T00:00:00Z',
                    'unread': False,
                }
                put = client.put('/api/email/mailbox', json={'messages': [msg], 'meta': {}}, headers=headers)
                self.assertEqual(put.status_code, 200, put.get_json())
                put2 = client.put('/api/email/mailbox', json={'messages': [], 'meta': {}}, headers=headers)
                self.assertEqual(put2.status_code, 200, put2.get_json())
                self.assertGreaterEqual(put2.get_json().get('archived_deleted', 0), 1)
                archived = [i for i in list_pending_archive_items() if i.get('source') == 'email' and i.get('original_id') == msg_id]
                self.assertEqual(len(archived), 1)
                self.assertEqual(archived[0]['payload'].get('subject'), 'Trash delete archive test')

    def test_backup_purges_archived_deleted_messages_after_success(self):
        from unittest.mock import patch
        from message_deletion_archive import (
            archive_deleted_message,
            count_pending_archive,
            export_pending_archive_document,
            finalize_archive_after_backup,
        )
        from backup_service import create_local_backup

        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, 'case_pm.db')
            backup_dir = os.path.join(td, 'backups')
            os.makedirs(backup_dir)
            conn = sqlite3.connect(db_path)
            conn.execute('CREATE TABLE placeholder (id INTEGER)')
            conn.commit()
            conn.close()

            archive_deleted_message('email', 1, 'x-1', {'subject': 'purge test'}, db_path=db_path)
            self.assertEqual(count_pending_archive(db_path=db_path), 1)

            with patch('backup_service.DB_PATH', db_path), patch('message_deletion_archive.DB_PATH', db_path):
                result = create_local_backup(note='test', config={'local_path': backup_dir}, progress_cb=None)
            self.assertTrue(result.get('ok'))
            zip_path = result['path']
            self.assertTrue(os.path.isfile(zip_path))

            with zipfile.ZipFile(zip_path, 'r') as zf:
                self.assertIn('case_pm.db', zf.namelist())
                self.assertIn('deleted_messages_archive.json', zf.namelist())

            self.assertEqual(count_pending_archive(db_path=db_path), 0)
            purge = result.get('deleted_messages_purged') or {}
            self.assertGreaterEqual(int(purge.get('purged') or 0), 1)

            doc = export_pending_archive_document(db_path=db_path)
            self.assertEqual(doc.get('pending_count'), 0)

            again = finalize_archive_after_backup(result['filename'], db_path=db_path)
            self.assertEqual(again.get('marked'), 0)


if __name__ == '__main__':
    unittest.main()
