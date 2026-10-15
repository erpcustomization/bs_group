"""DCS money precision; never converts amounts between currencies."""
from frappe.utils import flt

def money_precision(currency):
    return 3 if (currency or "").upper() == "OMR" else 2

def money_round(value, currency):
    return flt(value, money_precision(currency))

def money_tolerance(currency):
    return 0.5 * 10 ** -money_precision(currency)
