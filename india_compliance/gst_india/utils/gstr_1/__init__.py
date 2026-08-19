from frappe.utils import getdate

from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    CATEGORY_SUB_CATEGORY_MAPPING,
    JSON_CATEGORY_EXCEL_CATEGORY_MAPPING,
    PREVIOUS_VERSION,
    QUARTERLY_KEYS,
    SUB_CATEGORY_GOV_CATEGORY_MAPPING,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
    B2BInvoiceType,
    Category,
    DocField,
    ExcelLabel,
    HSNKey,
    ItemField,
    JsonKey,
    RawField,
    SheetName,
    SubCategory,
)

HSN_BIFURCATION_FROM = getdate("2025-05-01")

HSN_DESCRIPTION_LIMIT = 30

B2C_LIMIT = [
    ("2024-07-31", 2_50_000),
    ("2099-03-31", 1_00_000),
]


def get_b2c_limit(date):
    if isinstance(date, str):
        date = getdate(date)

    for limit_date, limit in B2C_LIMIT:
        if date <= getdate(limit_date):
            return limit

    return B2C_LIMIT[-1][1]


def truncate_hsn_description(description):
    return description.strip()[:HSN_DESCRIPTION_LIMIT].rstrip()
