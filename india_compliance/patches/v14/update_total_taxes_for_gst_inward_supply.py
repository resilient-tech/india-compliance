import frappe
from frappe.query_builder.functions import Sum


def execute():
    # Get GST Inward Supply Items
    dt = frappe.qb.DocType("GST Inward Supply Item")
    inward_supply_values = (
        frappe.qb.from_(dt)
        .select(
            dt.parent.as_("name"),
            Sum(dt.taxable_value),
            Sum(dt.igst),
            Sum(dt.cgst),
            Sum(dt.sgst),
            Sum(dt.cess),
        )
        .groupby(dt.parent)
        .run(as_dict=True)
    )

    frappe.db.bulk_update(
        "GST Inward Supply", {d.pop("name"): d for d in inward_supply_values}
    )
