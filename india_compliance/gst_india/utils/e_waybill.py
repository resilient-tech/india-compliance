import json
import re

import frappe
from frappe import _
from frappe.utils import flt

from . import (get_gst_accounts, get_itemised_tax_breakup_data,
               set_gst_state_and_state_number, validate_gstin_check_digit)


@frappe.whitelist()
def generate_ewb_json(dt, dn):
    dn = json.loads(dn)
    return get_ewb_data(dt, dn)


def get_ewb_data(dt, dn):

    ewaybills = []
    for doc_name in dn:
        doc = frappe.get_doc(dt, doc_name)

        validate_doc(doc)

        data = frappe._dict(
            {
                "transporterId": "",
                "TotNonAdvolVal": 0,
            }
        )

        data.userGstin = data.fromGstin = doc.company_gstin
        data.supplyType = "O"

        if dt == "Delivery Note":
            data.subSupplyType = 1
        elif doc.gst_category in ["Registered Regular", "SEZ"]:
            data.subSupplyType = 1
        elif doc.gst_category in ["Overseas", "Deemed Export"]:
            data.subSupplyType = 3
        else:
            frappe.throw(_("Unsupported GST Category for E-Way Bill JSON generation"))

        data.docType = "INV"
        data.docDate = frappe.utils.formatdate(doc.posting_date, "dd/mm/yyyy")

        company_address = frappe.get_doc("Address", doc.company_address)
        billing_address = frappe.get_doc("Address", doc.customer_address)

        # added dispatch address
        dispatch_address = (
            frappe.get_doc("Address", doc.dispatch_address_name)
            if doc.dispatch_address_name
            else company_address
        )
        shipping_address = frappe.get_doc("Address", doc.shipping_address_name)

        data = get_address_details(
            data, doc, company_address, billing_address, dispatch_address
        )

        data.itemList = []
        data.totalValue = doc.net_total

        data = get_item_list(data, doc, hsn_wise=True)

        disable_rounded = frappe.db.get_single_value(
            "Global Defaults", "disable_rounded_total"
        )
        data.totInvValue = doc.grand_total if disable_rounded else doc.rounded_total

        data = get_transport_details(data, doc)

        fields = {
            "/. -": {
                "docNo": doc.name,
                "fromTrdName": doc.company,
                "toTrdName": doc.customer_name,
                "transDocNo": doc.lr_no,
            },
            "@#/,&. -": {
                "fromAddr1": company_address.address_line1,
                "fromAddr2": company_address.address_line2,
                "fromPlace": company_address.city,
                "toAddr1": shipping_address.address_line1,
                "toAddr2": shipping_address.address_line2,
                "toPlace": shipping_address.city,
                "transporterName": doc.transporter_name,
            },
        }

        for allowed_chars, field_map in fields.items():
            for key, value in field_map.items():
                if not value:
                    data[key] = ""
                else:
                    data[key] = re.sub(r"[^\w" + allowed_chars + "]", "", value)

        ewaybills.append(data)

    data = {"version": "1.0.0421", "billLists": ewaybills}

    return data


def get_address_details(data, doc, company_address, billing_address, dispatch_address):
    data.fromPincode = validate_pincode(company_address.pincode, "Company Address")
    data.fromStateCode = validate_state_code(
        company_address.gst_state_number, "Company Address"
    )
    data.actualFromStateCode = validate_state_code(
        dispatch_address.gst_state_number, "Dispatch Address"
    )

    if not doc.billing_address_gstin or len(doc.billing_address_gstin) < 15:
        data.toGstin = "URP"
        set_gst_state_and_state_number(billing_address)
    else:
        data.toGstin = doc.billing_address_gstin

    data.toPincode = validate_pincode(billing_address.pincode, "Customer Address")
    data.toStateCode = validate_state_code(
        billing_address.gst_state_number, "Customer Address"
    )

    if doc.customer_address != doc.shipping_address_name:
        data.transType = 2
        shipping_address = frappe.get_doc("Address", doc.shipping_address_name)
        set_gst_state_and_state_number(shipping_address)
        data.toPincode = validate_pincode(shipping_address.pincode, "Shipping Address")
        data.actualToStateCode = validate_state_code(
            shipping_address.gst_state_number, "Shipping Address"
        )
    else:
        data.transType = 1
        data.actualToStateCode = data.toStateCode
        shipping_address = billing_address

    if doc.gst_category == "SEZ":
        data.toStateCode = 99

    return data


def get_item_list(data, doc, hsn_wise=False):
    for attr in ["cgstValue", "sgstValue", "igstValue", "cessValue", "OthValue"]:
        data[attr] = 0

    gst_accounts = get_gst_accounts(doc.company, account_wise=True)
    tax_map = {
        "sgst_account": ["sgstRate", "sgstValue"],
        "cgst_account": ["cgstRate", "cgstValue"],
        "igst_account": ["igstRate", "igstValue"],
        "cess_account": ["cessRate", "cessValue"],
    }
    item_data_attrs = ["sgstRate", "cgstRate", "igstRate", "cessRate", "cessNonAdvol"]
    hsn_wise_charges, hsn_taxable_amount = get_itemised_tax_breakup_data(
        doc, account_wise=True, hsn_wise=hsn_wise
    )
    for item_or_hsn, taxable_amount in hsn_taxable_amount.items():
        item_data = frappe._dict()
        if not item_or_hsn:
            frappe.throw(_("GST HSN Code does not exist for one or more items"))
        item_data.hsnCode = int(item_or_hsn) if hsn_wise else item_or_hsn
        item_data.taxableAmount = taxable_amount
        item_data.qtyUnit = ""
        for attr in item_data_attrs:
            item_data[attr] = 0

        for account, tax_detail in hsn_wise_charges.get(item_or_hsn, {}).items():
            account_type = gst_accounts.get(account, "")
            for tax_acc, attrs in tax_map.items():
                if account_type == tax_acc:
                    item_data[attrs[0]] = tax_detail.get("tax_rate")
                    data[attrs[1]] += tax_detail.get("tax_amount")
                    break
            else:
                data.OthValue += tax_detail.get("tax_amount")

        data.itemList.append(item_data)

        # Tax amounts rounded to 2 decimals to avoid exceeding max character limit
        for attr in ["sgstValue", "cgstValue", "igstValue", "cessValue"]:
            data[attr] = flt(data[attr], 2)

    return data


def get_transport_details(data, doc):
    if doc.distance > 4000:
        frappe.throw(_("Distance cannot be greater than 4000 kms"))

    data.transDistance = int(round(doc.distance))

    transport_modes = {"Road": 1, "Rail": 2, "Air": 3, "Ship": 4}

    vehicle_types = {"Regular": "R", "Over Dimensional Cargo (ODC)": "O"}

    data.transMode = transport_modes.get(doc.mode_of_transport)

    if doc.mode_of_transport == "Road":
        if not doc.gst_transporter_id and not doc.vehicle_no:
            frappe.throw(
                _(
                    "Either GST Transporter ID or Vehicle No is required if Mode of Transport is Road"
                )
            )
        if doc.vehicle_no:
            data.vehicleNo = doc.vehicle_no.replace(" ", "")
        if not doc.gst_vehicle_type:
            frappe.throw(_("Vehicle Type is required if Mode of Transport is Road"))
        else:
            data.vehicleType = vehicle_types.get(doc.gst_vehicle_type)
    else:
        if not doc.lr_no or not doc.lr_date:
            frappe.throw(
                _(
                    "Transport Receipt No and Date are mandatory for your chosen Mode of Transport"
                )
            )

    if doc.lr_no:
        data.transDocNo = doc.lr_no

    if doc.lr_date:
        data.transDocDate = frappe.utils.formatdate(doc.lr_date, "dd/mm/yyyy")

    if doc.gst_transporter_id:
        if doc.gst_transporter_id[0:2] != "88":
            validate_gstin_check_digit(
                doc.gst_transporter_id, label="GST Transporter ID"
            )
        data.transporterId = doc.gst_transporter_id

    return data


def validate_doc(doc):
    if doc.docstatus != 1:
        frappe.throw(_("E-Way Bill JSON can only be generated from submitted document"))

    if doc.is_return:
        frappe.throw(
            _("E-Way Bill JSON cannot be generated for Sales Return as of now")
        )

    if doc.ewaybill:
        frappe.throw(_("e-Way Bill already exists for this document"))

    reqd_fields = [
        "company_gstin",
        "company_address",
        "customer_address",
        "shipping_address_name",
        "mode_of_transport",
        "distance",
    ]

    for fieldname in reqd_fields:
        if not doc.get(fieldname):
            frappe.throw(
                _("{} is required to generate E-Way Bill JSON").format(
                    doc.meta.get_label(fieldname)
                )
            )

    if len(doc.company_gstin) < 15:
        frappe.throw(_("You must be a registered supplier to generate e-Way Bill"))


def validate_pincode(pincode, address):
    pin_not_found = "Pin Code doesn't exist for {}"
    incorrect_pin = (
        "Pin Code for {} is incorrecty formatted. It must be 6 digits (without spaces)"
    )

    if not pincode:
        frappe.throw(_(pin_not_found.format(address)))

    pincode = pincode.replace(" ", "")
    if not pincode.isdigit() or len(pincode) != 6:
        frappe.throw(_(incorrect_pin.format(address)))
    else:
        return int(pincode)


def validate_state_code(state_code, address):
    no_state_code = "GST State Code not found for {0}. Please set GST State in {0}"
    if not state_code:
        frappe.throw(_(no_state_code.format(address)))
    else:
        return int(state_code)


@frappe.whitelist()
def download_ewb_json():
    data = json.loads(frappe.local.form_dict.data)
    frappe.local.response.filecontent = json.dumps(data, indent=4, sort_keys=True)
    frappe.local.response.type = "download"

    filename_prefix = "Bulk"
    docname = frappe.local.form_dict.docname
    if docname:
        if docname.startswith("["):
            docname = json.loads(docname)
            if len(docname) == 1:
                docname = docname[0]

        if not isinstance(docname, list):
            # removes characters not allowed in a filename (https://stackoverflow.com/a/38766141/4767738)
            filename_prefix = re.sub(r"[^\w_.)( -]", "", docname)

    frappe.local.response.filename = "{0}_e-WayBill_Data_{1}.json".format(
        filename_prefix, frappe.utils.random_string(5)
    )
