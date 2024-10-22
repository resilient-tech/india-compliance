import frappe
from frappe.utils import cint, format_date, get_date_str, get_first_day, get_last_day

from india_compliance.gst_india.constants import UOM_MAP
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    GenerateGSTR1,
)
from india_compliance.gst_india.utils import get_month_or_quarter_dict
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
    quarter_no = get_month_or_quarter_dict().get(period)
    filters["from_date"] = get_first_day(f"{cint(year)}-{quarter_no[0]}-01")
    filters["to_date"] = get_last_day(f"{cint(year)}-{quarter_no[1]}-01")
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
            "taxable_value": invoice.taxable_value,
            "igst_rate": invoice.igst_amount,
            "cgst_rate": invoice.cgst_amount,
            "sgst_rate": invoice.sgst_amount,
            "cess_amount": invoice.total_cess_amount,
            "uom": f"{uom}-{UOM_MAP[uom]}",
            "qty": invoice.qty,
            "desc": invoice.description,
            "goods_type": "7b",
        }

    res = {}

    for invoice in invoice_data:
        key = invoice.invoice_no
        uom = invoice.uom.upper()
        challan_date = format_date(get_date_str(invoice.posting_date), "dd-mm-yyyy")

        if key not in res:
            res[key] = {
                "jw_state_code": invoice.place_of_supply,
                "flag": "",
                "items": [create_item(invoice, uom)],
                "original_challan_number": invoice.invoice_no,
                "original_challan_date": challan_date,
                "total_taxable_value": invoice.taxable_value,
                "total_igst_rate": invoice.igst_amount,
                "total_cgst_rate": invoice.cgst_amount,
                "total_sgst_rate": invoice.sgst_amount,
                "total_cess_amount": invoice.total_cess_amount,
            }
        else:
            current_invoice = res[key]
            current_invoice["total_taxable_value"] += invoice.taxable_value
            current_invoice["total_igst_rate"] += invoice.igst_amount
            current_invoice["total_cgst_rate"] += invoice.cgst_amount
            current_invoice["total_sgst_rate"] += invoice.sgst_amount
            current_invoice["total_cess_amount"] += invoice.total_cess_amount
            current_invoice["items"].append(create_item(invoice, uom))

    return res


def process_table_5a_data(invoice_data):
    def create_item(invoice, uom, jw_challan_date, challan_date):
        return {
            "original_challan_date": challan_date,
            "jw_challan_date": jw_challan_date,
            "nature_of_job": "Work",
            "uom": f"{uom}-{UOM_MAP[uom]}",
            "qty": invoice.qty,
            "desc": invoice.description,
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
                "original_challan_number": invoice.original_challan_no,
                "jw_challan_number": invoice.invoice_no,
                "company_gstin": invoice.company_gstin,
                "jw_state_code": invoice.place_of_supply,
                "flag": "",
                "items": [create_item(invoice, uom, jw_challan_date, challan_date)],
            }
        else:
            res[key]["items"].append(
                create_item(invoice, uom, jw_challan_date, challan_date)
            )

    return res


def get_return_period(month_or_quarter, year):
    return {
        "Apr - Jun": "13",
        "Jul - Sep": "14",
        "Oct - Dec": "15",
        "Jan - Mar": "16",
    }.get(month_or_quarter) + str(year)
