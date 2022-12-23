import click

from india_compliance.gst_india.constants import BUG_REPORT_URL
from india_compliance.gst_india.setup import after_uninstall as remove_gst_custom_fields
from india_compliance.income_tax_india.setup import (
    after_uninstall as remove_income_tax_fields,
)


def after_uninstall():
    try:
        print("Removing Income Tax customizations...")
        remove_income_tax_fields()

        print("Removing GST customizations...")
        remove_gst_custom_fields()

    except Exception as e:
        click.secho(
            "Removing Customizations for India Compliance failed due to an error."
            " Please try again or"
            f" report the issue on {BUG_REPORT_URL} if not resolved.",
            fg="bright_red",
        )
        raise e

    click.secho("Customizations has been removed Successfully...", fg="green")
