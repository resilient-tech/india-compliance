import frappe


def execute():
    """GSTR-2A now always downloads all sections.

    Clean up the obsolete per-category preferences:
    - the `reconcile_for_*` fields in GST Settings (auto reconciliation)
    - the `purchase_reco_2a_categories` user default (download dialog)
    """
    frappe.db.delete(
        "Singles",
        {
            "doctype": "GST Settings",
            "field": (
                "in",
                (
                    "reconcile_for_b2b",
                    "reconcile_for_b2ba",
                    "reconcile_for_cdnr",
                    "reconcile_for_cdnra",
                    "reconcile_for_isd",
                    "reconcile_for_isda",
                    "reconcile_for_impg",
                    "reconcile_for_impgsez",
                ),
            ),
        },
    )

    frappe.db.delete("DefaultValue", {"defkey": "purchase_reco_2a_categories"})
    frappe.clear_cache()
