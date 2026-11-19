"""Small Teams-compatible HTML blocks shared by private and group summaries.

Explicit line breaks preserve spacing even if Teams strips CSS margins.
"""
from collections import OrderedDict
from datetime import date
from html import escape


def unique_rows(rows):
    return list({row['task']: row for row in rows}.values())


def introduction(day, region):
    return (f'<p><b>These are the tasks scheduled for tomorrow ({day:%d %B %Y}) — {escape(region)}.</b>'
        '<br/>Please review your assigned work below.</p>')


def employee_section(employee, rows):
    rows = unique_rows(rows)
    projects = OrderedDict()
    for row in rows:
        key = row.get('project') or row['project_title']
        projects.setdefault(key, []).append(row)
    parts = [f'<p><b>{escape(employee)}</b><br/>{len(rows)} task(s) · {len(projects)} project(s)</p>']
    for items in projects.values():
        parts.append('<p><b>Project: ' + escape(items[0]['project_title']) + '</b></p>')
        for index, row in enumerate(items, 1):
            due = str(row.get('due_date') or '')[:10]
            if due:
                try:
                    due = date.fromisoformat(due).strftime('%d %b %Y')
                except ValueError:
                    pass
            parts.append('<p>' + str(index) + '. <b>' + escape(row['task_title']) + '</b><br/>'
                + escape(row['task'])
                + (' · Due: ' + escape(due) if due else ' · Due date not set')
                + (' · <b>OVERDUE</b>' if row.get('status') == 'Overdue' else '') + '</p>')
    return ''.join(parts)


def footer():
    return '<p><br/>Please update your daily work and task status in the project’s Project Plan.</p>'
