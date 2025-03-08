from india_compliance.utils.custom_fields import delete_old_fields


def execute():
    delete_old_fields("ecommerce_gstin", "Purchase Invoice")
