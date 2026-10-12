"""ITC-04 constants. Pure, no frappe. (Fields are Enums here, matching source access via .value.)"""

from enum import Enum


class JsonKey(Enum):
    # portal keys
    FG_RECEIVED = "table5A"
    RM_SENT = "m2jw"


class Category(Enum):
    # internal section names
    FG_RECEIVED = "FG Received"
    RM_SENT = "RM Sent"


class RawField(Enum):
    JOB_WORKER_GSTIN = "ctin"
    JOB_WORKER_STATE_CODE = "jw_stcd"
    ITEMS = "items"
    ORIGINAL_CHALLAN_NUMBER = "o_chnum"
    ORIGINAL_CHALLAN_DATE = "o_chdt"
    JOB_WORK_CHALLAN_NUMBER = "jw2_chnum"
    JOB_WORK_CHALLAN_DATE = "jw2_chdt"
    NATURE_OF_JOB = "nat_jw"
    UOM = "uqc"
    QUANTITY = "qty"
    DESCRIPTION = "desc"
    TAXABLE_VALUE = "txval"
    GOODS_TYPE = "goods_ty"
    IGST = "tx_i"
    CGST = "tx_c"
    SGST = "tx_s"
    CESS_AMOUNT = "tx_cs"
    FLAG = "flag"
    LOST_QUANTITY = "lwqty"
    LOST_UOM = "lwuqc"


class RawFieldSE(Enum):
    # RM-sent overrides
    ITEMS = "itms"
    ORIGINAL_CHALLAN_NUMBER = "chnum"
    ORIGINAL_CHALLAN_DATE = "chdt"


class DocField(Enum):
    JOB_WORKER_GSTIN = "supplier_gstin"
    JOB_WORKER_STATE_CODE = "jw_state_code"
    ITEMS = "items"
    ORIGINAL_CHALLAN_NUMBER = "original_challan_number"
    ORIGINAL_CHALLAN_DATE = "original_challan_date"
    JOB_WORK_CHALLAN_NUMBER = "jw_challan_number"
    JOB_WORK_CHALLAN_DATE = "jw_challan_date"
    TAXABLE_VALUE = "total_taxable_value"
    IGST = "total_igst_rate"
    CGST = "total_cgst_rate"
    SGST = "total_sgst_rate"
    CESS_AMOUNT = "total_cess_amount"
    FLAG = "flag"


class ItemField(Enum):
    NATURE_OF_JOB = "nature_of_job"
    UOM = "uom"
    QUANTITY = "qty"
    DESCRIPTION = "desc"
    TAXABLE_VALUE = "taxable_value"
    GOODS_TYPE = "goods_type"
    IGST = "igst_rate"
    CGST = "cgst_rate"
    SGST = "sgst_rate"
    CESS_AMOUNT = "cess_amount"
    LOST_QUANTITY = "lost_qty"
    LOST_UOM = "lost_uom"
