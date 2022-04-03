import re
from datetime import datetime

import pyqrcode

import frappe
from frappe import _
from frappe.utils import getdate, random_string
from frappe.utils.file_manager import save_file

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.api_classes.e_waybill import EWaybillAPI
from india_compliance.gst_india.constants.e_waybill import (
    DATETIME_FORMAT,
    ERROR_CODES,
    TRANSPORT_MODES,
    VEHICLE_TYPES,
)
from india_compliance.gst_india.utils.invoice_data import GSTInvoiceData

#######################################################################################
### Manual JSON Generation for e-Waybill ##############################################
#######################################################################################


@frappe.whitelist()
def generate_e_waybill_json(doctype: str, docnames):
    docnames = frappe.parse_json(docnames) if docnames.startswith("[") else [docnames]
    ewb_data = {
        "version": "1.0.0621",
        "billLists": [],
    }

    for doc in docnames:
        doc = frappe.get_doc(doctype, doc)
        doc.check_permission("submit")
        ewb_data["billLists"].append(EWaybillData(doc, for_json=True).get_data())

    return frappe.as_json(ewb_data, indent=4)


#######################################################################################
### e-Waybill Generation and Modification using APIs ##################################
#######################################################################################


@frappe.whitelist()
def auto_generate_e_waybill(*, docname):
    doc = frappe.get_doc("Sales Invoice", docname)
    doc.check_permission("submit")

    _generate_e_waybill(doc, throw=False)


@frappe.whitelist()
def generate_e_waybill(*, docname, values):
    doc = frappe.get_doc("Sales Invoice", docname)
    doc.check_permission("submit")

    update_invoice(doc, frappe.parse_json(values))
    _generate_e_waybill(doc)


def _generate_e_waybill(doc, throw=True):
    try:
        data = EWaybillData(doc).get_data()

    except frappe.ValidationError as e:
        if throw:
            raise e

        frappe.clear_last_message()
        frappe.msgprint(
            _(
                "e-Waybill auto-generation failed with error:<br>{0}<br><br>"
                "Please rectify this issue and generate e-Waybill manually."
            ).format(str(e)),
            _("Warning"),
            indicator="yellow",
        )
        return False

    result = EWaybillAPI(doc.company_gstin).generate_e_waybill(data)

    e_waybill = str(result.get("ewayBillNo"))
    doc.db_set("ewaybill", e_waybill)

    frappe.publish_realtime(
        "e_waybill_generated",
        {"doctype": doc.doctype, "docname": doc.name, "alert": result.alert},
    )

    e_waybill_date = datetime.strptime(result.get("ewayBillDate"), DATETIME_FORMAT)
    valid_upto = None
    if result.get("validUpto"):
        valid_upto = datetime.strptime(result.get("validUpto"), DATETIME_FORMAT)

    log_values = {
        "e_waybill_number": e_waybill,
        "e_waybill_date": e_waybill_date,
        "valid_upto": valid_upto,
        "reference_name": doc.name,
    }
    create_or_update_e_waybill_log(doc, None, log_values)
    print_e_waybill_as_per_settings(doc)


def log_and_process_e_waybill():
    pass


@frappe.whitelist()
def cancel_e_waybill(*, docname, values):
    doc = frappe.get_doc("Sales Invoice", docname)
    doc.check_permission("submit")

    values = frappe.parse_json(values)
    data = EWaybillData(doc).get_e_waybill_cancel_data(values)
    result = EWaybillAPI(doc.company_gstin).cancel_e_waybill(data)
    _cancel_e_waybill(doc, values, result)


def _cancel_e_waybill(doc, values, result):
    frappe.publish_realtime(
        "e_waybill_cancelled",
        {
            "doctype": doc.doctype,
            "docname": doc.name,
            "alert": "e-waybill Cancelled Successfully",
        },
    )

    dt_values = {
        "ewaybill": None,
    }
    log_values = {
        "name": doc.ewaybill,
        "is_cancelled": 1,
        "cancel_reason_code": ERROR_CODES[values.reason],
        "cancel_remark": values.remark if values.remark else values.reason,
        "cancel_date": datetime.strptime(result.get("cancelDate"), DATETIME_FORMAT),
    }

    create_or_update_e_waybill_log(doc, dt_values, log_values)


@frappe.whitelist()
def update_vehicle_info(*, docname, values):
    doc = frappe.get_doc("Sales Invoice", docname)
    doc.check_permission("submit")

    values = frappe.parse_json(values)
    data = EWaybillData(doc).get_update_vehicle_data(values)
    result = EWaybillAPI(doc.company_gstin).update_vehicle_info(data)
    frappe.publish_realtime(
        "vehicle_info_updated",
        {
            "doctype": doc.doctype,
            "docname": doc.name,
            "alert": "Vehicle Information Updated Successfully",
        },
    )

    doc_values = {
        "vehicle_no": values.vehicle_no.replace(" ", ""),
        "lr_no": values.lr_no,
        "lr_date": values.lr_date,
        "mode_of_transport": values.mode_of_transport,
        "gst_vehicle_type": values.gst_vehicle_type,
    }
    log_values = {
        "name": doc.ewaybill,
        "is_latest_data": 0,
        "valid_upto": datetime.strptime(result.get("validUpto"), DATETIME_FORMAT),
    }
    comment = (
        f"{frappe.session.user} updated vehicle info for e-waybill. New details are: \n"
        f" Vehicle No: {values.get('vehicle_no')} \n LR No: {values.get('lr_no')} \n LR"
        f" Date: {values.get('lr_date')} \n Mode of Transport:"
        f" {values.get('mode_of_transport')} \n GST Vehicle Type:"
        f" {values.get('gst_vehicle_type')}"
    )
    create_or_update_e_waybill_log(doc, doc_values, log_values, comment)

    if values.update_e_waybill_data:
        print_e_waybill_as_per_settings(doc, force_get_data=True)


@frappe.whitelist()
def update_transporter(*, docname, values):
    doc = frappe.get_doc("Sales Invoice", docname)
    doc.check_permission("submit")

    values = frappe.parse_json(values)
    data = EWaybillData(doc).get_update_transporter_data(values)
    result = EWaybillAPI(doc.company_gstin).update_transporter(data)
    frappe.publish_realtime(
        "transporter_info_updated",
        {
            "doctype": doc.doctype,
            "docname": doc.name,
            "alert": "Transporter Updated Successfully",
        },
    )

    # transporter_name can be different from transporter
    transporter_name = (
        frappe.db.get_value("Supplier", values.transporter, "supplier_name")
        if values.transporter
        else None
    )
    doc_values = {
        "transporter": values.transporter,
        "transporter_name": transporter_name,
        "gst_transporter_id": values.gst_transporter_id,
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

    if values.update_e_waybill_data:
        print_e_waybill_as_per_settings(doc, force_get_data=True)


#######################################################################################
### e-Waybill Print and Attach Functions ##############################################
#######################################################################################


def print_e_waybill_as_per_settings(doc, force_get_data=False):
    get_data, attach = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("fetch_e_waybill_data", "attach_e_waybill_print"),
    )
    if attach:
        _attach_or_print_e_waybill(doc, "attach")
    elif get_data or force_get_data:
        _attach_or_print_e_waybill(doc)


@frappe.whitelist()
def attach_or_print_e_waybill(docname, action):
    doc = frappe.get_doc("Sales Invoice", docname)
    doc.check_permission("submit")

    ewb = EWaybillData(doc)
    ewb.validate_settings()
    ewb.validate_doctype_for_e_waybill()
    ewb.validate_if_e_waybill_is_available()
    e_waybill_doc = ewb.validate_e_waybill_log(doc)
    _attach_or_print_e_waybill(doc, action, e_waybill_doc)


def _attach_or_print_e_waybill(doc, action=None, e_waybill_doc=None):
    if not e_waybill_doc or not e_waybill_doc.is_latest_data or not e_waybill_doc.data:
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
    e_waybill_date = datetime.strptime(result.ewayBillDate, DATETIME_FORMAT)
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
            "data": frappe.as_json(result, indent=4),
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


#######################################################################################
### Other Utility Functions ###########################################################
#######################################################################################


def create_or_update_e_waybill_log(doc, doc_values, log_values, comment=None):
    if doc_values:
        frappe.db.set_value(doc.doctype, doc.name, doc_values)

    if frappe.db.exists("e-Waybill Log", doc.ewaybill):
        # Handle Duplicate IRN
        return
    elif "name" in log_values:
        e_waybill_doc = frappe.get_doc("e-Waybill Log", log_values.pop("name"))
    else:
        e_waybill_doc = frappe.get_doc({"doctype": "e-Waybill Log"})

    e_waybill_doc.update(log_values)
    e_waybill_doc.save(ignore_permissions=True)

    if comment:
        e_waybill_doc.add_comment(text=comment)


def update_invoice(doc, data):
    transporter_name = (
        frappe.db.get_value("Supplier", data.transporter, "supplier_name")
        if data.transporter
        else None
    )

    doc.db_set(
        {
            "transporter": data.transporter,
            "transporter_name": transporter_name,
            "gst_transporter_id": data.gst_transporter_id,
            "vehicle_no": data.vehicle_no,
            "distance": data.distance,
            "lr_no": data.lr_no,
            "lr_date": data.lr_date,
            "mode_of_transport": data.mode_of_transport,
            "gst_vehicle_type": data.gst_vehicle_type,
            "gst_category": data.gst_category,
            "export_type": data.export_type,
        },
    )


#######################################################################################
### e-Waybill Data Generation #########################################################
#######################################################################################


class EWaybillData(GSTInvoiceData):
    def __init__(self, *args, **kwargs):
        self.for_json = kwargs.pop("for_json", False)
        super().__init__(*args, **kwargs)

    def get_data(self):
        self.validate_invoice()
        self.get_transporter_details()

        if self.doc.irn:
            return self.sanitize_data(
                {
                    "Irn": self.doc.irn,
                    "Distance": self.invoice_details.distance,
                    "TransMode": str(self.invoice_details.mode_of_transport),
                    "TransId": self.invoice_details.gst_transporter_id,
                    "TransName": self.invoice_details.transporter_name,
                    "TransDocDt": self.invoice_details.lr_date,
                    "TransDocNo": self.invoice_details.lr_no,
                    "VehNo": self.invoice_details.vehicle_no,
                    "VehType": self.invoice_details.vehicle_type,
                }
            )

        self.get_invoice_details()
        self.get_item_list()
        self.get_party_address_details()

        return self.get_invoice_data()

    def get_e_waybill_cancel_data(self, values):
        self.validate_doctype_for_e_waybill()
        self.validate_if_e_waybill_is_available(values)
        self.validate_e_waybill_validity()

        return {
            "ewbNo": self.doc.ewaybill,
            "cancelRsnCode": ERROR_CODES[values.reason],
            "cancelRmrk": values.remark if values.remark else values.reason,
        }

    def get_update_vehicle_data(self, values):
        self.validate_settings()
        self.validate_doctype_for_e_waybill()
        self.validate_if_e_waybill_is_available(values)
        self.validate_e_waybill_validity()

        dispatch_address = (
            self.doc.dispatch_address_name
            if self.doc.dispatch_address_name
            else self.doc.company_address
        )
        dispatch_address = frappe.get_doc("Address", dispatch_address)

        return {
            "ewbNo": self.doc.ewaybill,
            "vehicleNo": values.vehicle_no.replace(" ", ""),
            "fromPlace": dispatch_address.city,
            "fromState": dispatch_address.gst_state_number,
            "reasonCode": values.reason.split("-")[0],
            "reasonRem": values.remark,
            "transDocNo": values.lr_no,
            "transDocDate": frappe.utils.formatdate(values.lr_date, "dd/mm/yyyy"),
            "transMode": TRANSPORT_MODES.get(values.mode_of_transport),
            "vehicleType": VEHICLE_TYPES.get(values.gst_vehicle_type),
        }

    def get_update_transporter_data(self, values):
        self.validate_settings()
        self.validate_doctype_for_e_waybill()
        self.validate_if_e_waybill_is_available(values)
        self.validate_e_waybill_validity()
        return {
            "ewbNo": self.doc.ewaybill,
            "transporterId": values.gst_transporter_id,
        }

    def validate_invoice(self):
        super().validate_invoice()
        self.validate_if_e_waybill_is_available(available=False)
        self.validate_settings()
        self.validate_applicability()
        # TODO: Add Support for Delivery Note

    def validate_settings(self):
        if not self.settings.enable_e_waybill:
            frappe.throw(_("Please enable e-Waybill in GST Settings"))

        if not self.for_json and not self.settings.enable_api:
            frappe.throw(_("Please enable API in GST Settings"))

    def validate_applicability(self):
        """
        Validates:
        - Required fields
        - Atleast one item with HSN for goods is required
        - Overseas Returns are not allowed
        - Basic transporter details must be present
        - Grand Total Amount must be greater than Criteria
        - Max 250 Items
        """
        for fieldname in ("company_gstin", "company_address", "customer_address"):
            if not self.doc.get(fieldname):
                frappe.throw(
                    _("{0} is required to generate e-Waybill").format(
                        self.doc.meta.get_field(fieldname)
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

        if self.doc.is_return and self.doc.gst_category == "Overseas":
            frappe.throw(
                msg=_("Return/Credit Note is not supported for Overseas e-Waybill"),
                title=_("Invalid Data"),
            )

        if not self.doc.gst_transporter_id:
            self.validate_mode_of_transport()

        if self.doc.base_grand_total < self.settings.e_waybill_threshold:
            frappe.throw(
                _("e-Waybill is only applicable for invoices above {0}").format(
                    self.settings.e_waybill_threshold
                )
            )

        if len(self.doc.items) > 250:
            # TODO: Add support for HSN Summary
            frappe.throw(
                msg=_("e-Waybill cannot be generated for more than 250 items"),
                title=_("Invalid Data"),
            )

        self.validate_non_gst_items()

    def validate_doctype_for_e_waybill(self):
        if self.doc.doctype not in ("Sales Invoice", "Delivery Note"):
            frappe.throw(
                _(
                    "Only Sales Invoice and Delivery Note are supported for generating"
                    " e-Waybill"
                )
            )

    def validate_if_e_waybill_is_available(self, values=None, available=True):
        if not available:
            if self.doc.ewaybill:
                frappe.throw(_("e-Waybill already generated for this document"))
            return

        # e-Waybill should be available
        if not self.doc.ewaybill:
            frappe.throw(_("No e-Waybill found for this document"))

        if values and self.doc.ewaybill != values.ewaybill:
            frappe.throw(_("Invalid e-Waybill"))

    def validate_e_waybill_validity(self):
        # e_waybill_info = self.doc.get("__onload", {}).get("e_waybill_info")
        # if not e_waybill_info:
        e_waybill_info = frappe.get_value(
            "e-Waybill Log", self.doc.ewaybill, "valid_upto", as_dict=True
        )

        if (
            e_waybill_info["valid_upto"]
            and getdate(e_waybill_info["valid_upto"]) < getdate()
        ):
            frappe.throw(
                _("e-Waybill cannot be cancelled/modified after its validity is over")
            )

    def validate_e_waybill_log(self):
        e_waybill_doc = frappe.db.get_value(
            "e-Waybill Log",
            self.doc.ewaybill,
            ("is_latest_data", "data", "qr_base64", "e_waybill_number"),
            as_dict=1,
        )

        if not e_waybill_doc:
            frappe.throw(
                _(
                    "e-Waybill not found in e-Waybill Log. Did you generate it using"
                    " e-Waybill API's?"
                )
            )

        e_waybill_doc.doctype = self.doc.doctype

        return e_waybill_doc

    def update_invoice_details(self):
        # first HSN Code for goods
        main_hsn_code = next(
            row.gst_hsn_code
            for row in self.doc.items
            if not row.gst_hsn_code.startswith("99")
        )

        self.invoice_details.update(
            {
                "supply_type": "O",
                "sub_supply_type": 1,
                "document_type": "INV",
                "main_hsn_code": main_hsn_code,
            }
        )

        if self.doc.is_return:
            self.invoice_details.update(
                {
                    "supply_type": "I",
                    "sub_supply_type": 7,
                    "document_type": "CHL",
                }
            )

        elif self.doc.gst_category == "Overseas":
            self.invoice_details.sub_supply_type = 3

            if self.doc.export_type == "Without Payment of Tax":
                self.invoice_details.document_type = "BIL"

    def get_party_address_details(self):
        transaction_type = 1
        billTo_shipTo = self.doc.customer_address != (
            self.doc.shipping_address_name or self.doc.customer_address
        )
        billFrom_dispatchFrom = self.doc.company_address != (
            self.doc.dispatch_address_name or self.doc.company_address
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

    def get_invoice_data(self):
        if self.sandbox:
            self.invoice_details.update(
                {
                    "company_gstin": "05AAACG2115R1ZN",
                    "invoice_number": random_string(6),
                }
            )
            self.company_address.gstin = "05AAACG2115R1ZN"
            self.billing_address.gstin = "05AAACG2140A1ZL"

        data = {
            "userGstin": self.invoice_details.company_gstin,
            "supplyType": self.invoice_details.supply_type,
            "subSupplyType": self.invoice_details.sub_supply_type,
            "subSupplyDesc": "",
            "docType": self.invoice_details.document_type,
            "docNo": self.invoice_details.invoice_number,
            "docDate": self.invoice_details.invoice_date,
            "transactionType": self.invoice_details.transaction_type,
            "fromTrdName": self.company_address.address_title,
            "fromGstin": self.company_address.gstin,
            "fromAddr1": self.dispatch_address.address_line1,
            "fromAddr2": self.dispatch_address.address_line2,
            "fromPlace": self.dispatch_address.city,
            "fromPincode": self.dispatch_address.pincode,
            "fromStateCode": self.company_address.state_code,
            "actFromStateCode": self.dispatch_address.state_code,
            "toTrdName": self.billing_address.address_title,
            "toGstin": self.billing_address.gstin,
            "toAddr1": self.shipping_address.address_line1,
            "toAddr2": self.shipping_address.address_line2,
            "toPlace": self.shipping_address.city,
            "toPincode": self.shipping_address.pincode,
            "toStateCode": self.billing_address.state_code,
            "actToStateCode": self.shipping_address.state_code,
            "totalValue": self.invoice_details.base_total,
            "cgstValue": self.invoice_details.total_cgst_amount,
            "sgstValue": self.invoice_details.total_sgst_amount,
            "igstValue": self.invoice_details.total_igst_amount,
            "cessValue": self.invoice_details.total_cess_amount,
            "TotNonAdvolVal": self.invoice_details.total_cess_non_advol_amount,
            "OthValue": self.invoice_details.rounding_adjustment
            + self.invoice_details.other_charges,
            "totInvValue": self.invoice_details.base_grand_total,
            "transMode": self.invoice_details.mode_of_transport,
            "transDistance": self.invoice_details.distance,
            "transporterName": self.invoice_details.transporter_name,
            "transporterId": self.invoice_details.gst_transporter_id,
            "transDocNo": self.invoice_details.lr_no,
            "transDocDate": self.invoice_details.lr_date,
            "vehicleNo": self.invoice_details.vehicle_no,
            "vehicleType": self.invoice_details.vehicle_type,
            "itemList": self.item_list,
            "mainHsnCode": self.invoice_details.main_hsn_code,
        }

        if self.for_json:
            different_keys = {  # keys that are different in for_json
                "transactionType": "transType",
                "actFromStateCode": "actualFromStateCode",
                "actToStateCode": "actualToStateCode",
            }
            for key, value in different_keys.items():
                data[value] = data.pop(key)
        else:
            self.sanitize_data(data)

        return data

    def get_item_data(self, item_details):
        return {
            "itemNo": item_details.item_no,
            "productName": "",
            "productDesc": item_details.item_name,
            "hsnCode": item_details.hsn_code,
            "qtyUnit": item_details.uom,
            "quantity": item_details.qty,
            "taxableAmount": item_details.taxable_value,
            "sgstRate": item_details.sgst_rate,
            "cgstRate": item_details.cgst_rate,
            "igstRate": item_details.igst_rate,
            "cessRate": item_details.cess_rate,
            "cessNonAdvol": item_details.cess_non_advol_rate,
        }
