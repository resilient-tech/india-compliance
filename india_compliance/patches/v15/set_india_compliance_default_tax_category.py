import frappe

TEMPLATE_DOCTYPES = (
    "Sales Taxes and Charges Template",
    "Purchase Taxes and Charges Template",
)

DEFAULT_SCENARIOS = ((0, 0), (1, 0), (0, 1), (1, 1))


def execute():
    """Backfill the `is_india_compliance_default` flag on Tax Categories.

    Automatic GST tax template selection now only considers Tax Categories flagged as
    India Compliance defaults.
    """
    if not frappe.db.has_column("Tax Category", "is_india_compliance_default"):
        return

    if frappe.db.exists("Tax Category", {"is_india_compliance_default": 1}):
        return

    used_categories = set()
    for master_doctype in TEMPLATE_DOCTYPES:
        used_categories.update(
            frappe.get_all(
                master_doctype, filters={"disabled": 0, "tax_category": ["is", "set"]}, pluck="tax_category"
            )
        )
    if not used_categories:
        return

    tax_categories = frappe.get_all(
        "Tax Category",
        fields=["name", "is_inter_state", "is_reverse_charge", "gst_state"],
        filters={"disabled": 0, "gst_state": ["is", "not set"]},
    )

    defaults = []
    for is_inter_state, is_reverse_charge in DEFAULT_SCENARIOS:
        category = get_default_tax_category(
            tax_categories, used_categories, is_inter_state, is_reverse_charge
        )
        if category:
            defaults.append(category)

    if not defaults:
        return

    tax_category = frappe.qb.DocType("Tax Category")
    frappe.qb.update(tax_category).set(tax_category.is_india_compliance_default, 1).where(
        tax_category.name.isin(defaults)
    ).run()


def get_default_tax_category(categories, used_categories, is_inter_state, is_reverse_charge):
    for category in categories:
        if (
            category.is_inter_state == is_inter_state
            and category.is_reverse_charge == is_reverse_charge
            and category.name in used_categories
        ):
            return category.name

    return None
