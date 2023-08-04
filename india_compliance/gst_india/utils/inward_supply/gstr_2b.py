import frappe

from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.inward_supply.inward_supply import InwardSupply


class GSTR2b(InwardSupply):
    def get_transaction(self, category, supplier, invoice):
        transaction = super().get_transaction(category, supplier, invoice)
        transaction.return_period_2b = self.return_period
        transaction.gen_date_2b = parse_datetime(self.gen_date_2b, day_first=True)
        return transaction

    def get_supplier_details(self, supplier):
        return {
            "supplier_gstin": supplier.ctin,
            "supplier_name": supplier.trdnm,
            "gstr_1_filing_date": parse_datetime(supplier.supfildt, day_first=True),
            "sup_return_period": supplier.supprd,
        }

    def get_transaction_item(self, item):
        return {
            "item_number": item.num,
            "rate": item.rt,
            "taxable_value": item.txval,
            "igst": item.igst,
            "cgst": item.cgst,
            "sgst": item.sgst,
            "cess": item.cess,
        }


class GSTR2bB2B(GSTR2b):
    def setup(self):
        super().setup()
        self.keys_map.update(
            {
                "invoice_key": "inv",
                "items_key": "items",
            }
        )

    def get_invoice_details(self, invoice):
        return {
            "bill_no": invoice.inum,
            "supply_type": self.API_VALUES_MAP.gst_category.get(invoice.typ),
            "bill_date": parse_datetime(invoice.dt, day_first=True),
            "document_value": invoice.val,
            "place_of_supply": self.API_VALUES_MAP.states.get(invoice.pos),
            "is_reverse_charge": self.API_VALUES_MAP.Y_N_to_check.get(invoice.rev),
            "itc_availability": {**self.API_VALUES_MAP.yes_no, "T": "Temporary"}.get(
                invoice.itcavl
            ),
            "reason_itc_unavailability": self.API_VALUES_MAP.itc_unavailability_reason.get(
                invoice.rsn
            ),
            "diffprcnt": self.API_VALUES_MAP.diff_percentage.get(invoice.diffprcnt),
            "irn_source": invoice.srctyp,
            "irn_number": invoice.irn,
            "irn_gen_date": parse_datetime(invoice.irngendate, day_first=True),
            "doc_type": "Invoice",  # Custom Field
        }


class GSTR2bB2BA(GSTR2bB2B):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.oinum,
                "original_bill_date": parse_datetime(invoice.oidt, day_first=True),
            }
        )
        return invoice_details


class GSTR2bCDNR(GSTR2bB2B):
    def setup(self):
        super().setup()
        self.keys_map["invoice_key"] = "nt"

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "bill_no": invoice.ntnum,
                "doc_type": self.API_VALUES_MAP.note_type.get(invoice.typ),
                "supply_type": self.API_VALUES_MAP.gst_category.get(invoice.suptyp),
            }
        )
        return invoice_details


class GSTR2bCDNRA(GSTR2bCDNR):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.ontnum,
                "original_bill_date": parse_datetime(invoice.ontdt, day_first=True),
                "original_doc_type": self.API_VALUES_MAP.note_type.get(invoice.onttyp),
            }
        )
        return invoice_details


class GSTR2bISD(GSTR2b):
    def setup(self):
        super().setup()
        self.keys_map["invoice_key"] = "doclist"

    def get_invoice_details(self, invoice):
        return {
            "doc_type": self.API_VALUES_MAP.isd_type_2b.get(invoice.doctyp),
            "bill_no": invoice.docnum,
            "bill_date": parse_datetime(invoice.docdt, day_first=True),
            "itc_availability": self.API_VALUES_MAP.yes_no.get(invoice.itcelg),
            "document_value": invoice.igst + invoice.cgst + invoice.sgst + invoice.cess,
        }

    # item details are included in invoice details
    def get_transaction_items(self, invoice):
        return [self.get_transaction_item(invoice)]


class GSTR2bISDA(GSTR2bISD):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.odocnum,
                "original_bill_date": parse_datetime(invoice.odocdt, day_first=True),
                "original_doc_type": self.API_VALUES_MAP.isd_type_2b.get(
                    invoice.odoctyp
                ),
            }
        )
        return invoice_details


class GSTR2bIMPGSEZ(GSTR2b):
    def setup(self):
        super().setup()
        self.keys_map["invoice_key"] = "boe"

    def get_invoice_details(self, invoice):
        return {
            "doc_type": "Bill of Entry",  # custom field
            "bill_no": invoice.boenum,
            "bill_date": parse_datetime(invoice.boedt, day_first=True),
            "is_amended": self.API_VALUES_MAP.Y_N_to_check.get(invoice.isamd),
            "port_code": invoice.portcode,
            "document_value": invoice.txval + invoice.igst + invoice.cess,
            "itc_availability": "Yes",  # always available
        }

    # item details are included in invoice details
    def get_transaction_items(self, invoice):
        return [self.get_transaction_item(invoice)]


class GSTR2bIMPG(GSTR2bIMPGSEZ):
    def get_supplier_details(self, supplier):
        return {}

    # invoice details are included in supplier details
    def get_supplier_transactions(self, category, supplier):
        return [
            self.get_transaction(
                category, frappe._dict(supplier), frappe._dict(supplier)
            )
        ]
