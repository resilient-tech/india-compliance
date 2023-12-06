import click

import frappe
from frappe.query_builder import Case
from frappe.utils import get_datetime, random_string

from india_compliance.gst_india.constants import GST_TAX_TYPES, SALES_DOCTYPES
from india_compliance.gst_india.overrides.transaction import (
    ItemGSTDetails,
    get_valid_accounts,
)
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_accounts_by_type,
)
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
        {"fieldname": "is_nil_exempt"},
        {"fieldname": "is_non_gst"},
    ],
    TRANSACTION_DOCTYPES: [
        {"fieldname": "is_nil_exempt"},
        {"fieldname": "is_non_gst"},
    ],
}

NEW_TEMPLATES = {
    "is_nil_rated": "Nil-Rated",
    "is_exempted": "Exempted",
    "is_non_gst": "Non-GST",
}

UPDATE_FOR_MONTHS = 3


def execute():
    companies = get_indian_registered_companies()
    templates = update_item_tax_template(companies)
    update_items(templates)

    update_transactions()
    update_transaction_gst_details(companies)

    update_item_variant_settings()
    delete_custom_fields(FIELDS_TO_DELETE)


def get_indian_registered_companies():
    return frappe.get_all(
        "Company",
        filters={
            "country": "India",
            "gst_category": ["!=", "Unregistered"],
            "gstin": ["is", "set"],
        },
        pluck="name",
    )


def update_transaction_gst_details(companies):
    for company in companies:
        gst_accounts = []
        for account_type in ["Input", "Output"]:
            gst_accounts.extend(
                get_gst_accounts_by_type(company, account_type).values()
            )

        for doctype in ("Sales Invoice", "Purchase Invoice"):
            is_sales_doctype = doctype in SALES_DOCTYPES
            docs = get_docs_with_gst_accounts(doctype, gst_accounts)
            if not docs:
                continue

            chunk_size = 5000
            total_docs = len(docs)

            for i in range(0, total_docs, chunk_size):
                chunk = docs[i : i + chunk_size]
                taxes = get_taxes_for_docs(chunk, doctype, is_sales_doctype)
                items = get_items_for_docs(chunk, doctype)
                complied_docs = compile_docs(taxes, items)

                if not complied_docs:
                    continue

                gst_details = ItemGSTDetails().get(
                    complied_docs.values(), doctype, company
                )

                update_gst_details(gst_details, doctype)


def update_gst_details(gst_details, doctype):
    item_doctype = f"{doctype} Item"
    item = frappe.qb.DocType(item_doctype)

    update_query = frappe.qb.update(item)
    items = set()

    # Initialize case queries
    conditions = frappe._dict()
    for tax in GST_TAX_TYPES:
        for field in (f"{tax}_rate", f"{tax}_amount"):
            conditions.setdefault(field, Case())

    # Update item conditions
    first_row = True
    for item_name, row in gst_details.items():
        items.add(item_name)
        for q in conditions:
            if not row[q] and not first_row:
                continue

            conditions[q] = conditions[q].when(item.name == item_name, row[q])

        first_row = False

    # Update queries
    for q in conditions:
        conditions[q] = conditions[q].else_(item[q])
        update_query = update_query.set(item[q], conditions[q])

    update_query = update_query.where(item.name.isin(items)).run()


def get_taxes_for_docs(docs, doctype, is_sales_doctype):
    taxes_doctype = (
        "Sales Taxes and Charges" if is_sales_doctype else "Purchase Taxes and Charges"
    )
    taxes = frappe.qb.DocType(taxes_doctype)
    return (
        frappe.qb.from_(taxes)
        .select(
            taxes.tax_amount,
            taxes.account_head,
            taxes.parent,
            taxes.item_wise_tax_detail,
        )
        .where(taxes.parenttype == doctype)
        .where(taxes.parent.isin(docs))
        .run(as_dict=True)
    )


def get_items_for_docs(docs, doctype):
    item_doctype = f"{doctype} Item"
    item = frappe.qb.DocType(item_doctype)
    return (
        frappe.qb.from_(item)
        .select(
            item.name,
            item.parent,
            item.item_code,
            item.item_name,
            item.qty,
            item.taxable_value,
        )
        .where(item.parenttype == doctype)
        .where(item.parent.isin(docs))
        .run(as_dict=True)
    )


def compile_docs(taxes, items):
    response = frappe._dict()

    for tax in taxes:
        doc = response.setdefault(tax.parent, frappe._dict({"taxes": [], "items": []}))
        doc.get("taxes").append(tax)

    for item in items:
        doc = response.setdefault(item.parent, frappe._dict({"taxes": [], "items": []}))
        doc.get("items").append(item)

    return response


def get_docs_with_gst_accounts(doctype, gst_accounts):
    gl_entry = frappe.qb.DocType("GL Entry")

    return (
        frappe.qb.from_(gl_entry)
        .select("voucher_no")
        .where(gl_entry.voucher_type == doctype)
        .where(gl_entry.account.isin(gst_accounts))
        .where(gl_entry.is_cancelled == 0)
        .groupby("voucher_no")
        .run(pluck=True)
    )


def update_transactions():
    "Disclaimer: No specific way to differentate between nil and exempted. Hence all transactions are updated to nil"

    show_disclaimer = False
    for doctype in TRANSACTION_DOCTYPES:
        # GST Treatment is not required in Material Request Item
        if doctype == "Material Request Item":
            continue

        table = frappe.qb.DocType(doctype)
        query = frappe.qb.update(table)

        if frappe.db.get_value(doctype, {"is_nil_exempt": 1}):
            show_disclaimer = True
            (
                query.set(table.gst_treatment, "Nil-Rated")
                .where(table.is_nil_exempt == 1)
                .run()
            )

        if frappe.db.get_value(doctype, {"is_non_gst": 1}):
            (
                query.set(table.gst_treatment, "Non-GST")
                .where(table.is_non_gst == 1)
                .run()
            )

    if show_disclaimer:
        click.secho(
            "Nil Rated items are differentiated from Exempted for GST (configrable from Item Tax Template).",
            color="yellow",
        )
        click.secho(
            "All transactions that were marked as Nil or Exempt, are now marked as Nil Rated.",
            color="red",
        )


def update_item_tax_template(companies):
    DOCTYPE = "Item Tax Template"
    item_templates = frappe.get_all(DOCTYPE, pluck="name")
    companies_with_templates = set()
    companies_gst_accounts = frappe._dict()

    # update tax rates
    for gst_treatment in item_templates:
        doc = frappe.get_doc(DOCTYPE, gst_treatment)
        if doc.company not in companies:
            continue

        gst_accounts = get_all_gst_accounts(doc.company)
        if not gst_accounts or not doc.taxes:
            continue

        gst_rate = set()
        companies_with_templates.add(doc.company)
        companies_gst_accounts[doc.company] = gst_accounts
        valid_accounts = get_valid_accounts(doc.company, True, True)

        for row in doc.taxes:
            if row.tax_type in valid_accounts[1]:
                gst_rate.add(row.tax_rate * 2)
            elif row.tax_type in valid_accounts[2]:
                gst_rate.add(row.tax_rate)

        if len(gst_rate) != 1:
            continue

        doc.gst_rate = list(gst_rate)[0]

        if doc.gst_rate > 0:
            doc.gst_treatment = "Taxable"

        elif doc.gst_rate == 0:
            doc.gst_treatment = "Nil-Rated"

        doc.save()

    # create new templates for nil rated, exempted, non gst
    templates = {}
    for company in companies_with_templates:
        gst_accounts = [
            {"tax_type": account, "tax_rate": 0}
            for account in companies_gst_accounts[company]
        ]

        for gst_treatment in NEW_TEMPLATES.values():
            if template_name := frappe.db.get_value(
                DOCTYPE, {"company": company, "gst_treatment": gst_treatment}
            ):
                templates.setdefault(gst_treatment, []).append(template_name)
                continue

            doc = frappe.get_doc(
                {
                    "doctype": DOCTYPE,
                    "title": gst_treatment,
                    "company": company,
                    "gst_treatment": gst_treatment,
                    "tax_rate": 0,
                }
            )

            doc.extend("taxes", gst_accounts)
            doc.insert(ignore_if_duplicate=True)
            templates.setdefault(gst_treatment, []).append(doc.name)

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

    items = [item.name for item in item_list]

    # Don't update for existing templates
    item_templates = frappe.get_all(
        "Item Tax",
        fields=["parent as item", "item_tax_template"],
        filters={"parenttype": "Item", "parent": ["in", items]},
    )

    item_wise_templates = frappe._dict()
    for item in item_templates:
        item_wise_templates.setdefault(item.item, set()).add(item.item_tax_template)

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

    def extend_tax_template(item, templates):
        for template in templates:
            if template in item_wise_templates.get(item.name, []):
                continue

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
            extend_tax_template(item, templates["Nil-Rated"])
            continue

        if item.is_non_gst:
            extend_tax_template(item, templates["Non-GST"])

    frappe.db.bulk_insert("Item Tax", fields=fields, values=values)


def update_item_variant_settings():
    item_variant = frappe.get_single("Item Variant Settings")
    for field in reversed(item_variant.fields):
        if field.field_name in ("is_nil_exempt", "is_non_gst"):
            item_variant.fields.remove(field)

    item_variant.save()
