"""Deterministic stage boundary and handoff tests; no business records written."""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
from bsgroup.opportunity_progress import resolve

now = datetime(2026, 10, 26, 12)
opp = frappe._dict(status='Open')
checks = 0
def check(expected, surveys=(), presales=(), sheets=(), opportunity=opp):
    global checks
    actual = resolve(opportunity, surveys, presales, sheets, now)['label']
    assert actual == expected, (expected, actual)
    checks += 1

check('Open')
for hours, expected in [(0,'Open with Site Survey Team'),(23.99,'Open with Site Survey Team'),(24,'Delayed by Site Survey Team'),(24.01,'Delayed by Site Survey Team'),(48,'2 days - Delayed by Site Survey Team'),(72,'3 days - Delayed by Site Survey Team')]:
    survey = frappe._dict(name='S',status='Requested',creation=now-timedelta(hours=hours))
    check(expected,[survey])
    survey.modified = now
    check(expected,[survey])
survey = frappe._dict(name='S',status='Completed',creation=now-timedelta(days=5),completed_on=now)
pre = frappe._dict(name='P',status='Site Survey Results Received',docstatus=0,custom_site_survey_request='S',creation=now-timedelta(days=5))
check('Open with Presales',[survey],[pre])
survey.completed_on = now-timedelta(hours=24)
check('Delayed by Presales',[survey],[pre])
survey.completed_on -= timedelta(seconds=1)
check('Delayed by Presales',[survey],[pre])
pre.custom_site_survey_request = None
check('5 days - Delayed by Presales',[],[pre])
pre.creation = now
check('Open with Presales',[],[pre])
for hours, expected in [(0,'Deal Cost Sheet in Progress'),(24,'Delayed Deal Cost Sheet'),(25,'Delayed Deal Cost Sheet'),(48,'2 days - Delayed Deal Cost Sheet')]:
    sheet = frappe._dict(docstatus=0,custom_deal_status='Draft',creation=now-timedelta(hours=hours))
    check(expected,[],[pre],[sheet])
    sheet.modified = now
    check(expected,[],[pre],[sheet])
sheet.docstatus=1
sheet.custom_deal_status='Submitted to Sales'
check('Submitted to Sales',[],[pre],[sheet])
sheet.docstatus=2
check('Open with Presales',[],[pre],[sheet])
sheet.docstatus=0
sheet.custom_record_authority='Superseded'
check('Open with Presales',[],[pre],[sheet])
for native in ('Lost','Closed','Converted','Quotation'):
    check(native,[survey],[pre],[sheet],frappe._dict(status=native))
print(f'PASS {checks} progress checks')
