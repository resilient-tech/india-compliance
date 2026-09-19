# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""GSTR-2A/2B exporters. 2B rows from the sync's readers; 2A straight from the raw data."""

from functools import partial
from typing import ClassVar

import frappe
from frappe.query_builder.functions import Max
from frappe.utils import flt

from india_compliance.gst_india.doctype.gst_return_export.return_adapters import (
    GSTR2AAdapter,
    GSTR2BAdapter,
)
from india_compliance.gst_india.doctype.gst_return_export.template_exporter import (
    GovReturnExporter,
    amend_text,
    as_section_dict,
    date_text,
    financial_year,
    normalize_label,
    percent_text,
    period_text,
    raw_date_text,
    raw_yes_no_text,
    reformat_date,
    split_label,
    state_from_code,
    state_text,
    write_cell,
    yes_no_text,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    DOCTYPE as RETURN_LOG,
)
from india_compliance.gst_india.utils.gstr_utils import ReturnType
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.fields.gstr2 import RawField2a as raw2a
from india_compliance.gst_returns.fields.gstr2 import RawField2b as raw2b

# A workbook tab the exporter leaves empty on purpose; the comment beside it says why.
NOT_FILLED = None

SOURCE_PERIOD = "_period"

# each sheet generation worded the supplier filing header differently
SUPPLIER_HEADERS = (
    "gstr-1/iff",
    "gstr-1/1a/iff",
    "gstr-1/iff/1a",
    "gstr-1/iff/gstr-1a",
    "gstr-1/iff/gstr-5",
    "gstr-1/1a/iff/gstr-5",
    "gstr-1/iff/1a/gstr-5",
    "isd gstr-6",
)


class GSTR2BExporter(GovReturnExporter):
    """2B: document sheets from the sync's rows, ITC summary sheets from itcsumm."""

    adapter = GSTR2BAdapter
    template = "gstr2b_excel_template_v1.1.xlsx"
    NUMBER_FORMAT = "0.00"

    # column label -> our field name, with a formatter where the cell shows it differently
    FIELDS: ClassVar[dict] = {
        "gstin of supplier": doc.SUPPLIER_GSTIN,
        "gstin of isd": doc.SUPPLIER_GSTIN,
        "gstin of eco": doc.SUPPLIER_GSTIN,
        "trade/legal name": doc.SUPPLIER_NAME,
        **{f"{head} period": (doc.SUP_RETURN_PERIOD, period_text) for head in SUPPLIER_HEADERS},
        **{f"{head} filing date": (doc.GSTR_1_FILING_DATE, date_text) for head in SUPPLIER_HEADERS},
        "invoice details | invoice number": doc.BILL_NO,
        "invoice details | invoice type": doc.SUPPLY_TYPE,
        "invoice details | invoice date": (doc.BILL_DATE, date_text),
        "invoice details | invoice value": doc.DOC_VALUE,
        "document details | document number": doc.BILL_NO,  # ECO
        "document details | document type": doc.SUPPLY_TYPE,
        "document details | document date": (doc.BILL_DATE, date_text),
        "document details | document value": doc.DOC_VALUE,
        "credit note/debit note details | note number": doc.BILL_NO,
        "credit note/debit note details | note type": doc.DOC_TYPE,
        "credit note/debit note details | note supply type": doc.SUPPLY_TYPE,
        "credit note/debit note details | note date": (doc.BILL_DATE, date_text),
        "credit note/debit note details | note value": doc.DOC_VALUE,
        "debit note details | note number": doc.BILL_NO,  # B2B-DNR (ITC reversal)
        "debit note details | note type": doc.DOC_TYPE,
        "debit note details | note supply type": doc.SUPPLY_TYPE,
        "debit note details | note date": (doc.BILL_DATE, date_text),
        "debit note details | note value": doc.DOC_VALUE,
        "place of supply": (doc.POS, state_text),
        "supply attract reverse charge": (doc.REVERSE_CHARGE, yes_no_text),
        "taxable value": doc.TAXABLE_VALUE,
        "tax amount | integrated tax": doc.IGST,
        "tax amount | central tax": doc.CGST,
        "tax amount | state/ut tax": doc.SGST,
        "tax amount | cess": doc.CESS,
        "itc availability": doc.ITC_AVAILABILITY,
        "eligibility of itc": doc.ITC_AVAILABILITY,
        "reason": doc.ITC_REASON,
        "applicable % of tax rate": (doc.DIFF_PERCENTAGE, percent_text),
        "source": doc.IRN_SOURCE,
        "irn": doc.IRN_NUMBER,
        "irn date": (doc.IRN_GEN_DATE, date_text),
        "isd document type": doc.DOC_TYPE,
        "isd document number": doc.BILL_NO,
        "isd document date": (doc.BILL_DATE, date_text),
        "input tax distribution by isd | integrated tax": doc.IGST,
        "input tax distribution by isd | central tax": doc.CGST,
        "input tax distribution by isd | state/ut tax": doc.SGST,
        "input tax distribution by isd | cess": doc.CESS,
        "port code": doc.PORT_CODE,
        "bill of entry details | number": doc.BILL_NO,
        "bill of entry details | date": (doc.BILL_DATE, date_text),
        "bill of entry details | taxable value": doc.TAXABLE_VALUE,
        "amount of tax | integrated tax": doc.IGST,
        "amount of tax | cess": doc.CESS,
        # columns the portal copies back that our rows lack; the raw record's keys sit under the row
        "original invoice number": raw2b.ORIGINAL_INVOICE_NUMBER,
        "original invoice date": (raw2b.ORIGINAL_INVOICE_DATE, raw_date_text),
        "icegate reference date": (raw2b.ICEGATE_REF_DATE, raw_date_text),
        "type of amendment": (raw2b.AMEND_TYPE, amend_text),
        "whether itc to be reduced (taxpayer's input)": (raw2b.ITC_REDUCTION_REQUIRED, raw_yes_no_text),
        "amount declared by taxpayer for itc reduction | integrated tax": raw2b.DECLARED_IGST,
        "amount declared by taxpayer for itc reduction | central tax": raw2b.DECLARED_CGST,
        "amount declared by taxpayer for itc reduction | state/ut tax": raw2b.DECLARED_SGST,
        "amount declared by taxpayer for itc reduction | cess": raw2b.DECLARED_CESS,
        "remarks": raw2b.REMARKS,
    }

    # 'original details' block: every wording lands on the same three fields
    ORIGINAL_FIELDS: ClassVar[dict] = {
        "invoice number": doc.ORIGINAL_BILL_NO,
        "invoice date": (doc.ORIGINAL_BILL_DATE, date_text),
        "note type": doc.ORIGINAL_DOC_TYPE,
        "note number": doc.ORIGINAL_BILL_NO,
        "note date": (doc.ORIGINAL_BILL_DATE, date_text),
        "isd document type": doc.ORIGINAL_DOC_TYPE,
        "document number": doc.ORIGINAL_BILL_NO,
        "document date": (doc.ORIGINAL_BILL_DATE, date_text),
    }

    # The 2B workbook, in tab order. Read this next to the tabs.
    SHEETS: ClassVar[dict] = {
        # sheet: (raw data block, category, amended only)
        "B2B": (raw2b.DOC_DATA, "B2B", None),
        "B2BA": (raw2b.DOC_DATA, "B2BA", None),
        "B2B-CDNR": (raw2b.DOC_DATA, "CDNR", None),
        "B2B-CDNRA": (raw2b.DOC_DATA, "CDNRA", None),
        "ECO": (raw2b.DOC_DATA, "ECOM", None),
        "ECOA": (raw2b.DOC_DATA, "ECOMA", None),
        "ISD": (raw2b.DOC_DATA, "ISD", None),
        "ISDA": (raw2b.DOC_DATA, "ISDA", None),
        "IMPG": (raw2b.DOC_DATA, "IMPG", False),
        "IMPGA": (raw2b.DOC_DATA, "IMPG", True),
        "IMPGSEZ": (raw2b.DOC_DATA, "IMPGSEZ", False),
        "IMPGSEZA": (raw2b.DOC_DATA, "IMPGSEZ", True),
        "B2B (ITC Reversal)": (raw2b.ITC_REVERSAL, "B2B", None),
        "B2BA (ITC Reversal)": (raw2b.ITC_REVERSAL, "B2BA", None),
        "B2B-DNR": (raw2b.ITC_REVERSAL, "CDNR", None),
        "B2B-DNRA": (raw2b.ITC_REVERSAL, "CDNRA", None),
        "B2B(Rejected)": (raw2b.DOC_REJECTED, "B2B", None),
        "B2BA(Rejected)": (raw2b.DOC_REJECTED, "B2BA", None),
        "B2B-CDNR(Rejected)": (raw2b.DOC_REJECTED, "CDNR", None),
        "B2B-CDNRA(Rejected)": (raw2b.DOC_REJECTED, "CDNRA", None),
        "ECO(Rejected)": (raw2b.DOC_REJECTED, "ECOM", None),
        "ECOA(Rejected)": (raw2b.DOC_REJECTED, "ECOMA", None),
        "ISD(Rejected)": (raw2b.DOC_REJECTED, "ISD", None),
        "ISDA(Rejected)": (raw2b.DOC_REJECTED, "ISDA", None),
    }

    # ITC summary sheet -> its block inside itcsumm; this "itcrev" is not the top-level one
    ITC_SHEET_BLOCK: ClassVar[dict] = {
        "ITC Available": "itcavl",
        "ITC not available": "itcunavl",
        "ITC Reversal": "itcrev",
        "ITC Rejected": "itcRejected",
    }
    ITC_TAX_COLUMNS: ClassVar[dict] = {"igst": 4, "cgst": 5, "sgst": 6, "cess": 7}

    # section-total row label -> itcsumm bucket
    ITC_BUCKETS: ClassVar[dict] = {
        "all other itc - supplies from registered persons other than reverse charge": "nonrevsup",
        "all other itc - supplies from registered persons other than reverse charge (ims)": "nonrevsup",
        "itc reversal on account of rule 37a": "nonrevsup",
        "inward supplies from isd": "isdsup",
        "inward supplies liable for reverse charge": "revsup",
        "import of goods": "imports",
        "others": "othersup",
    }

    # detail row label -> key inside the current bucket
    ITC_DETAILS: ClassVar[dict] = {
        "b2b - invoices": "b2b",
        "b2b - invoices (ims)": "b2b",
        "b2b - invoices (amendment)": "b2ba",
        "b2b - invoices (amendment) (ims)": "b2ba",
        "b2b - debit notes": "cdnr",
        "b2b - debit notes (ims)": "cdnr",
        "b2b - credit notes (ims)": "cdnr",
        "b2b - credit notes - ims": "cdnr",
        "b2b - debit notes (amendment)": "cdnra",
        "b2b - debit notes (amendment) (ims)": "cdnra",
        "b2b - credit notes (amendment) (ims)": "cdnra",
        "b2b - credit notes (amendment) - ims": "cdnra",
        "b2b - credit notes (reverse charge)": "cdnrrev",
        "b2b - credit notes (reverse charge)(amendment)": "cdnrarev",
        "isd - invoices": "isd",
        "isd - credit notes": "isd",
        "isd - invoices (amendment)": "isda",
        "isd - credit notes (amendment)": "isda",
        "eco - documents": "ecom",
        "eco - documents (ims)": "ecom",
        "eco - documents (amendment)": "ecoma",
        "eco - documents (amendment) (ims)": "ecoma",
        "impg - import of goods from overseas": "impg",
        "impg (amendment)": "impga",
        "impgsez - import of goods from sez": "impgsez",
        "impgsez (amendment)": "impgasez",
    }

    def fill(self):
        # raw data blocks
        docdata = self.adapter.raw_sections(self.raw)
        blocks = {
            raw2b.DOC_DATA: docdata,
            raw2b.ITC_REVERSAL: as_section_dict(docdata.get(raw2b.ITC_REVERSAL)),
            raw2b.DOC_REJECTED: as_section_dict(self.raw.get(raw2b.DOC_REJECTED)),
        }

        # document sheets
        filled = False
        for sheet, (block, category, amended) in self.SHEETS.items():
            groups = blocks[block].get(category.lower()) or []
            if not groups:
                continue
            documents = self._section_documents(category, groups)
            if amended is not None:
                documents = [d for d in documents if bool(d[0].get(doc.IS_AMENDED)) == amended]
            # our row over the raw record: the map reads either by key
            sources = [{**record, **row} for row, record in documents]
            if sources and self.render(sheet, partial(self.rows_for, sheet, sources=sources)):
                filled = True

        # itc summary
        if itcsumm := self.raw.get(raw2b.ITC_SUMMARY):
            for sheet in self.ITC_SHEET_BLOCK:
                if self.excel.has_sheet(sheet):
                    self._fill_itc_sheet(sheet, itcsumm)
                    filled = True
        return filled

    def _section_documents(self, category, groups):
        """(our row, raw record) pairs. Pairing trusts the raw order."""
        reader = self.adapter(self.gstin).get_handler(self.periods[-1], category)
        _get_details, docs_key, _has_items = reader.SECTIONS[category]
        if docs_key:
            records = [record for group in groups for record in group.get(docs_key) or []]
        else:
            records = list(groups)
        return list(zip(reader.get_all_transactions(groups), records, strict=True))

    def _fill_itc_sheet(self, sheet, itcsumm):
        """Walk row labels: total row set the bucket, detail row read from it. Absent = 0."""
        block = itcsumm.get(self.ITC_SHEET_BLOCK[sheet]) or {}
        ws = self.excel.wb[sheet]
        bucket = None
        for row in range(1, ws.max_row + 1):
            heading = normalize_label(ws.cell(row, 2).value)
            if new_bucket := self.ITC_BUCKETS.get(heading):
                bucket = new_bucket
                self._write_itc_row(ws, row, block.get(bucket))
            elif bucket and (key := self.ITC_DETAILS.get(heading)):
                self._write_itc_row(ws, row, (block.get(bucket) or {}).get(key))

    def _write_itc_row(self, ws, row, values):
        for field, col in self.ITC_TAX_COLUMNS.items():
            cell = ws.cell(row=row, column=col, value=flt((values or {}).get(field)))
            cell.number_format = self.NUMBER_FORMAT

    def fill_readme(self):
        if not self.excel.has_sheet("Read me"):
            return
        period = self.periods[-1]
        info = self.get_gstin_names(self.gstin)
        gendt = self.raw.get(raw2b.GENERATION_DATE)

        ws = self.excel.wb["Read me"]
        self.set_merged(ws, 4, 3, financial_year(period))
        self.set_merged(ws, 5, 3, reformat_date(period, "%m%Y", "%B"))  # full month name
        self.set_merged(ws, 6, 3, self.gstin)
        self.set_merged(ws, 7, 3, info.get("legal_name") or "")
        self.set_merged(ws, 8, 3, info.get("trade_name") or "")
        self.set_merged(ws, 9, 3, raw_date_text(gendt) if gendt else "")


# 2A columns no key gives directly. computed(source, exporter); `source` is the supplier,
# document and item folded flat, `exporter` carries the names looked up for the workbook.
def supplier_name(source, exporter):
    """Name in the raw data, else what the sync or the GSTIN record knows."""
    return source.get(raw2a.SUPPLIER_NAME) or exporter.names.get(source.get(raw2a.SUPPLIER_GSTIN))


def ecom_name(source, exporter):
    return exporter.names.get(source.get(raw2a.ECOM_GSTIN))


def supplies_returned(source, exporter):
    return round(flt(source.get(raw2a.SUPPLY_VALUE)) - flt(source.get(raw2a.TCS_TAXABLE_VALUE)), 2)


def isd_column(key, credit_note):
    """ISD invoice vs credit-note columns: only the pair matching the document type fill."""

    def computed(source, exporter):
        if (source.get(raw2a.ISD_DOC_TYPE) == "ISDCN") == credit_note:
            return source.get(key)

    computed.__name__ = f"isd_{'credit_note' if credit_note else 'invoice'}({key})"
    return computed


class GSTR2AExporter(GovReturnExporter):
    """2A: raw codes as they are, item rows plus a total row, names looked up."""

    adapter = GSTR2AAdapter
    template = "gstr2a_excel_template_v1.0.xlsx"

    # absent numeric = 0, like the portal
    NUMERIC_ZERO_KEYS: ClassVar[set] = {
        raw2a.TAX_RATE,
        raw2a.TAXABLE_VALUE,
        raw2a.IGST,
        raw2a.CGST,
        raw2a.SGST,
        raw2a.CESS,
        raw2a.ISD_CESS,
    }

    FIELDS: ClassVar[dict] = {
        "gstin of supplier": raw2a.SUPPLIER_GSTIN,
        "gstin of isd": raw2a.SUPPLIER_GSTIN,
        "gstin of eco": raw2a.SUPPLIER_GSTIN,
        **{
            f"trade/legal name{who}": supplier_name
            for who in ("", " of the supplier", " of the eco", " of the isd")
        },
        # filing headers per sheet wording (ECO drop the "/5")
        **{
            f"{head} filing {part}": key
            for head in ("gstr-1/iff/gstr-1a/5", "gstr-1/iff/gstr-1a")
            for part, key in (
                ("status", raw2a.GSTR_1_FILING_STATUS),
                ("date", raw2a.GSTR_1_FILING_DATE),
                ("period", raw2a.SUP_RETURN_PERIOD),
            )
        },
        "isd gstr-6 filing status": raw2a.GSTR_1_FILING_STATUS,
        "gstr-3b filing status": raw2a.GSTR_3B_FILED,
        "effective date of cancellation": raw2a.CANCEL_DATE,
        "document details | document number": raw2a.DOC_NUMBER,
        "document details | document type": raw2a.INVOICE_TYPE,
        "document details | document date": raw2a.DOC_DATE,
        "document details | document value": raw2a.DOC_VALUE,
        "invoice details | invoice number": raw2a.DOC_NUMBER,
        "invoice details | invoice type": raw2a.INVOICE_TYPE,
        "invoice details | invoice date": raw2a.DOC_DATE,
        "invoice details | invoice value": raw2a.DOC_VALUE,
        "credit note/debit note details | note type": raw2a.NOTE_TYPE,
        "credit note/debit note details | note number": raw2a.NOTE_NUMBER,
        "credit note/debit note details | note supply type": raw2a.INVOICE_TYPE,
        "credit note/debit note details | note date": raw2a.NOTE_DATE,
        "credit note/debit note details | note value": raw2a.DOC_VALUE,
        "place of supply": (raw2a.POS, state_from_code),
        "supply attract reverse charge": raw2a.REVERSE_CHARGE,
        "tax period in which amended": raw2a.OTHER_PERIOD,  # base sheets
        "original tax period in which reported": raw2a.OTHER_PERIOD,
        "tax period in which reported earlier": raw2a.OTHER_PERIOD,
        "amendment made, if any": raw2a.AMEND_TYPE,
        "source": raw2a.IRN_SOURCE,
        "irn": raw2a.IRN,
        "irn date": raw2a.IRN_DATE,
        "eligibility of itc": raw2a.ITC_ELIGIBILITY,
        "isd document type": raw2a.ISD_DOC_TYPE,
        "isd invoice number": isd_column(raw2a.ISD_DOC_NUMBER, credit_note=False),
        "isd invoice date": isd_column(raw2a.ISD_DOC_DATE, credit_note=False),
        "isd credit note number": isd_column(raw2a.ISD_DOC_NUMBER, credit_note=True),
        "isd credit note date": isd_column(raw2a.ISD_DOC_DATE, credit_note=True),
        "original invoice number": raw2a.ORIGINAL_INVOICE_NUMBER,
        "original invoice date": raw2a.ORIGINAL_INVOICE_DATE,
        "input tax distribution by isd | integrated tax": raw2a.IGST,
        "input tax distribution by isd | central tax": raw2a.CGST,
        "input tax distribution by isd | state/ut tax": raw2a.SGST,
        "input tax distribution by isd | cess": raw2a.ISD_CESS,
        "reference date (icegate)": raw2a.ICEGATE_REF_DATE,
        "port code": raw2a.PORT_CODE,
        "bill of entry details | number": raw2a.BOE_NUMBER,
        "bill of entry details | date": raw2a.BOE_DATE,
        "bill of entry details | taxable value": raw2a.TAXABLE_VALUE,
        "amount of tax | integrated tax": raw2a.IGST,
        "amount of tax | cess": raw2a.CESS,
        "amended (yes)": raw2a.IS_AMENDED,
        "amended(yes)": raw2a.IS_AMENDED,
        "rate": raw2a.TAX_RATE,
        "taxable value": raw2a.TAXABLE_VALUE,
        "tax amount | integrated tax": raw2a.IGST,
        "tax amount | central tax": raw2a.CGST,
        "tax amount | state/ut tax": raw2a.SGST,
        "tax amount | state tax": raw2a.SGST,
        "tax amount | cess": raw2a.CESS,
        "tax amount | cess amount": raw2a.CESS,
    }

    ORIGINAL_FIELDS: ClassVar[dict] = {
        "invoice number": raw2a.ORIGINAL_DOC_NUMBER,
        "invoice date": raw2a.ORIGINAL_DOC_DATE,
        "note type": raw2a.NOTE_TYPE,
        "note number": raw2a.ORIGINAL_NOTE_NUMBER,
        "note date": raw2a.ORIGINAL_NOTE_DATE,
    }

    # one sheet's special cases, keyed as its headers read
    SHEET_FIELDS: ClassVar[dict] = {
        "ECOA": {
            "original details | document number": raw2a.ORIGINAL_DOC_NUMBER,
            "original details | document date": raw2a.ORIGINAL_DOC_DATE,
        },
        "TDS": {
            "gstin of deductor": raw2a.DEDUCTOR_GSTIN,
            "deductor's name": raw2a.DEDUCTOR_NAME,
            "tax period of gstr 7": raw2a.DEDUCTION_MONTH,  # MMYYYY, portal shows raw
            "taxable value": raw2a.DEDUCTED_VALUE,
            "amount of tax deducted by deductors | integrated tax": raw2a.IGST,
            "amount of tax deducted by deductors | central tax": raw2a.CGST,
            "amount of tax deducted by deductors | state/ut tax": raw2a.SGST,
        },
        "TCS": {
            "gstin of e-com. operator": raw2a.ECOM_GSTIN,
            "e-com. operator's name": ecom_name,
            "tax period of gstr 8": SOURCE_PERIOD,  # the record carries no month of its own
            "gross value of supplies": raw2a.SUPPLY_VALUE,
            "value of supplies returned": supplies_returned,
            "net amount liable for tcs": raw2a.TCS_TAXABLE_VALUE,
            "total tcs amount | integrated tax": raw2a.IGST,
            "total tcs amount | central tax": raw2a.CGST,
            "total tcs amount | state/ut tax": raw2a.SGST,
        },
    }

    SUPPLIER_ALIASES: ClassVar[dict] = {
        "IMPGSEZ": {raw2a.SUPPLIER_GSTIN: raw2a.SEZ_GSTIN, raw2a.SUPPLIER_NAME: raw2a.SEZ_TRADE_NAME},
    }

    # The 2A workbook, in tab order. Read this next to the tabs.
    SHEETS: ClassVar[dict] = {
        # sheet: (category, record list, item list); no lists means the record is the row
        "B2B": ("B2B", raw2a.INVOICES, raw2a.ITEMS),
        "B2BA": ("B2BA", raw2a.INVOICES, raw2a.ITEMS),
        "CDNR": ("CDNR", raw2a.NOTES, raw2a.ITEMS),
        "CDNRA": ("CDNRA", raw2a.NOTES, raw2a.ITEMS),
        "ECO": ("ECOM", raw2a.INVOICES, raw2a.ITEMS),
        "ECOA": ("ECOMA", raw2a.INVOICES, raw2a.ITEMS),
        "ISD": ("ISD", raw2a.ISD_DOCS, ""),
        # portal folds ISD amendments into the ISD sheet
        "ISDA": NOT_FILLED,
        "TDS": ("TDS", "", ""),
        "TDSA": NOT_FILLED,  # the portal's 2A raw data carries no amended-TDS category
        "TCS": ("TCS", "", ""),
        "IMPG": ("IMPG", "", ""),
        "IMPG SEZ": ("IMPGSEZ", "", ""),
    }

    def fill(self):
        # supplier names, one query
        docdata = self.adapter.raw_sections(self.raw)
        gstins = self._raw_gstins(docdata)
        self.names = {**self._supplier_names(gstins), **self._gstin_record_names(gstins)}

        # a sheet per tab
        filled = False
        for sheet, spec in self.SHEETS.items():
            if spec is NOT_FILLED:
                continue
            category, list_key, item_key = spec
            groups = self._section_groups(category)
            if groups and self.render(sheet, partial(self._build_rows, sheet, groups, list_key, item_key)):
                filled = True
        return filled

    def _raw_gstins(self, docdata):
        """Every GSTIN a sheet may need a name for."""
        return {
            gstin
            for spec in self.SHEETS.values()
            if spec is not NOT_FILLED
            for group in (docdata.get(spec[0].lower()) or [])
            if isinstance(group, dict)
            for gstin in (
                group.get(raw2a.SUPPLIER_GSTIN),
                group.get(raw2a.SEZ_GSTIN),
                group.get(raw2a.ECOM_GSTIN),
            )
            if gstin
        }

    def _supplier_names(self, gstins):
        """Names off inward supplies, newest row wins. Only the 2B sync saves them, so no period filter."""
        if not gstins:
            return {}

        GIS = frappe.qb.DocType("GST Inward Supply")
        rows = (
            frappe.qb.from_(GIS)
            .select(GIS.supplier_gstin, GIS.supplier_name)
            .where(
                (GIS.company_gstin == self.gstin)
                & GIS.supplier_gstin.isin(list(gstins))
                & GIS.supplier_name.isnotnull()
                & (GIS.supplier_name != "")
            )
            .groupby(GIS.supplier_gstin, GIS.supplier_name)
            .orderby(Max(GIS.modified))
            .run(as_dict=True)
        )
        return {row.supplier_gstin: row.supplier_name for row in rows}

    def _gstin_record_names(self, gstins):
        """Cached names for every supplier in the raw data, one query."""
        if not gstins:
            return {}

        # the portal's 2A shows the legal name (its 2B the trade name)
        return {
            row.name: row.legal_name or row.trade_name
            for row in frappe.get_all(
                "GSTIN",
                filters={"name": ("in", list(gstins))},
                fields=["name", "legal_name", "trade_name"],
            )
            if row.legal_name or row.trade_name
        }

    def _section_groups(self, category):
        """Each month's groups for the section, tagged with that month, supplier keys settled."""
        alias = self.SUPPLIER_ALIASES.get(category) or {}
        return [
            {SOURCE_PERIOD: period, **group, **{key: group.get(src) for key, src in alias.items()}}
            for period, raw in self.raw_by_period.items()
            for group in (self.adapter.raw_sections(raw).get(category.lower()) or [])
        ]

    def _build_rows(self, sheet, groups, list_key, item_key, labels):
        """Item rows, then a total row and a blank, per document; flat sections one row each."""
        # sources
        sources, totals = [], []
        for supplier in groups:
            for record in (supplier.get(list_key) or []) if list_key else [supplier]:
                if not item_key:
                    sources.append(self._source(supplier, record))
                    continue

                items = [entry.get(raw2a.ITEM_DETAILS, entry) for entry in record.get(item_key) or []]
                item_totals = {
                    key: sum(flt(item.get(key)) for item in items) for key in self.NUMERIC_ZERO_KEYS
                }
                sources.extend(self._source(supplier, record, item) for item in items)
                sources.append(self._source(supplier, record, item_totals))
                totals.append(len(sources) - 1)
                sources.append(None)

        # rows, total rows marked
        rows = self.rows_for(sheet, labels, sources)
        for index in totals:
            rows[index] = self._total_row(rows[index], labels)
        return rows

    def _source(self, *parts):
        """Supplier, document, item folded into one dict, later winning. Absent amounts are 0."""
        source = {key: value for part in parts for key, value in part.items()}
        for key in self.NUMERIC_ZERO_KEYS:
            if source.get(key) is None:
                source[key] = 0
        return source

    NUMBER_LABELS = ("invoice number", "note number", "document number")

    @classmethod
    def _total_row(cls, row, labels):
        """Per-invoice total: rate blank, "-Total" on the number. Match labels without their block."""
        for label in labels.values():
            base, is_original = split_label(label)
            if base == "rate":
                row[label] = "-"
            elif not is_original and base.endswith(cls.NUMBER_LABELS) and row.get(label) is not None:
                row[label] = f"{row[label]}-Total"
        return row

    def fill_readme(self):
        """2A Read me header: plain cells, period as MMYYYY."""
        if not self.excel.has_sheet("Read me"):
            return
        period = self.periods[-1]
        info = self.get_gstin_names(self.gstin)
        # 2A raw has no generation date; use the sync day
        synced_on = frappe.db.get_value(RETURN_LOG, f"{self.return_type}-{period}-{self.gstin}", "modified")

        ws = self.excel.wb["Read me"]
        write_cell(ws, 2, 3, self.gstin)  # C2  Taxpayer's GSTIN
        write_cell(ws, 3, 3, info.get("legal_name") or "")  # C3  Legal name
        write_cell(ws, 4, 3, info.get("trade_name") or "")  # C4  Trade name
        write_cell(ws, 2, 5, period)  # E2  Tax period (MMYYYY)
        write_cell(ws, 3, 5, financial_year(period))  # E3  Financial year
        write_cell(ws, 4, 5, synced_on.strftime("%d-%m-%Y") if synced_on else "")  # E4  Date of generation


EXPORTERS = {
    ReturnType.GSTR2A.value: GSTR2AExporter,
    ReturnType.GSTR2B.value: GSTR2BExporter,
}
