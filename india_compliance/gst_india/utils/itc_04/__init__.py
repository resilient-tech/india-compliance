from enum import Enum


class GovJsonKey(Enum):
    """
    Categories / Keys as per Govt JSON file
    """

    TABLE5A = "table5A"
    STOCK_ENTRY = "m2jw"


class ITC04JsonKey(Enum):
    """
    Categories / Keys as per Internal JSON file
    """

    TABLE5A = "Table 5A"
    STOCK_ENTRY = "Stock Entry"


class GovDataField(Enum):
    COMPANY_GSTIN = "ctin"
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
    LOSS_UOM = "lwuqc"
    LOSS_QTY = "lwqty"
    TAXABLE_VALUE = "txval"
    GOODS_TYPE = "goods_ty"
    IGST = "tx_i"
    CGST = "tx_c"
    SGST = "tx_s"
    CESS_AMOUNT = "tx_cs"
    FLAG = "flag"


class GovDataField_SE(Enum):
    ITEMS = "itms"
    ORIGINAL_CHALLAN_NUMBER = "chnum"
    ORIGINAL_CHALLAN_DATE = "chdt"


class ITC04_DataField(Enum):
    COMPANY_GSTIN = "company_gstin"
    JOB_WORKER_STATE_CODE = "jw_state_code"
    ITEMS = "items"
    ORIGINAL_CHALLAN_NUMBER = "original_challan_number"
    ORIGINAL_CHALLAN_DATE = "original_challan_date"
    JOB_WORK_CHALLAN_NUMBER = "jw_challan_number"
    JOB_WORK_CHALLAN_DATE = "jw_challan_date"
    NATURE_OF_JOB = "nature_of_job"
    UOM = "uom"
    QUANTITY = "qty"
    DESCRIPTION = "desc"
    LOSS_UOM = "loss_uom"
    LOSS_QTY = "loss_qty"
    TAXABLE_VALUE = "taxable_value"
    GOODS_TYPE = "goods_type"
    IGST = "igst_rate"
    CGST = "cgst_rate"
    SGST = "sgst_rate"
    CESS_AMOUNT = "cess_amount"
    FLAG = "flag"
