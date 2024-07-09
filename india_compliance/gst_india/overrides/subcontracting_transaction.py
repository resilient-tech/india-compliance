import frappe
from frappe import _, bold

from india_compliance.gst_india.overrides.transaction import (
    DOCTYPES_WITH_GST_DETAIL,
    GSTAccounts,
    ignore_gst_validations,
    set_gst_tax_type,
    update_taxable_values,
    validate_ecommerce_gstin,
    validate_gst_category,
    validate_gst_transporter_id,
    validate_gstin_status,
    validate_item_wise_tax_detail,
    validate_items,
    validate_mandatory_fields,
    validate_overseas_gst_category,
    validate_place_of_supply,
    validate_reverse_charge_transaction,
    validate_transaction,
)
from india_compliance.gst_india.utils import get_state, is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import (
    CustomTaxController,
    update_gst_details,
    validate_taxes,
)

STOCK_ENTRY_FIELD_MAP = {"total_taxable_value": "total_taxable_value"}
SUBCONTRACTING_ORDER_RECEIPT_FIELD_MAP = {"total_taxable_value": "total"}


def onload(doc, method=None):
    if not doc.get("ewaybill"):
        return

    gst_settings = frappe.get_cached_doc("GST Settings")

    if not (
        is_api_enabled(gst_settings)
        and gst_settings.enable_e_waybill
        and gst_settings.enable_e_waybill_for_sc
    ):
        return

    doc.set_onload("e_waybill_info", get_e_waybill_info(doc))


def validate(doc, method=None):
    if ignore_gst_validations(doc):
        return

    field_map = (
        STOCK_ENTRY_FIELD_MAP
        if doc.doctype == "Stock Entry"
        else SUBCONTRACTING_ORDER_RECEIPT_FIELD_MAP
    )
    CustomTaxController(doc, field_map).set_taxes_and_totals()

    set_gst_tax_type(doc)
    validate_taxes(doc)
    if doc.doctype == "Stock Entry":
        validate_stock_entry_transaction(doc)
    else:
        validate_transaction(doc)
    update_gst_details(doc)


def validate_stock_entry_transaction(doc, method=None):
    if ignore_gst_validations(doc):
        return False

    validate_items(doc)

    if doc.place_of_supply:
        validate_place_of_supply(doc)
    else:
        doc.place_of_supply = get_place_of_supply(doc)

    if validate_billing_address_field(doc) is False:
        return False

    if validate_mandatory_fields(doc, ("bill_from_gstin", "place_of_supply")) is False:
        return False

    if (
        validate_mandatory_fields(
            doc,
            "gst_category",
            _(
                "{0} is a mandatory field for GST Transactions. Please ensure that"
                " it is set in the Party and / or Address."
            ),
        )
        is False
    ):
        return False

    elif not doc.gst_category:
        doc.gst_category = "Unregistered"

    validate_overseas_gst_category(doc)

    is_sales_transaction = True
    gstin = doc.bill_to_gstin

    validate_gstin_status(gstin, doc.get("posting_date") or doc.get("transaction_date"))
    validate_gst_transporter_id(doc)
    validate_ecommerce_gstin(doc)

    validate_gst_category(doc.gst_category, gstin)

    StockEntryGSTAccounts().validate(doc, is_sales_transaction)
    validate_reverse_charge_transaction(doc)
    update_taxable_values(doc)
    validate_item_wise_tax_detail(doc)


def get_place_of_supply(party_details):
    """
    :param party_details: A frappe._dict or document containing fields related to party
    """

    party_gstin = party_details.bill_to_gstin or party_details.bill_from_gstin

    if not party_gstin:
        return

    state_code = party_gstin[:2]

    if state := get_state(state_code):
        return f"{state_code}-{state}"


def validate_billing_address_field(doc):
    if doc.doctype not in DOCTYPES_WITH_GST_DETAIL:
        return

    billing_address_field = "bill_from_address"

    if (
        validate_mandatory_fields(
            doc,
            billing_address_field,
            _(
                "Please set {0} to ensure Bill From GSTIN is fetched in the transaction."
            ).format(bold(doc.meta.get_label(billing_address_field))),
        )
        is False
    ):
        return False


class StockEntryGSTAccounts(GSTAccounts):
    def validate(self, doc, is_sales_transaction=False):
        self.doc = doc
        self.is_sales_transaction = is_sales_transaction

        if not self.doc.taxes:
            return

        if not self.has_gst_tax_rows():
            return

        self.setup_defaults()

        self.validate_invalid_account_for_transaction()  # Sales / Purchase
        self.validate_for_same_party_gstin()
        self.validate_reverse_charge_accounts()
        self.validate_sales_transaction()
        self.validate_purchase_transaction()
        self.validate_for_invalid_account_type()  # CGST / SGST / IGST
        self.validate_for_charge_type()
        self.validate_missing_accounts_in_item_tax_template()

        return

    def validate_for_same_party_gstin(self):
        bill_to_gstin = self.doc.get("bill_to_gstin")

        if not bill_to_gstin or self.doc.bill_from_gstin != bill_to_gstin:
            return

        self._throw(
            _(
                "Cannot charge GST in Row #{0} since Bill From GSTIN and Bill To GSTIN are"
                " same"
            ).format(self.first_gst_idx)
        )

    def validate_for_invalid_account_type(self):
        super().validate_for_invalid_account_type(is_inter_state_supply(self.doc))


def is_inter_state_supply(doc):
    return doc.gst_category == "SEZ" or (
        doc.place_of_supply[:2] != get_source_state_code(doc)
    )


def get_source_state_code(doc):
    return (doc.bill_from_gstin or doc.bill_to_gstin)[:2]
