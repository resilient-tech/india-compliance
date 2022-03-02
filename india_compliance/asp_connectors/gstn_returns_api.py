import frappe

from frappe.utils import now
from india_compliance.asp_connectors.auth_api import AuthApi


class GstnReturnsApi(AuthApi):
    def __init__(self, company_gstin):
        super().__init__()
        self.uid = frappe.utils.random_string(7)
        self.api_name = "enriched/returns"
        self.comp_gstin = company_gstin
        for creds in self.settings.gst_credentials:
            if creds.gstin == company_gstin and creds.service == "Returns":
                self.username = creds.username
                self.company = creds.company
                break

        if not self.username:
            frappe.throw(
                "You have not set credentials in GST Settings. Kindly set your GST credentials to use API service.",
                title="Credentials unavailable",
            )

    def get_params(self, action, ret_period, rtnprd):
        return {
            "action": action,
            "gstin": self.comp_gstin,
            "rtnprd": rtnprd,
            "ret_period": ret_period,
        }

    def get_headers(self, ret_period, otp):
        return {
            "username": self.username,
            "state-cd": self.comp_gstin[:2],
            "requestid": self.generate_request_id(),
            "gstin": self.comp_gstin,
            "ret_period": ret_period,
            "otp": otp,
            "x-api-key": self.settings.get_password('api_secret'),
        }

    def make_get_request(self, action, ret_period, otp, rtnprd=None):
        response = self.make_request(
            method="get",
            url_suffix=self.url_suffix,
            params=self.get_params(action, ret_period, rtnprd),
            headers=self.get_headers(ret_period or rtnprd, otp),
        )
        return frappe._dict(response)

    def create_or_update_download_log(
        self, gst_return, classification, return_period, no_data_found=0
    ):
        doctype = "GSTR Download Log"
        name = frappe.db.get_value(
            doctype,
            {
                "gstin": self.comp_gstin,
                "gst_return": gst_return,
                "classification": classification,
                "return_period": return_period,
            },
            fieldname="name",
        )
        if name:
            frappe.db.set_value(doctype, name, {"last_updated_on": now(), "no_data_found": no_data_found})
        else:
            doc = frappe.get_doc(
                {
                    "doctype": doctype,
                    "gstin": self.comp_gstin,
                    "gst_return": gst_return,
                    "classification": classification,
                    "return_period": return_period,
                    "no_data_found": no_data_found,
                }
            )
            doc.last_updated_on = now()
            doc.save(ignore_permissions=True)


class Gstr2bApi(GstnReturnsApi):
    def __init__(self, company_gstin):
        super().__init__(company_gstin)
        self.url_suffix = "/gstr2b?"

    def get_gstr_2b(self, ret_period, otp):
        return self.make_get_request("GET2B", None, otp, ret_period)
        # TODO: Create further calls if more than one file to download


class Gstr2aApi(GstnReturnsApi):
    def __init__(self, company_gstin):
        super().__init__(company_gstin)
        self.url_suffix = "/gstr2a?"

    def get_gstr_2a(self, action, ret_period, otp):
        return self.make_get_request(action, ret_period, otp)
