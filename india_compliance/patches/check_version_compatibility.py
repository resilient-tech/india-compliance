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
        "required_versions": {"version-14": "14.42.0"},
    },
    {
        "app_name": "ERPNext",
        "current_version": version.parse(erpnext.__version__),
        "required_versions": {"version-14": "14.32.0"},
    },
]


def execute():
    for app in VERSIONS_TO_COMPARE:
        app_name = app["app_name"]
        app_version = app["current_version"]

        if IC_VERSION.major != app_version.major:
            raise_incompatible_version_error(app_name, IC_VERSION.major)

        app_branch = get_app_branch(app_name.lower())
        required_versions = app["required_versions"]

        if app_branch not in required_versions:
            continue

        required_version = version.parse(required_versions[app_branch])

        if app_version < required_version:
            raise_incompatible_version_error(app_name, required_version)


def raise_incompatible_version_error(app_name, required_version):
    click.secho(
        (
            f"Incompatible {app_name} Version: \nPlease upgrade {app_name} to version"
            f" {required_version} or above to use the current version of India"
            " Compliance.\n"
        ),
        fg="red",
    )

    raise SystemExit(1)
