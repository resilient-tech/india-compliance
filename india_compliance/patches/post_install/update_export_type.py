from india_compliance.patches.post_install.update_reverse_charge_field import (
    update_and_process_column,
)


def execute():
    update_and_process_column(
        column="export_type",
        doctypes=("Purchase Invoice", "Sales Invoice"),
        values_to_update="With Payment of Tax",
    )
