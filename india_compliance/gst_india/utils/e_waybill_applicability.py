"""Whether a saved document can carry an e-Waybill, and the reasons it cannot."""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime

from india_compliance.gst_india.constants import (
    E_WAYBILL_STOCK_ENTRY_PURPOSES,
    STATE_NUMBERS,
)
from india_compliance.gst_india.constants.e_waybill import ADDRESS_FIELDS, PERMITTED_DOCTYPES
from india_compliance.gst_india.overrides.transaction import (
    _get_address_fields,
    get_source_state_code,
    is_inter_state_supply,
)
from india_compliance.gst_india.utils import (
    are_goods_supplied,
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
            applicable=self.is_applicable(),
            generatable=self.is_generatable(),
            required=self.is_required(),
            cancellable=self.is_cancellable(),
            reasons=[],
        )

        if self.is_enabled():
            applicability.reasons = self.get_applicability_reasons() + self.get_generation_reasons()

        return applicability

    def is_enabled(self):
        return bool(self.settings.enable_e_waybill and self.settings.get(self.SWITCH))

    def is_api_enabled(self):
        return bool(self.settings.enable_api and self.is_enabled())

    def is_applicable(self):
        return self.is_enabled() and not self.get_applicability_reasons()

    def is_generatable(self):
        return self.is_applicable() and not self.get_generation_reasons()

    def is_required(self):
        consignment_value = self.get_consignment_value()
        if consignment_value is None or self.doc.get("ewaybill") or not self.is_applicable():
            return False

        threshold = _get_e_waybill_threshold(self.doc, self.settings)
        return threshold is not None and abs(consignment_value) >= threshold

    def get_consignment_value(self):
        # None where the e-Waybill threshold is not checked
        return None

    def is_auto_generatable(self):
        return False

    def is_info_enabled(self):
        # the doctype switch governs new e-Waybills; an existing one stays manageable
        return bool(self.settings.enable_e_waybill and is_api_enabled(self.settings))

    def is_cancellable(self, e_waybill_info=None):
        if not (self.doc.get("ewaybill") and self.is_info_enabled()):
            return False

        e_waybill_info = e_waybill_info or self.doc.get_onload().get("e_waybill_info") or {}
        generated_on = e_waybill_info.get("created_on")

        # the portal allows cancelling for 24 hours after generation
        return bool(generated_on) and add_days(generated_on, 1) >= get_datetime()

    def is_auto_cancellable(self, e_waybill_info=None):
        return bool(self.settings.auto_cancel_e_waybill) and self.is_cancellable(e_waybill_info)

    def get_applicability_reasons(self):
        reasons = []

        if self.doc.get("is_opening") == "Yes":
            reasons.append(
                _("e-Waybill cannot be generated for transaction with 'Is Opening Entry' set to Yes.")
            )

        if not are_goods_supplied(self.doc):
            reasons.append(_("e-Waybill cannot be generated because all items have service HSN codes"))

        if self.has_same_gstin():
            reasons.append(_("e-Waybill cannot be generated because party GSTIN is same as company GSTIN"))

        return reasons

    def get_generation_reasons(self):
        return self.get_company_gstin_reasons() + self.get_address_reasons()

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


class SalesInvoiceApplicability(EWaybillApplicability):
    def get_consignment_value(self):
        return self.doc.base_grand_total

    def is_auto_generatable(self):
        return bool(
            self.settings.auto_generate_e_waybill
            and is_api_enabled(self.settings)
            and self.doc.e_waybill_status == "Pending"
            and not (self.doc.is_return or self.doc.is_debit_note)
        )


class PurchaseInvoiceApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_pi"

    def get_consignment_value(self):
        return self.doc.base_grand_total

    def get_generation_reasons(self):
        reasons = super().get_generation_reasons()

        if not self.doc.is_return and not self.doc.bill_no and self.doc.gst_category != "Unregistered":
            reasons.append(_("Bill No is mandatory to generate e-Waybill for Purchase Invoice"))

        return reasons


class PurchaseReceiptApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_pr"

    def get_consignment_value(self):
        return self.doc.base_grand_total


class DeliveryNoteApplicability(EWaybillApplicability):
    SWITCH = "enable_e_waybill_from_dn"
    SAME_GSTIN_ALLOWED = True

    def get_consignment_value(self):
        return self.doc.base_grand_total


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
    "Sales Invoice": SalesInvoiceApplicability,
    "Purchase Invoice": PurchaseInvoiceApplicability,
    "Purchase Receipt": PurchaseReceiptApplicability,
    "Delivery Note": DeliveryNoteApplicability,
    "Stock Entry": StockEntryApplicability,
    "Asset Movement": AssetMovementApplicability,
    "Subcontracting Order": SubcontractingOrderApplicability,
    "Subcontracting Receipt": SubcontractingReceiptApplicability,
}


def get_e_waybill_applicability(doc):
    return E_WAYBILL_APPLICABILITY[doc.doctype](doc)


def is_e_waybill_enabled(doc):
    return get_e_waybill_applicability(doc).is_enabled()


def is_e_waybill_api_enabled(doc):
    return get_e_waybill_applicability(doc).is_api_enabled()


def is_e_waybill_applicable(doc):
    return get_e_waybill_applicability(doc).is_applicable()


def is_e_waybill_generatable(doc):
    return get_e_waybill_applicability(doc).is_generatable()


def is_e_waybill_required(doc):
    return get_e_waybill_applicability(doc).is_required()


def is_e_waybill_auto_generatable(doc):
    return get_e_waybill_applicability(doc).is_auto_generatable()


def is_e_waybill_info_enabled(doc):
    return get_e_waybill_applicability(doc).is_info_enabled()


def is_e_waybill_cancellable(doc, e_waybill_info=None):
    return get_e_waybill_applicability(doc).is_cancellable(e_waybill_info)


def is_e_waybill_auto_cancellable(doc, e_waybill_info=None):
    return get_e_waybill_applicability(doc).is_auto_cancellable(e_waybill_info)


def set_e_waybill_applicability(doc, method=None):
    e_waybill_applicability = get_e_waybill_applicability(doc)

    # the client reads a missing key as all flags off
    if not (e_waybill_applicability.is_enabled() or doc.get("ewaybill")):
        return

    applicability = e_waybill_applicability.get()
    applicability.pop("reasons")

    doc.set_onload("e_waybill_applicability", applicability)


@frappe.whitelist()
def get_e_waybill_applicability_reasons(doctype: str, docname: str):
    if doctype not in PERMITTED_DOCTYPES:
        frappe.throw(_("e-Waybill is not supported for {0}").format(_(doctype)))

    doc = frappe.get_lazy_doc(doctype, docname, check_permission="read")

    return get_e_waybill_applicability(doc).get().reasons


def _get_e_waybill_threshold(doc, gst_settings=None):
    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    if is_inter_state_supply(doc):
        return gst_settings.e_waybill_threshold

    return get_intrastate_threshold(doc, gst_settings)


def get_intrastate_threshold(doc, gst_settings=None):
    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    state = get_source_state_code(doc)

    state_config = get_state_code_wise_config(gst_settings)

    if state in state_config:
        config = state_config[state]
        if not config.get("intrastate_applicable"):
            return None

        return config.get("intrastate_threshold")

    return gst_settings.e_waybill_threshold


def get_state_code_wise_config(gst_settings=None):
    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    state_config = {}
    for row in gst_settings.get("e_waybill_threshold_for_intrastate") or []:
        if not (state_code := STATE_NUMBERS.get(row.state)):
            continue

        state_config[state_code] = {
            "intrastate_applicable": row.intrastate_applicable,
            "intrastate_threshold": row.intrastate_threshold,
        }

    return state_config
