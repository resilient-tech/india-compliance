import frappe
from frappe.utils import flt
from frappe.utils.data import format_date

from india_compliance.gst_india.constants import ACTION_MAP, STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    update_previous_ims_action as _update_previous_ims_action,
)
from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import (
    GST_CATEGORY,
    STATES,
    get_mapped_value,
    get_unique_key,
)
from india_compliance.gst_returns.fields.ims import CLASSIFICATION_MAP
from india_compliance.gst_returns.fields.ims import DocField as doc
from india_compliance.gst_returns.fields.ims import RawField as raw
from india_compliance.gst_returns.steps import take

# stored value -> gov code, for upload
REVERSE_ACTION = {value: code for code, value in ACTION_MAP.items()}
REVERSE_GST_CATEGORY = {value: code for code, value in GST_CATEGORY.items()}

# portal -> GST Inward Supply, plain copies; the coded fields sit in the class
INVOICE_KEYS = {
    raw.SUPPLIER_GSTIN: doc.SUPPLIER_GSTIN,
    raw.SUP_RETURN_PERIOD: doc.SUP_RETURN_PERIOD,
    raw.SUP_RETURN_FORM: doc.SUPPLIER_RETURN_FORM,
    raw.DOC_VALUE: doc.DOC_VALUE,
    raw.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    raw.IGST: doc.IGST,
    raw.CGST: doc.CGST,
    raw.SGST: doc.SGST,
    raw.CESS: doc.CESS,
    raw.REMARKS: doc.REMARKS,
}


class IMS:
    # specified records carry the declared ITC block
    EMITS_ITC_REDUCTION = False

    def __init__(self, company=None, gstin=None, *args):
        self.company_gstin = gstin
        self.company = company
        self.existing_transactions = self.get_existing_transactions()

    def create_transactions(self, invoices, rejected_data):
        self.reset_previous_ims_action()

        if not invoices:
            self.handle_missing_transactions()
            return

        transactions = self.get_all_transactions(invoices)

        for transaction in transactions:
            create_inward_supply(transaction)

            if transaction.get("unique_key") in self.existing_transactions:
                self.existing_transactions.pop(transaction.get("unique_key"))

        self.handle_missing_transactions()

    def get_all_transactions(self, invoices):
        transactions = []
        for invoice in invoices:
            invoice = frappe._dict(invoice)
            transactions.append(self.get_transaction(invoice))

        return transactions

    def update_previous_ims_action(self, uploaded_invoices, error_invoices):
        errors = set()

        for supplier in error_invoices:
            for invoice in supplier.get(raw.INVOICES):
                # same key across categories
                errors.add(f"{invoice.get(raw.DOC_NUMBER)}_{supplier.get(raw.SUPPLIER_GSTIN)}")

        for invoice in uploaded_invoices:
            invoice = self.get_transaction(frappe._dict(invoice))

            # different keys across categories
            if f"{invoice.get(doc.BILL_NO)}_{invoice.get(doc.SUPPLIER_GSTIN)}" in errors:
                continue

            _update_previous_ims_action(invoice)

    def get_transaction(self, invoice):
        transaction = frappe._dict(
            **self.convert_data_to_internal_format(invoice),
            **self.get_invoice_details(invoice),
        )

        transaction["unique_key"] = get_unique_key(transaction)

        return transaction

    def convert_data_to_internal_format(self, invoice):
        classification, doc_type = CLASSIFICATION_MAP[self.ims_category()]
        itc_reduction = invoice.get(raw.ITC_REDUCTION_REQUIRED)

        details = take(invoice, INVOICE_KEYS)
        details.update(
            {
                doc.CLASSIFICATION: classification,
                doc.DOC_TYPE: doc_type,
                doc.COMPANY: self.company,
                doc.COMPANY_GSTIN: self.company_gstin,
                doc.FROM_IMS: 1,
                doc.SUPPLY_TYPE: get_mapped_value(invoice.get(raw.SUPPLY_TYPE), GST_CATEGORY),
                doc.POS: get_mapped_value(invoice.get(raw.POS), STATES),
                doc.PREVIOUS_IMS_ACTION: get_mapped_value(invoice.get(raw.ACTION), ACTION_MAP),
                doc.IS_PENDING_ACTION_ALLOWED: invoice.get(raw.PENDING_ACTION_BLOCKED) == "N",
                doc.IS_SUPPLIER_RETURN_FILED: 0 if invoice.get(raw.SUP_FILING_STATUS) == "Not Filed" else 1,
                # itcRedReq: Y = reduce ITC, N = nothing claimed, absent = no action yet
                doc.ITC_REDUCTION_REQUIRED: 1 if itc_reduction == "Y" else 0,
                doc.IS_ITC_REDUCTION_BLOCKED: 1 if invoice.get(raw.ITC_REDUCTION_BLOCKED) == "Y" else 0,
                doc.IS_REMARKS_BLOCKED: 1 if invoice.get(raw.REMARKS_BLOCKED) == "Y" else 0,
                # declared reversal per head; portal omits values for a full reversal -> supplier
                doc.DECLARED_IGST: self._declared_reversal(
                    invoice.get(raw.DECLARED_IGST), invoice.get(raw.IGST), itc_reduction
                ),
                doc.DECLARED_CGST: self._declared_reversal(
                    invoice.get(raw.DECLARED_CGST), invoice.get(raw.CGST), itc_reduction
                ),
                doc.DECLARED_SGST: self._declared_reversal(
                    invoice.get(raw.DECLARED_SGST), invoice.get(raw.SGST), itc_reduction
                ),
                doc.DECLARED_CESS: self._declared_reversal(
                    invoice.get(raw.DECLARED_CESS), invoice.get(raw.CESS), itc_reduction
                ),
            }
        )

        return details

    def convert_data_to_gov_format(self, invoice):
        data = {
            raw.SUPPLIER_GSTIN: invoice.get(doc.SUPPLIER_GSTIN),
            raw.SUPPLY_TYPE: get_mapped_value(invoice.get(doc.SUPPLY_TYPE), REVERSE_GST_CATEGORY),
            raw.SUP_RETURN_FORM: invoice.get(doc.SUPPLIER_RETURN_FORM),
            raw.SUP_RETURN_PERIOD: invoice.get(doc.SUP_RETURN_PERIOD),
            raw.DOC_VALUE: invoice.get(doc.DOC_VALUE),
            raw.POS: get_mapped_value(invoice.get(doc.POS).split("-")[1], STATE_NUMBERS),
            raw.PREVIOUS_ACTION: get_mapped_value(invoice.get(doc.PREVIOUS_IMS_ACTION), REVERSE_ACTION),
            raw.IGST: invoice.get(doc.IGST),
            raw.CGST: invoice.get(doc.CGST),
            raw.SGST: invoice.get(doc.SGST),
            raw.CESS: invoice.get(doc.CESS),
            raw.TAXABLE_VALUE: invoice.get(doc.TAXABLE_VALUE),
        }

        if invoice.get(doc.IMS_ACTION) != "No Action":
            data[raw.ACTION] = get_mapped_value(invoice.get(doc.IMS_ACTION), REVERSE_ACTION)

        self.set_itc_reduction(data, invoice)

        return data

    def set_itc_reduction(self, data, invoice):
        # remarks: any action, when not blocked
        if (
            invoice.get(doc.IMS_ACTION) in ("Accepted", "Rejected", "Pending")
            and invoice.get(doc.REMARKS)
            and not invoice.get(doc.IS_REMARKS_BLOCKED)
        ):
            data[raw.REMARKS] = invoice.get(doc.REMARKS)

        # declared reversal: specified accepts, if govt allows
        if (
            not self.EMITS_ITC_REDUCTION
            or invoice.get(doc.IMS_ACTION) != "Accepted"
            or invoice.get(doc.IS_ITC_REDUCTION_BLOCKED)
        ):
            return

        declared = {
            raw.DECLARED_IGST: flt(invoice.get(doc.DECLARED_IGST)),
            raw.DECLARED_CGST: flt(invoice.get(doc.DECLARED_CGST)),
            raw.DECLARED_SGST: flt(invoice.get(doc.DECLARED_SGST)),
            raw.DECLARED_CESS: flt(invoice.get(doc.DECLARED_CESS)),
        }

        # nothing claimed -> no reversal
        if not any(declared.values()):
            data[raw.ITC_REDUCTION_REQUIRED] = "N"
            return

        data[raw.ITC_REDUCTION_REQUIRED] = "Y"

        # full reversal -> omit values (portal reads absence as full); partial -> send them
        supplier = (
            invoice.get(doc.IGST),
            invoice.get(doc.CGST),
            invoice.get(doc.SGST),
            invoice.get(doc.CESS),
        )
        if any(flt(d, 2) != flt(s, 2) for d, s in zip(declared.values(), supplier, strict=True)):
            data.update(declared)

    def _declared_reversal(self, declared, supplier, itc_red_req):
        # specified record with no value = full reversal -> supplier
        if self.EMITS_ITC_REDUCTION and itc_red_req != "N" and declared is None:
            return supplier
        return declared

    def get_existing_transactions(self):
        category, doc_type = CLASSIFICATION_MAP[self.ims_category()]

        inward_supply = frappe.qb.DocType("GST Inward Supply")
        existing_transactions = (
            frappe.qb.from_(inward_supply)
            .select(
                inward_supply.name,
                inward_supply.supplier_gstin,
                inward_supply.bill_no,
                inward_supply.doc_type,
            )
            .where(inward_supply.is_downloaded_from_2b == 0)
            .where(inward_supply.is_downloaded_from_2a == 0)
            .where(inward_supply.is_downloaded_from_ims == 1)
            .where(inward_supply.is_supplier_return_filed == 0)
            .where(inward_supply.classification == category)
            .where(inward_supply.doc_type == doc_type)
            .where(inward_supply.company_gstin == self.company_gstin)
            .run(as_dict=True)
        )

        return {get_unique_key(transaction): transaction.get("name") for transaction in existing_transactions}

    def handle_missing_transactions(self):
        if not self.existing_transactions:
            return

        for inward_supply_name in self.existing_transactions.values():
            frappe.delete_doc("GST Inward Supply", inward_supply_name, ignore_permissions=True)

    def reset_previous_ims_action(self):
        category, doc_type = CLASSIFICATION_MAP[self.ims_category()]
        inward_supply = frappe.qb.DocType("GST Inward Supply")

        # blank baseline; download re-fills action and re-flags declaration if ours differs
        (
            frappe.qb.update(inward_supply)
            .set(inward_supply.previous_ims_action, "")
            .set(inward_supply.is_declaration_pending_upload, 0)
            .where(inward_supply.classification == category)
            .where(inward_supply.doc_type == doc_type)
            .where(inward_supply.company_gstin == self.company_gstin)
            .run()
        )

    def ims_category(self):
        return type(self).__name__.removeprefix("IMS")


class IMSB2B(IMS):
    def get_invoice_details(self, invoice):
        return {
            doc.BILL_NO: invoice.get(raw.DOC_NUMBER),
            doc.BILL_DATE: parse_datetime(invoice.get(raw.DOC_DATE), day_first=True),
        }

    def get_category_details(self, invoice):
        return {
            raw.DOC_NUMBER: invoice.get(doc.BILL_NO),
            raw.DOC_DATE: format_date(invoice.get(doc.BILL_DATE), "dd-mm-yyyy"),
        }


class IMSB2BA(IMSB2B):
    EMITS_ITC_REDUCTION = True

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                doc.ORIGINAL_BILL_NO: invoice.get(raw.ORIGINAL_DOC_NUMBER),
                doc.ORIGINAL_BILL_DATE: parse_datetime(invoice.get(raw.ORIGINAL_DOC_DATE), day_first=True),
                doc.IS_AMENDED: True,
            }
        )
        return invoice_details

    def get_category_details(self, invoice):
        invoice_details = super().get_category_details(invoice)
        invoice_details.update(
            {
                raw.ORIGINAL_DOC_NUMBER: invoice.get(doc.ORIGINAL_BILL_NO),
                raw.ORIGINAL_DOC_DATE: format_date(invoice.get(doc.ORIGINAL_BILL_DATE), "dd-mm-yyyy"),
            }
        )
        return invoice_details


class IMSB2BDN(IMSB2B):
    def get_invoice_details(self, invoice):
        return {
            doc.BILL_NO: invoice.get(raw.NOTE_NUMBER),
            doc.BILL_DATE: parse_datetime(invoice.get(raw.NOTE_DATE), day_first=True),
        }

    def get_category_details(self, invoice):
        return {
            raw.NOTE_NUMBER: invoice.get(doc.BILL_NO),
            raw.NOTE_DATE: format_date(invoice.get(doc.BILL_DATE), "dd-mm-yyyy"),
        }


class IMSB2BDNA(IMSB2BDN):
    EMITS_ITC_REDUCTION = True

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                doc.ORIGINAL_BILL_NO: invoice.get(raw.ORIGINAL_NOTE_NUMBER),
                doc.ORIGINAL_BILL_DATE: parse_datetime(invoice.get(raw.ORIGINAL_NOTE_DATE), day_first=True),
                doc.IS_AMENDED: True,
                doc.ORIGINAL_DOC_TYPE: "Debit Note",
            }
        )
        return invoice_details

    def get_category_details(self, invoice):
        invoice_details = super().get_category_details(invoice)
        invoice_details.update(
            {
                raw.ORIGINAL_NOTE_NUMBER: invoice.get(doc.ORIGINAL_BILL_NO),
                raw.ORIGINAL_NOTE_DATE: format_date(invoice.get(doc.ORIGINAL_BILL_DATE), "dd-mm-yyyy"),
            }
        )
        return invoice_details


class IMSB2BCN(IMSB2BDN):
    EMITS_ITC_REDUCTION = True


class IMSB2BCNA(IMSB2BDNA):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                doc.ORIGINAL_DOC_TYPE: "Credit Note",
            }
        )
        return invoice_details


def get_data_handler(category):
    return globals().get(f"IMS{category}")
