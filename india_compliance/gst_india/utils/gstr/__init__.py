from enum import Enum

<<<<<<< HEAD:india_compliance/gst_india/utils/gstr/__init__.py
import frappe
from frappe import _
from frappe.query_builder.terms import Criterion
from frappe.utils import cint

from india_compliance.gst_india.api_classes.returns import (
    GSTR2aAPI,
    GSTR2bAPI,
    ReturnsAPI,
)
from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    create_import_log,
    toggle_scheduled_jobs,
)
from india_compliance.gst_india.utils import get_party_for_gstin
from india_compliance.gst_india.utils.gstr import gstr_2a, gstr_2b


class ReturnType(Enum):
    GSTR2A = "GSTR2a"
    GSTR2B = "GSTR2b"


class GSTRCategory(Enum):
    B2B = "B2B"
    B2BA = "B2BA"
    CDNR = "CDNR"
    CDNRA = "CDNRA"
    ISD = "ISD"
    ISDA = "ISDA"
    IMPG = "IMPG"
    IMPGSEZ = "IMPGSEZ"


ACTIONS = {
    "B2B": GSTRCategory.B2B,
    "B2BA": GSTRCategory.B2BA,
    "CDN": GSTRCategory.CDNR,
    "CDNA": GSTRCategory.CDNRA,
    "ISD": GSTRCategory.ISD,
    "IMPG": GSTRCategory.IMPG,
    "IMPGSEZ": GSTRCategory.IMPGSEZ,
}

GSTR_MODULES = {
    ReturnType.GSTR2A.value: gstr_2a,
    ReturnType.GSTR2B.value: gstr_2b,
}

IMPORT_CATEGORY = ("IMPG", "IMPGSEZ")


def download_gstr_2a(gstin, return_periods, otp=None, gst_categories=None):
    total_expected_requests = len(return_periods) * len(ACTIONS)
    requests_made = 0
    queued_message = False
    settings = frappe.get_cached_doc("GST Settings")

    return_type = ReturnType.GSTR2A
    api = GSTR2aAPI(gstin)
    for return_period in return_periods:
        is_last_period = return_periods[-1] == return_period

        json_data = frappe._dict({"gstin": gstin, "fp": return_period})
        has_data = False
        for action, category in ACTIONS.items():
            requests_made += 1

            if (
                not settings.enable_overseas_transactions
                and category.value in IMPORT_CATEGORY
            ):
                continue

            if gst_categories and category.value not in gst_categories:
                continue

            frappe.publish_realtime(
                "update_api_progress",
                {
                    "current_progress": requests_made * 100 / total_expected_requests,
                    "return_period": return_period,
                    "is_last_period": is_last_period,
                },
                user=frappe.session.user,
                doctype="Purchase Reconciliation Tool",
            )

            response = api.get_data(action, return_period, otp)
            if response.error_type in ["otp_requested", "invalid_otp"]:
                return response

            if response.error_type == "no_docs_found":
                create_import_log(
                    gstin,
                    return_type.value,
                    return_period,
                    classification=category.value,
                    data_not_found=True,
                )
                continue

            # Queued
            if response.token:
                create_import_log(
                    gstin,
                    return_type.value,
                    return_period,
                    classification=category.value,
                    request_id=response.token,
                    retry_after_mins=cint(response.est),
                )
                queued_message = True
                continue

            if response.error_type:
                continue

            if not (data := response.get(action.lower())):
                frappe.throw(
                    _(
                        "Data received seems to be invalid from the GST Portal. Please try"
                        " again or raise support ticket."
                    ),
                    title=_("Invalid Response Received."),
                )

            # making consistent with GSTR2a upload
            json_data[action.lower()] = data
            has_data = True

        save_gstr_2a(gstin, return_period, json_data)

    if queued_message:
        show_queued_message()

    if not has_data:
        end_transaction_progress(return_period)


def download_gstr_2b(gstin, return_periods, otp=None):
    total_expected_requests = len(return_periods)
    requests_made = 0
    queued_message = False

    api = GSTR2bAPI(gstin)
    for return_period in return_periods:
        has_data = False
        is_last_period = return_periods[-1] == return_period
        requests_made += 1
        frappe.publish_realtime(
            "update_api_progress",
            {
                "current_progress": requests_made * 100 / total_expected_requests,
                "return_period": return_period,
                "is_last_period": is_last_period,
            },
            user=frappe.session.user,
            doctype="Purchase Reconciliation Tool",
        )

        response = api.get_data(return_period, otp)
        if response.error_type in ["otp_requested", "invalid_otp"]:
            return response

        if response.error_type == "not_generated":
            frappe.msgprint(
                _("No record is found in GSTR-2B or generation is still in progress"),
                title=_("Not Generated"),
            )
            continue

        if response.error_type == "no_docs_found":
            create_import_log(
                gstin, ReturnType.GSTR2B.value, return_period, data_not_found=True
            )
            continue

        if response.error_type == "queued":
            create_import_log(
                gstin,
                ReturnType.GSTR2B.value,
                return_period,
                request_id=response.requestid,
                retry_after_mins=response.retryTimeInMinutes,
            )
            queued_message = True
            continue

        if response.error_type:
            continue

        has_data = True

        # Handle multiple files for GSTR2B
        if response.data and (file_count := response.data.get("fc")):
            for file_num in range(1, file_count + 1):
                r = api.get_data(return_period, otp, file_num)
                save_gstr_2b(gstin, return_period, r)

            continue  # skip first response if file_count is greater than 1

        save_gstr_2b(gstin, return_period, response)

    if queued_message:
        show_queued_message()

    if not has_data:
        end_transaction_progress(return_period)


def save_gstr_2a(gstin, return_period, json_data):
    return_type = ReturnType.GSTR2A
    if (
        not json_data
        or json_data.get("gstin") != gstin
        or json_data.get("fp") != return_period
    ):
        frappe.throw(
            _(
                "Data received seems to be invalid from the GST Portal. Please try"
                " again or raise support ticket."
            ),
            title=_("Invalid Response Received."),
        )

    for action, category in ACTIONS.items():
        if action.lower() not in json_data:
            continue

        create_import_log(
            gstin, return_type.value, return_period, classification=category.value
        )

        # making consistent with GSTR2b
        json_data[category.value.lower()] = json_data.pop(action.lower())

    save_gstr(gstin, return_type, return_period, json_data)


def save_gstr_2b(gstin, return_period, json_data):
    json_data = json_data.data
    return_type = ReturnType.GSTR2B
    if not json_data or json_data.get("gstin") != gstin:
        frappe.throw(
            _(
                "Data received seems to be invalid from the GST Portal. Please try"
                " again or raise support ticket."
            ),
            title=_("Invalid Response Received."),
        )

    create_import_log(gstin, return_type.value, return_period)
    save_gstr(
        gstin,
        return_type,
        return_period,
        json_data.get("docdata"),
        json_data.get("gendt"),
    )
    update_import_history(return_period)


def save_gstr(gstin, return_type, return_period, json_data, gen_date_2b=None):
    frappe.enqueue(
        _save_gstr,
        queue="long",
        now=frappe.flags.in_test,
        timeout=1800,
        gstin=gstin,
        return_type=return_type.value,
        return_period=return_period,
        json_data=json_data,
        gen_date_2b=gen_date_2b,
    )


def _save_gstr(gstin, return_type, return_period, json_data, gen_date_2b=None):
    """Save GSTR data to Inward Supply

    :param return_period: str
    :param json_data: dict of list (GSTR category: suppliers)
    :param gen_date_2b: str (Date when GSTR 2B was generated)
    """

    company = get_party_for_gstin(gstin, "Company")
    for category in GSTRCategory:
        gstr = get_data_handler(return_type, category)
        gstr(company, gstin, return_period, json_data, gen_date_2b).create_transactions(
            category,
            json_data.get(category.value.lower()),
        )


def get_data_handler(return_type, category):
    class_name = return_type + category.value
    return getattr(GSTR_MODULES[return_type], class_name)


def update_import_history(return_periods):
    """Updates 2A data availability from 2B Import"""

    if not (
        inward_supplies := frappe.get_all(
            "GST Inward Supply",
            filters={"return_period_2b": ("in", return_periods)},
            fields=("sup_return_period as return_period", "classification"),
            distinct=True,
        )
    ):
        return

    log = frappe.qb.DocType("GSTR Import Log")
    (
        frappe.qb.update(log)
        .set(log.data_not_found, 0)
        .where(log.data_not_found == 1)
        .where(
            Criterion.any(
                (log.return_period == doc.return_period)
                & (log.classification == doc.classification)
                for doc in inward_supplies
            )
        )
        .run()
    )


def _download_gstr_2a(gstin, return_period, json_data):
    json_data.gstin = gstin
    json_data.fp = return_period
    save_gstr_2a(gstin, return_period, json_data)


GSTR_FUNCTIONS = {
    ReturnType.GSTR2A.value: _download_gstr_2a,
    ReturnType.GSTR2B.value: save_gstr_2b,
}


def download_queued_request():
    queued_requests = frappe.get_all(
        "GSTR Import Log",
        filters={"request_id": ["is", "set"]},
        fields=[
            "name",
            "gstin",
            "return_type",
            "classification",
            "return_period",
            "request_id",
            "request_time",
        ],
    )

    if not queued_requests:
        return toggle_scheduled_jobs(stopped=True)

    for doc in queued_requests:
        frappe.enqueue(_download_queued_request, queue="long", doc=doc)


def _download_queued_request(doc):
    try:
        api = ReturnsAPI(doc.gstin)
        response = api.download_files(
            doc.return_period,
            doc.request_id,
        )

    except Exception as e:
        frappe.db.delete("GSTR Import Log", {"name": doc.name})
        raise e

    if response.error_type in ["otp_requested", "invalid_otp"]:
        return toggle_scheduled_jobs(stopped=True)

    if response.error_type == "no_docs_found":
        return create_import_log(
            doc.gstin,
            doc.return_type,
            doc.return_period,
            doc.classification,
            data_not_found=True,
        )

    if response.error_type == "queued":
        return

    if response.error_type:
        return frappe.db.delete("GSTR Import Log", {"name": doc.name})

    frappe.db.set_value("GSTR Import Log", doc.name, "request_id", None)
    GSTR_FUNCTIONS[doc.return_type](doc.gstin, doc.return_period, response)


def show_queued_message():
    frappe.msgprint(
        _(
            "Some returns are queued for download at GSTN as there may be large data."
            " We will retry download every few minutes until it succeeds.<br><br>"
            "You can track download status from download dialog."
        )
    )


def end_transaction_progress(return_period):
    """
    For last period, set progress to 100% if no data is found
    This will update the progress bar to 100% in the frontend
    """

    frappe.publish_realtime(
        "update_transactions_progress",
        {
            "current_progress": 100,
            "return_period": return_period,
            "is_last_period": True,
        },
        user=frappe.session.user,
        doctype="Purchase Reconciliation Tool",
    )
=======

class GSTR1_Category(Enum):
    """
    Overview Page of GSTR-1
    """

    # Invoice Items Bifurcation
    B2B = "B2B, SEZ, DE"
    EXP = "Exports"
    B2CL = "B2C (Large)"
    B2CS = "B2C (Others)"
    NIL_EXEMPT = "Nil-Rated, Exempted, Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"

    # Other Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    HSN = "HSN Summary"
    DOC_ISSUE = "Document Issued"
    SUPECOM = "Supplies made through E-commerce Operators"


class GSTR1_SubCategory(Enum):
    """
    Summary Page of GSTR-1
    """

    # Invoice Items Bifurcation
    B2B_REGULAR = "B2B Regular"
    B2B_REVERSE_CHARGE = "B2B Reverse Charge"
    SEZWP = "SEZ With Payment of Tax"
    SEZWOP = "SEZ Without Payment of Tax"
    DE = "Deemed Exports"
    EXPWP = "Export With Payment of Tax"
    EXPWOP = "Export Without Payment of Tax"
    B2CL = "B2C (Large)"
    B2CS = "B2C (Others)"
    NIL_EXEMPT = "Nil-Rated, Exempted, Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"

    # Other Sub-Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    HSN = "HSN Summary"
    DOC_ISSUE = "Document Issued"

    # E-Commerce
    SUPECOM_52 = "TCS collected by E-commerce Operator u/s 52"
    SUPECOM_9_5 = "GST Payable on RCM by E-commerce Operator u/s 9(5)"


CATEGORY_SUB_CATEGORY_MAPPING = {
    GSTR1_Category.B2B: (
        GSTR1_SubCategory.B2B_REGULAR,
        GSTR1_SubCategory.B2B_REVERSE_CHARGE,
        GSTR1_SubCategory.SEZWP,
        GSTR1_SubCategory.SEZWOP,
        GSTR1_SubCategory.DE,
    ),
    GSTR1_Category.B2CL: (GSTR1_SubCategory.B2CL,),
    GSTR1_Category.EXP: (GSTR1_SubCategory.EXPWP, GSTR1_SubCategory.EXPWOP),
    GSTR1_Category.B2CS: (GSTR1_SubCategory.B2CS,),
    GSTR1_Category.NIL_EXEMPT: (GSTR1_SubCategory.NIL_EXEMPT,),
    GSTR1_Category.CDNR: (GSTR1_SubCategory.CDNR,),
    GSTR1_Category.CDNUR: (GSTR1_SubCategory.CDNUR,),
    GSTR1_Category.AT: (GSTR1_SubCategory.AT,),
    GSTR1_Category.TXP: (GSTR1_SubCategory.TXP,),
    GSTR1_Category.DOC_ISSUE: (GSTR1_SubCategory.DOC_ISSUE,),
    GSTR1_Category.HSN: (GSTR1_SubCategory.HSN,),
    GSTR1_Category.SUPECOM: (
        GSTR1_SubCategory.SUPECOM_52,
        GSTR1_SubCategory.SUPECOM_9_5,
    ),
}


class GSTR1_DataField(Enum):
    TRANSACTION_TYPE = "transaction_type"
    CUST_GSTIN = "customer_gstin"
    ECOMMERCE_GSTIN = "ecommerce_gstin"
    CUST_NAME = "customer_name"
    DOC_DATE = "document_date"
    DOC_NUMBER = "document_number"
    DOC_TYPE = "document_type"
    DOC_VALUE = "document_value"
    POS = "place_of_supply"
    DIFF_PERCENTAGE = "diff_percentage"
    REVERSE_CHARGE = "reverse_charge"
    TAXABLE_VALUE = "total_taxable_value"
    ITEMS = "items"
    IGST = "total_igst_amount"
    CGST = "total_cgst_amount"
    SGST = "total_sgst_amount"
    CESS = "total_cess_amount"
    TAX_RATE = "tax_rate"

    SHIPPING_BILL_NUMBER = "shipping_bill_number"
    SHIPPING_BILL_DATE = "shipping_bill_date"
    SHIPPING_PORT_CODE = "shipping_port_code"

    EXEMPTED_AMOUNT = "exempted_amount"
    NIL_RATED_AMOUNT = "nil_rated_amount"
    NON_GST_AMOUNT = "non_gst_amount"

    HSN_CODE = "hsn_code"
    DESCRIPTION = "description"
    UOM = "uom"
    QUANTITY = "quantity"

    FROM_SR = "from_sr_no"
    TO_SR = "to_sr_no"
    TOTAL_COUNT = "total_count"
    DRAFT_COUNT = "draft_count"
    CANCELLED_COUNT = "cancelled_count"
    NET_ISSUE = "net_issue"
    UPLOAD_STATUS = "upload_status"


class GSTR1_ItemField(Enum):
    INDEX = "idx"
    TAXABLE_VALUE = "taxable_value"
    IGST = "igst_amount"
    CGST = "cgst_amount"
    SGST = "sgst_amount"
    CESS = "cess_amount"
    TAX_RATE = "tax_rate"
    ITEM_DETAILS = "item_details"
    ADDITIONAL_AMOUNT = "additional_amount"


class GovDataField(Enum):
    CUST_GSTIN = "ctin"
    ECOMMERCE_GSTIN = "etin"
    DOC_DATE = "idt"
    DOC_NUMBER = "inum"
    DOC_VALUE = "val"
    POS = "pos"
    DIFF_PERCENTAGE = "diff_percent"
    REVERSE_CHARGE = "rchrg"
    TAXABLE_VALUE = "txval"
    ITEMS = "itms"
    IGST = "iamt"
    CGST = "camt"
    SGST = "samt"
    CESS = "csamt"
    TAX_RATE = "rt"
    ITEM_DETAILS = "itm_det"
    SHIPPING_BILL_NUMBER = "sbnum"
    SHIPPING_BILL_DATE = "sbdt"
    SHIPPING_PORT_CODE = "sbpcode"
    SUPPLY_TYPE = "sply_ty"
    NET_TAXABLE_VALUE = "suppval"

    EXEMPTED_AMOUNT = "expt_amt"
    NIL_RATED_AMOUNT = "nil_amt"
    NON_GST_AMOUNT = "ngsup_amt"

    HSN_DATA = "data"
    HSN_CODE = "hsn_sc"
    DESCRIPTION = "desc"
    UOM = "uqc"
    QUANTITY = "qty"
    ADVANCE_AMOUNT = "ad_amt"

    INDEX = "num"
    FROM_SR = "from"
    TO_SR = "to"
    TOTAL_COUNT = "totnum"
    CANCELLED_COUNT = "cancel"
    DOC_ISSUE_DETAILS = "doc_det"
    DOC_ISSUE_NUMBER = "doc_num"
    DOC_ISSUE_LIST = "docs"
    NET_ISSUE = "net_issue"

    INVOICE_TYPE = "inv_typ"
    INVOICES = "inv"
    EXPORT_TYPE = "exp_typ"
    TYPE = "typ"

    NOTE_TYPE = "ntty"
    NOTE_NUMBER = "nt_num"
    NOTE_DATE = "nt_dt"
    NOTE_DETAILS = "nt"

    SUPECOM_52 = "clttx"
    SUPECOM_9_5 = "paytx"

    FLAG = "flag"


class GovExcelField(Enum):
    CUST_GSTIN = "GSTIN/UIN of Recipient"
    CUST_NAME = "Receiver Name"
    INVOICE_NUMBER = "Invoice Number"
    INVOICE_DATE = "Invoice date"
    INVOICE_VALUE = "Invoice Value"
    POS = "Place Of Supply"
    REVERSE_CHARGE = "Reverse Charge"
    DIFF_PERCENTAGE = "Applicable % of Tax Rate"
    INVOICE_TYPE = "Invoice Type"
    TAXABLE_VALUE = "Taxable Value"
    ECOMMERCE_GSTIN = "E-Commerce GSTIN"
    TAX_RATE = "Rate"
    IGST = "Integrated Tax Amount"
    CGST = "Central Tax Amount"
    SGST = "State/UT Tax Amount"
    CESS = "Cess Amount"

    NOTE_NO = "Note Number"
    NOTE_DATE = "Note Date"
    NOTE_TYPE = "Note Type"
    NOTE_VALUE = "Note Value"

    PORT_CODE = "Port Code"
    SHIPPING_BILL_NO = "Shipping Bill Number"
    SHIPPING_BILL_DATE = "Shipping Bill Date"

    DESCRIPTION = "Description"
    # NIL_RATED = "Nil Rated Supplies"
    # EXEMPTED = "Exempted (other than nil rated/non-GST supplies)"
    # NON_GST = "Non-GST Supplies"

    HSN_CODE = "HSN"
    UOM = "UQC"
    QUANTITY = "Total Quantity"
    TOTAL_VALUE = "Total Value"


class GovJsonKey(Enum):
    """
    Categories / Keys as per Govt JSON file
    """

    B2B = "b2b"
    EXP = "exp"
    B2CL = "b2cl"
    B2CS = "b2cs"
    NIL_EXEMPT = "nil"
    CDNR = "cdnr"
    CDNUR = "cdnur"
    AT = "at"
    TXP = "txpd"
    HSN = "hsn"
    DOC_ISSUE = "doc_issue"
    SUPECOM = "supeco"
    RET_SUM = "sec_sum"


class GovExcelSheetName(Enum):
    """
    Categories / Worksheets as per Gov Excel file
    """

    B2B = "b2b, sez, de"
    EXP = "exp"
    B2CL = "b2cl"
    B2CS = "b2cs"
    NIL_EXEMPT = "exemp"
    CDNR = "cdnr"
    CDNUR = "cdnur"
    AT = "at"
    TXP = "atadj"
    HSN = "hsn"
    DOC_ISSUE = "docs"


SUB_CATEGORY_GOV_CATEGORY_MAPPING = {
    GSTR1_SubCategory.B2B_REGULAR: GovJsonKey.B2B,
    GSTR1_SubCategory.B2B_REVERSE_CHARGE: GovJsonKey.B2B,
    GSTR1_SubCategory.SEZWP: GovJsonKey.B2B,
    GSTR1_SubCategory.SEZWOP: GovJsonKey.B2B,
    GSTR1_SubCategory.DE: GovJsonKey.B2B,
    GSTR1_SubCategory.B2CL: GovJsonKey.B2CL,
    GSTR1_SubCategory.EXPWP: GovJsonKey.EXP,
    GSTR1_SubCategory.EXPWOP: GovJsonKey.EXP,
    GSTR1_SubCategory.B2CS: GovJsonKey.B2CS,
    GSTR1_SubCategory.NIL_EXEMPT: GovJsonKey.NIL_EXEMPT,
    GSTR1_SubCategory.CDNR: GovJsonKey.CDNR,
    GSTR1_SubCategory.CDNUR: GovJsonKey.CDNUR,
    GSTR1_SubCategory.AT: GovJsonKey.AT,
    GSTR1_SubCategory.TXP: GovJsonKey.TXP,
    GSTR1_SubCategory.DOC_ISSUE: GovJsonKey.DOC_ISSUE,
    GSTR1_SubCategory.HSN: GovJsonKey.HSN,
    GSTR1_SubCategory.SUPECOM_52: GovJsonKey.SUPECOM,
    GSTR1_SubCategory.SUPECOM_9_5: GovJsonKey.SUPECOM,
}

JSON_CATEGORY_EXCEL_CATEGORY_MAPPING = {
    GovJsonKey.B2B.value: GovExcelSheetName.B2B.value,
    GovJsonKey.EXP.value: GovExcelSheetName.EXP.value,
    GovJsonKey.B2CL.value: GovExcelSheetName.B2CL.value,
    GovJsonKey.B2CS.value: GovExcelSheetName.B2CS.value,
    GovJsonKey.NIL_EXEMPT.value: GovExcelSheetName.NIL_EXEMPT.value,
    GovJsonKey.CDNR.value: GovExcelSheetName.CDNR.value,
    GovJsonKey.CDNUR.value: GovExcelSheetName.CDNUR.value,
    GovJsonKey.AT.value: GovExcelSheetName.AT.value,
    GovJsonKey.TXP.value: GovExcelSheetName.TXP.value,
    GovJsonKey.HSN.value: GovExcelSheetName.HSN.value,
    GovJsonKey.DOC_ISSUE.value: GovExcelSheetName.DOC_ISSUE.value,
}


class GSTR1_B2B_InvoiceType(Enum):
    R = "Regular B2B"
    SEWP = "SEZ supplies with payment"
    SEWOP = "SEZ supplies without payment"
    DE = "Deemed Exp"


SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE = [
    GSTR1_SubCategory.HSN.value,
    GSTR1_SubCategory.DOC_ISSUE.value,
    GSTR1_SubCategory.SUPECOM_52.value,
    GSTR1_SubCategory.SUPECOM_9_5.value,
]

SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX = [
    GSTR1_SubCategory.B2B_REVERSE_CHARGE.value,
    *SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
]
>>>>>>> e2f1f3e2 (feat: GSTR-1 Beta for filing (#2112)):india_compliance/gst_india/utils/gstr_1/__init__.py
