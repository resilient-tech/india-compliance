import os

import frappe
from frappe import _
from frappe.desk.form.load import get_docinfo
from frappe.utils import add_to_date, get_datetime, get_fullname, random_string
from frappe.utils.file_manager import save_file

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.api_classes.e_waybill import EWaybillAPI
from india_compliance.gst_india.constants.e_waybill import (
    CANCEL_REASON_CODES,
    ITEM_LIMIT,
    SUB_SUPPLY_TYPES,
    UPDATE_VEHICLE_REASON_CODES,
)
from india_compliance.gst_india.utils import (
    load_doc,
    parse_datetime,
    send_updated_doc,
    update_onload,
)
from india_compliance.gst_india.utils.transaction_data import GSTTransactionData

PERMITTED_DOCTYPES = {"Sales Invoice", "Delivery Note"}


#######################################################################################
### Manual JSON Generation for e-Waybill ##############################################
#######################################################################################


@frappe.whitelist()
def generate_e_waybill_json(doctype: str, docnames, values=None):
    docnames = frappe.parse_json(docnames) if docnames.startswith("[") else [docnames]
    ewb_data = {
        "version": "1.0.0621",
        "billLists": [],
    }

    for doc in docnames:
        doc = frappe.get_doc(doctype, doc)
        doc.check_permission("submit")

        if values:
            update_transaction(doc, frappe.parse_json(values))
            send_updated_doc(doc)

        ewb_data["billLists"].append(EWaybillData(doc, for_json=True).get_data())

    return frappe.as_json(ewb_data, indent=4)


#######################################################################################
### e-Waybill Generation and Modification using APIs ##################################
#######################################################################################


@frappe.whitelist()
def generate_e_waybill(*, doctype, docname, values=None):
    doc = load_doc(doctype, docname, "submit")
    if values:
        update_transaction(doc, frappe.parse_json(values))

    _generate_e_waybill(doc, throw=True if values else False)


def _generate_e_waybill(doc, throw=True):
    try:
        # Via e-Invoice API if not Return or Debit Note
        # Handles following error when generating e-Waybill using IRN:
        # 4010: E-way Bill cannot generated for Debit Note, Credit Note and Services
        with_irn = doc.get("irn") and not (doc.is_return or doc.is_debit_note)
        data = EWaybillData(doc).get_data(with_irn=with_irn)

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

    api = EWaybillAPI if not with_irn else EInvoiceAPI
    result = api(doc).generate_e_waybill(data)
    log_and_process_e_waybill_generation(doc, result, with_irn=with_irn)

    if not frappe.request:
        return

    frappe.msgprint(
        _("e-Waybill generated successfully")
        if result.validUpto or result.EwbValidTill
        else _("e-Waybill (Part A) generated successfully"),
        indicator="green",
        alert=True,
    )
    return send_updated_doc(doc)


def log_and_process_e_waybill_generation(doc, result, *, with_irn=False):
    """Separate function, since called in backend from e-invoice utils"""

    e_waybill_number = str(result["ewayBillNo" if not with_irn else "EwbNo"])

    data = {"ewaybill": e_waybill_number}
    if distance := result.get("distance"):
        data["distance"] = distance

    doc.db_set(data)

    log_and_process_e_waybill(
        doc,
        {
            "e_waybill_number": e_waybill_number,
            "created_on": parse_datetime(
                result.get("ewayBillDate" if not with_irn else "EwbDt"),
                day_first=not with_irn,
            ),
            "valid_upto": parse_datetime(
                result.get("validUpto" if not with_irn else "EwbValidTill"),
                day_first=not with_irn,
            ),
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
        },
        fetch=frappe.get_cached_value(
            "GST Settings", "GST Settings", "fetch_e_waybill_data"
        ),
    )


@frappe.whitelist()
def cancel_e_waybill(*, doctype, docname, values):
    doc = load_doc(doctype, docname, "cancel")
    values = frappe.parse_json(values)
    _cancel_e_waybill(doc, values)

    return send_updated_doc(doc)


def _cancel_e_waybill(doc, values):
    """Separate function, since called in backend from e-invoice utils"""

    e_waybill_data = EWaybillData(doc)
    api = (
        EInvoiceAPI
        # Use EInvoiceAPI only for sandbox environment
        # if e-Waybill has been created using IRN
        if (
            e_waybill_data.sandbox_mode
            and doc.get("irn")
            and not (doc.is_return or doc.is_debit_note)
        )
        else EWaybillAPI
    )

    result = api(doc).cancel_e_waybill(e_waybill_data.get_data_for_cancellation(values))

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

    doc.db_set("ewaybill", "")

    frappe.msgprint(
        _("e-Waybill cancelled successfully"),
        indicator="green",
        alert=True,
    )


@frappe.whitelist()
def update_vehicle_info(*, doctype, docname, values):
    doc = load_doc(doctype, docname, "submit")
    values = frappe.parse_json(values)
    doc.db_set(
        {
            "vehicle_no": values.vehicle_no.replace(" ", ""),
            "lr_no": values.lr_no,
            "lr_date": values.lr_date,
            "mode_of_transport": values.mode_of_transport,
            "gst_vehicle_type": values.gst_vehicle_type,
        }
    )

    data = EWaybillData(doc).get_update_vehicle_data(values)
    result = EWaybillAPI(doc).update_vehicle_info(data)

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
def update_transporter(*, doctype, docname, values):
    doc = load_doc(doctype, docname, "submit")
    values = frappe.parse_json(values)
    data = EWaybillData(doc).get_update_transporter_data(values)
    EWaybillAPI(doc).update_transporter(data)

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
def fetch_e_waybill_data(*, doctype, docname, attach=False):
    doc = load_doc(doctype, docname, "write" if attach else "print")
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


def _fetch_e_waybill_data(doc, log):
    result = EWaybillAPI(doc).get_e_waybill(log.e_waybill_number)
    log.db_set(
        {
            "data": frappe.as_json(result, indent=4),
            "is_latest_data": 1,
        }
    )


def attach_e_waybill_pdf(doc, log=None):
    pdf_content = frappe.get_print(
        "e-Waybill Log",
        doc.ewaybill,
        "e-Waybill",
        doc=log,
        no_letterhead=True,
        as_pdf=True,
    )

    pdf_filename = get_pdf_filename(doc.ewaybill)
    delete_file(doc, pdf_filename)
    save_file(pdf_filename, pdf_content, doc.doctype, doc.name, is_private=1)
    publish_pdf_update(doc)


def delete_file(doc, filename):
    filename, extn = os.path.splitext(filename)

    for file in frappe.get_all(
        "File",
        filters=[
            ["attached_to_doctype", "=", doc.doctype],
            ["attached_to_name", "=", doc.name],
            ["file_name", "like", f"{filename}%"],
            ["file_name", "like", f"%{extn}"],
        ],
        pluck="name",
    ):
        frappe.delete_doc("File", file, force=True, ignore_permissions=True)


def publish_pdf_update(doc, pdf_deleted=False):
    get_docinfo(doc)

    # if it's a request, frappe.response["docinfo"] will get synced automatically
    if frappe.request:
        return

    frappe.publish_realtime(
        "e_waybill_pdf_update",
        {
            "docinfo": frappe.response["docinfo"],
            "pdf_deleted": pdf_deleted,
        },
        doctype=doc.doctype,
        docname=doc.name,
    )


def get_pdf_filename(e_waybill_number):
    return f"e-Waybill_{e_waybill_number}.pdf"


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

    frappe.db.commit()

    if log.is_cancelled:
        delete_file(doc, get_pdf_filename(log.name))
        publish_pdf_update(doc, pdf_deleted=True)

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


def update_transaction(doc, values):
    transporter_name = (
        frappe.db.get_value("Supplier", values.transporter, "supplier_name")
        if values.transporter
        else None
    )

    data = {
        "transporter": values.transporter,
        "transporter_name": transporter_name,
        "gst_transporter_id": values.gst_transporter_id,
        "vehicle_no": values.vehicle_no,
        "distance": values.distance,
        "lr_no": values.lr_no,
        "lr_date": values.lr_date,
        "mode_of_transport": values.mode_of_transport,
        "gst_vehicle_type": values.gst_vehicle_type,
    }

    doc.db_set(data)

    if doc.doctype == "Delivery Note":
        doc._sub_supply_type = SUB_SUPPLY_TYPES[values.sub_supply_type]


#######################################################################################
### e-Waybill Data Generation #########################################################
#######################################################################################


class EWaybillData(GSTTransactionData):
    def __init__(self, *args, **kwargs):
        self.for_json = kwargs.pop("for_json", False)
        super().__init__(*args, **kwargs)

        self.validate_settings()
        self.validate_doctype_for_e_waybill()

    def get_data(self, *, with_irn=False):
        self.validate_transaction()
        self.set_transporter_details()
        self.set_party_address_details()
        self.update_distance_if_zero()

        if with_irn:
            return self.sanitize_data(
                {
                    "Irn": self.doc.irn,
                    "Distance": self.transaction_details.distance,
                    "TransMode": str(self.transaction_details.mode_of_transport),
                    "TransId": self.transaction_details.gst_transporter_id,
                    "TransName": self.transaction_details.transporter_name,
                    "TransDocDt": self.transaction_details.lr_date,
                    "TransDocNo": self.transaction_details.lr_no,
                    "VehNo": self.transaction_details.vehicle_no,
                    "VehType": self.transaction_details.vehicle_type,
                }
            )

        self.set_transaction_details()
        self.set_item_list()

        return self.get_transaction_data()

    def get_data_for_cancellation(self, values):
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
        self.set_transporter_details()

        dispatch_address_name = (
            self.doc.dispatch_address_name
            if self.doc.dispatch_address_name
            else self.doc.company_address
        )
        dispatch_address = self.get_address_details(dispatch_address_name)

        return {
            "ewbNo": self.doc.ewaybill,
            "vehicleNo": self.transaction_details.vehicle_no,
            "fromPlace": dispatch_address.city,
            "fromState": dispatch_address.state_number,
            "reasonCode": UPDATE_VEHICLE_REASON_CODES[values.reason],
            "reasonRem": self.sanitize_value(values.remark, regex=3),
            "transDocNo": self.transaction_details.lr_no,
            "transDocDate": self.transaction_details.lr_date,
            "transMode": self.transaction_details.mode_of_transport,
            "vehicleType": self.transaction_details.vehicle_type,
        }

    def get_update_transporter_data(self, values):
        self.validate_if_e_waybill_is_set()
        self.check_e_waybill_validity()

        return {
            "ewbNo": self.doc.ewaybill,
            "transporterId": values.gst_transporter_id,
        }

    def validate_transaction(self):
        # TODO: Add Support for Delivery Note

        super().validate_transaction()

        if self.doc.ewaybill:
            frappe.throw(
                _("e-Waybill already generated for {0} {1}").format(
                    _(self.doc.doctype), frappe.bold(self.doc.name)
                )
            )

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
        """

        for fieldname in ("company_address", "customer_address"):
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

        self.validate_non_gst_items()

    def validate_doctype_for_e_waybill(self):
        if self.doc.doctype not in PERMITTED_DOCTYPES:
            frappe.throw(
                _(
                    "Only Sales Invoice and Delivery Note are supported for e-Waybill"
                    " actions"
                ),
                title=_("Unsupported DocType"),
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

    def get_all_item_details(self):
        if len(self.doc.items) <= ITEM_LIMIT:
            return super().get_all_item_details()

        hsn_wise_items = {}

        for item in super().get_all_item_details():
            hsn_wise_details = hsn_wise_items.setdefault(
                (item.hsn_code, item.uom, item.tax_rate),
                frappe._dict(
                    hsn_code=item.hsn_code,
                    uom=item.uom,
                    item_name="",
                    cgst_rate=item.cgst_rate,
                    sgst_rate=item.sgst_rate,
                    igst_rate=item.igst_rate,
                    cess_rate=item.cess_rate,
                    cess_non_advol_rate=item.cess_non_advol_rate,
                    item_no=item.item_no,
                    qty=0,
                    taxable_value=0,
                ),
            )

            hsn_wise_details.qty += item.qty
            hsn_wise_details.taxable_value += item.taxable_value

        if len(hsn_wise_items) > ITEM_LIMIT:
            frappe.throw(
                _("e-Waybill can only be generated for upto {0} HSN/SAC Codes").format(
                    ITEM_LIMIT
                ),
                title=_("HSN/SAC Limit Exceeded"),
            )

        return hsn_wise_items.values()

    def update_transaction_details(self):
        # first HSN Code for goods
        main_hsn_code = next(
            row.gst_hsn_code
            for row in self.doc.items
            if not row.gst_hsn_code.startswith("99")
        )

        self.transaction_details.update(
            {
                "supply_type": "O",
                "sub_supply_type": 1,
                "document_type": "INV",
                "main_hsn_code": main_hsn_code,
            }
        )

        if self.doc.is_return:
            self.transaction_details.update(
                {
                    "supply_type": "I",
                    "sub_supply_type": 7,
                    "document_type": "CHL",
                }
            )

        elif self.doc.gst_category == "Overseas":
            self.transaction_details.sub_supply_type = 3

            if not self.doc.is_export_with_gst:
                self.transaction_details.document_type = "BIL"

        if self.doc.doctype == "Delivery Note":
            self.transaction_details.update(
                {
                    "sub_supply_type": self.doc._sub_supply_type,
                    "document_type": "CHL",
                }
            )

    def set_party_address_details(self):
        transaction_type = 1
        has_different_shipping_address = (
            self.doc.shipping_address_name
            and self.doc.customer_address != self.doc.shipping_address_name
        )

        has_different_dispatch_address = (
            self.doc.dispatch_address_name
            and self.doc.company_address != self.doc.dispatch_address_name
        )

        self.to_address = self.get_address_details(self.doc.customer_address)
        self.from_address = self.get_address_details(self.doc.company_address)

        # Defaults
        # billing state is changed for SEZ, hence copy()
        self.shipping_address = self.to_address.copy()
        self.dispatch_address = self.from_address

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

        self.transaction_details.transaction_type = transaction_type

        if self.doc.gst_category == "SEZ":
            self.to_address.state_number = 96

    def get_address_details(self, *args, **kwargs):
        address_details = super().get_address_details(*args, **kwargs)
        address_details.state_number = int(address_details.state_number)

        return address_details

    def update_distance_if_zero(self):
        """
        e-Waybill portal doesn't return distance where from and to pincode is same.
        Hardcode distance to 1 km to simplify and automate this.
        Accuracy of distance is immaterial and used only for e-Waybill validity determination.
        """

        if (
            self.transaction_details.distance == 0
            and self.dispatch_address.pincode == self.shipping_address.pincode
        ):
            self.transaction_details.distance = 1

    def get_transaction_data(self):
        if self.sandbox_mode:
            self.transaction_details.update(
                {
                    "company_gstin": "05AAACG2115R1ZN",
                    "name": random_string(6).lstrip("0"),
                }
            )

            self.from_address.gstin = "05AAACG2115R1ZN"
            self.to_address.gstin = (
                "05AAACG2140A1ZL"
                if self.transaction_details.sub_supply_type not in (5, 10, 11, 12)
                else "05AAACG2115R1ZN"
            )

        if self.doc.is_return:
            self.from_address, self.to_address = self.to_address, self.from_address
            self.dispatch_address, self.shipping_address = (
                self.shipping_address,
                self.dispatch_address,
            )

        data = {
            "userGstin": self.transaction_details.company_gstin,
            "supplyType": self.transaction_details.supply_type,
            "subSupplyType": self.transaction_details.sub_supply_type,
            "subSupplyDesc": "",
            "docType": self.transaction_details.document_type,
            "docNo": self.transaction_details.name,
            "docDate": self.transaction_details.date,
            "transactionType": self.transaction_details.transaction_type,
            "fromTrdName": self.from_address.address_title,
            "fromGstin": self.from_address.gstin,
            "fromAddr1": self.dispatch_address.address_line1,
            "fromAddr2": self.dispatch_address.address_line2,
            "fromPlace": self.dispatch_address.city,
            "fromPincode": self.dispatch_address.pincode,
            "fromStateCode": self.from_address.state_number,
            "actFromStateCode": self.dispatch_address.state_number,
            "toTrdName": self.to_address.address_title,
            "toGstin": self.to_address.gstin,
            "toAddr1": self.shipping_address.address_line1,
            "toAddr2": self.shipping_address.address_line2,
            "toPlace": self.shipping_address.city,
            "toPincode": self.shipping_address.pincode,
            "toStateCode": self.to_address.state_number,
            "actToStateCode": self.shipping_address.state_number,
            "totalValue": self.transaction_details.base_total,
            "cgstValue": self.transaction_details.total_cgst_amount,
            "sgstValue": self.transaction_details.total_sgst_amount,
            "igstValue": self.transaction_details.total_igst_amount,
            "cessValue": self.transaction_details.total_cess_amount,
            "TotNonAdvolVal": self.transaction_details.total_cess_non_advol_amount,
            "OthValue": self.transaction_details.rounding_adjustment
            + self.transaction_details.other_charges,
            "totInvValue": self.transaction_details.base_grand_total,
            "transMode": self.transaction_details.mode_of_transport,
            "transDistance": self.transaction_details.distance,
            "transporterName": self.transaction_details.transporter_name,
            "transporterId": self.transaction_details.gst_transporter_id,
            "transDocNo": self.transaction_details.lr_no,
            "transDocDate": self.transaction_details.lr_date,
            "vehicleNo": self.transaction_details.vehicle_no,
            "vehicleType": self.transaction_details.vehicle_type,
            "itemList": self.item_list,
            "mainHsnCode": self.transaction_details.main_hsn_code,
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

            return data

        return self.sanitize_data(data)

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
