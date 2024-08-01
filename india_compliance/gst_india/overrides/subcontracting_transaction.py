import frappe
from frappe import _, bold
from frappe.contacts.doctype.address.address import get_address_display

from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.overrides.transaction import (
    GSTAccounts,
    get_place_of_supply,
    ignore_gst_validations,
    set_gst_tax_type,
    validate_gst_category,
    validate_gst_transporter_id,
    validate_gstin_status,
    validate_items,
    validate_mandatory_fields,
    validate_place_of_supply,
)
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import (
    CustomTaxController,
    update_gst_details,
    validate_taxes,
)

STOCK_ENTRY_FIELD_MAP = {"total_taxable_value": "total_taxable_value"}
SUBCONTRACTING_ORDER_RECEIPT_FIELD_MAP = {"total_taxable_value": "total"}


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

    if (doc.doctype == "Stock Entry" and doc.purpose == "Material Transfer") or (
        doc.doctype == "Subcontracting Receipt" and not doc.is_return
    ):
        if not doc.doc_references:
            frappe.throw(
                _("Please Select Original Document Reference for ITC-04 Reporting"),
                title=_("Mandatory Field"),
            )
        else:
            remove_duplicates(doc)

    if doc.doctype == "Stock Entry" and doc.purpose != "Send to Subcontractor":
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


@frappe.whitelist()
def get_relevant_references(
    supplier, supplied_items, received_items, subcontracting_orders
):

    if isinstance(supplied_items, str):
        supplied_items = frappe.parse_json(supplied_items)
        received_items = frappe.parse_json(received_items)
        subcontracting_orders = frappe.parse_json(subcontracting_orders)

    # same filters used for set_query in JS

    receipt_returns = frappe.db.get_all(
        "Subcontracting Receipt",
        filters=[
            ["docstatus", "=", 1],
            ["is_return", "=", 1],
            ["supplier", "=", supplier],
            ["Subcontracting Receipt Item", "item_code", "in", received_items],
            [
                "Subcontracting Receipt Item",
                "subcontracting_order",
                "in",
                subcontracting_orders,
            ],
        ],
        pluck="name",
        group_by="name",
    )

    stock_entries = frappe.db.get_all(
        "Stock Entry",
        filters=[
            ["docstatus", "=", 1],
            ["purpose", "=", "Send to Subcontractor"],
            ["subcontracting_order", "in", subcontracting_orders],
            ["supplier", "=", supplier],
            ["Stock Entry Detail", "item_code", "in", supplied_items],
        ],
        pluck="name",
        group_by="name",
    )

    data = {"Subcontracting Receipt": receipt_returns, "Stock Entry": stock_entries}

    return data


def remove_duplicates(doc):
    references, duplicate = [], False
    for row in doc.doc_references:
        ref = (row.link_doctype, row.link_name)

        if ref not in references:
            references.append(ref)
        else:
            duplicate = True

    if duplicate:
        doc.doc_references = []
        for row in references:
            doc.append("doc_references", dict(link_doctype=row[0], link_name=row[1]))
