from collections import defaultdict
from datetime import datetime
from itertools import chain

import frappe
from frappe.utils import cint, flt

from india_compliance.gst_india.constants import UOM_MAP
from india_compliance.gst_india.report.gstr_1.gstr_1 import (
    GSTR1DocumentIssuedSummary,
    GSTR11A11BData,
)
from india_compliance.gst_india.utils import (
    MONTHS,
    get_gst_accounts_by_type,
    get_party_for_gstin,
)
from india_compliance.gst_india.utils.gstr_1 import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    SUB_CATEGORY_GOV_CATEGORY_MAPPING,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX,
    SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
)
from india_compliance.gst_india.utils.gstr_1 import GovDataField as gov_f
from india_compliance.gst_india.utils.gstr_1 import (
    GovJsonKey,
    GSTR1_B2B_InvoiceType,
    GSTR1_Category,
)
from india_compliance.gst_india.utils.gstr_1 import GSTR1_DataField as inv_f
from india_compliance.gst_india.utils.gstr_1 import GSTR1_ItemField as item_f
from india_compliance.gst_india.utils.gstr_1 import (
    GSTR1_SubCategory,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Invoices
from india_compliance.gst_india.utils.gstr_mapper_utils import GovDataMapper

############################################################################################################
### Map Govt JSON to Internal Data Structure ###############################################################
############################################################################################################


class GSTR1DataMapper(GovDataMapper):
    """
    GST Developer API Documentation for Returns - https://developer.gst.gov.in/apiportal/taxpayer/returns

    GSTR-1 JSON format - https://developer.gst.gov.in/pages/apiportal/data/Returns/GSTR1%20-%20Save%20GSTR1%20data/v4.0/GSTR1%20-%20Save%20GSTR1%20data%20attributes.xlsx
    """

    # default item amounts
    DEFAULT_ITEM_AMOUNTS = {
        item_f.TAXABLE_VALUE: 0,
        item_f.IGST: 0,
        item_f.CGST: 0,
        item_f.SGST: 0,
        item_f.CESS: 0,
    }

    FLOAT_FIELDS = {
        gov_f.DOC_VALUE,
        gov_f.TAXABLE_VALUE,
        gov_f.DIFF_PERCENTAGE,
        gov_f.IGST,
        gov_f.CGST,
        gov_f.SGST,
        gov_f.CESS,
        gov_f.NET_TAXABLE_VALUE,
        gov_f.EXEMPTED_AMOUNT,
        gov_f.NIL_RATED_AMOUNT,
        gov_f.NON_GST_AMOUNT,
        gov_f.QUANTITY,
        gov_f.ADVANCE_AMOUNT,
    }

    DISCARD_IF_ZERO_FIELDS = {
        gov_f.DIFF_PERCENTAGE,
    }

    def __init__(self):
        super().__init__()
        self.gstin_party_map = {}

    # common value formatters
    def format_item_for_internal(self, items, *args):
        return [
            {
                **self.DEFAULT_ITEM_AMOUNTS.copy(),
                **self.format_data(item.get(gov_f.ITEM_DETAILS, {})),
            }
            for item in items
        ]

    def format_item_for_gov(self, items, *args):
        return [
            {
                gov_f.INDEX: index + 1,
                gov_f.ITEM_DETAILS: self.format_data(item, for_gov=True),
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

    def convert_to_internal_data_format(self, input_data):
        """
        Objective: Convert Govt JSON to Internal Data Structure
        Args:
            input_data (list): Govt JSON Data
        Returns:
            dict: Internal Data Structure
        """
        raise NotImplementedError("This method should be overridden in subclasses")

    def convert_to_gov_data_format(self, input_data, **kwargs):
        """
        Objective: Convert Internal Data Structure to Govt JSON
        Args:
            input_data (dict): Internal Data Structure
        Returns:
            list: Govt JSON Data
        """
        raise NotImplementedError("This method should be overridden in subclasses")


class B2B(GSTR1DataMapper):
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
        gov_f.FLAG: "flag",
        gov_f.DOC_NUMBER: inv_f.DOC_NUMBER,
        gov_f.DOC_DATE: inv_f.DOC_DATE,
        gov_f.DOC_VALUE: inv_f.DOC_VALUE,
        gov_f.POS: inv_f.POS,
        gov_f.REVERSE_CHARGE: inv_f.REVERSE_CHARGE,
        # GovDataFields.ECOMMERCE_GSTIN.value: df.ECOMMERCE_GSTIN.value,
        gov_f.INVOICE_TYPE: inv_f.DOC_TYPE,
        gov_f.DIFF_PERCENTAGE: inv_f.DIFF_PERCENTAGE,
        gov_f.ITEMS: inv_f.ITEMS,
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        gov_f.ITEM_DETAILS: item_f.ITEM_DETAILS,
        gov_f.TAX_RATE: item_f.TAX_RATE,
        gov_f.TAXABLE_VALUE: item_f.TAXABLE_VALUE,
        gov_f.IGST: item_f.IGST,
        gov_f.CGST: item_f.CGST,
        gov_f.SGST: item_f.SGST,
        gov_f.CESS: item_f.CESS,
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
            gov_f.ITEMS: self.format_item_for_internal,
            gov_f.INVOICE_TYPE: self.document_category_mapping,
            gov_f.POS: self.map_place_of_supply,
            gov_f.DOC_DATE: self.format_date_for_internal,
        }

        self.value_formatters_for_gov = {
            inv_f.ITEMS: self.format_item_for_gov,
            inv_f.DOC_TYPE: self.document_category_mapping,
            inv_f.POS: self.map_place_of_supply,
            inv_f.DOC_DATE: self.format_date_for_gov,
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
            customer_gstin = customer_data.get(gov_f.CUST_GSTIN)

            default_invoice_data = {
                inv_f.CUST_GSTIN: customer_gstin,
                inv_f.CUST_NAME: self.guess_customer_name(customer_gstin),
                inv_f.ERROR_CD: customer_data.get(gov_f.ERROR_CD),
                inv_f.ERROR_MSG: customer_data.get(gov_f.ERROR_MSG),
            }

            for invoice in customer_data.get(gov_f.INVOICES):
                invoice_data = self.format_data(invoice, default_invoice_data)
                self.update_totals(invoice_data, invoice_data.get(inv_f.ITEMS))

                subcategory_data = output.setdefault(
                    self.get_document_subcategory(invoice), {}
                )
                subcategory_data[invoice_data[inv_f.DOC_NUMBER]] = invoice_data

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
                invoice[inv_f.CUST_GSTIN],
                {
                    gov_f.CUST_GSTIN: invoice[inv_f.CUST_GSTIN],
                    gov_f.INVOICES: [],
                },
            )

            customer[gov_f.INVOICES].append(self.format_data(invoice, for_gov=True))

        return list(customer_data.values())

    def get_document_subcategory(self, invoice_data):
        if invoice_data.get(gov_f.INVOICE_TYPE) in self.SUBCATEGORIES:
            return self.SUBCATEGORIES[invoice_data[gov_f.INVOICE_TYPE]]

        if invoice_data.get(gov_f.REVERSE_CHARGE) == "Y":
            return GSTR1_SubCategory.B2B_REVERSE_CHARGE.value

        return GSTR1_SubCategory.B2B_REGULAR.value

    # value formatting methods

    def document_category_mapping(self, sub_category, data):
        return self.DOCUMENT_CATEGORIES.get(sub_category, sub_category)


class B2CL(GSTR1DataMapper):
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
        item_f.TAXABLE_VALUE: 0,
        item_f.IGST: 0,
        item_f.CESS: 0,
    }
    KEY_MAPPING = {
        # GovDataFields.POS.value: DataFields.POS.value,
        # GovDataFields.INVOICES.value: "invoices",
        gov_f.FLAG: "flag",
        gov_f.DOC_NUMBER: inv_f.DOC_NUMBER,
        gov_f.DOC_DATE: inv_f.DOC_DATE,
        gov_f.DOC_VALUE: inv_f.DOC_VALUE,
        # GovDataFields.ECOMMERCE_GSTIN.value: df.ECOMMERCE_GSTIN.value,
        gov_f.DIFF_PERCENTAGE: inv_f.DIFF_PERCENTAGE,
        gov_f.ITEMS: inv_f.ITEMS,
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        gov_f.ITEM_DETAILS: item_f.ITEM_DETAILS,
        gov_f.TAX_RATE: item_f.TAX_RATE,
        gov_f.TAXABLE_VALUE: item_f.TAXABLE_VALUE,
        gov_f.IGST: item_f.IGST,
        gov_f.CESS: item_f.CESS,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            gov_f.ITEMS: self.format_item_for_internal,
            gov_f.DOC_DATE: self.format_date_for_internal,
        }
        self.value_formatters_for_gov = {
            inv_f.ITEMS: self.format_item_for_gov,
            inv_f.DOC_DATE: self.format_date_for_gov,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for pos_data in input_data:
            pos = self.map_place_of_supply(pos_data.get(gov_f.POS))

            default_invoice_data = {
                inv_f.POS: pos,
                inv_f.DOC_TYPE: self.DOCUMENT_CATEGORY,
                inv_f.ERROR_CD: pos_data.get(gov_f.ERROR_CD),
                inv_f.ERROR_MSG: pos_data.get(gov_f.ERROR_MSG),
            }

            for invoice in pos_data.get(gov_f.INVOICES):
                invoice_level_data = self.format_data(invoice, default_invoice_data)
                self.update_totals(
                    invoice_level_data,
                    invoice_level_data.get(inv_f.ITEMS),
                )

                output[invoice_level_data[inv_f.DOC_NUMBER]] = invoice_level_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        pos_data = {}

        for invoice in input_data:
            pos = pos_data.setdefault(
                invoice[inv_f.POS],
                {
                    gov_f.POS: self.map_place_of_supply(invoice[inv_f.POS]),
                    gov_f.INVOICES: [],
                },
            )

            pos[gov_f.INVOICES].append(self.format_data(invoice, for_gov=True))

        return list(pos_data.values())


class Exports(GSTR1DataMapper):
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
        item_f.TAXABLE_VALUE: 0,
        item_f.IGST: 0,
        item_f.CESS: 0,
    }
    KEY_MAPPING = {
        # GovDataFields.POS.value: DataFields.POS.value,
        # GovDataFields.INVOICES.value: "invoices",
        gov_f.FLAG: "flag",
        # GovDataFields.EXPORT_TYPE.value: DataFields.DOC_TYPE.value,
        gov_f.DOC_NUMBER: inv_f.DOC_NUMBER,
        gov_f.DOC_DATE: inv_f.DOC_DATE,
        gov_f.DOC_VALUE: inv_f.DOC_VALUE,
        gov_f.SHIPPING_PORT_CODE: inv_f.SHIPPING_PORT_CODE,
        gov_f.SHIPPING_BILL_NUMBER: inv_f.SHIPPING_BILL_NUMBER,
        gov_f.SHIPPING_BILL_DATE: inv_f.SHIPPING_BILL_DATE,
        gov_f.ITEMS: inv_f.ITEMS,
        gov_f.TAXABLE_VALUE: item_f.TAXABLE_VALUE,
        gov_f.TAX_RATE: item_f.TAX_RATE,
        gov_f.IGST: item_f.IGST,
        gov_f.CESS: item_f.CESS,
    }

    SUBCATEGORIES = {
        "WPAY": GSTR1_SubCategory.EXPWP.value,
        "WOPAY": GSTR1_SubCategory.EXPWOP.value,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            gov_f.ITEMS: self.format_item_for_internal,
            gov_f.DOC_DATE: self.format_date_for_internal,
            gov_f.SHIPPING_BILL_DATE: self.format_date_for_internal,
        }
        self.value_formatters_for_gov = {
            inv_f.ITEMS: self.format_item_for_gov,
            inv_f.DOC_DATE: self.format_date_for_gov,
            inv_f.SHIPPING_BILL_DATE: self.format_date_for_gov,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for export_category in input_data:
            document_type = export_category.get(gov_f.EXPORT_TYPE)
            subcategory_data = output.setdefault(
                self.SUBCATEGORIES.get(document_type, document_type), {}
            )

            default_invoice_data = {
                inv_f.DOC_TYPE: document_type,
                inv_f.ERROR_CD: export_category.get(gov_f.ERROR_CD),
                inv_f.ERROR_MSG: export_category.get(gov_f.ERROR_MSG),
            }

            for invoice in export_category.get(gov_f.INVOICES):
                invoice_level_data = self.format_data(invoice, default_invoice_data)

                self.update_totals(
                    invoice_level_data,
                    invoice_level_data.get(inv_f.ITEMS),
                )
                subcategory_data[invoice_level_data[inv_f.DOC_NUMBER]] = (
                    invoice_level_data
                )

        return output

    def convert_to_gov_data_format(self, input_data, **kwargs):
        export_category_wise_data = {}

        for invoice in input_data:
            export_category = export_category_wise_data.setdefault(
                invoice[inv_f.DOC_TYPE],
                {
                    gov_f.EXPORT_TYPE: invoice[inv_f.DOC_TYPE],
                    gov_f.INVOICES: [],
                },
            )

            export_category[gov_f.INVOICES].append(
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


class B2CS(GSTR1DataMapper):
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
        gov_f.FLAG: "flag",
        # GovDataFields.SUPPLY_TYPE.value: "supply_type",
        gov_f.TAXABLE_VALUE: inv_f.TAXABLE_VALUE,
        gov_f.TYPE: inv_f.DOC_TYPE,
        # GovDataFields.ECOMMERCE_GSTIN.value: df.ECOMMERCE_GSTIN.value,
        gov_f.DIFF_PERCENTAGE: inv_f.DIFF_PERCENTAGE,
        gov_f.POS: inv_f.POS,
        gov_f.TAX_RATE: inv_f.TAX_RATE,
        gov_f.IGST: inv_f.IGST,
        gov_f.CGST: inv_f.CGST,
        gov_f.SGST: inv_f.SGST,
        gov_f.CESS: inv_f.CESS,
        gov_f.ERROR_CD: inv_f.ERROR_CD,
        gov_f.ERROR_MSG: inv_f.ERROR_MSG,
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            gov_f.ITEMS: self.format_item_for_internal,
            gov_f.POS: self.map_place_of_supply,
        }
        self.value_formatters_for_gov = {
            inv_f.ITEMS: self.format_item_for_gov,
            inv_f.POS: self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)

            output.setdefault(
                " - ".join(
                    (
                        invoice_data.get(inv_f.POS, ""),
                        str(flt(invoice_data.get(inv_f.TAX_RATE, ""))),
                        # invoice_data.get(df.ECOMMERCE_GSTIN.value, ""),
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

        data[gov_f.SUPPLY_TYPE] = (
            "INTRA" if data[gov_f.POS] == self.company_gstin[:2] else "INTER"
        )
        return data


class NilRated(GSTR1DataMapper):
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
        gov_f.SUPPLY_TYPE: inv_f.DOC_TYPE,
        gov_f.EXEMPTED_AMOUNT: inv_f.EXEMPTED_AMOUNT,
        gov_f.NIL_RATED_AMOUNT: inv_f.NIL_RATED_AMOUNT,
        gov_f.NON_GST_AMOUNT: inv_f.NON_GST_AMOUNT,
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
            gov_f.SUPPLY_TYPE: self.document_category_mapping
        }
        self.value_formatters_for_gov = {inv_f.DOC_TYPE: self.document_category_mapping}

    def convert_to_internal_data_format(self, input_data):
        output = {}

        default_data = {
            inv_f.ERROR_CD: input_data.get(gov_f.ERROR_CD),
            inv_f.ERROR_MSG: input_data.get(gov_f.ERROR_MSG),
        }

        for invoice in input_data[gov_f.INVOICES]:
            invoice_data = self.format_data(invoice, default_data)

            if not invoice_data:
                continue

            output.setdefault(invoice_data.get(inv_f.DOC_TYPE), []).append(invoice_data)

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)

        return {
            gov_f.INVOICES: [
                self.format_data(invoice, for_gov=True) for invoice in input_data
            ]
        }

    def format_data(self, data, default_data=None, for_gov=False):
        invoice_data = super().format_data(data, default_data, for_gov)

        if for_gov:
            return invoice_data

        # No need to discard if zero fields
        amounts = [
            invoice_data.get(inv_f.EXEMPTED_AMOUNT, 0),
            invoice_data.get(inv_f.NIL_RATED_AMOUNT, 0),
            invoice_data.get(inv_f.NON_GST_AMOUNT, 0),
        ]

        if all(amount == 0 for amount in amounts):
            return

        invoice_data[inv_f.TAXABLE_VALUE] = sum(amounts)
        return invoice_data

    # value formatters
    def document_category_mapping(self, doc_category, data):
        return self.DOCUMENT_CATEGORIES.get(doc_category, doc_category)


class CDNR(GSTR1DataMapper):
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
        gov_f.FLAG: "flag",
        # GovDataFields.NOTE_DETAILS.value: "credit_debit_note_details",
        gov_f.NOTE_TYPE: inv_f.TRANSACTION_TYPE,
        gov_f.NOTE_NUMBER: inv_f.DOC_NUMBER,
        gov_f.NOTE_DATE: inv_f.DOC_DATE,
        gov_f.POS: inv_f.POS,
        gov_f.REVERSE_CHARGE: inv_f.REVERSE_CHARGE,
        gov_f.INVOICE_TYPE: inv_f.DOC_TYPE,
        gov_f.DOC_VALUE: inv_f.DOC_VALUE,
        gov_f.DIFF_PERCENTAGE: inv_f.DIFF_PERCENTAGE,
        gov_f.ITEMS: inv_f.ITEMS,
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        # GovDataFields.ITEM_DETAILS.value: "item_details",
        gov_f.TAX_RATE: item_f.TAX_RATE,
        gov_f.TAXABLE_VALUE: item_f.TAXABLE_VALUE,
        gov_f.IGST: item_f.IGST,
        gov_f.SGST: item_f.SGST,
        gov_f.CGST: item_f.CGST,
        gov_f.CESS: item_f.CESS,
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
            gov_f.ITEMS: self.format_item_for_internal,
            gov_f.NOTE_TYPE: self.document_type_mapping,
            gov_f.POS: self.map_place_of_supply,
            gov_f.INVOICE_TYPE: self.document_category_mapping,
            gov_f.DOC_VALUE: self.format_doc_value,
            gov_f.NOTE_DATE: self.format_date_for_internal,
        }

        self.value_formatters_for_gov = {
            inv_f.ITEMS: self.format_item_for_gov,
            inv_f.TRANSACTION_TYPE: self.document_type_mapping,
            inv_f.POS: self.map_place_of_supply,
            inv_f.DOC_TYPE: self.document_category_mapping,
            inv_f.DOC_VALUE: lambda val, *args: abs(val),  # nosemgrep
            inv_f.DOC_DATE: self.format_date_for_gov,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for customer_data in input_data:
            customer_gstin = customer_data.get(gov_f.CUST_GSTIN)

            for document in customer_data.get(gov_f.NOTE_DETAILS):
                document_data = self.format_data(
                    document,
                    {
                        inv_f.CUST_GSTIN: customer_gstin,
                        inv_f.CUST_NAME: self.guess_customer_name(customer_gstin),
                        inv_f.ERROR_CD: customer_data.get(gov_f.ERROR_CD),
                        inv_f.ERROR_MSG: customer_data.get(gov_f.ERROR_MSG),
                    },
                )
                self.update_totals(document_data, document_data.get(inv_f.ITEMS))
                output[document_data[inv_f.DOC_NUMBER]] = document_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        customer_data = {}

        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)
        self.DOCUMENT_TYPES = self.reverse_dict(self.DOCUMENT_TYPES)

        for document in input_data:
            customer_gstin = document[inv_f.CUST_GSTIN]
            customer = customer_data.setdefault(
                customer_gstin,
                {
                    gov_f.CUST_GSTIN: customer_gstin,
                    gov_f.NOTE_DETAILS: [],
                },
            )
            customer[gov_f.NOTE_DETAILS].append(
                self.format_data(document, for_gov=True)
            )

        return list(customer_data.values())

    def format_item_for_internal(self, items, *args):
        formatted_items = super().format_item_for_internal(items, *args)

        data = args[0]
        if data[gov_f.NOTE_TYPE] == "D":
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
        return value * -1 if data[gov_f.NOTE_TYPE] == "C" else value


class CDNUR(GSTR1DataMapper):
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
        item_f.TAXABLE_VALUE: 0,
        item_f.IGST: 0,
        item_f.CESS: 0,
    }
    KEY_MAPPING = {
        gov_f.FLAG: "flag",
        gov_f.TYPE: inv_f.DOC_TYPE,
        gov_f.NOTE_TYPE: inv_f.TRANSACTION_TYPE,
        gov_f.NOTE_NUMBER: inv_f.DOC_NUMBER,
        gov_f.NOTE_DATE: inv_f.DOC_DATE,
        gov_f.DOC_VALUE: inv_f.DOC_VALUE,
        gov_f.POS: inv_f.POS,
        gov_f.DIFF_PERCENTAGE: inv_f.DIFF_PERCENTAGE,
        gov_f.ITEMS: inv_f.ITEMS,
        gov_f.TAX_RATE: item_f.TAX_RATE,
        gov_f.TAXABLE_VALUE: item_f.TAXABLE_VALUE,
        gov_f.IGST: item_f.IGST,
        gov_f.CESS: item_f.CESS,
        gov_f.ERROR_CD: inv_f.ERROR_CD,
        gov_f.ERROR_MSG: inv_f.ERROR_MSG,
    }
    DOCUMENT_TYPES = {
        "C": "Credit Note",
        "D": "Debit Note",
    }

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            gov_f.ITEMS: self.format_item_for_internal,
            gov_f.NOTE_TYPE: self.document_type_mapping,
            gov_f.POS: self.map_place_of_supply,
            gov_f.DOC_VALUE: self.format_doc_value,
            gov_f.NOTE_DATE: self.format_date_for_internal,
        }

        self.value_formatters_for_gov = {
            inv_f.ITEMS: self.format_item_for_gov,
            inv_f.TRANSACTION_TYPE: self.document_type_mapping,
            inv_f.POS: self.map_place_of_supply,
            inv_f.DOC_VALUE: lambda x, *args: abs(x),  # nosemgrep
            inv_f.DOC_DATE: self.format_date_for_gov,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)
            self.update_totals(invoice_data, invoice_data.get(inv_f.ITEMS))
            output[invoice_data[inv_f.DOC_NUMBER]] = invoice_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        self.DOCUMENT_TYPES = self.reverse_dict(self.DOCUMENT_TYPES)
        return [self.format_data(invoice, for_gov=True) for invoice in input_data]

    def format_item_for_internal(self, items, *args):
        formatted_items = super().format_item_for_internal(items, *args)

        data = args[0]
        if data[gov_f.NOTE_TYPE] == "D":
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
        return value * -1 if data[gov_f.NOTE_TYPE] == "C" else value


class HSNSUM(GSTR1DataMapper):
    """
    GST API Version - Supports both v4.1 and v4.0

    Government Data Format:
        {
            "flag": "N",
            "chksum": "11b149c8af5cff3580ed478a60233c1",
            "hsn_b2b": [
                {
                    "num": 1,
                    "hsn_sc": "1102",
                    "desc": "CEREAL FLOURS OTHER THAN THAT OF WHEAT OR MESLIN",
                    "user_desc": "WHEAT FLOUR",
                    "uqc": "BOX",
                    "qty": 2,
                    "txval": 100,
                    "camt": 0.5,
                    "samt": 0.5,
                    "rt": 1
                }
            ],
        }

    Internal Data Format:
        {
            'HSN Summary - B2B': {
                '1102 - BOX-BOX - 1.0': {
                    'document_type': 'HSN Summary - B2B',
                    'hsn_code': '1102',
                    'description': 'CEREAL FLOURS OTHER THAN THAT OF WHEAT OR MESLIN',
                    'uom': 'BOX-BOX',
                    'quantity': 2,
                    'total_taxable_value': 100,
                    'total_cgst_amount': 0.5,
                    'total_sgst_amount': 0.5,
                    'tax_rate': 1,
                    'document_value': 101
                }
            }
        }
    """

    DOCUMENT_CATEGORIES = {
        gov_f.HSN_B2B: GSTR1_SubCategory.HSN_B2B.value,
        gov_f.HSN_B2C: GSTR1_SubCategory.HSN_B2C.value,
        gov_f.HSN_DATA: GSTR1_SubCategory.HSN.value,  # Backwards Compatibility
    }
    KEY_MAPPING = {
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        gov_f.HSN_CODE: inv_f.HSN_CODE,
        gov_f.DESCRIPTION: inv_f.DESCRIPTION,
        gov_f.UOM: inv_f.UOM,
        gov_f.QUANTITY: inv_f.QUANTITY,
        gov_f.TAXABLE_VALUE: inv_f.TAXABLE_VALUE,
        gov_f.IGST: inv_f.IGST,
        gov_f.CGST: inv_f.CGST,
        gov_f.SGST: inv_f.SGST,
        gov_f.CESS: inv_f.CESS,
        gov_f.TAX_RATE: item_f.TAX_RATE,
    }

    def __init__(self):
        super().__init__()
        self.value_formatters_for_internal = {gov_f.UOM: self.map_uom}
        self.value_formatters_for_gov = {
            inv_f.UOM: self.map_uom,
            inv_f.DESCRIPTION: lambda x, *args: x[:30],
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        # error JSON is diff from normal JSON
        if isinstance(input_data, dict):
            input_data = [input_data]

        for row in input_data:
            default_data = {
                inv_f.ERROR_CD: row.get(gov_f.ERROR_CD),
                inv_f.ERROR_MSG: row.get(gov_f.ERROR_MSG),
            }

            for section, invoices in row.items():
                if section not in self.DOCUMENT_CATEGORIES:
                    continue

                document_type = self.DOCUMENT_CATEGORIES.get(section, section)

                formatted_invoices = self.get_formatted_invoices(
                    invoices, document_type, default_data
                )

                # This is required due to different format of error JSON
                if output.get(document_type):
                    output[document_type].update(formatted_invoices)
                else:
                    output[document_type] = formatted_invoices

        return output

    def convert_to_gov_data_format(self, input_data, **kwargs):
        output = {}
        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)
        index = defaultdict(int)

        for invoice in input_data:
            doc_type = invoice.get(inv_f.DOC_TYPE) or GSTR1_SubCategory.HSN.value
            section = self.DOCUMENT_CATEGORIES.get(doc_type, doc_type)
            index[section] += 1

            output.setdefault(section, []).append(
                self.format_data(
                    invoice,
                    {gov_f.INDEX: index[section]},
                    for_gov=True,
                )
            )

        return output

    def get_formatted_invoices(self, invoices, document_type, default_data=None):
        return {
            " - ".join(
                (
                    invoice.get(gov_f.HSN_CODE, ""),
                    self.map_uom(invoice.get(gov_f.UOM, "")),
                    str(flt(invoice.get(gov_f.TAX_RATE))),
                )
            ): self.format_data(
                invoice,
                {
                    **default_data,
                    inv_f.DOC_TYPE: document_type,
                },
            )
            for invoice in invoices
        }

    def format_data(self, data, default_data=None, for_gov=False):
        data = super().format_data(data, default_data, for_gov)

        if for_gov:
            return data

        data[inv_f.DOC_VALUE] = sum(
            (
                data.get(inv_f.TAXABLE_VALUE, 0),
                data.get(inv_f.IGST, 0),
                data.get(inv_f.CGST, 0),
                data.get(inv_f.SGST, 0),
                data.get(inv_f.CESS, 0),
            )
        )

        return data

    def map_uom(self, uom, data=None):
        uom = uom.upper()

        if "-" in uom:
            if (
                data
                and (hsn_code := data.get(inv_f.HSN_CODE) or "")
                and hsn_code.startswith("99")
            ):
                return "NA"

            return uom.split("-")[0]

        if uom in UOM_MAP:
            return f"{uom}-{UOM_MAP[uom]}"

        return f"OTH-{UOM_MAP.get('OTH')}"


class AT(GSTR1DataMapper):
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
        gov_f.FLAG: "flag",
        gov_f.POS: inv_f.POS,
        gov_f.DIFF_PERCENTAGE: inv_f.DIFF_PERCENTAGE,
        gov_f.ITEMS: inv_f.ITEMS,
        gov_f.TAX_RATE: item_f.TAX_RATE,
        gov_f.ADVANCE_AMOUNT: inv_f.TAXABLE_VALUE,
        gov_f.IGST: inv_f.IGST,
        gov_f.CGST: inv_f.CGST,
        gov_f.SGST: inv_f.SGST,
        gov_f.CESS: inv_f.CESS,
        gov_f.ERROR_CD: inv_f.ERROR_CD,
        gov_f.ERROR_MSG: inv_f.ERROR_MSG,
    }
    DEFAULT_ITEM_AMOUNTS = {
        inv_f.IGST: 0,
        inv_f.CESS: 0,
        inv_f.CGST: 0,
        inv_f.SGST: 0,
        inv_f.TAXABLE_VALUE: 0,
    }
    MULTIPLIER = 1

    def __init__(self):
        super().__init__()

        self.value_formatters_for_internal = {
            gov_f.ITEMS: self.format_item_for_internal,
            gov_f.POS: self.map_place_of_supply,
        }

        self.value_formatters_for_gov = {
            # df.ITEMS: self.format_item_for_gov,
            inv_f.POS: self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)
            items = invoice_data.pop(inv_f.ITEMS)

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
                            invoice_data.get(inv_f.POS, ""),
                            str(flt(item_data.get(inv_f.TAX_RATE, ""))),
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

            pos_data = pos_wise_data.setdefault(invoice[inv_f.POS], formatted_data)

            pos_data.setdefault(gov_f.ITEMS, []).extend(rate_wise_taxes[gov_f.ITEMS])

        return list(pos_wise_data.values())

    def get_item_details(self, invoice):
        """
        Transfer document values to item level (by POS and tax rate)
        """
        return {
            gov_f.ITEMS: [
                {
                    key: invoice.pop(key)
                    for key in [
                        gov_f.IGST,
                        gov_f.CESS,
                        gov_f.CGST,
                        gov_f.SGST,
                        gov_f.ADVANCE_AMOUNT,
                        gov_f.TAX_RATE,
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

        data[gov_f.SUPPLY_TYPE] = (
            "INTRA" if data[gov_f.POS] == self.company_gstin[:2] else "INTER"
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


class DOC_ISSUE(GSTR1DataMapper):
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
        gov_f.FROM_SR: inv_f.FROM_SR,
        gov_f.TO_SR: inv_f.TO_SR,
        gov_f.TOTAL_COUNT: inv_f.TOTAL_COUNT,
        gov_f.CANCELLED_COUNT: inv_f.CANCELLED_COUNT,
        gov_f.NET_ISSUE: inv_f.NET_ISSUE,
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

        for document in input_data[gov_f.DOC_ISSUE_DETAILS]:
            document_nature = self.get_document_nature(
                document.get(gov_f.DOC_ISSUE_NUMBER, "")
            )
            output.update(
                {
                    " - ".join(
                        (document_nature, doc.get(gov_f.FROM_SR))
                    ): self.format_data(doc, {inv_f.DOC_TYPE: document_nature})
                    for doc in document[gov_f.DOC_ISSUE_LIST]
                }
            )

        return {GSTR1_SubCategory.DOC_ISSUE.value: output}

    def convert_to_gov_data_format(self, input_data, **kwargs):
        self.DOCUMENT_NATURE = self.reverse_dict(self.DOCUMENT_NATURE)

        output = {gov_f.DOC_ISSUE_DETAILS: []}
        doc_nature_wise_data = {}

        for invoice in input_data:
            if invoice[inv_f.DOC_TYPE].startswith("Excluded from Report"):
                continue

            doc_nature_wise_data.setdefault(invoice[inv_f.DOC_TYPE], []).append(invoice)

        input_data = doc_nature_wise_data

        output = {
            gov_f.DOC_ISSUE_DETAILS: [
                {
                    gov_f.DOC_ISSUE_NUMBER: self.get_document_nature(doc_nature),
                    gov_f.DOC_ISSUE_LIST: [
                        self.format_data(
                            document,
                            {gov_f.INDEX: index + 1},
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
        data[inv_f.CANCELLED_COUNT] += data.get(inv_f.DRAFT_COUNT, 0)
        data["net_issue"] = data[inv_f.TOTAL_COUNT] - data.get(inv_f.CANCELLED_COUNT, 0)

        return super().format_data(data, additional_data, for_gov)

    def get_document_nature(self, doc_nature, *args):
        return self.DOCUMENT_NATURE.get(doc_nature, doc_nature)


class SUPECOM(GSTR1DataMapper):
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
        gov_f.ECOMMERCE_GSTIN: inv_f.ECOMMERCE_GSTIN,
        gov_f.NET_TAXABLE_VALUE: inv_f.TAXABLE_VALUE,
        "igst": item_f.IGST,
        "cgst": item_f.CGST,
        "sgst": item_f.SGST,
        "cess": item_f.CESS,
        gov_f.FLAG: "flag",
    }
    DOCUMENT_CATEGORIES = {
        gov_f.SUPECOM_52: GSTR1_SubCategory.SUPECOM_52.value,
        gov_f.SUPECOM_9_5: GSTR1_SubCategory.SUPECOM_9_5.value,
    }

    def __init__(self):
        super().__init__()

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for section, invoices in input_data.items():
            document_type = self.DOCUMENT_CATEGORIES.get(section, section)
            output[document_type] = {
                invoice.get(gov_f.ECOMMERCE_GSTIN, ""): self.format_data(
                    invoice, {inv_f.DOC_TYPE: document_type}
                )
                for invoice in invoices
            }

        return output

    def convert_to_gov_data_format(self, input_data, **kwargs):
        output = {}
        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)

        for invoice in input_data:
            section = invoice[inv_f.DOC_TYPE]
            output.setdefault(
                self.DOCUMENT_CATEGORIES.get(section, section), []
            ).append(self.format_data(invoice, for_gov=True))
        return output


class RETSUM(GSTR1DataMapper):
    """
    Convert GSTR-1 Summary as returned by the API to the internal format

    Usecase: Compute amendment liability for GSTR-1 Summary

    Exceptions:
        - Only supports latest summary format v4.0 and above
    """

    KEY_MAPPING = {
        "sec_nm": inv_f.DESCRIPTION,
        "typ": inv_f.DESCRIPTION,
        "ttl_rec": "no_of_records",
        "ttl_val": "total_document_value",
        "ttl_igst": inv_f.IGST,
        "ttl_cgst": inv_f.CGST,
        "ttl_sgst": inv_f.SGST,
        "ttl_cess": inv_f.CESS,
        "ttl_tax": inv_f.TAXABLE_VALUE,
        "act_val": "actual_document_value",
        "act_igst": "actual_igst",
        "act_sgst": "actual_sgst",
        "act_cgst": "actual_cgst",
        "act_cess": "actual_cess",
        "act_tax": "actual_taxable_value",
        "ttl_expt_amt": f"total_{inv_f.EXEMPTED_AMOUNT}",
        "ttl_ngsup_amt": f"total_{inv_f.NON_GST_AMOUNT}",
        "ttl_nilsup_amt": f"total_{inv_f.NIL_RATED_AMOUNT}",
        "ttl_doc_issued": inv_f.TOTAL_COUNT,
        "ttl_doc_cancelled": inv_f.CANCELLED_COUNT,
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
        "HSN": GSTR1_Category.HSN.value,  # Backwards Compatibility
        "HSN_B2B": GSTR1_SubCategory.HSN_B2B.value,
        "HSN_B2C": GSTR1_SubCategory.HSN_B2C.value,
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
                output[formatted_data[inv_f.DESCRIPTION]] = formatted_data

        return {"summary": output}

    def format_data(self, data, default_data=None, for_gov=False):
        response = super().format_data(data, default_data, for_gov)

        if data.get("sec_nm") == "DOC_ISSUE":
            response["no_of_records"] = data.get("net_doc_issued", 0)

        return response

    def format_subsection_data(self, section, subsection_data):
        subsection = subsection_data.get("typ") or subsection_data.get("sec_nm")
        formatted_data = self.format_data(subsection_data)

        formatted_data[inv_f.DESCRIPTION] = self.SECTIONS_WITH_SUBSECTIONS[section].get(
            subsection, subsection
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

    def get_category_from_subcategory(
        self, invoice_sub_category: str
    ) -> GSTR1_Category:
        invoice_sub_category = GSTR1_SubCategory(invoice_sub_category)
        for category, sub_category in CATEGORY_SUB_CATEGORY_MAPPING.items():
            if invoice_sub_category in sub_category:
                return category

    DATA_TO_ITEM_FIELD_MAPPING = {
        inv_f.TAXABLE_VALUE: item_f.TAXABLE_VALUE,
        inv_f.IGST: item_f.IGST,
        inv_f.CGST: item_f.CGST,
        inv_f.SGST: item_f.SGST,
        inv_f.CESS: item_f.CESS,
    }

    ITEM_TO_INVOICE_FIELD_MAPPING = {
        item_f.TAXABLE_VALUE: "taxable_value",
        item_f.IGST: "igst_amount",
        item_f.CGST: "cgst_amount",
        item_f.SGST: "sgst_amount",
        item_f.CESS: "total_cess_amount",
    }

    DATA_TO_INVOICE_FIELD_MAPPING = {
        inv_f.TAXABLE_VALUE: "taxable_value",
        inv_f.IGST: "igst_amount",
        inv_f.CGST: "cgst_amount",
        inv_f.SGST: "sgst_amount",
        inv_f.CESS: "total_cess_amount",
    }

    PRECISION = 2

    def process_data_for_invoice_no_key(self, grouped_data, prepared_data):
        """
        Input:
            grouped_data: {
                (invoice_sub_category, invoice_no): {
                    gst_rate: [invoice_items]
                }
            }
            prepared_data: dict to be updated with the processed data
        """
        if not grouped_data:
            return

        for (sub_category, invoice_no), rate_wise_item in grouped_data.items():
            doc = next(chain(*rate_wise_item.values()))

            if sub_category not in prepared_data:
                prepared_data[sub_category] = {}

            sub_category_dict = prepared_data[sub_category]
            sub_category_dict[invoice_no] = {
                # TODO: make a method for creating the dict
                inv_f.TRANSACTION_TYPE: self.get_transaction_type(doc),
                inv_f.CUST_GSTIN: doc.billing_address_gstin,
                inv_f.CUST_NAME: doc.customer_name,
                inv_f.DOC_DATE: doc.posting_date,
                inv_f.DOC_NUMBER: doc.invoice_no,
                inv_f.DOC_VALUE: doc.invoice_total,
                inv_f.POS: doc.place_of_supply,
                inv_f.REVERSE_CHARGE: ("Y" if doc.is_reverse_charge else "N"),
                inv_f.DOC_TYPE: doc.invoice_type,
                **self.get_invoice_values(),
                inv_f.DIFF_PERCENTAGE: 0,
                inv_f.SHIPPING_PORT_CODE: doc.shipping_port_code,
                inv_f.SHIPPING_BILL_NUMBER: doc.shipping_bill_number,
                inv_f.SHIPPING_BILL_DATE: doc.shipping_bill_date,
                "items": [],
            }

            invoice = sub_category_dict[invoice_no]

            for gst_rate, items in rate_wise_item.items():
                tax_item = defaultdict(int)

                for item in items:
                    for key, field in self.ITEM_TO_INVOICE_FIELD_MAPPING.items():
                        tax_item[key] += item.get(field, 0)

                tax_item[item_f.TAX_RATE] = gst_rate
                invoice["items"].append(dict(tax_item))

            # Aggregate the values for each item field with same GST Rate
            # Round off this aggregated value and compute the difference at GST Rate level

            for key, field in self.DATA_TO_ITEM_FIELD_MAPPING.items():
                for item in invoice["items"]:
                    value = item.get(field, 0)
                    rounded = flt(value, self.PRECISION)
                    diff = value - rounded

                    item[field] = rounded
                    invoice[key] += rounded

                    self.rounding_difference[key] += diff

                rounded = flt(invoice[key], self.PRECISION)
                invoice[key] = rounded
                self.invoice_totals[doc.hsn_sub_category][key] += rounded

    def process_data_for_nil_exempt(self, grouped_data, prepared_data):
        """
        Input:
            grouped_data: {
                (invoice_sub_category, invoice_no): {
                    gst_rate: [invoice_items]
                }
            }
            prepared_data: dict to be updated with the processed data
        """
        if not grouped_data:
            return

        sub_category = GSTR1_SubCategory.NIL_EXEMPT.value
        nil_exempt = prepared_data.setdefault(sub_category, {})

        for _, rate_wise_item in grouped_data.items():
            item = next(chain(*rate_wise_item.values()), None)

            if item.invoice_type not in nil_exempt:
                nil_exempt[item.invoice_type] = []

            invoices_by_type = nil_exempt[item.invoice_type]

            invoice = {
                inv_f.TRANSACTION_TYPE: self.get_transaction_type(item),
                inv_f.CUST_GSTIN: item.billing_address_gstin,
                inv_f.CUST_NAME: item.customer_name,
                inv_f.DOC_NUMBER: item.invoice_no,
                inv_f.DOC_DATE: item.posting_date,
                inv_f.DOC_VALUE: item.invoice_total,
                inv_f.POS: item.place_of_supply,
                inv_f.REVERSE_CHARGE: ("Y" if item.is_reverse_charge else "N"),
                inv_f.DOC_TYPE: item.invoice_type,
                inv_f.TAXABLE_VALUE: 0,
                inv_f.NIL_RATED_AMOUNT: 0,
                inv_f.EXEMPTED_AMOUNT: 0,
                inv_f.NON_GST_AMOUNT: 0,
            }

            invoices_by_type.append(invoice)

            for item in chain(*rate_wise_item.values()):
                invoice[inv_f.TAXABLE_VALUE] += item.taxable_value

                if item.gst_treatment == "Nil-Rated":
                    invoice[inv_f.NIL_RATED_AMOUNT] += item.taxable_value

                elif item.gst_treatment == "Exempted":
                    invoice[inv_f.EXEMPTED_AMOUNT] += item.taxable_value

                elif item.gst_treatment == "Non-GST":
                    invoice[inv_f.NON_GST_AMOUNT] += item.taxable_value

            # Round
            key = inv_f.TAXABLE_VALUE
            val = invoice.get(key, 0)
            rounded = flt(val, self.PRECISION)
            diff = val - rounded

            invoice[key] = rounded

            self.rounding_difference[key] += diff
            self.invoice_totals[item.hsn_sub_category][key] += rounded

    def process_data_for_b2cs(self, grouped_data, prepared_data):
        """
        Input:
            grouped_data: {
                (invoice_sub_category, invoice_no): {
                    gst_rate: [invoice_items]
                }
            }
            prepared_data: dict to be updated with the processed data
        """
        if not grouped_data:
            return

        sub_category = GSTR1_Category.B2CS.value
        b2c_others = prepared_data.setdefault(sub_category, {})

        for _, rate_wise_item in grouped_data.items():
            for gst_rate, items in rate_wise_item.items():
                item = items[0]
                key = f"{item.place_of_supply} - {flt(gst_rate)}"

                if key not in b2c_others:
                    b2c_others[key] = []

                invoice_list = b2c_others[key]

                invoice = {
                    inv_f.DOC_DATE: item.posting_date,
                    inv_f.DOC_NUMBER: item.invoice_no,
                    inv_f.DOC_VALUE: item.invoice_total,
                    inv_f.CUST_NAME: item.customer_name,
                    # currently other value is not supported in GSTR-1
                    inv_f.DOC_TYPE: "OE",
                    inv_f.TRANSACTION_TYPE: self.get_transaction_type(item),
                    inv_f.POS: item.place_of_supply,
                    inv_f.TAX_RATE: item.gst_rate,
                    inv_f.ECOMMERCE_GSTIN: item.ecommerce_gstin,
                    **self.get_invoice_values(),
                }

                invoice_list.append(invoice)

                for key, field in self.DATA_TO_INVOICE_FIELD_MAPPING.items():

                    for item in items:
                        invoice[key] += item.get(field, 0)

                    val = invoice.get(key, 0)
                    rounded = flt(val, self.PRECISION)
                    diff = val - rounded

                    invoice[key] = rounded

                    self.rounding_difference[key] += diff
                    self.invoice_totals[item.hsn_sub_category][key] += rounded

    def process_data_for_hsn_summary(self, grouped_data, prepared_data):
        """
        Input:
            grouped_data: {
                invoice_sub_category: {
                    "gst_hsn_code - uom - gst_rate": [invoice_items]
                }
            }
            prepared_data: dict to be updated with the processed data
        """

        data_to_invoice_field_map = {
            **self.DATA_TO_INVOICE_FIELD_MAPPING,
            inv_f.QUANTITY: "qty",
        }
        tax_fields = self.DATA_TO_INVOICE_FIELD_MAPPING.keys()

        for sub_category, hsn_key in grouped_data.items():
            sub_category_dict = prepared_data.setdefault(sub_category, {})

            # HSN Descriptions
            hsn_codes = [key.split(" - ")[0] for key in hsn_key]
            descriptions = frappe._dict(
                frappe.get_all(
                    "GST HSN Code",
                    fields=["name", "description"],
                    filters={"name": ["in", hsn_codes]},
                    as_list=True,
                )
            )

            # Map
            for key, items in hsn_key.items():
                item = items[0]

                sub_category_dict[key] = {
                    inv_f.DOC_TYPE: sub_category,
                    inv_f.HSN_CODE: item.gst_hsn_code,
                    inv_f.DESCRIPTION: descriptions.get(item.gst_hsn_code),
                    inv_f.UOM: item.uom,
                    inv_f.QUANTITY: 0,
                    inv_f.TAX_RATE: item.gst_rate,
                    **self.get_invoice_values(),
                }

                invoice = sub_category_dict[key]

                # Aggregate
                for key, field in data_to_invoice_field_map.items():
                    for item in items:
                        invoice[key] += item.get(field, 0)

                    invoice[key] = flt(invoice[key], self.PRECISION)

                doc_value = sum([invoice.get(field, 0) for field in tax_fields])
                invoice[inv_f.DOC_VALUE] = flt(doc_value, self.PRECISION)

            if hasattr(self, "invoice_totals"):
                self.adjust_hsn_totals(sub_category, sub_category_dict)

    def process_data_for_document_issued_summary(self, row, prepared_data):
        key = f"{row['nature_of_document']} - {row['from_serial_no']}"

        if key in prepared_data:
            return

        prepared_data[key] = {
            inv_f.DOC_TYPE: row["nature_of_document"],
            inv_f.FROM_SR: row["from_serial_no"],
            inv_f.TO_SR: row["to_serial_no"],
            inv_f.TOTAL_COUNT: row["total_issued"],
            inv_f.DRAFT_COUNT: row["total_draft"],
            inv_f.CANCELLED_COUNT: row["cancelled"],
            inv_f.NET_ISSUE: row["total_submitted"],
        }

    def process_data_for_advances_received_or_adjusted(
        self, row, prepared_data, multiplier=1
    ):
        advances = {}
        tax_rate = round(((row["tax_amount"] / row["taxable_value"]) * 100))
        key = f"{row['place_of_supply']} - {flt(tax_rate)}"

        mapped_dict = prepared_data.setdefault(key, [])

        advances[inv_f.CUST_NAME] = row["party"]
        advances[inv_f.DOC_NUMBER] = row["name"]
        advances[inv_f.DOC_DATE] = row["posting_date"]
        advances[inv_f.POS] = row["place_of_supply"]
        advances[inv_f.TAXABLE_VALUE] = row["taxable_value"] * multiplier
        advances[inv_f.TAX_RATE] = tax_rate
        advances[inv_f.CESS] = row["cess_amount"] * multiplier

        if row.get("reference_name"):
            advances["against_voucher"] = row["reference_name"]

        if row["place_of_supply"][0:2] == row["company_gstin"][0:2]:
            advances[inv_f.CGST] = row["tax_amount"] / 2 * multiplier
            advances[inv_f.SGST] = row["tax_amount"] / 2 * multiplier
            advances[inv_f.IGST] = 0

        else:
            advances[inv_f.IGST] = row["tax_amount"] * multiplier
            advances[inv_f.CGST] = 0
            advances[inv_f.SGST] = 0

        mapped_dict.append(advances)

    # utils

    def get_invoice_values(self, invoice=None):
        if invoice is None:
            invoice = {}

        return {
            inv_f.TAXABLE_VALUE: invoice.get("taxable_value", 0),
            inv_f.IGST: invoice.get("igst_amount", 0),
            inv_f.CGST: invoice.get("cgst_amount", 0),
            inv_f.SGST: invoice.get("sgst_amount", 0),
            inv_f.CESS: invoice.get("total_cess_amount", 0),
        }

    def initialize_totals(self):
        """
        Initialize the rounding difference dictionary.
        This method is used to reset the rounding difference.
        """
        self.invoice_totals = defaultdict(lambda: defaultdict(float))
        self.rounding_difference = defaultdict(float)

    def update_rounding_difference(self, prepared_data):
        """
        Round off the rounding difference values to 2 decimal places.
        This method is used to round off the rounding difference values.
        """
        precision = cint(frappe.db.get_default("currency_precision")) or None

        for key, value in self.rounding_difference.items():
            self.rounding_difference[key] = flt(value, precision)

        # saved as object -> it's normalized
        prepared_data["rounding_difference"] = {
            "rounding_difference": self.rounding_difference
        }

    def adjust_hsn_totals(self, sub_category, sub_category_dict):
        expected_totals = self.invoice_totals.get(sub_category)
        if not expected_totals:
            return

        # sort -> to ensure adjusted to same row
        hsn_data = sorted(
            sub_category_dict.values(),
            key=lambda item: item.get(inv_f.TAXABLE_VALUE, 0),
            reverse=True,
        )

        # diff
        for row in hsn_data:
            for key in expected_totals:
                expected_totals[key] -= row.get(key, 0)

        # adjust totals
        for key, diff in expected_totals.items():
            for row in hsn_data:
                if row.get(key):
                    row[key] = flt(row[key] + diff, self.PRECISION)
                    break


class GSTR1BooksData(BooksDataMapper):
    def __init__(self, filters):
        self.filters = filters
        if filters.get("month_or_quarter"):
            self.current_month = MONTHS.index(filters.month_or_quarter) + 1

    def prepare_mapped_data(self):
        prepared_data = {}

        _class = GSTR1Invoices(self.filters)
        data = _class.get_invoices_for_item_wise_summary()
        _class.process_invoices(data)

        # initialize rounding difference and hsn error
        self.initialize_totals()

        data_for_hsn, data_for_invoice_no_key, data_for_nil_exempt, data_for_b2cs = (
            self.get_structured_data(data)
        )

        self.process_data_for_invoice_no_key(data_for_invoice_no_key, prepared_data)
        self.process_data_for_nil_exempt(data_for_nil_exempt, prepared_data)
        self.process_data_for_b2cs(data_for_b2cs, prepared_data)

        other_categories = {
            GSTR1_Category.AT.value: self.prepare_advances_recevied_data(),
            GSTR1_Category.TXP.value: self.prepare_advances_adjusted_data(),
            GSTR1_Category.DOC_ISSUE.value: self.prepare_document_issued_data(),
        }

        self.process_data_for_hsn_summary(data_for_hsn, other_categories)

        for category, data in other_categories.items():
            if data:
                prepared_data[category] = data

        self.process_for_quarterly(prepared_data)

        self.update_rounding_difference(prepared_data)

        return prepared_data

    def prepare_hsn_data(self, invoices):
        hsn_summary = {}

        data_for_hsn, *_ = self.get_structured_data(invoices, only_for_hsn=True)
        self.process_data_for_hsn_summary(data_for_hsn, hsn_summary)

        return hsn_summary

    def get_structured_data(self, data, only_for_hsn=False):
        """
        Invoices are bifurcated into different categories by invoice sub-category, invoice number and GST Rate.
        - data_for_invoice_no_key: B2B, B2CL, CDNR, CDNUR, etc.
        - data_for_nil_exempt: Nil Rated, Exempted, Non-GST
        - data_for_b2cs: B2CS (B2C Others)

        Further all invoices are grouped by HSN code, UOM, and GST rate
        - data_for_hsn: HSN Summary
        """
        data_for_invoice_no_key = defaultdict(lambda: defaultdict(list))
        data_for_nil_exempt = defaultdict(lambda: defaultdict(list))
        data_for_b2cs = defaultdict(lambda: defaultdict(list))
        data_for_hsn = defaultdict(lambda: defaultdict(list))

        for item in data:
            gst_rate = flt(item.get("gst_rate"))
            hsn_key = f"{item.gst_hsn_code} - {item.uom} - {gst_rate}"

            data_for_hsn[item.get("hsn_sub_category")][hsn_key].append(item)

            if only_for_hsn or item.get("taxable_value") == 0:
                continue

            key = (item.get("invoice_sub_category"), item.get("invoice_no"))

            invoice_category = GSTR1_Category(item.get("invoice_category"))
            if invoice_category in (
                GSTR1_Category.B2B,
                GSTR1_Category.EXP,
                GSTR1_Category.B2CL,
                GSTR1_Category.CDNR,
                GSTR1_Category.CDNUR,
            ):
                data_for_invoice_no_key[key][gst_rate].append(item)

            elif invoice_category == GSTR1_Category.NIL_EXEMPT:
                data_for_nil_exempt[key][gst_rate].append(item)

            elif invoice_category == GSTR1_Category.B2CS:
                data_for_b2cs[key][gst_rate].append(item)

        return data_for_hsn, data_for_invoice_no_key, data_for_nil_exempt, data_for_b2cs

    def prepare_document_issued_data(self):
        doc_issued_data = {}
        data = GSTR1DocumentIssuedSummary(self.filters).get_data()

        for row in data:
            self.process_data_for_document_issued_summary(row, doc_issued_data)

        return doc_issued_data

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

    def process_for_quarterly(self, data):
        if self.filters.filing_preference != "Quarterly":
            return

        is_m3 = self.current_month % 3 == 0
        m1_m2_subcategories = (
            GSTR1_SubCategory.B2B_REGULAR.value,
            GSTR1_SubCategory.B2B_REVERSE_CHARGE.value,
            GSTR1_SubCategory.SEZWP.value,
            GSTR1_SubCategory.SEZWOP.value,
            GSTR1_SubCategory.DE.value,
            GSTR1_SubCategory.CDNR.value,
        )

        if is_m3:
            self.process_included_docs_for_quarterly(data, m1_m2_subcategories)
        else:
            self.process_excluded_docs_for_quarterly(data, m1_m2_subcategories)

    def process_included_docs_for_quarterly(self, data, m1_m2_subcategories):
        included_docs = self.get_already_filed_docs(m1_m2_subcategories)

        for category in data:
            if category not in m1_m2_subcategories:
                continue

            included = data.setdefault("already_included_docs_for_quarterly", [])

            for key, row in data[category].copy().items():
                if key in included_docs:
                    continue

                row["sub_category"] = category
                included.append(row)
                del data[category][key]

    def process_excluded_docs_for_quarterly(self, data, m1_m2_subcategories):
        for category in data.copy():
            if category in m1_m2_subcategories:
                continue

            if category in (
                GSTR1_SubCategory.HSN.value,  # Backwards Compatibility
                GSTR1_SubCategory.HSN_B2B.value,
                GSTR1_SubCategory.HSN_B2C.value,
                GSTR1_SubCategory.DOC_ISSUE.value,
            ):
                del data[category]
                continue

            excluded = data.setdefault("excluded_docs_for_quarterly", [])

            for row in data[category].values():
                if isinstance(row, dict):
                    row["sub_category"] = category
                    excluded.append(row)

                elif isinstance(row, list):
                    for item in row:
                        item["sub_category"] = category

                    excluded.extend(row)

            del data[category]

        return data

    def get_already_filed_docs(self, m1_m2_subcategories):
        from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
            get_gst_return_log,
        )

        company_gstin = self.filters.company_gstin
        year = self.filters.year

        log_names = [
            f"GSTR1-{(self.current_month - 1):02d}{year}-{company_gstin}",
            f"GSTR1-{(self.current_month - 2):02d}{year}-{company_gstin}",
        ]

        filed_invoices = set()

        for log_name in log_names:
            gstr1_log = get_gst_return_log(
                log_name,
                company=self.filters.company,
                filing_preference=self.filters.filing_preference,
            )

            if not gstr1_log.filed:
                gstr1_log.generate_gstr1_data(self.filters)

            filed_data = gstr1_log.get_json_for("filed")

            for category, invoices in filed_data.items():
                if category not in m1_m2_subcategories:
                    continue

                filed_invoices.update(invoices.keys())

        return filed_invoices
