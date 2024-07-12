# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import json
import os

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import DatePart
from frappe.query_builder.functions import Extract, IfNull, Sum
from frappe.utils import cstr, flt, get_date_str, get_first_day, get_last_day

from india_compliance.gst_india.constants import INVOICE_DOCTYPES
from india_compliance.gst_india.overrides.transaction import is_inter_state_supply
from india_compliance.gst_india.report.gstr_3b_details.gstr_3b_details import (
    IneligibleITC,
)

VALUES_TO_UPDATE = ["iamt", "camt", "samt", "csamt"]


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
            self.report_dict["ret_period"] = get_period(self.month, self.year)
            self.month_no = get_period(self.month)

            self.get_outward_supply_details("Sales Invoice")
            self.set_outward_taxable_supplies()

            self.get_outward_supply_details("Purchase Invoice", reverse_charge=True)
            self.set_supplies_liable_to_reverse_charge()

            itc_details = self.get_itc_details()
            self.set_itc_details(itc_details)
            self.get_itc_reversal_entries()
            inward_nil_exempt = self.get_inward_nil_exempt(
                self.gst_details.get("gst_state")
            )
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
            self.company, self.gst_details.get("gstin"), self.month_no, self.year
        ).get_for_purchase(
            "ITC restricted due to PoS rules", group_by="ineligibility_reason"
        )

        self.process_ineligible_credit(ineligible_credit)

    def update_itc_reversal_for_purchase_us_17_4(self):
        ineligible_credit = IneligibleITC(
            self.company, self.gst_details.get("gstin"), self.month_no, self.year
        ).get_for_purchase(
            "Ineligible As Per Section 17(5)", group_by="ineligibility_reason"
        )

        self.process_ineligible_credit(ineligible_credit)

    def update_itc_reversal_from_bill_of_entry(self):
        ineligible_credit = IneligibleITC(
            self.company, self.gst_details.get("gstin"), self.month_no, self.year
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
        gst_tax_type_to_key_map = {
            "sgst": "samt",
            "cgst": "camt",
            "igst": "iamt",
            "cess": "csamt",
            "cess_non_advol": "csamt",
        }

        for entry in reversal_entries:
            if entry.ineligibility_reason == "As per rules 42 & 43 of CGST Rules":
                index = 0
            else:
                index = 1

            tax_amount_key = gst_tax_type_to_key_map.get(entry.gst_tax_type)
            self.report_dict["itc_elg"]["itc_rev"][index][
                tax_amount_key
            ] += entry.amount
            net_itc[tax_amount_key] -= entry.amount

    def get_itc_details(self):
        itc_amounts = frappe.db.sql(
            """
            SELECT itc_classification, sum(itc_integrated_tax) as itc_integrated_tax,
            sum(itc_central_tax) as itc_central_tax,
            sum(itc_state_tax) as itc_state_tax,
            sum(itc_cess_amount) as itc_cess_amount
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
            and is_opening = 'No'
            and company_gstin != IFNULL(supplier_gstin, "")
            and month(posting_date) = %s and year(posting_date) = %s and company = %s
            and company_gstin = %s
            GROUP BY itc_classification
        """,
            (self.month_no, self.year, self.company, self.gst_details.get("gstin")),
            as_dict=1,
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
        boe_taxes = frappe.qb.DocType("Bill of Entry Taxes")

        def _get_tax_amount(account_type):
            return (
                frappe.qb.from_(boe)
                .select(Sum(boe_taxes.tax_amount))
                .join(boe_taxes)
                .on(boe_taxes.parent == boe.name)
                .where(
                    boe.posting_date.between(
                        get_date_str(get_first_day(f"{self.year}-{self.month_no}-01")),
                        get_date_str(get_last_day(f"{self.year}-{self.month_no}-01")),
                    )
                    & boe.company_gstin.eq(self.gst_details.get("gstin"))
                    & boe.docstatus.eq(1)
                    & boe_taxes.gst_tax_type.eq(account_type)
                )
                .run()
            )[0][0] or 0

        igst, cess = _get_tax_amount("igst"), _get_tax_amount("cess")
        itc_details.setdefault("Import Of Goods", {"iamt": 0, "csamt": 0})
        itc_details["Import Of Goods"]["iamt"] += igst
        itc_details["Import Of Goods"]["csamt"] += cess

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
            month(p.posting_date) = %s and year(p.posting_date) = %s
            and p.company = %s and p.company_gstin = %s
            """,
            (self.month_no, self.year, self.company, self.gst_details.get("gstin")),
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
        item_details = self.get_outward_items(doctype)
        tax_details = self.get_outward_tax_details(doctype)
        docs = self.combine_item_and_taxes(doctype, item_details, tax_details)

        self.set_item_wise_tax_details(docs)

    def set_item_wise_tax_details(self, docs):
        self.invoice_item_wise_tax_details = {}
        item_wise_details = {}
        gst_tax_type_map = {
            "cgst": "camt",
            "sgst": "samt",
            "igst": "iamt",
            "cess": "csamt",
            "cess_non_advol": "csamt",
        }

        item_defaults = frappe._dict(
            {
                "camt": 0,
                "samt": 0,
                "iamt": 0,
                "csamt": 0,
            }
        )

        # Process tax and item details
        for doc, details in docs.items():
            item_wise_details[doc] = {}
            invoice_items = {}
            item_code_gst_treatment_map = {}

            # Initialize invoice items with default values
            for item in details["items"]:
                item_code_gst_treatment_map[item.item_code or item.item_name] = (
                    item.gst_treatment
                )
                invoice_items.setdefault(
                    item.gst_treatment,
                    {
                        "taxable_value": 0,
                        **item_defaults,
                    },
                )

                invoice_items[item.gst_treatment]["taxable_value"] += item.get(
                    "taxable_value", 0
                )

            # Process tax details
            for tax in details["taxes"]:
                gst_tax_type = gst_tax_type_map.get(tax.gst_tax_type)

                if not gst_tax_type:
                    continue

                if tax.item_wise_tax_detail:
                    try:
                        item_wise_detail = json.loads(tax.item_wise_tax_detail)
                        for item_code, tax_amounts in item_wise_detail.items():
                            gst_treatment = item_code_gst_treatment_map.get(item_code)
                            invoice_items[gst_treatment][gst_tax_type] += tax_amounts[1]

                    except ValueError:
                        continue

            item_wise_details[doc].update(invoice_items)

        self.invoice_item_wise_tax_details = item_wise_details

    def combine_item_and_taxes(self, doctype, item_details, tax_details):
        response = frappe._dict()

        # Group tax details by parent document
        for tax in tax_details:
            if tax.parent not in response:
                response[tax.parent] = frappe._dict(taxes=[], items=[], doctype=doctype)

            response[tax.parent]["taxes"].append(tax)

        # Group item details by parent document
        for item in item_details:
            if item.parent not in response:
                response[item.parent] = frappe._dict(
                    taxes=[], items=[], doctype=doctype
                )

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

    def get_query_with_conditions(self, invoice, query, party_gstin):
        return (
            query.where(invoice.docstatus == 1)
            .where(Extract(DatePart.month, invoice.posting_date).eq(self.month_no))
            .where(Extract(DatePart.year, invoice.posting_date).eq(self.year))
            .where(invoice.company == self.company)
            .where(invoice.company_gstin == self.gst_details.get("gstin"))
            .where(invoice.is_opening == "No")
            .where(invoice.company_gstin != IfNull(party_gstin, ""))
        )

    def get_outward_items(self, doctype):
        if not self.invoice_map:
            return {}

        item_details = frappe.db.sql(
            f"""
            SELECT
                item_code, item_name, parent, taxable_value, gst_treatment
            FROM
                `tab{doctype} Item`
            WHERE parent in ({", ".join(["%s"] * len(self.invoice_map))})
            """,
            tuple(self.invoice_map),
            as_dict=1,
        )

        return item_details

    def get_outward_tax_details(self, doctype):
        if not self.invoice_map:
            return {}

        condition = self.get_reverse_charge_invoice_condition(doctype)

        tax_template = f"{doctype.split()[0]} Taxes and Charges"
        tax_details = frappe.db.sql(
            f"""
            SELECT
                parent, item_wise_tax_detail, gst_tax_type
            FROM `tab{tax_template}`
            WHERE
                parenttype = %s and docstatus = 1
                and parent in ({", ".join(["%s"] * len(self.invoice_map))})
                {condition}
            ORDER BY account_head
            """,
            (doctype, *self.invoice_map.keys()),
            as_dict=1,
        )

        return tax_details

    def get_reverse_charge_invoice_condition(self, doctype):
        condition = ""
        if doctype == "Sales Invoice" and self.reverse_charge_invoices:
            condition = f""" and parent not in ({', '.join([f'"{invoice}"' for invoice in self.reverse_charge_invoices])})"""

        return condition

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
        gst_details = frappe.get_all(
            "Address",
            fields=["gstin", "gst_state", "gst_state_number"],
            filters={"name": self.company_address},
        )

        if gst_details:
            return gst_details[0]
        else:
            frappe.throw(
                _("Please enter GSTIN and state for the Company Address {0}").format(
                    self.company_address
                )
            )

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
                    and month(posting_date) = %s and year(posting_date) = %s
                    and company = %s and place_of_supply IS NULL
                    and company_gstin != IFNULL({party_gstin},"")
                    and gst_category != 'Overseas'
                """,
                (self.month_no, self.year, self.company),
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


def get_period(month, year=None):
    month_no = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }.get(month)

    if year:
        return str(month_no).zfill(2) + str(year)
    else:
        return month_no


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
