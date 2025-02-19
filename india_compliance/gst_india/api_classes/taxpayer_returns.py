import frappe
from frappe import _

from india_compliance.gst_india.api_classes.taxpayer_base import (
    FilesAPI,
    TaxpayerBaseAPI,
)


class ReturnsAPI(TaxpayerBaseAPI):
    API_NAME = "GST Returns"
    IGNORED_ERROR_CODES = {
        **TaxpayerBaseAPI.IGNORED_ERROR_CODES,
        "RET11416": "no_docs_found",
        "RET12501": "no_docs_found",  # random `system failure` for CDNR
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
        "GTR2B-002": "not_generated",  # GSTR2B form is not generated for given return period
        "GTR2B-001": "not_applicable",  # GSTR2B form is not applicable for given return period
        # "IMS2B007": "not_applicable", # Either the entered ITC period is incorrect or it has 3B filed
        "IMS2005": "not_needed",  # 2B cannot be generated as there are no changes
        # "IMSSAV0015": # Previous Save or Reset request is already under progress. Please try after some time.
    }

    def download_files(self, return_period, token):
        return super().get_files(
            return_period, token, action="FILEDET", endpoint="returns"
        )

    def get_return_status(self, return_period, reference_id, otp=None):
        return self.get(
            action="RETSTATUS",
            return_period=return_period,
            params={"ret_period": return_period, "ref_id": reference_id},
            endpoint="returns",
            otp=otp,
        )

    def proceed_to_file(self, return_type, return_period, is_nil_return, otp=None):
        data = {
            "gstin": self.company_gstin,
            "ret_period": return_period,
        }

        if is_nil_return:
            data["isnil"] = "Y"

        return self.post(
            return_type=return_type,
            return_period=return_period,
            json={"action": "RETNEWPTF", "data": data},
            endpoint="returns/gstrptf",
            otp=otp,
        )


class GSTR2bAPI(ReturnsAPI):
    API_NAME = "GSTR-2B"
    END_POINT = "returns/gstr2b"

    def get_data(self, return_period, otp=None, file_num=None):
        params = {"rtnprd": return_period}
        if file_num:
            params.update({"file_num": file_num})

        return self.get(
            action="GET2B",
            return_period=return_period,
            params=params,
            endpoint=self.END_POINT,
            otp=otp,
        )

    def regenerate(self, return_period):
        return self.put(
            json={
                "action": "GEN2B",
                "data": {"rtin": self.company_gstin, "itcprd": return_period},
            },
            endpoint=self.END_POINT,
        )

    def generation_status(self, transaction_id):
        return self.get(
            action="GENSTS2B",
            params={
                "gstin": self.company_gstin,
                "int_tran_id": transaction_id,
            },
            endpoint=self.END_POINT,
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
        # action: RETSUM for summary
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

    def save_gstr_1_data(self, return_period, data, otp=None):
        return self.put(
            return_period=return_period,
            json={"action": "RETSAVE", "data": data},
            endpoint="returns/gstr1",
            otp=otp,
        )

    def reset_gstr_1_data(self, return_period, otp=None):
        return self.post(
            return_period=return_period,
            json={
                "action": "RESET",
                "data": {
                    "gstin": self.company_gstin,
                    "ret_period": return_period,
                },
            },
            endpoint="returns/gstr1",
            otp=otp,
        )

    def file_gstr_1(self, return_period, summary_data, pan, evc_otp):
        return self.post(
            return_period=return_period,
            json={
                "action": "RETFILE",
                "data": summary_data,
                "st": "EVC",
                "sid": f"{pan}|{evc_otp}",
            },
            endpoint="returns/gstr1",
        )


class GSTR3bAPI(ReturnsAPI):
    END_POINT = "returns/gstr3b"

    def setup(self, company_gstin, return_period):
        self.return_period = return_period
        super().setup(company_gstin=company_gstin)

    def get_data(self):
        return self.get(
            action="RETSUM",
            return_period=self.return_period,
            params={"gstin": self.company_gstin, "ret_period": self.return_period},
            endpoint=self.END_POINT,
        )

    def save_gstr3b(self, data):
        return self.put(
            return_period=self.return_period,
            json={
                "action": "RETSAVE",
                "data": data,
            },
            endpoint=self.END_POINT,
        )

    def submit_gstr3b(self, data):
        return self.post(
            return_period=self.return_period,
            json={
                "action": "RETSUBMIT",
                "data": data,
            },
            endpoint=self.END_POINT,
        )

    def save_offset_liability_gstr3b(self, data):
        return self.put(
            return_period=self.return_period,
            json={
                "action": "RETOFFSET",
                "data": data,
            },
            endpoint=self.END_POINT,
        )

    def file_gstr_3b(self, data, pan, evc_otp):
        return self.post(
            return_period=self.return_period,
            json={
                "action": "RETFILE",
                "data": data,
                "st": "EVC",
                "sid": f"{pan}|{evc_otp}",
            },
            endpoint=self.END_POINT,
        )

    def get_itc_liab_data(self):
        return self.get(
            action="AUTOLIAB",
            return_period=self.return_period,
            params={"gstin": self.company_gstin, "ret_period": self.return_period},
            endpoint=self.END_POINT,
        )

    def validate_3b_against_auto_calc(self, data):
        return self.post(
            return_period=self.return_period,
            json={
                "action": "VALID",
                "data": data,
            },
            endpoint=self.END_POINT,
        )

    def get_system_calc_interest(self):
        return self.get(
            action="RETINT",
            return_period=self.return_period,
            params={"gstin": self.company_gstin, "ret_period": self.return_period},
            endpoint=self.END_POINT,
        )

    def recompute_interest(self):
        return self.post(
            return_period=self.return_period,
            json={
                "action": "CMPINT",
                "data": {"gstn": self.company_gstin, "ret_period": self.return_period},
            },
            endpoint=self.END_POINT,
        )

    def save_past_liab(self, data):
        return self.put(
            return_period=self.return_period,
            json={"action": "RETBKP", "data": data},
            endpoint=self.END_POINT,
        )

    def get_itc_reversal_bal(self):
        return self.get(
            action="CLOSINGBAL",
            return_period=self.return_period,
            params={"gstin": self.company_gstin},
            endpoint=self.END_POINT,
        )

    def get_rcm_bal(self):
        return self.get(
            action="RCMCLOSINGBAL",
            return_period=self.return_period,
            params={"gstin": self.company_gstin},
            endpoint=self.END_POINT,
        )

    def get_opening_bal(self):
        return self.get(
            action="OPENINGBAL",
            return_period=self.return_period,
            params={"gstin": self.company_gstin},
            endpoint=self.END_POINT,
        )

    def get_rcm_opening_bal(self):
        return self.get(
            action="RCMOPNBAL",
            return_period=self.return_period,
            params={"gstin": self.company_gstin},
            endpoint=self.END_POINT,
        )

    def save_opening_bal(self, data):
        return self.post(
            return_period=self.return_period,
            json={"action": "SAVEOB", "data": data},
            endpoint=self.END_POINT,
        )

    def submit_rcm_opening_bal(self, data):
        return self.post(
            return_period=self.return_period,
            json={
                "action": "SAVERCMOPNBAL",
                "data": data,
            },
            endpoint=self.END_POINT,
        )


class IMSAPI(ReturnsAPI):
    API_NAME = "IMS"
    END_POINT = "returns/ims"

    def get_data(self, section):
        return self.get(
            action="GETINV",
            params={
                "gstin": self.company_gstin,
                "section": section,
            },
            endpoint=self.END_POINT,
        )

    def download_files(self, return_period, token):
        return self.get_files(
            return_period, token, action="FILEDET", endpoint=self.END_POINT
        )

    def get_files(self, return_period, token, action, endpoint):
        response = self.get(
            action=action,
            return_period=return_period,
            params={"gstin": self.company_gstin, "token": token},
            endpoint=endpoint,
        )

        if response.error_type == "queued":
            return response

        return FilesAPI().get_all(response)

    def save(self, data):
        return self.put(
            endpoint=self.END_POINT,
            json={
                "action": "SAVE",
                "data": {"rtin": self.company_gstin, "reqtyp": "SAVE", "invdata": data},
            },
        )

    def reset(self, data):
        return self.put(
            endpoint=self.END_POINT,
            json={
                "action": "RESETIMS",
                "data": {
                    "rtin": self.company_gstin,
                    "reqtyp": "RESET",
                    "invdata": data,
                },
            },
        )

    def get_request_status(self, transaction_id):
        return self.get(
            action="REQSTS",
            endpoint=self.END_POINT,
            params={"gstin": self.company_gstin, "int_tran_id": transaction_id},
        )
