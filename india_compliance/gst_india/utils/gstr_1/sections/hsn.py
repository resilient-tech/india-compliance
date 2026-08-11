"""HSN summary — quantities and tax per product code, split by buyer type (table 12).

Portal:    {hsn_b2b: [{num: 1, hsn_sc: "1102", uqc: "BOX", qty: 2, txval: 100, camt: 0.5}]}
Canonical: {"HSN Summary - B2B": {"1102 - BOX-BOX - 1.0": {hsn_code: "1102", uom: "BOX-BOX",
                                                           quantity: 2, total_taxable_value: 100,
                                                           document_value: 101}}}

Older returns used a single "data" key instead of the b2b/b2c split, and the portal's error
response arrives as one object rather than a list. Both shapes are accepted.
"""

from frappe.utils import flt

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw
from india_compliance.gst_returns.fields.gstr1 import SubCategory

from . import _shared as s

KEYS = {
    raw.HSN_CODE: doc.HSN_CODE,
    raw.DESCRIPTION: doc.DESCRIPTION,
    raw.UOM: doc.UOM,
    raw.QUANTITY: doc.QUANTITY,
    raw.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    raw.IGST: doc.IGST,
    raw.CGST: doc.CGST,
    raw.SGST: doc.SGST,
    raw.CESS: doc.CESS,
    raw.TAX_RATE: item.TAX_RATE,
}

# portal json key -> the subcategory its rows are filed under
SECTIONS = {
    raw.HSN_B2B: SubCategory.HSN_B2B.value,
    raw.HSN_B2C: SubCategory.HSN_B2C.value,
    raw.HSN_DATA: SubCategory.HSN.value,  # older returns
}
SECTION_KEYS = s.flip(SECTIONS)

# what the summary line is worth in total
VALUE_PARTS = (doc.TAXABLE_VALUE, doc.IGST, doc.CGST, doc.SGST, doc.CESS)

MONEY = (
    raw.QUANTITY,
    raw.TAXABLE_VALUE,
    raw.IGST,
    raw.CGST,
    raw.SGST,
    raw.CESS,
)

DESCRIPTION_LIMIT = 30


def truncate_description(text):
    """The portal caps descriptions at 30 characters, without padding."""
    return text.strip()[:DESCRIPTION_LIMIT].rstrip()


def group_key(entry):
    """Identity used to match books against the portal. Discarded before the data is stored."""
    return " - ".join(
        (
            entry.get(raw.HSN_CODE, ""),
            s.uom_from_gov(entry.get(raw.UOM, "")),
            str(flt(entry.get(raw.TAX_RATE))),
        )
    )


def to_canonical(gov_data):
    output = {}

    for payload in [gov_data] if isinstance(gov_data, dict) else gov_data:
        errors = {
            doc.ERROR_CD: payload.get(raw.ERROR_CD),
            doc.ERROR_MSG: payload.get(raw.ERROR_MSG),
        }

        for section, entries in payload.items():
            if section not in SECTIONS:
                continue

            subcategory = SECTIONS[section]
            rows = {}

            for entry in entries:
                row = s.with_defaults(s.pick(entry, KEYS), {**errors, doc.DOC_TYPE: subcategory})

                s.convert(row, doc.UOM, s.uom_from_gov)  # BOX -> BOX-BOX
                row[doc.DOC_VALUE] = s.sum_money(row, VALUE_PARTS)  # 100 + 0.5 + 0.5 -> 101

                # the portal reports errors per line; name the code it complained about
                if (message := row.get(doc.ERROR_MSG, "").strip()) and (hsn := row.get(doc.HSN_CODE)):
                    row[doc.ERROR_MSG] = f"HSN Code: {hsn} - {message}"

                rows[group_key(entry)] = row  # keyed "1102 - BOX-BOX - 1.0"

            # the error response can repeat a section, so merge rather than replace
            output.setdefault(subcategory, {}).update(rows)

    return output


def to_gov(rows, company_gstin=""):
    output = {}
    counts = {}

    for row in rows:
        subcategory = row.get(doc.DOC_TYPE) or SubCategory.HSN.value
        section = SECTION_KEYS.get(subcategory, subcategory)
        counts[section] = counts.get(section, 0) + 1

        out = s.round_money(s.with_defaults(s.pick_back(row, KEYS), {raw.INDEX: counts[section]}), MONEY)

        s.convert(out, raw.UOM, lambda uom: s.uom_to_gov(uom, row.get(doc.HSN_CODE)))
        s.convert(out, raw.DESCRIPTION, truncate_description)

        output.setdefault(section, []).append(out)

    return output
