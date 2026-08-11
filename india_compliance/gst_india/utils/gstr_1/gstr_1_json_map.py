"""Move GSTR-1 data between the portal's shape and ours.

The portal's own docs: https://developer.gst.gov.in/apiportal/taxpayer/returns

Each category is handled by its own module under `sections/`; this file only decides which one
runs. Reading keeps everything the portal sent, so the payload can always be rebuilt from what we
stored. Writing rounds amounts; blanks are removed once, where the JSON leaves for the portal.
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
    """Portal payload -> canonical rows, for every category present."""
    output = {}

    for category, (read, _write) in SECTIONS.items():
        if not gov_data.get(category):
            continue

        output.update(read(gov_data[category]))

    if not for_errors:
        return output

    errors = []
    for category, rows in output.items():
        for row in rows.values():
            if not (row.get(doc.ERROR_CD) or row.get(doc.ERROR_MSG)):
                continue

            row["category"] = category
            errors.append(row)

    return errors


def get_category_wise_data(
    subcategory_wise_data: dict,
    mapping: dict = SUB_CATEGORY_GOV_CATEGORY_MAPPING,
) -> dict:
    """Collect subcategory rows under the portal category that reports them.

    Example:
        {"B2B Regular": [...], "SEZ With Payment of Tax": [...]}  ->  {"b2b": [...both...]}
    """
    category_wise_data = {}

    for subcategory, category in mapping.items():
        if not subcategory_wise_data.get(subcategory.value):
            continue

        category_wise_data.setdefault(category.value, []).extend(
            subcategory_wise_data.get(subcategory.value, [])
        )

    return category_wise_data


def convert_to_gov_data_format(internal_data: dict, company_gstin: str) -> dict:
    """Canonical rows -> portal payload. Blanks are dropped later, at the JSON boundary."""
    category_wise_data = get_category_wise_data(internal_data)

    output = {}
    for category, (_read, write) in SECTIONS.items():
        if not write or not category_wise_data.get(category):
            continue

        output[category] = write(category_wise_data[category], company_gstin=company_gstin)

    return output


def summarize_retsum_data(input_data):
    return to_overview(input_data)
