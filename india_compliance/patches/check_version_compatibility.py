from packaging import version

import frappe
import erpnext

import india_compliance

# Note: India Compliance versions in DESCENDING order only
VERSION_COMPATIBILITY = {
    # Development Versions
    "15.0.0-dev": {"frappe": "15.0.0-dev", "erpnext": "15.0.0-dev"},
    # Stable Versions
    "15.0.0": {"frappe": "15.0.0", "erpnext": "15.0.0"},
    "14.14.0": {"frappe": "14.42.0", "erpnext": "14.32.0"},
    "14.10.4": {"frappe": "14.0.0", "erpnext": "14.29.0"},
    "14.0.0": {"frappe": "14.0.0", "erpnext": "14.0.0"},
}

CURRENT_VERSIONS = {
    "india_compliance": india_compliance.__version__,
    "frappe": frappe.__version__,
    "erpnext": erpnext.__version__,
}


def execute():
    current_version = version.parse(CURRENT_VERSIONS["india_compliance"])

    # dependencies for current version
    for _version, dependencies in VERSION_COMPATIBILITY.items():
        if current_version < version.parse(_version):
            continue

        break

    # check if all dependencies are satisfied
    for app, required_version in dependencies.items():
        app_version = version.parse(CURRENT_VERSIONS[app])

        if app_version < version.parse(required_version):
            frappe.throw(
                f"Please upgrade {app} to version {required_version} or above to use India Compliance {current_version}"
            )
