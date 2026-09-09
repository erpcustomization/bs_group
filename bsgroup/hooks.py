app_name = "bsgroup"
app_title = "BS Group"
app_publisher = "Tridots Tech"
app_description = "Customizations for BS Group"
app_email = "info@tridotstech.com"
app_license = "mit"

# Apps
# ------------------
# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "bsgroup",
# 		"logo": "/assets/bsgroup/logo.png",
# 		"title": "BS Group",
# 		"route": "/bsgroup",
# 		"has_permission": "bsgroup.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/bsgroup/css/bsgroup.css"
# app_include_js = "/assets/bsgroup/js/bsgroup.js"

# include js, css files in header of web template
# web_include_css = "/assets/bsgroup/css/bsgroup.css"
# web_include_js = "/assets/bsgroup/js/bsgroup.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "bsgroup/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "bsgroup/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "bsgroup.utils.jinja_methods",
# 	"filters": "bsgroup.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "bsgroup.install.before_install"
# after_install = "bsgroup.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "bsgroup.uninstall.before_uninstall"
# after_uninstall = "bsgroup.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "bsgroup.utils.before_app_install"
# after_app_install = "bsgroup.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "bsgroup.utils.before_app_uninstall"
# after_app_uninstall = "bsgroup.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "bsgroup.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"bsgroup.tasks.all"
# 	],
# 	"daily": [
# 		"bsgroup.tasks.daily"
# 	],
# 	"hourly": [
# 		"bsgroup.tasks.hourly"
# 	],
# 	"weekly": [
# 		"bsgroup.tasks.weekly"
# 	],
# 	"monthly": [
# 		"bsgroup.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "bsgroup.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "bsgroup.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------

# override_whitelisted_methods = {
#    "frappe.desk.doctype.event.event.get_events": "bsgroup.event.get_events"
# }

# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "bsgroup.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["bsgroup.utils.before_request"]
# after_request = ["bsgroup.utils.after_request"]

# Job Events
# ----------
# before_job = ["bsgroup.utils.before_job"]
# after_job = ["bsgroup.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"bsgroup.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# on_login = "bsgroup.utils.company_access.validate_company_on_login"

app_include_js = [
    "bsgroup.bundle.js",
    "navbar_custom.bundle.js",
    # "/assets/bsgroup/js/bs_welcome_banner.js",
]
app_include_css = [
    "/assets/bsgroup/css/sidebar.css",
    # "/assets/bsgroup/css/bs_welcome_banner.css",
]

website_context = {
    "favicon": "/assets/bsgroup/img/favicon.png",
    "splash_image": "/assets/bsgroup/img/logo.png",
}

permission_query_conditions = {
    "Lead": "bsgroup.permissions.get_common_conditions",
    "Opportunity": "bsgroup.permissions.get_common_conditions",
    "Presales Request": "bsgroup.permissions.get_common_conditions",
    "Deal Cost Sheet": "bsgroup.permissions.get_deal_cost_sheet_query_conditions",
    "Quotation": "bsgroup.permissions.get_common_conditions",
    "Customer": "bsgroup.permissions.get_customer_query_conditions",
    "Sales Target GP Entry": "bsgroup.permissions.get_sales_target_gp_entry_query_conditions",
    "*": "bsgroup.utils.company_access.global_company_condition",
}

has_permission = {
    "Customer": "bsgroup.permissions.has_customer_permission",
}

override_doctype_class = {
    "Timesheet": "bsgroup.overrides.timesheet.CustomTimesheet",
}

override_doctype_dashboards = {
    "Employee": "bsgroup.overrides.employee_dashboard.get_dashboard_for_employee",
}
ignore_links_on_delete = ["Deal Cost Sheet", "Quotation"]

doctype_js = {
    "Item": "public/js/item.js",
    "Employee": "public/js/employee.js",
    "Lead": 'public/js/Lead.js',
    "Opportunity": "public/js/opportunity.js",
    "Quotation": 'public/js/quotation.js',
    "Project": 'public/js/project.js',
    "Task": "public/js/task.js",
    "Timesheet": "public/js/timesheet.js",
    "Leave Application": "public/js/leave_application.js",
    "Material Request": "public/js/material_request.js",
    "HD Ticket": ["public/js/hd_ticket_service_report.js", "public/js/hd_ticket.js"],
    "Tech Task Scheduler": "public/js/tech_task_scheduler.js",
}

doctype_list_js = {
    "Project": "public/js/project_list.js",
    "Presales Request": "public/js/presales_request_list.js",
    "PPM Management": "public/js/ppm_management_list.js",
}

doc_events = {
    "Attendance": {
        "on_submit": "bsgroup.utils.attendance.create_comp_off_on_attendance_submit",
    },
    "Employee Checkin": {
        "validate": "bsgroup.utils.employee_checkin.validate_checkin_location",
    },
    "Organization Document": {
        "validate": "bsgroup.bs_group.doctype.organization_document_category.organization_document_category.validate_leaf_category",
    },
    "Employee": {
        "on_update": "bsgroup.utils.employee.create_holiday_list_assignment",
    },
    "Timesheet Detail": {
        "on_change": "bsgroup.overrides.timesheet.sync_row_status_on_change",
    },
    "Timesheet": {
        "on_submit": "bsgroup.overrides.timesheet.sync_scheduler_execution_link_on_submit",
        "on_update": "bsgroup.overrides.timesheet.sync_scheduler_execution_link_on_save",
        "before_cancel": "bsgroup.overrides.timesheet.release_scheduler_execution_before_cancel",
    },
    "Leave Application": {
        "validate": "bsgroup.utils.leave_application.validate_medical_certificate",
    },
    "Sales Person": {
        "validate": "bsgroup.utils.sales_person.validate_targets",
    },
    "Task": {
        "before_validate": [
            # Must run before core Task.validate() -> validate_status() ->
            # close_all_assignments(), which clears _assign as soon as status
            # becomes Completed. This guard needs to read _assign as it was
            # BEFORE that happens, so it cannot run as a "validate" hook.
            "bsgroup.utils.task.validate_zztest_task_closure_authority",
        ],
        "validate": [
            "bsgroup.utils.task.validate_completion_from_blocked_status",
            "bsgroup.utils.task.validate_milestone_requirements",
        ],
        "on_update": [
            "bsgroup.utils.task.sync_zztest_task_scheduler_status",
        ],
    },
    "HD Ticket": {
        "validate": [
            "bsgroup.utils.hd_ticket.set_customer_from_domain",
        ],
        "after_insert": [
            "bsgroup.utils.hd_ticket.thread_email_to_existing_ticket",
        ],
        "on_update": [
            "bsgroup.utils.hd_ticket.sync_tts_status",
            "bsgroup.utils.hd_ticket.sync_zztest_scheduler_status",
        ],
    },
    "Quotation": {
        "validate": "bsgroup.utils.quotation.validate_pipeline_stage",
        "on_update": "bsgroup.utils.quotation.sync_pipeline_result",
        "before_update_after_submit": "bsgroup.utils.quotation.validate_pipeline_stage",
        "on_update_after_submit": "bsgroup.utils.quotation.sync_pipeline_result",
    },
    "Opportunity": {
        "before_insert": [
            "bsgroup.utils.opportunity.set_opportunity_owner",
        ],
        "before_save": [
            "bsgroup.utils.opportunity.set_stage_history",
            "bsgroup.utils.opportunity.set_stage_updates",
            "bsgroup.utils.opportunity.set_last_updates",
        ],
        "autoname": "bsgroup.utils.doctype_naming.opportunity_autoname",
    },
    "Communication": {
        "before_insert": "bsgroup.utils.communication.hd_partner_email_threading"
    },
    "Project": {
        "before_insert": "bsgroup.utils.project.validate_mandatory_fields",
        "before_save": "bsgroup.utils.project.validate_project_completion",
        "on_update": [
            "bsgroup.utils.project.close_labor_preapprovals_on_completion",
            "bsgroup.utils.project_cost_baseline.check_project_cost_overrun",
        ],
    },
    "Purchase Order": {
        "validate": "bsgroup.utils.project_cost_baseline.check_transaction_cost_overrun",
        "on_cancel": "bsgroup.utils.project_cost_baseline.recalculate_project_baseline",
        "on_trash": "bsgroup.utils.project_cost_baseline.recalculate_project_baseline",
    },
    "Purchase Invoice": {
        "validate": "bsgroup.utils.project_cost_baseline.check_transaction_cost_overrun",
        "on_cancel": "bsgroup.utils.project_cost_baseline.recalculate_project_baseline",
        "on_trash": "bsgroup.utils.project_cost_baseline.recalculate_project_baseline",
    },
    "Expense Claim": {
        "validate": "bsgroup.utils.project_cost_baseline.check_transaction_cost_overrun",
        "on_cancel": "bsgroup.utils.project_cost_baseline.recalculate_project_baseline",
        "on_trash": "bsgroup.utils.project_cost_baseline.recalculate_project_baseline",
    },
    "Labor Attendance": {
        "on_submit": "bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval.sync_completion_status_from_attendance",
        "on_cancel": "bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval.sync_completion_status_from_attendance",
    },
    "Labor Preapproval": {
        "validate": "bsgroup.utils.project_cost_baseline.check_labor_preapproval_cost_overrun",
        "on_cancel": "bsgroup.utils.project_cost_baseline.recalculate_labor_preapproval_baseline",
        "on_trash": "bsgroup.utils.project_cost_baseline.recalculate_labor_preapproval_baseline",
    },
}

override_whitelisted_methods = {
	"erpnext.crm.doctype.opportunity.opportunity.make_quotation": "bsgroup.utils.quotation.make_quotation",
	# "frappe.utils.print_format.report_to_pdf": "bsgroup.utils.pdf.report_to_pdf",
	# "frappe.utils.print_format.download_pdf": "bsgroup.utils.pdf.download_pdf",
}

extend_doctype_class = {
    "Holiday List": [
        "bsgroup.utils.api.HolidayListEnglishDescriptionMixin"
    ]
}

scheduler_events = {
    "hourly": [
        "bsgroup.utils.tech_task_scheduler_overdue.mark_overdue_scheduler_rows",
    ],
    "daily": [
        "bsgroup.utils.opportunity.update_overdue_followup_for_all",
        "bsgroup.bs_group.doctype.presales_request.presales_request.calculate_due_date",
        "bsgroup.utils.visa.update_employee_visa_status",
        "bsgroup.utils.quotation.sync_expired_pipeline_stage",
    ]
}


before_request = ["bsgroup.utils.email_threading.apply_patches"]

fixtures = [
    {
        "doctype": "Property Setter",
        "filters": [["module", "=", "BS Group"]]
    },
    # {"doctype": "Workflow"},
    # {"doctype": "Workflow Action Master"},
    # {"doctype": "Workflow State"},
    # {"doctype": "Role"},
]
