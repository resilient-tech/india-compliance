import click
from packaging import version

import frappe
from frappe.utils.change_log import get_app_branch
import erpnext

import india_compliance

IC_VERSION = version.parse(india_compliance.__version__)

VERSIONS_TO_COMPARE = [
    {
        "app_name": "Frappe",
        "current_version": version.parse(frappe.__version__),
        "required_versions": {"version-14": "14.57.0", "version-15": "15.3.0"},
    },
    {
        "app_name": "ERPNext",
        "current_version": version.parse(erpnext.__version__),
        "required_versions": {"version-14": "14.66.5", "version-15": "15.19.3"},
    },
]


def execute():
    for app in VERSIONS_TO_COMPARE:
        app_name = app["app_name"]
        app_version = app["current_version"]

        if IC_VERSION.major != app_version.major:
            show_error_and_exit(
                f"Incompatible {app_name} Version: \n"
                f"{app_name} version {app_version} not compatible with India Compliance {IC_VERSION}\n"
                f"Please switch to version {IC_VERSION.major} of {app_name} to use the current version of"
                " India Compliance.\n"
            )

        if IC_VERSION.major == 16:
            continue

        app_branch = get_app_branch(app_name.lower())
        required_versions = app["required_versions"]

        if app_branch not in required_versions:
            continue

        required_version = version.parse(required_versions[app_branch])

        if app_version < required_version:
            show_error_and_exit(
                f"Incompatible {app_name} Version: \n"
                f"{app_name} version {app_version} not compatible with India Compliance {IC_VERSION}\n"
                "Please upgrade {app_name} to version {required_version} or above to use the current version of"
                " India Compliance.\n"
            )


def show_error_and_exit(error_message):
    click.secho(error_message, fg="red")
    raise SystemExit(1)
