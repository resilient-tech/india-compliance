import frappe
from frappe.query_builder.functions import Sum

from india_compliance.db_utils import bulk_update


def execute():
    # Get GST Inward Supply Items
    dt = frappe.qb.DocType("GST Inward Supply Item")
    inward_supply_values = (
        frappe.qb.from_(dt)
        .select(
            dt.parent.as_("name"),
            Sum(dt.taxable_value).as_("taxable_value"),
            Sum(dt.igst).as_("igst"),
            Sum(dt.cgst).as_("cgst"),
            Sum(dt.sgst).as_("sgst"),
            Sum(dt.cess).as_("cess"),
        )
        .groupby(dt.parent)
        .run(as_dict=True)
    )

    inward_supply_map = {d.pop("name"): d for d in inward_supply_values}

    # Update GST Inward Supply
    bulk_update("GST Inward Supply", inward_supply_map)
