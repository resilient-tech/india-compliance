from frappe.contacts.doctype.address.address import get_address_display

from india_compliance.gst_india.overrides.purchase_invoice import get_ineligibility_reason
from india_compliance.gst_india.overrides.transaction import (
    get_ecommerce_supply_type,
    get_gst_breakup_html,
)


class GSTBreakupExt:
    @property
    def gst_breakup_table(self):
        return get_gst_breakup_html(self)


class EcommerceSupplyTypeExt:
    @property
    def ecommerce_supply_type(self):
        return get_ecommerce_supply_type(self)


class AddressDisplayExt:
    def _get_address_display(self, address_field):
        address = self.get(address_field)
        return get_address_display(address) if address else None

    @property
    def bill_from_address_display(self):
        return self._get_address_display("bill_from_address")

    @property
    def bill_to_address_display(self):
        return self._get_address_display("bill_to_address")

    @property
    def ship_from_address_display(self):
        return self._get_address_display("ship_from_address")

    @property
    def ship_to_address_display(self):
        return self._get_address_display("ship_to_address")


# Purchase Invoice stores this field, so only Purchase Receipt is extended
class IneligibilityReasonExt:
    @property
    def ineligibility_reason(self):
        return get_ineligibility_reason(self)


def before_print(doc, method=None, print_settings=None):
    # print reads doc.get(), which skips properties
    for df in doc.meta.get("fields", {"is_virtual": 1}):
        doc.set(df.fieldname, doc.get_virtual_field_value(df))
