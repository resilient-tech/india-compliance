import json

import jwt

import frappe
from frappe import _
from frappe.utils import (
    add_to_date,
    cstr,
    format_date,
    get_datetime,
    getdate,
    random_string,
)

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.constants import (
    EXPORT_TYPES,
    GST_CATEGORIES,
    OVERSEAS_GST_CATEGORIES,
)
from india_compliance.gst_india.constants.e_invoice import (
    CANCEL_REASON_CODES,
    ITEM_LIMIT,
)
from india_compliance.gst_india.utils import (
    is_api_enabled,
    load_doc,
    parse_datetime,
    send_updated_doc,
    update_onload,
)
from india_compliance.gst_india.utils.e_waybill import (
    _cancel_e_waybill,
    log_and_process_e_waybill_generation,
)
from india_compliance.gst_india.utils.transaction_data import (
    GSTTransactionData,
    validate_non_gst_items,
)


@frappe.whitelist()
def enqueue_bulk_e_invoice_generation(docnames):
    """
    Enqueue bulk generation of e-Invoices for the given Sales Invoices.
    """

    frappe.has_permission("Sales Invoice", "submit", throw=True)

    gst_settings = frappe.get_cached_doc("GST Settings")
    if not is_api_enabled(gst_settings) or not gst_settings.enable_e_invoice:
        frappe.throw(_("Please enable e-Invoicing in GST Settings first"))

    docnames = frappe.parse_json(docnames) if docnames.startswith("[") else [docnames]
    rq_job = frappe.enqueue(
        "india_compliance.gst_india.utils.e_invoice.generate_e_invoices",
        queue="long",
        timeout=len(docnames) * 240,  # 4 mins per e-Invoice
        docnames=docnames,
    )

    return rq_job.id


def generate_e_invoices(docnames):
    """
    Bulk generate e-Invoices for the given Sales Invoices.
    Permission checks are done in the `generate_e_invoice` function.
    """

    for docname in docnames:
        try:
            generate_e_invoice(docname)

        except Exception:
            frappe.log_error(
                title=_("e-Invoice generation failed for Sales Invoice {0}").format(
                    docname
                ),
                message=frappe.get_traceback(),
            )

        finally:
            # each e-Invoice needs to be committed individually
            # nosemgrep
            frappe.db.commit()


@frappe.whitelist()
def generate_e_invoice(docname, throw=True):
    doc = load_doc("Sales Invoice", docname, "submit")
    try:
        data = EInvoiceData(doc).get_data()
        api = EInvoiceAPI(doc)
        result = api.generate_irn(data)

        # Handle Duplicate IRN
        if result.InfCd == "DUPIRN":
            response = api.get_e_invoice_by_irn(result.Desc.Irn)

            # Handle error 2283:
            # IRN details cannot be provided as it is generated more than 2 days ago
            result = result.Desc if response.error_code == "2283" else response

    except frappe.ValidationError as e:
        if throw:
            raise e

        frappe.clear_last_message()
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

    invoice_data = None
    if result.SignedInvoice:
        decoded_invoice = json.loads(
            jwt.decode(result.SignedInvoice, options={"verify_signature": False})[
                "data"
            ]
        )
        invoice_data = frappe.as_json(decoded_invoice, indent=4)

    log_e_invoice(
        doc,
        {
            "irn": doc.irn,
            "sales_invoice": docname,
            "acknowledgement_number": result.AckNo,
            "acknowledged_on": parse_datetime(result.AckDt),
            "signed_invoice": result.SignedInvoice,
            "signed_qr_code": result.SignedQRCode,
            "invoice_data": invoice_data,
        },
    )

    if result.EwbNo:
        log_and_process_e_waybill_generation(doc, result, with_irn=True)

    if not frappe.request:
        return

    frappe.msgprint(
        _("e-Invoice generated successfully"),
        indicator="green",
        alert=True,
    )

    return send_updated_doc(doc)


@frappe.whitelist()
def cancel_e_invoice(docname, values):
    doc = load_doc("Sales Invoice", docname, "cancel")
    values = frappe.parse_json(values)
    validate_if_e_invoice_can_be_cancelled(doc)

    if doc.get("ewaybill"):
        _cancel_e_waybill(doc, values)

    data = {
        "Irn": doc.irn,
        "Cnlrsn": CANCEL_REASON_CODES[values.reason],
        "Cnlrem": values.remark if values.remark else values.reason,
    }

    result = EInvoiceAPI(doc).cancel_irn(data)
    doc.db_set({"einvoice_status": "Cancelled", "irn": ""})

    log_e_invoice(
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

    return send_updated_doc(doc)


def log_e_invoice(doc, log_data):
    frappe.enqueue(
        _log_e_invoice,
        queue="short",
        at_front=True,
        log_data=log_data,
    )

    update_onload(doc, "e_invoice_info", log_data)


def _log_e_invoice(log_data):
    #  fallback to IRN to avoid duplicate entry error
    log_name = log_data.pop("name", log_data.get("irn"))
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

    if doc.irn:
        return _throw(
            _("e-Invoice has already been generated for Sales Invoice {0}").format(
                frappe.bold(doc.name)
            )
        )

    if not validate_non_gst_items(doc, throw=throw):
        return

    if doc.gst_category == "Unregistered":
        return _throw(
            _("e-Invoice is not applicable for invoices with Unregistered Customers")
        )

    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    if not gst_settings.enable_e_invoice:
        return _throw(_("e-Invoice is not enabled in GST Settings"))

    if getdate(gst_settings.e_invoice_applicable_from) > getdate(doc.posting_date):
        return _throw(
            _(
                "e-Invoice is not applicable for invoices before {0} as per your"
                " GST Settings"
            ).format(frappe.bold(format_date(gst_settings.e_invoice_applicable_from)))
        )

    return True


def validate_if_e_invoice_can_be_cancelled(doc):
    if not doc.irn:
        frappe.throw(_("IRN not found"), title=_("Error Cancelling e-Invoice"))

    # this works because we do run_onload in load_doc above
    acknowledged_on = doc.get_onload().get("e_invoice_info", {}).get("acknowledged_on")

    if (
        not acknowledged_on
        or add_to_date(get_datetime(acknowledged_on), days=1, as_datetime=True)
        < get_datetime()
    ):
        frappe.throw(
            _("e-Invoice can only be cancelled upto 24 hours after it is generated")
        )


class EInvoiceData(GSTTransactionData):
    def get_data(self):
        self.validate_transaction()
        self.set_transaction_details()
        self.set_item_list()
        self.set_transporter_details()
        self.set_party_address_details()
        return self.sanitize_data(self.get_invoice_data())

    def validate_transaction(self):
        super().validate_transaction()
        validate_e_invoice_applicability(self.doc, self.settings)

        if len(self.doc.items) > ITEM_LIMIT:
            frappe.throw(
                _("e-Invoice can only be generated for upto {0} items").format(
                    ITEM_LIMIT
                ),
                title=_("Item Limit Exceeded"),
            )

    def update_item_details(self, item_details, item):
        item_details.update(
            {
                "discount_amount": 0,
                "serial_no": "",
                "is_service_item": "Y" if item.gst_hsn_code.startswith("99") else "N",
                "unit_rate": (
                    abs(self.rounded(item.taxable_value / item.qty, 3))
                    if item.qty
                    else abs(self.rounded(item.taxable_value, 3))
                ),
                "barcode": self.sanitize_value(
                    item.barcode, max_length=30, truncate=False
                ),
            }
        )

        if batch_no := self.sanitize_value(
            item.batch_no, max_length=20, truncate=False
        ):
            batch_expiry_date = frappe.db.get_value(
                "Batch", item.batch_no, "expiry_date"
            )
            item_details.update(
                {
                    "batch_no": batch_no,
                    "batch_expiry_date": format_date(
                        batch_expiry_date, self.DATE_FORMAT
                    ),
                }
            )

    def update_transaction_details(self):
        invoice_type = "INV"

        if self.doc.is_debit_note:
            invoice_type = "DBN"

        elif self.doc.is_return:
            invoice_type = "CRN"

            if return_against := self.doc.return_against:
                self.transaction_details.update(
                    {
                        "original_name": return_against,
                        "original_date": format_date(
                            frappe.db.get_value(
                                "Sales Invoice", return_against, "posting_date"
                            ),
                            self.DATE_FORMAT,
                        ),
                    }
                )

        self.transaction_details.update(
            {
                "tax_scheme": "GST",
                "supply_type": self.get_supply_type(),
                "reverse_charge": (
                    "Y" if getattr(self.doc, "is_reverse_charge", 0) else "N"
                ),
                "invoice_type": invoice_type,
                "ecommerce_gstin": self.doc.ecommerce_gstin,
                "place_of_supply": self.doc.place_of_supply.split("-")[0],
            }
        )

        self.update_payment_details()

    def update_payment_details(self):
        # PAYMENT DETAILS
        # cover cases where advance payment is made
        credit_days = 0
        paid_amount = 0

        if self.doc.due_date and getdate(self.doc.due_date) > getdate(
            self.doc.posting_date
        ):
            credit_days = (
                getdate(self.doc.due_date) - getdate(self.doc.posting_date)
            ).days

        if (self.doc.is_pos or self.doc.advances) and self.doc.base_paid_amount:
            paid_amount = abs(self.rounded(self.doc.base_paid_amount))

        self.transaction_details.update(
            {
                "payee_name": self.sanitize_value(self.doc.company)
                if paid_amount
                else "",
                "mode_of_payment": self.get_mode_of_payment(),
                "paid_amount": paid_amount,
                "credit_days": credit_days,
                "outstanding_amount": abs(self.rounded(self.doc.outstanding_amount)),
                "payment_terms": self.sanitize_value(self.doc.payment_terms_template),
                "grand_total": (
                    abs(self.rounded(self.doc.grand_total))
                    if self.doc.currency != "INR"
                    else ""
                ),
            }
        )

    def get_mode_of_payment(self):
        modes_of_payment = set()
        for payment in self.doc.payments or ():
            modes_of_payment.add(payment.mode_of_payment)

        if not modes_of_payment:
            return

        return self.sanitize_value(", ".join(modes_of_payment), max_length=18)

    def get_supply_type(self):
        supply_type = GST_CATEGORIES[self.doc.gst_category]
        if self.doc.gst_category in OVERSEAS_GST_CATEGORIES:
            supply_type = f"{supply_type}{EXPORT_TYPES[self.doc.is_export_with_gst]}"

        return supply_type

    def set_party_address_details(self):
        self.billing_address = self.get_address_details(
            self.doc.customer_address,
            validate_gstin=self.doc.gst_category != "Overseas",
        )
        self.company_address = self.get_address_details(
            self.doc.company_address, validate_gstin=True
        )

        # Defaults
        self.shipping_address = self.billing_address
        self.dispatch_address = self.company_address

        if (
            self.doc.shipping_address_name
            and self.doc.customer_address != self.doc.shipping_address_name
        ):
            self.shipping_address = self.get_address_details(
                self.doc.shipping_address_name
            )

        if (
            self.doc.dispatch_address_name
            and self.doc.company_address != self.doc.dispatch_address_name
        ):
            self.dispatch_address = self.get_address_details(
                self.doc.dispatch_address_name
            )

        self.billing_address.legal_name = self.sanitize_value(
            self.doc.customer_name or self.doc.customer
        )
        self.company_address.legal_name = self.sanitize_value(self.doc.company)

    def get_invoice_data(self):
        if self.sandbox_mode:
            seller = {
                "gstin": "01AMBPG7773M002",
                "state_number": "01",
                "pincode": 193501,
            }
            self.company_address.update(seller)
            self.dispatch_address.update(seller)
            self.transaction_details.name = random_string(6).lstrip("0")

            if frappe.flags.in_test:
                self.transaction_details.name = "test_invoice_no"

            # For overseas transactions, dummy GSTIN is not needed
            if self.doc.gst_category != "Overseas":
                buyer = {
                    "gstin": "36AMBPG7773M002",
                    "state_number": "36",
                    "pincode": 500055,
                }
                self.billing_address.update(buyer)
                self.shipping_address.update(buyer)

                if self.transaction_details.total_igst_amount > 0:
                    self.transaction_details.place_of_supply = "36"
                else:
                    self.transaction_details.place_of_supply = "01"

        if self.doc.is_return:
            self.dispatch_address, self.shipping_address = (
                self.shipping_address,
                self.dispatch_address,
            )

        return {
            "Version": "1.1",
            "TranDtls": {
                "TaxSch": self.transaction_details.tax_scheme,
                "SupTyp": self.transaction_details.supply_type,
                "RegRev": self.transaction_details.reverse_charge,
                "EcmGstin": self.transaction_details.ecommerce_gstin,
            },
            "DocDtls": {
                "Typ": self.transaction_details.invoice_type,
                "No": self.transaction_details.name,
                "Dt": self.transaction_details.date,
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
                "Pos": self.transaction_details.place_of_supply,
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
                "AssVal": self.transaction_details.base_total,
                "CgstVal": self.transaction_details.total_cgst_amount,
                "SgstVal": self.transaction_details.total_sgst_amount,
                "IgstVal": self.transaction_details.total_igst_amount,
                "CesVal": self.transaction_details.total_cess_amount
                + self.transaction_details.total_cess_non_advol_amount,
                "Discount": self.transaction_details.discount_amount,
                "RndOffAmt": self.transaction_details.rounding_adjustment,
                "OthChrg": self.transaction_details.other_charges,
                "TotInvVal": self.transaction_details.base_grand_total,
                "TotInvValFc": self.transaction_details.grand_total,
            },
            "PayDtls": {
                "Nm": self.transaction_details.payee_name,
                "Mode": self.transaction_details.mode_of_payment,
                "PayTerm": self.transaction_details.payment_terms,
                "PaidAmt": self.transaction_details.paid_amount,
                "PaymtDue": self.transaction_details.outstanding_amount,
                "CrDay": self.transaction_details.credit_days,
            },
            "RefDtls": {
                "PrecDocDtls": [
                    {
                        "InvNo": self.transaction_details.original_name,
                        "InvDt": self.transaction_details.original_date,
                    }
                ]
            },
            "EwbDtls": {
                "TransId": self.transaction_details.gst_transporter_id,
                "TransName": self.transaction_details.transporter_name,
                "TransMode": cstr(self.transaction_details.mode_of_transport),
                "Distance": self.transaction_details.distance,
                "TransDocNo": self.transaction_details.lr_no,
                "TransDocDt": self.transaction_details.lr_date,
                "VehNo": self.transaction_details.vehicle_no,
                "VehType": self.transaction_details.vehicle_type,
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
