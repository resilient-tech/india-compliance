app_name = "india_compliance"
app_title = "India Compliance"
app_publisher = "Resilient Tech"
app_description = "ERPNext app to simplify compliance with Indian Rules and Regulations"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "hello@indiacompliance.app"
app_license = "GNU General Public License (v3)"
required_apps = ["frappe/erpnext"]

before_install = "india_compliance.patches.check_version_compatibility.execute"
after_install = "india_compliance.install.after_install"
before_uninstall = "india_compliance.uninstall.before_uninstall"

after_app_install = "india_compliance.install.after_app_install"
before_app_uninstall = "india_compliance.uninstall.before_app_uninstall"

before_migrate = "india_compliance.patches.check_version_compatibility.execute"
after_migrate = "india_compliance.audit_trail.setup.after_migrate"

before_tests = "india_compliance.tests.before_tests"

boot_session = "india_compliance.boot.set_bootinfo"

setup_wizard_requires = "assets/india_compliance/js/setup_wizard.js"
setup_wizard_complete = "india_compliance.gst_india.setup.setup_wizard_complete"
setup_wizard_stages = "india_compliance.setup_wizard.get_setup_wizard_stages"

app_include_js = "india_compliance.bundle.js"

doctype_js = {
    "Address": "gst_india/client_scripts/address.js",
    "Company": "gst_india/client_scripts/company.js",
    "Customer": "gst_india/client_scripts/customer.js",
    "Delivery Note": [
        "gst_india/client_scripts/e_waybill_actions.js",
        "gst_india/client_scripts/delivery_note.js",
    ],
    "Item": "gst_india/client_scripts/item.js",
    "Item Tax Template": "gst_india/client_scripts/item_tax_template.js",
    "Expense Claim": [
        "gst_india/client_scripts/journal_entry.js",
        "gst_india/client_scripts/expense_claim.js",
    ],
    "Journal Entry": "gst_india/client_scripts/journal_entry.js",
    "Payment Entry": "gst_india/client_scripts/payment_entry.js",
    "Purchase Invoice": [
        "gst_india/client_scripts/e_waybill_actions.js",
        "gst_india/client_scripts/purchase_invoice.js",
    ],
    "Purchase Receipt": [
        "gst_india/client_scripts/e_waybill_actions.js",
        "gst_india/client_scripts/purchase_receipt.js",
    ],
    "Sales Invoice": [
        "gst_india/client_scripts/e_invoice_actions.js",
        "gst_india/client_scripts/e_waybill_actions.js",
        "gst_india/client_scripts/sales_invoice.js",
    ],
    "Supplier": "gst_india/client_scripts/supplier.js",
    "Accounts Settings": "audit_trail/client_scripts/accounts_settings.js",
    "Customize Form": "audit_trail/client_scripts/customize_form.js",
    "Document Naming Settings": "gst_india/client_scripts/document_naming_settings.js",
    "Document Naming Rule": "gst_india/client_scripts/document_naming_rule.js",
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
        "onload": "india_compliance.gst_india.overrides.delivery_note.onload",
        "before_save": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "before_submit": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
    },
    "Email Template": {
        "after_rename": "india_compliance.gst_india.overrides.email_template.after_rename",
        "on_trash": "india_compliance.gst_india.overrides.email_template.on_trash",
    },
    "GL Entry": {
        "validate": "india_compliance.gst_india.overrides.gl_entry.validate",
    },
    "Item": {"validate": "india_compliance.gst_india.overrides.item.validate"},
    "Item Tax Template": {
        "validate": "india_compliance.gst_india.overrides.item_tax_template.validate"
    },
    "Journal Entry": {
        "validate": "india_compliance.gst_india.overrides.journal_entry.validate",
    },
    "Payment Entry": {
        "onload": "india_compliance.gst_india.overrides.payment_entry.onload",
        "validate": "india_compliance.gst_india.overrides.payment_entry.validate",
        "on_submit": "india_compliance.gst_india.overrides.payment_entry.on_submit",
        "on_update_after_submit": "india_compliance.gst_india.overrides.payment_entry.on_update_after_submit",
    },
    "Purchase Invoice": {
        "onload": "india_compliance.gst_india.overrides.purchase_invoice.onload",
        "validate": "india_compliance.gst_india.overrides.purchase_invoice.validate",
        "before_validate": (
            "india_compliance.gst_india.overrides.transaction.before_validate"
        ),
        "before_save": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "before_submit": [
            "india_compliance.gst_india.overrides.transaction.update_gst_details",
            "india_compliance.gst_india.overrides.ineligible_itc.update_valuation_rate",
        ],
        "before_gl_preview": "india_compliance.gst_india.overrides.ineligible_itc.update_valuation_rate",
        "before_sl_preview": "india_compliance.gst_india.overrides.ineligible_itc.update_valuation_rate",
        "after_mapping": "india_compliance.gst_india.overrides.transaction.after_mapping",
    },
    "Purchase Order": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
        "before_validate": (
            "india_compliance.gst_india.overrides.transaction.before_validate"
        ),
        "before_save": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "before_submit": "india_compliance.gst_india.overrides.transaction.update_gst_details",
    },
    "Purchase Receipt": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
        "before_validate": (
            "india_compliance.gst_india.overrides.transaction.before_validate"
        ),
        "before_save": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "before_submit": [
            "india_compliance.gst_india.overrides.transaction.update_gst_details",
            "india_compliance.gst_india.overrides.ineligible_itc.update_valuation_rate",
        ],
        "before_gl_preview": "india_compliance.gst_india.overrides.ineligible_itc.update_valuation_rate",
        "before_sl_preview": "india_compliance.gst_india.overrides.ineligible_itc.update_valuation_rate",
    },
    "Sales Invoice": {
        "onload": "india_compliance.gst_india.overrides.sales_invoice.onload",
        "validate": "india_compliance.gst_india.overrides.sales_invoice.validate",
        "before_save": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "before_submit": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "on_submit": "india_compliance.gst_india.overrides.sales_invoice.on_submit",
        "on_update_after_submit": (
            "india_compliance.gst_india.overrides.sales_invoice.on_update_after_submit"
        ),
        "before_cancel": "india_compliance.gst_india.overrides.sales_invoice.before_cancel",
        "after_mapping": "india_compliance.gst_india.overrides.transaction.after_mapping",
    },
    "Sales Order": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
        "before_save": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "before_submit": "india_compliance.gst_india.overrides.transaction.update_gst_details",
    },
    "Supplier": {
        "validate": [
            "india_compliance.gst_india.overrides.supplier.validate",
            "india_compliance.gst_india.overrides.party.validate_party",
        ],
        "after_insert": (
            "india_compliance.gst_india.overrides.party.create_primary_address"
        ),
    },
    "Tax Category": {
        "validate": "india_compliance.gst_india.overrides.tax_category.validate"
    },
    "Tax Withholding Category": {
        "on_change": "india_compliance.income_tax_india.overrides.tax_withholding_category.on_change",
    },
    "Unreconcile Payment": {
        "before_submit": "india_compliance.gst_india.overrides.unreconcile_payment.before_submit",
    },
    "POS Invoice": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
        "before_save": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "before_submit": "india_compliance.gst_india.overrides.transaction.update_gst_details",
    },
    "Quotation": {
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
        "before_save": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "before_submit": "india_compliance.gst_india.overrides.transaction.update_gst_details",
    },
    "Supplier Quotation": {
        "before_validate": (
            "india_compliance.gst_india.overrides.transaction.before_validate"
        ),
        "validate": (
            "india_compliance.gst_india.overrides.transaction.validate_transaction"
        ),
        "before_save": "india_compliance.gst_india.overrides.transaction.update_gst_details",
        "before_submit": "india_compliance.gst_india.overrides.transaction.update_gst_details",
    },
    "Accounts Settings": {
        "validate": "india_compliance.audit_trail.overrides.accounts_settings.validate"
    },
    "Property Setter": {
        "validate": "india_compliance.audit_trail.overrides.property_setter.validate",
        "on_trash": "india_compliance.audit_trail.overrides.property_setter.on_trash",
    },
    "Version": {
        "validate": "india_compliance.audit_trail.overrides.version.validate",
        "on_trash": "india_compliance.audit_trail.overrides.version.on_trash",
    },
}


regional_overrides = {
    "India": {
        "erpnext.controllers.taxes_and_totals.get_itemised_tax_breakup_header": "india_compliance.gst_india.overrides.transaction.get_itemised_tax_breakup_header",
        "erpnext.controllers.taxes_and_totals.get_itemised_tax_breakup_data": "india_compliance.gst_india.overrides.transaction.get_itemised_tax_breakup_data",
        "erpnext.controllers.taxes_and_totals.get_regional_round_off_accounts": (
            "india_compliance.gst_india.overrides.transaction.get_regional_round_off_accounts"
        ),
        "erpnext.controllers.accounts_controller.update_gl_dict_with_regional_fields": (
            "india_compliance.gst_india.overrides.gl_entry.update_gl_dict_with_regional_fields"
        ),
        "erpnext.controllers.accounts_controller.get_advance_payment_entries_for_regional": (
            "india_compliance.gst_india.overrides.payment_entry.get_advance_payment_entries_for_regional"
        ),
        "erpnext.accounts.doctype.payment_reconciliation.payment_reconciliation.adjust_allocations_for_taxes": (
            "india_compliance.gst_india.overrides.payment_entry.adjust_allocations_for_taxes_in_payment_reconciliation"
        ),
        "erpnext.accounts.doctype.purchase_invoice.purchase_invoice.make_regional_gl_entries": (
            "india_compliance.gst_india.overrides.ineligible_itc.update_regional_gl_entries"
        ),
        "erpnext.stock.doctype.purchase_receipt.purchase_receipt.update_regional_gl_entries": (
            "india_compliance.gst_india.overrides.ineligible_itc.update_regional_gl_entries"
        ),
        "erpnext.accounts.doctype.payment_entry.payment_entry.add_regional_gl_entries": (
            "india_compliance.gst_india.overrides.payment_entry.update_gl_for_advance_gst_reversal"
        ),
        "erpnext.accounts.party.get_regional_address_details": (
            "india_compliance.gst_india.overrides.transaction.update_party_details"
        ),
        "erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule.get_wdv_or_dd_depr_amount": (
            "india_compliance.income_tax_india.overrides.asset_depreciation_schedule.get_wdv_or_dd_depr_amount"
        ),
        "erpnext.assets.doctype.asset.depreciation.cancel_depreciation_entries": (
            "india_compliance.income_tax_india.overrides.asset_depreciation_schedule.cancel_depreciation_entries"
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
    "Purchase Invoice": (
        "india_compliance.gst_india.overrides.purchase_invoice.get_dashboard_data"
    ),
    "Purchase Receipt": (
        "india_compliance.gst_india.overrides.purchase_receipt.get_dashboard_data"
    ),
}

override_doctype_class = {
    "Customize Form": (
        "india_compliance.audit_trail.overrides.customize_form.CustomizeForm"
    ),
}


# DocTypes to be ignored while clearing transactions of a Company
company_data_to_be_ignored = ["GST Account", "GST Credential"]

# Links to these doctypes will be ignored when deleting a document
ignore_links_on_delete = ["e-Waybill Log", "e-Invoice Log"]

accounting_dimension_doctypes = ["Bill of Entry", "Bill of Entry Item"]

# DocTypes for which Audit Trail must be maintained
audit_trail_doctypes = [
    # To track the "Enable Audit Trail" setting
    "Accounts Settings",
    # ERPNext DocTypes that make GL Entries
    "Dunning",
    "Invoice Discounting",
    "Journal Entry",
    "Payment Entry",
    "Period Closing Voucher",
    "Process Deferred Accounting",
    "Purchase Invoice",
    "Sales Invoice",
    "Asset",
    "Asset Capitalization",
    "Asset Repair",
    "Delivery Note",
    "Landed Cost Voucher",
    "Purchase Receipt",
    "Stock Entry",
    "Stock Reconciliation",
    "Subcontracting Receipt",
    # Additional ERPNext DocTypes that constitute "Books of Account"
    "POS Invoice",
    # India Compliance DocTypes that make GL Entries
    "Bill of Entry",
]

scheduler_events = {
    "cron": {
        "*/5 * * * *": [
            "india_compliance.gst_india.utils.e_invoice.retry_e_invoice_e_waybill_generation",
            "india_compliance.gst_india.utils.gstr.download_queued_request",
        ],
        "0 1 * * *": [
            "india_compliance.gst_india.utils.e_waybill.extend_scheduled_e_waybills"
        ],
    }
}


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
override_whitelisted_methods = {
    "erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_reference_documents": (
        "india_compliance.gst_india.overrides.payment_entry.get_outstanding_reference_documents"
    )
}
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
