import json

import jwt

import frappe
from frappe import _
from frappe.desk.form.save import send_updated_docs
from frappe.utils import (
    add_to_date,
    cstr,
    format_date,
    get_datetime,
    getdate,
    random_string,
)

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.constants import EXPORT_TYPES, GST_CATEGORIES
from india_compliance.gst_india.constants.e_invoice import CANCEL_REASON_CODES
from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.e_waybill import (
    _cancel_e_waybill,
    log_and_process_e_waybill_generation,
)
from india_compliance.gst_india.utils.invoice_data import GSTInvoiceData


@frappe.whitelist()
def generate_e_invoice(docname, throw=True):
    doc = frappe.get_doc("Sales Invoice", docname)
    doc.check_permission("submit")

    try:
        data = EInvoiceData(doc).get_data()
        api = EInvoiceAPI(doc.company_gstin)
        result = api.generate_irn(data)

        # Handle Duplicate IRN
        if result.InfCd == "DUPIRN":
            result = api.get_e_invoice_by_irn(result.Desc.get("Irn"))

    except frappe.ValidationError as e:
        if throw:
            raise e

        frappe.clear_last_message()
        doc.db_set({"einvoice_status": "Pending"})
        frappe.msgprint(
            _(
                "e-Invoice auto-generation failed with error:<br>{0}<br><br>"
                "Please rectify this issue and generate e-Invoice manually."
            ).format(str(e)),
            _("Warning"),
            indicator="yellow",
        )
        return

    doc.db_set(
        {
            "irn": result.Irn,
            "einvoice_status": "Generated",
        }
    )

    if result.EwbNo:
        log_and_process_e_waybill_generation(doc, result)

    decoded_invoice = frappe.parse_json(
        jwt.decode(result.SignedInvoice, options={"verify_signature": False})["data"]
    )

    log_and_process_e_invoice(
        doc.name,
        {
            "irn": result.Irn,
            "sales_invoice": docname,
            "acknowledgement_number": result.AckNo,
            "acknowledged_on": parse_datetime(result.AckDt),
            "signed_invoice": result.SignedInvoice,
            "signed_qr_code": result.SignedQRCode,
            "invoice_data": frappe.as_json(decoded_invoice, indent=4),
        },
    )

    frappe.msgprint(
        _("e-Invoice generated successfully"),
        indicator="green",
        alert=True,
    )

    return send_updated_docs(doc)


@frappe.whitelist()
def cancel_e_invoice(docname, values):
    doc = frappe.get_doc("Sales Invoice", docname)
    doc.check_permission("cancel")
    values = frappe.parse_json(values)
    validate_if_e_invoice_can_be_cancelled(doc)

    if doc.ewaybill:
        _cancel_e_waybill(doc, values)

    data = {
        "Irn": doc.irn,
        "Cnlrsn": CANCEL_REASON_CODES[values.reason],
        "Cnlrem": values.remark if values.remark else values.reason,
    }

    result = EInvoiceAPI(doc.company_gstin).cancel_irn(data)
    doc.db_set({"einvoice_status": "Cancelled", "irn": ""})

    log_and_process_e_invoice(
        doc,
        {
            "name": result.Irn,
            "is_cancelled": 1,
            "cancel_reason_code": values.reason,
            "cancel_remark": values.remark,
            "cancelled_on": parse_datetime(result.CancelDate),
        },
    )

    frappe.msgprint(
        _("e-Invoice cancelled successfully"),
        indicator="green",
        alert=True,
    )

    return send_updated_docs(doc)


def log_and_process_e_invoice(doc, log_data):
    frappe.enqueue(
        _log_and_process_e_invoice,
        queue="short",
        at_front=True,
        doc=doc,
        log_data=log_data,
    )


def _log_and_process_e_invoice(doc, log_data):
    log_name = log_data.pop("name", doc.irn)
    try:
        log = frappe.get_doc("e-Invoice Log", log_name)
    except frappe.DoesNotExistError:
        log = frappe.new_doc("e-Invoice Log")
        frappe.clear_last_message()

    log.update(log_data)
    log.save(ignore_permissions=True)


def validate_e_invoice_applicability(doc, gst_settings=None, throw=True):
    def _throw(error):
        if throw:
            frappe.throw(error)

    if doc.gst_category == "Unregistered":
        return _throw(
            _("e-Invoice is not applicable for invoices with Unregistered Customers")
        )

    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    if not gst_settings.enable_api:
        return _throw(_("Enable API in GST Settings to generate e-Invoice"))

    if not gst_settings.enable_e_invoice:
        return _throw(_("Enable e-Invoicing in GST Settings to generate e-Invoice"))

    if getdate(gst_settings.e_invoice_applicable_from) > getdate(doc.posting_date):
        return _throw(
            _(
                "e-Invoice is not applicable for invoices before {0} as per your"
                " GST Settings"
            ).format(format_date(gst_settings.e_invoice_applicable_from))
        )

    return True


def validate_if_e_invoice_can_be_cancelled(doc):
    if not doc.irn:
        frappe.throw(_("IRN not found"), title=_("Error Cancelling e-Invoice"))

    acknowledged_on = frappe.db.get_value("e-Invoice Log", doc.irn, "acknowledged_on")

    if get_datetime(add_to_date(acknowledged_on, days=1)) < get_datetime():
        frappe.throw(
            _("e-Invoice can be cancelled only within 24 Hours of its generation")
        )


class EInvoiceData(GSTInvoiceData):
    def get_data(self):
        self.validate_invoice()
        self.get_invoice_details()
        self.get_item_list()
        self.get_transporter_details()
        self.get_party_address_details()

        einv_data = self.get_invoice_data()
        return self.sanitize_data(einv_data)

    def validate_invoice(self):
        super().validate_invoice()
        self.check_applicability()

    def check_applicability(self):
        self.validate_non_gst_items()
        validate_e_invoice_applicability(self.doc, self.settings)

    def update_item_details(self, item_details, item):
        item_details.update(
            {
                "discount_amount": 0,
                "serial_no": "",
                "is_service_item": "Y" if item.gst_hsn_code.startswith("99") else "N",
                "unit_rate": abs(self.rounded(item.taxable_value / item.qty, 3))
                if item.qty
                else abs(self.rounded(item.taxable_value, 3)),
                "barcode": item.get("barcode") or "",
            }
        )

        if item.get("batch_no"):
            batch_expiry_date = frappe.db.get_value(
                "Batch", item.batch_no, "expiry_date"
            )
            batch_expiry_date = format_date(batch_expiry_date, self.DATE_FORMAT)
            item_details.update(
                {
                    "batch_number": item.batch_no,
                    "batch_expiry_date": batch_expiry_date,
                }
            )

    def update_invoice_details(self):
        super().update_invoice_details()

        self.invoice_details.update(
            {
                "tax_scheme": "GST",
                "supply_type": self.get_supply_type(),
                "reverse_charge": self.doc.reverse_charge,
                "invoice_type": "CRN" if self.doc.is_return else "INV",
                "ecommerce_gstin": self.doc.ecommerce_gstin,
                "place_of_supply": self.doc.place_of_supply.split("-")[0],
            }
        )

        # RETURN/CN DETIALS
        if self.doc.is_return and (return_against := self.doc.return_against):
            self.invoice_details.update(
                {
                    "original_invoice_number": return_against,
                    "original_invoice_date": format_date(
                        frappe.db.get_value(
                            "Sales Invoice", return_against, "posting_date"
                        ),
                        self.DATE_FORMAT,
                    ),
                }
            )

        self.update_payment_details()

    def update_payment_details(self):
        # PAYMENT DETAILS
        # cover cases where advance payment is made
        credit_days = paid_amount = 0
        if self.doc.get("due_date"):
            credit_days = (
                getdate(self.doc.due_date) - getdate(self.doc.posting_date)
            ).days

        if (self.doc.is_pos or self.doc.advances) and self.doc.base_paid_amount:
            paid_amount = abs(self.rounded(self.doc.base_paid_amount))

        self.invoice_details.update(
            {
                "payee_name": self.doc.company if paid_amount else "",
                "mode_of_payment": ", ".join(
                    [d.mode_of_payment for d in self.doc.payments if self.doc.payments]
                ),
                "paid_amount": paid_amount,
                "credit_days": credit_days,
                "outstanding_amount": abs(self.rounded(self.doc.outstanding_amount)),
                "payment_terms": self.doc.payment_terms_template
                if self.doc.get("payment_terms_template")
                else "",
                "grand_total": abs(self.rounded(self.doc.grand_total)),
            }
        )

    def get_supply_type(self):
        supply_type = GST_CATEGORIES[self.doc.gst_category]
        if self.doc.gst_category in ("Overseas", "SEZ"):
            export_type = EXPORT_TYPES[self.doc.export_type]
            supply_type = f"{supply_type}{export_type}"

        return supply_type

    def get_party_address_details(self):
        validate_gstin = True
        if self.doc.gst_category == "Overseas":
            validate_gstin = False

        self.billing_address = self.shipping_address = self.get_address_details(
            self.doc.customer_address, validate_gstin=validate_gstin
        )
        self.company_address = self.dispatch_address = self.get_address_details(
            self.doc.company_address, validate_gstin=True
        )

        if (
            self.doc.get("shipping_address_name")
            and self.doc.customer_address != self.doc.shipping_address_name
        ):
            self.shipping_address = self.get_address_details(
                self.doc.shipping_address_name
            )

        if (
            self.doc.get("dispatch_address_name")
            and self.doc.company_address != self.doc.dispatch_address_name
        ):
            self.dispatch_address = self.get_address_details(
                self.doc.dispatch_address_name
            )

        self.billing_address.legal_name = (
            self.doc.get("customer_name") or self.doc.customer
        )
        self.company_address.legal_name = self.doc.company

    def get_invoice_data(self):
        if self.sandbox:
            seller = {
                "gstin": "01AMBPG7773M002",
                "state_number": "01",
                "pincode": 193501,
            }
            buyer = {
                "gstin": "36AMBPG7773M002",
                "state_number": "36",
                "pincode": 500055,
            }
            self.company_address.update(seller)
            self.dispatch_address.update(seller)
            self.billing_address.update(buyer)
            self.shipping_address.update(buyer)
            self.invoice_details.invoice_number = random_string(6)

            if self.invoice_details.total_igst_amount > 0:
                self.invoice_details.place_of_supply = "36"
            else:
                self.invoice_details.place_of_supply = "01"

        return {
            "Version": "1.1",
            "TranDtls": {
                "TaxSch": self.invoice_details.tax_scheme,
                "SupTyp": self.invoice_details.supply_type,
                "RegRev": self.invoice_details.reverse_charge,
                "EcmGstin": self.invoice_details.ecommerce_gstin,
            },
            "DocDtls": {
                "Typ": self.invoice_details.invoice_type,
                "No": self.invoice_details.invoice_number,
                "Dt": self.invoice_details.invoice_date,
            },
            "SellerDtls": {
                "Gstin": self.company_address.gstin,
                "LglNm": self.company_address.legal_name,
                "TrdNm": self.company_address.address_title,
                "Loc": self.company_address.city,
                "Pin": self.company_address.pincode,
                "Stcd": self.company_address.state_number,
                "Addr1": self.company_address.address_line1,
                "Addr2": self.company_address.address_line2,
            },
            "BuyerDtls": {
                "Gstin": self.billing_address.gstin,
                "LglNm": self.billing_address.legal_name,
                "TrdNm": self.billing_address.address_title,
                "Addr1": self.billing_address.address_line1,
                "Addr2": self.billing_address.address_line2,
                "Loc": self.billing_address.city,
                "Pin": self.billing_address.pincode,
                "Stcd": self.billing_address.state_number,
                "Pos": self.invoice_details.place_of_supply,
            },
            "DispDtls": {
                "Nm": self.dispatch_address.address_title,
                "Addr1": self.dispatch_address.address_line1,
                "Addr2": self.dispatch_address.address_line2,
                "Loc": self.dispatch_address.city,
                "Pin": self.dispatch_address.pincode,
                "Stcd": self.dispatch_address.state_number,
            },
            "ShipDtls": {
                "Gstin": self.shipping_address.gstin,
                "LglNm": self.shipping_address.address_title,
                "TrdNm": self.shipping_address.address_title,
                "Addr1": self.shipping_address.address_line1,
                "Addr2": self.shipping_address.address_line2,
                "Loc": self.shipping_address.city,
                "Pin": self.shipping_address.pincode,
                "Stcd": self.shipping_address.state_number,
            },
            "ItemList": self.item_list,
            "ValDtls": {
                "AssVal": self.invoice_details.base_total,
                "CgstVal": self.invoice_details.total_cgst_amount,
                "SgstVal": self.invoice_details.total_sgst_amount,
                "IgstVal": self.invoice_details.total_igst_amount,
                "CesVal": self.invoice_details.total_cess_amount
                + self.invoice_details.total_cess_non_advol_amount,
                "Discount": self.invoice_details.discount_amount,
                "RndOffAmt": self.invoice_details.rounding_adjustment,
                "OthChrg": self.invoice_details.other_charges,
                "TotInvVal": self.invoice_details.base_grand_total,
                "TotInvValFc": self.invoice_details.grand_total,
            },
            "PayDtls": {
                "Nm": self.invoice_details.payee_name,
                "Mode": self.invoice_details.mode_of_payment,
                "PayTerm": self.invoice_details.payment_terms,
                "PaidAmt": self.invoice_details.paid_amount,
                "PaymtDue": self.invoice_details.outstanding_amount,
                "CrDay": self.invoice_details.credit_days,
            },
            "RefDtls": {
                "PrecDocDtls": [
                    {
                        "InvNo": self.invoice_details.original_invoice_number,
                        "InvDt": self.invoice_details.original_invoice_date,
                    }
                ]
            },
            "EwbDtls": {
                "TransId": self.invoice_details.gst_transporter_id,
                "TransName": self.invoice_details.transporter_name,
                "TransMode": cstr(self.invoice_details.mode_of_transport),
                "Distance": self.invoice_details.distance,
                "TransDocNo": self.invoice_details.lr_no,
                "TransDocDt": self.invoice_details.lr_date,
                "VehNo": self.invoice_details.vehicle_no,
                "VehType": self.invoice_details.vehicle_type,
            },
        }

    def get_item_data(self, item_details):
        return {
            "SlNo": cstr(item_details.item_no),
            "PrdDesc": item_details.item_name,
            "IsServc": item_details.is_service_item,
            "HsnCd": item_details.hsn_code,
            "Barcde": item_details.barcode,
            "Unit": item_details.uom,
            "Qty": item_details.qty,
            "UnitPrice": item_details.unit_rate,
            "TotAmt": item_details.taxable_value,
            "Discount": item_details.discount_amount,
            "AssAmt": item_details.taxable_value,
            "PrdSlNo": item_details.serial_no,
            "GstRt": item_details.tax_rate,
            "IgstAmt": item_details.igst_amount,
            "CgstAmt": item_details.cgst_amount,
            "SgstAmt": item_details.sgst_amount,
            "CesRt": item_details.cess_rate,
            "CesAmt": item_details.cess_amount,
            "CesNonAdvlAmt": item_details.cess_non_advol_amount,
            "TotItemVal": item_details.total_value,
            "BchDtls": {
                "Nm": item_details.batch_no,
                "ExpDt": item_details.batch_expiry_date,
            },
        }
