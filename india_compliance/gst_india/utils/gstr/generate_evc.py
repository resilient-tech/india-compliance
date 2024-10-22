import frappe

from india_compliance.gst_india.api_classes.taxpayer_base import TaxpayerBaseAPI


@frappe.whitelist()
def generate_evc_otp(company_gstin, pan, request_type):
    frappe.has_permission("GSTR-1 Beta", "write", throw=True)
    return TaxpayerBaseAPI(company_gstin).initiate_otp_for_evc(pan, request_type)
