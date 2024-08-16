import frappe
from frappe import _

from india_compliance.gst_india.api_classes.taxpayer_base import TaxpayerBaseAPI


class ReturnsAPI(TaxpayerBaseAPI):
    API_NAME = "GST Returns"
    IGNORED_ERROR_CODES = {
        **TaxpayerBaseAPI.IGNORED_ERROR_CODES,
        "RET11416": "no_docs_found",
        "RET13508": "no_docs_found",
        "RET13509": "no_docs_found",
        "RET13510": "no_docs_found",
        "RET2B1023": "not_generated",
        "RET2B1016": "no_docs_found",
        "RT-3BAS1009": "no_docs_found",
        "RET11417": "no_docs_found",  # GSTR-1 Exports
        "RET2B1018": "requested_before_cutoff_date",
        "RTN_24": "queued",
        "RET11402": "authorization_failed",  # API Authorization Failed for 2A
        "RET2B1010": "authorization_failed",  # API Authorization Failed for 2B
    }

    def download_files(self, return_period, token, otp=None):
        return super().get_files(
            return_period, token, action="FILEDET", endpoint="returns", otp=otp
        )


class GSTR2bAPI(ReturnsAPI):
    API_NAME = "GSTR-2B"

    def get_data(self, return_period, otp=None, file_num=None):
        params = {"rtnprd": return_period}
        if file_num:
            params.update({"file_num": file_num})

        return self.get(
            action="GET2B",
            return_period=return_period,
            params=params,
            endpoint="returns/gstr2b",
            otp=otp,
        )


class GSTR2aAPI(ReturnsAPI):
    API_NAME = "GSTR-2A"

    def get_data(self, action, return_period, otp=None):
        return self.get(
            action=action,
            return_period=return_period,
            params={"ret_period": return_period},
            endpoint="returns/gstr2a",
            otp=otp,
        )


class GSTR1API(ReturnsAPI):
    API_NAME = "GSTR-1"

    def setup(self, doc=None, *, company_gstin=None):
        if doc:
            company_gstin = doc.gstin
            self.default_log_values.update(
                reference_doctype=doc.doctype,
                reference_name=doc.name,
            )

        if not company_gstin:
            frappe.throw(_("Company GSTIN is required to use the GSTR-1 API"))

        super().setup(company_gstin=company_gstin)

    def get_gstr_1_data(self, action, return_period, otp=None):
        return self.get(
            action=action,
            return_period=return_period,
            params={"ret_period": return_period},
            endpoint="returns/gstr1",
            otp=otp,
        )

    def get_einvoice_data(self, section, return_period, otp=None):
        return self.get(
            action="EINV",
            return_period=return_period,
            params={"ret_period": return_period, "sec": section},
            endpoint="returns/einvoice",
            otp=otp,
        )
