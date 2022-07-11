import json

import frappe
from frappe.desk.desktop import Workspace

from india_compliance.gst_india.utils.api import is_conf_api_enabled

PAGE_TO_RESTRICT = "india-compliance-account"


@frappe.whitelist()
@frappe.read_only()
def get_desktop_page(page):
    """Applies permissions, customizations and returns the configruration for a page
    on desk.

    Args:
            page (json): page data

    Returns:
            dict: dictionary of cards, charts and shortcuts to be displayed on website
                    Returns only allowed cards, charts and shortcuts in GST India
    """
    try:
        workspace = Workspace(json.loads(page))
        workspace.build_workspace()

        desktop_pages = frappe._dict(
            {
                "charts": workspace.charts,
                "shortcuts": workspace.shortcuts,
                "cards": workspace.cards,
                "onboardings": workspace.onboardings,
                "quick_lists": workspace.quick_lists,
            }
        )

        if not is_conf_api_enabled():
            return desktop_pages

        # Remove cards and shortcuts that are not allowed for saas users in GST India
        for shortcut in desktop_pages.shortcuts.get("items", []):
            if shortcut.get("link_to") == PAGE_TO_RESTRICT:
                desktop_pages.shortcuts.remove(shortcut)
                break

        for card in workspace.cards.get("items"):
            for link in card.get("links"):
                if link.get("link_to") == PAGE_TO_RESTRICT:
                    card.get("links").remove(link)
                    break

        return desktop_pages

    except frappe.DoesNotExistError:
        frappe.log_error("Workspace Missing")
        return {}
