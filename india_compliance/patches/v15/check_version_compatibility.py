import click

import frappe


def execute():
    if not getattr(frappe, "__version__", "").startswith("14."):
        return

    click.secho(
        (
            'The "develop" branch of India Compliance is no longer compatible with'
            " version 14 of Frappe Framework and ERPNext. Please switch to the"
            ' "version-14" branch by executing the following command:'
        ),
        fg="red",
    )
    click.secho("\nbench switch-to-branch version-14 india_compliance\n", bold=True)
    click.secho(
        "You can read more about this change here: https://discuss.frappe.io/t/95783\n",
        fg="red",
    )
    frappe.throw("Incompatible version of Frappe Framework")
