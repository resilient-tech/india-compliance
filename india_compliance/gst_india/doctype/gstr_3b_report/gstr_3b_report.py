# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import calendar
import json
import os
from collections import defaultdict
from typing import ClassVar

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, get_first_day, get_last_day
from openpyxl.cell.cell import MergedCell

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.overrides.transaction import is_inter_state_supply
from india_compliance.gst_india.utils import (
    get_data_file_path,
    get_gst_accounts_by_type,
    get_period,
)
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr3b.gstr3b_data import (
    GSTR3BInvoices,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import (
    GSTR1Invoices,
    GSTR11A11BData,
)

VALUES_TO_UPDATE = ["iamt", "camt", "samt", "csamt"]

# Maps GSTR-3B sub-category labels to the 'ty' key in the JSON template (ITC Available)
ITC_AVAILABLE_SUB_CATEGORY_MAP = {
    "Import Of Goods": "IMPG",
    "Import Of Service": "IMPS",
    "ITC on Reverse Charge": "ISRC",
    "Input Service Distributor": "ISD",
    "All Other ITC": "OTH",
}

# Maps GSTR-3B ITC Reversed sub-category labels to the 'ty' key in the JSON template
ITC_REVERSED_SUB_CATEGORY_TY_MAP = {
    "As per rules 42 & 43 of CGST Rules and section 17(5)": "RUL",
    "Others": "OTH",
}

# GST categories that need to be reported in section 3.2 (inter-state supplies)
INTER_STATE_GST_CATEGORIES = frozenset({"Unregistered", "Registered Composition", "UIN Holders"})

# Maps invoice amount fields to JSON key names used in the ITC section
_ITC_FIELD_MAP = {
    "iamt": "igst_amount",
    "camt": "cgst_amount",
    "samt": "sgst_amount",
    "csamt": "cess_amount",
}

# Maps JSON tax keys to GSTR-1 invoice amount field names (cess = total_cess_amount)
_GSTR1_FIELD_MAP = {
    "iamt": "igst_amount",
    "camt": "cgst_amount",
    "samt": "sgst_amount",
    "csamt": "total_cess_amount",
}

# Maps ITC ineligible / reclaimed category labels to the 'ty' key in itc_inelg
# (consistent with avl_by_ty / rev_by_ty lookup pattern in process_itc)
_ITC_INELG_CATEGORY_TY_MAP = {
    "Ineligible ITC": "OTH",  # PoS-restricted ineligible  → itc_inelg ty=OTH
    "ITC Reclaimed": "RUL",  # Reclaim of earlier reversal → itc_inelg ty=RUL
}


class GSTR3BReport(Document):
    @property
    def filing_status(self):
        status = "Not Filed"
        if not (self.company_gstin and self.month_or_quarter and self.year):
            return status

        period = get_period(self.month_or_quarter, self.year)
        filters = {
            "gstin": self.company_gstin,
            "return_period": period,
            "return_type": "GSTR3B",
        }
        status = frappe.db.get_value("GST Return Log", filters, "filing_status")

        return status or "Not Filed"

    def validate(self):
        self.json_output = ""
        self.generation_status = "In Process"

        if self.enqueue_report:
            frappe.msgprint(_("Initiated report generation in background"), alert=True)
            frappe.enqueue_doc("GSTR 3B Report", self.name, "get_data", queue="long")
            return

        self.get_data()

    def get_data(self):
        try:
            if not self.company_gstin:
                frappe.throw(_("Please enter GSTIN for Company {0}").format(self.company))
            self.report_dict = json.loads(get_json("gstr_3b_report_template"))
            self.report_dict["gstin"] = self.company_gstin
            self.report_dict["ret_period"] = get_period(self.month_or_quarter, self.year)
            self.month_or_quarter_no = get_period(self.month_or_quarter)
            self.from_date = get_first_day(f"{cint(self.year)}-{self.month_or_quarter_no[0]}-01")
            self.to_date = get_last_day(f"{cint(self.year)}-{self.month_or_quarter_no[1]}-01")

            self._process_outward_supply_data()
            self._process_inward_supply_data()

            self.report_dict = format_values(self.report_dict)
            self.json_output = frappe.as_json(self.report_dict)
            self.generation_status = "Generated"

            if self.enqueue_report:
                self.db_set(
                    {
                        "json_output": self.json_output,
                        "generation_status": self.generation_status,
                    }
                )

        except Exception as e:
            self.generation_status = "Failed"
            self.db_set({"generation_status": self.generation_status})
            frappe.db.commit()  # nosemgrep
            raise e

        finally:
            frappe.publish_realtime("gstr3b_report_generation", doctype=self.doctype, docname=self.name)

    def _get_filters(self):
        return frappe._dict(
            {
                "company": self.company,
                "company_gstin": self.company_gstin,
                "from_date": self.from_date,
                "to_date": self.to_date,
                "filter_by": self.filter_by,
            }
        )

    def _process_outward_supply_data(self):
        """
        Tables 3.1 (outward supplies), 3.1.1 (e-commerce), 3.2 (inter-state),
        and 3.3 (advances) — all derived from Sales Invoice data.
        """
        self.process_outward_supplies()
        self.set_advances_received_or_adjusted()

    def _process_inward_supply_data(self):
        """
        Tables 3.1(d) (RC inward), 4 (ITC), and 5 (nil/exempt inward)
        — derived from Purchase Invoice, Bill of Entry, and Journal Entry.
        """
        gstr3b = GSTR3BInvoices(self._get_filters())
        pi_items = gstr3b.get_data("Purchase Invoice", group_by_invoice=False)

        self.process_reverse_charge_inward(pi_items)
        self.process_itc(gstr3b)
        self.process_inward_nil_exempt(pi_items)

    def process_outward_supplies(self):
        """
        Populate sections 3.1 (outward supply details), 3.1.1 (e-commerce
        supplies) and 3.2 (inter-state supplies) from Sales Invoice line-item
        data provided by GSTR1Invoices.

        Section 3.1 mapping:
          gst_treatment == "Nil-Rated" / "Exempted"  → osup_nil_exmp  (txval only)
          gst_treatment == "Non-GST"                  → osup_nongst    (txval only)
          gst_treatment == "Zero-Rated"               → osup_zero      (txval + iamt + csamt)
          gst_treatment == "Taxable" (non-RC)         → osup_det       (txval + all taxes)
          gst_treatment == "Taxable" (RC)             → osup_det       (txval only, no taxes)
          gst_treatment == "Taxable" (RC + eco GSTIN) → eco_reg_sup   (txval only, deducted from osup_det)
                                                         NOT reported in section 3.2 (no longer in 3.1(a))

        Section 3.1.1 e-commerce split (confirmed against Excel template v5.7):
          eco_reg_sup  — Row 23 — 3.1.1(ii):
              Registered SELLER's taxable value for supplies made through an ECO
              that is liable to pay GST u/s 9(5) on their behalf (RC invoices
              with ecommerce_gstin set).  Only txval is reported; taxes are paid
              by the ECO.  Correctly deducted from osup_det.
          eco_sup      — Row 22 — 3.1.1(i):
              Reported by the ECO OPERATOR itself for supplies on which it pays
              tax u/s 9(5).  This field is relevant only when the company filing
              the return IS an ECO operator (e.g. Ola, Zomato, Urban Company).
              Population of eco_sup for ECO operators is not yet implemented
              (same gap as the pre-refactor code).
        """
        gstr1 = GSTR1Invoices(self._get_filters())
        invoices = gstr1.get_invoices_for_item_wise_summary()

        inter_state_supply = {}
        eco_taxable_value = 0.0

        for invoice in invoices:
            gst_treatment = invoice.gst_treatment
            section_key = {
                "Nil-Rated": "osup_nil_exmp",
                "Exempted": "osup_nil_exmp",
                "Zero-Rated": "osup_zero",
                "Non-GST": "osup_nongst",
                "Taxable": "osup_det",
            }.get(gst_treatment)
            if not section_key:
                continue

            taxable_value = invoice.taxable_value or 0
            section = self.report_dict["sup_details"][section_key]
            section["txval"] += taxable_value

            if gst_treatment == "Taxable":
                if not invoice.is_reverse_charge:
                    for key, field in _GSTR1_FIELD_MAP.items():
                        section[key] += invoice.get(field) or 0

                if invoice.is_reverse_charge and invoice.ecommerce_gstin:
                    eco_taxable_value += taxable_value
                    continue  # eco-RC supplies deducted from 3.1(a); excluded from 3.2

                # Section 3.2 is "of the supplies shown in 3.1(a)" — only taxable
                # outward supplies (osup_det) are in scope.  Nil-Rated, Exempted,
                # Zero-Rated and Non-GST supplies must NOT appear in 3.2.
                self._update_inter_state_supply(invoice, taxable_value, inter_state_supply)

            elif gst_treatment == "Zero-Rated":
                for key in ("iamt", "csamt"):
                    section[key] += invoice.get(_GSTR1_FIELD_MAP[key]) or 0

        self.report_dict["eco_dtls"]["eco_reg_sup"]["txval"] = eco_taxable_value
        self.report_dict["sup_details"]["osup_det"]["txval"] -= eco_taxable_value

        self.set_inter_state_supply(inter_state_supply)

    def _update_inter_state_supply(self, invoice, taxable_value, inter_state_supply):
        """
        Collect inter-state supply data for section 3.2.
        Only Unregistered, Registered Composition and UIN Holder categories qualify.

        Note: eco-operator RC invoices (is_reverse_charge + ecommerce_gstin) are
        excluded by the caller — they are no longer part of 3.1(a) after being
        deducted into eco_reg_sup and must not contribute to section 3.2.
        """
        gst_category = invoice.gst_category
        if gst_category not in INTER_STATE_GST_CATEGORIES:
            return

        place_of_supply = invoice.place_of_supply
        if not place_of_supply:
            return

        doc = frappe._dict(
            {
                "doctype": "Sales Invoice",
                "gst_category": gst_category,
                "place_of_supply": place_of_supply,
                "company_gstin": invoice.company_gstin,
            }
        )

        if not is_inter_state_supply(doc):
            return

        key = (gst_category, place_of_supply)
        inter_state_supply.setdefault(
            key,
            {
                "txval": 0.0,
                "pos": place_of_supply.split("-")[0],
                "iamt": 0.0,
            },
        )
        inter_state_supply[key]["txval"] += taxable_value
        if not invoice.is_reverse_charge:
            inter_state_supply[key]["iamt"] += invoice.igst_amount or 0

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

    def process_reverse_charge_inward(self, pi_items):
        """
        Populate section 3.1(d) — inward supplies liable to reverse charge —
        from the pre-fetched Purchase Invoice item-level data, filtered by the
        is_reverse_charge flag on the invoice header.

        Using is_reverse_charge (the actual RC-liability flag set at voucher
        entry) is semantically correct for section 3.1(d): it covers all ITC
        sub-categories including "Import Of Service" and "All Other ITC" that
        the old itc_classification == "ITC on Reverse Charge" filter missed.
        It also prevents PIs that carry the wrong itc_classification from being
        included incorrectly.

        ITC Reversed duplicate entries — copies appended by get_processed_invoices
        for ITC-available + Section-17(5) invoices — are skipped to avoid
        double-counting taxable values and tax amounts.
        """
        section = self.report_dict["sup_details"]["isup_rev"]
        for item in pi_items:
            if not item.get("is_reverse_charge"):
                continue
            if item.get("invoice_category") == "ITC Reversed":
                continue
            # Nil/exempt/composition and non-GST items on an RC PI belong to
            # table 5 only (process_inward_nil_exempt).  Including them here
            # would double-count the same supply in both 3.1(d) and table 5.
            if item.get("invoice_category") in (
                "Composition Scheme, Exempted, Nil Rated",
                "Non-GST",
            ):
                continue
            section["txval"] += item.taxable_value or 0
            section["iamt"] += item.igst_amount or 0
            section["camt"] += item.cgst_amount or 0
            section["samt"] += item.sgst_amount or 0
            section["csamt"] += item.cess_amount or 0

    def set_advances_received_or_adjusted(self):
        """Section 3.1(a) of GSTR-3B also includes the difference of advances received and adjusted."""

        def update_totals(data, totals, multiplier):
            for row in data:
                is_intra_state = row["place_of_supply"][:2] == self.company_gstin[:2]
                tax_amount = row["tax_amount"] * multiplier

                totals["txval"] += row.taxable_value * multiplier
                totals["iamt"] += 0 if is_intra_state else tax_amount
                totals["camt"] += (tax_amount / 2) if is_intra_state else 0
                totals["samt"] += (tax_amount / 2) if is_intra_state else 0
                totals["csamt"] += row.cess_amount * multiplier

        totals = defaultdict(int)
        gst_accounts = get_gst_accounts_by_type(self.company, "Output")
        _class = GSTR11A11BData(self._get_filters(), gst_accounts)

        for method, multiplier in (("get_11A_query", 1), ("get_11B_query", -1)):
            query = getattr(_class, method)()
            data = query.run(as_dict=True)
            update_totals(data, totals, multiplier)

        for key in totals:
            self.report_dict["sup_details"]["osup_det"][key] += totals[key]

    def process_itc(self, gstr3b):
        """
        Populate table 4 — ITC eligible (4A), reversed (4B), net (4C) and
        ineligible (4D) — from GSTR3BInvoices.

        Category → JSON section mapping
        ─────────────────────────────────────────────────────────────
        ITC Available  → itc_avl       (ty determined by sub-category)
                         also adds to itc_net
        ITC Reversed   → itc_rev       (ty = RUL or OTH)
                         also subtracts from itc_net
        Ineligible ITC → itc_inelg OTH (PoS restricted)
        ITC Reclaimed  → itc_inelg RUL (reclaim of earlier reversal)
        ─────────────────────────────────────────────────────────────
        Note: GSTR3BInvoices duplicates a PI that is BOTH ITC-available
        AND Section-17(5) ineligible — once under "ITC Available" and
        once under "ITC Reversed".  This is intentional: the available
        amount adds to net ITC and itc_avl, while the reversed amount
        subtracts from net ITC and adds to itc_rev[RUL], matching the
        existing report behaviour.
        """
        all_invoices = []
        for doctype in ("Purchase Invoice", "Bill of Entry", "Journal Entry"):
            all_invoices.extend(gstr3b.get_data(doctype, group_by_invoice=True))

        itc_avl = self.report_dict["itc_elg"]["itc_avl"]
        itc_rev = self.report_dict["itc_elg"]["itc_rev"]
        net_itc = self.report_dict["itc_elg"]["itc_net"]
        itc_inelg = self.report_dict["itc_elg"]["itc_inelg"]

        # Build lookup dicts keyed by 'ty' for fast access
        avl_by_ty = {d["ty"]: d for d in itc_avl}
        rev_by_ty = {d["ty"]: d for d in itc_rev}
        inelg_by_ty = {d["ty"]: d for d in itc_inelg}

        for invoice in all_invoices:
            category = invoice.get("invoice_category")
            sub_category = invoice.get("invoice_sub_category")

            if category == "ITC Available":
                ty = ITC_AVAILABLE_SUB_CATEGORY_MAP.get(sub_category)
                if not ty:
                    frappe.logger().warning(
                        f"GSTR-3B: unknown ITC Available sub-category "
                        f"{sub_category!r} on {invoice.get('voucher_no')} "
                        f"— falling back to OTH (All Other ITC)"
                    )
                    ty = "OTH"
                if ty in avl_by_ty:
                    for key in VALUES_TO_UPDATE:
                        amount = invoice.get(_ITC_FIELD_MAP[key]) or 0
                        avl_by_ty[ty][key] += amount
                        net_itc[key] += amount

            elif category == "ITC Reversed":
                ty = ITC_REVERSED_SUB_CATEGORY_TY_MAP.get(sub_category)
                if ty is None:
                    frappe.logger().warning(
                        f"GSTR-3B: unknown ITC Reversed sub-category "
                        f"{sub_category!r} on {invoice.get('voucher_no')} "
                        f"— skipped from table 4B"
                    )
                    continue
                for key in VALUES_TO_UPDATE:
                    amount = invoice.get(_ITC_FIELD_MAP[key]) or 0
                    rev_by_ty[ty][key] += amount
                    net_itc[key] -= amount

            elif category in _ITC_INELG_CATEGORY_TY_MAP:
                ty = _ITC_INELG_CATEGORY_TY_MAP[category]
                entry = inelg_by_ty.get(ty)
                if entry is None:
                    frappe.logger().warning(
                        f"GSTR-3B: itc_inelg has no entry with ty={ty!r} "
                        f"— {invoice.get('voucher_no')} skipped from table 4D"
                    )
                    continue
                for key in VALUES_TO_UPDATE:
                    entry[key] += invoice.get(_ITC_FIELD_MAP[key]) or 0

    def process_inward_nil_exempt(self, pi_items):
        """
        Populate table 5 — inward nil/exempt (GST) and non-GST supplies —
        from the pre-fetched Purchase Invoice item-level data.

        GSTR3BInvoices.update_tax_values() sets `inter` and `intra` on each
        item for the "Composition Scheme, Exempted, Nil Rated" and "Non-GST"
        categories based on is_inter_state_supply(), mirroring the existing
        address-state logic in the old get_inward_nil_exempt().
        """
        isup_details = self.report_dict["inward_sup"]["isup_details"]
        gst_entry = next((d for d in isup_details if d["ty"] == "GST"), None)
        non_gst_entry = next((d for d in isup_details if d["ty"] == "NONGST"), None)
        if gst_entry is None or non_gst_entry is None:
            frappe.throw(
                _(
                    "GSTR-3B report template is missing required inward supply "
                    "entries (expected ty='GST' and ty='NONGST'). "
                    "Please regenerate the report or contact support."
                )
            )

        for invoice in pi_items:
            category = invoice.get("invoice_category")

            if category == "Composition Scheme, Exempted, Nil Rated":
                gst_entry["inter"] += invoice.get("inter") or 0
                gst_entry["intra"] += invoice.get("intra") or 0

            elif category == "Non-GST":
                non_gst_entry["inter"] += invoice.get("inter") or 0
                non_gst_entry["intra"] += invoice.get("intra") or 0


def get_json(template):
    file_path = os.path.join(os.path.dirname(__file__), f"{template}.json")
    with open(file_path) as f:  # nosemgrep
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
def view_report(name: str):
    frappe.has_permission("GSTR 3B Report", throw=True)

    json_data = frappe.get_value("GSTR 3B Report", name, "json_output")
    return json.loads(json_data)


@frappe.whitelist()
def make_json(name: str):
    frappe.has_permission("GSTR 3B Report", throw=True)

    json_data = frappe.get_value("GSTR 3B Report", name, "json_output")
    file_name = "GST3B.json"
    frappe.local.response.filename = file_name
    frappe.local.response.filecontent = json_data
    frappe.local.response.type = "download"


@frappe.whitelist()
def download_gstr3b_as_excel(name: str):
    """Download GSTR 3B report as Excel file"""
    frappe.has_permission("GSTR 3B Report", throw=True)
    json_data = frappe.get_value("GSTR 3B Report", name, "json_output")

    if not json_data:
        frappe.throw(_("Report data not found. Please generate the report."))

    data = json.loads(json_data)
    exporter = GSTR3BExcelExporter(data)
    exporter.generate_excel()


class GSTR3BExcelExporter:
    """
    Export GSTR-3B data to Excel format using the official template.

    This class handles data transformation and mapping from JSON to Excel cells
    following the official GSTR-3B offline utility format.
    """

    TEMPLATE_FILE: ClassVar[str] = get_data_file_path("gstr3b_excel_utility_v5.7.xlsx")
    WORKSHEET_NAME: ClassVar[str] = "GSTR-3B"

    _STATE_CODE_TO_NAME: ClassVar[dict] = {code: state for state, code in STATE_NUMBERS.items()}

    # Row mappings for each section (consistent with JSON keys)
    ROWS: ClassVar[dict] = {
        # Header info
        "gstin": 5,
        "year": 5,
        "month": 6,
        # Section 3.1 - Outward supplies
        "osup_det": 11,
        "osup_zero": 12,
        "osup_nil_exmp": 13,
        "isup_rev": 14,
        "osup_nongst": 15,
        "eco_reg_sup": 23,
        # Section 3.2 - Inter-state
        "inter_state_start": 88,
        # Section 4 - ITC
        "itc_import_goods": 31,
        "itc_import_services": 32,
        "itc_reverse_charge": 33,
        "itc_isd": 34,
        "itc_others": 35,
        "itc_reversed_rules": 37,
        "itc_reversed_others": 38,
        "itc_reclaimed": 41,
        "itc_ineligible": 42,
        # Section 5 - Inward supplies
        "inward_gst": 48,
        "inward_non_gst": 49,
    }

    HEADER_COLUMNS: ClassVar[dict] = {
        "gstin": 3,
        "year": 7,
        "month": 7,
    }

    # Section 3.1 - Tax columns
    TAX_COLUMNS: ClassVar[dict] = {
        "txval": 3,
        "iamt": 4,
        "camt": 5,
        "csamt": 7,
    }

    # Section 4 - ITC columns
    ITC_COLUMNS: ClassVar[dict] = {
        "iamt": 3,
        "camt": 4,
        "csamt": 6,
    }

    # Section 5 - Inward supplies columns
    INWARD_COLUMNS: ClassVar[dict] = {
        "inter": 4,
        "intra": 5,
    }

    # ITC type mappings based on 'ty' field in JSON
    ITC_AVAILABLE_TYPES: ClassVar[dict] = {
        "IMPG": "itc_import_goods",
        "IMPS": "itc_import_services",
        "ISRC": "itc_reverse_charge",
        "ISD": "itc_isd",
        "OTH": "itc_others",
    }

    ITC_REVERSED_TYPES: ClassVar[dict] = {
        "RUL": "itc_reversed_rules",
        "OTH": "itc_reversed_others",
    }

    INWARD_SUPPLY_TYPES: ClassVar[dict] = {
        "GST": "inward_gst",
        "NONGST": "inward_non_gst",
    }

    ITC_INELIGIBLE_TYPES: ClassVar[dict] = {
        "RUL": "itc_reclaimed",
        "OTH": "itc_ineligible",
    }

    COLUMN_SETS: ClassVar[dict] = {
        "tax": ["txval", "iamt", "camt", "csamt"],
        "itc": ["iamt", "camt", "csamt"],
        "import_itc": ["iamt", "csamt"],
        "inward": ["inter", "intra"],
        "zero_rated": ["txval", "iamt", "csamt"],
        "taxable_only": ["txval"],
    }

    def __init__(self, data):
        self.data = data
        self.gstin = data.get("gstin")
        self.worksheet = None
        self.month = None
        self.fiscal_year = None

    def generate_excel(self):
        """Generate and export Excel file"""
        if not os.path.exists(self.TEMPLATE_FILE):
            frappe.throw(_("GSTR 3B Excel template not found"))

        excel = ExcelExporter(file=self.TEMPLATE_FILE)
        self._update_worksheet(excel)

        file_name = self._get_filename()
        excel.export(file_name)

    def _get_filename(self):
        return f"GSTR-3B-{self.gstin}-{self.month}-{self.fiscal_year}"

    def _update_worksheet(self, excel):
        self.worksheet = excel.wb[self.WORKSHEET_NAME]

        self._set_header_info()
        self._set_outward_supplies()
        self._set_ecommerce_supplies()
        self._set_inter_state_supplies()
        self._set_itc_details()
        self._set_inward_supplies()

    def _set_header_info(self):
        """Set header information"""
        period = self.data.get("ret_period", "")
        if not period or len(period) < 6:
            return

        try:
            month_num = int(period[:2])
            calendar_year = int(period[2:6])
        except ValueError:
            return

        self.month = calendar.month_name[month_num]
        self.fiscal_year = self._get_fiscal_year(month_num, calendar_year)

        self._set_cell(self.ROWS["gstin"], self.HEADER_COLUMNS["gstin"], self.gstin)
        self._set_cell(self.ROWS["year"], self.HEADER_COLUMNS["year"], self.fiscal_year)
        self._set_cell(self.ROWS["month"], self.HEADER_COLUMNS["month"], self.month)

    def _get_fiscal_year(self, month_num, calendar_year):
        if month_num >= 4:
            fiscal_year_start = str(calendar_year)
            fiscal_year_end = str(calendar_year + 1)[2:]
        else:
            fiscal_year_start = str(calendar_year - 1)
            fiscal_year_end = str(calendar_year)[2:]

        return f"{fiscal_year_start}-{fiscal_year_end}"

    def _set_outward_supplies(self):
        sup_details = self.data.get("sup_details", {})

        section_mappings = [
            ("osup_det", "tax"),
            ("osup_zero", "zero_rated"),
            ("osup_nil_exmp", "taxable_only"),
            ("isup_rev", "tax"),
            ("osup_nongst", "taxable_only"),
        ]

        for json_key, column_set in section_mappings:
            data = sup_details.get(json_key, {})
            self._set_section_data(json_key, data, column_set)

    def _set_ecommerce_supplies(self):
        eco_dtls = self.data.get("eco_dtls", {})
        self._set_section_data("eco_reg_sup", eco_dtls.get("eco_reg_sup", {}), "taxable_only")

    def _set_inter_state_supplies(self):
        inter_sup = self.data.get("inter_sup", {})
        pos_data = self._group_by_place_of_supply(inter_sup)

        if not pos_data:
            return

        for i, (pos, data) in enumerate(sorted(pos_data.items())):
            row = self.ROWS["inter_state_start"] + i
            self._set_inter_state_row(row, pos, data)

    def _group_by_place_of_supply(self, inter_sup):
        pos_data = {}
        categories = {
            "unreg_details": "unreg",
            "comp_details": "comp",
            "uin_details": "uin",
        }

        for category_key, category_name in categories.items():
            for item in inter_sup.get(category_key, []):
                state_code = item.get("pos", "00")
                state_name = self._format_place_of_supply(state_code)

                if state_name not in pos_data:
                    pos_data[state_name] = {
                        "unreg": {"txval": 0, "iamt": 0},
                        "comp": {"txval": 0, "iamt": 0},
                        "uin": {"txval": 0, "iamt": 0},
                    }

                pos_data[state_name][category_name]["txval"] += flt(item.get("txval", 0), 2)
                pos_data[state_name][category_name]["iamt"] += flt(item.get("iamt", 0), 2)

        return pos_data

    def _set_inter_state_row(self, row, pos, data):
        self._set_cell(row, 2, pos)

        categories = [
            ("unreg", 3, 4),
            ("comp", 5, 6),
            ("uin", 7, 8),
        ]

        for category, val_col, tax_col in categories:
            category_data = data.get(category, {"txval": 0, "iamt": 0})
            self._set_cell(row, val_col, category_data["txval"])
            self._set_cell(row, tax_col, category_data["iamt"])

    def _set_itc_details(self):
        itc_elg = self.data.get("itc_elg", {})
        self._populate_itc_sections(itc_elg.get("itc_avl", []), self.ITC_AVAILABLE_TYPES)
        self._populate_itc_sections(itc_elg.get("itc_rev", []), self.ITC_REVERSED_TYPES)
        self._populate_itc_sections(itc_elg.get("itc_inelg", []), self.ITC_INELIGIBLE_TYPES)

    def _populate_itc_sections(self, itc_entries, type_mapping):
        for itc_entry in itc_entries:
            itc_type = itc_entry.get("ty", "")
            if itc_type not in type_mapping:
                continue

            row_key = type_mapping[itc_type]
            column_set = "import_itc" if itc_type in ["IMPG", "IMPS"] else "itc"
            self._set_section_data(row_key, itc_entry, column_set, self.ITC_COLUMNS)

    def _set_inward_supplies(self):
        inward_sup = self.data.get("inward_sup", {})
        isup_details = inward_sup.get("isup_details", [])

        for supply_data in isup_details:
            supply_type = supply_data.get("ty")
            if supply_type in self.INWARD_SUPPLY_TYPES:
                row_key = self.INWARD_SUPPLY_TYPES[supply_type]
                self._set_section_data(row_key, supply_data, "inward", self.INWARD_COLUMNS)

    def _set_section_data(self, row_key, data, column_set, columns_dict=None):
        row = self.ROWS[row_key]
        columns = self.COLUMN_SETS[column_set]
        mapping = columns_dict or self.TAX_COLUMNS

        for key in columns:
            if key in mapping:
                value = flt(data.get(key, 0), 2)
                self._set_cell(row, mapping[key], value)

    def _set_cell(self, row, column, value):
        cell = self.worksheet.cell(row, column)
        if not isinstance(cell, MergedCell):
            cell.value = value

    @classmethod
    def _format_place_of_supply(cls, state_code):
        formatted_code = state_code.zfill(2)
        state_name = cls._STATE_CODE_TO_NAME.get(formatted_code, "Other Territory")
        return f"{formatted_code}-{state_name}"
