import click
import frappe

TEMPLATE_DOCTYPES = (
    "Sales Taxes and Charges Template",
    "Purchase Taxes and Charges Template",
)

#: (is_inter_state, is_reverse_charge) -> what the combination is commonly called
DEFAULT_SCENARIOS = {
    (0, 0): "In-State",
    (1, 0): "Out-State",
    (0, 1): "Reverse Charge In-State",
    (1, 1): "Reverse Charge Out-State",
}


def execute():
    """Backfill the `is_india_compliance_default` flag on Tax Categories.

    Automatic GST tax template selection now only considers Tax Categories flagged as
    India Compliance defaults. Combinations that already have one are left as they are.
    """
    if not frappe.db.has_column("Tax Category", "is_india_compliance_default"):
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
        fields=["name", "is_inter_state", "is_reverse_charge"],
        filters={"disabled": 0, "name": ["in", list(used_categories)]},
        order_by="creation desc",
    )

    defaults = []
    for (is_inter_state, is_reverse_charge), scenario in DEFAULT_SCENARIOS.items():
        if frappe.db.exists(
            "Tax Category",
            {
                "is_india_compliance_default": 1,
                "is_inter_state": is_inter_state,
                "is_reverse_charge": is_reverse_charge,
                "disabled": 0,
            },
        ):
            continue

        category = get_default_tax_category(tax_categories, is_inter_state, is_reverse_charge)

        if not category:
            click.secho(
                f"No Tax Category could be set as the India Compliance Default for {scenario}"
                " transactions. Please set it manually to use automatic GST tax template"
                " selection.",
                fg="yellow",
            )
            continue

        defaults.append(category)

    if not defaults:
        return

    tax_category = frappe.qb.DocType("Tax Category")
    frappe.qb.update(tax_category).set(tax_category.is_india_compliance_default, 1).where(
        tax_category.name.isin(defaults)
    ).run()


def get_default_tax_category(categories, is_inter_state, is_reverse_charge):
    for category in categories:
        if category.is_inter_state == is_inter_state and category.is_reverse_charge == is_reverse_charge:
            return category.name

    return None
