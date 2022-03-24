import json
import re

import frappe
from frappe import _

from india_compliance.gst_india.utils.api import pretty_json
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

    def get_e_waybill_data(self):
        self.pre_validate_invoice()
        self.get_item_list()
        self.get_invoice_details()
        self.get_transporter_details()
        self.get_party_address_details()
        self.post_validate_invoice()

        print(self.item_list)
        ewb_data = self.get_invoice_map(
            invoice_details=self.invoice_details,
            item_list=self.item_list,
            billing_address=self.billing_address,
            shipping_address=self.shipping_address,
            company_address=self.company_address,
            dispatch_address=self.dispatch_address,
        )
        ewb_data.replace("'", "")
        print(ewb_data)
        return json.loads(ewb_data)

    def pre_validate_invoice(self):
        """
        Validates:
        - Ewaybill already exists
        - Required fields
        - Atleast one item with HSN for goods is required
        - Basic transporter details must be present
        - Max 250 Items
        """
        super().pre_validate_invoice()

        # TODO: Validate with e-Waybill settings
        # TODO: Add Support for Delivery Note

        if self.doc.get("ewaybill"):
            frappe.throw(_("E-Waybill already generated for this invoice"))

        reqd_fields = [
            "company_gstin",
            "company_address",
            "customer_address",
        ]

        for fieldname in reqd_fields:
            if not self.doc.get(fieldname):
                frappe.throw(
                    _("{} is required to generate e-Waybill JSON").format(
                        self.doc.meta.get_label(fieldname)
                    )
                )

        # Atleast one item with HSN code of goods is required
        doc_with_goods = False
        for item in self.doc.items:
            if not item.gst_hsn_code.startswith("99"):
                doc_with_goods = True
                break
        if not doc_with_goods:
            frappe.throw(
                msg=_(
                    "e-Waybill cannot be generated as all items are with service HSN"
                    " codes."
                ),
                title=_("Invalid Data"),
            )

        if self.doc.get("is_return") and self.doc.get("gst_category") == "Overseas":
            frappe.throw(
                msg=_("Return/Credit Note is not supported for Overseas e-Waybill."),
                title=_("Invalid Data"),
            )

        # check if transporter_id or vehicle number is present
        transport_mode = self.doc.get("transport_mode")
        missing_transport_details = (
            road_transport := (transport_mode == "Road")
            and not self.doc.get("vehicle_number")
            or transport_mode in ["Rail", "Air", "Ship"]
            and not self.doc.get("lr_no")
        )
        if not self.doc.get("gst_transporter_id"):
            if missing_transport_details:
                frappe.throw(
                    msg=_(
                        "Please enter {0} to generate e-Waybill.".format(
                            "Vehicle Number" if road_transport else "LR Number"
                        )
                    ),
                    title=_("Invalid Data"),
                )

        if len(self.doc.items) > 250:
            # TODO: Add support for HSN Summary
            frappe.throw(
                msg=_("e-Waybill cannot be generated for more than 250 items."),
                title=_("Invalid Data"),
            )

    def update_invoice_details(self):
        super().update_invoice_details()

        self.invoice_details.update(
            {
                "supply_type": "O",
                "sub_supply_type": 1,
                "document_type": "INV",
            }
        )

        if self.doc.is_return:
            self.invoice_details.update(
                {"supply_type": "I", "sub_supply_type": 7, "document_type": "CHL"}
            )

        elif self.doc.gst_category == "Overseas":
            self.invoice_details.sub_supply_type = 3

            if self.doc.export_type == "With Payment of Tax":
                self.invoice_details.document_type = "BIL"

    def get_party_address_details(self):
        transaction_type = 1
        billTo_shipTo = self.doc.customer_address != (
            self.doc.get("shipping_address_name") or self.doc.customer_address
        )
        billFrom_dispatchFrom = self.doc.company_address != (
            self.doc.get("dispatch_address_name") or self.doc.company_address
        )
        self.billing_address = self.shipping_address = self.get_address_details(
            self.doc.customer_address
        )
        self.company_address = self.dispatch_address = self.get_address_details(
            self.doc.company_address
        )

        if billTo_shipTo and billFrom_dispatchFrom:
            transaction_type = 4
            self.shipping_address = self.get_address_details(
                self.doc.shipping_address_name
            )
            self.dispatch_address = self.get_address_details(
                self.doc.dispatch_address_name
            )
        elif billFrom_dispatchFrom:
            transaction_type = 3
            self.dispatch_address = self.get_address_details(
                self.doc.dispatch_address_name
            )
        elif billTo_shipTo:
            transaction_type = 2
            self.shipping_address = self.get_address_details(
                self.doc.shipping_address_name
            )

        self.invoice_details.update(
            {
                "transaction_type": transaction_type,
            }
        )

        if self.doc.gst_category == "SEZ":
            self.billing_address.state_code = 96

    def get_invoice_map(self, **kwargs):
        return """
        {{
            "userGstin": "{invoice_details.company_gstin}",
            "supplyType": "{invoice_details.supply_type}",
            "subSupplyType": {invoice_details.sub_supply_type},
            "subSupplyDesc":"",
            "docType": "{invoice_details.document_type}",
            "docNo": "{invoice_details.invoice_number}",
            "docDate": "{invoice_details.invoice_date}",
            "transType": {invoice_details.transaction_type},
            "fromTrdName": "{company_address.address_title}",
            "fromGstin": "{company_address.gstin}",
            "fromAddr1": "{dispatch_address.address_line1}",
            "fromAddr2": "{dispatch_address.address_line2}",
            "fromPlace": "{dispatch_address.city}",
            "fromPincode": {dispatch_address.pincode},
            "fromStateCode": {company_address.state_code},
            "actualFromStateCode": {dispatch_address.state_code},
            "toTrdName": "{billing_address.address_title}",
            "toGstin": "{billing_address.gstin}",
            "toAddr1": "{shipping_address.address_line1}",
            "toAddr2": "{shipping_address.address_line2}",
            "toPlace": "{shipping_address.city}",
            "toPincode": {shipping_address.pincode},
            "toStateCode": {billing_address.state_code},
            "actualToStateCode": {shipping_address.state_code},
            "totalValue": {invoice_details.base_total},
            "cgstValue": {invoice_details.total_cgst_amount},
            "sgstValue": {invoice_details.total_sgst_amount},
            "igstValue": {invoice_details.total_igst_amount},
            "cessValue": {invoice_details.total_cess_amount},
            "TotNonAdvolVal": {invoice_details.total_cess_non_advol_amount},
            "OthValue": {invoice_details.rounding_adjustment},
            "totInvValue": {invoice_details.base_grand_total},
            "transMode": {invoice_details.mode_of_transport},
            "transDistance": {invoice_details.distance},
            "transporterName": "{invoice_details.transporter_name}",
            "transporterId": "{invoice_details.transporter_gstin}",
            "transDocNo": "{invoice_details.lr_no}",
            "transDocDate": "{invoice_details.lr_date_str}",
            "vehicleNo": "{invoice_details.vehicle_no}",
            "vehicleType": "{invoice_details.vehicle_type}",
            "itemList": [{item_list}]
        }}""".format(
            **kwargs
        )

    def get_item_map(self, item_details):
        return """
        {{
            "productName": "",
            "productDesc": "{item_details.item_name}",
            "hsnCode": "{item_details.hsn_code}",
            "qtyUnit": "{item_details.uom}",
            "quantity": {item_details.qty},
            "taxableAmount": {item_details.taxable_value},
            "sgstRate": {item_details.sgst_rate},
            "cgstRate": {item_details.cgst_rate},
            "igstRate": {item_details.igst_rate},
            "cessRate": {item_details.cess_rate},
            "cessNonAdvol": {item_details.cess_non_advol_rate}
        }}""".format(
            item_details=item_details
        )
