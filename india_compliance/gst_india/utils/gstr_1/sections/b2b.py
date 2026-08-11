"""B2B — invoices to registered buyers, including SEZ and deemed exports (table 4).

Portal groups invoices under the buyer's GSTIN:
    [{ctin: "24AANFA2641L1ZF", inv: [{inum: "S008400", itms: [{num: 1, itm_det: {txval: 10000}}]}]}]

We keep one row per invoice, filed under the subcategory its invoice type decides:
    {"B2B Regular": {"S008400": {customer_gstin: "24AANFA...", document_number: "S008400",
                                 items: [{taxable_value: 10000}], total_taxable_value: 10000}}}
"""

from india_compliance.gst_returns.fields.gstr1 import B2BInvoiceType, SubCategory
from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw

from . import _shared as s

# portal key -> canonical name. One table for the invoice and its items -- the portal reuses names.
KEYS = {
    raw.FLAG: doc.FLAG,
    raw.DOC_NUMBER: doc.DOC_NUMBER,
    raw.DOC_DATE: doc.DOC_DATE,
    raw.DOC_VALUE: doc.DOC_VALUE,
    raw.POS: doc.POS,
    raw.REVERSE_CHARGE: doc.REVERSE_CHARGE,
    raw.INVOICE_TYPE: doc.DOC_TYPE,
    raw.DIFF_PERCENTAGE: doc.DIFF_PERCENTAGE,
    raw.ITEMS: doc.ITEMS,
    raw.ITEM_DETAILS: item.ITEM_DETAILS,
    raw.TAX_RATE: item.TAX_RATE,
    raw.TAXABLE_VALUE: item.TAXABLE_VALUE,
    raw.IGST: item.IGST,
    raw.CGST: item.CGST,
    raw.SGST: item.SGST,
    raw.CESS: item.CESS,
}

# inv_typ -> readable invoice type
INVOICE_TYPES = {
    "R": B2BInvoiceType.R.value,
    "SEWP": B2BInvoiceType.SEWP.value,
    "SEWOP": B2BInvoiceType.SEWOP.value,
    "DE": B2BInvoiceType.DE.value,
}
INVOICE_CODES = s.flip(INVOICE_TYPES)

# inv_typ -> the subcategory the invoice is filed under
SUBCATEGORY_OF = {
    "SEWP": SubCategory.SEZWP.value,
    "SEWOP": SubCategory.SEZWOP.value,
    "DE": SubCategory.DE.value,
}

ITEM_DEFAULTS = dict.fromkeys(s.ITEM_TOTALS, 0)

MONEY = (raw.DOC_VALUE, raw.DIFF_PERCENTAGE)
ITEM_MONEY = (raw.TAXABLE_VALUE, raw.IGST, raw.CGST, raw.SGST, raw.CESS)


def subcategory_of(invoice):
    """SEZ and deemed exports file separately; the rest split by who pays the tax."""
    if invoice.get(raw.INVOICE_TYPE) in SUBCATEGORY_OF:
        return SUBCATEGORY_OF[invoice[raw.INVOICE_TYPE]]

    if invoice.get(raw.REVERSE_CHARGE) == "Y":
        return SubCategory.B2B_REVERSE_CHARGE.value

    return SubCategory.B2B_REGULAR.value


def to_canonical(gov_data):
    names = {}
    output = {}

    def buyer(group):
        gstin = group.get(raw.CUST_GSTIN)
        return {
            doc.CUST_GSTIN: gstin,
            doc.CUST_NAME: s.customer_name(gstin, names),
            doc.ERROR_CD: group.get(raw.ERROR_CD),
            doc.ERROR_MSG: group.get(raw.ERROR_MSG),
        }

    def read(invoice, header):
        row = s.drop_flag(s.with_defaults(s.pick(invoice, KEYS), header))

        s.convert(row, doc.DOC_DATE, s.date_from_gov)  # 24-11-2016 -> 2016-11-24
        s.convert(row, doc.POS, s.pos_from_gov)  # 06 -> 06-Haryana
        s.remap(row, doc.DOC_TYPE, INVOICE_TYPES)  # R -> Regular B2B
        s.convert(row, doc.ITEMS, lambda items: s.wrapped_items_from_gov(items, KEYS, ITEM_DEFAULTS))
        s.add_item_totals(row, row.get(doc.ITEMS), s.ITEM_TOTALS)  # items 10000 + 5000 -> 15000

        return subcategory_of(invoice), row

    for subcategory, row in s.rows_from_groups(gov_data, raw.INVOICES, buyer, read):
        output.setdefault(subcategory, {})[row[doc.DOC_NUMBER]] = row

    return output


def to_gov(rows, company_gstin=""):
    def write(row):
        out = s.round_money(s.pick_back(row, KEYS), MONEY)

        s.convert(out, raw.DOC_DATE, s.date_to_gov)  # 2016-11-24 -> 24-11-2016
        s.convert(out, raw.POS, s.pos_to_gov)  # 06-Haryana -> 06
        s.remap(out, raw.INVOICE_TYPE, INVOICE_CODES)  # Regular B2B -> R
        s.convert(out, raw.ITEMS, lambda items: s.wrapped_items_to_gov(items, KEYS, ITEM_MONEY))

        return s.drop_zero_diff(out)

    return s.groups_from_rows(
        rows,
        group_key=lambda row: row[doc.CUST_GSTIN],
        group_header=lambda row: {raw.CUST_GSTIN: row[doc.CUST_GSTIN]},
        rows_field=raw.INVOICES,
        write_row=write,
    )
