"""Move GSTR-1 data between the portal's shape and ours.

Each category lives in its own module under `sections/`; this file only picks which one runs.
Portal docs: https://developer.gst.gov.in/apiportal/taxpayer/returns
"""

from india_compliance.gst_india.utils.gstr_1 import (
    SUB_CATEGORY_GOV_CATEGORY_MAPPING,
)
from india_compliance.gst_india.utils.gstr_1 import (
    DocField as doc,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_books_map import (  # noqa: F401
    GSTR1BooksData,
)
from india_compliance.gst_india.utils.gstr_1.sections import SECTIONS
from india_compliance.gst_india.utils.gstr_1.sections.summary import to_overview


def convert_to_internal_data_format(gov_data, for_errors=False):
    """Portal payload -> our rows, every category present."""
    output = {}

    for category, (read, _write) in SECTIONS.items():
        if not gov_data.get(category):
            continue

        output.update(read(gov_data[category]))

    if not for_errors:
        return output

    errors = []
    for category, rows in output.items():
        for value in rows.values():
            for row in value if isinstance(value, list) else [value]:
                if not (row.get(doc.ERROR_CD) or row.get(doc.ERROR_MSG)):
                    continue

                row["category"] = category
                errors.append(row)

    return errors


def get_category_wise_data(
    subcategory_wise_data: dict,
    mapping: dict = SUB_CATEGORY_GOV_CATEGORY_MAPPING,
) -> dict:
    """Put subcategory rows under the portal category that reports them."""
    category_wise_data = {}

    for subcategory, category in mapping.items():
        if not subcategory_wise_data.get(subcategory.value):
            continue

        category_wise_data.setdefault(category.value, []).extend(
            subcategory_wise_data.get(subcategory.value, [])
        )

    return category_wise_data


def convert_to_gov_data_format(internal_data: dict, company_gstin: str) -> dict:
    """Our rows -> portal payload. Blanks go later, at the JSON boundary."""
    category_wise_data = get_category_wise_data(internal_data)

    output = {}
    for category, (_read, write) in SECTIONS.items():
        if not write or not category_wise_data.get(category):
            continue

        output[category] = write(category_wise_data[category], company_gstin=company_gstin)

    return output


def summarize_retsum_data(input_data):
    return to_overview(input_data)
