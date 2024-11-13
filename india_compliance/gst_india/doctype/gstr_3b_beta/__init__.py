import frappe
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Abs, IfNull, Sum

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    GSTIN_RULES,
    PAN_RULES,
    BaseUtil,
    BillOfEntry,
    PurchaseInvoice,
    Reconciler,
)

ORIGINAL_VS_AMENDED = (
    {
        "original": "B2B",
        "amended": "B2BA",
    },
    {
        "original": "ISD",
        "amended": "ISDA",
    },
    {
        "original": "IMPG",
        "amended": "",
    },
    {
        "original": "IMPGSEZ",
        "amended": "",
    },
)


def auto_reconcile_invoices(filters):
    """
    Reconcile purchases and inward supplies for given category.
    """

    _Reconciler = Reconciler()

    for row in ORIGINAL_VS_AMENDED:
        filters["category"] = row["original"]
        filters["amended_category"] = row["amended"] or None

        purchases = get_unmatched_purchases(filters)
        inward_supplies = get_unmatched_inward_supplies(filters)

        # GSTIN Level matching
        _Reconciler.reconcile_for_rules(GSTIN_RULES, purchases, inward_supplies)

        if filters.category == "IMPG":  # Is this required here ??
            return

        # PAN Level matching
        purchases = _Reconciler.get_pan_level_data(purchases)
        inward_supplies = _Reconciler.get_pan_level_data(inward_supplies)
        _Reconciler.reconcile_for_rules(PAN_RULES, purchases, inward_supplies)


def get_unmatched_inward_supplies(filters):
    categories = [filters.category, filters.amended_category]
    inward_supply = frappe.qb.DocType("GST Inward Supply")
    inward_supply_item = frappe.qb.DocType("GST Inward Supply Item")

    query = get_base_inward_supply_query(inward_supply, inward_supply_item)
    query = get_query_with_filters(inward_supply, query, filters)

    data = (
        query.where(IfNull(inward_supply.match_status, "") == "")
        .where(IfNull(inward_supply.ims_action, "") != "")
        .where(inward_supply.classification.isin(categories))
        .run(as_dict=True)
    )

    for doc in data:
        doc.fy = BaseUtil.get_fy(doc.bill_date)

    return BaseUtil.get_dict_for_key("supplier_gstin", data)


def get_unmatched_purchases(filters):
    if filters.category in ("IMPG", "IMPGSEZ"):
        return get_unmatched_bill_of_entry(filters)

    return get_unmatched_purchase_invoices(filters)


def get_unmatched_purchase_invoices(filters):
    purchase = frappe.qb.DocType("Purchase Invoice")
    purchase_item = frappe.qb.DocType("Purchase Invoice Item")

    gst_category = (
        ("Registered Regular", "Tax Deductor", "Input Service Distributor")
        if filters.category in ("B2B", "ISD")
        else ("SEZ", "Overseas", "UIN Holders")
    )

    query = get_base_purchase_query(purchase, purchase_item)
    query = get_query_with_filters(purchase, query, filters)

    data = (
        query.where(
            purchase.name.notin(PurchaseInvoice.query_matched_purchase_invoice())
        )
        .where(purchase.gst_category.isin(gst_category))
        .where(purchase.is_return == 0)
        .run(as_dict=True)
    )

    for doc in data:
        doc.fy = BaseUtil.get_fy(doc.bill_date)

    return BaseUtil.get_dict_for_key("supplier_gstin", data)


def get_unmatched_bill_of_entry(filters):
    boe = frappe.qb.DocType("Bill of Entry")
    boe_item = frappe.qb.DocType("Bill of Entry Item")
    purchase_invoice = frappe.qb.DocType("Purchase Invoice")

    gst_category = "SEZ" if filters.category == "IMPGSEZ" else "Overseas"

    query = get_base_bill_of_entry_query(boe, boe_item, purchase_invoice)
    query = get_query_with_filters(boe, query, filters)

    data = (
        query.where(purchase_invoice.gst_category == gst_category)
        .where(boe.name.notin(BillOfEntry.query_matched_bill_of_entry()))
        .run(as_dict=True)
    )

    for doc in data:
        doc.fy = BaseUtil.get_fy(doc.bill_date)

    return BaseUtil.get_dict_for_key("supplier_gstin", data)


def get_base_inward_supply_query(inward_supply, inward_supply_item):
    fields = GST_TAX_TYPES[:-1] + ("taxable_value",)
    tax_fields = [Sum(inward_supply_item[field]).as_(field) for field in fields]

    return (
        frappe.qb.from_(inward_supply)
        .left_join(inward_supply_item)
        .on(inward_supply_item.parent == inward_supply.name)
        .select(
            *tax_fields,
            inward_supply.supplier_gstin,
            inward_supply.supplier_name,
            inward_supply.bill_no,
            inward_supply.bill_date,
            inward_supply.company,
            inward_supply.company_gstin,
            inward_supply.link_name,
            inward_supply.link_doctype,
            inward_supply.match_status,
            inward_supply.ims_action,
            inward_supply.supply_type,
            inward_supply.name,
            inward_supply.classification,
            inward_supply.is_reverse_charge,
            inward_supply.place_of_supply,
            ConstantColumn("GST Inward Supply").as_("doctype"),
        )
        .where(inward_supply_item.parenttype == "GST Inward Supply")
        .groupby(inward_supply_item.parent)
    )


def get_base_purchase_query(purchase, purchase_item):
    tax_fields = [
        query_tax_amount(purchase_item, f"{tax_type}_amount").as_(tax_type)
        for tax_type in GST_TAX_TYPES
    ]

    return (
        frappe.qb.from_(purchase)
        .left_join(purchase_item)
        .on(purchase_item.parent == purchase.name)
        .select(
            Abs(Sum(purchase_item.taxable_value)).as_("taxable_value"),
            *tax_fields,
            purchase.name,
            purchase.supplier_gstin,
            purchase.supplier,
            purchase.bill_no,
            purchase.bill_date,
            purchase.company,
            purchase.company_gstin,
            purchase.is_reverse_charge,
            purchase.place_of_supply,
            ConstantColumn("Purchase Invoice").as_("doctype"),
        )
        .groupby(purchase.name)
    )


def get_base_bill_of_entry_query(boe, boe_item, purchase_invoice):
    tax_fields = [
        query_tax_amount(boe_item, f"{tax_type}_amount").as_(tax_type)
        for tax_type in GST_TAX_TYPES
    ]

    return (
        frappe.qb.from_(boe)
        .left_join(boe_item)
        .on(boe_item.parent == boe.name)
        .join(purchase_invoice)
        .on(boe.purchase_invoice == purchase_invoice.name)
        .select(
            *tax_fields,
            boe.total_taxable_value.as_("taxable_value"),
            boe.bill_of_entry_no,
            boe.bill_of_entry_date,
            purchase_invoice.supplier_gstin,
            purchase_invoice.supplier,
            boe.name,
            purchase_invoice.is_reverse_charge,
            purchase_invoice.place_of_supply,
            ConstantColumn("Bill of Entry").as_("doctype"),
        )
        .where(boe.docstatus == 1)
        .where(boe_item.parenttype == "Bill of Entry")
        .groupby(boe.name)
    )


def query_tax_amount(doc, field):
    return Abs(Sum(getattr(doc, field)))


def get_query_with_filters(doc, query, filters):
    if filters.get("company"):
        query = query.where(doc.company == filters.company)

    if filters.get("company_gstin"):
        query = query.where(doc.company_gstin == filters.company_gstin)

    return query
