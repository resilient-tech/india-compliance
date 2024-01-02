import click

import frappe
import frappe.defaults
from frappe.query_builder import Case
from frappe.query_builder.functions import IfNull
from frappe.utils import get_datetime, random_string
from frappe.utils.user import get_users_with_role

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

TRANSACTION_ITEM_DOCTYPES = (
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
    TRANSACTION_ITEM_DOCTYPES: [
        {"fieldname": "is_nil_exempt"},
        {"fieldname": "is_non_gst"},
    ],
}

NEW_TEMPLATES = {
    "is_nil_rated": "Nil-Rated",
    "is_exempted": "Exempted",
    "is_non_gst": "Non-GST",
}


def execute():
    if not frappe.db.has_column("Item", "is_nil_exempt"):
        return

    companies = get_indian_companies()
    templates = create_or_update_item_tax_templates(companies)
    update_items_with_templates(templates)

    update_gst_treatment_for_transactions()
    update_gst_details_for_transactions(companies)

    remove_old_item_variant_settings()
    delete_custom_fields(FIELDS_TO_DELETE)


def get_indian_companies():
    return frappe.get_all("Company", filters={"country": "India"}, pluck="name")


def create_or_update_item_tax_templates(companies):
    if not companies:
        return

    DOCTYPE = "Item Tax Template"
    item_tax_templates = frappe.get_all(DOCTYPE, pluck="name")
    companies_with_templates = set()
    company_wise_gst_accounts = frappe._dict()

    # update tax rates
    for template_name in item_tax_templates:
        doc = frappe.get_doc(DOCTYPE, template_name)
        if doc.company not in companies or not doc.taxes:
            continue

        if doc.company not in company_wise_gst_accounts:
            company_wise_gst_accounts[doc.company] = get_all_gst_accounts(doc.company)

        gst_accounts = company_wise_gst_accounts[doc.company]
        if not gst_accounts:
            continue

        _, intra_state_accounts, inter_state_accounts = get_valid_accounts(
            doc.company, for_sales=True, for_purchase=True, throw=False
        )

        # All GST Accounts not configured
        if not intra_state_accounts or not inter_state_accounts:
            continue

        gst_rates = set()
        companies_with_templates.add(doc.company)

        for row in doc.taxes:
            if row.tax_type in intra_state_accounts:
                gst_rates.add(row.tax_rate * 2)
            elif row.tax_type in inter_state_accounts:
                gst_rates.add(row.tax_rate)

        # Invalid template
        if len(gst_rates) != 1:
            continue

        doc.gst_rate = next(iter(gst_rates))

        if doc.gst_treatment != "Taxable":
            # Cases where patch is run again
            continue

        elif doc.gst_rate > 0:
            doc.gst_treatment = "Taxable"

        elif doc.gst_rate == 0:
            doc.gst_treatment = "Nil-Rated"

        doc.save()

    # create new templates for nil rated, exempted, non gst
    templates = {}
    show_notification = False
    for company in companies_with_templates:
        gst_accounts = [
            {"tax_type": account, "tax_rate": 0}
            for account in company_wise_gst_accounts[company]
        ]

        for new_template in NEW_TEMPLATES.values():
            if template_name := frappe.db.get_value(
                DOCTYPE, {"company": company, "gst_treatment": new_template}
            ):
                templates.setdefault(new_template, []).append(template_name)
                continue

            doc = frappe.get_doc(
                {
                    "doctype": DOCTYPE,
                    "title": new_template,
                    "company": company,
                    "gst_treatment": new_template,
                    "tax_rate": 0,
                }
            )

            doc.extend("taxes", gst_accounts)
            doc.insert(ignore_if_duplicate=True)
            templates.setdefault(new_template, []).append(doc.name)
            show_notification = True

    if show_notification:
        click.secho(
            "Nil Rated items are differentiated from Exempted for GST (configrable from Item Tax Template).",
            color="yellow",
        )
        click.secho(
            "All transactions that were marked as Nil or Exempt, are now marked as Nil Rated.",
            color="red",
        )

        for user in get_users_with_role("Accounts Manager"):
            frappe.defaults.set_user_default(
                "needs_item_tax_template_notification", 1, user=user
            )

    return templates


def update_items_with_templates(templates):
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
    all_templates = []
    for category_templates in templates.values():
        all_templates.extend(category_templates)

    # Don't update for existing templates
    item_templates = frappe.get_all(
        "Item Tax",
        fields=["parent as item", "item_tax_template"],
        filters={
            "parenttype": "Item",
            "parent": ["in", items],
            "item_tax_template": ["in", all_templates],
        },
    )

    item_wise_templates = frappe._dict()
    for row in item_templates:
        item_wise_templates.setdefault(row.item, set()).add(row.item_tax_template)

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

    values = []
    time = get_datetime()

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

    for item in item_list:
        if item.is_nil_exempt:
            extend_tax_template(item, templates["Nil-Rated"])
            continue

        if item.is_non_gst:
            extend_tax_template(item, templates["Non-GST"])

    frappe.db.bulk_insert("Item Tax", fields=fields, values=values)


def remove_old_item_variant_settings():
    item_variant = frappe.get_single("Item Variant Settings")
    for field in reversed(item_variant.fields):
        if field.field_name in ("is_nil_exempt", "is_non_gst"):
            item_variant.fields.remove(field)

    item_variant.save()


###### Updating Transactions ##############################################
def update_gst_treatment_for_transactions():
    "Disclaimer: No specific way to differentate between nil and exempted. Hence all transactions are updated to nil"

    for item_doctype in TRANSACTION_ITEM_DOCTYPES:
        # GST Treatment is not required in Material Request Item
        if item_doctype == "Material Request Item":
            continue

        table = frappe.qb.DocType(item_doctype)
        query = frappe.qb.update(table)

        (
            query.set(
                table.gst_treatment,
                Case()
                .when(table.is_nil_exempt == 1, "Nil-Rated")
                .when(table.is_non_gst == 1, "Non-GST")
                .else_("Taxable"),
            )
            .where(IfNull(table.gst_treatment, "") == "")
            .run()
        )

        doctype = item_doctype.replace(" Item", "")
        if doctype not in SALES_DOCTYPES:
            continue

        doc = frappe.qb.DocType(doctype)

        (
            query.join(doc)
            .on(doc.name == table.parent)
            .set(table.gst_treatment, "Zero-Rated")
            .where(
                (doc.gst_category == "SEZ")
                | (
                    (doc.gst_category == "Overseas")
                    & (doc.place_of_supply == "96-Other Countries")
                )
            )
            .run()
        )


def update_gst_details_for_transactions(companies):
    for company in companies:
        gst_accounts = []
        for account_type in ["Input", "Output"]:
            gst_accounts.extend(
                get_gst_accounts_by_type(company, account_type, throw=False).values()
            )

        if not gst_accounts:
            continue

        for doctype in ("Sales Invoice", "Purchase Invoice"):
            is_sales_doctype = doctype in SALES_DOCTYPES
            docs = get_docs_with_gst_accounts(doctype, gst_accounts)
            if not docs:
                continue

            chunk_size = 100
            total_docs = len(docs)

            with click.progressbar(
                range(0, total_docs, chunk_size),
                label=f"Updating {total_docs} {doctype}s",
            ) as bar:
                for index in bar:
                    chunk = docs[index : index + chunk_size]

                    taxes = get_taxes_for_docs(chunk, doctype, is_sales_doctype)
                    items = get_items_for_docs(chunk, doctype)
                    complied_docs = compile_docs(taxes, items)

                    if not complied_docs:
                        continue

                    gst_details = ItemGSTDetails().get(
                        complied_docs.values(), doctype, company
                    )

                    if not gst_details:
                        continue

                    build_query_and_update_gst_details(gst_details, doctype)
                    frappe.db.commit()


def get_docs_with_gst_accounts(doctype, gst_accounts):
    gl_entry = frappe.qb.DocType("GL Entry")

    return (
        frappe.qb.from_(gl_entry)
        .select(gl_entry.voucher_no)
        .where(gl_entry.voucher_type == doctype)
        .where(gl_entry.account.isin(gst_accounts))
        .where(gl_entry.is_cancelled == 0)
        .distinct()
        .run(pluck=True)
    )


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
    """
    Complie docs, so that each one could be accessed as if it's a single doc.
    """
    response = frappe._dict()

    for tax in taxes:
        if tax.parent not in response:
            response[tax.parent] = frappe._dict(taxes=[], items=[])

        response[tax.parent]["taxes"].append(tax)

    for item in items:
        if item.parent not in response:
            response[item.parent] = frappe._dict(taxes=[], items=[])

        response[item.parent]["items"].append(item)

    return response


def build_query_and_update_gst_details(gst_details, doctype):
    transaction_item = frappe.qb.DocType(f"{doctype} Item")

    update_query = frappe.qb.update(transaction_item)
    execute_query = False

    # Initialize CASE queries
    conditions = frappe._dict()
    conditions_available_for = set()

    for tax in GST_TAX_TYPES:
        for field in (f"{tax}_rate", f"{tax}_amount"):
            conditions[field] = Case()

    # Update item conditions (WHEN)
    for item_name, row in gst_details.items():
        for field in conditions:
            if not row.get(field):
                continue

            conditions[field] = conditions[field].when(
                transaction_item.name == item_name, row[field]
            )
            conditions_available_for.add(field)

    # Update queries
    for field in conditions:
        # Atleast one WHEN condition required for Case queries
        if field not in conditions_available_for:
            continue

        # ELSE
        conditions[field] = conditions[field].else_(transaction_item[field])
        update_query = update_query.set(transaction_item[field], conditions[field])
        execute_query = True

    if execute_query:
        update_query = update_query.where(
            transaction_item.name.isin(list(gst_details.keys()))
        ).run()
