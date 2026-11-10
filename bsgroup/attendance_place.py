"""Display already stored place names alongside permission-scoped punch GPS.

No coordinates are sent to an external mapping service from attendance views.
"""
import frappe
from bsgroup.attendance_location import format_location


def describe_location(latitude, longitude, head_offices=None):
    gps = format_location(latitude, longitude)
    if gps == 'Location not recorded':
        return gps
    lat, lon = float(latitude), float(longitude)
    try:
        key = f'bsgroup:reverse_geocode:en:{round(lat, 5)}:{round(lon, 5)}'
        cached = frappe.cache.get_value(key)
        if isinstance(cached, str) and cached.strip():
            return f'{cached.strip()} · {gps} · © OpenStreetMap contributors'
        from bsgroup.bs_group.report.employee_checkin_report.employee_checkin_report import get_head_offices, get_place
        offices = head_offices
        if offices is None:
            local = getattr(frappe, 'local', None)
            offices = getattr(local, 'bs_attendance_place_offices', None)
            if offices is None:
                offices = get_head_offices()
                if local is not None:
                    local.bs_attendance_place_offices = offices
        place = get_place(lat, lon, offices, allow_external=False)
        if place:
            return f'{place} · {gps}'
    except Exception:
        # A missing office setup or cache outage must not hide recorded punches.
        pass
    return f'Place name unavailable · {gps}'
