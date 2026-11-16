"""Current-user dashboard punches using normal HRMS insert permissions."""
import math
import frappe
from bsgroup.attendance_place import describe_location
from frappe.utils import now_datetime, cint, get_datetime


def previous_shift_open(emp, row, now):
    """Only changes available actions; never closes or edits an old punch."""
    if not row or row.log_type != 'IN':
        return False
    from hrms.hr.doctype.shift_assignment.shift_assignment import get_actual_start_end_datetime_of_shift
    stamp = get_datetime(row.time)
    if stamp >= now:
        return False
    current = get_actual_start_end_datetime_of_shift(emp, now, consider_default_shift=True)
    if current:
        return stamp < current['actual_start']
    previous = get_actual_start_end_datetime_of_shift(emp, stamp, consider_default_shift=True)
    if previous and now <= previous['actual_end']:
        return False  # An overnight shift must not reset at midnight.
    # Preserve off-shift/unassigned punching, with a new local working day.
    return stamp.date() < now.date()


def employee():
    rows=frappe.get_all('Employee',filters={'user_id':frappe.session.user,'status':'Active'},pluck='name',limit_page_length=2)
    if len(rows)!=1:
        frappe.throw('Ask HR to link your login to one active Employee record.')
    return rows[0]


def latest(emp):
    rows=frappe.get_all('Employee Checkin',filters={'employee':emp},fields=['name','log_type','time','latitude','longitude'],order_by='time desc, creation desc',limit_page_length=1)
    return rows[0] if rows else None


@frappe.whitelist()
def context():
    emp=employee()
    allowed=bool(cint(frappe.db.get_single_value('HR Settings','allow_employee_checkin_from_mobile_app'))) and frappe.has_permission('Employee Checkin','create')
    row=latest(emp)
    new_shift=previous_shift_open(emp, row, now_datetime())
    return dict(allowed=allowed,last_name=row.name if row else '',last_type=row.log_type if row else None,
                can_check_in=not row or row.log_type != 'IN' or new_shift,
                can_check_out=bool(row and row.log_type == 'IN' and not new_shift),
                previous_checkout_missing=new_shift,
                last_time=str(row.time) if row else None,
                last_location=describe_location(row.latitude, row.longitude) if row else None,
                location_required=bool(cint(frappe.db.get_single_value('HR Settings','allow_geolocation_tracking'))))


@frappe.whitelist(methods=['POST'])
def punch(log_type, expected_last='', latitude=None, longitude=None):
    if log_type not in ('IN','OUT'):
        frappe.throw('Choose Check In or Check Out.')
    emp=employee()
    frappe.db.sql('select name from `tabEmployee` where name=%s for update',(emp,))
    state=context()
    if not state['allowed']:
        frappe.throw('Check-in access is not enabled. Please contact HR.',frappe.PermissionError)
    if (expected_last or '')!=state['last_name']:
        frappe.throw('Attendance changed. Refresh and try again.')
    if not state['can_check_in' if log_type == 'IN' else 'can_check_out']:
        frappe.throw('This action does not match your latest attendance record. Refresh and try again.')
    if state['location_required'] and (latitude is None or longitude is None):
        frappe.throw('Allow location access to mark attendance.')
    coords={}
    if latitude is not None or longitude is not None:
        try:
            lat,lon=float(latitude),float(longitude)
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
                raise ValueError
        except (TypeError,ValueError):
            frappe.throw('A valid current location is required.')
        coords=dict(latitude=lat,longitude=lon)
    doc=frappe.get_doc(dict(doctype='Employee Checkin',employee=emp,log_type=log_type,time=now_datetime(),**coords))
    doc.insert()  # Preserve native permissions, shift rules and location validations.
    return dict(name=doc.name,log_type=doc.log_type,time=str(doc.time))
