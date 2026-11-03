import unittest
from datetime import date
from schedule_guard import already_attempted, COLLECTION_STEP

class ScheduleGuardTests(unittest.TestCase):
    def check(self, event='schedule', current=2, run_id=1, **overrides):
        step = dict(name=COLLECTION_STEP, status='completed', conclusion='success',
                    started_at='2026-11-03T03:24:00Z', completed_at='2026-11-03T03:25:00Z')
        step.update(overrides)
        # Deliberately use yesterday's creation date: actual collection date wins.
        return already_attempted([dict(id=run_id, event=event, created_at='2026-11-02T00:00:00Z')],
            current, date(2026, 11, 3), lambda _: [dict(steps=[step])])

    def test_all_production_paths_and_same_run_rerun_block(self):
        for event in ('schedule', 'workflow_dispatch'):
            for run_id in (1, 2):
                self.assertTrue(self.check(event=event, run_id=run_id))

    def test_failed_cancelled_and_ambiguous_send_block(self):
        for conclusion in ('failure', 'cancelled', None):
            self.assertTrue(self.check(conclusion=conclusion))
        self.assertTrue(self.check(status='in_progress', conclusion=None, completed_at=None))

    def test_push_skipped_and_future_step_do_not_block(self):
        self.assertFalse(self.check(event='push'))
        self.assertFalse(self.check(conclusion='skipped'))
        self.assertFalse(self.check(status='pending', started_at=None, completed_at=None))

    def test_previous_day_and_midnight_crossing(self):
        self.assertFalse(self.check(started_at='2026-11-02T14:58:00Z', completed_at='2026-11-02T14:59:59Z'))
        self.assertTrue(self.check(started_at='2026-11-02T14:58:00Z', completed_at='2026-11-02T15:01:00Z'))
        self.assertTrue(self.check(started_at='2026-11-02T15:00:00Z'))

    def test_missing_history_and_api_failure_fail_closed(self):
        with self.assertRaises(ValueError):
            self.check(started_at=None)
        with self.assertRaises(RuntimeError):
            already_attempted([dict(id=1, event='schedule')], 2, date(2026, 11, 3),
                lambda _: (_ for _ in ()).throw(RuntimeError('API unavailable')))

if __name__ == '__main__':
    unittest.main()
