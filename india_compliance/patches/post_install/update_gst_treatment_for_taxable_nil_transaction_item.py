import frappe

DOCTYPES = ("Sales Invoice Item", "Purchase Invoice Item")


def execute():
    update_taxable_items()
    update_nil_rated_items()


def update_taxable_items():
    # Patch invoices where gst_treatment is Nil-Rated but tax is applied.
    # Cases where is_nil_exempt was checked but Item tax template was selected.
    for dt in DOCTYPES:
        doctype = frappe.qb.DocType(dt)

        (
            frappe.qb.update(doctype)
            .set(doctype.gst_treatment, "Taxable")
            .where(doctype.gst_treatment.notin(("Zero-Rated", "Taxable")))
            .where(
                (
                    doctype.cgst_amount
                    + doctype.igst_amount
                    + doctype.sgst_amount
                    + doctype.cess_amount
                )
                != 0
            )
            .run()
        )


def update_nil_rated_items():
    # Patch invoices where Item Tax Template is Nil-Rated.

    nil_rated_templates = frappe.get_all(
        "Item Tax Template", filters={"gst_treatment": "Nil-Rated"}, pluck="name"
    )

    if not nil_rated_templates:
        return

    for dt in DOCTYPES:
        doctype = frappe.qb.DocType(dt)

        (
            frappe.qb.update(doctype)
            .set(doctype.gst_treatment, "Nil-Rated")
            .where(doctype.item_tax_template.isin(nil_rated_templates))
            .where(doctype.gst_treatment == "Taxable")
            .run()
        )
