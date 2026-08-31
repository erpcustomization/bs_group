import frappe
import math
from frappe import _, throw
from frappe.utils import getdate


@frappe.whitelist()
def validate_employee_location(latitude, longitude, log_type="Check-in"):
    """
    Validates whether the calling employee is within the allowed distance
    of their mapped Head Office.

    Args:
        latitude  (float): Employee's current latitude.
        longitude (float): Employee's current longitude.
        log_type  (str):   Label used in the error message (e.g. "Check-in").

    Returns:
        dict: {"status": "Success"} or {"status": "Failed", "message": "..."}
    """
    employee = frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user},
        ["name", "employee_name", "custom_head_office"],
        as_dict=True,
    )

    if not employee:
        frappe.throw("No Employee record linked to your account.")

    if not employee.custom_head_office:
        # No head office mapped — allow by default
        return {"status": "Success"}

    ho = frappe.db.get_value(
        "Head Office",
        employee.custom_head_office,
        ["latitude", "longitude", "allowd_distance_meters", "title"],
        as_dict=True,
    )

    if not ho or not ho.latitude or not ho.longitude:
        return {"status": "Success"}

    distance_m = _haversine_distance_meters(
        float(latitude), float(longitude),
        float(ho.latitude), float(ho.longitude),
    )
    allowed_m = float(ho.allowd_distance_meters or 0)

    if distance_m <= allowed_m:
        return {"status": "Success"}

    return {
        "status": "Failed",
        "message": (
            f"To {log_type}, you must be within {allowed_m:.0f} m of "
            f"{ho.title or 'your Head Office'}. "
            f"You are currently {distance_m:.0f} m away."
        ),
    }


def _haversine_distance_meters(lat1, lon1, lat2, lon2):
    """Returns the great-circle distance in metres between two lat/lon points."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def validate_ho_distance_latlng(log_type,latitude,longitude,custom_ho):
    import requests
    frappe.log_error("validate_ho_distance_latlng", [log_type, latitude, longitude, custom_ho])
    destinations = ""
    hos = frappe.db.get_all("Head Office",
                order_by = "creation DESC",
                fields = ['address','latitude','longitude','allowd_distance_meters'],
                limit_page_length=100)
    if hos:
        for h in hos:
            # destinations += h.latitude+","+h.longitude
            distance_results = frappe.db.sql("""
                                SELECT  
                                SQRT(POW(69.1 * (%(from_latitude)s - %(to_latitude)s), 2) + 
                                POW(69.1 * (%(to_longitude)s - %(from_longitude)s) * 
                                COS(%(from_latitude)s / 57.3), 2)) AS distance
                                """,{"from_latitude":latitude,
                                    "to_latitude":h.latitude,
                                    "from_longitude":longitude,
                                    "to_longitude":h.longitude,
                                    },as_dict=1)
            # frappe.log_error(title="distance_results",message=distance_results)
            is_allowed = 0
            if distance_results:
                if float(distance_results[0].distance)<=float(h.allowd_distance_meters):
                    is_allowed = 1
            if is_allowed==1:
                return {"status":"Success"}
            return {"status":"Failed","message":"To check "+log_type+", you must be within "+"{:.2f}".format(float(h.allowd_distance_meters))+" meters from the head office."}
    return {"status":"Success"}
 
 

def validate_ho_distance(log_type, from_location, custom_ho):
    import requests
    frappe.log_error("validate_ho_distance",[log_type, from_location, custom_ho])

    destinations = ""
    hos = frappe.db.get_all(
        "Homegenie Head Office",
        order_by="creation DESC",
        filters={"name": custom_ho},
        fields=["address", "latitude", "longitude", "allowd_distance_meters"],
        limit_page_length=100,
    )
    if hos:
        for h in hos:
            # destinations += h.latitude+","+h.longitude
            destinations = h.address
            maps = frappe.get_single("Google Settings")
            if maps.enable:
                GOOGLE_MAPS_API_URL = (
                    "https://maps.googleapis.com/maps/api/distancematrix/json"
                )
                params = {
                    "key": maps.api_key,
                    "origins": from_location,
                    "destinations": destinations,
                    "mode": "driving",
                }
                req = requests.get(GOOGLE_MAPS_API_URL, params=params)
                res = req.json()
                if res.get("rows"):
                    is_allowed = 0
                    for x in res.get("rows")[0].get("elements"):
                        if x.get("distance"):
                            if float(x.get("distance").get("value")) <= float(
                                h.allowd_distance_meters
                            ):
                                is_allowed = 1
                    if is_allowed == 1:
                        return {"status": "Success"}
                return {
                    "status": "Failed",
                    "message": "To check "
                    + log_type
                    + ", you must be within "
                    + "{:.2f}".format(float(h.allowd_distance_meters))
                    + " meters from the head office.",
                }
    return {"status": "Success"}


class HolidayListEnglishDescriptionMixin:
 """Force "Add Local Holidays" to fetch holiday names in English.

 The `holidays` PyPI library only translates names when the exact
 locale code is one of that country's `supported_languages` (e.g. UAE
 only recognises "en_US", not "en"). erpnext passes `frappe.local.lang`
 verbatim, which is usually just "en", so the match fails silently and
 the library falls back to the country's own default language (Arabic,
 French, etc). Here we pick whichever English variant the country
 actually supports before calling into the library.
 """

 @frappe.whitelist()
 def get_local_holidays(self):
  import holidays as holidays_module
  from holidays import country_holidays

  if not self.country:
   throw(_("Please select a country"))

  existing_holidays = self.get_holidays()
  from_date = getdate(self.from_date)
  to_date = getdate(self.to_date)

  country_class = getattr(holidays_module, self.country, None)
  supported_languages = getattr(country_class, "supported_languages", ()) or ()
  language = next((lang for lang in supported_languages if lang.startswith("en")), None)

  for holiday_date, holiday_name in country_holidays(
   self.country,
   subdiv=self.subdivision,
   years=list(range(from_date.year, to_date.year + 1)),
   language=language,
  ).items():
   if holiday_date in existing_holidays:
    continue

   if holiday_date < from_date or holiday_date > to_date:
    continue

   self.append(
    "holidays", {"description": holiday_name, "holiday_date": holiday_date, "weekly_off": 0}
   )
 