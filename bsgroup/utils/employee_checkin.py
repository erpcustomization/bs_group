import math
import frappe


def validate_checkin_location(doc, method=None):
    if not doc.latitude or not doc.longitude:
        return

    employee = frappe.db.get_value(
        "Employee",
        doc.employee,
        ["employee_name", "custom_head_office"],
        as_dict=True,
    )

    if not employee or not employee.custom_head_office:
        return

    ho = frappe.db.get_value(
        "Head Office",
        employee.custom_head_office,
        ["latitude", "longitude", "allowd_distance_meters", "title"],
        as_dict=True,
    )

    if not ho or not ho.latitude or not ho.longitude:
        return

    distance_m = _haversine_distance_meters(
        float(doc.latitude), float(doc.longitude),
        float(ho.latitude), float(ho.longitude),
    )
    allowed_m = float(ho.allowd_distance_meters or 0)

    if distance_m > allowed_m:
        frappe.throw(
            f"Check-in not allowed. You must be within {allowed_m:.0f} m of "
            f"{ho.title or employee.custom_head_office}. "
            f"Your current distance is {distance_m:.0f} m.",
            title="Location Validation Failed",
        )


def _haversine_distance_meters(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
