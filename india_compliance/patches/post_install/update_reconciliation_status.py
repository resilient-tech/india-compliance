import frappe
from frappe.query_builder.functions import IfNull


def execute():
    PI = frappe.qb.DocType("Purchase Invoice")
    PI_ITEM = frappe.qb.DocType("Purchase Invoice Item")
    BOE = frappe.qb.DocType("Bill of Entry")

    (
        frappe.qb.update(PI)
        .set(PI.reconciliation_status, "Not Applicable")
        .join(PI_ITEM)
        .on(PI.name == PI_ITEM.parent)
        .where(PI.docstatus == 1)
        .where(
            (IfNull(PI.supplier_gstin, "") == "")
            | (
                IfNull(PI.gst_category, "").isin(
                    ["Registered Composition", "Unregistered", "Overseas"]
                )
            )
            | (IfNull(PI.supplier_gstin, "") == PI.company_gstin)
            | (IfNull(PI.is_opening, "") == "Yes")
            | (PI_ITEM.gst_treatment == "Non-GST")
        )
        .run()
    )

    (
        frappe.qb.update(PI)
        .set(PI.reconciliation_status, "Unreconciled")
        .where(PI.docstatus == 1)
        .where(IfNull(PI.reconciliation_status, "") == "")
        .run()
    )

    (
        frappe.qb.update(BOE)
        .set(BOE.reconciliation_status, "Unreconciled")
        .where(BOE.docstatus == 1)
        .run()
    )
