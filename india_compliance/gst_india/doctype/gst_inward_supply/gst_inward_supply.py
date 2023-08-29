# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_link_to_form

from india_compliance.gst_india.constants import ORIGINAL_VS_AMENDED


class GSTInwardSupply(Document):
    def before_save(self):
        if self.classification.endswith("A"):
            self.is_amended = True

        if self.gstr_1_filing_date:
            self.gstr_1_filled = True

        if self.match_status != "Amended" and (
            self.other_return_period or self.is_amended
        ):
            update_docs_for_amendment(self)


def create_inward_supply(transaction):
    filters = {
        "bill_no": transaction.bill_no,
        "bill_date": transaction.bill_date,
        "classification": transaction.classification,
        "supplier_gstin": transaction.supplier_gstin,
    }

    if name := frappe.get_value("GST Inward Supply", filters):
        gst_inward_supply = frappe.get_doc("GST Inward Supply", name)
    else:
        gst_inward_supply = frappe.new_doc("GST Inward Supply")

    gst_inward_supply.update(transaction)
    return gst_inward_supply.save(ignore_permissions=True)


def update_docs_for_amendment(doc):
    fields = [
        "name",
        "match_status",
        "action",
        "link_doctype",
        "link_name",
        "sup_return_period",
    ]
    if doc.is_amended:
        original = frappe.db.get_value(
            "GST Inward Supply",
            filters={
                "bill_no": doc.original_bill_no,
                "bill_date": doc.original_bill_date,
                "supplier_gstin": doc.supplier_gstin,
                "classification": get_other_classification(doc),
            },
            fieldname=fields,
            as_dict=True,
        )
        if not original:
            # handle amendment from amendments where original is not available
            original = frappe.db.get_value(
                "GST Inward Supply",
                filters={
                    "original_bill_no": doc.original_bill_no,
                    "original_bill_date": doc.original_bill_date,
                    "supplier_gstin": doc.supplier_gstin,
                    "classification": doc.classification,
                    "name": ["!=", doc.name],
                },
                fieldname=fields,
                as_dict=True,
            )
            if not original:
                return

        # handle future amendments
        if (
            original.match_status == "Amended"
            and original.link_name
            and original.link_name != doc.name
            and doc.is_new()
        ):
            frappe.db.set_value(
                "GST Inward Supply", original.name, "link_name", doc.name
            )

            # new original
            original = frappe.db.get_value(
                "GST Inward Supply", original.link_name, fields
            )

        if original.match_status == "Amended":
            return

        # update_original_from_amended
        frappe.db.set_value(
            "GST Inward Supply",
            original.name,
            {
                "match_status": "Amended",
                "action": "No Action",
                "link_doctype": "GST Inward Supply",
                "link_name": doc.name,
            },
        )

        # update_amended_from_original
        doc.update(
            {
                "match_status": original.match_status,
                "action": original.action,
                "link_doctype": original.link_doctype,
                "link_name": original.link_name,
            }
        )
        if not doc.other_return_period:
            doc.other_return_period = original.sup_return_period

        ensure_valid_match(doc, original)

    else:
        # Handle case where original is imported after amended
        ensure_valid_match(doc, doc)
        if doc.match_status == "Amended":
            return

        doc.update(
            {
                "match_status": "Amended",
                "action": "No Action",
            }
        )
        amended = frappe.db.get_value(
            "GST Inward Supply",
            filters={
                "original_bill_no": doc.bill_no,
                "original_bill_date": doc.bill_date,
                "supplier_gstin": doc.supplier_gstin,
                "classification": get_other_classification(doc),
            },
            fieldname=fields,
            as_dict=True,
        )

        if not amended:
            return

        # update_original_from_amended
        doc.update(
            {
                "link_doctype": "GST Inward Supply",
                "link_name": amended.name,
            }
        )


def ensure_valid_match(doc, original):
    """
    Where receiver GSTIN is amended, company cannot claim credit for the original document.
    """

    if doc.amendment_type != "Receiver GSTIN Amended":
        return

    if original.link_doctype:
        frappe.msgprint(
            _(
                "You have claimend credit for {0} {1}  against GST Inward Supply {2} where receiver GSTIN is amended. The same has been reversed."
            ).format(
                original.link_doctype,
                get_link_to_form(original.link_doctype, original.link_name),
                get_link_to_form("GST Inward Supply", original.name),
            ),
            title=_("Invalid Match"),
        )

    doc.update(
        {
            "match_status": "Amended",
            "action": "No Action",
            "link_doctype": None,
            "link_name": None,
        }
    )


def get_other_classification(doc):
    if doc.is_amended:
        for row in ORIGINAL_VS_AMENDED:
            if row["original"] in doc.classification:
                return row["original"]

    for row in ORIGINAL_VS_AMENDED:
        if row["original"] == doc.classification:
            return row["amended"] or row["original"]
