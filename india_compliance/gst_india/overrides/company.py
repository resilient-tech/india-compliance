import frappe
from frappe.utils import flt
from erpnext.setup.setup_wizard.operations.taxes_setup import from_detailed_data

from india_compliance.gst_india.utils import get_data_file_path


def delete_gst_settings_for_company(doc, method=None):
    if doc.country != "India":
        return

    gst_settings = frappe.get_doc("GST Settings")

    gst_settings.gst_accounts = [
        row for row in gst_settings.get("gst_accounts", []) if row.company != doc.name
    ]

    gst_settings.flags.ignore_mandatory = True
    gst_settings.save()


def make_company_fixtures(doc, method=None):
    if not frappe.flags.country_change or doc.country != "India":
        return

    create_company_fixtures(doc.name, doc.default_gst_rate)


def create_company_fixtures(company, gst_rate=None):
    if not frappe.flags.in_setup_wizard:
        # Manual Trigger in Setup Wizard with custom rate
        make_default_tax_templates(company, gst_rate)

    make_default_customs_accounts(company)
    make_default_gst_expense_accounts(company)


def make_default_customs_accounts(company):
    create_default_company_account(
        company,
        account_name="Customs Duty Payable",
        parent="Duties and Taxes",
        default_fieldname="default_customs_payable_account",
    )

    create_default_company_account(
        company,
        account_name="Customs Duty Expense",
        parent="Stock Expenses",
        default_fieldname="default_customs_expense_account",
    )


def make_default_gst_expense_accounts(company):
    create_default_company_account(
        company,
        account_name="GST Expense",
        parent="Indirect Expenses",
        default_fieldname="default_gst_expense_account",
    )


@frappe.whitelist()
def make_default_tax_templates(company: str, gst_rate=None):
    frappe.has_permission("Company", ptype="write", doc=company, throw=True)

    default_taxes = get_tax_defaults(gst_rate)
    from_detailed_data(company, default_taxes)
    update_gst_settings(company)


def get_tax_defaults(gst_rate=None):
    if not gst_rate:
        gst_rate = 18

    default_taxes = frappe.get_file_json(get_data_file_path("tax_defaults.json"))

    gst_rate = flt(gst_rate, 3)
    if gst_rate == 18:
        return default_taxes

    return modify_tax_defaults(default_taxes, gst_rate)


def modify_tax_defaults(default_taxes, gst_rate):
    # Identifying new_rate based on existing rate
    for template_type in ("sales_tax_templates", "purchase_tax_templates"):
        template = default_taxes["chart_of_accounts"]["*"][template_type]
        for tax in template:
            for row in tax.get("taxes"):
                rate = (
                    gst_rate
                    if row["account_head"]["tax_rate"] == 18
                    else flt(gst_rate / 2, 3)
                )

                row["account_head"]["tax_rate"] = rate

    return default_taxes


def update_gst_settings(company):
    # Will only add default GST accounts if present
    input_account_names = ["Input Tax CGST", "Input Tax SGST", "Input Tax IGST"]
    output_account_names = ["Output Tax CGST", "Output Tax SGST", "Output Tax IGST"]
    rcm_accounts = ["Input Tax CGST RCM", "Input Tax SGST RCM", "Input Tax IGST RCM"]
    gst_settings = frappe.get_single("GST Settings")
    existing_account_list = []

    for account in gst_settings.get("gst_accounts"):
        for key in ["cgst_account", "sgst_account", "igst_account"]:
            existing_account_list.append(account.get(key))

    gst_accounts = frappe._dict(
        frappe.get_all(
            "Account",
            {
                "company": company,
                "account_name": (
                    "in",
                    input_account_names + output_account_names + rcm_accounts,
                ),
            },
            ["account_name", "name"],
            as_list=1,
        )
    )

    add_accounts_in_gst_settings(
        company,
        input_account_names,
        gst_accounts,
        existing_account_list,
        gst_settings,
        "Input",
    )
    add_accounts_in_gst_settings(
        company,
        output_account_names,
        gst_accounts,
        existing_account_list,
        gst_settings,
        "Output",
    )
    add_accounts_in_gst_settings(
        company,
        rcm_accounts,
        gst_accounts,
        existing_account_list,
        gst_settings,
        "Reverse Charge",
    )

    # Ignore mandatory during install, some values may not be set by post install patch
    if frappe.flags.in_install:
        gst_settings.flags.ignore_mandatory = True

    gst_settings.save()


def add_accounts_in_gst_settings(
    company,
    account_names,
    gst_accounts,
    existing_account_list,
    gst_settings,
    account_type,
):
    accounts_not_added = 1
    for account in account_names:
        # Default Account Added does not exist
        if not gst_accounts.get(account):
            accounts_not_added = 0

        # Check if already added in GST Settings
        if gst_accounts.get(account) in existing_account_list:
            accounts_not_added = 0

    if accounts_not_added:
        gst_settings.append(
            "gst_accounts",
            {
                "company": company,
                "cgst_account": gst_accounts.get(account_names[0]),
                "sgst_account": gst_accounts.get(account_names[1]),
                "igst_account": gst_accounts.get(account_names[2]),
                "account_type": account_type,
            },
        )


def create_default_company_account(
    company,
    account_name,
    parent,
    default_fieldname=None,
):
    """
    Creats a default company account if missing
    Updates the company with the default account name
    """
    parent_account = frappe.db.get_value(
        "Account",
        filters={"account_name": parent, "company": company, "is_group": 1},
    )

    if not parent_account:
        return

    account = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": account_name,
            "parent_account": parent_account,
            "company": company,
            "is_group": 0,
            "account_type": "Tax",
        }
    )
    account.flags.ignore_permissions = True
    account.insert(ignore_if_duplicate=True)

    if default_fieldname and not frappe.db.get_value(
        "Company", company, default_fieldname
    ):
        frappe.db.set_value(
            "Company", company, default_fieldname, account.name, update_modified=False
        )
