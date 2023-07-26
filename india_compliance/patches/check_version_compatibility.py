import click
from packaging import version

import frappe
import erpnext

from india_compliance import MIN_ERPNEXT_VERSION, MIN_FRAPPE_VERSION

VERSIONS_TO_COMPARE = [
    {
        "app_name": "frappe",
        "current_version": frappe.__version__,
        "required_version": MIN_FRAPPE_VERSION,
    },
    {
        "app_name": "erpnext",
        "current_version": erpnext.__version__,
        "required_version": MIN_ERPNEXT_VERSION,
    },
]


def execute():
    for app in VERSIONS_TO_COMPARE:
        app_name = app["app_name"]
        current_version = app["current_version"]
        required_version = app["required_version"]

        if version.parse(current_version) >= version.parse(required_version):
            continue

        click.secho(
            (
                f"Please upgrade {app_name} to version {required_version} or"
                " above to use the current version of India Compliance."
            ),
            fg="red",
        )

        frappe.throw(f"Incompatible {app_name.title()} Version")
