import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import Application, serve
from patient_journal import delete_change, load_changes, upsert_change


class PatientJournalTests(unittest.TestCase):
    def app(self, home, serial='A'):
        result = Application(home)
        result.data = SimpleNamespace(catalog={'device': {'serial': serial}})
        return result

    def test_legacy_context_and_explicit_previous_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            values = {
                'A|2026-08-01|2026-08-07': {
                    'mask_off': 'yes',
                },
                'A|2026-08-02|2026-08-08': {
                    'mask_off': 'yes',
                    '_saved_at': '2026-08-08T10:00:00',
                },
                'A|2026-08-03|2026-08-08': {
                    'mask_off': 'no',
                    '_saved_at': '2026-08-08T11:00:00',
                },
                'A|2026-09-10|2026-09-11': {
                    'mask_off': 'yes',
                    '_saved_at': '2026-09-11T12:00:00',
                },
                'B|2026-12-01|2026-12-02': {
                    'mask_off': 'yes',
                    '_saved_at': '2026-12-02T12:00:00',
                },
            }
            (Path(temp) / 'patient-contexts.json').write_text(
                json.dumps(values), encoding='utf-8')
            app = self.app(temp)

            # A legacy record remains readable by its original fields and has
            # no fabricated save timestamp.
            legacy = app.get_context('2026-08-01', '2026-08-07')
            self.assertEqual(legacy['mask_off'], 'yes')
            self.assertNotIn('_saved_at', legacy)

            self.assertEqual(app.get_context('2026-09-01', '2026-09-07'), {})
            current = app.report_context('2026-09-01', '2026-09-07')
            previous = current['_previous_context']
            self.assertEqual((previous['start'], previous['end']), ('2026-08-03', '2026-08-08'))
            self.assertEqual(previous['saved_at'], '2026-08-08T11:00:00')
            self.assertEqual(previous['context']['mask_off'], 'no')
            self.assertNotIn('B|2026-12-01|2026-12-02', current)

            # A future period and another device are never candidates.
            app.save_context('2026-09-01', '2026-09-07', {'sleepiness': 'no'})
            saved = app.get_context('2026-09-01', '2026-09-07')
            self.assertNotIn('_saved_at', saved)
            self.assertEqual(saved['sleepiness'], 'no')
            self.assertIn('_saved_at', app.report_context('2026-09-01', '2026-09-07'))

    def test_change_crud_validation_persistence_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            created = upsert_change(temp, 'A', {
                'date': '2026-09-01', 'kind': 'mask', 'note': '更换鼻罩',
            })
            self.assertEqual(created['kind'], 'mask')
            self.assertEqual(created['note'], '更换鼻罩')
            self.assertEqual(len(created['id']), 32)
            self.assertEqual((Path(temp) / 'patient-changes.json').stat().st_mode & 0o777, 0o600)

            updated = upsert_change(temp, 'A', {
                'id': created['id'], 'date': '2026-09-02',
                'kind': 'comfort', 'note': '',
            })
            self.assertEqual(updated['id'], created['id'])
            self.assertEqual(updated['created_at'], created['created_at'])
            self.assertEqual(updated['date'], '2026-09-02')
            self.assertEqual(load_changes(temp, 'A')[0], updated)

            removed = delete_change(temp, 'A', created['id'])
            self.assertEqual(removed['id'], created['id'])
            self.assertEqual(load_changes(temp, 'A'), [])
            with self.assertRaises(ValueError):
                delete_change(temp, 'A', created['id'])

            for value in [
                {'date': '2026-02-29', 'kind': 'mask', 'note': ''},
                {'date': '1999-12-31', 'kind': 'mask', 'note': ''},
                {'date': '2100-01-01', 'kind': 'mask', 'note': ''},
                {'date': '2026-09-01', 'kind': 'unknown', 'note': ''},
                {'date': '2026-09-01', 'kind': 'mask', 'note': 'x' * 1001},
            ]:
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        upsert_change(temp, 'A', value)
            with self.assertRaises(ValueError):
                upsert_change(temp, 'A', {
                    'id': 'missing', 'date': '2026-09-01', 'kind': 'mask', 'note': '',
                })

    def test_changes_are_isolated_by_device(self):
        with tempfile.TemporaryDirectory() as temp:
            a = upsert_change(temp, 'A', {'date': '2026-09-01', 'kind': 'mask', 'note': ''})
            b = upsert_change(temp, 'B', {'date': '2026-09-02', 'kind': 'clinician', 'note': '复诊'})
            self.assertEqual([item['id'] for item in load_changes(temp, 'A')], [a['id']])
            self.assertEqual([item['id'] for item in load_changes(temp, 'B')], [b['id']])
            self.assertEqual([item['id'] for item in self.app(temp, 'A').get_changes()], [a['id']])

    def test_make_report_exposes_context_metadata_without_prefilling(self):
        with tempfile.TemporaryDirectory() as temp:
            rows = [{
                'date': f'2026-09-{day:02d}', 'minutes': 360,
                'current': False, 'counts': {'OSA': 0, 'CSA': 0, 'HYP': 0},
                'wave': False, 'index': 0,
            } for day in range(1, 8)]
            app = self.app(temp)
            app.data = SimpleNamespace(
                catalog={'device': {'serial': 'A', 'model': 'TEST'}},
                overview=lambda: {'days': rows},
            )
            app.save_context('2026-08-01', '2026-08-07', {'mask_off': 'yes'})

            report = app.make_report('2026-09-01', '2026-09-07')
            self.assertIsNone(report['context_saved_at'])
            self.assertEqual(report['context']['mask_off'], 'unknown')
            self.assertEqual(report['previous_context']['context']['mask_off'], 'yes')

            app.save_context('2026-09-01', '2026-09-07', {'mask_off': 'no'})
            report = app.make_report('2026-09-01', '2026-09-07')
            self.assertIsInstance(report['context_saved_at'], str)
            self.assertEqual(report['context']['mask_off'], 'no')
            self.assertNotIn('_saved_at', report['context'])

    def test_change_post_keeps_same_origin_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            app = self.app(temp)
            server, url = serve(app, host='127.0.0.1')
            try:
                body = json.dumps({
                    'date': '2026-09-01', 'kind': 'mask', 'note': '',
                }).encode()
                request = Request(url + 'api/change', data=body, method='POST', headers={
                    'Content-Type': 'application/json',
                    'Origin': 'http://127.0.0.1:' + str(server.server_port),
                })
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read())
                self.assertTrue(payload['saved'])
                self.assertEqual(payload['change']['kind'], 'mask')

                request = Request(url + 'api/change', data=body, method='POST', headers={
                    'Content-Type': 'application/json', 'Origin': 'http://evil.example',
                })
                with self.assertRaises(HTTPError) as error:
                    urlopen(request, timeout=3)
                self.assertEqual(error.exception.code, 403)
                error.exception.read()
                error.exception.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
