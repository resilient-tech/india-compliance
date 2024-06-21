from enum import Enum


class GovJsonKey(Enum):
    """
    Categories / Keys as per Govt JSON file
    """

    TABLE5A = "table5A"
    TABLE5B = "table5B"


class GovDataField(Enum):
    COMPANY_GSTIN = "ctin"
    JOB_WORKER_STATE_CODE = "jw_stcd"
    ITEMS = "items"
    ORIGINAL_CAHLLAN_NUMBER = "o_chnum"
    ORIGINAL_CHALLAN_DATE = "o_chdt"
    CHALLAN_NUMBER = "jw2_chnum"
    CHALLAN_DATE = "jw2_chdt"
    NATURE_OF_JOB = "nat_jw"
    UOM = "uqc"
    QTY = "qty"
    DESCRIPTION = "desc"
    LOSS_UOM = "lwuqc"
    LOSS_QTY = "lwqty"


class ITC04_DataField(Enum):
    COMPANY_GSTIN = "company_gstin"
    JOB_WORKER_STATE_CODE = "jw_state_code"
    ITEMS = "items"
    ORIGINAL_CAHLLAN_NUMBER = "original_challan_number"
    ORIGINAL_CHALLAN_DATE = "original_challan_date"
    CHALLAN_NUMBER = "jw_challan_number"
    CHALLAN_DATE = "jw_challan_date"
    NATURE_OF_JOB = "nature_of_job"
    UOM = "uom"
    QTY = "qty"
    DESCRIPTION = "desc"
    LOSS_UOM = "loss_uom"
    LOSS_QTY = "loss_qty"
