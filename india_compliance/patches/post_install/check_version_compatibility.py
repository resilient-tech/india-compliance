from packaging import version

import frappe

# Note: India Compliance versions in DECENDING order only
VERSION_COMPATIBILITY = {
    # Development Versions
    "15.0.0-dev": {"frappe": "15.0.0-dev", "erpnext": "15.0.0-dev"},
    # Stable Versions
    "15.0.0": {"frappe": "15.0.0", "erpnext": "15.0.0"},
    "14.12.0": {"erpnext": "14.29.0"},
    "14.10.4": {"erpnext": "14.29.0"},
    "14.0.0": {"frappe": "14.0.0", "erpnext": "14.0.0"},
}


def execute():
    ic_version = frappe.get_attr("india_compliance.__version__")

    for _version, dependencies in VERSION_COMPATIBILITY.items():
        if version.parse(ic_version) < version.parse(_version):
            continue

        break

    for app, required_version in dependencies.items():
        app_version = version.parse(frappe.get_attr(f"{app}.__version__"))

        if app_version < version.parse(required_version):
            frappe.throw(
                f"Please upgrade {app} to version {required_version} or above to use India Compliance {ic_version}"
            )
