import frappe
from frappe import _

from india_compliance.gst_india.api_classes.taxpayer_base import TaxpayerBaseAPI


class EInvoiceAPI(TaxpayerBaseAPI):
    endpoint = "einvoice"

    IGNORED_ERROR_CODES = {
        **TaxpayerBaseAPI.IGNORED_ERROR_CODES,
        "EINV30107": "no_docs_found",
        "EINV30108": "no_docs_found",
        "EINV30118": "no_docs_found",
        "EINV30109": "queued",
    }

    def setup(self, doc=None, *, company_gstin=None):
        if doc:
            company_gstin = doc.company_gstin
            self.default_log_values.update(
                reference_doctype=doc.doctype,
                reference_name=doc.name,
            )

        if self.sandbox_mode:
            frappe.throw(_("Sandbox mode is not supported for Taxpayer e-Invoice API"))

        if not company_gstin:
            frappe.throw(_("Company GSTIN is required to use the e-Invoice API"))

        super().setup(company_gstin=company_gstin)

    def get_irn_list(
        self,
        return_period,
        supply_type,
        supplier_gstin=None,
        recipient_gstin=None,
        otp=None,
    ):
        action = "IRNLIST"
        return self.get(
            action=action,
            params={
                "rtnprd": return_period,
                "suptyp": supply_type,
                "stin": supplier_gstin,
                "rtin": recipient_gstin,
            },
            endpoint=self.endpoint,
            otp=otp,
        )

    def get_irn_details(self, irn, otp=None):
        action = "IRNDTL"
        return self.get(
            action=action,
            return_period=None,
            params={"irn": irn},
            endpoint=self.endpoint,
            otp=otp,
        )

    def download_files(self, return_period, token, otp=None):
        return super().get_files(
            return_period, token, action="FILEDETL", endpoint=self.endpoint, otp=otp
        )
