import json
import re
from datetime import datetime

import pyqrcode

import frappe
from frappe import _
from frappe.utils import random_string, today
from frappe.utils.file_manager import save_file

from india_compliance.gst_india.api_classes.e_waybill import EWaybillAPI
from india_compliance.gst_india.constants.e_waybill import (
    TRANSPORT_MODES,
    VEHICLE_TYPES,
)
from india_compliance.gst_india.utils.api import pretty_json
from india_compliance.gst_india.utils.invoice_data import GSTInvoiceData

########################################################################################################################
### Manual JSON Generation for e-Waybill ###############################################################################
########################################################################################################################


@frappe.whitelist()
def download_e_waybill_json(doctype, docnames):
    docnames = json.loads(docnames) if docnames.startswith("[") else [docnames]
    frappe.response.filecontent = generate_e_waybill_json(doctype, docnames)
    frappe.response.type = "download"
    frappe.response.filename = get_file_name(docnames)


def generate_e_waybill_json(doctype, docnames):
    ewb_data = frappe._dict(
        {
            "version": "1.0.0621",
            "billLists": [],
        }
    )

    for doc in docnames:
        doc = frappe.get_doc(doctype, doc)
        ewb_data.billLists.append(
            EWaybillData(doc, json_download=True).get_e_waybill_data()
        )

    return pretty_json(ewb_data)


def get_file_name(docnames):
    prefix = "Bulk"
    if len(docnames) == 1:
        prefix = re.sub(r"[^\w_.)( -]", "", docnames[0])

    return f"{prefix}_e-Waybill_Data_{frappe.utils.random_string(5)}.json"


########################################################################################################################
### e-Waybill Generation and Modification using APIs ###################################################################
########################################################################################################################


DATE_FORMAT = "%d/%m/%Y %I:%M:%S %p"


@frappe.whitelist()
def generate_e_waybill_if_possible(doctype, docname):
    doc = frappe.get_doc(doctype, docname)
    _generate_e_waybill(doc, throw=False)


@frappe.whitelist()
def generate_e_waybill(doctype, docname, dialog):
    doc = frappe.get_doc(doctype, docname)
    dialog = json.loads(dialog)
    update_invoice(doc, dialog)
    _generate_e_waybill(doc)


def _generate_e_waybill(doc, throw=True):
    validate_doctype_for_e_waybill(doc)
    validate_if_e_waybill_is_available(doc, available=False)

    try:
        data = EWaybillData(doc).get_e_waybill_data()

    except frappe.ValidationError as e:
        if throw:
            raise e

        frappe.clear_last_message()
        frappe.publish_realtime(
            "e_waybill_generated",
            {
                "doctype": doc.doctype,
                "docname": doc.name,
                "alert": "e-Waybill could not be auto-generated",
            },
        )
        return False

    result = EWaybillAPI(doc.company_gstin).generate_e_waybill(data)
    frappe.publish_realtime(
        "e_waybill_generated",
        {"doctype": doc.doctype, "docname": doc.name, "alert": result.alert},
    )

    e_waybill = str(result.get("ewayBillNo"))
    e_waybill_date = datetime.strptime(result.get("ewayBillDate"), DATE_FORMAT)
    valid_upto = None
    if result.get("validUpto"):
        valid_upto = datetime.strptime(result.get("validUpto"), DATE_FORMAT)
    doc.db_set(
        {
            "ewaybill": e_waybill,
            "e_waybill_validity": valid_upto,
        }
    )
    log_values = {
        "e_waybill_number": e_waybill,
        "e_waybill_date": e_waybill_date,
        "valid_upto": valid_upto,
        "linked_with": doc.name,
    }
    create_or_update_e_waybill_log(doc, None, log_values)
    print_e_waybill_as_per_settings(doc)


@frappe.whitelist()
def cancel_e_waybill(doc, dialog):
    doc = frappe._dict(json.loads(doc))
    dialog = json.loads(dialog)

    validate_doctype_for_e_waybill(doc)
    validate_if_e_waybill_is_available(doc, dialog)
    validate_e_waybill_validity(doc)

    delete_e_waybill_pdf(doc.doctype, doc.name, doc.ewaybill)

    data = {
        "ewbNo": doc.ewaybill,
        "cancelRsnCode": dialog.get("reason").split("-")[0],
        "cancelRmrk": dialog.get("remark"),
    }
    result = EWaybillAPI(doc.company_gstin).cancel_e_waybill(data)

    dt_values = {
        "ewaybill": None,
        "e_waybill_validity": None,
    }
    log_values = {
        "name": doc.ewaybill,
        "is_cancelled": 1,
        "cancel_reason_code": dialog.get("reason"),
        "cancel_remark": dialog.get("remark"),
        "cancel_date": datetime.strptime(result.get("cancelDate"), DATE_FORMAT),
    }

    create_or_update_e_waybill_log(doc, dt_values, log_values)


@frappe.whitelist()
def update_vehicle_info(doc, dialog):
    doc = frappe._dict(json.loads(doc))
    dialog = json.loads(dialog)

    validate_doctype_for_e_waybill(doc)
    validate_if_e_waybill_is_available(doc, dialog)
    validate_e_waybill_validity(doc)

    dispatch_address = (
        doc.dispatch_address_name if doc.dispatch_address_name else doc.company_address
    )
    dispatch_address = frappe.get_doc("Address", dispatch_address)

    data = {
        "ewbNo": doc.ewaybill,
        "vehicleNo": dialog.get("vehicle_no").replace(" ", ""),
        "fromPlace": dispatch_address.city,
        "fromState": dispatch_address.gst_state_number,
        "reasonCode": dialog.get("reason").split("-")[0],
        "reasonRem": dialog.get("remark"),
        "transDocNo": dialog.get("lr_no"),
        "transDocDate": frappe.utils.formatdate(dialog.get("lr_date"), "dd/mm/yyyy"),
        "transMode": TRANSPORT_MODES.get(dialog.get("mode_of_transport")),
        "vehicleType": VEHICLE_TYPES.get(dialog.get("gst_vehicle_type")),
    }
    result = EWaybillAPI(doc.company_gstin).update_vehicle_info(data)

    doc_values = {
        "e_waybill_validity": datetime.strptime(result.get("validUpto"), DATE_FORMAT),
        "vehicle_no": dialog.get("vehicle_no").replace(" ", ""),
        "lr_no": dialog.get("lr_no"),
        "lr_date": dialog.get("lr_date"),
        "mode_of_transport": dialog.get("mode_of_transport"),
        "gst_vehicle_type": dialog.get("gst_vehicle_type"),
    }
    log_values = {
        "name": doc.ewaybill,
        "is_latest_data": 0,
        "valid_upto": datetime.strptime(result.get("validUpto"), DATE_FORMAT),
    }
    comment = (
        f"{frappe.session.user} updated vehicle info for e-waybill. New details are: \n"
        f" Vehicle No: {dialog.get('vehicle_no')} \n LR No: {dialog.get('lr_no')} \n LR"
        f" Date: {dialog.get('lr_date')} \n Mode of Transport:"
        f" {dialog.get('mode_of_transport')} \n GST Vehicle Type:"
        f" {dialog.get('gst_vehicle_type')}"
    )
    create_or_update_e_waybill_log(doc, doc_values, log_values, comment)

    if dialog.get("update_e_waybill_data"):
        print_e_waybill_as_per_settings(doc, force_get_data=True)


@frappe.whitelist()
def update_transporter(doc, dialog):
    doc = frappe._dict(json.loads(doc))
    dialog = json.loads(dialog)

    validate_doctype_for_e_waybill(doc)
    validate_if_e_waybill_is_available(doc, dialog)
    validate_e_waybill_validity(doc)

    data = {
        "ewbNo": doc.ewaybill,
        "transporterId": dialog.get("gst_transporter_id"),
    }
    result = EWaybillAPI(doc.company_gstin).update_transporter(data)

    # transporter_name can be different from transporter
    transporter_name = (
        frappe.db.get_value("Supplier", dialog.get("transporter"), "supplier_name")
        if dialog.get("transporter")
        else None
    )
    doc_values = {
        "transporter": dialog.get("transporter"),
        "transporter_name": transporter_name,
        "gst_transporter_id": dialog.get("gst_transporter_id"),
    }
    log_values = {
        "name": doc.ewaybill,
        "is_latest_data": 0,
    }
    comment = (
        f"{frappe.session.user} updated transporter for e-Waybill. New Transporter ID"
        f" is {result.get('transporterId')}."
    )
    create_or_update_e_waybill_log(doc, doc_values, log_values, comment)

    if dialog.get("update_e_waybill_data"):
        print_e_waybill_as_per_settings(doc, force_get_data=True)


########################################################################################################################
### e-Waybill Print and Attach Functions ###############################################################################
########################################################################################################################


def print_e_waybill_as_per_settings(doc, force_get_data=False):
    get_data, attach = frappe.get_cached_value(
        "GST Settings", "GST Settings", ("get_data_for_print", "attach_e_waybill_print")
    )
    if attach:
        _attach_or_print_e_waybill(doc, "attach")
    elif get_data or force_get_data:
        _attach_or_print_e_waybill(doc)


@frappe.whitelist()
def attach_or_print_e_waybill(doc, action):
    doc = frappe._dict(json.loads(doc))
    validate_doctype_for_e_waybill(doc)
    validate_if_e_waybill_is_available(doc)
    e_waybill_doc = validate_e_waybill_log(doc)
    _attach_or_print_e_waybill(doc, action, e_waybill_doc)


def _attach_or_print_e_waybill(doc, action=None, e_waybill_doc=None):
    if (
        not e_waybill_doc
        or not e_waybill_doc.get("is_latest_data")
        or not e_waybill_doc.get("data")
    ):
        result, qr_base64 = get_e_waybill_data(doc.ewaybill, doc.company_gstin)
        e_waybill_doc = frappe._dict(
            {
                "e_waybill_number": doc.ewaybill,
                "data": result,
                "qr_base64": qr_base64,
            }
        )

    if action == "attach":
        generate_e_waybill_pdf(doc.doctype, doc.name, doc.ewaybill, e_waybill_doc)


def get_e_waybill_data(e_waybill, company_gstin):
    result = EWaybillAPI(company_gstin).get_e_waybill(e_waybill)
    e_waybill_date = datetime.strptime(result.ewayBillDate, DATE_FORMAT)
    qr_text = "/".join(
        (
            e_waybill,
            result.userGstin,
            datetime.strftime(e_waybill_date, "%d-%m-%Y %H:%M:%S"),
        )
    )
    qr_base64 = pyqrcode.create(qr_text).png_as_base64_str(scale=5, quiet_zone=1)
    frappe.db.set_value(
        "e-Waybill Log",
        e_waybill,
        {
            "data": json.dumps(result, indent=4),
            "qr_base64": qr_base64,
            "is_latest_data": 1,
        },
    )
    return result, qr_base64


def generate_e_waybill_pdf(doctype, docname, e_waybill, e_waybill_doc=None):
    delete_e_waybill_pdf(doctype, docname, e_waybill)
    if not e_waybill_doc:
        e_waybill_doc = frappe.get_doc("e-Waybill Log", e_waybill)

    pdf = frappe.get_print(
        "e-Waybill Log", e_waybill, "e-Waybill", no_letterhead=True, as_pdf=True
    )
    save_file(f"{e_waybill}-{docname}.pdf", pdf, doctype, docname, is_private=1)


def delete_e_waybill_pdf(doctype, docname, e_waybill):
    doc_list = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": doctype,
            "attached_to_name": docname,
            "file_name": f"{e_waybill}-{docname}.pdf",
        },
        pluck="name",
    )
    for doc in doc_list:
        frappe.delete_doc("File", doc)


########################################################################################################################
### Other Utility and Validation Functions ############################################################################
########################################################################################################################


def create_or_update_e_waybill_log(doc, doc_values, log_values, comment=None):
    if doc_values:
        frappe.db.set_value(doc.doctype, doc.name, doc_values)

    if "name" in log_values:
        e_waybill_doc = frappe.get_doc("e-Waybill Log", log_values.pop("name"))
    else:
        e_waybill_doc = frappe.get_doc({"doctype": "e-Waybill Log"})
    e_waybill_doc.update(log_values)
    e_waybill_doc.save(ignore_permissions=True)

    if comment:
        e_waybill_doc.add_comment(text=comment)


def update_invoice(doc, dialog):
    transporter_name = (
        frappe.db.get_value("Supplier", dialog.get("transporter"), "supplier_name")
        if dialog.get("transporter")
        else None
    )

    doc.db_set(
        {
            "transporter": dialog.get("transporter"),
            "transporter_name": transporter_name,
            "gst_transporter_id": dialog.get("gst_transporter_id"),
            "vehicle_no": dialog.get("vehicle_no"),
            "distance": dialog.get("distance"),
            "lr_no": dialog.get("lr_no"),
            "lr_date": dialog.get("lr_date"),
            "mode_of_transport": dialog.get("mode_of_transport"),
            "gst_vehicle_type": dialog.get("gst_vehicle_type"),
            "gst_category": dialog.get("gst_category"),
            "export_type": dialog.get("export_type"),
        },
    )


def validate_doctype_for_e_waybill(doc):
    if doc.doctype not in ("Sales Invoice", "Delivery Note"):
        frappe.throw(
            _(
                "Only Sales Invoice and Delivery Note are supported for generating"
                " e-Waybill"
            )
        )


def validate_if_e_waybill_is_available(doc, dia=None, available=True):
    if not available:
        if doc.ewaybill:
            frappe.throw(_("e-Waybill already generated for this document"))
        return

    # e-Waybill should be available
    if not doc.get("ewaybill"):
        frappe.throw(_("No e-Waybill found for this document"))

    if dia and doc.ewaybill != dia.get("ewaybill"):
        frappe.throw(_("Invalid e-Waybill"))


def validate_e_waybill_validity(doc):
    if doc.e_waybill_validity and doc.e_waybill_validity < today():
        frappe.throw(
            _("e-Waybill cannot be cancelled/modified after its validity is over")
        )


def validate_e_waybill_log(doc):
    e_waybill_doc = frappe.db.get_value(
        "e-Waybill Log",
        doc.ewaybill,
        ["is_latest_data", "data", "qr_base64", "e_waybill_number"],
        as_dict=1,
    )

    if not e_waybill_doc:
        frappe.throw(
            _("e-Waybill not found. Did you generate it using e-Waybill API's?")
        )

    e_waybill_doc.doctype = doc.doctype

    return e_waybill_doc


########################################################################################################################
### e-Waybill Data Generation ##########################################################################################
########################################################################################################################


class EWaybillData(GSTInvoiceData):
    def __init__(self, doc):
        super().__init__(doc)

    def get_e_waybill_data(self):
        self.pre_validate_invoice()
        self.get_item_list()
        self.get_invoice_details()
        self.get_transporter_details()
        self.get_party_address_details()

        ewb_data = self.get_invoice_map()
        return json.loads(ewb_data)

    def pre_validate_invoice(self):
        """
        Validates:
        - Ewaybill already exists
        - Required fields
        - Atleast one item with HSN for goods is required
        - Basic transporter details must be present
        - Max 250 Items
        """
        super().pre_validate_invoice()

        # TODO: Validate with e-Waybill settings
        # TODO: Add Support for Delivery Note

        if self.doc.get("ewaybill"):
            frappe.throw(_("E-Waybill already generated for this invoice"))

        reqd_fields = [
            "company_gstin",
            "company_address",
            "customer_address",
        ]

        for fieldname in reqd_fields:
            if not self.doc.get(fieldname):
                frappe.throw(
                    _("{} is required to generate e-Waybill JSON").format(
                        frappe.unscrub(fieldname)
                    ),
                    exc=frappe.MandatoryError,
                )

        # Atleast one item with HSN code of goods is required
        doc_with_goods = False
        for item in self.doc.items:
            if not item.gst_hsn_code.startswith("99"):
                doc_with_goods = True
                break
        if not doc_with_goods:
            frappe.throw(
                msg=_(
                    "e-Waybill cannot be generated as all items are with service HSN"
                    " codes"
                ),
                title=_("Invalid Data"),
            )

        if self.doc.get("is_return") and self.doc.get("gst_category") == "Overseas":
            frappe.throw(
                msg=_("Return/Credit Note is not supported for Overseas e-Waybill"),
                title=_("Invalid Data"),
            )

        transport_mode = self.doc.get("mode_of_transport")
        if not self.doc.get("gst_transporter_id"):
            if not transport_mode:
                frappe.throw(
                    msg=_(
                        "Transporter or Mode of Transport is required to generate"
                        " e-Waybill"
                    ),
                    title=_("Invalid Data"),
                )
            elif transport_mode == "Road" and not self.doc.get("vehicle_no"):
                frappe.throw(
                    msg=_("Vehicle Number is required to generate e-Waybill"),
                    title=_("Invalid Data"),
                )
            elif (
                transport_mode == "Ship"
                and not self.doc.get("vehicle_no")
                and not self.doc.get("lr_no")
            ):
                frappe.throw(
                    msg=_(
                        "Vehicle Number and L/R No is required to generate e-Waybill"
                    ),
                    title=_("Invalid Data"),
                )
            elif transport_mode in ["Rail", "Air"] and not self.doc.get("lr_no"):
                frappe.throw(
                    msg=_("L/R No. is required to generate e-Waybill"),
                    title=_("Invalid Data"),
                )
        else:
            missing_transport_details = (
                not transport_mode
                or transport_mode == "Road"
                and not self.doc.get("vehicle_no")
                or (transport_mode == "Ship")
                and not self.doc.get("vehicle_no")
                and not self.doc.get("lr_no")
                or transport_mode in ["Rail", "Air"]
                and not self.doc.get("lr_no")
            )
            if missing_transport_details:
                self.generate_part_a = True

        if len(self.doc.items) > 250:
            # TODO: Add support for HSN Summary
            frappe.throw(
                msg=_("e-Waybill cannot be generated for more than 250 items"),
                title=_("Invalid Data"),
            )

    def update_invoice_details(self):
        super().update_invoice_details()

        self.invoice_details.update(
            {
                "supply_type": "O",
                "sub_supply_type": 1,
                "document_type": "INV",
                "main_hsn_code": self.doc.items[0].get(
                    "gst_hsn_code"
                ),  # instead get first HSN code with goods
            }
        )

        if self.doc.is_return:
            self.invoice_details.update(
                {"supply_type": "I", "sub_supply_type": 7, "document_type": "CHL"}
            )

        elif self.doc.gst_category == "Overseas":
            self.invoice_details.sub_supply_type = 3

            if self.doc.export_type == "With Payment of Tax":
                self.invoice_details.document_type = "BIL"

    def get_party_address_details(self):
        transaction_type = 1
        billTo_shipTo = self.doc.customer_address != (
            self.doc.get("shipping_address_name") or self.doc.customer_address
        )
        billFrom_dispatchFrom = self.doc.company_address != (
            self.doc.get("dispatch_address_name") or self.doc.company_address
        )
        self.billing_address = self.shipping_address = self.get_address_details(
            self.doc.customer_address
        )
        self.company_address = self.dispatch_address = self.get_address_details(
            self.doc.company_address
        )

        if billTo_shipTo and billFrom_dispatchFrom:
            transaction_type = 4
            self.shipping_address = self.get_address_details(
                self.doc.shipping_address_name
            )
            self.dispatch_address = self.get_address_details(
                self.doc.dispatch_address_name
            )
        elif billFrom_dispatchFrom:
            transaction_type = 3
            self.dispatch_address = self.get_address_details(
                self.doc.dispatch_address_name
            )
        elif billTo_shipTo:
            transaction_type = 2
            self.shipping_address = self.get_address_details(
                self.doc.shipping_address_name
            )

        self.invoice_details.update(
            {
                "transaction_type": transaction_type,
            }
        )

        if self.doc.gst_category == "SEZ":
            self.billing_address.state_code = 96

    def get_invoice_map(self):
        if self.sandbox:
            self.invoice_details.update(
                {
                    "company_gstin": "05AAACG2115R1ZN",
                    "docNo": random_string(6),
                }
            )
            self.company_address.gstin = "05AAACG2115R1ZN"
            self.billing_address.gstin = "05AAACG2140A1ZL"

        data = f"""
        {{
            "userGstin": "{self.invoice_details.company_gstin}",
            "supplyType": "{self.invoice_details.supply_type}",
            "subSupplyType": {self.invoice_details.sub_supply_type},
            "subSupplyDesc":"",
            "docType": "{self.invoice_details.document_type}",
            "docNo": "{self.invoice_details.invoice_number}",
            "docDate": "{self.invoice_details.invoice_date}",
            "transactionType": {self.invoice_details.transaction_type},
            "fromTrdName": "{self.company_address.address_title}",
            "fromGstin": "{self.company_address.gstin}",
            "fromAddr1": "{self.dispatch_address.address_line1}",
            "fromAddr2": "{self.dispatch_address.address_line2}",
            "fromPlace": "{self.dispatch_address.city}",
            "fromPincode": {self.dispatch_address.pincode},
            "fromStateCode": {self.company_address.state_code},
            "actFromStateCode": {self.dispatch_address.state_code},
            "toTrdName": "{self.billing_address.address_title}",
            "toGstin": "{self.billing_address.gstin}",
            "toAddr1": "{self.shipping_address.address_line1}",
            "toAddr2": "{self.shipping_address.address_line2}",
            "toPlace": "{self.shipping_address.city}",
            "toPincode": {self.shipping_address.pincode},
            "toStateCode": {self.billing_address.state_code},
            "actToStateCode": {self.shipping_address.state_code},
            "totalValue": {self.invoice_details.base_total},
            "cgstValue": {self.invoice_details.total_cgst_amount},
            "sgstValue": {self.invoice_details.total_sgst_amount},
            "igstValue": {self.invoice_details.total_igst_amount},
            "cessValue": {self.invoice_details.total_cess_amount},
            "TotNonAdvolVal": {self.invoice_details.total_cess_non_advol_amount},
            "OthValue": {self.invoice_details.rounding_adjustment + self.invoice_details.other_charges},
            "totInvValue": {self.invoice_details.base_grand_total},
            "transMode": {self.invoice_details.mode_of_transport},
            "transDistance": {self.invoice_details.distance},
            "transporterName": "{self.invoice_details.transporter_name}",
            "transporterId": "{self.invoice_details.gst_transporter_id}",
            "transDocNo": "{self.invoice_details.lr_no}",
            "transDocDate": "{self.invoice_details.lr_date_str}",
            "vehicleNo": "{self.invoice_details.vehicle_no}",
            "vehicleType": "{self.invoice_details.vehicle_type}",
            "itemList": [{self.item_list}],
            "mainHsnCode": "{self.invoice_details.main_hsn_code}"
        }}"""

        if self.json_download:
            different_keys = {  # keys that are different in json_download
                "transactionType": "transType",
                "actFromStateCode": "actualFromStateCode",
                "actToStateCode": "actualToStateCode",
            }
            for key, value in different_keys.items():
                data = data.replace(key, value)

        return data

    def get_item_map(self):
        return f"""
        {{
            "itemNo": {self.item_details.item_no},
            "productName": "",
            "productDesc": "{self.item_details.item_name}",
            "hsnCode": "{self.item_details.hsn_code}",
            "qtyUnit": "{self.item_details.uom}",
            "quantity": {self.item_details.qty},
            "taxableAmount": {self.item_details.taxable_value},
            "sgstRate": {self.item_details.sgst_rate},
            "cgstRate": {self.item_details.cgst_rate},
            "igstRate": {self.item_details.igst_rate},
            "cessRate": {self.item_details.cess_rate},
            "cessNonAdvol": {self.item_details.cess_non_advol_rate}
        }}"""
