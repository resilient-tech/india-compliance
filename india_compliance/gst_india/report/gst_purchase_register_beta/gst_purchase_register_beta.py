# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
from pypika import Order

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils import cint

SECTION_MAPPING = {
    "Eligible ITC": {
        "ITC Available": [
            "Import Of Goods",
            "Import Of Service",
            "ITC on Reverse Charge",
            "Input Service Distributor",
            "All Other ITC",
        ],
    },
    "Values of exempt, nil rated and non-GST inward supplies": {
        "Composition Scheme, Exempted, Nil Rated": [
            "Composition Scheme, Exempted, Nil Rated",
        ],
        "Non-GST": ["Non-GST"],
    },
}


def execute(filters: dict | None = None):
    filters = frappe._dict(filters or {})
    _class = GSTPurchaseRegisterBeta(filters)

    if filters.get("summary_by") == "Overview":
        data = _class.get_overview(filters, SECTION_MAPPING[filters.sub_section])
        columns = _class.get_columns(filters)

    else:
        data = _class.get_data(filters)
        columns = _class.get_columns(filters)

    return columns, data


class GSTPurchaseRegisterBeta:
    AMOUNT_FIELDS = {
        "iamt": 0,
        "camt": 0,
        "samt": 0,
        "csamt": 0,
    }

    def __init__(self, filters=None):
        self.filters = filters or {}
        self.company_gstin = self.filters.company_gstin

    def get_data(self, filters):
        doc = frappe.qb.DocType("Purchase Invoice")
        doc_item = frappe.qb.DocType("Purchase Invoice Item")

        query = (
            frappe.qb.from_(doc)
            .inner_join(doc_item)
            .on(doc.name == doc_item.parent)
            .select(
                doc.supplier,
                doc.supplier_gstin,
                doc.supplier_address,
                doc.place_of_supply,
                doc.name.as_("invoice_no"),
                doc.posting_date,
                doc.grand_total.as_("invoice_total"),
                doc.itc_classification,
                doc.gst_category,
                IfNull(doc_item.gst_treatment, "Not Defined").as_("gst_treatment"),
                (doc.itc_integrated_tax).as_("iamt"),
                (doc.itc_central_tax).as_("camt"),
                (doc.itc_state_tax).as_("samt"),
                (doc.itc_cess_amount).as_("csamt"),
            )
            .where(doc.docstatus == 1)
            .groupby(doc.name)
            .orderby(doc.name, order=Order.desc)
        )

        if filters.get("company"):
            query = query.where(doc.company == filters.company)

        if filters.get("date_range"):
            from_date = filters.date_range[0]
            to_date = filters.date_range[1]

            query = query.where(doc.posting_date >= from_date)
            query = query.where(doc.posting_date <= to_date)

        data = query.run(as_dict=True)

        self.set_invoice_sub_category(data, filters.sub_section, filters.company_gstin)

        if filters.get("invoice_sub_category"):
            data = [
                d
                for d in data
                if d.invoice_sub_category == filters.invoice_sub_category
            ]

        return data

    def get_columns(self, filters):
        base_columns = [
            {
                "fieldname": "invoice_no",
                "label": _("Invoice Number"),
                "fieldtype": "Link",
                "options": "Purchase Invoice",
                "width": 180,
            },
            {
                "fieldname": "supplier",
                "label": _("Supplier"),
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "fieldname": "posting_date",
                "label": _("Posting Date"),
                "fieldtype": "Date",
                "width": 90,
            },
            {
                "fieldname": "invoice_total",
                "label": _("Invoice Total"),
                "fieldtype": "Data",
                "width": 90,
            },
            {
                "fieldname": "gst_treatment",
                "label": _("GST Treatment"),
                "fieldtype": "Data",
                "width": 90,
            },
            {
                "fieldname": "samt",
                "label": _("State Tax"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "iamt",
                "label": _("Integrated Tax"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "camt",
                "label": _("Central Tax"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "csamt",
                "label": _("CESS Amount"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "invoice_sub_category",
                "label": _("Invoice Sub Category"),
                "fieldtype": "Data",
                "width": 90,
            },
        ]

        if filters.get("summary_by") == "Overview":
            overview_columns = [
                {"label": _("Description"), "fieldname": "description", "width": "240"},
                {
                    "label": _("No. of records"),
                    "fieldname": "no_of_records",
                    "width": "120",
                    "fieldtype": "Int",
                },
                {
                    "fieldname": "samt",
                    "label": _("State Tax"),
                    "fieldtype": "Currency",
                    "width": 90,
                },
                {
                    "fieldname": "iamt",
                    "label": _("Integrated Tax"),
                    "fieldtype": "Currency",
                    "width": 90,
                },
                {
                    "fieldname": "camt",
                    "label": _("Central Tax"),
                    "fieldtype": "Currency",
                    "width": 90,
                },
                {
                    "fieldname": "csamt",
                    "label": _("CESS Amount"),
                    "fieldtype": "Currency",
                    "width": 90,
                },
            ]
            return overview_columns

        return base_columns

    def get_overview(self, filters, mapping):
        final_summary = []
        sub_category_summary = self.get_sub_category_summary(filters, mapping)

        for category, sub_categories in mapping.items():
            category_summary = {
                "description": category,
                "no_of_records": 0,
                "indent": 0,
                **self.AMOUNT_FIELDS,
            }
            final_summary.append(category_summary)

            for sub_category in sub_categories:
                sub_category_row = sub_category_summary[sub_category]
                category_summary["no_of_records"] += sub_category_row["no_of_records"]

                for key in self.AMOUNT_FIELDS:
                    category_summary[key] += sub_category_row[key]

                final_summary.append(sub_category_row)

        return final_summary

    def get_sub_category_summary(self, filters, mapping):
        invoices = self.get_data(filters)
        sub_categories = []
        for category in mapping:
            sub_categories.extend(mapping[category])

        summary = {
            category: {
                "description": category,
                "no_of_records": 0,
                "indent": 1,
                "unique_records": set(),
                **self.AMOUNT_FIELDS,
            }
            for category in sub_categories
        }

        def _update_summary_row(row, sub_category_field="invoice_sub_category"):
            if row.get(sub_category_field) not in sub_categories:
                return

            summary_row = summary[row.get(sub_category_field)]

            for key in self.AMOUNT_FIELDS:
                summary_row[key] += row[key]

            summary_row["unique_records"].add(row.invoice_no)

        for row in invoices:
            _update_summary_row(row)

        for summary_row in summary.values():
            summary_row["no_of_records"] = len(summary_row["unique_records"])

        return summary

    def set_invoice_sub_category(self, data, sub_section, company_gstin):
        if sub_section == "Eligible ITC":
            for invoice in data:
                invoice.invoice_sub_category = invoice.itc_classification

        else:
            address_state_map = frappe._dict(
                frappe.get_all(
                    "Address", fields=["name", "gst_state_number"], as_list=1
                )
            )

            state = cint(company_gstin[0:2])

            for invoice in data:
                place_of_supply = cint(invoice.place_of_supply[0:2]) or state

                invoice_sub_category = ""

                if invoice.gst_category == "Registered Composition":
                    supplier_state = cint(invoice.supplier_gstin[0:2])
                else:
                    supplier_state = (
                        cint(address_state_map.get(invoice.supplier_address)) or state
                    )
                intra, inter = 0, 0
                taxable_value = invoice.taxable_value

                if (
                    invoice.gst_treatment in ["Nil-Rated", "Exempted"]
                    or invoice.get("gst_category") == "Registered Composition"
                ):
                    invoice_sub_category = "Composition Scheme, Exempted, Nil Rated"

                elif invoice.gst_treatment == "Non-GST":
                    invoice_sub_category = "Non GST Supply"

                if supplier_state == place_of_supply:
                    intra = taxable_value
                else:
                    inter = taxable_value

                invoice.invoice_sub_category = invoice_sub_category
                invoice.intra = intra
                invoice.inter = inter
