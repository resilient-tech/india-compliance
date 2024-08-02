from pypika import Order

import frappe
from frappe import _, bold
from frappe.contacts.doctype.address.address import get_address_display
from frappe.utils import flt
from erpnext.accounts.party import get_address_tax_category
from erpnext.stock.get_item_details import get_item_tax_template

from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.overrides.transaction import (
    GSTAccounts,
    get_place_of_supply,
    ignore_gst_validations,
    is_inter_state_supply,
    set_gst_tax_type,
    validate_gst_category,
    validate_gst_transporter_id,
    validate_gstin_status,
    validate_items,
    validate_mandatory_fields,
    validate_place_of_supply,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type, is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import (
    CustomTaxController,
    update_gst_details,
    validate_taxes,
)

STOCK_ENTRY_FIELD_MAP = {"total_taxable_value": "total_taxable_value"}
SUBCONTRACTING_ORDER_RECEIPT_FIELD_MAP = {"total_taxable_value": "total"}


def after_mapping_subcontracting_order(doc, method, source_doc):
    if source_doc.doctype != "Purchase Order":
        return

    doc.taxes_and_charges = ""
    doc.taxes = []

    if ignore_gst_validations(doc):
        return

    set_taxes(doc)

    if not doc.items:
        return

    tax_category = source_doc.tax_category

    if not tax_category:
        tax_category = get_address_tax_category(
            frappe.db.get_value("Supplier", source_doc.supplier, "tax_category"),
            source_doc.supplier_address,
        )

    args = {"company": doc.company, "tax_category": tax_category}

    for item in doc.items:
        out = {}
        item_doc = frappe.get_cached_doc("Item", item.item_code)
        get_item_tax_template(args, item_doc, out)
        item.item_tax_template = out.get("item_tax_template")


def after_mapping_stock_entry(doc, method, source_doc):
    if source_doc.doctype == "Subcontracting Order":
        return

    doc.taxes_and_charges = ""
    doc.taxes = []


def set_taxes(doc):
    accounts = get_gst_accounts_by_type(doc.company, "Output", throw=False)
    if not accounts:
        return

    sales = frappe.qb.DocType("Sales Taxes and Charges")
    sales_template = frappe.qb.DocType("Sales Taxes and Charges Template")

    rate = (
        frappe.qb.from_(sales)
        .left_join(sales_template)
        .on(sales_template.name == sales.parent)
        .select(sales.rate or 0)
        .where(sales.parenttype == "Sales Taxes and Charges Template")
        .where(sales.account_head == accounts.get("igst_account"))
        .where(sales_template.disabled == 0)
        .orderby(sales_template.is_default, order=Order.desc)
        .run(pluck=True)
    )[0]

    tax_types = ("igst",)
    if not is_inter_state_supply(doc):
        tax_types = ("cgst", "sgst")
        rate = flt(rate / 2)

    for tax_type in tax_types:
        account = accounts.get(tax_type + "_account")
        doc.append(
            "taxes",
            {
                "charge_type": "On Net Total",
                "account_head": account,
                "rate": rate,
                "gst_tax_type": tax_type,
                "description": account,
            },
        )


def get_dashboard_data(data):
    doctype = (
        "Subcontracting Receipt"
        if data.fieldname == "subcontracting_receipt"
        else "Stock Entry"
    )
    return update_dashboard_with_gst_logs(
        doctype,
        data,
        "e-Waybill Log",
        "Integration Request",
    )


def onload(doc, method=None):
    if doc.doctype == "Stock Entry":
        set_address_display(doc)

        # For e-Waybill data mapping
        doc.company_gstin = doc.bill_from_gstin
        doc.supplier_gstin = doc.bill_to_gstin
        doc.gst_category = doc.bill_to_gst_category

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
    if ignore_gst_validation_for_subcontracting(doc):
        return

    field_map = (
        STOCK_ENTRY_FIELD_MAP
        if doc.doctype == "Stock Entry"
        else SUBCONTRACTING_ORDER_RECEIPT_FIELD_MAP
    )
    CustomTaxController(doc, field_map).set_taxes_and_totals()

    set_gst_tax_type(doc)
    validate_taxes(doc)

    if validate_transaction(doc) is False:
        return

    update_gst_details(doc)


def validate_transaction(doc, method=None):
    validate_items(doc)

    if doc.doctype == "Stock Entry":
        company_gstin_field = "bill_from_gstin"
        party_gstin_field = "bill_to_gstin"
        company_address_field = "bill_from_address"
        gst_category_field = "bill_to_gst_category"
    else:
        company_gstin_field = "company_gstin"
        party_gstin_field = "supplier_gstin"
        company_address_field = "billing_address"
        gst_category_field = "gst_category"

    if doc.place_of_supply:
        validate_place_of_supply(doc)
    else:
        doc.place_of_supply = get_place_of_supply(doc, doc.doctype)

    if validate_company_address_field(doc, company_address_field) is False:
        return False

    if (
        validate_mandatory_fields(doc, (company_gstin_field, "place_of_supply"))
        is False
    ):
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

    validate_gstin_status(gstin, doc.get("posting_date") or doc.get("transaction_date"))
    validate_gst_transporter_id(doc)
    validate_gst_category(doc.get(gst_category_field), gstin)

    SubcontractingGSTAccounts().validate(doc, True)


def validate_company_address_field(doc, company_address_field):
    if (
        validate_mandatory_fields(
            doc,
            company_address_field,
            _(
                "Please set {0} to ensure Bill From GSTIN is fetched in the transaction."
            ).format(bold(doc.meta.get_label(company_address_field))),
        )
        is False
    ):
        return False


class SubcontractingGSTAccounts(GSTAccounts):
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
        self.validate_for_invalid_account_type()  # CGST / SGST / IGST
        self.validate_for_charge_type()

    def validate_for_same_party_gstin(self):
        company_gstin = self.doc.get("company_gstin") or self.doc.bill_from_gstin
        party_gstin = self.doc.get("supplier_gstin") or self.doc.bill_to_gstin

        if not party_gstin or company_gstin != party_gstin:
            return

        self._throw(
            _(
                "Cannot charge GST in Row #{0} since Bill From GSTIN and Bill To GSTIN are"
                " same"
            ).format(self.first_gst_idx)
        )

    def validate_for_charge_type(self):
        for row in self.gst_tax_rows:
            # validating charge type "On Item Quantity" and non_cess_advol_account
            self.validate_charge_type_for_cess_non_advol_accounts(row)


def ignore_gst_validation_for_subcontracting(doc):
    if doc.doctype == "Stock Entry" and doc.purpose != "Send to Subcontractor":
        return True

    return ignore_gst_validations(doc)


def set_address_display(doc):
    adddress_fields = (
        "bill_from_address",
        "bill_to_address",
        "ship_from_address",
        "ship_to_address",
    )

    for address in adddress_fields:
        if doc.get(address):
            setattr(doc, address + "_display", get_address_display(doc.get(address)))
