"""B2CS — small sales to unregistered buyers, reported as one total per state and rate (table 7).

Portal:    [{typ: "OE", pos: "05", rt: 5, txval: 110, iamt: 5.5}]
Canonical: {"B2C (Others)": {"05-Uttarakhand - 5.0": [{place_of_supply: "05-Uttarakhand",
                                                       total_taxable_value: 110, document_type: "OE"}]}}
"""

from frappe.utils import flt

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import RawField as raw
from india_compliance.gst_returns.fields.gstr1 import SubCategory

from . import _shared as s

SUBCATEGORY = SubCategory.B2CS.value

KEYS = {
    raw.FLAG: doc.FLAG,
    raw.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    raw.TYPE: doc.DOC_TYPE,
    raw.DIFF_PERCENTAGE: doc.DIFF_PERCENTAGE,
    raw.POS: doc.POS,
    raw.TAX_RATE: doc.TAX_RATE,
    raw.IGST: doc.IGST,
    raw.CGST: doc.CGST,
    raw.SGST: doc.SGST,
    raw.CESS: doc.CESS,
    raw.ERROR_CD: doc.ERROR_CD,
    raw.ERROR_MSG: doc.ERROR_MSG,
}

MONEY = (
    raw.TAXABLE_VALUE,
    raw.DIFF_PERCENTAGE,
    raw.IGST,
    raw.CGST,
    raw.SGST,
    raw.CESS,
)


def group_key(row):
    """Identity used to match books against the portal. Discarded before the data is stored."""
    return " - ".join((row.get(doc.POS) or "", str(flt(row.get(doc.TAX_RATE, "")))))


def to_canonical(gov_data):
    output = {}

    for entry in gov_data:
        row = s.drop_flag(s.pick(entry, KEYS))
        s.convert(row, doc.POS, s.pos_from_gov)  # 05 -> 05-Uttarakhand

        output.setdefault(group_key(row), []).append(row)  # keyed "05-Uttarakhand - 5.0"

    return {SUBCATEGORY: output}


def to_gov(rows, company_gstin=""):
    def write(row):
        out = s.round_money(s.pick_back(row, KEYS), MONEY)

        s.convert(out, raw.POS, s.pos_to_gov)  # 05-Uttarakhand -> 05
        s.drop_zero_diff(out)

        out[raw.SUPPLY_TYPE] = s.supply_type(out[raw.POS], company_gstin)  # seller 24, buyer 05 -> INTER

        return out

    return [write(row) for row in rows]
