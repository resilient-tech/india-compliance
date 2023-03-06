import click

import frappe


def execute():
    click.secho(
        (
            'The "next" branch of India Compliance has been deprecated in favour of'
            ' "develop" to maintain consistency with Frappe Framework and ERPNext.'
            ' Please switch to the "develop" branch by executing the following command:'
        ),
        fg="red",
    )
    click.secho("\nbench switch-to-branch develop india_compliance\n", bold=True)
    frappe.throw('Deprecated Branch "next"')
