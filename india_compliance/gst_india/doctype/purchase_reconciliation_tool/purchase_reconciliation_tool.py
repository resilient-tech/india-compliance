# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

from calendar import monthrange
from datetime import datetime
from math import ceil
from typing import List

import pandas as pd
from fuzzywuzzy import fuzz, process

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import Sum
from frappe.utils import cint, getdate

from india_compliance.gst_india.utils import get_json_from_file
from india_compliance.gst_india.utils.gstr import (
    GSTRCategory,
    ReturnType,
    download_gstr_2a,
    download_gstr_2b,
    save_gstr_2a,
    save_gstr_2b,
)


class PurchaseReconciliationTool(Document):
    FIELDS_TO_MATCH = ["fy", "bill_no", "place_of_supply", "reverse_charge", "tax"]

    def validate(self):
        self.reconcilier()

    def reconcilier(self):
        purchases = self.get_b2b_purchase()
        print(purchases)
        inward_supplies = self.get_b2b_inward_supply()

        rules_list = [
            {"Exact Match": ["E", "E", "E", "E", 0]},
            {"Exact Match": ["E", "F", "E", "E", 0]},
            {"Partial Match": ["E", "E", "E", "E", 4]},
            {"Partial Match": ["E", "F", "E", "E", 4]},
            {"Mismatch": ["E", "E", "N", "N", "N"]},
            {"Mismatch": ["E", "F", "N", "N", "N"]},
            {"Residual Match": ["E", "N", "E", "E", 4]},
        ]
        for rules in rules_list:
            for k, v in rules.items():
                self.find_match(purchases, inward_supplies, k, v)

    def find_match(self, purchases, inward_supplies, status, rules):
        for gstin in purchases:
            if not inward_supplies.get(gstin):
                continue

            monthly_pur = {}
            if status == "Residual Match":
                monthly_pur = self.get_monthly_pur(purchases[gstin])
                monthly_isup = self.get_monthly_pur(inward_supplies[gstin])
                status = "Mismatch"

            for pur in purchases[gstin][:]:
                for isup in inward_supplies.get(gstin)[:]:
                    if monthly_pur and not (
                        -4
                        < monthly_pur[pur.bill_date.month]
                        - monthly_isup[isup.bill_date.month]
                        < 4
                    ):
                        continue

                    if not self.rules_match(pur, isup, rules):
                        continue
                    print(pur.bill_no, isup.bill_no, pur.name, isup.name)
                    # frappe.db.set_value(
                    #     "Inward Supply",
                    #     isup.name,
                    #     {
                    #         "match_status": status,
                    #         "link_doctype": "Purchase Invoice",
                    #         "link_name": pur.name,
                    #     },
                    # )
                    purchases[gstin].remove(pur)
                    inward_supplies[gstin].remove(isup)
                    break

    def rules_match(self, pur, isup, rules):
        for field in self.FIELDS_TO_MATCH:
            i = self.FIELDS_TO_MATCH.index(field)
            if not self.get_field_match(pur, isup, field, rules[i]):
                return False
        return True

    def get_field_match(self, pur, isup, field, rule):
        # **** Just for Reference ****
        #  "E": "Exact Match"
        #  "F": "Fuzzy Match for Bill No"
        #  "N": "No Match"
        #    0: "No Tax Difference"
        #    4: "Rounding Tax Difference"
        if rule == "E":
            return pur[field] == isup[field]
        elif rule == "N":
            return True
        elif rule == "F":
            return self.fuzzy_match(pur, isup)
        elif rule == 0:
            return self.get_tax_differece(pur, isup) == 0
        elif rule == 4:
            return -4 < self.get_tax_differece(pur, isup) < 4

    def get_monthly_pur(self, gstin_data):
        monthly_pur = {}
        for pur in gstin_data:
            if monthly_pur.get(pur.bill_date.month):
                monthly_pur[pur.bill_date.month] += self.get_pur_tax(pur)
            else:
                monthly_pur[pur.bill_date.month] = self.get_pur_tax(pur)
        return monthly_pur

    def get_tax_differece(self, pur, isup):
        pur_tax = self.get_pur_tax(pur)
        isup_tax = self.get_pur_tax(isup)
        return pur_tax - isup_tax

    def get_pur_tax(self, pur):
        return pur.igst + pur.cgst + pur.sgst + pur.cess

    def fuzzy_match(self, pur, isup):
        if pur.bill_date.month != isup.bill_date.month:
            return False

        partial_ratio = fuzz.partial_ratio(pur._bill_no, isup._bill_no)
        if float(partial_ratio) == 100:
            return True
        return float(process.extractOne(pur._bill_no, [isup._bill_no])[1]) >= 90.0

    def get_b2b_purchase(self):
        purchase_invoices = frappe.get_all(
            "Purchase Invoice",
            filters={
                "company_gstin": self.company_gstin,
                "gst_category": "Registered Regular",
                "is_return": 0,
                "posting_date": (
                    "between",
                    [self.purchase_from_date, self.purchase_to_date],
                ),
            },
            fields=(
                "name",
                "posting_date",
                "supplier_name",
                "supplier_gstin",
                "bill_no",
                "bill_date",
                "reverse_charge",
                "place_of_supply",
                # TODO get tax accounts to match
                "itc_integrated_tax as igst",
                "itc_central_tax as cgst",
                "itc_state_tax as sgst",
                "itc_cess_amount as cess",
            ),
        )

        linked_purchase_invoice = frappe.get_all(
            "Inward Supply",
            filters={"link_doctype": "Purchase Invoice"},
            fields="link_name",
            pluck="name",
        )

        for invoice in purchase_invoices:
            if invoice.name in linked_purchase_invoice:
                del invoice
                continue

            invoice.fy = self.get_fy(invoice.bill_date or invoice.posting_date)
            invoice.reverse_charge = cint(invoice.reverse_charge == "Y")
            invoice._bill_no = self.get_comparable_bill_no(invoice.bill_no, invoice.fy)

        return self.get_dict_for_key("supplier_gstin", purchase_invoices)

    def get_b2b_inward_supply(self):
        inward_supply = frappe.qb.DocType("Inward Supply")
        inward_supply_item = frappe.qb.DocType("Inward Supply Item")
        inward_supply_data = (
            frappe.qb.from_(inward_supply)
            .join(inward_supply_item)
            .on(inward_supply_item.parent == inward_supply.name)
            .where(self.company_gstin == inward_supply.company_gstin)
            .where(inward_supply.action.isin(["No Action", "Pending"]))
            .where(inward_supply.link_name.isnull())
            .where(inward_supply.classification.isin(["B2B", "B2BA"]))
            .where(inward_supply.doc_date < "2021-08-01")
            .groupby(inward_supply_item.parent)
            .select(
                "name",
                "supplier_name",
                "supplier_gstin",
                inward_supply.doc_number.as_("bill_no"),
                inward_supply.doc_date.as_("bill_date"),
                "reverse_charge",
                "place_of_supply",
                "classification",
                Sum(inward_supply_item.taxable_value).as_("taxable_value"),
                Sum(inward_supply_item.igst).as_("igst"),
                Sum(inward_supply_item.cgst).as_("cgst"),
                Sum(inward_supply_item.sgst).as_("sgst"),
                Sum(inward_supply_item.cess).as_("cess"),
            )
            .run(as_dict=True, debug=True)
        )
        # TODO process inward_supply_data
        for i_s in inward_supply_data:
            i_s["fy"] = self.get_fy(i_s.bill_date)
            i_s["_bill_no"] = self.get_comparable_bill_no(i_s.bill_no, i_s.fy)
            if i_s.classification == "B2BA":
                # find B2B
                # change action
                # unmatch with purchase and add match with current B2BA and same status
                # remove it from the list and remove B2B from the list if action in where filters above
                pass

        inward_supply_data = self.get_dict_for_key("supplier_gstin", inward_supply_data)
        return inward_supply_data

    def get_fy(self, date):
        if not date:
            return
        # Standard for India. Presuming 99.99% suppliers would use this.
        if date.month < 4:
            return f"{date.year - 1}-{date.year}"
        return f"{date.year}-{date.year + 1}"

    def get_dict_for_key(self, key, list):
        new_dict = frappe._dict()
        for data in list:
            if data[key] in new_dict:
                new_dict[data[key]].append(data)
            else:
                new_dict[data[key]] = [data]
        return new_dict

    def get_comparable_bill_no(self, bill_no, fy):
        fy = fy.split("-")
        replace_list = [
            f"{fy[0]}-{fy[1]}",
            f"{fy[0]}/{fy[1]}",
            f"{fy[0]}-{fy[1][2:]}",
            f"{fy[0]}/{fy[1][2:]}",
            f"{fy[0][2:]}-{fy[1][2:]}",
            f"{fy[0][2:]}/{fy[1][2:]}",
            "/",  # these are only special characters allowed in invoice
            "-",
        ]

        inv = bill_no
        for replace in replace_list:
            inv = inv.replace(replace, " ")
        inv = " ".join(inv.split()).lstrip("0")
        return inv

    @frappe.whitelist()
    def upload_gstr(self, return_type, period, file_path):
        return_type = ReturnType(return_type)
        json_data = get_json_from_file(file_path)
        if return_type == ReturnType.GSTR2A:
            return save_gstr_2a(self.company_gstin, period, json_data)

        if return_type == ReturnType.GSTR2B:
            return save_gstr_2b(self.company_gstin, period, json_data)

    @frappe.whitelist()
    def download_gstr_2a(self, fiscal_year, force=False, otp=None):
        periods = get_periods(fiscal_year)
        if not force:
            periods = self.get_periods_to_download(ReturnType.GSTR2A, periods)

        return download_gstr_2a(self.company_gstin, periods, otp)

    @frappe.whitelist()
    def download_gstr_2b(self, fiscal_year, otp=None):
        periods = self.get_periods_to_download(
            ReturnType.GSTR2B, get_periods(fiscal_year)
        )
        return download_gstr_2b(self.company_gstin, periods, otp)

    def get_periods_to_download(self, return_type, periods):
        existing_periods = get_downloads_history(
            self.company_gstin,
            return_type,
            periods,
            pluck="return_period",
        )

        return set(periods) - set(existing_periods)

    @frappe.whitelist()
    def get_download_history(self, return_type, fiscal_year, for_download=True):
        # TODO: refactor this method
        if not return_type:
            return

        return_type = ReturnType(return_type)
        periods = get_periods(fiscal_year)
        history = get_downloads_history(self.company_gstin, return_type, periods)

        columns = [
            "Period",
            "Classification",
            "Status",
            f"{'Downloaded' if for_download else 'Uploaded'} On",
        ]

        data = {}
        for period in periods:
            # TODO: skip if today is not greater than 14th return period's next months
            data[period] = []
            status = "🟢 &nbsp; Downloaded"
            for category in GSTRCategory:
                download = next(
                    (
                        log
                        for log in history
                        if log.return_period == period
                        and log.classification in (category.value, "")
                    ),
                    None,
                )

                status = "🟠 &nbsp; Not Downloaded"
                if download:
                    status = "🟢 &nbsp; Downloaded"
                    if download.data_not_found:
                        status = "🔵 &nbsp; Data Not Found"

                if not for_download:
                    status = status.replace("Downloaded", "Uploaded")

                _dict = {
                    "Classification": category.value
                    if return_type is ReturnType.GSTR2A
                    else "ALL",
                    "Status": status,
                    columns[-1]: "✅ &nbsp;"
                    + download.last_updated_on.strftime("%d-%m-%Y %H:%M:%S")
                    if download
                    else "",
                }
                if _dict not in data[period]:
                    data[period].append(_dict)

        return frappe.render_template(
            "gst_india/doctype/purchase_reconciliation_tool/download_history.html",
            {"columns": columns, "data": data},
        )

    @frappe.whitelist()
    def get_return_period_from_file(self, return_type, file_path):
        if not file_path:
            return

        return_type = ReturnType(return_type)
        try:
            json_data = get_json_from_file(file_path)
            if return_type == ReturnType.GSTR2A:
                return json_data.get("fp")

            if return_type == ReturnType.GSTR2B:
                return json_data.get("data").get("rtnprd")

        except Exception:
            pass

    # filters
    # get 2 data sets
    # rules to match data with preference
    @frappe.whitelist()
    def get_date_range(self, period):
        now = datetime.now()
        start_month = end_month = month = now.month
        start_year = end_year = year = now.year
        quarter = ceil(month / 3)

        if "Previous Month" in period:
            start_month = end_month = month - 1 or 12
        elif "Quarter" in period:
            end_month = quarter * 3
            if "Previous" in period:
                end_month = (quarter - 1) * 3 or 12
            start_month = end_month - 2

        if start_month > month:
            start_year = end_year = year - 1
        elif "Year" in period:
            start_month = 4
            end_month = 3
            if "Previous" in period:
                start_year = end_year = year - 1
            if start_month > month:
                start_year -= 1
            else:
                end_year += 1

        date1 = datetime.strftime(datetime(start_year, start_month, 1), "%Y-%m-%d")
        date2 = datetime(end_year, end_month, monthrange(end_year, end_month)[1])
        date2 = datetime.strftime(date2 if date2 < now else now, "%Y-%m-%d")
        return [date1, date2]

    @frappe.whitelist()
    def get_reconciliation_data(self, company_gstin, force=False):
        if not force and self.reconciliation_data:
            return self.reconciliation_data

        # TODO: add more filters

        purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        purchase_tax = frappe.qb.DocType("Purchase Taxes and Charges")
        inward_supply = frappe.qb.DocType("Inward Supply")
        inward_supply_item = frappe.qb.DocType("Inward Supply Item")

        # TODO: do full outer joinap
        self.reconciliation_data = (
            frappe.qb.from_(purchase_invoice)
            .left_join(purchase_tax)
            .on(purchase_tax.parent == purchase_invoice.name)
            .full_outer_join(inward_supply)
            .on(
                (inward_supply.link_doctype == "Purchase Invoice")
                & (inward_supply.link_name == purchase_invoice.name)
            )
            .left_join(inward_supply_item)
            .on(inward_supply_item.parent == inward_supply.name)
            .where(company_gstin == purchase_invoice.company_gstin)
            .where(purchase_invoice.is_return == 0)
            .where(purchase_invoice.gst_category == "Registered Regular")
            .select(
                purchase_invoice.name.as_("purchase_invoice_number"),
                purchase_invoice.supplier_name,
                purchase_invoice.supplier_gstin,
                # from inward supply
                inward_supply.name.as_("inward_supply_number"),
                inward_supply.doc_number.as_("bill_no"),
                inward_supply.doc_date.as_("bill_date"),
                inward_supply.reverse_charge,
                inward_supply.place_of_supply,
                inward_supply.classification,
                inward_supply.match_status,
                Sum(inward_supply_item.taxable_value).as_("taxable_value"),
                Sum(inward_supply_item.igst).as_("igst"),
                Sum(inward_supply_item.cgst).as_("cgst"),
                Sum(inward_supply_item.sgst).as_("sgst"),
                Sum(inward_supply_item.cess).as_("cess"),
            )
        )


@frappe.whitelist()
def get_summary_data(
    company_gstin,
    purchase_from_date,
    purchase_to_date,
    inward_from_date,
    inward_to_date,
):
    purchase = frappe.qb.DocType("Purchase Invoice")
    taxes = frappe.qb.DocType("Purchase Taxes and Charges")
    purchase_data = (
        frappe.qb.from_(purchase)
        .join(taxes)
        .on(taxes.parent == purchase.name)
        .where(
            purchase.posting_date[purchase_from_date:purchase_to_date]
        )  # TODO instead all purchases not matched yet but gst accounts affected, should come up here after a specific date.
        .where(company_gstin == purchase.company_gstin)
        .where(purchase.is_return == 0)
        .where(purchase.gst_category == "Registered Regular")
        # .where(purchase.bill_no.like("GST/%"))
        .groupby(taxes.parent)
        .select(
            "name",
            "supplier_name",
            "supplier_gstin",
        )
        .run(as_dict=True, debug=True)
    )

    inward_supply = frappe.qb.DocType("Inward Supply")
    inward_supply_item = frappe.qb.DocType("Inward Supply Item")
    inward_supply_data = (
        frappe.qb.from_(inward_supply)
        .join(inward_supply_item)
        .on(inward_supply_item.parent == inward_supply.name)
        .where(inward_supply.doc_date[inward_from_date:inward_to_date])
        .where(company_gstin == inward_supply.company_gstin)
        .where(inward_supply.action.isin(["No Action", "Pending"]))
        .where(inward_supply.link_name.isnull())
        .where(inward_supply.classification.isin(["B2B", "B2BA"]))
        .where(inward_supply.doc_date < "2021-08-01")
        .groupby(inward_supply_item.parent)
        .select(
            "name",
            "supplier_name",
            "supplier_gstin",
            inward_supply.doc_number.as_("bill_no"),
            inward_supply.doc_date.as_("bill_date"),
            "reverse_charge",
            "place_of_supply",
            "classification",
            Sum(inward_supply_item.taxable_value).as_("taxable_value"),
            Sum(inward_supply_item.igst).as_("igst"),
            Sum(inward_supply_item.cgst).as_("cgst"),
            Sum(inward_supply_item.sgst).as_("sgst"),
            Sum(inward_supply_item.cess).as_("cess"),
        )
        .run(as_dict=True, debug=True)
    )

    summary_data = []
    summary_data.append(
        {
            "no_of_doc_purchase": len(purchase_data),
            "no_of_inward_supp": len(inward_supply_data),
            "purchase_data": purchase_data,
        }
    )
    return summary_data


def get_periods(fiscal_year):
    """Returns a list of month (formatted as `MMYYYY`) in a fiscal year"""

    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        fiscal_year,
        ("year_start_date as start_date", "year_end_date as end_date"),
        as_dict=True,
    )

    if not fiscal_year:
        return []

    end_date = min(fiscal_year.end_date, getdate())

    # latest to oldest
    return tuple(reversed(_get_periods(fiscal_year.start_date, end_date)))


def _get_periods(start_date, end_date):
    """Returns a list of month (formatted as `MMYYYY`) in given date range"""

    return pd.date_range(start_date, end_date, freq="MS").strftime("%m%Y").tolist()


# TODO: rearrange the code
def get_downloads_history(
    company_gstin, return_type: ReturnType, periods: List[str], fields=None, pluck=None
):
    if not (fields or pluck):
        fields = (
            "return_period",
            "classification",
            "data_not_found",
            "last_updated_on",
        )

    return frappe.db.get_all(
        "GSTR Download Log",
        filters={
            "gstin": company_gstin,
            "return_type": return_type.value,
            "return_period": ("in", periods),
        },
        fields=fields,
        pluck=pluck,
    )
