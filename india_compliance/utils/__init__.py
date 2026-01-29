from functools import wraps

import frappe


def execute_in_new_transaction(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        _db = frappe.local.db
        try:
            frappe.connect(set_admin_as_user=False)
            result = fn(*args, **kwargs)
            frappe.db.commit()  # nosemgrep
            return result

        finally:
            frappe.db.close()
            frappe.local.db = _db

    return wrapper
