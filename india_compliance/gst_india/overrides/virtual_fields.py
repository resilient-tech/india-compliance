from frappe.contacts.doctype.address.address import get_address_display
from frappe.utils import is_a_property

from india_compliance.gst_india.overrides.purchase_invoice import get_ineligibility_reason
from india_compliance.gst_india.overrides.transaction import (
    get_ecommerce_supply_type,
    get_gst_breakup_html,
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


EXTENSIONS = (
    GSTBreakupExtension,
    EcommerceSupplyTypeExtension,
    AddressDisplayExtension,
    IneligibilityReasonExtension,
)


def before_print(doc, method=None, print_settings=None):
    # ponytail: print reads doc.get(), which skips properties; drop this hook once frappe print resolves them
    for extension in EXTENSIONS:
        if not isinstance(doc, extension):
            continue

        for fieldname, value in vars(extension).items():
            if is_a_property(value):
                doc.set(fieldname, getattr(doc, fieldname))
