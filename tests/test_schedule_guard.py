import unittest
from datetime import date
from schedule_guard import already_attempted, COLLECTION_STEP


class ScheduleGuardTests(unittest.TestCase):
    def check(self, *, conclusion='success', started='2026-11-02T00:01:00Z',
              event='schedule', created='2026-11-02T00:00:00Z', run_id=1):
        return already_attempted(
            [{'id': run_id, 'event': event, 'created_at': created}],
            2, date(2026, 11, 2), lambda _: [{'steps': [{
                'name': COLLECTION_STEP, 'started_at': started,
                'conclusion': conclusion}]}])

    def test_success_and_ambiguous_failure_block_duplicate(self):
        for conclusion in ('success', 'failure', 'cancelled', None):
            with self.subTest(conclusion=conclusion):
                self.assertTrue(self.check(conclusion=conclusion))

    def test_no_collection_started_allows_recovery(self):
        self.assertFalse(self.check(started=None))
        self.assertFalse(self.check(conclusion='skipped'))

    def test_dry_run_and_current_run_do_not_block(self):
        self.assertFalse(self.check(event='push'))
        self.assertFalse(self.check(event='workflow_dispatch'))
        self.assertFalse(self.check(run_id=2))

    def test_jst_boundary_and_previous_day(self):
        self.assertFalse(self.check(created='2026-11-01T14:59:59Z'))
        self.assertTrue(self.check(created='2026-11-01T15:00:00Z'))


if __name__ == '__main__':
    unittest.main()
