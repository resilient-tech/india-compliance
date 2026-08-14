"""GST controller for transactions that carry estimated taxes rather than an invoice.

Subcontracting Order / Receipt, Stock Entry and Asset Movement compute GST for e-Waybill
and ITC-04 reporting without posting it to the GL, and share the same bill-from / bill-to
machinery. Each subclass supplies only what differs, so supporting a new doctype is a
subclass rather than another `doc.doctype ==` branch.

Subclasses live in their doctype's own `overrides/` module, which stays a thin hook wrapper.
"""

import frappe
from frappe import _, bold

from india_compliance.gst_india.constants import DOCTYPES_WITH_BILL_FROM_TO
from india_compliance.gst_india.overrides.transaction import (
    GSTAccounts,
    ignore_gst_validations,
    set_gst_tax_type,
    validate_gst_category,
    validate_gst_transporter_id,
    validate_gstin_status,
    validate_items,
    validate_mandatory_fields,
    validate_place_of_supply,
)
from india_compliance.gst_india.utils import (
    get_place_of_supply,
    is_api_enabled,
    is_inward_transaction,
    is_same_gstin_allowed,
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.utils import (
    validate_invoice_number as validate_transaction_name,
)
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import (
    CustomTaxController,
    update_gst_details,
    validate_taxes,
)

SUBCONTRACTING_ORDER_RECEIPT_FIELD_MAP = {"total_taxable_value": "total"}


def get_field_map(doc):
    """Where the company and the party sit on this doctype.

    Doctypes with bill_from / bill_to swap sides by direction; the rest bill the supplier
    from a fixed set of fields.
    """
    if doc.doctype not in DOCTYPES_WITH_BILL_FROM_TO:
        return frappe._dict(
            company_gstin_field="company_gstin",
            party_gstin_field="supplier_gstin",
            company_address_field="billing_address",
            gst_category_field="gst_category",
        )

    if is_inward_transaction(doc):
        return frappe._dict(
            company_gstin_field="bill_to_gstin",
            party_gstin_field="bill_from_gstin",
            company_address_field="bill_to_address",
            gst_category_field="bill_from_gst_category",
        )

    return frappe._dict(
        company_gstin_field="bill_from_gstin",
        party_gstin_field="bill_to_gstin",
        company_address_field="bill_from_address",
        gst_category_field="bill_to_gst_category",
    )


class GSTTransactionController:
    DOCTYPE = None
    TAXES_FIELD_MAP = SUBCONTRACTING_ORDER_RECEIPT_FIELD_MAP

    # GST caps the document number at 16 alphanumeric characters. Only enforced where the
    # number is actually reported to the portal.
    VALIDATES_TRANSACTION_NAME = False

    GST_LOG_DOCTYPES = ("e-Waybill Log", "Integration Request")

    def __init__(self, doc):
        self.doc = doc

    @classmethod
    def get_dashboard_data(cls, data):
        return update_dashboard_with_gst_logs(cls.DOCTYPE, data, *cls.GST_LOG_DOCTYPES)

    def set_e_waybill_info(self):
        if not self.doc.get("ewaybill"):
            return

        gst_settings = frappe.get_cached_doc("GST Settings")

        if not (
            self.is_e_waybill_applicable()
            or (
                is_api_enabled(gst_settings)
                and gst_settings.enable_e_waybill
                and gst_settings.auto_cancel_e_waybill
            )
        ):
            return

        if e_waybill_info := get_e_waybill_info(self.doc):
            self.doc.set_onload("e_waybill_info", e_waybill_info)

    def is_e_waybill_applicable(self):
        gst_settings = frappe.get_cached_doc("GST Settings")

        return bool(gst_settings.enable_api and gst_settings.enable_e_waybill)

    def ignore_gst_validations(self):
        return bool(ignore_gst_validations(self.doc))

    @property
    def field_map(self):
        return get_field_map(self.doc)

    def set_fields(self):
        "set any doc field values that are needed for GST validation"
        pass

    def validate(self):
        tax_controller = CustomTaxController(self.doc, self.TAXES_FIELD_MAP)

        if self.ignore_gst_validations():
            tax_controller.set_taxes_and_totals()
            return

        if not self.is_e_waybill_applicable():
            tax_controller.set_taxes_and_totals()
            return

        self.set_fields()
        tax_controller.set_taxes_and_totals()

        if self.VALIDATES_TRANSACTION_NAME:
            validate_transaction_name(self.doc)

        set_gst_tax_type(self.doc)
        validate_taxes(self.doc)

        if self.validate_gst_details() is False:
            return

        update_gst_details(self.doc)

    def before_save(self):
        if not self.is_e_waybill_applicable():
            self.doc.taxes_and_charges = ""
            self.doc.taxes = []
            return

        for row in self.doc.taxes:
            if row.charge_type == "Actual":
                frappe.throw(
                    _(
                        "Tax Row #{0}: Charge Type cannot be {1}."
                        " Try setting it to 'On Net Total' or 'On Item Quantity'."
                    ).format(row.idx, bold(row.charge_type))
                )

    def validate_gst_details(self):
        doc = self.doc
        validate_items(doc)

        field_map = self.field_map
        company_gstin_field = field_map.company_gstin_field
        party_gstin_field = field_map.party_gstin_field
        company_address_field = field_map.company_address_field
        gst_category_field = field_map.gst_category_field

        if doc.place_of_supply:
            validate_place_of_supply(doc)
        else:
            doc.place_of_supply = get_place_of_supply(doc, doc.doctype)

        if self.validate_company_address_field(company_address_field) is False:
            return False

        if validate_mandatory_fields(doc, (company_gstin_field, "place_of_supply")) is False:
            return False

        if getattr(doc, company_address_field) and (
            validate_mandatory_fields(
                doc,
                gst_category_field,
                _(
                    "{0} is a mandatory field for GST Transactions. Please ensure that"
                    " it is set in the Party and / or Address."
                ),
            )
            is False
        ):
            return False

        elif not doc.get(gst_category_field):
            setattr(doc, gst_category_field, "Unregistered")

        gstin = getattr(doc, party_gstin_field)

        validate_gstin_status(gstin, doc)
        validate_gst_transporter_id(doc)
        validate_gst_category(doc.get(gst_category_field), gstin)

        CustomGSTAccounts(doc, self.field_map).validate(True)

    def validate_company_address_field(self, company_address_field):
        if (
            validate_mandatory_fields(
                self.doc,
                company_address_field,
                _("Please set {0} to ensure Company GSTIN is fetched in the transaction.").format(
                    bold(self.doc.meta.get_label(company_address_field))
                ),
            )
            is False
        ):
            return False


class CustomGSTAccounts(GSTAccounts):
    def __init__(self, doc, field_map=None):
        super().__init__(doc)
        self.field_map = field_map or get_field_map(doc)

    def validate(self, is_sales_transaction=False):
        self.is_sales_transaction = is_sales_transaction

        if not self.doc.taxes:
            return

        if not self.has_gst_tax_rows():
            return

        self.setup_defaults()

        self.validate_invalid_account_for_transaction()  # Sales / Purchase
        self.validate_for_same_party_gstin()
        self.validate_for_invalid_account_type()  # CGST / SGST / IGST
        self.validate_for_charge_type()

    def validate_for_same_party_gstin(self):
        if is_same_gstin_allowed(self.doc):
            return

        company_gstin = self.doc.get(self.field_map.company_gstin_field)
        party_gstin = self.doc.get(self.field_map.party_gstin_field)

        if not party_gstin or company_gstin != party_gstin:
            return

        self._throw(
            _("Cannot charge GST in Row #{0} since Bill From GSTIN and Bill To GSTIN are same").format(
                self.first_gst_idx
            )
        )

    def validate_for_charge_type(self):
        for row in self.gst_tax_rows:
            # validating charge type "On Item Quantity" and non_cess_advol_account
            self.validate_charge_type_for_cess_non_advol_accounts(row)
