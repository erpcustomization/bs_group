"""Format recorded GPS only; never request or transmit an employee's location."""
import math


def format_location(latitude, longitude):
    missing = 'Location not recorded'
    if latitude is None or longitude is None or latitude == '' or longitude == '':
        return missing
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return missing
    if (not math.isfinite(lat) or not math.isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180
            or (lat == 0 and lon == 0)):
        return missing
    return f'GPS {lat:.5f}, {lon:.5f}'
