import frappe


def read_data_file(file_name):
    file_path = frappe.get_app_path(
        "india_compliance", "income_tax_india", "data", file_name
    )
    with open(file_path, "r") as f:
        return f.read()
