import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.utils import get_gstin_list
from india_compliance.gst_india.utils.gstr import ReturnsAPI


def get_mapped_value(value, mapping):
    return mapping.get(value)


class GSTR:
    # Maps of API keys to doctype fields
    KEY_MAPS = frappe._dict()

    # Maps of API values to doctype values
    VALUE_MAPS = frappe._dict(
        {
            "Y_N_to_check": {"Y": 1, "N": 0},
            "yes_no": {"Y": "Yes", "N": "No"},
            "gst_category": {
                "R": "Regular",
                "SEZWP": "SEZ supplies with payment of tax",
                "SEZWOP": "SEZ supplies with out payment of tax",
                "DE": "Deemed exports",
                "CBW": "Intra-State Supplies attracting IGST",
            },
            "states": {value: f"{value}-{key}" for key, value in STATE_NUMBERS.items()},
            "note_type": {"C": "Credit Note", "D": "Debit Note"},
            "isd_type_2a": {"ISDCN": "ISD Credit Note", "ISD": "ISD Invoice"},
            "isd_type_2b": {"ISDC": "ISD Credit Note", "ISDI": "ISD Invoice"},
            "amend_type": {
                "R": "Receiver GSTIN Amended",
                "N": "Invoice Number Amended",
                "D": "Other Details Amended",
            },
        }
    )

    def __init__(self, company, gstin, return_period, data, gen_date_2b):
        self.company = company
        self.gstin = gstin
        self.return_period = return_period
        self._data = data
        self.gen_date_2b = gen_date_2b
        self.setup()

    def setup(self):
        pass

    def create_transactions(self, category, suppliers):
        if not suppliers:
            return

        transactions = self.get_all_transactions(category, suppliers)
        total_transactions = len(transactions)
        current_transaction = 0

        for transaction in transactions:
            create_inward_supply(transaction)

            current_transaction += 1
            frappe.publish_realtime(
                "update_transactions_progress",
                {
                    "current_progress": current_transaction * 100 / total_transactions,
                    "return_period": self.return_period,
                },
                user=frappe.session.user,
                doctype="Purchase Reconciliation Tool",
            )

    def get_all_transactions(self, category, suppliers):
        transactions = []
        for supplier in suppliers:
            transactions.extend(self.get_supplier_transactions(category, supplier))

        self.update_gstins()

        return transactions

    def get_supplier_transactions(self, category, supplier):
        return [
            self.get_transaction(
                category, frappe._dict(supplier), frappe._dict(invoice)
            )
            for invoice in supplier.get(self.get_key("invoice_key"))
        ]

    def get_transaction(self, category, supplier, invoice):
        return frappe._dict(
            company=self.company,
            company_gstin=self.gstin,
            # TODO: change classification to gstr_category
            classification=category.value,
            **self.get_supplier_details(supplier),
            **self.get_invoice_details(invoice),
            items=self.get_transaction_items(invoice),
        )

    def get_supplier_details(self, supplier):
        return {}

    def get_invoice_details(self, invoice):
        return {}

    def get_transaction_items(self, invoice):
        return [
            self.get_transaction_item(frappe._dict(item))
            for item in invoice.get(self.get_key("items_key"))
        ]

    def get_transaction_item(self, item):
        return frappe._dict()

    def get_key(self, key):
        return self.KEY_MAPS.get(key)

    def set_key(self, key, value):
        self.KEY_MAPS[key] = value

    def update_gstins(self):
        pass


@frappe.whitelist()
def validate_company_gstins(company=None, company_gstin=None):
    """
    Checks the validity of the company's GSTIN authentication.

    Args:
        company_gstin (str): The GSTIN of the company to validate.

    Returns:
        dict: A dictionary where the keys are the GSTINs and the values are booleans indicating whether the authentication is valid.
    """
    frappe.has_permission("GST Settings", throw=True)

    credentials = get_company_gstin_credentials(company, company_gstin)

    if company_gstin and not credentials:
        frappe.throw(
            _("Missing GSTIN credentials for GSTIN: {gstin}.").format(
                gstin=company_gstin
            )
        )

    if not credentials:
        frappe.throw(_("Missing credentials in GST Settings"))

    if company and not company_gstin:
        missing_credentials = set(get_gstin_list(company)) - set(
            credential.gstin for credential in credentials
        )

        if missing_credentials:
            frappe.throw(
                _("Missing GSTIN credentials for GSTIN(s): {gstins}.").format(
                    gstins=", ".join(missing_credentials),
                )
            )

    gstin_authentication_status = {
        credential.gstin: (
            credential.session_expiry
            and credential.auth_token
            and credential.session_expiry > add_to_date(now_datetime(), minutes=30)
        )
        for credential in credentials
    }

    return gstin_authentication_status


def get_company_gstin_credentials(company=None, company_gstin=None):
    filters = {"service": "Returns"}

    if company:
        filters["company"] = company

    if company_gstin:
        filters["gstin"] = company_gstin

    return frappe.get_all(
        "GST Credential",
        filters=filters,
        fields=["gstin", "session_expiry", "auth_token"],
    )


@frappe.whitelist()
def request_otp(company_gstin):
    frappe.has_permission("GST Settings", throw=True)

    return ReturnsAPI(company_gstin).request_otp()


@frappe.whitelist()
def authenticate_otp(company_gstin, otp):
    frappe.has_permission("GST Settings", throw=True)

    api = ReturnsAPI(company_gstin)
    response = api.autheticate_with_otp(otp)

    return api.process_response(response)
