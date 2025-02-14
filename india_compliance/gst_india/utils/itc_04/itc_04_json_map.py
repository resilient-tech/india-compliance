from india_compliance.gst_india.constants import UOM_MAP
from india_compliance.gst_india.utils.gstr_mapper_utils import GovDataMapper
from india_compliance.gst_india.utils.itc_04 import (
    GovDataField,
    GovDataField_SE,
    GovJsonKey,
    ITC04_DataField,
    ITC04_ItemField,
    ITC04JsonKey,
)

############################################################################################################
### Map Govt JSON to Internal Data Structure ###############################################################
############################################################################################################


class ITC04DataMapper(GovDataMapper):
    """
    GST Developer API Documentation for Returns - https://developer.gst.gov.in/apiportal/taxpayer/returns

    ITC-04 JSON format - https://developer.gst.gov.in/pages/apiportal/data/Returns/ITC04%20-%20Save/v1.2/ITC04%20-%20Save%20attributes.xlsx
    """

    DEFAULT_ITEM_AMOUNTS = {
        ITC04_ItemField.TAXABLE_VALUE.value: 0,
        ITC04_ItemField.IGST.value: 0,
        ITC04_ItemField.CGST.value: 0,
        ITC04_ItemField.SGST.value: 0,
        ITC04_ItemField.CESS_AMOUNT.value: 0,
    }

    FLOAT_FIELDS = {
        GovDataField.TAXABLE_VALUE.value,
        GovDataField.IGST.value,
        GovDataField.CGST.value,
        GovDataField.SGST.value,
        GovDataField.CESS_AMOUNT.value,
        GovDataField.QUANTITY.value,
    }

    def __init__(self):
        super().__init__()

    def map_uom(self, uom, *args):
        uom = uom.upper()

        if "-" in uom:
            return uom.split("-")[0]

        if uom in UOM_MAP:
            return f"{uom}-{UOM_MAP[uom]}"

        return f"OTH-{UOM_MAP.get('OTH')}"

    def convert_to_gov_data_format(self, input_data, **kwargs):
        output = []

        for invoice in input_data:
            output.append(self.format_data(invoice, for_gov=True))

        return output

    def format_item_for_gov(self, items, *args):
        return [self.format_data(item, for_gov=True) for item in items]


class FGReceived(ITC04DataMapper):
    CATEGORY = ITC04JsonKey.FG_RECEIVED.value

    KEY_MAPPING = {
        GovDataField.JOB_WORKER_GSTIN.value: ITC04_DataField.JOB_WORKER_GSTIN.value,
        GovDataField.JOB_WORKER_STATE_CODE.value: ITC04_DataField.JOB_WORKER_STATE_CODE.value,
        GovDataField.ITEMS.value: ITC04_DataField.ITEMS.value,
        GovDataField.ORIGINAL_CHALLAN_DATE.value: ITC04_DataField.ORIGINAL_CHALLAN_DATE.value,
        GovDataField.JOB_WORK_CHALLAN_DATE.value: ITC04_DataField.JOB_WORK_CHALLAN_DATE.value,
        GovDataField.NATURE_OF_JOB.value: ITC04_ItemField.NATURE_OF_JOB.value,
        GovDataField.UOM.value: ITC04_ItemField.UOM.value,
        GovDataField.QUANTITY.value: ITC04_ItemField.QUANTITY.value,
        GovDataField.DESCRIPTION.value: ITC04_ItemField.DESCRIPTION.value,
        GovDataField.FLAG.value: ITC04_DataField.FLAG.value,
        GovDataField.LOST_QUANTITY.value: ITC04_ItemField.LOST_QUANTITY.value,
        GovDataField.LOST_UOM.value: ITC04_ItemField.LOST_UOM.value,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.ITEMS.value: self.format_item_for_internal,
            GovDataField.UOM.value: self.map_uom,
            GovDataField.LOST_UOM.value: self.map_uom,
            GovDataField.JOB_WORKER_STATE_CODE.value: self.map_place_of_supply,
        }

        self.value_formatters_for_gov = {
            ITC04_DataField.ITEMS.value: self.format_item_for_gov,
            ITC04_ItemField.UOM.value: self.map_uom,
            ITC04_ItemField.LOST_UOM.value: self.map_uom,
            ITC04_DataField.JOB_WORKER_STATE_CODE.value: self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            original_challan_number = invoice.get(GovDataField.ITEMS.value)[0].get(
                GovDataField.ORIGINAL_CHALLAN_NUMBER.value
            )
            job_work_challan_number = invoice.get(GovDataField.ITEMS.value)[0].get(
                GovDataField.JOB_WORK_CHALLAN_NUMBER.value
            )
            output[f"{original_challan_number} - {job_work_challan_number}"] = (
                self.format_data(
                    invoice,
                    {
                        ITC04_DataField.ORIGINAL_CHALLAN_NUMBER.value: original_challan_number,
                        ITC04_DataField.JOB_WORK_CHALLAN_NUMBER.value: job_work_challan_number,
                    },
                )
            )

        return {self.CATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        output = []

        for invoice in input_data:
            self.original_challan_number = invoice.get(
                ITC04_DataField.ORIGINAL_CHALLAN_NUMBER.value
            )
            self.job_work_challan_number = invoice.get(
                ITC04_DataField.JOB_WORK_CHALLAN_NUMBER.value
            )
            output.append(self.format_data(invoice, for_gov=True))

        return output

    def format_item_for_internal(self, items, *args):
        return [
            {
                **self.format_data(item),
            }
            for item in items
        ]

    def format_item_for_gov(self, items, *args):
        return [
            self.format_data(
                item,
                {
                    GovDataField.ORIGINAL_CHALLAN_NUMBER.value: self.original_challan_number,
                    GovDataField.JOB_WORK_CHALLAN_NUMBER.value: self.job_work_challan_number,
                },
                for_gov=True,
            )
            for item in items
        ]


class RMSent(ITC04DataMapper):
    CATEGORY = ITC04JsonKey.RM_SENT.value

    KEY_MAPPING = {
        GovDataField.JOB_WORKER_GSTIN.value: ITC04_DataField.JOB_WORKER_GSTIN.value,
        GovDataField.JOB_WORKER_STATE_CODE.value: ITC04_DataField.JOB_WORKER_STATE_CODE.value,
        GovDataField_SE.ITEMS.value: ITC04_DataField.ITEMS.value,
        GovDataField_SE.ORIGINAL_CHALLAN_NUMBER.value: ITC04_DataField.ORIGINAL_CHALLAN_NUMBER.value,
        GovDataField_SE.ORIGINAL_CHALLAN_DATE.value: ITC04_DataField.ORIGINAL_CHALLAN_DATE.value,
        GovDataField.UOM.value: ITC04_ItemField.UOM.value,
        GovDataField.QUANTITY.value: ITC04_ItemField.QUANTITY.value,
        GovDataField.DESCRIPTION.value: ITC04_ItemField.DESCRIPTION.value,
        GovDataField.TAXABLE_VALUE.value: ITC04_ItemField.TAXABLE_VALUE.value,
        GovDataField.GOODS_TYPE.value: ITC04_ItemField.GOODS_TYPE.value,
        GovDataField.IGST.value: ITC04_ItemField.IGST.value,
        GovDataField.CGST.value: ITC04_ItemField.CGST.value,
        GovDataField.SGST.value: ITC04_ItemField.SGST.value,
        GovDataField.CESS_AMOUNT.value: ITC04_ItemField.CESS_AMOUNT.value,
        GovDataField.FLAG.value: ITC04_DataField.FLAG.value,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField_SE.ITEMS.value: self.format_item_for_internal,
            GovDataField.UOM.value: self.map_uom,
            GovDataField.JOB_WORKER_STATE_CODE.value: self.map_place_of_supply,
        }

        self.value_formatters_for_gov = {
            ITC04_DataField.ITEMS.value: self.format_item_for_gov,
            ITC04_ItemField.UOM.value: self.map_uom,
            ITC04_DataField.JOB_WORKER_STATE_CODE.value: self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            original_challan_number = invoice.get(
                GovDataField_SE.ORIGINAL_CHALLAN_NUMBER.value
            )

            invoice_level_data = self.format_data(invoice)

            self.update_totals(
                invoice_level_data,
                invoice_level_data.get(ITC04_DataField.ITEMS.value),
            )
            output[str(original_challan_number)] = invoice_level_data

        return {self.CATEGORY: output}

    def format_item_for_internal(self, items, *args):
        return [
            {
                **self.DEFAULT_ITEM_AMOUNTS.copy(),
                **self.format_data(item),
            }
            for item in items
        ]


CLASS_MAP = {
    GovJsonKey.FG_RECEIVED.value: FGReceived,
    GovJsonKey.RM_SENT.value: RMSent,
}

CATEGORY_MAP = {
    GovJsonKey.FG_RECEIVED.value: ITC04JsonKey.FG_RECEIVED.value,
    GovJsonKey.RM_SENT.value: ITC04JsonKey.RM_SENT.value,
}


def convert_to_internal_data_format(gov_data):
    """
    Converts Gov data format to internal data format for all categories
    """
    output = {}

    for category, mapper_class in CLASS_MAP.items():
        if not gov_data.get(category):
            continue

        output.update(
            mapper_class().convert_to_internal_data_format(gov_data.get(category))
        )

    return output


def convert_to_gov_data_format(internal_data: dict, company_gstin: str) -> dict:
    """
    converts internal data format to Gov data format for all categories
    """

    output = {}
    for category, mapper_class in CLASS_MAP.items():
        if not internal_data.get(CATEGORY_MAP.get(category)):
            continue

        output[category] = mapper_class().convert_to_gov_data_format(
            internal_data.get(CATEGORY_MAP.get(category)), company_gstin=company_gstin
        )

    return output
