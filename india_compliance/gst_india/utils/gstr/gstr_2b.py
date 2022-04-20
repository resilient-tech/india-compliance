import frappe

from india_compliance.gst_india.api_classes.returns import GSTR2bAPI
from india_compliance.gst_india.doctype.gstr_download_log.gstr_download_log import (
    create_download_log,
)
from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr import (
    GSTR,
    ReturnType,
    get_mapped_value,
    save_gstr,
)


def download_gstr_2b(gstin, return_periods, otp=None):
    api = GSTR2bAPI(gstin)
    for return_period in return_periods:
        response = api.get_data(return_period, otp)
        if response.error_type == "otp_requested":
            return response

        if response.error_type == "no_docs_found":
            create_download_log(
                gstin, ReturnType.GSTR2B, return_period, data_not_found=True
            )
            continue

        json_data = response.json_data
        # TODO: confirm about throwing
        if (
            not json_data
            or json_data.get("gstin") != gstin
            or json_data.get("rtnprd") != return_period
        ):
            frappe.throw(
                "Data received seems to be invalid from the GST Portal. Please try"
                " again or raise support ticket.",
                title="Invalid Response Received.",
            )

        save_gstr(return_period, json_data.get("docdata"))


class GSTR2b(GSTR):
    def get_transaction(self, category, supplier, invoice):
        transaction = super().get_transaction(category, supplier, invoice)

        transaction.return_period_2b = self.return_period
        # TODO: find a way to save gendt
        transaction.gen_date_2b = parse_datetime(
            self.json_data.get("gendt"), day_first=True
        )
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
        self.KEY_MAPS.items_key = "items"
        self.KEY_MAPS.invoice_key = "inv"

    def get_invoice_details(self, invoice):
        return {
            "doc_number": invoice.inum,
            "supply_type": get_mapped_value(invoice.typ, self.VALUE_MAPS.gst_category),
            "doc_date": parse_datetime(invoice.dt, day_first=True),
            "document_value": invoice.val,
            "place_of_supply": get_mapped_value(invoice.pos, self.VALUE_MAPS.states),
            "reverse_charge": get_mapped_value(invoice.rev, self.VALUE_MAPS.yes_no),
            "itc_availability": get_mapped_value(
                invoice.itcavl, {"Y": "Yes", "N": "No", "T": "Temporary"}
            ),
            "reason_itc_unavailability": get_mapped_value(
                invoice.rsn,
                {
                    "P": (
                        "POS and supplier state are same but recipient state is"
                        " different"
                    ),
                    "C": "Return filed post annual cut-off",
                },
            ),
            "diffprcnt": get_mapped_value(
                invoice.diffprcnt, {1: 1, 0.65: 0.65, None: 1}
            ),
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
                "original_doc_number": invoice.oinum,
                "original_doc_date": parse_datetime(invoice.oidt, day_first=True),
            }
        )
        return invoice_details


class GSTR2bCDNR(GSTR2bB2B):
    def setup(self):
        super().setup()
        self.KEY_MAPS.invoice_key = "nt"

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "doc_number": invoice.ntnum,
                "doc_type": get_mapped_value(invoice.typ, self.VALUE_MAPS.note_type),
                "supply_type": get_mapped_value(
                    invoice.suptyp, self.VALUE_MAPS.gst_category
                ),
            }
        )
        return invoice_details


class GSTR2bCDNRA(GSTR2bCDNR):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_doc_number": invoice.ontnum,
                "original_doc_date": parse_datetime(invoice.ontdt, day_first=True),
                "original_doc_type": get_mapped_value(
                    invoice.onttyp, self.VALUE_MAPS.note_type
                ),
            }
        )
        return invoice_details


class GSTR2bISD(GSTR2b):
    def setup(self):
        super().setup()
        self.KEY_MAPS.invoice_key = "doclist"

    def get_invoice_details(self, invoice):
        return {
            "doc_type": get_mapped_value(invoice.doctyp, self.VALUE_MAPS.isd_type),
            "doc_number": invoice.docnum,
            "doc_date": parse_datetime(invoice.docdt, day_first=True),
            "itc_availability": get_mapped_value(
                invoice.itcelg, {"Y": "Yes", "N": "No"}
            ),
        }

    # item details are included in invoice details
    def get_transaction_items(self, invoice):
        return [self.get_transaction_item(invoice)]


class GSTR2bISDA(GSTR2bISD):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_doc_number": invoice.odocnum,
                "original_doc_date": parse_datetime(invoice.odocdt, day_first=True),
                "original_doc_type": get_mapped_value(
                    invoice.odoctyp, self.VALUE_MAPS.isd_type
                ),
            }
        )
        return invoice_details


class GSTR2bIMPGSEZ(GSTR2b):
    def setup(self):
        super().setup()
        self.KEY_MAPS.invoice_key = "boe"

    def get_invoice_details(self, invoice):
        return {
            "doc_type": "Bill of Entry",  # custom field
            "doc_number": invoice.boenum,
            "doc_date": parse_datetime(invoice.boedt, day_first=True),
            "is_amended": get_mapped_value(invoice.isamd, self.VALUE_MAPS.yes_no),
            "port_code": invoice.portcode,
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
