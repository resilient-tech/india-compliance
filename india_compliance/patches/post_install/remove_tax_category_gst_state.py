from india_compliance.utils.custom_fields import delete_old_fields


def execute():
    delete_old_fields(("gst_state", "tax_category_column_break"), "Tax Category")
