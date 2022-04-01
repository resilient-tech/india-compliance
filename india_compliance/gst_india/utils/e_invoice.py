import json

import frappe
from frappe import _
from frappe.utils import format_date, getdate, random_string

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.constants import EXPORT_TYPES, GST_CATEGORIES
from india_compliance.gst_india.utils.invoice_data import GSTInvoiceData


def generate_e_invoice(doc, sandbox=False):
    doc = frappe.get_doc("Sales Invoice", "SINV-CFY-00010-1")
    data = EInvoiceData(doc, sandbox=sandbox).get_e_invoice_data()

    if sandbox:
        api = EInvoiceAPI("01AMBPG7773M002")
        api.BASE_URL = "https://asp.resilient.tech/test"
    else:
        api = EInvoiceAPI(doc.company_gstin)

    result = api.generate_irn(data)
    return result


def set_einvoice_data(result):

    pass


def validate_e_invoice_applicability(doc, gst_settings=None, throw=True):
    if doc.gst_category == "Unregistered":
        if throw:
            frappe.throw(
                _(
                    "e-Invoice is not applicable for invoices with Unregistered"
                    " Customers"
                )
            )

        return

    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    if not gst_settings.enable_api:
        if throw:
            frappe.throw(_("Enable API in GST Settings to generate e-Invoice"))

        return

    if not gst_settings.enable_e_invoice:
        if throw:
            frappe.throw(_("Enable e-Invoicing in GST Settings to generate e-Invoice"))

        return

    if getdate(gst_settings.e_invoice_applicable_from) > getdate(doc.posting_date):
        if throw:
            frappe.throw(
                _(
                    "e-Invoice is not applicable for invoices before {0} as per your"
                    " GST Settings"
                ).format(format_date(gst_settings.e_invoice_applicable_from))
            )

        return

    return True


class EInvoiceData(GSTInvoiceData):
    def __init__(self, doc, json_download=False, sandbox=False):
        super().__init__(doc, json_download, sandbox)

    def get_e_invoice_data(self):
        self.pre_validate_invoice()
        self.get_item_list()
        self.get_invoice_details()
        self.get_transporter_details()
        self.get_party_address_details()

        einv_data = self.get_invoice_map()
        einv_data = json.loads(einv_data)
        return self.sanitize_invoice_map(einv_data)

    def pre_validate_invoice(self):
        super().pre_validate_invoice()
        self.check_e_invoice_applicability()

    def check_e_invoice_applicability(self):
        self.validate_company()
        self.validate_non_gst_items()
        validate_e_invoice_applicability(self.doc, self.settings)

    def update_item_details(self, row):
        super().update_item_details(row)

        self.item_details.update(
            {
                "discount_amount": 0,
                "serial_no": "",
                "is_service_item": "Y" if row.gst_hsn_code.startswith("99") else "N",
                "unit_rate": abs(row.taxable_value / row.qty)
                if row.qty
                else abs(row.taxable_value),
                "barcode": row.get("barcode") or "",
            }
        )

        if row.get("batch_no"):
            batch_expiry_date = frappe.db.get_value(
                "Batch", row.batch_no, "expiry_date"
            )
            batch_expiry_date = format_date(batch_expiry_date, self.DATE_FORMAT)
            self.item_details.update(
                {
                    "batch_number": row.batch_no,
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
        gstin_validation = True
        if self.doc.gst_category == "Overseas":
            gstin_validation = False

        self.billing_address = self.shipping_address = self.get_address_details(
            self.doc.customer_address, gstin_validation=gstin_validation
        )
        self.company_address = self.dispatch_address = self.get_address_details(
            self.doc.company_address, gstin_validation=True
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

    def get_invoice_map(self):
        if self.sandbox:
            seller = {
                "gstin": "01AMBPG7773M002",
                "state_code": "01",
                "pincode": "193501",
            }
            buyer = {
                "gstin": "36AMBPG7773M002",
                "state_code": "36",
                "pincode": "500055",
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

        return f"""
        {{
            "Version": "1.1",
            "TranDtls": {{
                "TaxSch": "{self.invoice_details.tax_scheme}",
                "SupTyp": "{self.invoice_details.supply_type}",
                "RegRev": "{self.invoice_details.reverse_charge}",
                "EcmGstin": "{self.invoice_details.ecommerce_gstin}"
            }},
            "DocDtls": {{
                "Typ": "{self.invoice_details.invoice_type}",
                "No": "{self.invoice_details.invoice_number}",
                "Dt": "{self.invoice_details.invoice_date}"
            }},
            "SellerDtls": {{
                "Gstin": "{self.company_address.gstin}",
                "LglNm": "{self.company_address.legal_name}",
                "TrdNm": "{self.company_address.address_title}",
                "Loc": "{self.company_address.city}",
                "Pin": {self.company_address.pincode},
                "Stcd": "{self.company_address.state_code}",
                "Addr1": "{self.company_address.address_line1}",
                "Addr2": "{self.company_address.address_line2}"
            }},
            "BuyerDtls": {{
                "Gstin": "{self.billing_address.gstin}",
                "LglNm": "{self.billing_address.legal_name}",
                "TrdNm": "{self.billing_address.address_title}",
                "Addr1": "{self.billing_address.address_line1}",
                "Addr2": "{self.billing_address.address_line2}",
                "Loc": "{self.billing_address.city}",
                "Pin": {self.billing_address.pincode},
                "Stcd": "{self.billing_address.state_code}",
                "Pos": "{self.invoice_details.place_of_supply}"
            }},
            "DispDtls": {{
                "Nm": "{self.dispatch_address.address_title}",
                "Addr1": "{self.dispatch_address.address_line1}",
                "Addr2": "{self.dispatch_address.address_line2}",
                "Loc": "{self.dispatch_address.city}",
                "Pin": {self.dispatch_address.pincode},
                "Stcd": "{self.dispatch_address.state_code}"
            }},
            "ShipDtls": {{
                "Gstin": "{self.shipping_address.gstin}",
                "LglNm": "{self.shipping_address.address_title}",
                "TrdNm": "{self.shipping_address.address_title}",
                "Addr1": "{self.shipping_address.address_line1}",
                "Addr2": "{self.shipping_address.address_line2}",
                "Loc": "{self.shipping_address.city}",
                "Pin": {self.shipping_address.pincode},
                "Stcd": "{self.shipping_address.state_code}"
            }},
            "ItemList": [
                {self.item_list}
            ],
            "ValDtls": {{
                "AssVal": {self.invoice_details.base_total},
                "CgstVal": {self.invoice_details.total_cgst_amount},
                "SgstVal": {self.invoice_details.total_sgst_amount},
                "IgstVal": {self.invoice_details.total_igst_amount},
                "CesVal": {self.invoice_details.total_cess_amount + self.invoice_details.total_cess_non_advol_amount},
                "Discount": {self.invoice_details.discount_amount},
                "RndOffAmt": {self.invoice_details.rounding_adjustment},
                "OthChrg": {self.invoice_details.other_charges},
                "TotInvVal": {self.invoice_details.base_grand_total},
                "TotInvValFc": {self.invoice_details.grand_total}
            }},
            "PayDtls": {{
                "Nm": "{self.invoice_details.payee_name}",
                "Mode": "{self.invoice_details.mode_of_payment}",
                "PayTerm": "{self.invoice_details.payment_terms}",
                "PaidAmt": {self.invoice_details.paid_amount},
                "PaymtDue": {self.invoice_details.outstanding_amount},
                "CrDay": {self.invoice_details.credit_days}
            }},
            "RefDtls": {{
                "PrecDocDtls": [{{
                    "InvNo": "{self.invoice_details.original_invoice_number}",
                    "InvDt": "{self.invoice_details.original_invoice_date}"
                }}]
            }},
            "EwbDtls": {{
                "TransId": "{self.invoice_details.gst_transporter_id}",
                "TransName": "{self.invoice_details.transporter_name}",
                "TransMode": "{self.invoice_details.mode_of_transport}",
                "Distance": {self.invoice_details.distance},
                "TransDocNo": "{self.invoice_details.lr_no}",
                "TransDocDt": "{self.invoice_details.lr_date_str}",
                "VehNo": "{self.invoice_details.vehicle_no}",
                "VehType": "{self.invoice_details.vehicle_type}"
            }}
        }}
        """

    def get_item_map(self):
        return f"""
        {{
            "SlNo": "{self.item_details.item_no}",
            "PrdDesc": "{self.item_details.item_name}",
            "IsServc": "{self.item_details.is_service_item}",
            "HsnCd": "{self.item_details.hsn_code}",
            "Barcde": "{self.item_details.barcode}",
            "Unit": "{self.item_details.uom}",
            "Qty": {self.item_details.qty},
            "UnitPrice": {self.item_details.unit_rate},
            "TotAmt": {self.item_details.taxable_value},
            "Discount": {self.item_details.discount_amount},
            "AssAmt": {self.item_details.taxable_value},
            "PrdSlNo": "{self.item_details.serial_no}",
            "GstRt": {self.item_details.tax_rate},
            "IgstAmt": {self.item_details.igst_amount},
            "CgstAmt": {self.item_details.cgst_amount},
            "SgstAmt": {self.item_details.sgst_amount},
            "CesRt": {self.item_details.cess_rate},
            "CesAmt": {self.item_details.cess_amount},
            "CesNonAdvlAmt": {self.item_details.cess_non_advol_amount},
            "TotItemVal": {self.item_details.total_value},
            "BchDtls": {{
                "Nm": "{self.item_details.batch_no}",
                "ExpDt": "{self.item_details.batch_expiry_date}"
            }}
        }}
        """
