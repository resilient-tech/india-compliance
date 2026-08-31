import frappe
from frappe.utils import flt
from frappe.utils.data import format_date

from india_compliance.gst_india.constants import (
    ACTION_MAP,
    GST_CATEGORY_MAP,
    STATE_NUMBERS,
)
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    update_previous_ims_action as _update_previous_ims_action,
)
from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import get_mapped_value, get_unique_key

CLASSIFICATION_MAP = {
    "B2B": ["B2B", "Invoice"],
    "B2BA": ["B2BA", "Invoice"],
    "B2BCN": ["CDNR", "Credit Note"],
    "B2BCNA": ["CDNRA", "Credit Note"],
    "B2BDN": ["CDNR", "Debit Note"],
    "B2BDNA": ["CDNRA", "Debit Note"],
}


class IMS:
    # specified records carry the declared ITC block
    EMITS_ITC_REDUCTION = False

    VALUE_MAPS = frappe._dict(
        {
            "states": {value: f"{value}-{key}" for key, value in STATE_NUMBERS.items()},
            "reverse_states": STATE_NUMBERS,
            "action": ACTION_MAP,
            "reverse_action": {v: k for k, v in ACTION_MAP.items()},
            "gst_category": GST_CATEGORY_MAP,
            "reverse_gst_category": {v: k for k, v in GST_CATEGORY_MAP.items()},
            "classification": CLASSIFICATION_MAP,
        }
    )

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
            for invoice in supplier.get("inv"):
                # same key across categories
                errors.add(f"{invoice.get('inum')}_{supplier.get('stin')}")

        for invoice in uploaded_invoices:
            invoice = self.get_transaction(frappe._dict(invoice))

            # different keys across categories
            if f"{invoice.get('bill_no')}_{invoice.get('supplier_gstin')}" in errors:
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
        return {
            "supplier_gstin": invoice.stin,
            "sup_return_period": invoice.rtnprd,
            "supply_type": get_mapped_value(invoice.inv_typ, self.VALUE_MAPS.gst_category),
            "place_of_supply": get_mapped_value(invoice.pos, self.VALUE_MAPS.states),
            "document_value": invoice.val,
            "company": self.company,
            "company_gstin": self.company_gstin,
            "is_pending_action_allowed": invoice.ispendactblocked == "N",
            "previous_ims_action": get_mapped_value(invoice.action, self.VALUE_MAPS.action),
            "is_downloaded_from_ims": 1,
            "is_supplier_return_filed": 0 if invoice.srcfilstatus == "Not Filed" else 1,
            "supplier_return_form": invoice.srcform,
            "cgst": invoice.camt,
            "sgst": invoice.samt,
            "igst": invoice.iamt,
            "cess": invoice.cess,
            "taxable_value": invoice.txval,
            # itcRedReq: Y = reduce ITC, N = nothing claimed, absent = no action yet
            "itc_reduction_required": 1 if invoice.itcRedReq == "Y" else 0,
            "is_itc_reduction_blocked": 1 if invoice.isItcRedReqBlocked == "Y" else 0,
            # declared reversal per head; portal omits values for a full reversal -> supplier
            "declared_igst": self._declared_reversal(invoice.declIgst, invoice.iamt, invoice.itcRedReq),
            "declared_cgst": self._declared_reversal(invoice.declCgst, invoice.camt, invoice.itcRedReq),
            "declared_sgst": self._declared_reversal(invoice.declSgst, invoice.samt, invoice.itcRedReq),
            "declared_cess": self._declared_reversal(invoice.declCess, invoice.cess, invoice.itcRedReq),
            "remarks": invoice.remarks,
            "is_remarks_blocked": 1 if invoice.isRemarksBlocked == "Y" else 0,
        }

    def convert_data_to_gov_format(self, invoice):
        data = {
            "stin": invoice.supplier_gstin,
            "inv_typ": get_mapped_value(invoice.supply_type, self.VALUE_MAPS.reverse_gst_category),
            "srcform": invoice.supplier_return_form,
            "rtnprd": invoice.sup_return_period,
            "val": invoice.document_value,
            "pos": get_mapped_value(invoice.place_of_supply.split("-")[1], self.VALUE_MAPS.reverse_states),
            "prev_status": get_mapped_value(invoice.previous_ims_action, self.VALUE_MAPS.reverse_action),
            "iamt": invoice.igst,
            "camt": invoice.cgst,
            "samt": invoice.sgst,
            "cess": invoice.cess,
            "txval": invoice.taxable_value,
        }

        if invoice.ims_action != "No Action":
            data["action"] = get_mapped_value(invoice.ims_action, self.VALUE_MAPS.reverse_action)

        self.set_itc_reduction(data, invoice)

        return data

    def set_itc_reduction(self, data, invoice):
        # remarks: any action, when not blocked
        if (
            invoice.ims_action in ("Accepted", "Rejected", "Pending")
            and invoice.remarks
            and not invoice.is_remarks_blocked
        ):
            data["remarks"] = invoice.remarks

        # declared reversal: specified accepts, if govt allows
        if (
            not self.EMITS_ITC_REDUCTION
            or invoice.ims_action != "Accepted"
            or invoice.is_itc_reduction_blocked
        ):
            return

        declared = {
            "declIgst": flt(invoice.declared_igst),
            "declCgst": flt(invoice.declared_cgst),
            "declSgst": flt(invoice.declared_sgst),
            "declCess": flt(invoice.declared_cess),
        }

        # nothing claimed -> no reversal
        if not any(declared.values()):
            data["itcRedReq"] = "N"
            return

        data["itcRedReq"] = "Y"

        # full reversal -> omit values (portal reads absence as full); partial -> send them
        supplier = (invoice.igst, invoice.cgst, invoice.sgst, invoice.cess)
        if any(flt(d, 2) != flt(s, 2) for d, s in zip(declared.values(), supplier, strict=True)):
            data.update(declared)

    def _declared_reversal(self, declared, supplier, itc_red_req):
        # specified record with no value = full reversal -> supplier
        if self.EMITS_ITC_REDUCTION and itc_red_req != "N" and declared is None:
            return supplier
        return declared

    def get_existing_transactions(self):
        category, doc_type = get_mapped_value(self.ims_category(), self.VALUE_MAPS.classification)

        inward_supply = frappe.qb.DocType("GST Inward Supply")
        existing_transactions = (
            frappe.qb.from_(inward_supply)
            .select(inward_supply.name, inward_supply.supplier_gstin, inward_supply.bill_no)
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
        category, doc_type = get_mapped_value(self.ims_category(), self.VALUE_MAPS.classification)
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
            "bill_no": invoice.inum,
            "bill_date": parse_datetime(invoice.idt, day_first=True),
            "classification": "B2B",
            "doc_type": "Invoice",
        }

    def get_category_details(self, invoice):
        return {
            "inum": invoice.bill_no,
            "idt": format_date(invoice.bill_date, "dd-mm-yyyy"),
        }


class IMSB2BA(IMSB2B):
    EMITS_ITC_REDUCTION = True

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.oinum,
                "original_bill_date": parse_datetime(invoice.oidt, day_first=True),
                "is_amended": True,
                "classification": "B2BA",
            }
        )
        return invoice_details

    def get_category_details(self, invoice):
        invoice_details = super().get_category_details(invoice)
        invoice_details.update(
            {
                "oinum": invoice.original_bill_no,
                "oidt": format_date(invoice.original_bill_date, "dd-mm-yyyy"),
            }
        )
        return invoice_details


class IMSB2BDN(IMSB2B):
    def get_invoice_details(self, invoice):
        return {
            "bill_no": invoice.nt_num,
            "bill_date": parse_datetime(invoice.nt_dt, day_first=True),
            "classification": "CDNR",
            "doc_type": "Debit Note",
        }

    def get_category_details(self, invoice):
        return {
            "nt_num": invoice.bill_no,
            "nt_dt": format_date(invoice.bill_date, "dd-mm-yyyy"),
        }


class IMSB2BDNA(IMSB2BDN):
    EMITS_ITC_REDUCTION = True

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.ont_num,
                "original_bill_date": parse_datetime(invoice.ont_dt, day_first=True),
                "is_amended": True,
                "original_doc_type": "Debit Note",
                "classification": "CDNRA",
            }
        )
        return invoice_details

    def get_category_details(self, invoice):
        invoice_details = super().get_category_details(invoice)
        invoice_details.update(
            {
                "ont_num": invoice.original_bill_no,
                "ont_dt": format_date(invoice.original_bill_date, "dd-mm-yyyy"),
            }
        )
        return invoice_details


class IMSB2BCN(IMSB2BDN):
    EMITS_ITC_REDUCTION = True

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "doc_type": "Credit Note",
            }
        )
        return invoice_details


class IMSB2BCNA(IMSB2BDNA):
    EMITS_ITC_REDUCTION = True

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "doc_type": "Credit Note",
                "original_doc_type": "Credit Note",
            }
        )
        return invoice_details

    def get_category_details(self, invoice):
        invoice_details = super().get_category_details(invoice)
        invoice_details.update(
            {
                "ont_num": invoice.original_bill_no,
                "ont_dt": format_date(invoice.original_bill_date, "dd-mm-yyyy"),
            }
        )
        return invoice_details


def get_data_handler(category):
    return globals().get(f"IMS{category}")
