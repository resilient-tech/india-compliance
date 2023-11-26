import click

import frappe
from frappe.utils import get_datetime, random_string

from india_compliance.gst_india.overrides.transaction import get_valid_accounts
from india_compliance.gst_india.utils import get_all_gst_accounts
from india_compliance.patches.post_install.update_e_invoice_fields_and_logs import (
    delete_custom_fields,
)

TRANSACTION_DOCTYPES = (
    "Material Request Item",
    "Supplier Quotation Item",
    "Purchase Order Item",
    "Purchase Receipt Item",
    "Purchase Invoice Item",
    "Quotation Item",
    "Sales Order Item",
    "Delivery Note Item",
    "Sales Invoice Item",
    "POS Invoice Item",
)

FIELDS_TO_DELETE = {
    "Item": [
        {
            "fieldname": "is_nil_exempt",
        },
        {
            "fieldname": "is_non_gst",
        },
    ],
    TRANSACTION_DOCTYPES: [{"fieldname": "is_nil_exempt"}],
}
NEW_TEMPLATES = {
    "is_nil_rated": "Is Nil Rated",
    "is_exempted": "Is exempted",
    "is_non_gst": "Is Non GST",
}


def execute():
    update_transactions()
    templates = update_item_tax_template()
    update_items(templates)

    delete_custom_fields(FIELDS_TO_DELETE)


def update_transactions():
    "Disclaimer: No specific way to differentate between nil and exempted. Hence all transactions are updated to nil"

    show_disclaimer = False
    for doctype in TRANSACTION_DOCTYPES:
        if not frappe.db.get_value(doctype, {"is_nil_exempt": 1}):
            continue

        table = frappe.qb.DocType(doctype)
        frappe.qb.update(table).set(table.is_nil_rated, table.is_nil_exempt).run()
        show_disclaimer = True

    if show_disclaimer:
        click.secho(
            "Nil Rated items are differentiated from Exempted for GST (configrable from Item Tax Template).",
            color="yellow",
        )
        click.secho(
            "All transactions that were marked as Nil or Exempt, are now marked as Nil Rated.",
            color="red",
        )


def update_item_tax_template():
    DOCTYPE = "Item Tax Template"
    item_templates = frappe.get_all(DOCTYPE, pluck="name")
    companies_with_templates = set()

    # update tax rates
    for template in item_templates:
        doc = frappe.get_doc(DOCTYPE, template)
        gst_accounts = get_all_gst_accounts(doc.company)
        if doc.taxes[0].tax_type not in gst_accounts:
            continue

        tax_rate = set()
        companies_with_templates.add(doc.company)
        valid_accounts = get_valid_accounts(doc.company, True, True)

        for row in doc.taxes:
            if row.tax_type in valid_accounts[1]:
                tax_rate.add(row.tax_rate * 2)
            elif row.tax_type in valid_accounts[2]:
                tax_rate.add(row.tax_rate)

        if len(tax_rate) != 1:
            continue

        doc.tax_rate = list(tax_rate)[0]
        doc.save()

    # create new templates for nil rated, exempted, non gst
    templates = {}
    for company in companies_with_templates:
        for template, label in NEW_TEMPLATES.items():
            if frappe.db.get_value(DOCTYPE, {"company": company, template: 1}):
                continue

            doc = frappe.get_doc(
                {
                    "doctype": DOCTYPE,
                    "title": label,
                    "company": company,
                    "tax_rate": 0,
                    template: 1,
                }
            )
            for account in gst_accounts:
                doc.append("taxes", {"tax_type": account, "tax_rate": 0})

            doc.insert()
            templates.setdefault(template, []).append(doc.name)

    return templates


def update_items(templates):
    "Disclaimer: No specific way to differentate between nil and exempted. Hence all transactions are updated to nil"

    if not templates:
        return

    table = frappe.qb.DocType("Item")
    item_list = (
        frappe.qb.from_(table)
        .select("name", "is_nil_exempt", "is_non_gst")
        .where((table.is_nil_exempt == 1) | (table.is_non_gst == 1))
        .run(as_dict=True)
    )

    # Make sure this is run only once
    frappe.qb.update(table).set(table.is_nil_exempt, 0).set(table.is_non_gst, 0).run()

    fields = (
        "name",
        "parent",
        "parentfield",
        "parenttype",
        "item_tax_template",
        "owner",
        "modified_by",
        "creation",
        "modified",
    )

    def append_tax_template(template):
        values.append(
            [
                random_string(10),
                item.name,
                "taxes",
                "Item",
                template,
                "Administrator",
                "Administrator",
                time,
                time,
            ]
        )

    values = []
    time = get_datetime()
    for item in item_list:
        if item.is_nil_exempt:
            for template in templates["is_nil_rated"]:
                append_tax_template(template)

            for template in templates["is_exempted"]:
                append_tax_template(template)

        if item.is_non_gst:
            for template in templates["is_non_gst"]:
                append_tax_template(template)

    frappe.db.bulk_insert("Item Tax", fields=fields, values=values)
