import json
import re

import frappe
from frappe import _

from india_compliance.gst_india.constants.e_waybill import E_WAYBILL_INVOICE
from india_compliance.gst_india.utils.invoice_data import GSTInvoiceData


@frappe.whitelist()
def generate_e_waybill_json(doctype, doclist):
    doclist = json.loads(doclist)
    ewaybills = []
    for doc in doclist:
        doc = frappe.get_doc(doctype, doc)
        ewaybills.append(doc.get_e_waybill_data())

    data = {"version": "1.0.0421", "billLists": ewaybills}
    return data


@frappe.whitelist()
def download_e_waybill_json():
    data = json.loads(frappe.local.form_dict.data)
    frappe.local.response.filecontent = json.dumps(data, indent=4, sort_keys=True)
    frappe.local.response.type = "download"

    filename_prefix = "Bulk"
    docname = frappe.local.form_dict.docname
    if docname:
        if docname.startswith("["):
            docname = json.loads(docname)
            if len(docname) == 1:
                docname = docname[0]

        if not isinstance(docname, list):
            # removes characters not allowed in a filename (https://stackoverflow.com/a/38766141/4767738)
            filename_prefix = re.sub(r"[^\w_.)( -]", "", docname)

    frappe.local.response.filename = "{0}_e-Waybill_Data_{1}.json".format(
        filename_prefix, frappe.utils.random_string(5)
    )


class EWaybillData(GSTInvoiceData):
    def get_e_waybill_data(self):
        self.validate_invoice_for_ewb()
        item_list = self.get_item_list()
        self.get_invoice_details()
        self.update_invoice_details()
        self.update_address_details()

        ewb_data = self.map_template(E_WAYBILL_INVOICE, self)
        ewb_data.update({"itemList": item_list})
        return ewb_data

    def validate_invoice_for_ewb(self):
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

        if self.get("ewaybill"):
            frappe.throw(_("E-Waybill already generated for this invoice"))

        reqd_fields = [
            "company_gstin",
            "company_address",
            "customer_address",
        ]

        for fieldname in reqd_fields:
            if not self.get(fieldname):
                frappe.throw(
                    _("{} is required to generate e-Waybill JSON").format(
                        self.meta.get_label(fieldname)
                    )
                )

        # Atleast one item with HSN code of goods is required
        doc_with_goods = False
        for item in self.items:
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

        if self.get("is_return") and self.get("gst_category") == "Overseas":
            frappe.throw(
                msg=_("Return/Credit Note is not supported for Overseas e-Waybill."),
                title=_("Invalid Data"),
            )

        # check if transporter_id or vehicle number is present
        transport_mode = self.get("transport_mode")
        missing_transport_details = (
            road_transport := (transport_mode == "Road")
            and not self.get("vehicle_number")
            or transport_mode in ["Rail", "Air", "Ship"]
            and not self.get("lr_no")
        )
        if not self.get("gst_transporter_id"):
            if missing_transport_details:
                frappe.throw(
                    msg=_(
                        "Please enter {0} to generate e-Waybill.".format(
                            "Vehicle Number" if road_transport else "LR Number"
                        )
                    ),
                    title=_("Invalid Data"),
                )

        if len(self.items) > 250:
            # TODO: Add support for HSN Summary
            frappe.throw(
                msg=_("e-Waybill cannot be generated for more than 250 items."),
                title=_("Invalid Data"),
            )

    def update_invoice_details(self):
        self.supply_type = "O"
        self.sub_supply_type = 1
        self.document_type = "INV"

        if self.is_return:
            self.supply_type = "I"
            self.sub_supply_type = 7
            self.document_type = "CHL"
        elif self.gst_category == "Overseas":
            self.shipping_address = self.get_address_details()
            self.sub_supply_type = 3
            if self.export_type == "With Payment of Tax":
                self.document_type = "BIL"

    def update_address_details(self):
        self.transaction_type = 1
        billTo_shipTo = self.customer_address != (
            self.get("shipping_address_name") or self.customer_address
        )
        billFrom_dispatchFrom = self.company_address != (
            self.get("dispatch_address_name") or self.company_address
        )
        billing_address = shipping_address = self.get_address_details(
            self.customer_address
        )
        company_address = dispatch_address = self.get_address_details(
            self.company_address
        )

        if billTo_shipTo and billFrom_dispatchFrom:
            self.transaction_type = 4
            shipping_address = self.get_address_details(self.shipping_address_name)
            dispatch_address = self.get_address_details(self.dispatch_address_name)
        elif billFrom_dispatchFrom:
            self.transaction_type = 3
            dispatch_address = self.get_address_details(self.dispatch_address_name)
        elif billTo_shipTo:
            self.transaction_type = 2
            shipping_address = self.get_address_details(self.shipping_address_name)

        self.update(
            {
                "to_state_code": 99
                if self.gst_category == "SEZ"
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
