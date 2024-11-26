from datetime import datetime

import frappe
from frappe.utils import flt

from india_compliance.gst_india.constants import STATE_NUMBERS, UOM_MAP
from india_compliance.gst_india.report.gstr_1.gstr_1 import (
    GSTR1DocumentIssuedSummary,
    GSTR11A11BData,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.gst_india.utils.__init__ import get_party_for_gstin
from india_compliance.gst_india.utils.gstr_1 import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    SUB_CATEGORY_GOV_CATEGORY_MAPPING,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
    GovDataField,
    GovJsonKey,
    GSTR1_B2B_InvoiceType,
    GSTR1_Category,
    GSTR1_DataField,
    GSTR1_ItemField,
    GSTR1_SubCategory,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Invoices

############################################################################################################
### Map Govt JSON to Internal Data Structure ###############################################################
############################################################################################################


class GovDataMapper:
    """
    GST Developer API Documentation for Returns - https://developer.gst.gov.in/apiportal/taxpayer/returns

    GSTR-1 JSON format - https://developer.gst.gov.in/pages/apiportal/data/Returns/GSTR1%20-%20Save%20GSTR1%20data/v4.0/GSTR1%20-%20Save%20GSTR1%20data%20attributes.xlsx
    """

    KEY_MAPPING = {}
    # default item amounts
    DEFAULT_ITEM_AMOUNTS = {
        GSTR1_ItemField.TAXABLE_VALUE.value: 0,
        GSTR1_ItemField.IGST.value: 0,
        GSTR1_ItemField.CGST.value: 0,
        GSTR1_ItemField.SGST.value: 0,
        GSTR1_ItemField.CESS.value: 0,
    }

    FLOAT_FIELDS = {
        GovDataField.DOC_VALUE.value,
        GovDataField.TAXABLE_VALUE.value,
        GovDataField.DIFF_PERCENTAGE.value,
        GovDataField.IGST.value,
        GovDataField.CGST.value,
        GovDataField.SGST.value,
        GovDataField.CESS.value,
        GovDataField.NET_TAXABLE_VALUE.value,
        GovDataField.EXEMPTED_AMOUNT.value,
        GovDataField.NIL_RATED_AMOUNT.value,
        GovDataField.NON_GST_AMOUNT.value,
        GovDataField.QUANTITY.value,
        GovDataField.ADVANCE_AMOUNT.value,
    }

    DISCARD_IF_ZERO_FIELDS = {
        GovDataField.DIFF_PERCENTAGE.value,
    }

    def __init__(self):
        self.set_total_defaults()

        self.value_formatters_for_internal = {}
        self.value_formatters_for_gov = {}
        self.gstin_party_map = {}
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

    def format_item_for_internal(self, items, *args):
        return [
            {
                **self.DEFAULT_ITEM_AMOUNTS.copy(),
                **self.format_data(item.get(GovDataField.ITEM_DETAILS.value, {})),
            }
            for item in items
        ]

    def format_item_for_gov(self, items, *args):
        return [
            {
                GovDataField.INDEX.value: index + 1,
                GovDataField.ITEM_DETAILS.value: self.format_data(item, for_gov=True),
            }
            for index, item in enumerate(items)
        ]

    def guess_customer_name(self, gstin):
        if party := self.gstin_party_map.get(gstin):
            return party

        return self.gstin_party_map.setdefault(
            gstin, get_party_for_gstin(gstin, "Customer") or "Unknown"
        )

    def format_date_for_internal(self, date, *args):
        return datetime.strptime(date, "%d-%m-%Y").strftime("%Y-%m-%d")

    def format_date_for_gov(self, date, *args):
        return datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")


class B2B(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        [
            {
                'ctin': '24AANFA2641L1ZF',
                'inv': [
                    {
                        'inum': 'S008400',
                        'itms': [
                            {'num': 1, 'itm_det': {'txval': 10000,
                                ...
                            }}
                        ]
                    }
                    ...
                ]
            }
        ]

    Internal Data Format:
        {
            'B2B Regular': {'S008400': {
                    'customer_gstin': '24AANFA2641L1ZF',
                    'document_number': 'S008400',
                    'items': [
                        {
                            'taxable_value': 10000,
                            ...
                        }
                    ],
                    ...
            }}
        }

    """

    KEY_MAPPING = {
        # GovDataFields.CUST_GSTIN.value: DataFields.CUST_GSTIN.value,
        # GovDataFields.INVOICES.value: "invoices",
        GovDataField.FLAG.value: "flag",
        GovDataField.DOC_NUMBER.value: GSTR1_DataField.DOC_NUMBER.value,
        GovDataField.DOC_DATE.value: GSTR1_DataField.DOC_DATE.value,
        GovDataField.DOC_VALUE.value: GSTR1_DataField.DOC_VALUE.value,
        GovDataField.POS.value: GSTR1_DataField.POS.value,
        GovDataField.REVERSE_CHARGE.value: GSTR1_DataField.REVERSE_CHARGE.value,
        # GovDataFields.ECOMMERCE_GSTIN.value: GSTR1_DataFields.ECOMMERCE_GSTIN.value,
        GovDataField.INVOICE_TYPE.value: GSTR1_DataField.DOC_TYPE.value,
        GovDataField.DIFF_PERCENTAGE.value: GSTR1_DataField.DIFF_PERCENTAGE.value,
        GovDataField.ITEMS.value: GSTR1_DataField.ITEMS.value,
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        GovDataField.ITEM_DETAILS.value: GSTR1_ItemField.ITEM_DETAILS.value,
        GovDataField.TAX_RATE.value: GSTR1_ItemField.TAX_RATE.value,
        GovDataField.TAXABLE_VALUE.value: GSTR1_ItemField.TAXABLE_VALUE.value,
        GovDataField.IGST.value: GSTR1_ItemField.IGST.value,
        GovDataField.CGST.value: GSTR1_ItemField.CGST.value,
        GovDataField.SGST.value: GSTR1_ItemField.SGST.value,
        GovDataField.CESS.value: GSTR1_ItemField.CESS.value,
    }

    # value formatting constants
    DOCUMENT_CATEGORIES = {
        "R": GSTR1_B2B_InvoiceType.R.value,
        "SEWP": GSTR1_B2B_InvoiceType.SEWP.value,
        "SEWOP": GSTR1_B2B_InvoiceType.SEWOP.value,
        "DE": GSTR1_B2B_InvoiceType.DE.value,
    }

    SUBCATEGORIES = {
        # "B2B": GSTR1_SubCategories.B2B_REGULAR.value,
        # "B2B": GSTR1_SubCategories.B2B_REVERSE_CHARGE.value,
        "SEWP": GSTR1_SubCategory.SEZWP.value,
        "SEWOP": GSTR1_SubCategory.SEZWOP.value,
        "DE": GSTR1_SubCategory.DE.value,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.ITEMS.value: self.format_item_for_internal,
            GovDataField.INVOICE_TYPE.value: self.document_category_mapping,
            GovDataField.POS.value: self.map_place_of_supply,
            GovDataField.DOC_DATE.value: self.format_date_for_internal,
        }

        self.value_formatters_for_gov = {
            GSTR1_DataField.ITEMS.value: self.format_item_for_gov,
            GSTR1_DataField.DOC_TYPE.value: self.document_category_mapping,
            GSTR1_DataField.POS.value: self.map_place_of_supply,
            GSTR1_DataField.DOC_DATE.value: self.format_date_for_gov,
        }

    def convert_to_internal_data_format(self, input_data):
        """
        Objective: Convert Govt JSON to Internal Data Structure
        Args:
            input_data (list): Govt JSON Data
        Returns:
            dict: Internal Data Structure
        """

        output = {}

        for customer_data in input_data:
            customer_gstin = customer_data.get(GovDataField.CUST_GSTIN.value)

            default_invoice_data = {
                GSTR1_DataField.CUST_GSTIN.value: customer_gstin,
                GSTR1_DataField.CUST_NAME.value: self.guess_customer_name(
                    customer_gstin
                ),
                GSTR1_DataField.ERROR_CD.value: customer_data.get(
                    GovDataField.ERROR_CD.value
                ),
                GSTR1_DataField.ERROR_MSG.value: customer_data.get(
                    GovDataField.ERROR_MSG.value
                ),
            }

            for invoice in customer_data.get(GovDataField.INVOICES.value):
                invoice_data = self.format_data(invoice, default_invoice_data)
                self.update_totals(
                    invoice_data, invoice_data.get(GSTR1_DataField.ITEMS.value)
                )

                subcategory_data = output.setdefault(
                    self.get_document_subcategory(invoice), {}
                )
                subcategory_data[invoice_data[GSTR1_DataField.DOC_NUMBER.value]] = (
                    invoice_data
                )

        return output

    def convert_to_gov_data_format(self, input_data, **kwargs):
        """
        Objective: Convert Internal Data Structure to Govt JSON
        Args:
            input_data (dict): Internal Data Structure
        Returns:
            list: Govt JSON Data
        """
        customer_data = {}

        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)

        for invoice in input_data:
            customer = customer_data.setdefault(
                invoice[GSTR1_DataField.CUST_GSTIN.value],
                {
                    GovDataField.CUST_GSTIN.value: invoice[
                        GSTR1_DataField.CUST_GSTIN.value
                    ],
                    GovDataField.INVOICES.value: [],
                },
            )

            customer[GovDataField.INVOICES.value].append(
                self.format_data(invoice, for_gov=True)
            )

        return list(customer_data.values())

    def get_document_subcategory(self, invoice_data):
        if invoice_data.get(GovDataField.INVOICE_TYPE.value) in self.SUBCATEGORIES:
            return self.SUBCATEGORIES[invoice_data[GovDataField.INVOICE_TYPE.value]]

        if invoice_data.get(GovDataField.REVERSE_CHARGE.value) == "Y":
            return GSTR1_SubCategory.B2B_REVERSE_CHARGE.value

        return GSTR1_SubCategory.B2B_REGULAR.value

    # value formatting methods

    def document_category_mapping(self, sub_category, data):
        return self.DOCUMENT_CATEGORIES.get(sub_category, sub_category)


class B2CL(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        {
            'pos': '05',
            'inv': [
                {
                    'inum': '92661',
                    'itms': [
                        {'num': 1,'itm_det': {'txval': 10000,
                            ...
                        }},
                        ...
                    ]
                }
                ...
            ],
            ...
        }

    Internal Data Format:

        {
            'B2C (Large)': {
                '92661': {
                    'place_of_supply': '05-Uttarakhand',
                    'document_number': '92661',
                    'items': [
                        {
                            'taxable_value': 10000,
                            ...
                        },
                        ...
                    ],
                    'total_taxable_value': 10000,
                    ...
                }
                ...
            }
        }
    """

    DOCUMENT_CATEGORY = "B2C (Large)"
    SUBCATEGORY = GSTR1_SubCategory.B2CL.value
    DEFAULT_ITEM_AMOUNTS = {
        GSTR1_ItemField.TAXABLE_VALUE.value: 0,
        GSTR1_ItemField.IGST.value: 0,
        GSTR1_ItemField.CESS.value: 0,
    }
    KEY_MAPPING = {
        # GovDataFields.POS.value: DataFields.POS.value,
        # GovDataFields.INVOICES.value: "invoices",
        GovDataField.FLAG.value: "flag",
        GovDataField.DOC_NUMBER.value: GSTR1_DataField.DOC_NUMBER.value,
        GovDataField.DOC_DATE.value: GSTR1_DataField.DOC_DATE.value,
        GovDataField.DOC_VALUE.value: GSTR1_DataField.DOC_VALUE.value,
        # GovDataFields.ECOMMERCE_GSTIN.value: GSTR1_DataFields.ECOMMERCE_GSTIN.value,
        GovDataField.DIFF_PERCENTAGE.value: GSTR1_DataField.DIFF_PERCENTAGE.value,
        GovDataField.ITEMS.value: GSTR1_DataField.ITEMS.value,
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        GovDataField.ITEM_DETAILS.value: GSTR1_ItemField.ITEM_DETAILS.value,
        GovDataField.TAX_RATE.value: GSTR1_ItemField.TAX_RATE.value,
        GovDataField.TAXABLE_VALUE.value: GSTR1_ItemField.TAXABLE_VALUE.value,
        GovDataField.IGST.value: GSTR1_ItemField.IGST.value,
        GovDataField.CESS.value: GSTR1_ItemField.CESS.value,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.ITEMS.value: self.format_item_for_internal,
            GovDataField.DOC_DATE.value: self.format_date_for_internal,
        }
        self.value_formatters_for_gov = {
            GSTR1_DataField.ITEMS.value: self.format_item_for_gov,
            GSTR1_DataField.DOC_DATE.value: self.format_date_for_gov,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for pos_data in input_data:
            pos = self.map_place_of_supply(pos_data.get(GovDataField.POS.value))

            default_invoice_data = {
                GSTR1_DataField.POS.value: pos,
                GSTR1_DataField.DOC_TYPE.value: self.DOCUMENT_CATEGORY,
                GSTR1_DataField.ERROR_CD.value: pos_data.get(
                    GovDataField.ERROR_CD.value
                ),
                GSTR1_DataField.ERROR_MSG.value: pos_data.get(
                    GovDataField.ERROR_MSG.value
                ),
            }

            for invoice in pos_data.get(GovDataField.INVOICES.value):
                invoice_level_data = self.format_data(invoice, default_invoice_data)
                self.update_totals(
                    invoice_level_data,
                    invoice_level_data.get(GSTR1_DataField.ITEMS.value),
                )

                output[invoice_level_data[GSTR1_DataField.DOC_NUMBER.value]] = (
                    invoice_level_data
                )

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        pos_data = {}

        for invoice in input_data:
            pos = pos_data.setdefault(
                invoice[GSTR1_DataField.POS.value],
                {
                    GovDataField.POS.value: self.map_place_of_supply(
                        invoice[GSTR1_DataField.POS.value]
                    ),
                    GovDataField.INVOICES.value: [],
                },
            )

            pos[GovDataField.INVOICES.value].append(
                self.format_data(invoice, for_gov=True)
            )

        return list(pos_data.values())


class Exports(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        {
            'exp_typ': 'WPAY',
            'inv': [
                {
                    'inum': '81542',
                    'val': 995048.36,
                    'itms': [
                        {
                            'txval': 10000,
                            ...
                        },
                        ...
                    ],
                    ...
                },
                ...
            ]
        }

    Internal Data Format:
        {
            'Export With Payment of Tax': {
                '81542': {
                    'document_number': '81542',
                    'document_value': 995048.36,
                    'items': [
                        {
                            'taxable_value': 10000,
                            ...
                        },
                        ...
                    ],
                    'total_taxable_value': 10000,
                    ...
                },
                ...
            }
        }
    """

    DEFAULT_ITEM_AMOUNTS = {
        GSTR1_ItemField.TAXABLE_VALUE.value: 0,
        GSTR1_ItemField.IGST.value: 0,
        GSTR1_ItemField.CESS.value: 0,
    }
    KEY_MAPPING = {
        # GovDataFields.POS.value: DataFields.POS.value,
        # GovDataFields.INVOICES.value: "invoices",
        GovDataField.FLAG.value: "flag",
        # GovDataFields.EXPORT_TYPE.value: DataFields.DOC_TYPE.value,
        GovDataField.DOC_NUMBER.value: GSTR1_DataField.DOC_NUMBER.value,
        GovDataField.DOC_DATE.value: GSTR1_DataField.DOC_DATE.value,
        GovDataField.DOC_VALUE.value: GSTR1_DataField.DOC_VALUE.value,
        GovDataField.SHIPPING_PORT_CODE.value: GSTR1_DataField.SHIPPING_PORT_CODE.value,
        GovDataField.SHIPPING_BILL_NUMBER.value: GSTR1_DataField.SHIPPING_BILL_NUMBER.value,
        GovDataField.SHIPPING_BILL_DATE.value: GSTR1_DataField.SHIPPING_BILL_DATE.value,
        GovDataField.ITEMS.value: GSTR1_DataField.ITEMS.value,
        GovDataField.TAXABLE_VALUE.value: GSTR1_ItemField.TAXABLE_VALUE.value,
        GovDataField.TAX_RATE.value: GSTR1_ItemField.TAX_RATE.value,
        GovDataField.IGST.value: GSTR1_ItemField.IGST.value,
        GovDataField.CESS.value: GSTR1_ItemField.CESS.value,
    }

    SUBCATEGORIES = {
        "WPAY": GSTR1_SubCategory.EXPWP.value,
        "WOPAY": GSTR1_SubCategory.EXPWOP.value,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.ITEMS.value: self.format_item_for_internal,
            GovDataField.DOC_DATE.value: self.format_date_for_internal,
            GovDataField.SHIPPING_BILL_DATE.value: self.format_date_for_internal,
        }
        self.value_formatters_for_gov = {
            GSTR1_DataField.ITEMS.value: self.format_item_for_gov,
            GSTR1_DataField.DOC_DATE.value: self.format_date_for_gov,
            GSTR1_DataField.SHIPPING_BILL_DATE.value: self.format_date_for_gov,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for export_category in input_data:
            document_type = export_category.get(GovDataField.EXPORT_TYPE.value)
            subcategory_data = output.setdefault(
                self.SUBCATEGORIES.get(document_type, document_type), {}
            )

            default_invoice_data = {
                GSTR1_DataField.DOC_TYPE.value: document_type,
                GSTR1_DataField.ERROR_CD.value: export_category.get(
                    GovDataField.ERROR_CD.value
                ),
                GSTR1_DataField.ERROR_MSG.value: export_category.get(
                    GovDataField.ERROR_MSG.value
                ),
            }

            for invoice in export_category.get(GovDataField.INVOICES.value):
                invoice_level_data = self.format_data(invoice, default_invoice_data)

                self.update_totals(
                    invoice_level_data,
                    invoice_level_data.get(GSTR1_DataField.ITEMS.value),
                )
                subcategory_data[
                    invoice_level_data[GSTR1_DataField.DOC_NUMBER.value]
                ] = invoice_level_data

        return output

    def convert_to_gov_data_format(self, input_data, **kwargs):
        export_category_wise_data = {}

        for invoice in input_data:
            export_category = export_category_wise_data.setdefault(
                invoice[GSTR1_DataField.DOC_TYPE.value],
                {
                    GovDataField.EXPORT_TYPE.value: invoice[
                        GSTR1_DataField.DOC_TYPE.value
                    ],
                    GovDataField.INVOICES.value: [],
                },
            )

            export_category[GovDataField.INVOICES.value].append(
                self.format_data(invoice, for_gov=True)
            )

        return list(export_category_wise_data.values())

    def format_item_for_internal(self, items, *args):
        return [
            {
                **self.DEFAULT_ITEM_AMOUNTS.copy(),
                **self.format_data(item),
            }
            for item in items
        ]

    def format_item_for_gov(self, items, *args):
        return [self.format_data(item, for_gov=True) for item in items]


class B2CS(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        [
            {
                'typ': 'OE',
                'pos': '05',
                'txval': 110,
                ...
            },
            ...
        ]

    Internal Data Format:
        {
            'B2C (Others)': {
                '05-Uttarakhand - 5.0': [
                    {
                        'total_taxable_value': 110,
                        'document_type': 'OE',
                        'place_of_supply': '05-Uttarakhand',
                        ...
                    },
                    ...
                ],
                ...
            }
        }
    """

    SUBCATEGORY = GSTR1_SubCategory.B2CS.value
    KEY_MAPPING = {
        GovDataField.FLAG.value: "flag",
        # GovDataFields.SUPPLY_TYPE.value: "supply_type",
        GovDataField.TAXABLE_VALUE.value: GSTR1_DataField.TAXABLE_VALUE.value,
        GovDataField.TYPE.value: GSTR1_DataField.DOC_TYPE.value,
        # GovDataFields.ECOMMERCE_GSTIN.value: GSTR1_DataFields.ECOMMERCE_GSTIN.value,
        GovDataField.DIFF_PERCENTAGE.value: GSTR1_DataField.DIFF_PERCENTAGE.value,
        GovDataField.POS.value: GSTR1_DataField.POS.value,
        GovDataField.TAX_RATE.value: GSTR1_DataField.TAX_RATE.value,
        GovDataField.IGST.value: GSTR1_DataField.IGST.value,
        GovDataField.CGST.value: GSTR1_DataField.CGST.value,
        GovDataField.SGST.value: GSTR1_DataField.SGST.value,
        GovDataField.CESS.value: GSTR1_DataField.CESS.value,
        GovDataField.ERROR_CD.value: GSTR1_DataField.ERROR_CD.value,
        GovDataField.ERROR_MSG.value: GSTR1_DataField.ERROR_MSG.value,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.ITEMS.value: self.format_item_for_internal,
            GovDataField.POS.value: self.map_place_of_supply,
        }
        self.value_formatters_for_gov = {
            GSTR1_DataField.ITEMS.value: self.format_item_for_gov,
            GSTR1_DataField.POS.value: self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)

            output.setdefault(
                " - ".join(
                    (
                        invoice_data.get(GSTR1_DataField.POS.value, ""),
                        str(flt(invoice_data.get(GSTR1_DataField.TAX_RATE.value, ""))),
                        # invoice_data.get(GSTR1_DataFields.ECOMMERCE_GSTIN.value, ""),
                    )
                ),
                [],
            ).append(invoice_data)

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        self.company_gstin = kwargs.get("company_gstin", "")
        return [self.format_data(invoice, for_gov=True) for invoice in input_data]

    def format_data(self, data, default_data=None, for_gov=False):
        data = super().format_data(data, default_data, for_gov)
        if not for_gov:
            return data

        data[GovDataField.SUPPLY_TYPE.value] = (
            "INTRA"
            if data[GovDataField.POS.value] == self.company_gstin[:2]
            else "INTER"
        )
        return data


class NilRated(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        {
            'inv': [
                {
                    'sply_ty': 'INTRB2B',
                    'expt_amt': 123.45,
                    'nil_amt': 1470.85,
                    'ngsup_amt': 1258.5
                }
            ]
        }

    Internal Data Format:
        {
            'Nil-Rated, Exempted, Non-GST': {
                'Inter-State supplies to registered persons': [
                    {
                        'document_type': 'Inter-State supplies to registered persons',
                        'exempted_amount': 123.45,
                        'nil_rated_amount': 1470.85,
                        'non_gst_amount': 1258.5,
                        'total_taxable_value': 2852.8
                    }
                ]
            }
        }
    """

    SUBCATEGORY = GSTR1_SubCategory.NIL_EXEMPT.value
    KEY_MAPPING = {
        GovDataField.SUPPLY_TYPE.value: GSTR1_DataField.DOC_TYPE.value,
        GovDataField.EXEMPTED_AMOUNT.value: GSTR1_DataField.EXEMPTED_AMOUNT.value,
        GovDataField.NIL_RATED_AMOUNT.value: GSTR1_DataField.NIL_RATED_AMOUNT.value,
        GovDataField.NON_GST_AMOUNT.value: GSTR1_DataField.NON_GST_AMOUNT.value,
    }

    DOCUMENT_CATEGORIES = {
        "INTRB2B": "Inter-State supplies to registered persons",
        "INTRB2C": "Inter-State supplies to unregistered persons",
        "INTRAB2B": "Intra-State supplies to registered persons",
        "INTRAB2C": "Intra-State supplies to unregistered persons",
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.SUPPLY_TYPE.value: self.document_category_mapping
        }
        self.value_formatters_for_gov = {
            GSTR1_DataField.DOC_TYPE.value: self.document_category_mapping
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        default_data = {
            GSTR1_DataField.ERROR_CD.value: input_data.get(GovDataField.ERROR_CD.value),
            GSTR1_DataField.ERROR_MSG.value: input_data.get(
                GovDataField.ERROR_MSG.value
            ),
        }

        for invoice in input_data[GovDataField.INVOICES.value]:
            invoice_data = self.format_data(invoice, default_data)

            if not invoice_data:
                continue

            output.setdefault(
                invoice_data.get(GSTR1_DataField.DOC_TYPE.value), []
            ).append(invoice_data)

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)

        return {
            GovDataField.INVOICES.value: [
                self.format_data(invoice, for_gov=True) for invoice in input_data
            ]
        }

    def format_data(self, data, default_data=None, for_gov=False):
        invoice_data = super().format_data(data, default_data, for_gov)

        if for_gov:
            return invoice_data

        # No need to discard if zero fields
        amounts = [
            invoice_data.get(GSTR1_DataField.EXEMPTED_AMOUNT.value, 0),
            invoice_data.get(GSTR1_DataField.NIL_RATED_AMOUNT.value, 0),
            invoice_data.get(GSTR1_DataField.NON_GST_AMOUNT.value, 0),
        ]

        if all(amount == 0 for amount in amounts):
            return

        invoice_data[GSTR1_DataField.TAXABLE_VALUE.value] = sum(amounts)
        return invoice_data

    # value formatters
    def document_category_mapping(self, doc_category, data):
        return self.DOCUMENT_CATEGORIES.get(doc_category, doc_category)


class CDNR(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        [
            {
                'ctin': '24AANFA2641L1ZF',
                'nt': [
                    {
                        'ntty': 'C',
                        'nt_num': '533515',
                        'val': 123123,
                        'itms': [
                            {'num': 1,'itm_det': {'txval': 5225.28,
                                ...
                            }},
                            ...
                        ],
                        ...
                    },
                    ...
                ]
            },
            ...
        ]

    Internal Data Format:
        {
            'Credit/Debit Notes (Registered)': {
                '533515': {
                    'transaction_type': 'Credit Note',
                    'document_number': '533515',
                    'items': [
                        {
                            'taxable_value': -5225.28,
                            ...
                        },
                        ...
                    ],
                    'total_taxable_value': -10450.56,
                    ...
                },
                ...
            }
        }
    """

    SUBCATEGORY = GSTR1_SubCategory.CDNR.value
    KEY_MAPPING = {
        # GovDataFields.CUST_GSTIN.value: DataFields.CUST_GSTIN.value,
        GovDataField.FLAG.value: "flag",
        # GovDataFields.NOTE_DETAILS.value: "credit_debit_note_details",
        GovDataField.NOTE_TYPE.value: GSTR1_DataField.TRANSACTION_TYPE.value,
        GovDataField.NOTE_NUMBER.value: GSTR1_DataField.DOC_NUMBER.value,
        GovDataField.NOTE_DATE.value: GSTR1_DataField.DOC_DATE.value,
        GovDataField.POS.value: GSTR1_DataField.POS.value,
        GovDataField.REVERSE_CHARGE.value: GSTR1_DataField.REVERSE_CHARGE.value,
        GovDataField.INVOICE_TYPE.value: GSTR1_DataField.DOC_TYPE.value,
        GovDataField.DOC_VALUE.value: GSTR1_DataField.DOC_VALUE.value,
        GovDataField.DIFF_PERCENTAGE.value: GSTR1_DataField.DIFF_PERCENTAGE.value,
        GovDataField.ITEMS.value: GSTR1_DataField.ITEMS.value,
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        # GovDataFields.ITEM_DETAILS.value: "item_details",
        GovDataField.TAX_RATE.value: GSTR1_ItemField.TAX_RATE.value,
        GovDataField.TAXABLE_VALUE.value: GSTR1_ItemField.TAXABLE_VALUE.value,
        GovDataField.IGST.value: GSTR1_ItemField.IGST.value,
        GovDataField.SGST.value: GSTR1_ItemField.SGST.value,
        GovDataField.CGST.value: GSTR1_ItemField.CGST.value,
        GovDataField.CESS.value: GSTR1_ItemField.CESS.value,
    }

    DOCUMENT_CATEGORIES = {
        "R": "Regular B2B",
        "SEWP": "SEZ supplies with payment",
        "SEWOP": "SEZ supplies without payment",
        "DE": "Deemed Exports",
    }

    DOCUMENT_TYPES = {
        "C": "Credit Note",
        "D": "Debit Note",
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.ITEMS.value: self.format_item_for_internal,
            GovDataField.NOTE_TYPE.value: self.document_type_mapping,
            GovDataField.POS.value: self.map_place_of_supply,
            GovDataField.INVOICE_TYPE.value: self.document_category_mapping,
            GovDataField.DOC_VALUE.value: self.format_doc_value,
            GovDataField.NOTE_DATE.value: self.format_date_for_internal,
        }

        self.value_formatters_for_gov = {
            GSTR1_DataField.ITEMS.value: self.format_item_for_gov,
            GSTR1_DataField.TRANSACTION_TYPE.value: self.document_type_mapping,
            GSTR1_DataField.POS.value: self.map_place_of_supply,
            GSTR1_DataField.DOC_TYPE.value: self.document_category_mapping,
            GSTR1_DataField.DOC_VALUE.value: lambda val, *args: abs(val),
            GSTR1_DataField.DOC_DATE.value: self.format_date_for_gov,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for customer_data in input_data:
            customer_gstin = customer_data.get(GovDataField.CUST_GSTIN.value)

            for document in customer_data.get(GovDataField.NOTE_DETAILS.value):
                document_data = self.format_data(
                    document,
                    {
                        GSTR1_DataField.CUST_GSTIN.value: customer_gstin,
                        GSTR1_DataField.CUST_NAME.value: self.guess_customer_name(
                            customer_gstin
                        ),
                        GSTR1_DataField.ERROR_CD.value: customer_data.get(
                            GovDataField.ERROR_CD.value
                        ),
                        GSTR1_DataField.ERROR_MSG.value: customer_data.get(
                            GovDataField.ERROR_MSG.value
                        ),
                    },
                )
                self.update_totals(
                    document_data, document_data.get(GSTR1_DataField.ITEMS.value)
                )
                output[document_data[GSTR1_DataField.DOC_NUMBER.value]] = document_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        customer_data = {}

        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)
        self.DOCUMENT_TYPES = self.reverse_dict(self.DOCUMENT_TYPES)

        for document in input_data:
            customer_gstin = document[GSTR1_DataField.CUST_GSTIN.value]
            customer = customer_data.setdefault(
                customer_gstin,
                {
                    GovDataField.CUST_GSTIN.value: customer_gstin,
                    GovDataField.NOTE_DETAILS.value: [],
                },
            )
            customer[GovDataField.NOTE_DETAILS.value].append(
                self.format_data(document, for_gov=True)
            )

        return list(customer_data.values())

    def format_item_for_internal(self, items, *args):
        formatted_items = super().format_item_for_internal(items, *args)

        data = args[0]
        if data[GovDataField.NOTE_TYPE.value] == "D":
            return formatted_items

        # for credit notes amounts -ve
        for item in formatted_items:
            item.update(
                {
                    key: value * -1
                    for key, value in item.items()
                    if key in list(self.DEFAULT_ITEM_AMOUNTS.keys())
                }
            )

        return formatted_items

    def format_item_for_gov(self, items, *args):
        keys = set((self.DEFAULT_ITEM_AMOUNTS.keys()))
        # for credit notes amounts -ve
        for item in items:
            for key, value in item.items():
                if key in keys:
                    item[key] = abs(value)

        return super().format_item_for_gov(items, *args)

    def document_type_mapping(self, doc_type, data):
        return self.DOCUMENT_TYPES.get(doc_type, doc_type)

    def document_category_mapping(self, doc_category, data):
        return self.DOCUMENT_CATEGORIES.get(doc_category, doc_category)

    def format_doc_value(self, value, data):
        return value * -1 if data[GovDataField.NOTE_TYPE.value] == "C" else value


class CDNUR(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        [
            {
                'ntty': 'C',
                'nt_num': '533515',
                'itms': [
                    {'num': 1,'itm_det': { 'txval': 5225.28,
                        ...
                    }},
                    ...
                ],
                ...
            },
            ...
        ]

    Internal Data Format:
        {
            'Credit/Debit Notes (Unregistered)': {
                '533515': {
                    'transaction_type': 'Credit Note',
                    'document_number': '533515',
                    'items': [
                        {
                            'taxable_value': -5225.28,
                            ...
                        }
                    ],
                    'total_taxable_value': -5225.28,
                    ...
                },
                ...
            }
        }
    """

    SUBCATEGORY = GSTR1_SubCategory.CDNUR.value
    DEFAULT_ITEM_AMOUNTS = {
        GSTR1_ItemField.TAXABLE_VALUE.value: 0,
        GSTR1_ItemField.IGST.value: 0,
        GSTR1_ItemField.CESS.value: 0,
    }
    KEY_MAPPING = {
        GovDataField.FLAG.value: "flag",
        GovDataField.TYPE.value: GSTR1_DataField.DOC_TYPE.value,
        GovDataField.NOTE_TYPE.value: GSTR1_DataField.TRANSACTION_TYPE.value,
        GovDataField.NOTE_NUMBER.value: GSTR1_DataField.DOC_NUMBER.value,
        GovDataField.NOTE_DATE.value: GSTR1_DataField.DOC_DATE.value,
        GovDataField.DOC_VALUE.value: GSTR1_DataField.DOC_VALUE.value,
        GovDataField.POS.value: GSTR1_DataField.POS.value,
        GovDataField.DIFF_PERCENTAGE.value: GSTR1_DataField.DIFF_PERCENTAGE.value,
        GovDataField.ITEMS.value: GSTR1_DataField.ITEMS.value,
        GovDataField.TAX_RATE.value: GSTR1_ItemField.TAX_RATE.value,
        GovDataField.TAXABLE_VALUE.value: GSTR1_ItemField.TAXABLE_VALUE.value,
        GovDataField.IGST.value: GSTR1_ItemField.IGST.value,
        GovDataField.CESS.value: GSTR1_ItemField.CESS.value,
        GovDataField.ERROR_CD.value: GSTR1_DataField.ERROR_CD.value,
        GovDataField.ERROR_MSG.value: GSTR1_DataField.ERROR_MSG.value,
    }
    DOCUMENT_TYPES = {
        "C": "Credit Note",
        "D": "Debit Note",
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.ITEMS.value: self.format_item_for_internal,
            GovDataField.NOTE_TYPE.value: self.document_type_mapping,
            GovDataField.POS.value: self.map_place_of_supply,
            GovDataField.DOC_VALUE.value: self.format_doc_value,
            GovDataField.NOTE_DATE.value: self.format_date_for_internal,
        }

        self.value_formatters_for_gov = {
            GSTR1_DataField.ITEMS.value: self.format_item_for_gov,
            GSTR1_DataField.TRANSACTION_TYPE.value: self.document_type_mapping,
            GSTR1_DataField.POS.value: self.map_place_of_supply,
            GSTR1_DataField.DOC_VALUE.value: lambda x, *args: abs(x),
            GSTR1_DataField.DOC_DATE.value: self.format_date_for_gov,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)
            self.update_totals(
                invoice_data, invoice_data.get(GSTR1_DataField.ITEMS.value)
            )
            output[invoice_data[GSTR1_DataField.DOC_NUMBER.value]] = invoice_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        self.DOCUMENT_TYPES = self.reverse_dict(self.DOCUMENT_TYPES)
        return [self.format_data(invoice, for_gov=True) for invoice in input_data]

    def format_item_for_internal(self, items, *args):
        formatted_items = super().format_item_for_internal(items, *args)

        data = args[0]
        if data[GovDataField.NOTE_TYPE.value] == "D":
            return formatted_items

        # for credit notes amounts -ve
        for item in formatted_items:
            item.update(
                {
                    key: value * -1
                    for key, value in item.items()
                    if key in list(self.DEFAULT_ITEM_AMOUNTS.keys())
                }
            )

        return formatted_items

    def format_item_for_gov(self, items, *args):
        keys = set(self.DEFAULT_ITEM_AMOUNTS.keys())
        # for credit notes amounts -ve
        for item in items:
            for key, value in item.items():
                if key in keys:
                    item[key] = abs(value)

        return super().format_item_for_gov(items, *args)

    # value formatters
    def document_type_mapping(self, doc_type, data):
        return self.DOCUMENT_TYPES.get(doc_type, doc_type)

    def format_doc_value(self, value, data):
        return value * -1 if data[GovDataField.NOTE_TYPE.value] == "C" else value


class HSNSUM(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        {
            'data': [
                {
                    'num': 1,
                    'hsn_sc': '1010',
                    'desc': 'Goods Description',
                    'uqc': 'KGS',
                    'qty': 2.05,
                    'txval': 10.23,
                    'iamt': 14.52,
                    'csamt': 500,
                    'rt': 0.1
                }
            ]
        }

    Internal Data Format:
        {
            'HSN Summary': {
                '1010 - KGS-KILOGRAMS - 0.1': {
                    'hsn_code': '1010',
                    'description': 'Goods Description',
                    'uom': 'KGS-KILOGRAMS',
                    'quantity': 2.05,
                    'total_taxable_value': 10.23,
                    'total_igst_amount': 14.52,
                    'total_cess_amount': 500,
                    'tax_rate': 0.1
                }
            }
        }
    """

    SUBCATEGORY = GSTR1_SubCategory.HSN.value
    KEY_MAPPING = {
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        GovDataField.HSN_CODE.value: GSTR1_DataField.HSN_CODE.value,
        GovDataField.DESCRIPTION.value: GSTR1_DataField.DESCRIPTION.value,
        GovDataField.UOM.value: GSTR1_DataField.UOM.value,
        GovDataField.QUANTITY.value: GSTR1_DataField.QUANTITY.value,
        GovDataField.TAXABLE_VALUE.value: GSTR1_DataField.TAXABLE_VALUE.value,
        GovDataField.IGST.value: GSTR1_DataField.IGST.value,
        GovDataField.CGST.value: GSTR1_DataField.CGST.value,
        GovDataField.SGST.value: GSTR1_DataField.SGST.value,
        GovDataField.CESS.value: GSTR1_DataField.CESS.value,
        GovDataField.TAX_RATE.value: GSTR1_ItemField.TAX_RATE.value,
    }

    def __init__(self):
        super().__init__()
        self.value_formatters_for_internal = {GovDataField.UOM.value: self.map_uom}
        self.value_formatters_for_gov = {
            GSTR1_DataField.UOM.value: self.map_uom,
            GSTR1_DataField.DESCRIPTION.value: lambda x, *args: x[:30],
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        default_data = {
            GSTR1_DataField.ERROR_CD.value: input_data.get(GovDataField.ERROR_CD.value),
            GSTR1_DataField.ERROR_MSG.value: input_data.get(
                GovDataField.ERROR_MSG.value
            ),
        }

        for invoice in input_data[GovDataField.HSN_DATA.value]:
            output[
                " - ".join(
                    (
                        invoice.get(GovDataField.HSN_CODE.value, ""),
                        self.map_uom(invoice.get(GovDataField.UOM.value, "")),
                        str(flt(invoice.get(GovDataField.TAX_RATE.value))),
                    )
                )
            ] = self.format_data(invoice, default_data)

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        return {
            GovDataField.HSN_DATA.value: [
                self.format_data(
                    invoice, {GovDataField.INDEX.value: index + 1}, for_gov=True
                )
                for index, invoice in enumerate(input_data)
            ]
        }

    def format_data(self, data, default_data=None, for_gov=False):
        data = super().format_data(data, default_data, for_gov)

        if for_gov:
            return data

        data[GSTR1_DataField.DOC_VALUE.value] = sum(
            (
                data.get(GSTR1_DataField.TAXABLE_VALUE.value, 0),
                data.get(GSTR1_DataField.IGST.value, 0),
                data.get(GSTR1_DataField.CGST.value, 0),
                data.get(GSTR1_DataField.SGST.value, 0),
                data.get(GSTR1_DataField.CESS.value, 0),
            )
        )

        return data

    def map_uom(self, uom, data=None):
        uom = uom.upper()

        if "-" in uom:
            if data and data.get(GSTR1_DataField.HSN_CODE.value, "").startswith("99"):
                return "NA"
            else:
                return uom.split("-")[0]

        if uom in UOM_MAP:
            return f"{uom}-{UOM_MAP[uom]}"

        return f"OTH-{UOM_MAP.get('OTH')}"


class AT(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        [
            {
                'pos': '05',
                'itms': [
                    {
                        'rt': 5,
                        'ad_amt': 100,
                        ...
                    },
                    ...
                ],
                ...
            },
            ...
        ]

    Internal Data Format:
        {
            'Advances Received': {
                '05-Uttarakhand - 5.0': [
                    {
                        'place_of_supply': '05-Uttarakhand',
                        'total_taxable_value': 100,
                        'tax_rate': 5,
                        ...
                    },
                    ...
                ],
                ...
            }
        }
    """

    SUBCATEGORY = GSTR1_SubCategory.AT.value
    KEY_MAPPING = {
        GovDataField.FLAG.value: "flag",
        GovDataField.POS.value: GSTR1_DataField.POS.value,
        GovDataField.DIFF_PERCENTAGE.value: GSTR1_DataField.DIFF_PERCENTAGE.value,
        GovDataField.ITEMS.value: GSTR1_DataField.ITEMS.value,
        GovDataField.TAX_RATE.value: GSTR1_ItemField.TAX_RATE.value,
        GovDataField.ADVANCE_AMOUNT.value: GSTR1_DataField.TAXABLE_VALUE.value,
        GovDataField.IGST.value: GSTR1_DataField.IGST.value,
        GovDataField.CGST.value: GSTR1_DataField.CGST.value,
        GovDataField.SGST.value: GSTR1_DataField.SGST.value,
        GovDataField.CESS.value: GSTR1_DataField.CESS.value,
        GovDataField.ERROR_CD.value: GSTR1_DataField.ERROR_CD.value,
        GovDataField.ERROR_MSG.value: GSTR1_DataField.ERROR_MSG.value,
    }
    DEFAULT_ITEM_AMOUNTS = {
        GSTR1_DataField.IGST.value: 0,
        GSTR1_DataField.CESS.value: 0,
        GSTR1_DataField.CGST.value: 0,
        GSTR1_DataField.SGST.value: 0,
        GSTR1_DataField.TAXABLE_VALUE.value: 0,
    }
    MULTIPLIER = 1

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            GovDataField.ITEMS.value: self.format_item_for_internal,
            GovDataField.POS.value: self.map_place_of_supply,
        }

        self.value_formatters_for_gov = {
            # GSTR1_DataField.ITEMS.value: self.format_item_for_gov,
            GSTR1_DataField.POS.value: self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)
            items = invoice_data.pop(GSTR1_DataField.ITEMS.value)

            for item in items:
                if self.MULTIPLIER != 1:
                    item.update(
                        {
                            key: value * self.MULTIPLIER
                            for key, value in item.items()
                            if key in self.DEFAULT_ITEM_AMOUNTS
                        }
                    )

                item_data = invoice_data.copy()
                item_data.update(item)
                output[
                    " - ".join(
                        (
                            invoice_data.get(GSTR1_DataField.POS.value, ""),
                            str(flt(item_data.get(GSTR1_DataField.TAX_RATE.value, ""))),
                        )
                    )
                ] = [item_data]

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        self.company_gstin = kwargs.get("company_gstin", "")
        pos_wise_data = {}

        for invoice in input_data:
            formatted_data = self.format_data(invoice, for_gov=True)
            rate_wise_taxes = self.get_item_details(formatted_data)

            pos_data = pos_wise_data.setdefault(
                invoice[GSTR1_DataField.POS.value], formatted_data
            )

            pos_data.setdefault(GovDataField.ITEMS.value, []).extend(
                rate_wise_taxes[GovDataField.ITEMS.value]
            )

        return list(pos_wise_data.values())

    def get_item_details(self, invoice):
        """
        Transfer document values to item level (by POS and tax rate)
        """
        return {
            GovDataField.ITEMS.value: [
                {
                    key: invoice.pop(key)
                    for key in [
                        GovDataField.IGST.value,
                        GovDataField.CESS.value,
                        GovDataField.CGST.value,
                        GovDataField.SGST.value,
                        GovDataField.ADVANCE_AMOUNT.value,
                        GovDataField.TAX_RATE.value,
                    ]
                }
            ]
        }

    def format_data(self, data, default_data=None, for_gov=False):
        if self.MULTIPLIER != 1 and for_gov:
            data.update(
                {
                    key: value * self.MULTIPLIER
                    for key, value in data.items()
                    if key in self.DEFAULT_ITEM_AMOUNTS
                }
            )

        data = super().format_data(data, default_data, for_gov)

        if not for_gov:
            return data

        data[GovDataField.SUPPLY_TYPE.value] = (
            "INTRA"
            if data[GovDataField.POS.value] == self.company_gstin[:2]
            else "INTER"
        )
        return data

    def format_item_for_internal(self, items, *args):
        return [
            {
                **self.DEFAULT_ITEM_AMOUNTS.copy(),
                **self.format_data(item),
            }
            for item in items
        ]

    def format_item_for_gov(self, items, *args):
        return [self.format_data(item, for_gov=True) for item in items]


class TXPD(AT):
    SUBCATEGORY = GSTR1_SubCategory.TXP.value
    MULTIPLIER = -1


class DOC_ISSUE(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        {
            'doc_det': [
                {
                    'doc_num': 1,
                    'docs': [
                        {
                            'num': 1,
                            'from': '1',
                            'to': '10',
                            'totnum': 10,
                            'cancel': 0,
                            'net_issue': 10
                        }
                    ]
                }
            ]
        }

    Internal Data Format:
        {
            'Document Issued': {
                'Invoices for outward supply - 1': {
                    'document_type': 'Invoices for outward supply',
                    'from_sr_no': '1',
                    'to_sr_no': '10',
                    'total_count': 10,
                    'cancelled_count': 0,
                    'net_issue': 10
                }
            }
        }
    """

    KEY_MAPPING = {
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        GovDataField.FROM_SR.value: GSTR1_DataField.FROM_SR.value,
        GovDataField.TO_SR.value: GSTR1_DataField.TO_SR.value,
        GovDataField.TOTAL_COUNT.value: GSTR1_DataField.TOTAL_COUNT.value,
        GovDataField.CANCELLED_COUNT.value: GSTR1_DataField.CANCELLED_COUNT.value,
        GovDataField.NET_ISSUE.value: GSTR1_DataField.NET_ISSUE.value,
    }
    DOCUMENT_NATURE = {
        1: "Invoices for outward supply",
        2: "Invoices for inward supply from unregistered person",
        3: "Revised Invoice",
        4: "Debit Note",
        5: "Credit Note",
        6: "Receipt voucher",
        7: "Payment Voucher",
        8: "Refund voucher",
        9: "Delivery Challan for job work",
        10: "Delivery Challan for supply on approval",
        11: "Delivery Challan in case of liquid gas",
        12: "Delivery Challan in cases other than by way of supply (excluding at S no. 9 to 11)",
    }

    def __init__(self):
        super().__init__()

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for document in input_data[GovDataField.DOC_ISSUE_DETAILS.value]:
            document_nature = self.get_document_nature(
                document.get(GovDataField.DOC_ISSUE_NUMBER.value, "")
            )
            output.update(
                {
                    " - ".join(
                        (document_nature, doc.get(GovDataField.FROM_SR.value))
                    ): self.format_data(
                        doc, {GSTR1_DataField.DOC_TYPE.value: document_nature}
                    )
                    for doc in document[GovDataField.DOC_ISSUE_LIST.value]
                }
            )

        return {GSTR1_SubCategory.DOC_ISSUE.value: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        self.DOCUMENT_NATURE = self.reverse_dict(self.DOCUMENT_NATURE)

        output = {GovDataField.DOC_ISSUE_DETAILS.value: []}
        doc_nature_wise_data = {}

        for invoice in input_data:
            if invoice[GSTR1_DataField.DOC_TYPE.value].startswith(
                "Excluded from Report"
            ):
                continue

            doc_nature_wise_data.setdefault(
                invoice[GSTR1_DataField.DOC_TYPE.value], []
            ).append(invoice)

        input_data = doc_nature_wise_data

        output = {
            GovDataField.DOC_ISSUE_DETAILS.value: [
                {
                    GovDataField.DOC_ISSUE_NUMBER.value: self.get_document_nature(
                        doc_nature
                    ),
                    GovDataField.DOC_ISSUE_LIST.value: [
                        self.format_data(
                            document,
                            {GovDataField.INDEX.value: index + 1},
                            for_gov=True,
                        )
                        for index, document in enumerate(documents)
                    ],
                }
                for doc_nature, documents in doc_nature_wise_data.items()
            ]
        }

        return output

    def format_data(self, data, additional_data=None, for_gov=False):
        if not for_gov:
            return super().format_data(data, additional_data)

        # compute additional data
        data[GSTR1_DataField.CANCELLED_COUNT.value] += data.get(
            GSTR1_DataField.DRAFT_COUNT.value, 0
        )
        data["net_issue"] = data[GSTR1_DataField.TOTAL_COUNT.value] - data.get(
            GSTR1_DataField.CANCELLED_COUNT.value, 0
        )

        return super().format_data(data, additional_data, for_gov)

    def get_document_nature(self, doc_nature, *args):
        return self.DOCUMENT_NATURE.get(doc_nature, doc_nature)


class SUPECOM(GovDataMapper):
    """
    GST API Version - v4.0

    Government Data Format:
        {
            'clttx': [
                {
                    'etin': '20ALYPD6528PQC5',
                    'suppval': 10000,
                    'igst': 1000,
                    'cgst': 0,
                    'sgst': 0,
                    'cess': 0
                }
            ]
        }

    Internal Data Format:
        {
            'TCS collected by E-commerce Operator u/s 52': {
                '20ALYPD6528PQC5': {
                    'document_type': 'TCS collected by E-commerce Operator u/s 52',
                    'ecommerce_gstin': '20ALYPD6528PQC5',
                    'total_taxable_value': 10000,
                    'igst_amount': 1000,
                    'cgst_amount': 0,
                    'sgst_amount': 0,
                    'cess_amount': 0
                }
            }
        }
    """

    KEY_MAPPING = {
        GovDataField.ECOMMERCE_GSTIN.value: GSTR1_DataField.ECOMMERCE_GSTIN.value,
        GovDataField.NET_TAXABLE_VALUE.value: GSTR1_DataField.TAXABLE_VALUE.value,
        "igst": GSTR1_ItemField.IGST.value,
        "cgst": GSTR1_ItemField.CGST.value,
        "sgst": GSTR1_ItemField.SGST.value,
        "cess": GSTR1_ItemField.CESS.value,
        GovDataField.FLAG.value: "flag",
    }
    DOCUMENT_CATEGORIES = {
        GovDataField.SUPECOM_52.value: GSTR1_SubCategory.SUPECOM_52.value,
        GovDataField.SUPECOM_9_5.value: GSTR1_SubCategory.SUPECOM_9_5.value,
    }

    def __init__(self):
        super().__init__()

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for section, invoices in input_data.items():
            document_type = self.DOCUMENT_CATEGORIES.get(section, section)
            output[document_type] = {
                invoice.get(GovDataField.ECOMMERCE_GSTIN.value, ""): self.format_data(
                    invoice, {GSTR1_DataField.DOC_TYPE.value: document_type}
                )
                for invoice in invoices
            }

        return output

    def convert_to_gov_data_format(self, input_data, **kwargs):
        output = {}
        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)

        for invoice in input_data:
            section = invoice[GSTR1_DataField.DOC_TYPE.value]
            output.setdefault(
                self.DOCUMENT_CATEGORIES.get(section, section), []
            ).append(self.format_data(invoice, for_gov=True))
        return output


class RETSUM(GovDataMapper):
    """
    Convert GSTR-1 Summary as returned by the API to the internal format

    Usecase: Compute amendment liability for GSTR-1 Summary

    Exceptions:
        - Only supports latest summary format v4.0 and above
    """

    KEY_MAPPING = {
        "sec_nm": GSTR1_DataField.DESCRIPTION.value,
        "typ": GSTR1_DataField.DESCRIPTION.value,
        "ttl_rec": "no_of_records",
        "ttl_val": "total_document_value",
        "ttl_igst": GSTR1_DataField.IGST.value,
        "ttl_cgst": GSTR1_DataField.CGST.value,
        "ttl_sgst": GSTR1_DataField.SGST.value,
        "ttl_cess": GSTR1_DataField.CESS.value,
        "ttl_tax": GSTR1_DataField.TAXABLE_VALUE.value,
        "act_val": "actual_document_value",
        "act_igst": "actual_igst",
        "act_sgst": "actual_sgst",
        "act_cgst": "actual_cgst",
        "act_cess": "actual_cess",
        "act_tax": "actual_taxable_value",
        "ttl_expt_amt": f"total_{GSTR1_DataField.EXEMPTED_AMOUNT.value}",
        "ttl_ngsup_amt": f"total_{GSTR1_DataField.NON_GST_AMOUNT.value}",
        "ttl_nilsup_amt": f"total_{GSTR1_DataField.NIL_RATED_AMOUNT.value}",
        "ttl_doc_issued": GSTR1_DataField.TOTAL_COUNT.value,
        "ttl_doc_cancelled": GSTR1_DataField.CANCELLED_COUNT.value,
    }

    SECTION_NAMES = {
        "AT": GSTR1_Category.AT.value,
        "B2B_4A": GSTR1_SubCategory.B2B_REGULAR.value,
        "B2B_4B": GSTR1_SubCategory.B2B_REVERSE_CHARGE.value,
        "B2B_6C": GSTR1_SubCategory.DE.value,
        "B2B_SEZWOP": GSTR1_SubCategory.SEZWOP.value,
        "B2B_SEZWP": GSTR1_SubCategory.SEZWP.value,
        "B2B": GSTR1_Category.B2B.value,
        "B2CL": GSTR1_Category.B2CL.value,
        "B2CS": GSTR1_Category.B2CS.value,
        "TXPD": GSTR1_Category.TXP.value,
        "EXP": GSTR1_Category.EXP.value,
        "CDNR": GSTR1_Category.CDNR.value,
        "CDNUR": GSTR1_Category.CDNUR.value,
        "SUPECOM": GSTR1_Category.SUPECOM.value,
        "ECOM": "ECOM",
        "ECOM_REG": "ECOM_REG",
        "ECOM_DE": "ECOM_DE",
        "ECOM_SEZWOP": "ECOM_SEZWOP",
        "ECOM_SEZWP": "ECOM_SEZWP",
        "ECOM_UNREG": "ECOM_UNREG",
        "ATA": f"{GSTR1_Category.AT.value} (Amended)",
        "B2BA_4A": f"{GSTR1_SubCategory.B2B_REGULAR.value} (Amended)",
        "B2BA_4B": f"{GSTR1_SubCategory.B2B_REVERSE_CHARGE.value} (Amended)",
        "B2BA_6C": f"{GSTR1_SubCategory.DE.value} (Amended)",
        "B2BA_SEZWOP": f"{GSTR1_SubCategory.SEZWOP.value} (Amended)",
        "B2BA_SEZWP": f"{GSTR1_SubCategory.SEZWP.value} (Amended)",
        "B2BA": f"{GSTR1_Category.B2B.value} (Amended)",
        "B2CLA": f"{GSTR1_Category.B2CL.value} (Amended)",
        "B2CSA": f"{GSTR1_Category.B2CS.value} (Amended)",
        "TXPDA": f"{GSTR1_Category.TXP.value} (Amended)",
        "EXPA": f"{GSTR1_Category.EXP.value} (Amended)",
        "CDNRA": f"{GSTR1_Category.CDNR.value} (Amended)",
        "CDNURA": f"{GSTR1_Category.CDNUR.value} (Amended)",
        "SUPECOMA": f"{GSTR1_Category.SUPECOM.value} (Amended)",
        "ECOMA": "ECOMA",
        "ECOMA_REG": "ECOMA_REG",
        "ECOMA_DE": "ECOMA_DE",
        "ECOMA_SEZWOP": "ECOMA_SEZWOP",
        "ECOMA_SEZWP": "ECOMA_SEZWP",
        "ECOMA_UNREG": "ECOMA_UNREG",
        "HSN": GSTR1_Category.HSN.value,
        "NIL": GSTR1_Category.NIL_EXEMPT.value,
        "DOC_ISSUE": GSTR1_Category.DOC_ISSUE.value,
        "TTL_LIAB": "Total Liability",
    }

    SECTIONS_WITH_SUBSECTIONS = {
        "SUPECOM": {
            "SUPECOM_14A": GSTR1_SubCategory.SUPECOM_52.value,
            "SUPECOM_14B": GSTR1_SubCategory.SUPECOM_9_5.value,
        },
        "SUPECOMA": {
            "SUPECOMA_14A": f"{GSTR1_SubCategory.SUPECOM_52.value} (Amended)",
            "SUPECOMA_14B": f"{GSTR1_SubCategory.SUPECOM_9_5.value} (Amended)",
        },
        "EXP": {
            "EXPWP": GSTR1_SubCategory.EXPWP.value,
            "EXPWOP": GSTR1_SubCategory.EXPWOP.value,
        },
        "EXPA": {
            "EXPWP": f"{GSTR1_SubCategory.EXPWP.value} (Amended)",
            "EXPWOP": f"{GSTR1_SubCategory.EXPWOP.value} (Amended)",
        },
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            "sec_nm": self.map_document_types,
            "typ": self.map_document_types,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for section_data in input_data:
            section = section_data.get("sec_nm")
            output[self.SECTION_NAMES.get(section, section)] = self.format_data(
                section_data
            )

            if section not in self.SECTIONS_WITH_SUBSECTIONS:
                continue

            # Unsupported Legacy Summary API. Fallback to self-calculated summary.
            sub_sections = section_data.get("sub_sections", {})
            if not sub_sections:
                return {}

            for subsection_data in sub_sections:
                formatted_data = self.format_subsection_data(section, subsection_data)
                output[formatted_data[GSTR1_DataField.DESCRIPTION.value]] = (
                    formatted_data
                )

        return {"summary": output}

    def format_data(self, data, default_data=None, for_gov=False):
        response = super().format_data(data, default_data, for_gov)

        if data.get("sec_nm") == "DOC_ISSUE":
            response["no_of_records"] = data.get("net_doc_issued", 0)

        return response

    def format_subsection_data(self, section, subsection_data):
        subsection = subsection_data.get("typ") or subsection_data.get("sec_nm")
        formatted_data = self.format_data(subsection_data)

        formatted_data[GSTR1_DataField.DESCRIPTION.value] = (
            self.SECTIONS_WITH_SUBSECTIONS[section].get(subsection, subsection)
        )
        return formatted_data

    def map_document_types(self, doc_type, *args):
        return self.SECTION_NAMES.get(doc_type, doc_type)


CLASS_MAP = {
    GovJsonKey.B2B.value: B2B,
    GovJsonKey.B2CL.value: B2CL,
    GovJsonKey.EXP.value: Exports,
    GovJsonKey.B2CS.value: B2CS,
    GovJsonKey.NIL_EXEMPT.value: NilRated,
    GovJsonKey.CDNR.value: CDNR,
    GovJsonKey.CDNUR.value: CDNUR,
    GovJsonKey.HSN.value: HSNSUM,
    GovJsonKey.DOC_ISSUE.value: DOC_ISSUE,
    GovJsonKey.AT.value: AT,
    GovJsonKey.TXP.value: TXPD,
    GovJsonKey.SUPECOM.value: SUPECOM,
    GovJsonKey.RET_SUM.value: RETSUM,
}


def convert_to_internal_data_format(gov_data, for_errors=False):
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

    if not for_errors:
        return output

    errors = []
    for category, data in output.items():
        for row in data.values():
            row["category"] = category
            errors.append(row)

    return errors


def get_category_wise_data(
    subcategory_wise_data: dict,
    mapping: dict = SUB_CATEGORY_GOV_CATEGORY_MAPPING,
) -> dict:
    """
    returns category wise data from subcategory wise data

    Args:
        subcategory_wise_data (dict): subcategory wise data
        mapping (dict): subcategory to category mapping
        with_subcategory (bool): include subcategory level data

    Returns:
        dict: category wise data

    Example (with_subcategory=True):
        {
            "B2B, SEZ, DE": {
                "B2B": data,
                ...
            }
            ...
        }

    Example (with_subcategory=False):
        {
            "B2B, SEZ, DE": data,
            ...
        }
    """
    category_wise_data = {}
    for subcategory, category in mapping.items():
        if not subcategory_wise_data.get(subcategory.value):
            continue

        category_wise_data.setdefault(category.value, []).extend(
            subcategory_wise_data.get(subcategory.value, [])
        )

    return category_wise_data


def convert_to_gov_data_format(internal_data: dict, company_gstin: str) -> dict:
    """
    converts internal data format to Gov data format for all categories
    """

    category_wise_data = get_category_wise_data(internal_data)

    output = {}
    for category, mapper_class in CLASS_MAP.items():
        if not category_wise_data.get(category):
            continue

        output[category] = mapper_class().convert_to_gov_data_format(
            category_wise_data.get(category), company_gstin=company_gstin
        )

    return output


def summarize_retsum_data(input_data):
    if not input_data:
        return []

    summarized_data = []
    total_values_keys = [
        "no_of_records",
        "total_igst_amount",
        "total_cgst_amount",
        "total_sgst_amount",
        "total_cess_amount",
        "total_taxable_value",
    ]
    amended_data = {key: 0 for key in total_values_keys}

    input_data = {row.get("description"): row for row in input_data}

    def _sum(row):
        return flt(sum([row.get(key, 0) for key in total_values_keys]), 2)

    for category, sub_categories in CATEGORY_SUB_CATEGORY_MAPPING.items():
        category = category.value
        if category not in input_data:
            continue

        # compute total liability and total amended data
        amended_category_data = input_data.get(f"{category} (Amended)", {})
        for key in total_values_keys:
            amended_data[key] += amended_category_data.get(key, 0)

        # add category data
        if _sum(input_data[category]) == 0:
            continue

        summarized_data.append({**input_data.get(category), "indent": 0})

        # add subcategory data
        for sub_category in sub_categories:
            sub_category = sub_category.value
            if sub_category not in input_data:
                continue

            if _sum(input_data[sub_category]) == 0:
                continue

            summarized_data.append(
                {
                    **input_data.get(sub_category),
                    "indent": 1,
                    "consider_in_total_taxable_value": (
                        False
                        if sub_category
                        in SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE
                        else True
                    ),
                    "consider_in_total_tax": (
                        False
                        if sub_category in SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX
                        else True
                    ),
                }
            )

    # add total amendment liability
    if _sum(amended_data) != 0:
        summarized_data.extend(
            [
                {
                    "description": "Net Liability from Amendments",
                    **amended_data,
                    "indent": 0,
                    "consider_in_total_taxable_value": True,
                    "consider_in_total_tax": True,
                    "no_of_records": 0,
                }
            ]
        )

    return summarized_data


####################################################################################################
### Map Books Data to Internal Data Structure ######################################################
####################################################################################################


class BooksDataMapper:
    def get_transaction_type(self, invoice):
        if invoice.is_debit_note:
            return "Debit Note"
        elif invoice.is_return:
            return "Credit Note"
        else:
            return "Invoice"

    def process_data_for_invoice_no_key(self, invoice, prepared_data):
        invoice_sub_category = invoice.invoice_sub_category
        invoice_no = invoice.invoice_no

        mapped_dict = prepared_data.setdefault(invoice_sub_category, {}).setdefault(
            invoice_no,
            {
                GSTR1_DataField.TRANSACTION_TYPE.value: self.get_transaction_type(
                    invoice
                ),
                GSTR1_DataField.CUST_GSTIN.value: invoice.billing_address_gstin,
                GSTR1_DataField.CUST_NAME.value: invoice.customer_name,
                GSTR1_DataField.DOC_DATE.value: invoice.posting_date,
                GSTR1_DataField.DOC_NUMBER.value: invoice.invoice_no,
                GSTR1_DataField.DOC_VALUE.value: invoice.invoice_total,
                GSTR1_DataField.POS.value: invoice.place_of_supply,
                GSTR1_DataField.REVERSE_CHARGE.value: (
                    "Y" if invoice.is_reverse_charge else "N"
                ),
                GSTR1_DataField.DOC_TYPE.value: invoice.invoice_type,
                GSTR1_DataField.TAXABLE_VALUE.value: 0,
                GSTR1_DataField.IGST.value: 0,
                GSTR1_DataField.CGST.value: 0,
                GSTR1_DataField.SGST.value: 0,
                GSTR1_DataField.CESS.value: 0,
                GSTR1_DataField.DIFF_PERCENTAGE.value: 0,
                GSTR1_DataField.SHIPPING_PORT_CODE.value: invoice.shipping_port_code,
                GSTR1_DataField.SHIPPING_BILL_NUMBER.value: invoice.shipping_bill_number,
                GSTR1_DataField.SHIPPING_BILL_DATE.value: invoice.shipping_bill_date,
                "items": [],
            },
        )

        items = mapped_dict["items"]

        for item in items:
            if item[GSTR1_ItemField.TAX_RATE.value] == invoice.gst_rate:
                item[GSTR1_ItemField.TAXABLE_VALUE.value] += invoice.taxable_value
                item[GSTR1_ItemField.IGST.value] += invoice.igst_amount
                item[GSTR1_ItemField.CGST.value] += invoice.cgst_amount
                item[GSTR1_ItemField.SGST.value] += invoice.sgst_amount
                item[GSTR1_ItemField.CESS.value] += invoice.total_cess_amount
                self.update_totals(mapped_dict, invoice)
                return

        items.append(
            {
                GSTR1_ItemField.TAXABLE_VALUE.value: invoice.taxable_value,
                GSTR1_ItemField.IGST.value: invoice.igst_amount,
                GSTR1_ItemField.CGST.value: invoice.cgst_amount,
                GSTR1_ItemField.SGST.value: invoice.sgst_amount,
                GSTR1_ItemField.CESS.value: invoice.total_cess_amount,
                GSTR1_ItemField.TAX_RATE.value: invoice.gst_rate,
            }
        )

        self.update_totals(mapped_dict, invoice)

    def process_data_for_nil_exempt(self, invoice, prepared_data):
        key = invoice.invoice_category
        invoices_by_type = prepared_data.setdefault(key, {}).setdefault(
            invoice.invoice_type, []
        )

        for mapped_dict in invoices_by_type:
            if mapped_dict[GSTR1_DataField.DOC_NUMBER.value] == invoice.invoice_no:
                break

        else:
            mapped_dict = {
                GSTR1_DataField.TRANSACTION_TYPE.value: self.get_transaction_type(
                    invoice
                ),
                GSTR1_DataField.CUST_GSTIN.value: invoice.billing_address_gstin,
                GSTR1_DataField.CUST_NAME.value: invoice.customer_name,
                GSTR1_DataField.DOC_NUMBER.value: invoice.invoice_no,
                GSTR1_DataField.DOC_DATE.value: invoice.posting_date,
                GSTR1_DataField.DOC_VALUE.value: invoice.invoice_total,
                GSTR1_DataField.POS.value: invoice.place_of_supply,
                GSTR1_DataField.REVERSE_CHARGE.value: (
                    "Y" if invoice.is_reverse_charge else "N"
                ),
                GSTR1_DataField.DOC_TYPE.value: invoice.invoice_type,
                GSTR1_DataField.TAXABLE_VALUE.value: 0,
                GSTR1_DataField.NIL_RATED_AMOUNT.value: 0,
                GSTR1_DataField.EXEMPTED_AMOUNT.value: 0,
                GSTR1_DataField.NON_GST_AMOUNT.value: 0,
            }
            invoices_by_type.append(mapped_dict)

        mapped_dict[GSTR1_DataField.TAXABLE_VALUE.value] += invoice.taxable_value

        if invoice.gst_treatment == "Nil-Rated":
            mapped_dict[GSTR1_DataField.NIL_RATED_AMOUNT.value] += invoice.taxable_value
        elif invoice.gst_treatment == "Exempted":
            mapped_dict[GSTR1_DataField.EXEMPTED_AMOUNT.value] += invoice.taxable_value
        elif invoice.gst_treatment == "Non-GST":
            mapped_dict[GSTR1_DataField.NON_GST_AMOUNT.value] += invoice.taxable_value

    def process_data_for_b2cs(self, invoice, prepared_data):
        key = f"{invoice.place_of_supply} - {flt(invoice.gst_rate)}"
        mapped_dict = prepared_data.setdefault("B2C (Others)", {}).setdefault(key, [])

        for row in mapped_dict:
            if row[GSTR1_DataField.DOC_NUMBER.value] == invoice.invoice_no:
                self.update_totals(row, invoice)
                return

        mapped_dict.append(
            {
                GSTR1_DataField.DOC_DATE.value: invoice.posting_date,
                GSTR1_DataField.DOC_NUMBER.value: invoice.invoice_no,
                GSTR1_DataField.DOC_VALUE.value: invoice.invoice_total,
                GSTR1_DataField.CUST_NAME.value: invoice.customer_name,
                # currently other value is not supported in GSTR-1
                GSTR1_DataField.DOC_TYPE.value: "OE",
                GSTR1_DataField.TRANSACTION_TYPE.value: self.get_transaction_type(
                    invoice
                ),
                GSTR1_DataField.POS.value: invoice.place_of_supply,
                GSTR1_DataField.TAX_RATE.value: invoice.gst_rate,
                GSTR1_DataField.ECOMMERCE_GSTIN.value: invoice.ecommerce_gstin,
                **self.get_invoice_values(invoice),
            }
        )

    def process_data_for_hsn_summary(self, invoice, prepared_data):
        key = f"{invoice.gst_hsn_code} - {invoice.stock_uom} - {flt(invoice.gst_rate)}"

        if key not in prepared_data:
            mapped_dict = prepared_data.setdefault(
                key,
                {
                    GSTR1_DataField.HSN_CODE.value: invoice.gst_hsn_code,
                    GSTR1_DataField.DESCRIPTION.value: frappe.db.get_value(
                        "GST HSN Code", invoice.gst_hsn_code, "description"
                    ),
                    GSTR1_DataField.UOM.value: invoice.stock_uom,
                    GSTR1_DataField.QUANTITY.value: 0,
                    GSTR1_DataField.TAX_RATE.value: invoice.gst_rate,
                    GSTR1_DataField.TAXABLE_VALUE.value: 0,
                    GSTR1_DataField.IGST.value: 0,
                    GSTR1_DataField.CGST.value: 0,
                    GSTR1_DataField.SGST.value: 0,
                    GSTR1_DataField.CESS.value: 0,
                },
            )

        else:
            mapped_dict = prepared_data[key]

        self.update_totals(mapped_dict, invoice, for_qty=True)

        mapped_dict[GSTR1_DataField.DOC_VALUE.value] = sum(
            (
                mapped_dict.get(GSTR1_DataField.TAXABLE_VALUE.value, 0),
                mapped_dict.get(GSTR1_DataField.IGST.value, 0),
                mapped_dict.get(GSTR1_DataField.CGST.value, 0),
                mapped_dict.get(GSTR1_DataField.SGST.value, 0),
                mapped_dict.get(GSTR1_DataField.CESS.value, 0),
            )
        )

    def process_data_for_document_issued_summary(self, row, prepared_data):
        key = f"{row['nature_of_document']} - {row['from_serial_no']}"
        prepared_data.setdefault(
            key,
            {
                GSTR1_DataField.DOC_TYPE.value: row["nature_of_document"],
                GSTR1_DataField.FROM_SR.value: row["from_serial_no"],
                GSTR1_DataField.TO_SR.value: row["to_serial_no"],
                GSTR1_DataField.TOTAL_COUNT.value: row["total_issued"],
                GSTR1_DataField.DRAFT_COUNT.value: row["total_draft"],
                GSTR1_DataField.CANCELLED_COUNT.value: row["cancelled"],
                GSTR1_DataField.NET_ISSUE.value: row["total_submitted"],
            },
        )

    def process_data_for_advances_received_or_adjusted(
        self, row, prepared_data, multiplier=1
    ):
        advances = {}
        tax_rate = round(((row["tax_amount"] / row["taxable_value"]) * 100))
        key = f"{row['place_of_supply']} - {flt(tax_rate)}"

        mapped_dict = prepared_data.setdefault(key, [])

        advances[GSTR1_DataField.CUST_NAME.value] = row["party"]
        advances[GSTR1_DataField.DOC_NUMBER.value] = row["name"]
        advances[GSTR1_DataField.DOC_DATE.value] = row["posting_date"]
        advances[GSTR1_DataField.POS.value] = row["place_of_supply"]
        advances[GSTR1_DataField.TAXABLE_VALUE.value] = (
            row["taxable_value"] * multiplier
        )
        advances[GSTR1_DataField.TAX_RATE.value] = tax_rate
        advances[GSTR1_DataField.CESS.value] = row["cess_amount"] * multiplier

        if row.get("reference_name"):
            advances["against_voucher"] = row["reference_name"]

        if row["place_of_supply"][0:2] == row["company_gstin"][0:2]:
            advances[GSTR1_DataField.CGST.value] = row["tax_amount"] / 2 * multiplier
            advances[GSTR1_DataField.SGST.value] = row["tax_amount"] / 2 * multiplier
            advances[GSTR1_DataField.IGST.value] = 0

        else:
            advances[GSTR1_DataField.IGST.value] = row["tax_amount"] * multiplier
            advances[GSTR1_DataField.CGST.value] = 0
            advances[GSTR1_DataField.SGST.value] = 0

        mapped_dict.append(advances)

    # utils

    def update_totals(self, mapped_dict, invoice, for_qty=False):
        data_invoice_amount_map = {
            GSTR1_DataField.TAXABLE_VALUE.value: GSTR1_ItemField.TAXABLE_VALUE.value,
            GSTR1_DataField.IGST.value: GSTR1_ItemField.IGST.value,
            GSTR1_DataField.CGST.value: GSTR1_ItemField.CGST.value,
            GSTR1_DataField.SGST.value: GSTR1_ItemField.SGST.value,
            GSTR1_DataField.CESS.value: GSTR1_ItemField.CESS.value,
        }

        if for_qty:
            data_invoice_amount_map[GSTR1_DataField.QUANTITY.value] = "qty"

        for key, field in data_invoice_amount_map.items():
            mapped_dict[key] += invoice.get(field, 0)

    def get_invoice_values(self, invoice):
        return {
            GSTR1_DataField.TAXABLE_VALUE.value: invoice.taxable_value,
            GSTR1_DataField.IGST.value: invoice.igst_amount,
            GSTR1_DataField.CGST.value: invoice.cgst_amount,
            GSTR1_DataField.SGST.value: invoice.sgst_amount,
            GSTR1_DataField.CESS.value: invoice.total_cess_amount,
        }


class GSTR1BooksData(BooksDataMapper):
    def __init__(self, filters):
        self.filters = filters

    def prepare_mapped_data(self):
        prepared_data = {}

        _class = GSTR1Invoices(self.filters)
        data = _class.get_invoices_for_item_wise_summary()
        _class.process_invoices(data)

        for invoice in data:
            if invoice.get("taxable_value") == 0:
                continue

            if invoice["invoice_category"] in (
                GSTR1_Category.B2B.value,
                GSTR1_Category.EXP.value,
                GSTR1_Category.B2CL.value,
                GSTR1_Category.CDNR.value,
                GSTR1_Category.CDNUR.value,
            ):
                self.process_data_for_invoice_no_key(invoice, prepared_data)
            elif invoice["invoice_category"] == GSTR1_Category.NIL_EXEMPT.value:
                self.process_data_for_nil_exempt(invoice, prepared_data)
            elif invoice["invoice_category"] == GSTR1_Category.B2CS.value:
                self.process_data_for_b2cs(invoice, prepared_data)

        other_categories = {
            GSTR1_Category.AT.value: self.prepare_advances_recevied_data(),
            GSTR1_Category.TXP.value: self.prepare_advances_adjusted_data(),
            GSTR1_Category.HSN.value: self.prepare_hsn_data(data),
            GSTR1_Category.DOC_ISSUE.value: self.prepare_document_issued_data(),
        }

        for category, data in other_categories.items():
            if data:
                prepared_data[category] = data

        return prepared_data

    def prepare_document_issued_data(self):
        doc_issued_data = {}
        data = GSTR1DocumentIssuedSummary(self.filters).get_data()

        for row in data:
            self.process_data_for_document_issued_summary(row, doc_issued_data)

        return doc_issued_data

    def prepare_hsn_data(self, data):
        hsn_summary_data = {}

        for row in data:
            self.process_data_for_hsn_summary(row, hsn_summary_data)

        return hsn_summary_data

    def prepare_advances_recevied_data(self):
        return self.prepare_advances_received_or_adjusted_data("Advances")

    def prepare_advances_adjusted_data(self):
        return self.prepare_advances_received_or_adjusted_data("Adjustment")

    def prepare_advances_received_or_adjusted_data(self, type_of_business):
        advances_data = {}
        self.filters.type_of_business = type_of_business
        gst_accounts = get_gst_accounts_by_type(self.filters.company, "Output")
        _class = GSTR11A11BData(self.filters, gst_accounts)

        if type_of_business == "Advances":
            query = _class.get_11A_query()
            fields = (
                _class.pe.name,
                _class.pe.party,
                _class.pe.posting_date,
                _class.pe.company_gstin,
            )
            multipler = 1

        elif type_of_business == "Adjustment":
            query = _class.get_11B_query()
            fields = (
                _class.pe.name,
                _class.pe.party,
                _class.pe.posting_date,
                _class.pe.company_gstin,
                _class.pe_ref.reference_name,
            )
            multipler = -1

        query = query.select(*fields)
        data = query.run(as_dict=True)

        for row in data:
            self.process_data_for_advances_received_or_adjusted(
                row, advances_data, multipler
            )

        return advances_data
