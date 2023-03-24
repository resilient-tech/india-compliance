from . import __version__ as app_version

app_name = "india_compliance"
app_title = "India Compliance"
app_publisher = "Resilient Tech"
app_description = "ERPNext app to simplify compliance with Indian Rules and Regulations"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "hello@indiacompliance.app"
app_license = "GNU General Public License (v3)"
required_apps = ["frappe/erpnext"]

after_install = "india_compliance.install.after_install"
before_tests = "india_compliance.tests.before_tests"
boot_session = "india_compliance.boot.set_bootinfo"

before_uninstall = "india_compliance.uninstall.before_uninstall"

app_include_js = "gst_india.bundle.js"

doctype_js = {
    "Address": "gst_india/client_scripts/address.js",
    "Company": "gst_india/client_scripts/company.js",
    "Customer": "gst_india/client_scripts/customer.js",
    "Delivery Note": [
        "gst_india/client_scripts/e_waybill_actions.js",
        "gst_india/client_scripts/delivery_note.js",
    ],
    "Item": "gst_india/client_scripts/item.js",
    "Journal Entry": "gst_india/client_scripts/journal_entry.js",
    "Payment Entry": "gst_india/client_scripts/payment_entry.js",
    "Purchase Invoice": "gst_india/client_scripts/purchase_invoice.js",
    "Sales Invoice": [
        "gst_india/client_scripts/e_invoice_actions.js",
        "gst_india/client_scripts/e_waybill_actions.js",
        "gst_india/client_scripts/sales_invoice.js",
    ],
    "Supplier": "gst_india/client_scripts/supplier.js",
}

doctype_list_js = {
    "Sales Invoice": [
        "gst_india/client_scripts/e_waybill_actions.js",
        "gst_india/client_scripts/sales_invoice_list.js",
    ]
}

doc_events = {
    "Address": {
        "validate": [
            "india_compliance.gst_india.overrides.address.validate",
            "india_compliance.gst_india.overrides.party.set_docs_with_previous_gstin",
        ],
    },
    "Company": {
        "on_trash": "india_compliance.gst_india.overrides.company.delete_gst_settings_for_company",
        "on_update": [
            "india_compliance.income_tax_india.overrides.company.make_company_fixtures",
            "india_compliance.gst_india.overrides.company.make_company_fixtures",
        ],
        "validate": "india_compliance.gst_india.overrides.party.validate_party",
    },
    "Customer": {
        "validate": "india_compliance.gst_india.overrides.party.validate_party",
        "after_insert": (
            "india_compliance.gst_india.overrides.party.create_primary_address"
        ),
    },
    "Delivery Note": {
        "on_trash": (
            "india_compliance.gst_india.overrides.transaction.ignore_logs_on_trash"
        ),
        "onload": "india_compliance.gst_india.overrides.delivery_note.onload",
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
    },
    "Item": {"validate": "india_compliance.gst_india.overrides.item.validate_hsn_code"},
    "Payment Entry": {
        "validate": (
            "india_compliance.gst_india.overrides.payment_entry.update_place_of_supply"
        )
    },
    "Purchase Invoice": {
        "onload": "india_compliance.gst_india.overrides.purchase_invoice.onload",
        "validate": "india_compliance.gst_india.overrides.purchase_invoice.validate",
    },
    "Purchase Order": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
    },
    "Purchase Receipt": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
    },
    "Sales Invoice": {
        "on_trash": (
            "india_compliance.gst_india.overrides.transaction.ignore_logs_on_trash"
        ),
        "onload": "india_compliance.gst_india.overrides.sales_invoice.onload",
        "validate": "india_compliance.gst_india.overrides.sales_invoice.validate",
        "on_submit": "india_compliance.gst_india.overrides.sales_invoice.on_submit",
    },
    "Sales Order": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
    },
    "Supplier": {
        "validate": [
            "india_compliance.gst_india.overrides.supplier.update_transporter_gstin",
            "india_compliance.gst_india.overrides.party.validate_party",
        ],
        "after_insert": (
            "india_compliance.gst_india.overrides.party.create_primary_address"
        ),
    },
    "Tax Category": {
        "validate": "india_compliance.gst_india.overrides.tax_category.validate"
    },
    "POS Invoice": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
    },
    "Quotation": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
    },
}


regional_overrides = {
    "India": {
        "erpnext.controllers.taxes_and_totals.get_itemised_tax_breakup_header": "india_compliance.gst_india.overrides.transaction.get_itemised_tax_breakup_header",
        "erpnext.controllers.taxes_and_totals.get_itemised_tax_breakup_data": (
            "india_compliance.gst_india.utils.get_itemised_tax_breakup_data"
        ),
        "erpnext.controllers.taxes_and_totals.get_regional_round_off_accounts": "india_compliance.gst_india.overrides.transaction.get_regional_round_off_accounts",
        "erpnext.accounts.party.get_regional_address_details": (
            "india_compliance.gst_india.overrides.transaction.update_party_details"
        ),
        "erpnext.stock.doctype.item.item.set_item_tax_from_hsn_code": "india_compliance.gst_india.overrides.transaction.set_item_tax_from_hsn_code",
        "erpnext.assets.doctype.asset.asset.get_depreciation_amount": (
            "india_compliance.income_tax_india.overrides.asset.get_depreciation_amount"
        ),
    }
}

jinja = {
    "methods": [
        "india_compliance.gst_india.utils.get_state",
        "india_compliance.gst_india.utils.jinja.add_spacing",
        "india_compliance.gst_india.utils.jinja.get_supply_type",
        "india_compliance.gst_india.utils.jinja.get_sub_supply_type",
        "india_compliance.gst_india.utils.jinja.get_e_waybill_qr_code",
        "india_compliance.gst_india.utils.jinja.get_qr_code",
        "india_compliance.gst_india.utils.jinja.get_transport_type",
        "india_compliance.gst_india.utils.jinja.get_transport_mode",
        "india_compliance.gst_india.utils.jinja.get_ewaybill_barcode",
        "india_compliance.gst_india.utils.jinja.get_e_invoice_item_fields",
        "india_compliance.gst_india.utils.jinja.get_e_invoice_amount_fields",
    ],
}

override_doctype_dashboards = {
    "Sales Invoice": (
        "india_compliance.gst_india.overrides.sales_invoice.get_dashboard_data"
    ),
    "Delivery Note": (
        "india_compliance.gst_india.overrides.delivery_note.get_dashboard_data"
    ),
}


# DocTypes to be ignored while clearing transactions of a Company
company_data_to_be_ignored = ["GST Account", "GST Credential"]

# Links to these doctypes will be ignored when deleting a document
ignore_links_on_delete = ["e-Waybill Log", "e-Invoice Log"]

accounting_dimension_doctypes = ["Bill of Entry", "Bill of Entry Item"]


# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/india_compliance/css/india_compliance.css"

# include js, css files in header of web template
# web_include_css = "/assets/india_compliance/css/india_compliance.css"
# web_include_js = "/assets/india_compliance/js/india_compliance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "india_compliance/public/scss/website"

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

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "india_compliance.utils.jinja_methods",
# 	"filters": "india_compliance.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "india_compliance.install.before_install"

# Uninstallation
# ------------

# before_uninstall = "india_compliance.uninstall.before_uninstall"
# after_uninstall = "india_compliance.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "india_compliance.notifications.get_notification_config"

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

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
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
# 		"india_compliance.tasks.all"
# 	],
# 	"daily": [
# 		"india_compliance.tasks.daily"
# 	],
# 	"hourly": [
# 		"india_compliance.tasks.hourly"
# 	],
# 	"weekly": [
# 		"india_compliance.tasks.weekly"
# 	],
# 	"monthly": [
# 		"india_compliance.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "india_compliance.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "india_compliance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "india_compliance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


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
# 	"india_compliance.auth.validate"
# ]
