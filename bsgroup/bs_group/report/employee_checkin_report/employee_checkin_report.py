# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import re
import time

import frappe
import requests
from frappe import _
from frappe.utils import add_days, getdate, nowdate, time_diff_in_hours

from bsgroup.utils.employee_checkin import _haversine_distance_meters

DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

_last_nominatim_call = 0.0


def execute(filters: dict | None = None):
	filters = filters or {}
	columns = get_columns(filters)
	data, summary = get_data(filters)
	return columns, data, None, None, summary


def get_leave_map(from_date, to_date, employee_names):
	"""Returns {(employee, date_str): label} for every day covered by an
	approved Leave Application in the given range.

	label is the Leave Type name (e.g. "Sick Leave"), "Half Day" for the
	half-day date of a half-day application, or "Absent" for Leave Without
	Pay leave types - which should still read as Absent, not as a leave.
	"""
	if not employee_names:
		return {}

	leave_apps = frappe.db.sql(
		"""
		SELECT la.employee, la.from_date, la.to_date, la.half_day, la.half_day_date,
			la.leave_type, lt.is_lwp
		FROM `tabLeave Application` la
		INNER JOIN `tabLeave Type` lt ON lt.name = la.leave_type
		WHERE la.docstatus = 1
		AND la.status = 'Approved'
		AND la.employee IN %(employees)s
		AND la.from_date <= %(to_date)s
		AND la.to_date >= %(from_date)s
		""",
		{"employees": employee_names, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)

	leave_map = {}
	for la in leave_apps:
		d = max(getdate(la.from_date), from_date)
		end = min(getdate(la.to_date), to_date)
		while d <= end:
			if la.is_lwp:
				label = "Absent"
			elif la.half_day and la.half_day_date and getdate(la.half_day_date) == d:
				label = "Half Day"
			else:
				label = la.leave_type
			leave_map[(la.employee, str(d))] = label
			d = add_days(d, 1)

	return leave_map


def get_columns(filters=None) -> list[dict]:
	cols = [
		{
			"label": _("Employee ID"),
			"fieldname": "employee",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Shift"),
			"fieldname": "shift",
			"fieldtype": "Link",
			"options": "Shift Type",
			"width": 120,
		},
		{
			"label": _("Status"),
			"fieldname": "checkin_status",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Date"),
			"fieldname": "work_date",
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"label": _("Day"),
			"fieldname": "day",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("Check-In Time"),
			"fieldname": "checkin_time",
			"fieldtype": "Datetime",
			"width": 180,
		},
		{
			"label": _("Check-Out Time"),
			"fieldname": "checkout_time",
			"fieldtype": "Datetime",
			"width": 180,
		},
		{
			"label": _("Total Working Hours"),
			"fieldname": "working_hours",
			"fieldtype": "Float",
			"width": 160,
		},
		{
			"label": _("Latitude"),
			"fieldname": "latitude",
			"fieldtype": "Float",
			"precision": 6,
			"width": 120,
		},
		{
			"label": _("Longitude"),
			"fieldname": "longitude",
			"fieldtype": "Float",
			"precision": 6,
			"width": 120,
		},
		{
			"label": _("Place"),
			"fieldname": "place",
			"fieldtype": "Data",
			"width": 160,
		},
	]
	return cols


def _parse_coordinate(value):
	"""Parse a latitude/longitude value that may be a plain number or a
	string like "23.6038° N" / "72.5714 W" into a signed float. Returns
	None if the value can't be parsed."""
	if value is None or value == "":
		return None
	if isinstance(value, (int, float)):
		return float(value)

	text = str(value).strip().upper()
	match = re.match(r"^(-?\d+(?:\.\d+)?)\s*[°\s]*\s*([NSEW]?)$", text)
	if not match:
		try:
			return float(text)
		except ValueError:
			return None

	number = float(match.group(1))
	direction = match.group(2)
	if direction in ("S", "W"):
		number = -abs(number)
	return number


def get_head_offices():
	"""All Head Office records with valid coordinates, for nearest-match lookup."""
	rows = frappe.db.get_all(
		"Head Office",
		filters=[["latitude", "is", "set"], ["longitude", "is", "set"]],
		fields=["name", "title", "latitude", "longitude", "allowd_distance_meters"],
	)
	offices = []
	for r in rows:
		r.latitude = _parse_coordinate(r.latitude)
		r.longitude = _parse_coordinate(r.longitude)
		if r.latitude is not None and r.longitude is not None:
			offices.append(r)
	return offices


def get_place(latitude, longitude, head_offices):
	"""Nearest Head Office name if the check-in falls within that office's
	allowed radius; otherwise a real-world address via reverse geocoding.
	Returns None only when there are no coordinates or geocoding fails."""
	lat, lon = _parse_coordinate(latitude), _parse_coordinate(longitude)
	if lat is None or lon is None:
		return None

	nearest = None
	nearest_distance = None

	for ho in head_offices:
		distance = _haversine_distance_meters(lat, lon, ho.latitude, ho.longitude)
		if nearest_distance is None or distance < nearest_distance:
			nearest = ho
			nearest_distance = distance

	if nearest is not None:
		allowed_m = float(nearest.allowd_distance_meters or 0)
		if not allowed_m or nearest_distance <= allowed_m:
			return nearest.title or nearest.name

	return reverse_geocode(lat, lon)


def reverse_geocode(latitude, longitude):
	"""Address for (latitude, longitude) via OpenStreetMap Nominatim,
	cached per rounded coordinate so repeat report runs and duplicate
	check-in points don't re-hit the API. Behaviour (on/off, URL, contact,
	rate limit, cache TTL) is configured in BS Group Settings > Geocoding."""
	global _last_nominatim_call

	settings = frappe.get_cached_doc("BS Group Settings")
	if not settings.enable_reverse_geocoding:
		return None

	cache_key = f"bsgroup:reverse_geocode:en:{round(latitude, 5)}:{round(longitude, 5)}"
	cache = frappe.cache()
	cached = cache.get_value(cache_key)
	if cached is not None:
		return cached or None

	min_interval = settings.nominatim_min_interval or 1.1
	cache_ttl = (settings.geocode_cache_ttl_days or 30) * 24 * 60 * 60
	user_agent = (
		f"bsgroup-frappe-app/1.0 ({settings.geocoding_contact_email})"
		if settings.geocoding_contact_email
		else "bsgroup-frappe-app/1.0"
	)

	address = None
	try:
		elapsed = time.time() - _last_nominatim_call
		if elapsed < min_interval:
			time.sleep(min_interval - elapsed)

		response = requests.get(
			settings.nominatim_url or DEFAULT_NOMINATIM_URL,
			params={"lat": latitude, "lon": longitude, "format": "jsonv2", "accept-language": "en"},
			headers={"User-Agent": user_agent},
			timeout=5,
		)
		_last_nominatim_call = time.time()
		response.raise_for_status()
		address = response.json().get("display_name")
	except Exception:
		frappe.log_error(
			title="Reverse Geocoding Failed",
			message=frappe.get_traceback(),
		)

	# Cache a failure too (as "") so a bad point doesn't get re-queried on
	# every report refresh within the TTL.
	cache.set_value(cache_key, address or "", expires_in_sec=cache_ttl)
	return address


def get_data(filters=None):
	filters = filters or {}

	from_date = getdate(filters.get("from_date") or nowdate())
	to_date = getdate(filters.get("to_date") or nowdate())
	employee_filter = filters.get("employee")
	status_filter = filters.get("status_filter")      # driven by card clicks
	checkin_status = filters.get("checkin_status")    # dropdown filter

	conditions = ["DATE(ec.time) BETWEEN %(from_date)s AND %(to_date)s"]
	params = {"from_date": from_date, "to_date": to_date}

	if employee_filter:
		conditions.append("ec.employee = %(employee)s")
		params["employee"] = employee_filter

	where_clause = "WHERE " + " AND ".join(conditions)

	# Checked-in rows: group by employee + date, pick first IN and last OUT
	checkin_rows = frappe.db.sql(
		f"""
		SELECT
			ec.employee,
			DATE(ec.time) AS work_date,
			MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END)  AS checkin_time,
			MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS checkout_time,
			SUBSTRING_INDEX(
				GROUP_CONCAT(CASE WHEN ec.log_type = 'IN' THEN ec.shift END ORDER BY ec.time ASC),
				',', 1
			) AS shift,
			SUBSTRING_INDEX(
				GROUP_CONCAT(CASE WHEN ec.log_type = 'IN' THEN ec.latitude END ORDER BY ec.time ASC),
				',', 1
			) AS latitude,
			SUBSTRING_INDEX(
				GROUP_CONCAT(CASE WHEN ec.log_type = 'IN' THEN ec.longitude END ORDER BY ec.time ASC),
				',', 1
			) AS longitude
		FROM `tabEmployee Checkin` ec
		{where_clause}
		GROUP BY ec.employee, DATE(ec.time)
		""",
		params,
		as_dict=True,
	)
	checkin_map = {(row.employee, str(row.work_date)): row for row in checkin_rows}

	# All active employees (optionally narrowed to the requested employee)
	emp_filters = {"status": "Active"}
	if employee_filter:
		emp_filters["name"] = employee_filter
	all_employees = frappe.db.get_all(
		"Employee",
		filters=emp_filters,
		fields=["name", "employee_name", "holiday_list", "company"],
	)

	leave_map = get_leave_map(from_date, to_date, [emp.name for emp in all_employees])
	head_offices = get_head_offices()

	standard_working_hours = (
		frappe.db.get_single_value("HR Settings", "standard_working_hours") or 8
	)
	half_day_hours = standard_working_hours / 2

	holiday_dates_by_list = {}

	def get_holiday_dates(holiday_list_name):
		"""Returns {date_str: status} for every Holiday date in the list -
		"Weekend" for the weekly off, "Holiday" for a named holiday - matching
		how Employee Monthly Attendance distinguishes the two."""
		if not holiday_list_name:
			return {}
		if holiday_list_name not in holiday_dates_by_list:
			rows = frappe.db.get_all(
				"Holiday",
				filters={
					"parent": holiday_list_name,
					"holiday_date": ["between", [from_date, to_date]],
				},
				fields=["holiday_date", "weekly_off"],
			)
			holiday_dates_by_list[holiday_list_name] = {
				str(r.holiday_date): ("Weekend" if r.weekly_off else "Holiday") for r in rows
			}
		return holiday_dates_by_list[holiday_list_name]

	company_default_holiday_list = {}

	def get_employee_holiday_list(emp):
		if emp.holiday_list:
			return emp.holiday_list
		if emp.company not in company_default_holiday_list:
			company_default_holiday_list[emp.company] = frappe.db.get_value(
				"Company", emp.company, "default_holiday_list"
			)
		return company_default_holiday_list[emp.company]

	# --- Build report rows: one row per employee per day in the range ---
	data = []
	work_dates = []
	d = from_date
	while d <= to_date:
		work_dates.append(d)
		d = add_days(d, 1)

	summary_counts = {"Half Day": 0, "Present": 0, "Absent": 0, "Weekend": 0}
	employees_present_set = set()
	employees_absent_set = set()

	for emp in all_employees:
		holiday_dates = get_holiday_dates(get_employee_holiday_list(emp))

		for work_date in work_dates:
			date_str = str(work_date)
			row = checkin_map.get((emp.name, date_str))
			checkin = row.checkin_time if row else None
			checkout = row.checkout_time if row else None
			shift = row.shift if row else None
			latitude = row.latitude if row else None
			longitude = row.longitude if row else None
			working_hours = None

			if checkin and checkout:
				working_hours = round(time_diff_in_hours(checkout, checkin), 2)
				if working_hours >= half_day_hours:
					status = "Present"
				else:
					status = "Half Day"
			elif checkin:
				status = "Present"
			elif date_str in holiday_dates:
				status = holiday_dates[date_str]
			else:
				status = "Absent"

			# An approved Leave Application should explain an otherwise-Absent
			# day - show its leave type (or "Half Day"), unless it's Leave
			# Without Pay, which stays Absent.
			leave_label = leave_map.get((emp.name, date_str))
			if status == "Absent" and leave_label:
				status = leave_label

			if status == "Absent":
				employees_absent_set.add(emp.name)
			elif status != "Weekend":
				employees_present_set.add(emp.name)

			summary_counts[status] = summary_counts.get(status, 0) + 1

			if status_filter == "checked_in" and not checkin:
				continue
			if status_filter == "not_checked_in" and status != "Absent":
				continue
			if checkin_status and checkin_status != status:
				continue

			data.append({
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"checkin_status": status,
				"work_date": work_date,
				"day": work_date.strftime("%A"),
				"shift": shift,
				"checkin_time": checkin,
				"checkout_time": checkout,
				"working_hours": working_hours,
				"latitude": latitude,
				"longitude": longitude,
				"place": get_place(latitude, longitude, head_offices),
			})

	data.sort(key=lambda r: (r["work_date"] is None, r["work_date"]), reverse=True)

	summary = [
		{"label": _("Total Employees"),          "value": len(all_employees),                "indicator": "blue",  "status_filter": "total"},
		{"label": _("Employees Present"),        "value": len(employees_present_set),         "indicator": "green", "status_filter": "checked_in"},
		{"label": _("Employees Absent"),         "value": len(employees_absent_set),          "indicator": "red",   "status_filter": "not_checked_in"},
	]

	return data, summary
