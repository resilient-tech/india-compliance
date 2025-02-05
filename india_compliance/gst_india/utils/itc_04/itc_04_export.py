import frappe
from frappe.utils import cint, format_date, get_date_str, get_first_day, get_last_day

from india_compliance.gst_india.constants import UOM_MAP
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    GenerateGSTR1,
)
from india_compliance.gst_india.utils import get_month_or_quarter_dict
from india_compliance.gst_india.utils.itc_04 import ITC04_DataField, ITC04_ItemField
from india_compliance.gst_india.utils.itc_04.itc_04_data import ITC04Query
from india_compliance.gst_india.utils.itc_04.itc_04_json_map import (
    convert_to_gov_data_format,
)


@frappe.whitelist()
def download_itc_04_json(
    company,
    company_gstin,
    period,
    year,
):
    frappe.has_permission("GST Job Work Stock Movement", "export", throw=True)

    filters = get_filters(
        company,
        company_gstin,
        period,
        year,
    )
    ret_period = get_return_period(period, year)
    data = get_data(filters)

    GenerateGSTR1().normalize_data(data)

    return {
        "data": {
            "gstin": company_gstin,
            "fp": ret_period,
            **convert_to_gov_data_format(data, company_gstin),
        },
        "filename": f"ITC-04-Gov-{company_gstin}-{ret_period}.json",
    }


def get_filters(
    company,
    company_gstin,
    period,
    year,
):
    filters = {}
    year = cint(year)
    quarter_no = get_month_or_quarter_dict().get(period)
    filters["from_date"] = get_first_day(f"{year}-{quarter_no[0]}-01")

    if quarter_no[1] < quarter_no[0]:
        year += 1

    filters["to_date"] = get_last_day(f"{year}-{quarter_no[1]}-01")
    filters["company_gstin"] = company_gstin
    filters["company"] = company

    return filters


def get_data(filters):
    itc04 = ITC04Query(filters)

    table_4_data = itc04.get_query_table_4_se().run(
        as_dict=True
    ) + itc04.get_query_table_4_sr().run(as_dict=True)

    table_5a_data = itc04.get_query_table_5A_se().run(
        as_dict=True
    ) + itc04.get_query_table_5A_sr().run(as_dict=True)

    return {
        "Stock Entry": process_table_4_data(table_4_data),
        "Table 5A": process_table_5a_data(table_5a_data),
    }


def process_table_4_data(invoice_data):
    def create_item(invoice, uom):
        return {
            ITC04_ItemField.TAXABLE_VALUE.value: abs(invoice.taxable_value),
            ITC04_ItemField.IGST.value: invoice.igst_rate,
            ITC04_ItemField.CGST.value: invoice.cgst_rate,
            ITC04_ItemField.SGST.value: invoice.sgst_rate,
            ITC04_ItemField.CESS_AMOUNT.value: abs(invoice.total_cess_amount),
            ITC04_ItemField.UOM.value: f"{uom}-{UOM_MAP[uom]}",
            ITC04_ItemField.QUANTITY.value: abs(invoice.qty),
            ITC04_ItemField.DESCRIPTION.value: invoice.description,
            ITC04_ItemField.GOODS_TYPE.value: invoice.item_type,
        }

    res = {}

    for invoice in invoice_data:
        key = invoice.invoice_no
        uom = invoice.uom.upper()
        challan_date = format_date(get_date_str(invoice.posting_date), "dd-mm-yyyy")

        if key not in res:
            res[key] = {
                ITC04_DataField.JOB_WORKER_STATE_CODE.value: invoice.place_of_supply,
                ITC04_DataField.FLAG.value: "N",
                ITC04_DataField.ITEMS.value: [create_item(invoice, uom)],
                ITC04_DataField.ORIGINAL_CHALLAN_NUMBER.value: invoice.invoice_no,
                ITC04_DataField.ORIGINAL_CHALLAN_DATE.value: challan_date,
            }
        else:
            res[key][ITC04_DataField.ITEMS.value].append(create_item(invoice, uom))

    return res


def process_table_5a_data(invoice_data):
    def create_item(invoice, uom, jw_challan_date, challan_date):
        return {
            ITC04_DataField.ORIGINAL_CHALLAN_DATE.value: challan_date,
            ITC04_DataField.JOB_WORK_CHALLAN_DATE.value: jw_challan_date,
            ITC04_ItemField.NATURE_OF_JOB.value: "Job Work",  # TODO: What should this be?
            ITC04_ItemField.UOM.value: f"{uom}-{UOM_MAP[uom]}",
            ITC04_ItemField.QUANTITY.value: invoice.qty,
            ITC04_ItemField.DESCRIPTION.value: invoice.description,
        }

    res = {}

    for invoice in invoice_data:
        key = f"{invoice.original_challan_no} - {invoice.invoice_no}"
        uom = invoice.uom.upper()

        jw_challan_date = format_date(get_date_str(invoice.posting_date), "dd-mm-yyyy")
        challan_date = format_date(
            get_date_str(invoice.original_challan_date), "dd-mm-yyyy"
        )

        if key not in res:
            res[key] = {
                ITC04_DataField.ORIGINAL_CHALLAN_NUMBER.value: invoice.original_challan_no,
                ITC04_DataField.JOB_WORK_CHALLAN_NUMBER.value: invoice.invoice_no,
                ITC04_DataField.JOB_WORKER_GSTIN.value: invoice.supplier_gstin,
                ITC04_DataField.JOB_WORKER_STATE_CODE.value: invoice.place_of_supply,
                ITC04_DataField.FLAG.value: "N",
                ITC04_DataField.ITEMS.value: [
                    create_item(invoice, uom, jw_challan_date, challan_date)
                ],
            }
        else:
            res[key][ITC04_DataField.ITEMS.value].append(
                create_item(invoice, uom, jw_challan_date, challan_date)
            )

    return res


def get_return_period(month_or_quarter, year):
    return {
        "Apr - Jun": "13",
        "Jul - Sep": "14",
        "Oct - Dec": "15",
        "Jan - Mar": "16",
        "Apr - Sep": "17",
        "Oct - Mar": "18",
    }.get(month_or_quarter) + str(year)
