# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import json
import os
from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import IfNull, Sum
from frappe.utils import cint, cstr, flt, get_first_day, get_last_day

from india_compliance.gst_india.constants import INVOICE_DOCTYPES, STATE_NUMBERS
from india_compliance.gst_india.overrides.transaction import is_inter_state_supply
from india_compliance.gst_india.report.gstr_1.gstr_1 import GSTR11A11BData
from india_compliance.gst_india.report.gstr_3b_details.gstr_3b_details import (
    IneligibleITC,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type, get_period

VALUES_TO_UPDATE = ["iamt", "camt", "samt", "csamt"]
GST_TAX_TYPE_MAP = {
    "sgst": "samt",
    "cgst": "camt",
    "igst": "iamt",
    "cess": "csamt",
    "cess_non_advol": "csamt",
}


class GSTR3BReport(Document):
    def validate(self):
        self.json_output = ""
        self.missing_field_invoices = ""
        self.generation_status = "In Process"

        if self.enqueue_report:
            frappe.msgprint(_("Intiated report generation in background"), alert=True)
            frappe.enqueue_doc("GSTR 3B Report", self.name, "get_data", queue="long")
            return

        self.get_data()

    def get_data(self):
        try:
            self.report_dict = json.loads(get_json("gstr_3b_report_template"))

            self.gst_details = self.get_company_gst_details()
            self.report_dict["gstin"] = self.gst_details.get("gstin")
            self.report_dict["ret_period"] = get_period(
                self.month_or_quarter, self.year
            )
            self.month_or_quarter_no = get_period(self.month_or_quarter)
            self.from_date = get_first_day(
                f"{cint(self.year)}-{self.month_or_quarter_no[0]}-01"
            )

            self.to_date = get_last_day(
                f"{cint(self.year)}-{self.month_or_quarter_no[1]}-01"
            )

            self.get_outward_supply_details("Sales Invoice")
            self.set_outward_taxable_supplies()

            self.get_outward_supply_details("Purchase Invoice", reverse_charge=True)
            self.set_supplies_liable_to_reverse_charge()

            self.set_advances_received_or_adjusted()

            itc_details = self.get_itc_details()
            self.set_itc_details(itc_details)
            self.get_itc_reversal_entries()
            inward_nil_exempt = self.get_inward_nil_exempt(
                self.gst_details.get("gst_state")
            )
            self.set_reclaim_of_itc_reversal()
            self.set_inward_nil_exempt(inward_nil_exempt)

            self.set_reverse_charge_supply_through_ecomm_operators()

            self.missing_field_invoices = self.get_missing_field_invoices()
            self.report_dict = format_values(self.report_dict)
            self.json_output = frappe.as_json(self.report_dict)
            self.generation_status = "Generated"

            if self.enqueue_report:
                self.db_set(
                    {
                        "json_output": self.json_output,
                        "missing_field_invoices": self.missing_field_invoices,
                        "generation_status": self.generation_status,
                    }
                )

        except Exception as e:
            self.generation_status = "Failed"
            self.db_set({"generation_status": self.generation_status})
            frappe.db.commit()
            raise e

        finally:
            frappe.publish_realtime(
                "gstr3b_report_generation", doctype=self.doctype, docname=self.name
            )

    def set_inward_nil_exempt(self, inward_nil_exempt):
        self.report_dict["inward_sup"]["isup_details"][0]["inter"] = flt(
            inward_nil_exempt.get("gst").get("inter"), 2
        )
        self.report_dict["inward_sup"]["isup_details"][0]["intra"] = flt(
            inward_nil_exempt.get("gst").get("intra"), 2
        )
        self.report_dict["inward_sup"]["isup_details"][1]["inter"] = flt(
            inward_nil_exempt.get("non_gst").get("inter"), 2
        )
        self.report_dict["inward_sup"]["isup_details"][1]["intra"] = flt(
            inward_nil_exempt.get("non_gst").get("intra"), 2
        )

    def set_itc_details(self, itc_details):
        itc_eligible_type_map = {
            "IMPG": "Import Of Goods",
            "IMPS": "Import Of Service",
            "ISRC": "ITC on Reverse Charge",
            "ISD": "Input Service Distributor",
            "OTH": "All Other ITC",
        }

        net_itc = self.report_dict["itc_elg"]["itc_net"]

        for d in self.report_dict["itc_elg"]["itc_avl"]:
            itc_type = itc_eligible_type_map.get(d["ty"])
            for key in VALUES_TO_UPDATE:
                d[key] = flt(itc_details.get(itc_type, {}).get(key))
                net_itc[key] += d[key]

    def get_itc_reversal_entries(self):
        self.update_itc_reversal_from_journal_entry()
        self.update_itc_reversal_from_purchase_invoice()
        self.update_itc_reversal_from_bill_of_entry()

    def update_itc_reversal_from_purchase_invoice(self):
        self.update_itc_reversal_for_purchase_us_17_4()
        self.update_itc_reversal_for_purchase_due_to_pos()

    def update_itc_reversal_for_purchase_due_to_pos(self):
        ineligible_credit = IneligibleITC(
            self.company,
            self.gst_details.get("gstin"),
            self.month_or_quarter_no,
            self.year,
        ).get_for_purchase(
            "ITC restricted due to PoS rules", group_by="ineligibility_reason"
        )

        self.process_ineligible_credit(ineligible_credit)

    def update_itc_reversal_for_purchase_us_17_4(self):
        ineligible_credit = IneligibleITC(
            self.company,
            self.gst_details.get("gstin"),
            self.month_or_quarter_no,
            self.year,
        ).get_for_purchase(
            "Ineligible As Per Section 17(5)", group_by="ineligibility_reason"
        )

        self.process_ineligible_credit(ineligible_credit)

    def update_itc_reversal_from_bill_of_entry(self):
        ineligible_credit = IneligibleITC(
            self.company,
            self.gst_details.get("gstin"),
            self.month_or_quarter_no,
            self.year,
        ).get_for_bill_of_entry()

        self.process_ineligible_credit(ineligible_credit)

    def process_ineligible_credit(self, ineligible_credit):
        if not ineligible_credit:
            return

        tax_amounts = VALUES_TO_UPDATE

        for row in ineligible_credit:
            if row.itc_classification == "Ineligible As Per Section 17(5)":
                for key in tax_amounts:
                    if key not in row:
                        continue

                    self.report_dict["itc_elg"]["itc_rev"][0][key] += row[key]
                    self.report_dict["itc_elg"]["itc_net"][key] -= row[key]

            elif row.itc_classification == "ITC restricted due to PoS rules":
                for key in tax_amounts:
                    if key not in row:
                        continue

                    self.report_dict["itc_elg"]["itc_inelg"][1][key] += row[key]

    def update_itc_reversal_from_journal_entry(self):
        journal_entry = frappe.qb.DocType("Journal Entry")
        journal_entry_account = frappe.qb.DocType("Journal Entry Account")

        reversal_entries = (
            frappe.qb.from_(journal_entry)
            .join(journal_entry_account)
            .on(journal_entry_account.parent == journal_entry.name)
            .select(
                journal_entry_account.gst_tax_type,
                journal_entry.ineligibility_reason,
                Sum(journal_entry_account.credit_in_account_currency).as_("amount"),
            )
            .where(journal_entry.voucher_type == "Reversal Of ITC")
            .where(IfNull(journal_entry_account.gst_tax_type, "") != "")
            .groupby(
                journal_entry_account.gst_tax_type, journal_entry.ineligibility_reason
            )
        )
        reversal_entries = self.get_query_with_conditions(
            journal_entry, reversal_entries, party_gstin=""
        ).run(as_dict=True)

        net_itc = self.report_dict["itc_elg"]["itc_net"]

        for entry in reversal_entries:
            if entry.ineligibility_reason == "As per rules 42 & 43 of CGST Rules":
                index = 0
            else:
                index = 1

            tax_amount_key = GST_TAX_TYPE_MAP.get(entry.gst_tax_type)
            self.report_dict["itc_elg"]["itc_rev"][index][
                tax_amount_key
            ] += entry.amount

            net_itc[tax_amount_key] -= entry.amount

    def get_itc_details(self):
        purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")

        itc_amounts = (
            frappe.qb.from_(purchase_invoice)
            .inner_join(purchase_invoice_item)
            .on(
                (purchase_invoice_item.parent == purchase_invoice.name)
                & (purchase_invoice_item.parenttype == "Purchase Invoice")
            )
            .select(
                purchase_invoice.itc_classification,
                Sum(purchase_invoice_item.igst_amount).as_("itc_integrated_tax"),
                Sum(purchase_invoice_item.cgst_amount).as_("itc_central_tax"),
                Sum(purchase_invoice_item.sgst_amount).as_("itc_state_tax"),
                Sum(purchase_invoice_item.cess_amount).as_("itc_cess_amount"),
            )
            .where(
                (purchase_invoice.docstatus == 1)
                & (purchase_invoice.is_opening == "No")
                & (purchase_invoice.posting_date[self.from_date : self.to_date])
                & (purchase_invoice.company == self.company)
                & (purchase_invoice.company_gstin == self.company_gstin)
                & (
                    purchase_invoice.company_gstin
                    != IfNull(purchase_invoice.supplier_gstin, "")
                )
                & (IfNull(purchase_invoice.itc_classification, "") != "")
                & (
                    IfNull(purchase_invoice.ineligibility_reason, "")
                    != "ITC restricted due to PoS rules"
                )  # Ignore as it is Ineligible for ITC
            )
            .groupby(purchase_invoice.itc_classification)
            .run(as_dict=True)
        )

        itc_details = {}
        for d in itc_amounts:
            itc_details.setdefault(
                d.itc_classification,
                {
                    "iamt": d.itc_integrated_tax,
                    "camt": d.itc_central_tax,
                    "samt": d.itc_state_tax,
                    "csamt": d.itc_cess_amount,
                },
            )

        self.update_imports_from_bill_of_entry(itc_details)

        return itc_details

    def update_imports_from_bill_of_entry(self, itc_details):
        boe = frappe.qb.DocType("Bill of Entry")
        boe_taxes = frappe.qb.DocType("India Compliance Taxes and Charges")

        def _get_tax_amount(account_type):
            return (
                frappe.qb.from_(boe)
                .select(Sum(boe_taxes.tax_amount))
                .join(boe_taxes)
                .on(boe_taxes.parent == boe.name)
                .where(
                    boe.posting_date[self.from_date : self.to_date]
                    & boe.company_gstin.eq(self.gst_details.get("gstin"))
                    & boe.docstatus.eq(1)
                    & boe_taxes.gst_tax_type.eq(account_type)
                )
                .where(boe_taxes.parenttype == "Bill of Entry")
                .run()
            )[0][0] or 0

        igst, cess = _get_tax_amount("igst"), _get_tax_amount("cess")
        itc_details.setdefault("Import Of Goods", {"iamt": 0, "csamt": 0})
        itc_details["Import Of Goods"]["iamt"] += igst
        itc_details["Import Of Goods"]["csamt"] += cess

    def set_reclaim_of_itc_reversal(self):
        journal_entry = frappe.qb.DocType("Journal Entry")
        journal_entry_account = frappe.qb.DocType("Journal Entry Account")

        reclaimed_entries = (
            frappe.qb.from_(journal_entry)
            .join(journal_entry_account)
            .on(journal_entry_account.parent == journal_entry.name)
            .select(
                journal_entry_account.gst_tax_type,
                Sum(journal_entry_account.debit_in_account_currency).as_("amount"),
            )
            .where(journal_entry.voucher_type == "Reclaim of ITC Reversal")
            .where(IfNull(journal_entry_account.gst_tax_type, "") != "")
            .groupby(journal_entry_account.gst_tax_type)
        )
        reclaimed_entries = self.get_query_with_conditions(
            journal_entry, reclaimed_entries, party_gstin=""
        ).run(as_dict=True)

        for entry in reclaimed_entries:
            tax_amount_key = GST_TAX_TYPE_MAP.get(entry.gst_tax_type)
            self.report_dict["itc_elg"]["itc_inelg"][0][tax_amount_key] += entry.amount

    def get_inward_nil_exempt(self, state):
        inward_nil_exempt = frappe.db.sql(
            """
            SELECT p.place_of_supply, p.supplier_address,
            i.taxable_value, i.gst_treatment
            FROM `tabPurchase Invoice` p , `tabPurchase Invoice Item` i
            WHERE p.docstatus = 1 and p.name = i.parent
            and p.is_opening = 'No'
            and p.company_gstin != IFNULL(p.supplier_gstin, "")
            and (i.gst_treatment != 'Taxable' or p.gst_category = 'Registered Composition') and
            p.posting_date between %s and %s
            and p.company = %s and p.company_gstin = %s
            """,
            (
                self.from_date,
                self.to_date,
                self.company,
                self.gst_details.get("gstin"),
            ),
            as_dict=1,
        )

        inward_nil_exempt_details = {
            "gst": {"intra": 0.0, "inter": 0.0},
            "non_gst": {"intra": 0.0, "inter": 0.0},
        }

        address_state_map = get_address_state_map()

        for d in inward_nil_exempt:
            if not d.place_of_supply:
                d.place_of_supply = "00-" + cstr(state)

            supplier_state = address_state_map.get(d.supplier_address) or state
            is_intra_state = cstr(supplier_state) == cstr(
                d.place_of_supply.split("-")[1]
            )
            amount = flt(d.taxable_value, 2)

            if d.gst_treatment != "Non-GST":
                if is_intra_state:
                    inward_nil_exempt_details["gst"]["intra"] += amount
                else:
                    inward_nil_exempt_details["gst"]["inter"] += amount
            else:
                if is_intra_state:
                    inward_nil_exempt_details["non_gst"]["intra"] += amount
                else:
                    inward_nil_exempt_details["non_gst"]["inter"] += amount

        return inward_nil_exempt_details

    def set_reverse_charge_supply_through_ecomm_operators(self):
        si = frappe.qb.DocType("Sales Invoice")
        si_item = frappe.qb.DocType("Sales Invoice Item")
        query = (
            frappe.qb.from_(si)
            .join(si_item)
            .on(si.name == si_item.parent)
            .select(
                IfNull(Sum(si_item.taxable_value), 0).as_("taxable_value"),
            )
        )
        query = self.get_query_with_conditions(si, query, si.billing_address_gstin)
        result = (
            query.where(si.is_reverse_charge == 1)
            .where(IfNull(si.ecommerce_gstin, "") != "")
            .run(as_dict=True)
        )
        total_taxable_value = flt(result[0]["taxable_value"], 2)

        self.report_dict["eco_dtls"]["eco_reg_sup"]["txval"] = total_taxable_value
        self.report_dict["sup_details"]["osup_det"]["txval"] -= total_taxable_value

    def get_outward_supply_details(self, doctype, reverse_charge=None):
        self.get_outward_tax_invoices(doctype, reverse_charge=reverse_charge)
        self.get_invoice_item_wise_tax_details(doctype)

    def get_invoice_item_wise_tax_details(self, doctype):
        docs = self.get_grouped_item_details(doctype)
        self.set_item_wise_tax_details(docs)

    def set_item_wise_tax_details(self, docs):
        self.invoice_item_wise_tax_details = {}

        for doc, details in docs.items():
            invoice_items = {}
            item_code_gst_treatment_map = {}

            for item in details["items"]:
                item_code = item.item_code or item.item_name
                gst_treatment = item.gst_treatment
                item_code_gst_treatment_map[item_code] = gst_treatment

                invoice_items.setdefault(gst_treatment, defaultdict(int))
                invoice_items[gst_treatment]["taxable_value"] += item.get(
                    "taxable_value", 0
                )

                if (
                    details.doctype == "Sales Invoice"
                    and doc in self.reverse_charge_invoices
                ):
                    continue

                for tax, tax_type in GST_TAX_TYPE_MAP.items():
                    invoice_items[gst_treatment][tax_type] += item.get(
                        f"{tax}_amount", 0
                    )

            self.invoice_item_wise_tax_details[doc] = invoice_items

    def get_grouped_item_details(self, doctype):
        item_details = self.get_outward_items(doctype)
        response = defaultdict(lambda: frappe._dict(items=[], doctype=doctype))

        # Group item details by parent document
        for item in item_details:
            response[item.parent]["items"].append(item)

        return response

    def get_outward_tax_invoices(self, doctype, reverse_charge=None):
        self.invoice_map = {}

        invoice = frappe.qb.DocType(doctype)
        fields = [
            invoice.name,
            invoice.gst_category,
            invoice.place_of_supply,
            invoice.is_reverse_charge,
        ]
        party_gstin = invoice.supplier_gstin

        if doctype == "Sales Invoice":
            fields.append(invoice.is_export_with_gst)
            party_gstin = invoice.billing_address_gstin

        query = frappe.qb.from_(invoice).select(*fields)
        query = self.get_query_with_conditions(invoice, query, party_gstin)

        if reverse_charge:
            query = query.where(invoice.is_reverse_charge == 1)

        invoice_details = query.orderby(invoice.name).run(as_dict=True)
        self.invoice_map = {d.name: d for d in invoice_details}
        self.reverse_charge_invoices = {
            d.name for d in invoice_details if d.is_reverse_charge
        }

    def set_advances_received_or_adjusted(self):
        """
        Section 3.1(a) of GSTR-3B also includes the difference of advances received and adjusted
        """

        def update_totals(data, totals, multiplier):
            for row in data:
                is_intra_state = row["place_of_supply"][:2] == self.company_gstin[:2]
                tax_amount = row["tax_amount"] * multiplier

                totals["txval"] += row.taxable_value * multiplier
                totals["iamt"] += 0 if is_intra_state else tax_amount
                totals["camt"] += (tax_amount / 2) if is_intra_state else 0
                totals["samt"] += (tax_amount / 2) if is_intra_state else 0
                totals["csamt"] += row.cess_amount * multiplier

        filters = frappe._dict(
            {
                "company": self.company,
                "company_gstin": self.company_gstin,
                "from_date": self.from_date,
                "to_date": self.to_date,
            }
        )

        totals = defaultdict(int)
        gst_accounts = get_gst_accounts_by_type(self.company, "Output")
        _class = GSTR11A11BData(filters, gst_accounts)

        for method, multiplier in (("get_11A_query", 1), ("get_11B_query", -1)):
            query = getattr(_class, method)()
            data = query.run(as_dict=True)
            update_totals(data, totals, multiplier)

        for key in totals:
            self.report_dict["sup_details"]["osup_det"][key] += totals[key]

    def get_query_with_conditions(self, invoice, query, party_gstin):
        return (
            query.where(invoice.docstatus == 1)
            .where(invoice.posting_date[self.from_date : self.to_date])
            .where(invoice.company == self.company)
            .where(invoice.company_gstin == self.gst_details.get("gstin"))
            .where(invoice.is_opening == "No")
            .where(invoice.company_gstin != IfNull(party_gstin, ""))
        )

    def get_outward_items(self, doctype):
        if not self.invoice_map:
            return {}

        tax_fields = ", ".join(f"{tax}_amount" for tax in GST_TAX_TYPE_MAP)

        item_details = frappe.db.sql(
            f"""
            SELECT
               {tax_fields}, item_code, item_name, parent, taxable_value, gst_treatment
            FROM
                `tab{doctype} Item`
            WHERE parent in ({", ".join(["%s"] * len(self.invoice_map))})
            """,
            tuple(self.invoice_map),
            as_dict=1,
        )

        return item_details

    def set_outward_taxable_supplies(self):
        inter_state_supply_details = {}
        gst_treatment_map = {
            "Nil-Rated": "osup_nil_exmp",
            "Exempted": "osup_nil_exmp",
            "Zero-Rated": "osup_zero",
            "Non-GST": "osup_nongst",
            "Taxable": "osup_det",
        }

        for inv, invoice_details in self.invoice_map.items():
            gst_treatment_details = self.invoice_item_wise_tax_details.get(inv, {})
            gst_category = invoice_details.get("gst_category")
            place_of_supply = (
                invoice_details.get("place_of_supply") or "00-Other Territory"
            )

            doc = frappe._dict(
                {
                    "gst_category": gst_category,
                    "place_of_supply": place_of_supply,
                    "company_gstin": self.gst_details.get("gstin"),
                }
            )

            is_inter_state = is_inter_state_supply(doc)

            for gst_treatment, details in gst_treatment_details.items():
                gst_treatment_section = gst_treatment_map.get(gst_treatment)
                section = self.report_dict["sup_details"][gst_treatment_section]

                taxable_value = details.get("taxable_value")

                # updating taxable value and tax value
                section["txval"] += taxable_value
                for key in section:
                    if key in VALUES_TO_UPDATE:
                        section[key] += details.get(key, 0)

                # section 3.2 details
                if not gst_treatment == "Taxable":
                    continue

                if (
                    gst_category
                    in [
                        "Unregistered",
                        "Registered Composition",
                        "UIN Holders",
                    ]
                    and is_inter_state
                ):
                    inter_state_supply_details.setdefault(
                        (gst_category, place_of_supply),
                        {
                            "txval": 0.0,
                            "pos": place_of_supply.split("-")[0],
                            "iamt": 0.0,
                        },
                    )

                    inter_state_supply_details[(gst_category, place_of_supply)][
                        "txval"
                    ] += taxable_value
                    inter_state_supply_details[(gst_category, place_of_supply)][
                        "iamt"
                    ] += details.get("iamt")

        self.set_inter_state_supply(inter_state_supply_details)

    def set_supplies_liable_to_reverse_charge(self):
        section = self.report_dict["sup_details"]["isup_rev"]
        for inv, invoice_details in self.invoice_map.items():
            gst_treatment_section = self.invoice_item_wise_tax_details.get(inv, {})
            for item in gst_treatment_section.values():
                section["txval"] += item.get("taxable_value")
                for key in section:
                    if key in VALUES_TO_UPDATE:
                        section[key] += item.get(key, 0)

    def set_inter_state_supply(self, inter_state_supply):
        inter_state_supply_map = {
            "Unregistered": "unreg_details",
            "Registered Composition": "comp_details",
            "UIN Holders": "uin_details",
        }

        for key, value in inter_state_supply.items():
            section = inter_state_supply_map.get(key[0])

            if section:
                self.report_dict["inter_sup"][section].append(value)

    def get_company_gst_details(self):
        if not self.company_gstin:
            frappe.throw(_("Please enter GSTIN for Company {0}").format(self.company))

        return {
            "gstin": self.company_gstin,
            "gst_state": next(
                (
                    key
                    for key, value in STATE_NUMBERS.items()
                    if value == self.company_gstin[:2]
                ),
                None,
            ),
        }

    def get_missing_field_invoices(self):
        missing_field_invoices = []

        for doctype in INVOICE_DOCTYPES:
            party_gstin = (
                "billing_address_gstin"
                if doctype == "Sales Invoice"
                else "supplier_gstin"
            )
            docnames = frappe.db.sql(
                f"""
                    SELECT name FROM `tab{doctype}`
                    WHERE docstatus = 1 and is_opening = 'No'
                    and posting_date between %s and %s
                    and company = %s and place_of_supply IS NULL
                    and company_gstin != IFNULL({party_gstin},"")
                    and gst_category != 'Overseas'
                """,
                (
                    self.from_date,
                    self.to_date,
                    self.company,
                ),
                as_dict=1,
            )  # nosec

            for d in docnames:
                missing_field_invoices.append(d.name)

        return ",".join(missing_field_invoices)


def get_address_state_map():
    return frappe._dict(
        frappe.get_all("Address", fields=["name", "gst_state"], as_list=1)
    )


def get_json(template):
    file_path = os.path.join(
        os.path.dirname(__file__), "{template}.json".format(template=template)
    )
    with open(file_path, "r") as f:
        return cstr(f.read())


def format_values(data, precision=2):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (int, float)):
                data[key] = flt(value, precision)
            elif isinstance(value, dict) or isinstance(value, list):
                format_values(value)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (int, float)):
                data[i] = flt(item, precision)
            elif isinstance(item, dict) or isinstance(item, list):
                format_values(item)

    return data


@frappe.whitelist()
def view_report(name):
    frappe.has_permission("GSTR 3B Report", throw=True)

    json_data = frappe.get_value("GSTR 3B Report", name, "json_output")
    return json.loads(json_data)


@frappe.whitelist()
def make_json(name):
    frappe.has_permission("GSTR 3B Report", throw=True)

    json_data = frappe.get_value("GSTR 3B Report", name, "json_output")
    file_name = "GST3B.json"
    frappe.local.response.filename = file_name
    frappe.local.response.filecontent = json_data
    frappe.local.response.type = "download"
