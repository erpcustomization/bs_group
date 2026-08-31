import frappe
from frappe.utils import getdate, today

NOTIFY_STATUSES = ("Expiring Soon", "Expired")


def update_employee_visa_status():
    current_date = getdate(today())

    employees = frappe.get_all(
        "Employee",
        filters={"status": ["!=", "Left"]},
        fields=[
            "name",
            "employee_name",
            "custom_visa_expiry_date",
            "custom_visa_status",
            "user_id",
        ],
    )

    for emp in employees:
        if not emp.custom_visa_expiry_date:
            status = "Pending"
        else:
            expiry_date = getdate(emp.custom_visa_expiry_date)
            days_left = (expiry_date - current_date).days

            if days_left < 0:
                status = "Expired"
            elif days_left <= 30:
                status = "Expiring Soon"
            else:
                status = "Valid"

        if status != emp.custom_visa_status:
            frappe.db.set_value(
                "Employee",
                emp.name,
                "custom_visa_status",
                status,
                update_modified=False
            )

            if status in NOTIFY_STATUSES:
                send_visa_status_email(emp, status)


def send_visa_status_email(employee, status):
    if not employee.user_id:
        return

    recipient = frappe.db.get_value("User", employee.user_id, "email")
    if not recipient:
        return

    expiry_date = getdate(employee.custom_visa_expiry_date)

    if status == "Expired":
        subject = "Your Visa Has Expired"
        message = (
            f"Dear {employee.employee_name},<br><br>"
            f"Your visa expired on {expiry_date.strftime('%d-%m-%Y')}. "
            "Please contact HR immediately to renew your visa.<br><br>Regards,<br>HR Team"
        )
    else:
        subject = "Your Visa is Expiring Soon"
        message = (
            f"Dear {employee.employee_name},<br><br>"
            f"Your visa is expiring on {expiry_date.strftime('%d-%m-%Y')}. "
            "Please contact HR to begin the renewal process.<br><br>Regards,<br>HR Team"
        )

    frappe.sendmail(recipients=[recipient], subject=subject, message=message, now=False)