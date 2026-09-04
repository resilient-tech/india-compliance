"""commit_after_response for frappe 15.

Copied from frappe/database/utils.py (frappe 16), where it was added along with the reliable
after_response callbacks (frappe #42371, in 15.120.0 too). Drop this module once the app is on
frappe >= 16 and import it from frappe instead.
"""

import frappe
from frappe.utils import CallbackManager


class CommitAfterResponseManager(CallbackManager):
    __slots__ = ()

    def run(self):
        db = getattr(frappe.local, "db", None)
        if not db:
            # try reconnecting to the database
            frappe.connect(set_admin_as_user=False)
            db = frappe.local.db

        savepoint_name = "commit_after_response"

        while self._functions:
            _func = self._functions.popleft()
            try:
                db.savepoint(savepoint_name)
                _func()
            except Exception:
                db.rollback(save_point=savepoint_name)
                frappe.log_error(title="Error executing commit_after_response callback")

        db.commit()  # nosemgrep


def commit_after_response(func):
    """
    Runs and commits some queries after response is sent.
    Works only if in a request context and not in tests.
    Calls function immediately otherwise.
    """

    request = getattr(frappe.local, "request", False)
    if not request or frappe.flags.in_test:
        func()
        return

    callback_manager = getattr(request, "commit_after_response", None)
    if callback_manager is None:
        # if no callback manager, create one
        callback_manager = CommitAfterResponseManager()
        request.commit_after_response = callback_manager
        request.after_response.add(callback_manager.run)

    callback_manager.add(func)
