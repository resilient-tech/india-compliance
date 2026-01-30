from functools import wraps

import frappe


def execute_in_new_transaction(fn):
    if frappe.flags.in_test:
        return fn

    @wraps(fn)
    def wrapper(*args, **kwargs):
        _db = frappe.local.db
        try:
            frappe.connect(set_admin_as_user=False)
            result = fn(*args, **kwargs)
            frappe.db.commit()  # nosemgrep
            return result

        finally:
            if frappe.local.db is not _db:
                frappe.db.close()
                frappe.local.db = _db

    return wrapper
