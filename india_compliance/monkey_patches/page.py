from frappe.core.doctype.page.page import Page

from india_compliance.gst_india.utils.api import is_conf_api_enabled

pages_to_restrict = "india-compliance-account"

_is_permitted = Page.is_permitted


def is_permitted(self):
    """Restrict `India Compliance Account Page for IC Config Users`"""
    _is_permitted(self)

    if self.name in pages_to_restrict and is_conf_api_enabled():
        return False
    return True


Page.is_permitted = is_permitted
