"""Submission evidence cases; uses no production data or uploaded files."""
from pathlib import Path
import sys
from unittest.mock import patch
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
from bsgroup.dcs import supplier_evidence as evidence


def reject(message):
    raise frappe.ValidationError(message)


def blocked(rows):
    try:
        evidence.validate_supplier_quotations(frappe._dict(supplier_quotations=rows))
    except frappe.ValidationError:
        return
    raise AssertionError('Expected submission to be blocked')


with patch.object(evidence, '_', side_effect=lambda s:s), patch.object(frappe, 'throw', side_effect=reject):
    blocked([])
    blocked([frappe._dict(supplier_name='Vendor A')])
    with patch.object(frappe, 'get_all', return_value=[]):
        blocked([frappe._dict(quotation='/private/files/missing.pdf')])
    with patch.object(frappe, 'get_all', return_value=['FILE-1']), patch.object(evidence, 'has_permission', return_value=False):
        blocked([frappe._dict(quotation='/private/files/other-deal.pdf')])
    with patch.object(frappe, 'get_all', return_value=['FILE-1']), patch.object(evidence, 'has_permission', return_value=True):
        evidence.validate_supplier_quotations(frappe._dict(supplier_quotations=[
            frappe._dict(supplier_name='Vendor A',quotation='/private/files/a.pdf'),
            frappe._dict(supplier_name='Vendor B',quotation='/private/files/b.pdf')]))
        blocked([frappe._dict(quotation='/private/files/a.pdf'),frappe._dict()])
print('PASS missing, incomplete, deleted and inaccessible evidence blocked; multiple valid supplier files accepted')