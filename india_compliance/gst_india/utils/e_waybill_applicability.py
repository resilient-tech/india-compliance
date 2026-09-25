"""Whether a saved document can carry an e-Waybill, and the reasons it cannot."""

import frappe
from frappe import _

from india_compliance.gst_india.constants import (
    E_WAYBILL_STOCK_ENTRY_PURPOSES,
    SERVICE_HSN_PREFIX,
)
from india_compliance.gst_india.utils import (
    get_items,
    is_inward_transaction,
    is_same_gstin_allowed,
    load_doc,
)


class EWaybillApplicability:
    # GST Settings switch needed on top of enable_e_waybill
    SWITCH = None

    def __init__(self, doc):
        self.doc = doc
        self.settings = frappe.get_cached_doc("GST Settings")

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
        return bool(self.settings.enable_e_waybill and (not self.SWITCH or self.settings.get(self.SWITCH)))

    def is_api_enabled(self):
        return bool(self.settings.enable_api and self.is_enabled())

    def get_applicability_reasons(self):
        reasons = self.get_company_gstin_reasons()

        if self.doc.get("is_opening") == "Yes":
            reasons.append(
                _("e-Waybill cannot be generated for transaction with 'Is Opening Entry' set to Yes.")
            )

        return reasons + self.get_goods_reasons()

    def get_company_gstin_reasons(self):
        if self.doc.company_gstin:
            return []

        return [_("Company GSTIN is not set. Ensure it's set in Company Address.")]

    def get_goods_reasons(self):
        for item in get_items(self.doc):
            if item.gst_hsn_code and not item.gst_hsn_code.startswith(SERVICE_HSN_PREFIX) and item.qty != 0:
                return []

        return [_("All items are service items (HSN code starts with 99).")]

    def get_generation_reasons(self):
        return []


class SalesInvoiceApplicability(EWaybillApplicability):
    def get_generation_reasons(self):
        reasons = []

        if not self.doc.customer_address:
            reasons.append(_("Customer Address is mandatory to generate e-Waybill."))

        if self.doc.company_gstin == self.doc.billing_address_gstin:
            reasons.append(_("Company GSTIN and Billing Address GSTIN are same."))

        return reasons


class PurchaseInvoiceApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_pi"

    def get_generation_reasons(self):
        reasons = []

        if not self.doc.supplier_address:
            reasons.append(_("Supplier Address is mandatory to generate e-Waybill."))

        if self.doc.company_gstin == self.doc.supplier_gstin:
            reasons.append(_("Company GSTIN and Supplier GSTIN are same."))

        return reasons


class PurchaseReceiptApplicability(PurchaseInvoiceApplicability):
    SWITCH = "enable_e_waybill_from_pr"


class DeliveryNoteApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_dn"

    def get_generation_reasons(self):
        if self.doc.customer_address:
            return []

        return [_("Customer Address is mandatory to generate e-Waybill.")]


class StockEntryApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_for_sc"

    def is_enabled(self):
        # Inward purposes (Delivery, RM Return) carry only an e-Waybill; the
        # principal reports them in ITC-04 / GSTR-1, not the company (job worker).
        return super().is_enabled() and self.doc.purpose in E_WAYBILL_STOCK_ENTRY_PURPOSES

    def get_company_gstin_reasons(self):
        reasons = []

        if is_inward_transaction(self.doc):
            if not self.doc.bill_to_gstin:
                reasons.append(_("Bill To GSTIN is not set. Ensure it's set in Bill To Address."))

        elif not self.doc.bill_from_gstin:
            reasons.append(_("Bill From GSTIN is not set. Ensure it's set in Bill From Address."))

        if self.doc.bill_from_gstin == self.doc.bill_to_gstin and not is_same_gstin_allowed(self.doc):
            reasons.append(_("Bill From GSTIN and Bill To GSTIN are same."))

        return reasons

    def get_generation_reasons(self):
        if self.doc.bill_to_address:
            return []

        return [_("Bill To address is mandatory to generate e-Waybill.")]


class AssetMovementApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_asset_movement"

    def get_applicability_reasons(self):
        return self.get_company_gstin_reasons() + self.get_goods_reasons()

    def get_company_gstin_reasons(self):
        gstin_field, label = (
            ("bill_to_gstin", "Bill To")
            if is_inward_transaction(self.doc)
            else ("bill_from_gstin", "Bill From")
        )

        if self.doc.get(gstin_field):
            return []

        return [f"{label} GSTIN is not set. Ensure its set in {label} Address."]

    def get_generation_reasons(self):
        address_field, label = (
            ("bill_from_address", "Bill From")
            if is_inward_transaction(self.doc)
            else ("bill_to_address", "Bill To")
        )

        if self.doc.get(address_field):
            return []

        return [f"{label} address is mandatory to generate e-Waybill."]


class SubcontractingOrderApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_for_sc"


class SubcontractingReceiptApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_for_sc"

    def get_generation_reasons(self):
        if self.doc.supplier_address:
            return []

        return [_("Supplier address is mandatory for e-waybill generation.")]


E_WAYBILL_APPLICABILITY = {
    "Sales Invoice": SalesInvoiceApplicability,
    "Purchase Invoice": PurchaseInvoiceApplicability,
    "Purchase Receipt": PurchaseReceiptApplicability,
    "Delivery Note": DeliveryNoteApplicability,
    "Stock Entry": StockEntryApplicability,
    "Asset Movement": AssetMovementApplicability,
    "Subcontracting Order": SubcontractingOrderApplicability,
    "Subcontracting Receipt": SubcontractingReceiptApplicability,
}


def set_e_waybill_applicability(doc, method=None):
    applicability = E_WAYBILL_APPLICABILITY[doc.doctype](doc).get()
    applicability.pop("reasons")

    doc.set_onload("e_waybill_applicability", applicability)


@frappe.whitelist()
def get_e_waybill_applicability_reasons(doctype: str, docname: str):
    if doctype not in E_WAYBILL_APPLICABILITY:
        frappe.throw(_("e-Waybill is not supported for {0}").format(_(doctype)))

    return E_WAYBILL_APPLICABILITY[doctype](load_doc(doctype, docname)).get().reasons
