from india_compliance.utils.custom_fields import delete_old_fields


def execute():
    """Remove the deprecated "Source State" (`gst_state`) field from Tax Category.

    Automatic GST tax template selection no longer relies on a source state configured
    on the Tax Category. Selection is based purely on the transaction's place of supply
    (Inter State / Reverse Charge) via the India Compliance default Tax Categories.
    """
    delete_old_fields(("gst_state", "tax_category_column_break"), "Tax Category")
