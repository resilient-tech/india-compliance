from frappe.contacts.doctype.address.address import get_address_display

from india_compliance.gst_india.overrides.purchase_invoice import get_ineligibility_reason
from india_compliance.gst_india.overrides.transaction import (
    get_ecommerce_supply_type,
    get_gst_breakup_html,
)

# class extensions for virtual fields


class GSTBreakupExt:
    """Resolves the ``gst_breakup_table`` virtual field (sales & purchase transactions)."""

    @property
    def gst_breakup_table(self):
        return get_gst_breakup_html(self)


class EcommerceSupplyTypeExt:
    """Resolves the ``ecommerce_supply_type`` virtual field (Sales Order/Delivery Note/Sales Invoice)."""

    @property
    def ecommerce_supply_type(self):
        return get_ecommerce_supply_type(self)


class AddressDisplayExt:
    """Resolves the four subcontracting ``*_address_display`` virtual fields (Stock Entry)."""

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


class IneligibilityReasonExt:
    """Resolves the virtual ``ineligibility_reason`` field (Purchase Receipt).

    On Purchase Invoice this field is stored, so it is not extended here.
    """

    @property
    def ineligibility_reason(self):
        return get_ineligibility_reason(self)
