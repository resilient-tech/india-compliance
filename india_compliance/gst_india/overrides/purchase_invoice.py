import json

import jwt

import frappe
from frappe import _
from frappe.utils import flt, getdate
from erpnext.accounts.party import get_party_details

from india_compliance.gst_india.api_classes.taxpayer_base import (
    TaxpayerBaseAPI,
    otp_handler,
)
from india_compliance.gst_india.api_classes.taxpayer_e_invoice import (
    EInvoiceAPI as TaxpayerEInvoiceAPI,
)
from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.overrides.transaction import (
    validate_hsn_codes as _validate_hsn_codes,
)
from india_compliance.gst_india.overrides.transaction import validate_transaction
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info


def onload(doc, method=None):
    if doc.docstatus != 1:
        return

    if doc.gst_category == "Overseas":
        doc.set_onload(
            "bill_of_entry_exists",
            frappe.db.exists(
                "Bill of Entry",
                {"purchase_invoice": doc.name, "docstatus": 1},
            ),
        )

    if not doc.get("ewaybill"):
        return

    gst_settings = frappe.get_cached_doc("GST Settings")

    if not is_api_enabled(gst_settings):
        return

    if (
        gst_settings.enable_e_waybill
        and gst_settings.enable_e_waybill_from_pi
        and doc.ewaybill
    ):
        doc.set_onload("e_waybill_info", get_e_waybill_info(doc))


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    validate_hsn_codes(doc)
    set_ineligibility_reason(doc)
    update_itc_totals(doc)
    validate_supplier_invoice_number(doc)
    validate_with_inward_supply(doc)
    set_reconciliation_status(doc)
    update_item_mapping(doc)


def on_cancel(doc, method=None):
    frappe.db.set_value(
        "GST Inward Supply",
        {"link_doctype": "Purchase Invoice", "link_name": doc.name},
        {
            "match_status": "",
            "link_name": "",
            "link_doctype": "",
            "action": "No Action",
        },
    )


def set_reconciliation_status(doc):
    reconciliation_status = "Not Applicable"

    if is_b2b_invoice(doc):
        reconciliation_status = "Unreconciled"

    doc.reconciliation_status = reconciliation_status


def is_b2b_invoice(doc):
    return not (
        doc.supplier_gstin in ["", None]
        or doc.gst_category in ["Registered Composition", "Unregistered", "Overseas"]
        or doc.supplier_gstin == doc.company_gstin
        or doc.is_opening == "Yes"
    )


def update_itc_totals(doc, method=None):
    # Set default value
    set_itc_classification(doc)
    validate_reverse_charge(doc)

    # Initialize values
    doc.itc_integrated_tax = 0
    doc.itc_state_tax = 0
    doc.itc_central_tax = 0
    doc.itc_cess_amount = 0

    if doc.ineligibility_reason == "ITC restricted due to PoS rules":
        return

    for tax in doc.get("taxes"):
        if tax.gst_tax_type == "igst":
            doc.itc_integrated_tax += flt(tax.base_tax_amount_after_discount_amount)

        if tax.gst_tax_type == "sgst":
            doc.itc_state_tax += flt(tax.base_tax_amount_after_discount_amount)

        if tax.gst_tax_type == "cgst":
            doc.itc_central_tax += flt(tax.base_tax_amount_after_discount_amount)

        if tax.gst_tax_type == "cess":
            doc.itc_cess_amount += flt(tax.base_tax_amount_after_discount_amount)


def set_itc_classification(doc):
    if doc.gst_category == "Overseas":
        for item in doc.items:
            if not item.gst_hsn_code.startswith("99"):
                doc.itc_classification = "Import Of Goods"
                break
        else:
            doc.itc_classification = "Import Of Service"

    elif doc.is_reverse_charge:
        doc.itc_classification = "ITC on Reverse Charge"

    elif doc.gst_category == "Input Service Distributor" and doc.is_internal_transfer():
        doc.itc_classification = "Input Service Distributor"

    else:
        doc.itc_classification = "All Other ITC"


def validate_supplier_invoice_number(doc):
    if (
        doc.bill_no
        or doc.gst_category == "Unregistered"
        or not frappe.get_cached_value(
            "GST Settings", "GST Settings", "require_supplier_invoice_no"
        )
    ):
        return

    frappe.throw(
        _("As per your GST Settings, Bill No is mandatory for Purchase Invoice."),
        title=_("Missing Mandatory Field"),
    )


def update_item_mapping(doc):
    if not frappe.db.exists(
        "e-Invoice Log",
        {"reference_name": doc.name, "reference_doctype": "Purchase Invoice"},
    ):
        return

    item_mapping = frappe.get_all(
        "e-Invoice Mapping",
        filters={
            "erpnext_value": ["=", ""],
            "item_row_name": ["in", [item.name for item in doc.items]],
        },
        fields=["item_row_name", "rate", "erpnext_fieldname"],
    )

    mapped_items = {
        (item.item_row_name, flt(item.rate, precision=2), item.erpnext_fieldname)
        for item in item_mapping
    }

    def update_mapping(item, fieldname):
        frappe.db.set_value(
            "e-Invoice Mapping",
            {
                "item_row_name": item.name,
                "rate": item.rate,
                "erpnext_fieldname": fieldname,
            },
            "erpnext_value",
            item.get("item_code" if fieldname == "item_name" else fieldname),
        )

    for item in doc.items:
        rate = flt(item.rate, precision=2)

        for fieldname in ["item_name", "uom"]:
            key = (item.name, rate, fieldname)

            if key in mapped_items:
                update_mapping(item, fieldname)


def get_dashboard_data(data):
    transactions = data.setdefault("transactions", [])
    reference_section = next(
        (row for row in transactions if row.get("label") == "Reference"), None
    )

    if reference_section is None:
        reference_section = {"label": "Reference", "items": []}
        transactions.append(reference_section)

    reference_section["items"].append("Bill of Entry")

    update_dashboard_with_gst_logs(
        "Purchase Invoice",
        data,
        "e-Waybill Log",
        "Integration Request",
        "GST Inward Supply",
    )

    return data


def validate_with_inward_supply(doc):
    if not doc.get("_inward_supply"):
        return

    mismatch_fields = {}
    for field in [
        "company",
        "company_gstin",
        "supplier_gstin",
        "bill_no",
        "bill_date",
        "is_reverse_charge",
        "place_of_supply",
    ]:
        if doc.get(field) != doc._inward_supply.get(field):
            mismatch_fields[field] = doc._inward_supply.get(field)

    # mismatch for taxable_value
    taxable_value = sum([item.taxable_value for item in doc.items])
    if taxable_value != doc._inward_supply.get("taxable_value"):
        mismatch_fields["Taxable Value"] = doc._inward_supply.get("taxable_value")

    # mismatch for taxes
    for tax in ["cgst", "sgst", "igst", "cess"]:
        tax_amount = get_tax_amount(doc.taxes, tax)
        if tax == "cess":
            tax_amount += get_tax_amount(doc.taxes, "cess_non_advol")

        if tax_amount == doc._inward_supply.get(tax):
            continue

        mismatch_fields[tax.upper()] = doc._inward_supply.get(tax)

    if mismatch_fields:
        message = (
            "Purchase Invoice does not match with releted GST Inward Supply.<br>"
            "Following values are not matching from 2A/2B: <br>"
        )
        for field, value in mismatch_fields.items():
            message += f"<br>{field}: {value}"

        frappe.msgprint(
            _(message),
            title=_("Mismatch with GST Inward Supply"),
        )

    elif doc._action == "submit":
        frappe.msgprint(
            _("Invoice matched with GST Inward Supply"),
            alert=True,
            indicator="green",
        )


def get_tax_amount(taxes, gst_tax_type):
    if not (taxes or gst_tax_type):
        return 0

    return sum(
        [
            tax.base_tax_amount_after_discount_amount
            for tax in taxes
            if tax.gst_tax_type == gst_tax_type
        ]
    )


def set_ineligibility_reason(doc, show_alert=True):
    doc.ineligibility_reason = ""

    for item in doc.items:
        if item.is_ineligible_for_itc:
            doc.ineligibility_reason = "Ineligible As Per Section 17(5)"
            break

    if (
        doc.place_of_supply not in ["96-Other Countries", "97-Other Territory"]
        and doc.place_of_supply[:2] != doc.company_gstin[:2]
    ):
        doc.ineligibility_reason = "ITC restricted due to PoS rules"

    if show_alert and doc.ineligibility_reason:
        frappe.msgprint(
            _("ITC Ineligible: {0}").format(frappe.bold(doc.ineligibility_reason)),
            alert=True,
            indicator="orange",
        )


def validate_reverse_charge(doc):
    if doc.itc_classification != "Import Of Goods" or not doc.is_reverse_charge:
        return

    frappe.throw(_("Reverse Charge is not applicable on Import of Goods"))


def validate_hsn_codes(doc):
    if doc.gst_category != "Overseas":
        return

    _validate_hsn_codes(
        doc,
        throw=True,
        message="GST HSN Code is mandatory for Overseas Purchase Invoice.<br>",
    )


@frappe.whitelist()
@otp_handler
def create_purchase_invoice_from_irn(company_gstin, irn):
    e_invoice_log = get_e_invoice_log(company_gstin, irn)

    invoice_data = format_data(json.loads(e_invoice_log.invoice_data))

    supplier = get_party_name(invoice_data.get("supplier"), party_type="Supplier")
    company = get_party_name(invoice_data.get("buyer"), party_type="Company")

    doc = create_purchase_invoice(supplier, company, invoice_data.get("invoice"))
    e_invoice_log.update(
        {
            "reference_doctype": "Purchase Invoice",
            "reference_name": doc.name,
        }
    ).save(ignore_permissions=True)

    update_mapped_and_unmapped_items(doc, supplier, e_invoice_log)

    return doc.name


def get_e_invoice_log(company_gstin, irn):
    if frappe.db.exists("e-Invoice Log", irn):
        return frappe.get_doc("e-Invoice Log", irn)

    irn_data = get_irn_details(company_gstin, irn)
    return frappe.get_doc(
        {
            "doctype": "e-Invoice Log",
            "irn": irn,
            "acknowledgement_number": irn_data.get("AckNo"),
            "acknowledged_on": irn_data.get("AckDt"),
            "invoice_data": frappe.as_json(irn_data, indent=4),
        }
    ).save(ignore_permissions=True)


def get_irn_details(company_gstin, irn):
    TaxpayerBaseAPI(company_gstin).validate_auth_token()

    response = TaxpayerEInvoiceAPI(company_gstin=company_gstin).get_irn_details(irn)
    decoded_data = jwt.decode(
        response.data["SignedInvoice"], options={"verify_signature": False}
    )

    return json.loads(decoded_data["data"])


def format_data(irn_data):
    field_map = {
        "BuyerDtls": "buyer",
        "SellerDtls": "supplier",
        "Gstin": "gstin",
        "Pin": "pincode",
        "Stcd": "gst_state_number",
        "Dt": "bill_date",
        "No": "bill_no",
        "AckDt": "posting_date",
        "Distance": "distance",
        "VehNo": "vehicle_no",
        "TransId": "gst_transporter_id",
        "HsnCd": "item_code",
        "PrdDesc": "item_name",
        "Qty": "qty",
        "Unit": "uom",
        "UnitPrice": "rate",
    }
    data = {
        "supplier": {},
        "buyer": {},
        "invoice": {"items": []},
    }

    def map_keys(source, target, section):
        for key, value in source.items():
            if not field_map.get(key):
                continue

            target[section][field_map.get(key)] = value

    map_keys(irn_data["BuyerDtls"], data, "buyer")
    map_keys(irn_data["SellerDtls"], data, "supplier")
    map_keys({**irn_data["DocDtls"], **irn_data["EwbDtls"]}, data, "invoice")

    for item in irn_data["ItemList"]:
        items_details = {
            field_map.get(key): value
            for key, value in item.items()
            if field_map.get(key)
        }
        data["invoice"]["items"].append(items_details)

    return data


def create_purchase_invoice(supplier, company, invoice_info):
    invoice_data = {
        "doctype": "Purchase Invoice",
        "supplier": supplier,
        "company": company,
        "due_date": frappe.utils.nowdate(),
        "is_generated_from_irn": 1,
    }
    invoice_info["bill_date"] = getdate(invoice_info["bill_date"])
    invoice_data.update(invoice_info)

    doc = frappe.get_doc(invoice_data)
    doc.update(
        get_party_details(
            posting_date=doc.posting_date,
            bill_date=doc.bill_date,
            party=doc.supplier,
            party_type="Supplier",
            account=doc.credit_to,
            price_list=doc.buying_price_list,
            fetch_payment_terms_template=(
                not doc.ignore_default_payment_terms_template
            ),
            company=doc.company,
            doctype="Purchase Invoice",
        )
    )
    doc.calculate_taxes_and_totals()

    doc.flags.ignore_validate = True
    doc.flags.ignore_links = True
    doc.insert(ignore_mandatory=True)

    return doc


def get_party_name(party_details, party_type):
    try:
        address_doc = frappe.get_doc("Address", party_details)
    except frappe.DoesNotExistError:
        frappe.clear_last_message()
        frappe.throw(
            _(
                "Address with GSTIN {gstin}, Pincode {pincode}, and State code {state_code} not found"
            ).format(
                gstin=party_details.get("Gstin"),
                pincode=party_details.get("Pin"),
                state_code=party_details.get("Stcd"),
            )
        )

    for link in address_doc.links:
        if link.link_doctype == party_type:
            return link.link_name

    frappe.throw(f"{party_type.capitalize()} not found with this address")


def update_mapped_and_unmapped_items(doc, supplier, e_invoice_log):
    def get_mapped_data(mappings, fieldname):
        return {
            mapping.get("e_invoice_value"): mapping.get("erpnext_value")
            for mapping in mappings
            if mapping.get("erpnext_fieldname") == fieldname
        }

    def log_unmapped_item(fieldname, item):
        frappe.get_doc(
            {
                "doctype": "e-Invoice Mapping",
                "party": supplier,
                "party_type": "Supplier",
                "erpnext_fieldname": fieldname,
                "e_invoice_value": item.get(fieldname),
                "rate": item.rate,
                "item_row_name": item.name,
            }
        ).save(ignore_permissions=True)

    mappings = frappe.get_all(
        "e-Invoice Mapping",
        filters={"party": supplier, "erpnext_value": ["!=", ""]},
        fields=["e_invoice_value", "erpnext_value", "erpnext_fieldname"],
    )

    mapped_items = get_mapped_data(mappings, "item_name")
    mapped_uoms = get_mapped_data(mappings, "uom")

    items = frappe.get_all(
        "Item",
        filters={"item_code": ["in", list(mapped_items.values())]},
        fields=["item_code", "item_name"],
    )
    item_names = {item.item_code: item.item_name for item in items}

    for item in doc.items:
        if item_code := mapped_items.get(item.item_name):
            item.item_code = item_code
            item.item_name = item_names.get(item_code)
        else:
            log_unmapped_item("item_name", item)

        if item_uom := mapped_uoms.get(item.uom):
            item.uom = item_uom
        else:
            log_unmapped_item("uom", item)

    doc.flags.ignore_validate = True
    doc.save(ignore_permissions=True)
    e_invoice_log.save(ignore_permissions=True)


@frappe.whitelist()
def get_item_details(args, doc):
    from erpnext.stock.get_item_details import get_item_details

    doc = json.loads(doc)
    data = get_item_details(args, doc)

    if not doc.get("is_generated_from_irn"):
        return data

    args = json.loads(args)
    data.rate = args.get("net_rate")
    data.qty = args.get("qty")
    data.uom = args.get("uom")
    data.price_list_rate = 0
    data.discount_percentage = 0
    data.discount_amount = 0
    data.margin_rate_or_amount = data.rate

    return data


@frappe.whitelist()
def get_gstin_with_company_name():
    data = frappe.get_all(
        "Address",
        filters=[
            ["Address", "gstin", "!=", ""],
            ["Dynamic Link", "link_doctype", "=", "Company"],
        ],
        fields=["gstin as value", "`tabDynamic Link`.link_name as description"],
        distinct=True,
    )
    return data
