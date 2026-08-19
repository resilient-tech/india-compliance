import frappe
from erpnext.accounts.party import get_address_tax_category
from erpnext.stock.get_item_details import ItemDetailsCtx, get_item_tax_template
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display, get_default_address
from frappe.utils import flt
from pypika import Order

from india_compliance.gst_india.constants.e_waybill import (
    ADDRESS_FIELDS,
    ADDRESS_GSTIN_FIELD_MAP,
    buying_address,
)
from india_compliance.gst_india.overrides.transaction import (
    ignore_gst_validations,
    is_inter_state_supply,
)
from india_compliance.gst_india.utils import (
    get_gst_accounts_by_type,
    get_items,
)
from india_compliance.gst_india.utils.custom_transaction_controller import CustomEwaybillController


# Functions to perform operations before and after mapping of transactions
def after_mapping_subcontracting_order(doc, method, source_doc):
    if source_doc.doctype != "Purchase Order":
        return

    doc.taxes_and_charges = ""
    doc.taxes = []

    if ignore_gst_validations(doc):
        return

    set_taxes(doc)
    update_item_tax_template(doc, source_doc)


def update_item_tax_template(doc, source_doc):
    items = get_items(doc)
    if not items:
        return

    tax_category = source_doc.tax_category

    if not tax_category:
        tax_category = get_address_tax_category(
            frappe.db.get_value("Supplier", source_doc.supplier, "tax_category"),
            source_doc.supplier_address,
        )

    args = ItemDetailsCtx({"company": doc.company, "tax_category": tax_category})

    for item in items:
        if not item.item_code:
            continue

        if item.item_tax_template:
            continue

        out = frappe._dict()
        item_doc = frappe.get_cached_doc("Item", item.item_code)
        get_item_tax_template(args, item_doc, out)
        item.item_tax_template = out.get("item_tax_template")


def after_mapping_stock_entry(doc, method, source_doc):
    if source_doc.doctype != "Subcontracting Order":
        doc.taxes_and_charges = ""
        doc.taxes = []

    set_item_tax_template(doc, source_doc)

    # set_address_fields
    if source_doc.doctype == "Subcontracting Inward Order":
        set_address_for_subcontracting_inward(doc, source_doc)
    else:
        update_address_fields(doc, source_doc)


def update_address_fields(doc, source_doc):
    address_map = get_mapped_address(doc, source_doc)

    if not address_map:
        return

    doc.bill_from_address = address_map.bill_from
    doc.bill_from_gstin = address_map.bill_from_gstin
    doc.bill_to_address = address_map.bill_to
    doc.bill_to_gstin = address_map.bill_to_gstin
    doc.ship_from_address = address_map.ship_from
    doc.ship_to_address = address_map.ship_to

    set_address_display(doc)


def set_address_for_subcontracting_inward(doc, source_doc):
    """Set company (bill_from) -> customer (bill_to) addresses for Subcontracting Inward Stock Entries."""
    if not doc.bill_from_address:
        doc.bill_from_address = get_default_address("Company", source_doc.company)

    if not doc.bill_to_address:
        doc.bill_to_address = get_default_address("Customer", source_doc.customer)

    set_address_display(doc)


def get_mapped_address(doc, source_doc):
    """
    Return bill_from, bill_from_gstin, bill_to, bill_to_gstin, ship_from, ship_to
    resolved from source_doc using ADDRESS_FIELDS (plus SCO mapping).

    reverse - swap bill_from <> bill_to and ship_from <> ship_to.
    """
    address_map = frappe._dict(
        {
            "Subcontracting Order": buying_address,
            **ADDRESS_FIELDS,
        }
    )

    fields = address_map.get(source_doc.doctype, {})

    if not fields:
        return

    bill_from = source_doc.get(fields.get("bill_from"))
    bill_to = source_doc.get(fields.get("bill_to"))
    ship_from = source_doc.get(fields.get("ship_from"))
    ship_to = source_doc.get(fields.get("ship_to"))
    bill_from_gstin = source_doc.get(ADDRESS_GSTIN_FIELD_MAP.get(fields.get("bill_from")))
    bill_to_gstin = source_doc.get(ADDRESS_GSTIN_FIELD_MAP.get(fields.get("bill_to")))

    reverse = (
        source_doc.doctype in ("Subcontracting Order", "Purchase Receipt")
        and doc.purpose in ("Material Transfer", "Send to Subcontractor")
        and doc.is_return == 0
    )

    if reverse:
        bill_from, bill_to, bill_from_gstin, bill_to_gstin = (
            bill_to,
            bill_from,
            bill_to_gstin,
            bill_from_gstin,
        )
        ship_from, ship_to = ship_to, ship_from

    return frappe._dict(
        bill_from=bill_from,
        bill_from_gstin=bill_from_gstin,
        bill_to=bill_to,
        bill_to_gstin=bill_to_gstin,
        ship_from=ship_from,
        ship_to=ship_to,
    )


def set_item_tax_template(doc, source_doc):
    if source_doc.doctype not in ("Subcontracting Order", "Purchase Order"):
        return

    update_item_tax_template(doc, source_doc)


def before_mapping_subcontracting_receipt(doc, method, source_doc, table_maps):
    table_maps["India Compliance Taxes and Charges"] = {
        "doctype": "India Compliance Taxes and Charges",
        "add_if_empty": True,
    }


def set_taxes(doc):
    accounts = get_gst_accounts_by_type(doc.company, "Output", throw=False)
    if not accounts:
        return

    sales_tax_template = frappe.qb.DocType("Sales Taxes and Charges Template")
    sales_tax_template_row = frappe.qb.DocType("Sales Taxes and Charges")

    rate = (
        frappe.qb.from_(sales_tax_template_row)
        .left_join(sales_tax_template)
        .on(sales_tax_template.name == sales_tax_template_row.parent)
        .select(sales_tax_template_row.rate)
        .where(sales_tax_template_row.parenttype == "Sales Taxes and Charges Template")
        .where(sales_tax_template_row.account_head == accounts.get("igst_account"))
        .where(sales_tax_template.disabled == 0)
        .orderby(sales_tax_template.is_default, order=Order.desc)
        .orderby(sales_tax_template.modified, order=Order.desc)
        .limit(1)
        .run(pluck=True)
    )
    rate = rate[0] if rate else 0

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


# Common Functions for Subcontracting Transactions
def get_dashboard_data(data):
    return SubcontractingReceiptController.get_dashboard_data(data)


def onload(doc, method=None):
    SubcontractingReceiptController(doc).set_e_waybill_info()


class SubcontractingController(CustomEwaybillController):
    """Shared by every doctype behind the "e-Waybill for Subcontracting" switch.

    Stock Entry subclasses this too, from `overrides/stock_entry.py`.
    """

    def is_e_waybill_applicable(self):
        return super().is_e_waybill_applicable() and bool(
            frappe.get_cached_doc("GST Settings").enable_e_waybill_for_sc
        )


class SubcontractingOrderController(SubcontractingController):
    DOCTYPE = "Subcontracting Order"


class SubcontractingReceiptController(SubcontractingController):
    DOCTYPE = "Subcontracting Receipt"

    # the receipt number is reported, so it must satisfy the GST format
    VALIDATES_TRANSACTION_NAME = True


def get_transaction_controller(doc):
    if doc.doctype == "Subcontracting Receipt":
        return SubcontractingReceiptController(doc)

    return SubcontractingOrderController(doc)


def is_e_waybill_applicable(doc):
    return get_transaction_controller(doc).is_e_waybill_applicable()


def validate(doc, method=None):
    get_transaction_controller(doc).validate()


def before_save(doc, method=None):
    get_transaction_controller(doc).before_save()


def validate_doc_references(doc, method=None):
    if ignore_gst_validations(doc):
        return

    is_return_material_transfer = (
        doc.doctype == "Stock Entry" and doc.purpose == "Material Transfer" and doc.is_return
    )

    is_subcontracting_receipt = doc.doctype == "Subcontracting Receipt" and not doc.is_return

    if not (is_return_material_transfer or is_subcontracting_receipt):
        return

    if doc.doc_references:
        remove_duplicates(doc)
        return

    error_msg = _("Please Select Original Document Reference for ITC-04 Reporting")
    if is_return_material_transfer:
        frappe.throw(error_msg, title=_("Mandatory Field"))
    else:
        frappe.msgprint(error_msg, alert=True, indicator="yellow")


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
def get_relevant_references(filters: str | dict | frappe._dict | None = None):
    """Permission check not required as get_list in called functions checks permissions."""
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)

    receipt_returns = get_subcontracting_receipt_references(
        filters=filters,
        doctype=None,
        txt=None,
        searchfield=None,
        start=None,
        page_len=None,
    )
    stock_entries = get_stock_entry_references(filters=filters, only_linked_references=True)

    return {
        "Subcontracting Receipt": [row[0] for row in receipt_returns],
        "Stock Entry": [row[0] for row in stock_entries],
    }


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_subcontracting_receipt_references(
    doctype: str | None = None,
    txt: str | None = None,
    searchfield: str | None = None,
    start: int | None = None,
    page_len: int | None = None,
    filters: str | dict | frappe._dict | None = None,
):
    """Permission check not required as get_list checks permissions."""
    filters = frappe._dict(filters)

    _filters = [
        ["docstatus", "=", 1],
        ["is_return", "=", 1],
        ["supplier", "=", filters.supplier],
        ["Subcontracting Receipt Item", "item_code", "in", filters.received_items],
        [
            "Subcontracting Receipt Item",
            "subcontracting_order",
            "in",
            filters.subcontracting_orders,
        ],
    ]

    if txt:
        _filters.append(["name", "like", f"%{txt}%"])

    return frappe.get_list(
        "Subcontracting Receipt",
        filters=_filters,
        fields=["name", "posting_date"],
        group_by="name",
        as_list=True,
    )


@frappe.whitelist()
def get_stock_entry_references(
    doctype: str | None = None,
    txt: str | None = None,
    searchfield: str | None = None,
    start: int | None = None,
    page_len: int | None = None,
    filters: str | dict | frappe._dict | None = None,
    only_linked_references: bool = False,
):
    """Permission check not required as get_list checks permissions."""
    filters = frappe._dict(filters)

    or_filters = []
    _filters = [
        ["docstatus", "=", 1],
        ["purpose", "=", "Send to Subcontractor"],
        ["supplier", "=", filters.supplier],
        ["Stock Entry Detail", "item_code", "in", filters.supplied_items],
    ]

    if txt:
        _filters.append(["name", "like", f"%{txt}%"])

    if only_linked_references:
        _filters.append(["subcontracting_order", "in", filters.subcontracting_orders])

    else:
        or_filters = [
            ["subcontracting_order", "is", "not set"],
            ["subcontracting_order", "in", filters.subcontracting_orders],
        ]

    return frappe.get_list(
        "Stock Entry",
        filters=_filters,
        or_filters=or_filters,
        fields=["name", "posting_date", "subcontracting_order"],
        group_by="name",
        as_list=True,
    )


def remove_duplicates(doc):
    references = []
    has_duplicates = False

    for row in doc.doc_references:
        ref = (row.link_doctype, row.link_name)

        if ref not in references:
            references.append(ref)
        else:
            has_duplicates = True

    if has_duplicates:
        doc.doc_references = []
        for row in references:
            doc.append("doc_references", dict(link_doctype=row[0], link_name=row[1]))


def set_subcontracting_inward_taxable_value(doc):
    """Add the value of customer-provided materials to the e-Waybill taxable value
    of Subcontracting Inward Stock Entries."""
    if doc.purpose == "Subcontracting Delivery":
        _set_subcontracting_delivery_additional_value(doc)
    elif doc.purpose == "Return Raw Material to Customer":
        _set_return_raw_material_additional_value(doc)


def _set_subcontracting_delivery_additional_value(doc):
    """Add the value of consumed customer materials to the delivered finished goods.

    additional = SUM(order_rate * consumed_qty) / produced_qty * delivered transfer_qty.
    Quantities are all in stock UOM (consumed_qty, produced_qty, transfer_qty), so
    the value is consistent with the row amount. Left at 0 for secondary items,
    no consumption, or no production yet.
    """
    scio_details = {item.scio_detail for item in doc.items if item.get("scio_detail")}
    if not scio_details:
        return

    # Customer-provided received items for the finished goods being delivered.
    received_items = frappe.get_all(
        "Subcontracting Inward Order Received Item",
        filters={"reference_name": ("in", list(scio_details)), "is_customer_provided_item": 1},
        fields=["reference_name", "rate", "consumed_qty"],
    )
    if not received_items:
        return

    produced_qty = frappe._dict(
        frappe.get_all(
            "Subcontracting Inward Order Item",
            filters={"name": ("in", list(scio_details))},
            fields=["name", "produced_qty"],
            as_list=True,
        )
    )

    # Total consumed customer-material value per finished good, using the order rate.
    fg_material_cost = {}
    for row in received_items:
        cost = flt(row.rate) * flt(row.consumed_qty)
        fg_material_cost[row.reference_name] = fg_material_cost.get(row.reference_name, 0) + cost

    precision = doc.precision("additional_taxable_value", "items")
    rows_without_produced_qty = []

    for item in doc.items:
        scio_detail = item.get("scio_detail")
        material_cost = fg_material_cost.get(scio_detail)
        if not material_cost:
            continue

        if not produced_qty.get(scio_detail):
            rows_without_produced_qty.append(item.idx)
            continue

        item.additional_taxable_value = flt(
            material_cost / flt(produced_qty.get(scio_detail)) * flt(item.transfer_qty), precision
        )

    if rows_without_produced_qty:
        frappe.msgprint(
            _(
                "Row #{0}: Value of customer-provided materials could not be added to the"
                " taxable value as no production has been reported yet"
            ).format(", ".join(str(idx) for idx in rows_without_produced_qty)),
            alert=True,
            indicator="yellow",
        )


def _set_return_raw_material_additional_value(doc):
    """Set the returned RM taxable value to the customer's declared value (Rule 55).

    additional = rate * qty - amount, and may be negative to correct the SE
    amount. A return moves on-hand material, so the SCIO Received Item rate is used;
    self-procured items (no rate) are skipped.
    """
    scio_details = {item.scio_detail for item in doc.items if item.get("scio_detail")}
    if not scio_details:
        return

    rates = frappe._dict(
        frappe.get_all(
            "Subcontracting Inward Order Received Item",
            filters={"name": ("in", list(scio_details)), "is_customer_provided_item": 1},
            fields=["name", "rate"],
            as_list=True,
        )
    )
    if not rates:
        return

    precision = doc.precision("additional_taxable_value", "items")

    for item in doc.items:
        scio_detail = item.get("scio_detail")
        if scio_detail not in rates:
            continue

        declared_value = flt(rates[scio_detail]) * flt(item.transfer_qty)
        item.additional_taxable_value = flt(declared_value - flt(item.amount), precision)
