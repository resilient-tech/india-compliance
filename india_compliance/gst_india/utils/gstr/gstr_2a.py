from datetime import datetime

import frappe

from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr.gstr import (
    API_VALUES_MAP,
    GSTR,
    get_mapped_value,
)


def map_date_format(date_str, source_format, target_format):
    return date_str and datetime.strptime(date_str, source_format).strftime(
        target_format
    )


class GSTR2a(GSTR):
    def get_supplier_details(self, supplier):
        return {
            "supplier_gstin": supplier.ctin,
            "gstr_1_filled": API_VALUES_MAP.Y_N_to_check.get(supplier.cfs),
            "gstr_3b_filled": API_VALUES_MAP.Y_N_to_check.get(supplier.cfs3b),
            "gstr_1_filing_date": parse_datetime(supplier.fldtr1),
            "registration_cancel_date": parse_datetime(supplier.dtcancel),
            "sup_return_period": map_date_format(supplier.flprdr1, "%b-%y", "%m%Y"),
        }

    # item details are in item_det for GSTR2a
    def get_transaction_items(self, invoice):
        return [
            self.get_transaction_item(
                frappe._dict(item.get("itm_det", {})), item.get("num", 0)
            )
            for item in invoice.get(self.keys_map.get("items_key"))
        ]

    def get_transaction_item(self, item, item_number=None):
        return {
            "item_number": item_number,
            "rate": item.rt,
            "taxable_value": item.txval,
            "igst": item.iamt,
            "cgst": item.camt,
            "sgst": item.samt,
            "cess": item.csamt,
        }


class GSTR2aB2B(GSTR2a):
    def setup(self):
        super().setup()
        self.keys_map.update(
            {
                "invoice_key": "inv",
                "items_key": "itms",
            }
        )

    def get_invoice_details(self, invoice):
        return {
            "bill_no": invoice.inum,
            "supply_type": API_VALUES_MAP.gst_category.get(invoice.inv_typ),
            "bill_date": parse_datetime(invoice.idt, day_first=True),
            "document_value": invoice.val,
            "place_of_supply": API_VALUES_MAP.states.get(invoice.pos),
            "other_return_period": map_date_format(invoice.aspd, "%b-%y", "%m%Y"),
            "amendment_type": API_VALUES_MAP.amend_type.get(invoice.atyp),
            "is_reverse_charge": API_VALUES_MAP.Y_N_to_check.get(invoice.rchrg),
            "diffpercent": get_mapped_value(
                invoice.diff_percent, {1: 1, 0.65: 0.65, None: 1}
            ),
            "irn_source": invoice.srctyp,
            "irn_number": invoice.irn,
            "irn_gen_date": parse_datetime(invoice.irngendate, day_first=True),
            "doc_type": "Invoice",
        }


class GSTR2aB2BA(GSTR2aB2B):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.oinum,
                "original_bill_date": parse_datetime(invoice.oidt, day_first=True),
            }
        )
        return invoice_details


class GSTR2aCDNR(GSTR2aB2B):
    def setup(self):
        super().setup()
        self.keys_map["invoice_key"] = "nt"

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "bill_no": invoice.nt_num,
                "doc_type": API_VALUES_MAP.note_type.get(invoice.ntty),
                "bill_date": parse_datetime(invoice.nt_dt, day_first=True),
            }
        )
        return invoice_details


class GSTR2aCDNRA(GSTR2aCDNR):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.ont_num,
                "original_bill_date": parse_datetime(invoice.ont_dt, day_first=True),
                "original_doc_type": API_VALUES_MAP.note_type.get(invoice.ntty),
            }
        )
        return invoice_details


class GSTR2aISD(GSTR2a):
    def setup(self):
        super().setup()
        self.keys_map["invoice_key"] = "doclist"

    def get_invoice_details(self, invoice):
        return {
            "doc_type": API_VALUES_MAP.isd_type_2a.get(invoice.isd_docty),
            "bill_no": invoice.docnum,
            "bill_date": parse_datetime(invoice.docdt, day_first=True),
            "itc_availability": API_VALUES_MAP.yes_no.get(invoice.itc_elg),
            "other_return_period": map_date_format(invoice.aspd, "%b-%y", "%m%Y"),
            "is_amended": 1 if invoice.atyp else 0,
            "amendment_type": API_VALUES_MAP.amend_type.get(invoice.atyp),
            "document_value": invoice.iamt + invoice.camt + invoice.samt + invoice.cess,
        }

    def get_transaction_item(self, item):
        transaction_item = super().get_transaction_item(item)
        transaction_item["cess"] = item.cess
        return transaction_item

    # item details are included in invoice details
    def get_transaction_items(self, invoice):
        return [self.get_transaction_item(invoice)]


class GSTR2aISDA(GSTR2aISD):
    pass


class GSTR2aIMPG(GSTR2a):
    def get_supplier_details(self, supplier):
        return {}

    def get_invoice_details(self, invoice):
        return {
            "doc_type": "Bill of Entry",  # custom field
            "bill_no": invoice.benum,
            "bill_date": parse_datetime(invoice.bedt, day_first=True),
            "is_amended": API_VALUES_MAP.Y_N_to_check.get(invoice.amd),
            "port_code": invoice.portcd,
            "document_value": invoice.txval + invoice.iamt + invoice.csamt,
        }

    # invoice details are included in supplier details
    def get_supplier_transactions(self, category, supplier):
        return [
            self.get_transaction(
                category, frappe._dict(supplier), frappe._dict(supplier)
            )
        ]

    # item details are included in invoice details
    def get_transaction_items(self, invoice):
        return [self.get_transaction_item(invoice)]


class GSTR2aIMPGSEZ(GSTR2aIMPG):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "supplier_gstin": invoice.sgstin,
                "supplier_name": invoice.tdname,
            }
        )
        return invoice_details
