import unittest
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('tech_ops_tickets',
    Path(__file__).resolve().parents[1] / 'bsgroup' / 'tech_ops_tickets.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
merge_scheduled_tickets = module.merge_scheduled_tickets


class TicketScheduleTests(unittest.TestCase):
    def ticket(self, **changes):
        data = dict(name=42, subject="Visit", status="Open", status_category="Open",
            _assign='["a@example.com", "b@example.com"]', custom_next_action_date="2026-11-19")
        data.update(changes)
        return data

    def merge(self, tickets, rows=None, assignments=None, user=None):
        return merge_scheduled_tickets(rows or [], tickets, assignments or [], "2026-11-18", user)

    def test_scheduled_for_each_assignee(self):
        rows = self.merge([self.ticket()])
        self.assertEqual({r['resource'] for r in rows}, {'a@example.com', 'b@example.com'})
        self.assertEqual({r['date'] for r in rows}, {'2026-11-19'})

    def test_exact_duplicate_and_repeat_refresh(self):
        existing = dict(category='HD Ticket', ticket_id='42', date='2026-11-19', resource='a@example.com')
        rows = self.merge([self.ticket()], [existing, existing])
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(self.merge([self.ticket()], rows)), 2)

    def test_same_title_different_ticket_and_date_preserved(self):
        self.assertEqual(len(self.merge([self.ticket(), self.ticket(name=43)])), 4)
        rows = self.merge([self.ticket()], [dict(category='HD Ticket', ticket_id='42',
            date='2026-11-18', resource='a@example.com')])
        self.assertEqual(len(rows), 3)

    def test_closed_merged_past_undated_unassigned(self):
        for change in [dict(status='Closed'), dict(status_category='Resolved'), dict(is_merged=1),
                dict(custom_next_action_date='2026-11-17'), dict(custom_next_action_date=None), dict(_assign='[]')]:
            self.assertEqual(self.merge([self.ticket(**change)]), [])

    def test_assignment_date_fallback_and_action_date_precedence(self):
        assignment = dict(reference_name='42', allocated_to='a@example.com', date='2026-11-20', status='Open')
        rows = self.merge([self.ticket(custom_next_action_date=None)], assignments=[assignment, assignment])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['date'], '2026-11-20')
        rows = self.merge([self.ticket()], assignments=[assignment])
        self.assertEqual({r['date'] for r in rows}, {'2026-11-19'})

    def test_limited_user_only_and_project_rows_preserved(self):
        project = dict(category='Project', date='2026-11-19', resource='a@example.com')
        rows = self.merge([self.ticket()], [project], user='a@example.com')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], project)
        self.assertTrue(all(r['resource'] == 'a@example.com' for r in rows))


if __name__ == '__main__':
    unittest.main()
