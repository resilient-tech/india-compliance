import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, get_fullname, random_string
from frappe.utils.file_manager import save_file

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.api_classes.e_waybill import EWaybillAPI
from india_compliance.gst_india.constants.e_waybill import (
    CANCEL_REASON_CODES,
    UPDATE_VEHICLE_REASON_CODES,
)
from india_compliance.gst_india.utils import (
    load_doc,
    parse_datetime,
    send_updated_doc,
    update_onload,
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
def generate_e_waybill(*, docname, values=None):
    doc = load_doc("Sales Invoice", docname, "submit")
    if values:
        update_invoice(doc, frappe.parse_json(values))

    _generate_e_waybill(doc, throw=True if values else False)


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
        return

    api = EWaybillAPI if not doc.get("irn") else EInvoiceAPI
    result = api(doc.company_gstin).generate_e_waybill(data)
    log_and_process_e_waybill_generation(doc, result)

    frappe.msgprint(
        _("e-Waybill generated successfully")
        if result.validUpto
        else _("e-Waybill (Part A) generated successfully"),
        indicator="green",
        alert=True,
    )

    return send_updated_doc(doc)


def log_and_process_e_waybill_generation(doc, result):
    """Separate function, since called in backend from e-invoice utils"""

    irn = doc.get("irn")
    e_waybill_number = str(result["ewayBillNo" if not irn else "EwbNo"])
    doc.db_set("ewaybill", e_waybill_number)

    log_and_process_e_waybill(
        doc,
        {
            "e_waybill_number": e_waybill_number,
            "created_on": parse_datetime(
                result.get("ewayBillDate" if not irn else "EwbDt", day_first=not irn)
            ),
            "valid_upto": parse_datetime(
                result.get(
                    "validUpto" if not irn else "EwbValidTill", day_first=not irn
                )
            ),
            "reference_name": doc.name,
        },
        fetch=frappe.get_cached_value(
            "GST Settings", "GST Settings", "fetch_e_waybill_data"
        ),
    )


@frappe.whitelist()
def cancel_e_waybill(*, docname, values):
    doc = load_doc("Sales Invoice", docname, "cancel")
    values = frappe.parse_json(values)
    _cancel_e_waybill(doc, values)

    return send_updated_doc(doc)


def _cancel_e_waybill(doc, values):
    """Separate function, since called in backend from e-invoice utils"""

    data = EWaybillData(doc).get_e_waybill_cancel_data(values)
    api = EWaybillAPI if not doc.get("irn") else EInvoiceAPI
    result = api(doc.company_gstin).cancel_e_waybill(data)
    doc.db_set("ewaybill", "")

    frappe.msgprint(
        _("e-Waybill cancelled successfully"),
        indicator="green",
        alert=True,
    )

    log_and_process_e_waybill(
        doc,
        {
            "name": doc.ewaybill,
            "is_cancelled": 1,
            "cancel_reason_code": CANCEL_REASON_CODES[values.reason],
            "cancel_remark": values.remark if values.remark else values.reason,
            "cancelled_on": parse_datetime(result.cancelDate, day_first=True),
        },
    )


@frappe.whitelist()
def update_vehicle_info(*, docname, values):
    doc = load_doc("Sales Invoice", docname, "submit")
    doc.db_set(
        {
            "vehicle_no": values.vehicle_no.replace(" ", ""),
            "lr_no": values.lr_no,
            "lr_date": values.lr_date,
            "mode_of_transport": values.mode_of_transport,
            "gst_vehicle_type": values.gst_vehicle_type,
        }
    )

    values = frappe.parse_json(values)
    data = EWaybillData(doc).get_update_vehicle_data(values)
    result = EWaybillAPI(doc.company_gstin).update_vehicle_info(data)

    frappe.msgprint(
        _("Vehicle Info updated successfully"),
        indicator="green",
        alert=True,
    )

    comment = _(
        "Vehicle Info has been updated by {user}.<br><br> New details are: <br>"
    ).format(user=frappe.bold(get_fullname()))

    values_in_comment = {
        "Vehicle No": values.vehicle_no,
        "LR No": values.lr_no,
        "LR Date": values.lr_date,
        "Mode of Transport": values.mode_of_transport,
        "GST Vehicle Type": values.gst_vehicle_type,
    }

    for key, value in values_in_comment.items():
        if value:
            comment += "{0}: {1} <br>".format(frappe.bold(_(key)), value)

    log_and_process_e_waybill(
        doc,
        {
            "name": doc.ewaybill,
            "is_latest_data": 0,
            "valid_upto": parse_datetime(result.validUpto, day_first=True),
        },
        fetch=values.update_e_waybill_data,
        comment=comment,
    )

    return send_updated_doc(doc)


@frappe.whitelist()
def update_transporter(*, docname, values):
    doc = load_doc("Sales Invoice", docname, "submit")
    values = frappe.parse_json(values)
    data = EWaybillData(doc).get_update_transporter_data(values)
    EWaybillAPI(doc.company_gstin).update_transporter(data)

    frappe.msgprint(
        _("Transporter Info updated successfully"),
        indicator="green",
        alert=True,
    )

    # Transporter Name can be different from Transporter
    transporter_name = (
        frappe.db.get_value("Supplier", values.transporter, "supplier_name")
        if values.transporter
        else None
    )

    doc.db_set(
        {
            "transporter": values.transporter,
            "transporter_name": transporter_name,
            "gst_transporter_id": values.gst_transporter_id,
        }
    )

    comment = (
        "Transporter Info has been updated by {user}. New Transporter ID is"
        " {transporter_id}."
    ).format(
        user=frappe.bold(get_fullname()),
        transporter_id=frappe.bold(values.gst_transporter_id),
    )

    log_and_process_e_waybill(
        doc,
        {
            "name": doc.ewaybill,
            "is_latest_data": 0,
        },
        fetch=values.update_e_waybill_data,
        comment=comment,
    )

    return send_updated_doc(doc)


#######################################################################################
### e-Waybill Print and Attach Functions ##############################################
#######################################################################################


@frappe.whitelist()
def fetch_e_waybill_data(*, docname, attach=False):
    doc = load_doc("Sales Invoice", docname, "write" if attach else "print")

    log = frappe.get_doc("e-Waybill Log", doc.ewaybill)
    if not log.is_latest_data:
        _fetch_e_waybill_data(doc, log)

    if not attach:
        return

    attach_e_waybill_pdf(doc, log)

    frappe.msgprint(
        _("e-Waybill PDF attached successfully"),
        indicator="green",
        alert=True,
    )

    return send_updated_doc(doc, set_docinfo=True)


def _fetch_e_waybill_data(doc, log):
    result = EWaybillAPI(doc.company_gstin).get_e_waybill(log.e_waybill_number)
    log.db_set(
        {
            "data": frappe.as_json(result, indent=4),
            "is_latest_data": 1,
        }
    )


def attach_e_waybill_pdf(doc, log=None):
    if log:
        # to avoid get_doc when printing
        doc._e_waybill_log = log

    pdf_content = frappe.get_print(
        doc.doctype, doc.name, "e-Waybill", doc=doc, no_letterhead=True, as_pdf=True
    )

    # remove temporary attribute
    doc.__dict__.pop("_e_waybill_log", None)

    pdf_filename = f"e-Waybill_{doc.ewaybill}.pdf"
    delete_file(doc, pdf_filename)
    save_file(pdf_filename, pdf_content, doc.doctype, doc.name, is_private=1)

    if not frappe.request:
        # trigger reload_doc if called in background
        frappe.publish_realtime(
            "e_waybill_pdf_attached",
            doctype=doc.doctype,
            docname=doc.name,
        )


def delete_file(doc, filename):
    for file in frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": doc.doctype,
            "attached_to_name": doc.name,
            "file_name": filename,
        },
        pluck="name",
    ):
        frappe.delete_doc("File", file, force=True)


#######################################################################################
### Other Utility Functions ###########################################################
#######################################################################################


def log_and_process_e_waybill(doc, log_data, fetch=False, comment=None):
    frappe.enqueue(
        _log_and_process_e_waybill,
        queue="short",
        at_front=True,
        doc=doc,
        log_data=log_data,
        fetch=fetch,
        comment=comment,
    )

    update_onload(doc, "e_waybill_info", log_data)


def _log_and_process_e_waybill(doc, log_data, fetch=False, comment=None):
    ### Log e-Waybill

    #  fallback to e-Waybill number to avoid duplicate entry error
    log_name = log_data.pop("name", log_data.get("e_waybill_number"))
    try:
        log = frappe.get_doc("e-Waybill Log", log_name)
    except frappe.DoesNotExistError:
        log = frappe.new_doc("e-Waybill Log")
        frappe.clear_last_message()

    log.update(log_data)
    log.save(ignore_permissions=True)

    if comment:
        log.add_comment(text=comment)

    ### Fetch Data

    if not fetch:
        return

    _fetch_e_waybill_data(doc, log)
    frappe.db.commit()

    ### Attach PDF

    if not frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        "attach_e_waybill_print",
    ):
        return

    attach_e_waybill_pdf(doc, log)


def update_invoice(doc, values):
    transporter_name = (
        frappe.db.get_value("Supplier", values.transporter, "supplier_name")
        if values.transporter
        else None
    )

    doc.db_set(
        {
            "transporter": values.transporter,
            "transporter_name": transporter_name,
            "gst_transporter_id": values.gst_transporter_id,
            "vehicle_no": values.vehicle_no,
            "distance": values.distance,
            "lr_no": values.lr_no,
            "lr_date": values.lr_date,
            "mode_of_transport": values.mode_of_transport,
            "gst_vehicle_type": values.gst_vehicle_type,
            "gst_category": values.gst_category,
            "export_type": values.export_type,
        },
    )


#######################################################################################
### e-Waybill Data Generation #########################################################
#######################################################################################


class EWaybillData(GSTInvoiceData):
    def __init__(self, *args, **kwargs):
        self.for_json = kwargs.pop("for_json", False)
        super().__init__(*args, **kwargs)

        self.validate_settings()
        self.validate_doctype_for_e_waybill()

    def get_data(self):
        self.validate_invoice()
        self.get_transporter_details()

        if irn := self.doc.get("irn"):
            # Via e-Invoice
            return self.sanitize_data(
                {
                    "Irn": irn,
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
        self.validate_if_e_waybill_is_set()
        self.validate_if_ewaybill_can_be_cancelled()

        return {
            "ewbNo": self.doc.ewaybill,
            "cancelRsnCode": CANCEL_REASON_CODES[values.reason],
            "cancelRmrk": values.remark if values.remark else values.reason,
        }

    def get_update_vehicle_data(self, values):
        self.validate_if_e_waybill_is_set()
        self.check_e_waybill_validity()
        self.validate_mode_of_transport()
        self.get_transporter_details()

        dispatch_address_name = (
            self.doc.dispatch_address_name
            if self.doc.dispatch_address_name
            else self.doc.company_address
        )
        dispatch_address = self.get_address_details(dispatch_address_name)

        return {
            "ewbNo": self.doc.ewaybill,
            "vehicleNo": self.invoice_details.vehicle_no,
            "fromPlace": dispatch_address.city,
            "fromState": dispatch_address.state_number,
            "reasonCode": UPDATE_VEHICLE_REASON_CODES[values.reason],
            "reasonRem": self.sanitize_value(values.remark),
            "transDocNo": self.invoice_details.lr_no,
            "transDocDate": self.invoice_details.lr_date,
            "transMode": self.invoice_details.mode_of_transport,
            "vehicleType": self.invoice_details.vehicle_type,
        }

    def get_update_transporter_data(self, values):
        self.validate_if_e_waybill_is_set()
        self.check_e_waybill_validity()

        return {
            "ewbNo": self.doc.ewaybill,
            "transporterId": values.gst_transporter_id,
        }

    def validate_invoice(self):
        # TODO: Add Support for Delivery Note

        super().validate_invoice()

        if self.doc.ewaybill:
            frappe.throw(_("e-Waybill already generated for this document"))

        self.validate_applicability()

    def validate_settings(self):
        if not self.settings.enable_e_waybill:
            frappe.throw(_("Please enable e-Waybill in GST Settings"))

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
                        _(self.doc.meta.get_label(fieldname))
                    ),
                    exc=frappe.MandatoryError,
                )

        # Atleast one item with HSN code of goods is required
        for item in self.doc.items:
            if not item.gst_hsn_code.startswith("99"):
                break

        else:
            frappe.throw(
                _(
                    "e-Waybill cannot be generated because all items have service HSN"
                    " codes"
                ),
                title=_("Invalid Data"),
            )

        # TODO: check if this validation is required
        # if self.doc.is_return and self.doc.gst_category == "Overseas":
        #     frappe.throw(
        #         msg=_("Return/Credit Note is not supported for Overseas e-Waybill"),
        #         title=_("Incorrect Usage"),
        #     )

        if not self.doc.gst_transporter_id:
            self.validate_mode_of_transport()

        if self.doc.base_grand_total < self.settings.e_waybill_threshold:
            frappe.throw(
                _("e-Waybill is only applicable for Invoice Value above {0}").format(
                    self.settings.e_waybill_threshold
                )
            )

        # TODO: Add support for HSN Summary
        item_limit = 1000 if self.doc.get("irn") else 250
        if len(self.doc.items) > item_limit:
            frappe.throw(
                _("e-Waybill cannot be generated for more than {0} items").format(
                    item_limit
                ),
                title=_("Invalid Data"),
            )

        self.validate_non_gst_items()

    def validate_doctype_for_e_waybill(self):
        if self.doc.doctype not in ("Sales Invoice", "Delivery Note"):
            frappe.throw(
                _(
                    "Only Sales Invoice and Delivery Note are supported for e-Waybill"
                    " actions"
                )
            )

    def validate_if_e_waybill_is_set(self):
        if not self.doc.ewaybill:
            frappe.throw(_("No e-Waybill found for this document"))

    def check_e_waybill_validity(self):
        # this works because we do run_onload in load_doc above
        valid_upto = self.doc.get_onload().get("e_waybill_info", {}).get("valid_upto")

        if valid_upto and get_datetime(valid_upto) < get_datetime():
            frappe.throw(_("e-Waybill cannot be modified after its validity is over"))

    def validate_if_ewaybill_can_be_cancelled(self):
        cancel_upto = add_to_date(
            # this works because we do run_onload in load_doc above
            get_datetime(
                self.doc.get_onload().get("e_waybill_info", {}).get("created_on")
            ),
            days=1,
            as_datetime=True,
        )

        if cancel_upto < get_datetime():
            frappe.throw(
                _("e-Waybill can be cancelled only within 24 Hours of its generation")
            )

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
        has_different_shipping_address = (
            self.doc.shipping_address_name
            and self.doc.customer_address != self.doc.shipping_address_name
        )

        has_different_dispatch_address = (
            self.doc.dispatch_address_name
            and self.doc.company_address != self.doc.dispatch_address_name
        )

        self.billing_address = self.get_address_details(self.doc.customer_address)
        self.company_address = self.get_address_details(self.doc.company_address)

        # Defaults
        self.shipping_address = self.billing_address
        self.dispatch_address = self.company_address

        if has_different_shipping_address and has_different_dispatch_address:
            transaction_type = 4
            self.shipping_address = self.get_address_details(
                self.doc.shipping_address_name
            )
            self.dispatch_address = self.get_address_details(
                self.doc.dispatch_address_name
            )

        elif has_different_dispatch_address:
            transaction_type = 3
            self.dispatch_address = self.get_address_details(
                self.doc.dispatch_address_name
            )

        elif has_different_shipping_address:
            transaction_type = 2
            self.shipping_address = self.get_address_details(
                self.doc.shipping_address_name
            )

        self.invoice_details.transaction_type = transaction_type

        if self.doc.gst_category == "SEZ":
            self.billing_address.state_number = 96

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
            "fromStateCode": self.company_address.state_number,
            "actFromStateCode": self.dispatch_address.state_number,
            "toTrdName": self.billing_address.address_title,
            "toGstin": self.billing_address.gstin,
            "toAddr1": self.shipping_address.address_line1,
            "toAddr2": self.shipping_address.address_line2,
            "toPlace": self.shipping_address.city,
            "toPincode": self.shipping_address.pincode,
            "toStateCode": self.billing_address.state_number,
            "actToStateCode": self.shipping_address.state_number,
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
            for key, value in (
                # keys that are different in for_json
                {
                    "transactionType": "transType",
                    "actFromStateCode": "actualFromStateCode",
                    "actToStateCode": "actualToStateCode",
                }
            ).items():
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
