from frappe.utils import flt

from india_compliance.gst_india.constants import STATE_NUMBERS


class GovDataMapper:
    KEY_MAPPING = {}
    FLOAT_FIELDS = {}
    DISCARD_IF_ZERO_FIELDS = {}
    TOTAL_DEFAULTS = {}
    DEFAULT_ITEM_AMOUNTS = {}

    def __init__(self):
        self.set_total_defaults()

        self.value_formatters_for_internal = {}
        self.value_formatters_for_gov = {}

        # value formatting constants
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
            for key, value in default_data.items():
                if not (value or value == 0):
                    continue

                output[key] = value

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

            if new_key in self.DISCARD_IF_ZERO_FIELDS and not invoice_data_value:
                continue

            if not (invoice_data_value or invoice_data_value == 0):
                # continue if value is None or empty object
                continue

            value_formatter = value_formatters.get(old_key)

            if callable(value_formatter):
                output[new_key] = value_formatter(invoice_data_value, data)
            else:
                output[new_key] = invoice_data_value

            if new_key in self.FLOAT_FIELDS:
                output[new_key] = flt(output[new_key], 2)

        return output

    # common utils

    def update_totals(self, invoice, items):
        """
        Update item totals to the invoice row
        """
        total_data = self.TOTAL_DEFAULTS.copy()

        for item in items:
            for field, value in item.items():
                total_field = f"total_{field}"

                if total_field not in total_data:
                    continue

                invoice[total_field] = invoice.setdefault(total_field, 0) + value

    def set_total_defaults(self):
        self.TOTAL_DEFAULTS = {
            f"total_{key}": 0 for key in self.DEFAULT_ITEM_AMOUNTS.keys()
        }

    def reverse_dict(self, data):
        return {v: k for k, v in data.items()}

    # common value formatters
    def map_place_of_supply(self, pos, *args):
        if pos.isnumeric():
            return f"{pos}-{self.STATE_NUMBERS.get(pos)}"

        return pos.split("-")[0]
