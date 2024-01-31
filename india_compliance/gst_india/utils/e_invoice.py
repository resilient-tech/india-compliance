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

from india_compliance.exceptions import GSPServerError
from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.constants import (
    CURRENCY_CODES,
    EXPORT_TYPES,
    GST_CATEGORIES,
    PORT_CODES,
)
from india_compliance.gst_india.constants.e_invoice import (
    CANCEL_REASON_CODES,
    ITEM_LIMIT,
)
from india_compliance.gst_india.overrides.transaction import (
    _validate_hsn_codes,
    validate_mandatory_fields,
)
from india_compliance.gst_india.utils import (
    are_goods_supplied,
    handle_server_errors,
    is_api_enabled,
    is_foreign_doc,
    is_overseas_doc,
    load_doc,
    parse_datetime,
    send_updated_doc,
    update_onload,
)
from india_compliance.gst_india.utils.e_waybill import (
    _cancel_e_waybill,
    generate_pending_e_waybills,
    log_and_process_e_waybill_generation,
)
from india_compliance.gst_india.utils.transaction_data import GSTTransactionData


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
        queue="short" if len(docnames) < 5 else "long",
        timeout=len(docnames) * 240,  # 4 mins per e-Invoice
        docnames=docnames,
    )

    return rq_job.id


def generate_e_invoices(docnames, force=False):
    """
    Bulk generate e-Invoices for the given Sales Invoices.
    Permission checks are done in the `generate_e_invoice` function.
    """

    def log_error():
        frappe.log_error(
            title=_("e-Invoice generation failed for Sales Invoice {0}").format(
                docname
            ),
            message=frappe.get_traceback(),
        )

    for docname in docnames:
        try:
            generate_e_invoice(docname, throw=False, force=force)

        except GSPServerError:
            frappe.db.set_value(
                "Sales Invoice",
                {"name": ("in", docnames), "irn": ("is", "not set")},
                "einvoice_status",
                "Auto-Retry",
            )

            log_error()
            frappe.clear_last_message()

        except Exception:
            log_error()
            frappe.clear_last_message()

        finally:
            # each e-Invoice needs to be committed individually
            frappe.db.commit()  # nosemgrep


@frappe.whitelist()
def generate_e_invoice(docname, throw=True, force=False):
    doc = load_doc("Sales Invoice", docname, "submit")

    settings = frappe.get_cached_doc("GST Settings")

    try:
        if (
            not force
            and settings.enable_retry_einv_ewb_generation
            and settings.is_retry_einv_ewb_generation_pending
        ):
            raise GSPServerError

        data = EInvoiceData(doc).get_data()
        api = EInvoiceAPI(doc)
        result = api.generate_irn(data)

        # Handle Duplicate IRN
        if result.InfCd == "DUPIRN":
            response = api.get_e_invoice_by_irn(result.Desc.Irn)

            if signed_data := response.SignedInvoice:
                invoice_data = json.loads(
                    jwt.decode(signed_data, options={"verify_signature": False})["data"]
                )

                previous_invoice_amount = invoice_data.get("ValDtls").get("TotInvVal")
                current_invoice_amount = data.get("ValDtls").get("TotInvVal")

                if previous_invoice_amount != current_invoice_amount:
                    frappe.throw(
                        _(
                            "e-Invoice is already available against Invoice {0} with a Grand Total of Rs.{1}"
                            " Duplicate IRN requests are not considered by e-Invoice Portal."
                        ).format(
                            frappe.bold(invoice_data.get("DocDtls").get("No")),
                            frappe.bold(previous_invoice_amount),
                        )
                    )

            # Handle error 2283:
            # IRN details cannot be provided as it is generated more than 2 days ago
            result = result.Desc if response.error_code == "2283" else response

        # Handle Invalid GSTIN Error
        if result.error_code in ("3028", "3029"):
            gstin = data.get("BuyerDtls").get("Gstin")
            response = api.sync_gstin_info(gstin)

            if response.Status != "ACT":
                frappe.throw(_("GSTIN {0} status is not Active").format(gstin))

            result = api.generate_irn(data)

    except GSPServerError as e:
        handle_server_errors(settings, doc, "e-Invoice", e)
        return

    except frappe.ValidationError as e:
        doc.db_set({"einvoice_status": "Failed"})

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

    except Exception as e:
        doc.db_set({"einvoice_status": "Failed"})
        raise e

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
            "is_generated_in_sandbox_mode": api.sandbox_mode,
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

    log_and_process_e_invoice_cancellation(
        doc, values, result, "e-Invoice cancelled successfully"
    )

    return send_updated_doc(doc)


def log_and_process_e_invoice_cancellation(doc, values, result, message):
    log_e_invoice(
        doc,
        {
            "name": doc.irn,
            "is_cancelled": 1,
            "cancel_reason_code": values.reason,
            "cancel_remark": values.remark or values.reason,
            "cancelled_on": (
                get_datetime()  # Fallback to handle already cancelled IRN
                if result.error_code == "9999"
                else parse_datetime(result.CancelDate)
            ),
        },
    )

    doc.db_set(
        {
            "einvoice_status": result.get("einvoice_status") or "Cancelled",
            "irn": "",
        }
    )

    frappe.msgprint(_(message), indicator="green", alert=True)


@frappe.whitelist()
def mark_e_invoice_as_cancelled(doctype, docname, values):
    doc = load_doc(doctype, docname, "cancel")

    if doc.docstatus != 2:
        return

    values = frappe.parse_json(values)
    result = frappe._dict(
        {
            "CancelDate": values.cancelled_on,
            "einvoice_status": "Manually Cancelled",
        }
    )

    log_and_process_e_invoice_cancellation(
        doc, values, result, "e-Invoice marked as cancelled successfully"
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

    if doc.company_gstin == doc.billing_address_gstin:
        return _throw(
            _(
                "e-Invoice is not applicable for invoices with same company and billing"
                " GSTIN"
            )
        )

    if doc.irn:
        return _throw(
            _("e-Invoice has already been generated for Sales Invoice {0}").format(
                frappe.bold(doc.name)
            )
        )

    if not validate_taxable_item(doc, throw=throw):
        # e-Invoice not required for invoice wih all nill-rated/exempted items.
        return

    if not (doc.place_of_supply == "96-Other Countries" or doc.billing_address_gstin):
        return _throw(_("e-Invoice is not applicable for B2C invoices"))

    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    if not gst_settings.enable_e_invoice:
        return _throw(_("e-Invoice is not enabled in GST Settings"))

    applicability_date = get_e_invoice_applicability_date(doc, gst_settings, throw)

    if not applicability_date:
        return _throw(
            _("e-Invoice is not applicable for company {0}").format(doc.company)
        )

    if getdate(applicability_date) > getdate(doc.posting_date):
        return _throw(
            _(
                "e-Invoice is not applicable for invoices before {0} as per your"
                " GST Settings"
            ).format(frappe.bold(format_date(applicability_date)))
        )

    return True


def validate_hsn_codes_for_e_invoice(doc):
    _validate_hsn_codes(
        doc,
        valid_hsn_length=[6, 8],
        message=_("Since HSN/SAC Code is mandatory for generating e-Invoices.<br>"),
    )


def validate_taxable_item(doc, throw=True):
    """
    Validates that the document contains at least one GST taxable item.

    If all items are Nil-Rated or Exempted and throw is True, it raises an exception.
    Otherwise, it simply returns False.

    """
    # Check if there is at least one taxable item in the document
    if any(item.gst_treatment in ("Taxable", "Zero-Rated") for item in doc.items):
        return True

    if not throw:
        return

    frappe.throw(
        _("e-Invoice is not applicable for invoice with only Nil-Rated/Exempted items"),
    )


def get_e_invoice_applicability_date(doc, settings=None, throw=True):
    if not settings:
        settings = frappe.get_cached_doc("GST Settings")

    e_invoice_applicable_from = settings.e_invoice_applicable_from

    if settings.apply_e_invoice_only_for_selected_companies:
        for row in settings.e_invoice_applicable_companies:
            if doc.company == row.company:
                e_invoice_applicable_from = row.applicable_from
                break

        else:
            return

    return e_invoice_applicable_from


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


def retry_e_invoice_e_waybill_generation():
    settings = frappe.get_cached_doc("GST Settings")

    if (
        not settings.enable_retry_einv_ewb_generation
        or not settings.is_retry_einv_ewb_generation_pending
    ):
        return

    settings.db_set("is_retry_einv_ewb_generation_pending", 0, update_modified=False)

    generate_pending_e_invoices()

    generate_pending_e_waybills()


def generate_pending_e_invoices():
    queued_sales_invoices = frappe.db.get_all(
        "Sales Invoice",
        filters={"einvoice_status": "Auto-Retry"},
        pluck="name",
    )

    if not queued_sales_invoices:
        return

    generate_e_invoices(queued_sales_invoices)


def get_e_invoice_info(doc):
    return frappe.db.get_value(
        "e-Invoice Log",
        doc.irn,
        ("is_generated_in_sandbox_mode", "acknowledged_on"),
        as_dict=True,
    )


class EInvoiceData(GSTTransactionData):
    def get_data(self):
        self.validate_transaction()
        self.set_transaction_details()
        self.set_item_list()
        self.update_other_charges()
        self.set_transporter_details()
        self.set_party_address_details()
        return self.sanitize_data(self.get_invoice_data())

    def set_item_list(self):
        self.item_list = []

        for item_details in self.get_all_item_details():
            if item_details.get("gst_treatment") not in ("Taxable", "Zero-Rated"):
                continue

            self.item_list.append(self.get_item_data(item_details))

    def update_other_charges(self):
        """
        Non Taxable Value should be added to other charges.
        """
        self.transaction_details.other_charges += (
            self.transaction_details.total_non_taxable_value
        )

    def validate_transaction(self):
        super().validate_transaction()
        validate_e_invoice_applicability(self.doc, self.settings)

        validate_mandatory_fields(
            self.doc,
            "customer_address",
            _("{0} is a mandatory field for generating e-Invoices"),
        )

        validate_hsn_codes_for_e_invoice(self.doc)

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
                "payee_name": (
                    self.sanitize_value(self.doc.company) if paid_amount else ""
                ),
                "mode_of_payment": self.get_mode_of_payment(),
                "paid_amount": paid_amount,
                "credit_days": credit_days,
                "outstanding_amount": abs(self.rounded(self.doc.outstanding_amount)),
                "payment_terms": self.sanitize_value(self.doc.payment_terms_template),
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
        if is_overseas_doc(self.doc):
            supply_type = f"{supply_type}{EXPORT_TYPES[self.doc.is_export_with_gst]}"

        return supply_type

    def set_transporter_details(self):
        if (
            # e-waybill threshold is not met
            self.transaction_details.grand_total < self.settings.e_waybill_threshold
            # e-waybill auto-generation is disabled by user
            or not self.settings.generate_e_waybill_with_e_invoice
        ):
            return

        return super().set_transporter_details()

    def set_party_address_details(self):
        self.billing_address = self.get_address_details(
            self.doc.customer_address,
            validate_gstin=self.doc.gst_category != "Overseas",
        )
        self.company_address = self.get_address_details(
            self.doc.company_address, validate_gstin=True
        )

        ship_to_address = (
            self.doc.port_address
            if (is_foreign_doc(self.doc) and self.doc.port_address)
            else self.doc.shipping_address_name
        )

        # Defaults
        self.shipping_address = None
        self.dispatch_address = None

        if ship_to_address and self.doc.customer_address != ship_to_address:
            self.shipping_address = self.get_address_details(ship_to_address)

        if (
            self.doc.dispatch_address_name
            and self.doc.company_address != self.doc.dispatch_address_name
        ):
            self.dispatch_address = self.get_address_details(
                self.doc.dispatch_address_name
            )

        self.billing_address.legal_name = self.transaction_details.party_name
        self.company_address.legal_name = self.transaction_details.company_name

    def get_invoice_data(self):
        if self.sandbox_mode:
            seller = {
                "gstin": "02AMBPG7773M002",
                "state_number": "02",
                "pincode": 171302,
            }
            self.company_address.update(seller)
            if self.dispatch_address:
                self.dispatch_address.update(seller)

            self.transaction_details.name = (
                random_string(6).lstrip("0")
                if not frappe.flags.in_test
                else "test_invoice_no"
            )

            # For overseas transactions, dummy GSTIN is not needed
            if not is_foreign_doc(self.doc):
                buyer = {
                    "gstin": "36AMBPG7773M002",
                    "state_number": "36",
                    "pincode": 500055,
                }
                self.billing_address.update(buyer)
                if self.shipping_address:
                    self.shipping_address.update(buyer)

                if self.transaction_details.total_igst_amount > 0:
                    self.transaction_details.place_of_supply = "36"
                else:
                    self.transaction_details.place_of_supply = "02"

        if self.doc.is_return:
            self.dispatch_address, self.shipping_address = (
                self.shipping_address,
                self.dispatch_address,
            )

        invoice_data = {
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
                "TrdNm": self.company_address.legal_name,
                "Loc": self.company_address.city,
                "Pin": self.company_address.pincode,
                "Stcd": self.company_address.state_number,
                "Addr1": self.company_address.address_line1,
                "Addr2": self.company_address.address_line2,
            },
            "BuyerDtls": {
                "Gstin": self.billing_address.gstin,
                "LglNm": self.billing_address.legal_name,
                "TrdNm": self.billing_address.legal_name,
                "Addr1": self.billing_address.address_line1,
                "Addr2": self.billing_address.address_line2,
                "Loc": self.billing_address.city,
                "Pin": self.billing_address.pincode,
                "Stcd": self.billing_address.state_number,
                "Pos": self.transaction_details.place_of_supply,
            },
            "ItemList": self.item_list,
            "ValDtls": {
                "AssVal": self.transaction_details.total_taxable_value,
                "CgstVal": self.transaction_details.total_cgst_amount,
                "SgstVal": self.transaction_details.total_sgst_amount,
                "IgstVal": self.transaction_details.total_igst_amount,
                "CesVal": (
                    self.transaction_details.total_cess_amount
                    + self.transaction_details.total_cess_non_advol_amount
                ),
                "Discount": self.transaction_details.discount_amount,
                "RndOffAmt": self.transaction_details.rounding_adjustment,
                "OthChrg": self.transaction_details.other_charges,
                "TotInvVal": self.transaction_details.grand_total,
                "TotInvValFc": self.transaction_details.grand_total_in_foreign_currency,
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

        if self.dispatch_address:
            invoice_data["DispDtls"] = {
                "Nm": self.dispatch_address.address_title,
                "Addr1": self.dispatch_address.address_line1,
                "Addr2": self.dispatch_address.address_line2,
                "Loc": self.dispatch_address.city,
                "Pin": self.dispatch_address.pincode,
                "Stcd": self.dispatch_address.state_number,
            }

        if self.shipping_address:
            invoice_data["ShipDtls"] = {
                "Gstin": self.shipping_address.gstin,
                "LglNm": self.shipping_address.address_title,
                "TrdNm": self.shipping_address.address_title,
                "Addr1": self.shipping_address.address_line1,
                "Addr2": self.shipping_address.address_line2,
                "Loc": self.shipping_address.city,
                "Pin": self.shipping_address.pincode,
                "Stcd": self.shipping_address.state_number,
            }

        if is_foreign_doc(self.doc):
            invoice_data["ExpDtls"] = self.get_export_details()

        return invoice_data

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

    def get_export_details(self):
        export_details = {"CntCode": self.billing_address.country_code}

        currency = self.doc.currency and self.doc.currency.upper()
        if currency != "INR" and currency in CURRENCY_CODES:
            export_details["ForCur"] = currency

        if not are_goods_supplied(self.doc):
            return export_details

        export_details["ShipBNo"] = self.doc.shipping_bill_number
        export_details["ShipBDt"] = format_date(
            self.doc.shipping_bill_date, self.DATE_FORMAT
        )

        if self.doc.port_code in PORT_CODES:
            export_details["Port"] = self.doc.port_code

        return export_details
