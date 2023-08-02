# Copyright (c) 2023, Resilient Tech and contributors
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

        self.update_docs_for_amendment()

    def update_docs_for_amendment(self):
        if self.match_status == "Amended" or not (
            self.other_return_period or self.is_amended
        ):
            return

        if self.is_amended:
            update_amended_doc(self)
        else:
            _update_doc_for_amendment(self)


def update_amended_doc(doc):
    # Handle case where is_amended is True
    original_inward = get_gst_inward_supply(
        bill_no=doc.original_bill_no,
        bill_date=doc.original_bill_date,
        supplier_gstin=doc.supplier_gstin,
        classification=get_other_classification(doc),
    )

    if not original_inward:
        # handle amendment from amendments where original is not available
        original_inward = get_gst_inward_supply(
            original_bill_no=doc.original_bill_no,
            original_bill_date=doc.original_bill_date,
            supplier_gstin=doc.supplier_gstin,
            classification=doc.classification,
            name=["!=", doc.name],
        )

    if not original_inward:
        return

    # handle future amendments
    if (
        original_inward.match_status == "Amended"
        and original_inward.link_name
        and original_inward.link_name != doc.name
        and doc.is_new()
    ):
        frappe.db.set_value(
            "GST Inward Supply", original_inward.name, "link_name", doc.name
        )

        # new original
        original_inward = get_gst_inward_supply(name=original_inward.link_name)

    if original_inward.match_status == "Amended":
        return

    # update_original_from_amended
    frappe.db.set_value(
        "GST Inward Supply",
        original_inward.name,
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
            "match_status": original_inward.match_status,
            "action": original_inward.action,
            "link_doctype": original_inward.link_doctype,
            "link_name": original_inward.link_name,
        }
    )

    if not doc.other_return_period:
        doc.other_return_period = original_inward.sup_return_period

    ensure_valid_match(doc, original_inward)


def _update_doc_for_amendment(doc):
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

    amended_inward = get_gst_inward_supply(
        original_bill_no=doc.bill_no,
        original_bill_date=doc.bill_date,
        supplier_gstin=doc.supplier_gstin,
        classification=get_other_classification(doc),
    )

    if not amended_inward:
        return

    # update_original_from_amended
    doc.update(
        {
            "link_doctype": "GST Inward Supply",
            "link_name": amended_inward.name,
        }
    )


def get_gst_inward_supply(**kwargs):
    frappe.db.get_value(
        "GST Inward Supply",
        filters=kwargs,
        fieldname=[
            "name",
            "match_status",
            "action",
            "link_doctype",
            "link_name",
            "sup_return_period",
        ],
        as_dict=True,
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
            title="Invalid Match",
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
    for original, amended in ORIGINAL_VS_AMENDED.items():
        if original != doc.classification:
            continue

        if doc.is_amended:
            return original

        return amended or original


def create_inward_supply(transaction):
    doctype = "GST Inward Supply"
    filters = {
        "bill_no": transaction.bill_no,
        "bill_date": transaction.bill_date,
        "classification": transaction.classification,
        "supplier_gstin": transaction.supplier_gstin,
    }

    if name := frappe.db.exists(doctype, filters):
        gst_inward_supply = frappe.get_doc(doctype, name)
    else:
        gst_inward_supply = frappe.new_doc(doctype)

    gst_inward_supply.update(transaction)
    return gst_inward_supply.save(ignore_permissions=True)
