from frappe.utils import getdate

from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    CATEGORY_SUB_CATEGORY_MAPPING,
    JSON_CATEGORY_EXCEL_CATEGORY_MAPPING,
    PREVIOUS_VERSION,
    QUARTERLY_KEYS,
    SUB_CATEGORY_GOV_CATEGORY_MAPPING,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
    SUPECOM,
    HSNKey,
)
from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    B2BInvoiceType as GSTR1_B2B_InvoiceType,
)
from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    Category as GSTR1_Category,
)
from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    DocField as GSTR1_DataField,
)
from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    ExcelLabel as GovExcelField,
)
from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    ItemField as GSTR1_ItemField,
)
from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    JsonKey as GovJsonKey,
)
from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    RawField as GovDataField,
)
from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    SheetName as GovExcelSheetName,
)
from india_compliance.gst_returns.fields.gstr1 import (  # noqa: F401
    SubCategory as GSTR1_SubCategory,
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
