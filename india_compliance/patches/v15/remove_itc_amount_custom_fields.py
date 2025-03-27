from india_compliance.utils.custom_fields import delete_old_fields


def execute():
    # these fields are not required
    fields_to_delete = [
        "gst_col_break",
        "itc_integrated_tax",
        "itc_central_tax",
        "itc_state_tax",
        "itc_cess_amount",
    ]

    for field in fields_to_delete:
        delete_old_fields(field, "Purchase Invoice")
