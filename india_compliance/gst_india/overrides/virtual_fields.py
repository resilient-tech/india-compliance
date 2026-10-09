from frappe.contacts.doctype.address.address import get_address_display
from frappe.utils import is_a_property

from india_compliance.gst_india.overrides.purchase_invoice import get_ineligibility_reason
from india_compliance.gst_india.overrides.transaction import (
    get_ecommerce_supply_type,
    get_gst_breakup_html,
)

VIRTUAL_FIELDS = (
    "gst_breakup_table",
    "ecommerce_supply_type",
    "bill_from_address_display",
    "bill_to_address_display",
    "ship_from_address_display",
    "ship_to_address_display",
    "ineligibility_reason",
)


class GSTBreakupExtension:
    @property
    def gst_breakup_table(self):
        return get_gst_breakup_html(self)


class EcommerceSupplyTypeExtension:
    @property
    def ecommerce_supply_type(self):
        return get_ecommerce_supply_type(self)


class AddressDisplayExtension:
    @property
    def bill_from_address_display(self):
        return get_address_display(self.bill_from_address)

    @property
    def bill_to_address_display(self):
        return get_address_display(self.bill_to_address)

    @property
    def ship_from_address_display(self):
        return get_address_display(self.ship_from_address)

    @property
    def ship_to_address_display(self):
        return get_address_display(self.ship_to_address)


# Purchase Invoice stores this field, so only Purchase Receipt is extended
class IneligibilityReasonExtension:
    @property
    def ineligibility_reason(self):
        return get_ineligibility_reason(self)


def before_print(doc, method=None, print_settings=None):
    # print reads doc.get(), which skips properties; remove once frappe print resolves them
    for fieldname in VIRTUAL_FIELDS:
        if is_a_property(getattr(type(doc), fieldname, None)):
            doc.set(fieldname, getattr(doc, fieldname))
