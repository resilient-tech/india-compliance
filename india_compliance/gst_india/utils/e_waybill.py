import json
import re

import frappe
from frappe import _

from india_compliance.gst_india.asp_connectors.utils import pretty_json
from india_compliance.gst_india.constants.e_waybill import (
    E_WAYBILL_INVOICE,
    E_WAYBILL_ITEM,
)
from india_compliance.gst_india.utils.invoice_data import GSTInvoiceData


@frappe.whitelist()
def download_e_waybill_json(doctype, docnames):
    docnames = json.loads(docnames) if docnames.startswith("[") else [docnames]
    frappe.response.filecontent = generate_e_waybill_json(doctype, docnames)
    frappe.response.type = "download"
    frappe.response.filename = get_file_name(docnames)


def generate_e_waybill_json(doctype, docnames):
    return pretty_json(
        {
            "version": "1.0.0421",
            "billLists": [eWaybill(doc).get_e_waybill_data() for doc in docnames],
        }
    )


def get_file_name(docnames):
    prefix = "Bulk"
    if len(docnames) == 1:
        prefix = re.sub(r"[^\w_.)( -]", "", docnames[0])

    return f"{prefix}_e-Waybill_Data_{frappe.utils.random_string(5)}.json"


class eWaybill(GSTInvoiceData):
    def __init__(self, doc):
        super().__init__(doc)
        self.item_map = E_WAYBILL_ITEM
        self.invoice_map = E_WAYBILL_INVOICE

    def get_e_waybill_data(self):
        doc = self.doc
        self.validate_invoice_for_ewb(doc)
        item_list = self.get_item_list()
        self.get_invoice_details()
        self.update_invoice_details(doc)
        self.update_address_details(doc)

        ewb_data = self.map_template(self.invoice_map, doc)
        ewb_data.update({"itemList": item_list})
        return ewb_data

    def validate_invoice_for_ewb(self, doc):
        """
        Validates:
        - Ewaybill already exists
        - Required fields
        - Atleast one item with HSN for goods is required
        - Basic transporter details must be present
        - Max 250 Items
        """

        # TODO: Validate with e-Waybill settings
        # TODO: Add Support for Delivery Note

        if doc.get("ewaybill"):
            frappe.throw(_("E-Waybill already generated for this invoice"))

        reqd_fields = [
            "company_gstin",
            "company_address",
            "customer_address",
        ]

        for fieldname in reqd_fields:
            if not doc.get(fieldname):
                frappe.throw(
                    _("{} is required to generate e-Waybill JSON").format(
                        doc.meta.get_label(fieldname)
                    )
                )

        # Atleast one item with HSN code of goods is required
        doc_with_goods = False
        for item in doc.items:
            if not item.gst_hsn_code.startswith("99"):
                doc_with_goods = True
                break
        if not doc_with_goods:
            frappe.throw(
                msg=_(
                    "e-Waybill cannot be generated as all items are with service HSN codes."
                ),
                title=_("Invalid Data"),
            )

        if doc.get("is_return") and doc.get("gst_category") == "Overseas":
            frappe.throw(
                msg=_("Return/Credit Note is not supported for Overseas e-Waybill."),
                title=_("Invalid Data"),
            )

        # check if transporter_id or vehicle number is present
        transport_mode = doc.get("transport_mode")
        missing_transport_details = (
            road_transport := (transport_mode == "Road")
            and not doc.get("vehicle_number")
            or transport_mode in ["Rail", "Air", "Ship"]
            and not doc.get("lr_no")
        )
        if not doc.get("gst_transporter_id"):
            if missing_transport_details:
                frappe.throw(
                    msg=_(
                        "Please enter {0} to generate e-Waybill.".format(
                            "Vehicle Number" if road_transport else "LR Number"
                        )
                    ),
                    title=_("Invalid Data"),
                )

        if len(doc.items) > 250:
            # TODO: Add support for HSN Summary
            frappe.throw(
                msg=_("e-Waybill cannot be generated for more than 250 items."),
                title=_("Invalid Data"),
            )

    def update_invoice_details(self, doc):
        doc.supply_type = "O"
        doc.sub_supply_type = 1
        doc.document_type = "INV"

        if doc.is_return:
            doc.supply_type = "I"
            doc.sub_supply_type = 7
            doc.document_type = "CHL"
        elif doc.gst_category == "Overseas":
            doc.shipping_address = self.get_address_details()
            doc.sub_supply_type = 3
            if doc.export_type == "With Payment of Tax":
                doc.document_type = "BIL"

    def update_address_details(self, doc):
        doc.transaction_type = 1
        billTo_shipTo = doc.customer_address != (
            doc.get("shipping_address_name") or doc.customer_address
        )
        billFrom_dispatchFrom = doc.company_address != (
            doc.get("dispatch_address_name") or doc.company_address
        )
        billing_address = shipping_address = self.get_address_details(
            doc.customer_address
        )
        company_address = dispatch_address = self.get_address_details(
            doc.company_address
        )

        if billTo_shipTo and billFrom_dispatchFrom:
            doc.transaction_type = 4
            shipping_address = self.get_address_details(doc.shipping_address_name)
            dispatch_address = self.get_address_details(doc.dispatch_address_name)
        elif billFrom_dispatchFrom:
            doc.transaction_type = 3
            dispatch_address = self.get_address_details(doc.dispatch_address_name)
        elif billTo_shipTo:
            doc.transaction_type = 2
            shipping_address = self.get_address_details(doc.shipping_address_name)

        doc.update(
            {
                "to_state_code": 99
                if self.doc.gst_category == "SEZ"
                else billing_address.state_code,
                "to_address_1": shipping_address.address_line1,
                "to_address_2": shipping_address.address_line2,
                "to_city": shipping_address.city,
                "to_pincode": shipping_address.pincode,
                "actual_to_state_code": shipping_address.state_code,
                "from_state_code": company_address.state_code,
                "from_address_1": dispatch_address.address_line1,
                "from_address_2": dispatch_address.address_line2,
                "from_city": dispatch_address.city,
                "from_pincode": dispatch_address.pincode,
                "actual_from_state_code": dispatch_address.state_code,
            }
        )
