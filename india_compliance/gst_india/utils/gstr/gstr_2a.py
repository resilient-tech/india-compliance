from isodate import parse_datetime

import frappe

from india_compliance.gst_india.api_classes.returns import GSTR2aAPI
from india_compliance.gst_india.doctype.gstr_download_log.gstr_download_log import (
    create_download_log,
)
from india_compliance.gst_india.utils.gstr import (
    GSTR,
    GSTRCategory,
    ReturnType,
    get_mapped_value,
    map_date_format,
    save_gstr,
)

ACTIONS = {
    "B2B": GSTRCategory.B2B,
    "B2BA": GSTRCategory.B2BA,
    "CDN": GSTRCategory.CDNR,
    "CDNA": GSTRCategory.CDNRA,
    "ISD": GSTRCategory.ISD,
    "IMPG": GSTRCategory.IMPG,
    "IMPGSEZ": GSTRCategory.IMPGSEZ,
}


def download_gstr_2a(gstin, return_periods, otp=None):
    api = GSTR2aAPI(gstin)
    for return_period in return_periods:
        json_data = {}
        for action, category in ACTIONS.items():
            # call api only if data is available
            if frappe.db.get_value(
                "GSTR Download Log",
                {
                    "gst_return": ReturnType.GSTR2A,
                    "return_period": return_period,
                    "classification": category,
                },
                "no_data_found",
            ):
                continue

            response = api.get_data(action, return_period, otp)
            if response.error_type == "otp_requested":
                return response

            if response.error_type == "no_docs_found":
                create_download_log(
                    gstin,
                    ReturnType.GSTR2A,
                    return_period,
                    data_not_found=True,
                )
                continue

            # TODO: confirm about throwing
            if not response.get(action.lower()):
                frappe.throw(
                    "Data received seems to be invalid from the GST Portal. Please try"
                    " again or raise support ticket.",
                    title="Invalid Response Received.",
                )

            json_data.update(response.json_data)

        save_gstr(return_period, json_data)


class GSTR2a(GSTR):
    def get_supplier_details(self, supplier):
        return {
            "supplier_gstin": supplier.ctin,
            "gstr_1_filled": get_mapped_value(supplier.cfs, self.VALUE_MAPS.yes_no),
            "gstr_3b_filled": get_mapped_value(supplier.cfs3b, self.VALUE_MAPS.yes_no),
            "gstr_1_filing_date": parse_datetime(supplier.fldtr1),
            "registration_cancel_date": parse_datetime(supplier.dtcancel),
            "sup_return_period": map_date_format(supplier.flprdr1, "%b-%y", "%m%Y"),
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


class GSTR2aB2B(GSTR2a):
    def setup(self):
        super().setup()
        self.KEY_MAPS.items_key = "itms"
        self.KEY_MAPS.invoice_key = "inv"

    def get_invoice_details(self, invoice):
        return {
            "doc_number": invoice.inum,
            "supply_type": get_mapped_value(
                invoice.inv_typ, self.VALUE_MAPS.gst_category
            ),
            "doc_date": parse_datetime(invoice.idt, day_first=True),
            "document_value": invoice.val,
            "place_of_supply": get_mapped_value(invoice.pos, self.VALUE_MAPS.states),
            "other_return_period": map_date_format(invoice.aspd, "%b-%y", "%m%Y"),
            "amendment_type": get_mapped_value(
                invoice.atyp, self.VALUE_MAPS.amend_type
            ),
            "reverse_charge": get_mapped_value(invoice.rchrg, self.VALUE_MAPS.yes_no),
            "diffprcnt": get_mapped_value(
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
                "original_doc_number": invoice.oinum,
                "original_doc_date": parse_datetime(invoice.oidt, day_first=True),
            }
        )
        return invoice_details


class GSTR2aCDNR(GSTR2aB2B):
    def setup(self):
        super().setup()
        self.KEY_MAPS.invoice_key = "nt"

    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "doc_number": invoice.nt_num,
                "doc_type": get_mapped_value(invoice.ntty, self.VALUE_MAPS.note_type),
                "doc_date": parse_datetime(invoice.suptyp, day_first=True),
            }
        )
        return invoice_details


class GSTR2aCDNRA(GSTR2aCDNR):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_doc_number": invoice.ont_num,
                "original_doc_date": parse_datetime(invoice.ont_dt, day_first=True),
                "original_doc_type": get_mapped_value(
                    invoice.ntty, self.VALUE_MAPS.note_type
                ),
            }
        )
        return invoice_details


class GSTR2aISD(GSTR2a):
    def setup(self):
        super().setup()
        self.KEY_MAPS.invoice_key = "doclist"

    def get_invoice_details(self, invoice):
        return {
            "doc_type": get_mapped_value(invoice.isd_docty, self.VALUE_MAPS.isd_type),
            "doc_number": invoice.docnum,
            "doc_date": parse_datetime(invoice.docdt, day_first=True),
            "itc_availability": get_mapped_value(
                invoice.itc_elg, {"Y": "Yes", "N": "No"}
            ),
            "other_return_period": map_date_format(invoice.aspd, "%b-%y", "%m%Y"),
            "amendment_type": get_mapped_value(
                invoice.atyp, self.VALUE_MAPS.amend_type
            ),
        }

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
            "doc_number": invoice.benum,
            "doc_date": parse_datetime(invoice.bedt, day_first=True),
            "is_amended": get_mapped_value(invoice.amd, self.VALUE_MAPS.yes_no),
            "port_code": invoice.portcd,
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
