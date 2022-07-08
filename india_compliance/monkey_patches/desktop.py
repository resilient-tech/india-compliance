from frappe.desk.desktop import Workspace, handle_not_exist

from india_compliance.gst_india.utils.api import is_conf_api_enabled

page_to_restrict = "india-compliance-account"

_get_shortcuts = Workspace.get_shortcuts


@handle_not_exist
def get_shortcuts(self):
    """Restrict `India Compliance Account Page for IC Config Users`"""
    shortcuts = _get_shortcuts(self)

    if is_conf_api_enabled():
        shortcuts = [s for s in shortcuts if s.get("link_to") != page_to_restrict]

    return shortcuts


Workspace.get_shortcuts = get_shortcuts

_get_links = Workspace.get_links


@handle_not_exist
def get_links(self):
    """Restrict `India Compliance Account Page for IC Config Users`"""
    links = _get_links(self)

    if is_conf_api_enabled():
        for link in links:
            for l in link.get("links"):
                if l.get("link_to") == page_to_restrict:
                    link.get("links").remove(l)
                    break

    return links


Workspace.get_links = get_links
