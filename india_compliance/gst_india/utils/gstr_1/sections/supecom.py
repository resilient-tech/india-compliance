"""Supplies through e-commerce operators, one total per operator (table 14).

Portal:    {clttx: [{etin: "20ALYPD6528PQC5", suppval: 10000, igst: 1000}]}
Canonical: {"Liable to collect tax u/s 52(TCS)": {"20ALYPD6528PQC5": {ecommerce_gstin: "20ALYPD...",
                                                                     total_taxable_value: 10000,
                                                                     total_igst_amount: 1000}}}
"""

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import RawField as raw
from india_compliance.gst_returns.fields.gstr1 import SubCategory

from . import _shared as s

KEYS = {
    raw.ECOMMERCE_GSTIN: doc.ECOMMERCE_GSTIN,
    raw.NET_TAXABLE_VALUE: doc.TAXABLE_VALUE,
    raw.ECOM_IGST: doc.IGST,
    raw.ECOM_CGST: doc.CGST,
    raw.ECOM_SGST: doc.SGST,
    raw.ECOM_CESS: doc.CESS,
    raw.FLAG: doc.FLAG,
}

# portal json key -> the subcategory its rows are filed under
SECTIONS = {
    raw.SUPECOM_52: SubCategory.SUPECOM_52.value,
    raw.SUPECOM_9_5: SubCategory.SUPECOM_9_5.value,
}
SECTION_KEYS = s.flip(SECTIONS)

# only the supply value is rounded; the portal sends taxes already rounded here
MONEY = (raw.NET_TAXABLE_VALUE,)


def to_canonical(gov_data):
    output = {}

    for section, entries in gov_data.items():
        subcategory = SECTIONS.get(section, section)  # clttx -> Liable to collect tax u/s 52(TCS)

        output[subcategory] = {
            entry.get(raw.ECOMMERCE_GSTIN, ""): s.drop_flag(
                s.with_defaults(s.pick(entry, KEYS), {doc.DOC_TYPE: subcategory})
            )
            for entry in entries
        }

    return output


def to_gov(rows, company_gstin=""):
    output = {}

    for row in rows:
        subcategory = row[doc.DOC_TYPE]
        section = SECTION_KEYS.get(subcategory, subcategory)

        output.setdefault(section, []).append(s.round_money(s.pick_back(row, KEYS), MONEY))

    return output
