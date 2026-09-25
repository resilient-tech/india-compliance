"""Whether a saved document can carry an e-Waybill, and the reasons it cannot."""

import frappe
from frappe import _

from india_compliance.gst_india.constants import (
    E_WAYBILL_STOCK_ENTRY_PURPOSES,
    SERVICE_HSN_PREFIX,
)
from india_compliance.gst_india.constants.e_waybill import ADDRESS_FIELDS, PERMITTED_DOCTYPES
from india_compliance.gst_india.overrides.transaction import _get_address_fields
from india_compliance.gst_india.utils import (
    get_items,
    is_api_enabled,
    is_same_gstin_allowed,
)


class EWaybillApplicability:
    # GST Settings switch needed on top of enable_e_waybill
    SWITCH = "enable_e_waybill"
    SAME_GSTIN_ALLOWED = False

    def __init__(self, doc):
        self.doc = doc
        self.settings = frappe.get_cached_doc("GST Settings")
        self.fields = _get_address_fields(doc.doctype, doc)

    def get(self):
        applicability = frappe._dict(
            api_enabled=self.is_api_enabled(),
            applicable=False,
            generatable=False,
            reasons=[],
        )

        if not self.is_enabled():
            return applicability

        applicability.reasons = self.get_applicability_reasons()
        applicability.applicable = not applicability.reasons

        generation_reasons = self.get_generation_reasons()
        applicability.generatable = applicability.applicable and not generation_reasons
        applicability.reasons.extend(generation_reasons)

        return applicability

    def is_enabled(self):
        return bool(self.settings.enable_e_waybill and self.settings.get(self.SWITCH))

    def is_api_enabled(self):
        return bool(self.settings.enable_api and self.is_enabled())

    def is_info_enabled(self):
        # an existing e-Waybill stays visible for auto-cancel even when this doctype's switch is off
        return bool(
            is_api_enabled(self.settings)
            and (
                self.is_enabled() or (self.settings.enable_e_waybill and self.settings.auto_cancel_e_waybill)
            )
        )

    def get_applicability_reasons(self):
        reasons = []

        if self.doc.get("is_opening") == "Yes":
            reasons.append(
                _("e-Waybill cannot be generated for transaction with 'Is Opening Entry' set to Yes.")
            )

        if not self.has_goods_item():
            reasons.append(_("e-Waybill cannot be generated because all items have service HSN codes"))

        if self.has_same_gstin():
            reasons.append(_("e-Waybill cannot be generated because party GSTIN is same as company GSTIN"))

        return reasons

    def get_generation_reasons(self):
        return self.get_company_gstin_reasons() + self.get_address_reasons()

    def has_goods_item(self):
        return any(
            item.gst_hsn_code and not item.gst_hsn_code.startswith(SERVICE_HSN_PREFIX)
            for item in get_items(self.doc)
        )

    def has_same_gstin(self):
        if self.SAME_GSTIN_ALLOWED or is_same_gstin_allowed(self.doc):
            return False

        return self.doc.get(self.fields.company_gstin_field) == self.doc.get(self.fields.party_gstin_field)

    def get_company_gstin_reasons(self):
        if self.doc.get(self.fields.company_gstin_field):
            return []

        return [
            _("{0} is not set. Ensure it's set in the Company Address.").format(
                _(self.doc.meta.get_label(self.fields.company_gstin_field))
            )
        ]

    def get_address_reasons(self):
        address = ADDRESS_FIELDS[self.doc.doctype]

        return [
            _("{0} is required to generate e-Waybill").format(_(self.doc.meta.get_label(address[key])))
            for key in ("bill_from", "bill_to")
            if not self.doc.get(address[key])
        ]


class PurchaseInvoiceApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_pi"

    def get_generation_reasons(self):
        reasons = super().get_generation_reasons()

        if not self.doc.is_return and not self.doc.bill_no and self.doc.gst_category != "Unregistered":
            reasons.append(_("Bill No is mandatory to generate e-Waybill for Purchase Invoice"))

        return reasons


class PurchaseReceiptApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_pr"


class DeliveryNoteApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_dn"
    SAME_GSTIN_ALLOWED = True


class StockEntryApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_for_sc"

    def is_enabled(self):
        # Inward purposes (Delivery, RM Return) carry only an e-Waybill; the
        # principal reports them in ITC-04 / GSTR-1, not the company (job worker).
        return super().is_enabled() and self.doc.purpose in E_WAYBILL_STOCK_ENTRY_PURPOSES


class AssetMovementApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_asset_movement"


class SubcontractingOrderApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_for_sc"


class SubcontractingReceiptApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_for_sc"


E_WAYBILL_APPLICABILITY = {
    "Sales Invoice": EWaybillApplicability,
    "Purchase Invoice": PurchaseInvoiceApplicability,
    "Purchase Receipt": PurchaseReceiptApplicability,
    "Delivery Note": DeliveryNoteApplicability,
    "Stock Entry": StockEntryApplicability,
    "Asset Movement": AssetMovementApplicability,
    "Subcontracting Order": SubcontractingOrderApplicability,
    "Subcontracting Receipt": SubcontractingReceiptApplicability,
}


def set_e_waybill_applicability(doc, method=None):
    e_waybill_applicability = E_WAYBILL_APPLICABILITY[doc.doctype](doc)

    # the client reads a missing key as all flags off
    if not e_waybill_applicability.is_enabled():
        return

    applicability = e_waybill_applicability.get()
    applicability.pop("reasons")

    doc.set_onload("e_waybill_applicability", applicability)


@frappe.whitelist()
def get_e_waybill_applicability_reasons(doctype: str, docname: str):
    if doctype not in PERMITTED_DOCTYPES:
        frappe.throw(_("e-Waybill is not supported for {0}").format(_(doctype)))

    doc = frappe.get_lazy_doc(doctype, docname, check_permission="read")

    return E_WAYBILL_APPLICABILITY[doctype](doc).get().reasons
