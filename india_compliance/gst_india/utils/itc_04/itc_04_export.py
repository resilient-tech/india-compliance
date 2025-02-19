import frappe
from frappe import _
from frappe.utils import cint, format_date, get_date_str

from india_compliance.gst_india.constants import UOM_MAP
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    GenerateGSTR1,
)
from india_compliance.gst_india.utils.itc_04 import (
    ITC04_DataField,
    ITC04_ItemField,
    ITC04JsonKey,
)
from india_compliance.gst_india.utils.itc_04.itc_04_data import ITC04Query
from india_compliance.gst_india.utils.itc_04.itc_04_json_map import (
    convert_to_gov_data_format,
)


@frappe.whitelist()
def download_itc_04_json(filters):
    frappe.has_permission("GST Job Work Stock Movement", "export", throw=True)

    filters = frappe.parse_json(filters)
    company_gstin = filters.get("company_gstin")
    ret_period = get_return_period(filters)

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


def get_return_period(filters):
    # Helper function to extract year and month from a date string in the format "YYYY-MM"
    def extract_year_month(date_str):
        year, month = map(cint, date_str.split("-")[:2])
        return year, month

    # Extract year and month
    start_year, start_month = extract_year_month(filters.get("from_date"))
    end_year, end_month = extract_year_month(filters.get("to_date"))

    # If the end year is greater than the start year, adjust the end month accordingly
    year_diff = end_year - start_year
    if end_year > start_year:
        end_month += 12 * year_diff

    RETURN_PERIODS = {
        13: (4, 6),
        14: (7, 9),
        15: (10, 12),
        16: (1, 3),
        17: (4, 9),
        18: (10, 15),
        19: (4, 15),
    }

    for period, (start_q, end_q) in RETURN_PERIODS.items():
        if start_month >= start_q and end_month <= end_q:
            return f"{period}{start_year}"

    frappe.throw(
        _(
            "Date range does not belong to any <b>Quarterly</b>,  <b>Half Yearly</b> or <b>Annual</b> Returns."
        )
    )


def get_data(filters):
    itc04 = ITC04Query(filters)

    table_4_data = itc04.get_query_table_4_se().run(
        as_dict=True
    ) + itc04.get_query_table_4_sr().run(as_dict=True)

    table_5a_data = itc04.get_query_table_5A_se().run(
        as_dict=True
    ) + itc04.get_query_table_5A_sr().run(as_dict=True)

    return {
        ITC04JsonKey.FG_RECEIVED.value: process_table_5a_data(table_5a_data),
        ITC04JsonKey.RM_SENT.value: process_table_4_data(table_4_data),
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
            ITC04_ItemField.GOODS_TYPE.value: (
                "8b" if invoice.item_type == "Inputs" else "7b"
            ),
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
