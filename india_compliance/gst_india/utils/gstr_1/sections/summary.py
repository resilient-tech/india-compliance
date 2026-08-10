"""The portal's own summary of a filed return, and the overview built from it.

Read only -- the portal computes this, we never file it back. That is why the keys here are plain
functions over one table instead of a reversible mapping like every other category: two portal
keys ("sec_nm" for a section, "typ" for a line inside one) both become the row's description.

Portal:    [{sec_nm: "B2B_4A", ttl_rec: 12, ttl_tax: 5000, ttl_igst: 900}]
Canonical: {"summary": {"B2B Regular": {description: "B2B Regular", no_of_records: 12,
                                        total_taxable_value: 5000, total_igst_amount: 900}}}
"""

from india_compliance.gst_returns.fields.gstr1 import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
    Category,
    SubCategory,
)
from india_compliance.gst_returns.fields.gstr1 import DocField as doc

from . import _shared as s

AMENDED = "(Amended)"

# summary-only portal keys: "ttl_" is what was filed, "act_" what the portal recomputed
SECTION = "sec_nm"
LINE_TYPE = "typ"
SUB_SECTIONS = "sub_sections"
NET_DOC_ISSUED = "net_doc_issued"

KEYS = {
    SECTION: doc.DESCRIPTION,
    LINE_TYPE: doc.DESCRIPTION,
    "ttl_rec": "no_of_records",
    "ttl_val": "total_document_value",
    "ttl_igst": doc.IGST,
    "ttl_cgst": doc.CGST,
    "ttl_sgst": doc.SGST,
    "ttl_cess": doc.CESS,
    "ttl_tax": doc.TAXABLE_VALUE,
    "act_val": "actual_document_value",
    "act_igst": "actual_igst",
    "act_sgst": "actual_sgst",
    "act_cgst": "actual_cgst",
    "act_cess": "actual_cess",
    "act_tax": "actual_taxable_value",
    "ttl_expt_amt": f"total_{doc.EXEMPTED_AMOUNT}",
    "ttl_ngsup_amt": f"total_{doc.NON_GST_AMOUNT}",
    "ttl_nilsup_amt": f"total_{doc.NIL_RATED_AMOUNT}",
    "ttl_doc_issued": doc.TOTAL_COUNT,
    "ttl_doc_cancelled": doc.CANCELLED_COUNT,
}

# portal section code -> the name shown to the user
SECTION_NAMES = {
    "AT": Category.AT.value,
    "B2B_4A": SubCategory.B2B_REGULAR.value,
    "B2B_4B": SubCategory.B2B_REVERSE_CHARGE.value,
    "B2B_6C": SubCategory.DE.value,
    "B2B_SEZWOP": SubCategory.SEZWOP.value,
    "B2B_SEZWP": SubCategory.SEZWP.value,
    "B2B": Category.B2B.value,
    "B2CL": Category.B2CL.value,
    "B2CS": Category.B2CS.value,
    "TXPD": Category.TXP.value,
    "EXP": Category.EXP.value,
    "CDNR": Category.CDNR.value,
    "CDNUR": Category.CDNUR.value,
    "SUPECOM": Category.SUPECOM.value,
    "ECOM": "ECOM",
    "ECOM_REG": "ECOM_REG",
    "ECOM_DE": "ECOM_DE",
    "ECOM_SEZWOP": "ECOM_SEZWOP",
    "ECOM_SEZWP": "ECOM_SEZWP",
    "ECOM_UNREG": "ECOM_UNREG",
    "ATA": f"{Category.AT.value} {AMENDED}",
    "B2BA_4A": f"{SubCategory.B2B_REGULAR.value} {AMENDED}",
    "B2BA_4B": f"{SubCategory.B2B_REVERSE_CHARGE.value} {AMENDED}",
    "B2BA_6C": f"{SubCategory.DE.value} {AMENDED}",
    "B2BA_SEZWOP": f"{SubCategory.SEZWOP.value} {AMENDED}",
    "B2BA_SEZWP": f"{SubCategory.SEZWP.value} {AMENDED}",
    "B2BA": f"{Category.B2B.value} {AMENDED}",
    "B2CLA": f"{Category.B2CL.value} {AMENDED}",
    "B2CSA": f"{Category.B2CS.value} {AMENDED}",
    "TXPDA": f"{Category.TXP.value} {AMENDED}",
    "EXPA": f"{Category.EXP.value} {AMENDED}",
    "CDNRA": f"{Category.CDNR.value} {AMENDED}",
    "CDNURA": f"{Category.CDNUR.value} {AMENDED}",
    "SUPECOMA": f"{Category.SUPECOM.value} {AMENDED}",
    "ECOMA": "ECOMA",
    "ECOMA_REG": "ECOMA_REG",
    "ECOMA_DE": "ECOMA_DE",
    "ECOMA_SEZWOP": "ECOMA_SEZWOP",
    "ECOMA_SEZWP": "ECOMA_SEZWP",
    "ECOMA_UNREG": "ECOMA_UNREG",
    "HSN": Category.HSN.value,  # older returns
    "HSN_B2B": SubCategory.HSN_B2B.value,
    "HSN_B2C": SubCategory.HSN_B2C.value,
    "NIL": Category.NIL_EXEMPT.value,
    "DOC_ISSUE": Category.DOC_ISSUE.value,
    "TTL_LIAB": "Total Liability",
}

# sections the portal breaks down one level further
SUBSECTION_NAMES = {
    "SUPECOM": {
        "SUPECOM_14A": SubCategory.SUPECOM_52.value,
        "SUPECOM_14B": SubCategory.SUPECOM_9_5.value,
    },
    "SUPECOMA": {
        "SUPECOM_14A": f"{SubCategory.SUPECOM_52.value} {AMENDED}",
        "SUPECOM_14B": f"{SubCategory.SUPECOM_9_5.value} {AMENDED}",
    },
    "EXP": {
        "EXPWP": SubCategory.EXPWP.value,
        "EXPWOP": SubCategory.EXPWOP.value,
    },
    "EXPA": {
        "EXPWP": f"{SubCategory.EXPWP.value} {AMENDED}",
        "EXPWOP": f"{SubCategory.EXPWOP.value} {AMENDED}",
    },
}

# the columns an overview row adds up
TOTAL_FIELDS = (
    "no_of_records",
    doc.IGST,
    doc.CGST,
    doc.SGST,
    doc.CESS,
    doc.TAXABLE_VALUE,
)


def read_row(entry):
    """One summary line, with its section code turned into a readable name."""
    row = s.pick(entry, KEYS)

    s.remap(row, doc.DESCRIPTION, SECTION_NAMES)

    # document ranges count what was actually issued, not what was declared
    if entry.get(SECTION) == "DOC_ISSUE":
        row["no_of_records"] = entry.get(NET_DOC_ISSUED, 0)

    return row


def to_canonical(gov_data):
    output = {}

    for entry in gov_data:
        section = entry.get(SECTION)
        output[SECTION_NAMES.get(section, section)] = read_row(entry)

        if section not in SUBSECTION_NAMES:
            continue

        subsections = entry.get(SUB_SECTIONS, {})

        # older summary APIs do not break sections down; fall back to computing our own
        if not subsections:
            return {}

        for subsection in subsections:
            row = read_row(subsection)
            code = subsection.get(LINE_TYPE) or subsection.get(SECTION)
            row[doc.DESCRIPTION] = SUBSECTION_NAMES[section].get(code, code)
            output[row[doc.DESCRIPTION]] = row

    return {"summary": output}


def total_of(row):
    """Zero-test for an overview row. A null the portal sent counts as nothing."""
    return s.sum_money(row, TOTAL_FIELDS)


def to_overview(rows):
    """Portal summary -> the indented overview shown on the GSTR-1 page."""
    if not rows:
        return []

    overview = []
    amended = dict.fromkeys(TOTAL_FIELDS, 0)
    by_description = {row.get(doc.DESCRIPTION): row for row in rows}

    for category, subcategories in CATEGORY_SUB_CATEGORY_MAPPING.items():
        category = category.value
        if category not in by_description:
            continue

        # amendments are collected into one closing line instead of shown per category
        for field in TOTAL_FIELDS:
            amended[field] += by_description.get(f"{category} {AMENDED}", {}).get(field) or 0

        if total_of(by_description[category]) == 0:
            continue

        overview.append({**by_description[category], "indent": 0})

        for subcategory in subcategories:
            subcategory = subcategory.value
            if subcategory not in by_description or total_of(by_description[subcategory]) == 0:
                continue

            overview.append(
                {
                    **by_description[subcategory],
                    "indent": 1,
                    "consider_in_total_taxable_value": (
                        subcategory not in SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE
                    ),
                    "consider_in_total_tax": (subcategory not in SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX),
                }
            )

    if total_of(amended) != 0:
        overview.append(
            {
                doc.DESCRIPTION: "Net Liability from Amendments",
                **amended,
                "indent": 0,
                "consider_in_total_taxable_value": True,
                "consider_in_total_tax": True,
                "no_of_records": 0,
            }
        )

    return overview
