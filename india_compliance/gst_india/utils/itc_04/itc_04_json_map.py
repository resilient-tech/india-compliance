from india_compliance.gst_india.constants import STATE_NUMBERS, UOM_MAP
from india_compliance.gst_india.utils.gstr_mapper_utils import GSTRDataMapper
from india_compliance.gst_india.utils.itc_04 import (
    GovDataField,
    GovJsonKey,
    ITC04_DataField,
)

############################################################################################################
### Map Govt JSON to Internal Data Structure ###############################################################
############################################################################################################


class GovDataMapper:
    """
    GST Developer API Documentation for Returns - https://developer.gst.gov.in/apiportal/taxpayer/returns

    ITC-04 JSON format - https://developer.gst.gov.in/pages/apiportal/data/Returns/ITC04%20-%20Save/v1.2/ITC04%20-%20Save%20attributes.xlsx
    """

    KEY_MAPPING = {}

    def __init__(self):
        self.value_formatters_for_internal = {}
        self.value_formatters_for_gov = {}
        self.STATE_NUMBERS = self.reverse_dict(STATE_NUMBERS)

    def format_data(
        self, data: dict, default_data: dict = None, for_gov: bool = False
    ) -> dict:
        """
        Objective: Convert Object from one format to another.
            eg: Govt JSON to Internal Data Structure

        Args:
            data (dict): Data to be converted
            default_data (dict, optional): Default Data to be added. Hardcoded values.
            for_gov (bool, optional): If the data is to be converted to Govt JSON. Defaults to False.
                else it will be converted to Internal Data Structure.

        Steps:
            1. Use key mapping to map the keys from one format to another.
            2. Use value formatters to format the values of the keys.
            3. Round values
        """
        output = {}

        if default_data:
            output.update(default_data)

        key_mapping = self.KEY_MAPPING.copy()

        if for_gov:
            key_mapping = self.reverse_dict(key_mapping)

        value_formatters = (
            self.value_formatters_for_gov
            if for_gov
            else self.value_formatters_for_internal
        )

        for old_key, new_key in key_mapping.items():
            invoice_data_value = data.get(old_key, "")

            if not for_gov and old_key == "flag":
                continue

            if not (invoice_data_value or invoice_data_value == 0):
                # continue if value is None or empty object
                continue

            value_formatter = value_formatters.get(old_key)

            if callable(value_formatter):
                output[new_key] = value_formatter(invoice_data_value)
            else:
                output[new_key] = invoice_data_value

        return output

    def map_uom(self, uom):
        uom = uom.upper()

        if "-" in uom:
            return uom.split("-")[0]

        if uom in UOM_MAP:
            return f"{uom}-{UOM_MAP[uom]}"

        return f"OTH-{UOM_MAP.get('OTH')}"

    def map_place_of_supply(self, state_code):
        if state_code.isnumeric():
            return f"{state_code}-{self.STATE_NUMBERS.get(state_code)}"

        return state_code.split("-")[0]

    def reverse_dict(self, data):
        return {v: k for k, v in data.items()}


class TABLE5A(GovDataMapper):
    CATEGORY = GovJsonKey.TABLE5A.value

    KEY_MAPPING = {
        GovDataField.COMPANY_GSTIN.value: ITC04_DataField.COMPANY_GSTIN.value,
        GovDataField.JOB_WORKER_STATE_CODE.value: ITC04_DataField.JOB_WORKER_STATE_CODE.value,
        GovDataField.ITEMS.value: ITC04_DataField.ITEMS.value,
        GovDataField.ORIGINAL_CAHLLAN_NUMBER.value: ITC04_DataField.ORIGINAL_CAHLLAN_NUMBER.value,
        GovDataField.ORIGINAL_CHALLAN_DATE.value: ITC04_DataField.ORIGINAL_CHALLAN_DATE.value,
        GovDataField.CHALLAN_NUMBER.value: ITC04_DataField.CHALLAN_NUMBER.value,
        GovDataField.CHALLAN_DATE.value: ITC04_DataField.CHALLAN_DATE.value,
        GovDataField.NATURE_OF_JOB.value: ITC04_DataField.NATURE_OF_JOB.value,
        GovDataField.UOM.value: ITC04_DataField.UOM.value,
        GovDataField.QTY.value: ITC04_DataField.QTY.value,
        GovDataField.DESCRIPTION.value: ITC04_DataField.DESCRIPTION.value,
        GovDataField.LOSS_UOM.value: ITC04_DataField.LOSS_UOM.value,
        GovDataField.LOSS_QTY.value: ITC04_DataField.LOSS_QTY.value,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.ITEMS.value: self.format_item_for_internal,
            GovDataField.UOM.value: self.map_uom,
            GovDataField.LOSS_UOM.value: self.map_uom,
            GovDataField.JOB_WORKER_STATE_CODE.value: self.map_place_of_supply,
        }

        self.value_formatters_for_gov = {
            ITC04_DataField.ITEMS.value: self.format_item_for_gov,
            ITC04_DataField.UOM.value: self.map_uom,
            ITC04_DataField.LOSS_UOM.value: self.map_uom,
            ITC04_DataField.JOB_WORKER_STATE_CODE.value: self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            original_challan_number = invoice.get(GovDataField.ITEMS.value)[0].get(
                GovDataField.ORIGINAL_CAHLLAN_NUMBER.value
            )
            output[original_challan_number] = self.format_data(invoice)

        return {self.CATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        output = []

        for invoice in input_data:
            formatted_data = self.format_data(invoice, for_gov=True)

            output.append(formatted_data)

        return output

    def format_item_for_internal(self, items):
        return [
            {
                **self.format_data(item),
            }
            for item in items
        ]

    def format_item_for_gov(self, items, *args):
        return [
            {
                **self.format_data(item, for_gov=True),
            }
            for item in items
        ]


class TABLE5B(TABLE5A):
    CATEGORY = GovJsonKey.TABLE5B.value

    def __init__(self):
        super().__init__()


class ITC04DataMapper(GSTRDataMapper):
    CLASS_MAP = {
        GovJsonKey.TABLE5A.value: TABLE5A,
        GovJsonKey.TABLE5B.value: TABLE5B,
    }
