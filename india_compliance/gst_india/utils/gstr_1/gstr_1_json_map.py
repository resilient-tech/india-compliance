from datetime import datetime

from frappe.utils import flt

from india_compliance.gst_india.constants import STATE_NUMBERS, UOM_MAP
from india_compliance.gst_india.utils.__init__ import get_party_for_gstin
from india_compliance.gst_india.utils.gstr_1 import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    SUB_CATEGORY_GOV_CATEGORY_MAPPING,
    DataFields,
    GovDataFields,
    GSTR1_Categories,
    GSTR1_Gov_Categories,
    GSTR1_SubCategories,
    ItemFields,
)

"""
Map Govt JSON to Internal Data Structure
"""


class DataMapper:
    KEY_MAPPING = {}
    # default item amounts
    DEFAULT_ITEM_AMOUNTS = {
        ItemFields.TAXABLE_VALUE.value: 0,
        ItemFields.IGST.value: 0,
        ItemFields.CGST.value: 0,
        ItemFields.SGST.value: 0,
        ItemFields.CESS.value: 0,
    }

    FLOAT_FIELDS = {
        GovDataFields.DOC_VALUE.value,
        GovDataFields.TAXABLE_VALUE.value,
        GovDataFields.DIFF_PERCENTAGE.value,
        GovDataFields.IGST.value,
        GovDataFields.CGST.value,
        GovDataFields.SGST.value,
        GovDataFields.CESS.value,
    }

    def __init__(self):
        self.set_total_defaults()

        self.json_value_formatters = {}
        self.data_value_formatters = {}
        self.gstin_party_map = {}
        # value formatting constants

        self.STATE_NUMBERS = self.reverse_dict(STATE_NUMBERS)

    def format_data(self, data, default_data=None, reverse=False):
        output = {}

        if default_data:
            output.update(default_data)

        key_mapping = self.KEY_MAPPING.copy()

        if reverse:
            key_mapping = self.reverse_dict(key_mapping)

        value_formatters = (
            self.data_value_formatters if reverse else self.json_value_formatters
        )

        for old_key, new_key in key_mapping.items():
            invoice_data_value = data.get(old_key, "")

            if not (invoice_data_value or invoice_data_value == 0):
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

    def format_item_wise_json_data(self, items, *args):
        return [
            {
                ItemFields.INDEX.value: item[GovDataFields.INDEX.value],
                **self.DEFAULT_ITEM_AMOUNTS.copy(),
                **self.format_data(item.get(GovDataFields.ITEM_DETAILS.value, {})),
            }
            for item in items
        ]

    def format_item_wise_internal_data(self, items, *args):
        return [
            {
                GovDataFields.INDEX.value: item[ItemFields.INDEX.value],
                GovDataFields.ITEM_DETAILS.value: self.format_data(item, reverse=True),
            }
            for item in items
        ]

    def guess_customer_name(self, gstin):
        if party := self.gstin_party_map.get(gstin):
            return party

        return self.gstin_party_map.setdefault(
            gstin, get_party_for_gstin(gstin, "Customer") or "Unknown"
        )

    def format_date(self, date, *args):
        return datetime.strptime(date, "%d-%m-%Y").strftime("%Y-%m-%d")

    def format_date_reverse(self, date, *args):
        return datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")


class B2B(DataMapper):
    KEY_MAPPING = {
        # GovDataFields.CUST_GSTIN.value: DataFields.CUST_GSTIN.value,
        # GovDataFields.INVOICES.value: "invoices",
        # "flag":"flag",
        GovDataFields.DOC_NUMBER.value: DataFields.DOC_NUMBER.value,
        GovDataFields.DOC_DATE.value: DataFields.DOC_DATE.value,
        GovDataFields.DOC_VALUE.value: DataFields.DOC_VALUE.value,
        GovDataFields.POS.value: DataFields.POS.value,
        GovDataFields.REVERSE_CHARGE.value: DataFields.REVERSE_CHARGE.value,
        GovDataFields.ECOMMERCE_GSTIN.value: DataFields.ECOMMERCE_GSTIN.value,
        GovDataFields.INVOICE_TYPE.value: DataFields.DOC_TYPE.value,
        GovDataFields.DIFF_PERCENTAGE.value: DataFields.DIFF_PERCENTAGE.value,
        GovDataFields.ITEMS.value: DataFields.ITEMS.value,
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        GovDataFields.ITEM_DETAILS.value: ItemFields.ITEM_DETAILS.value,
        GovDataFields.TAX_RATE.value: ItemFields.TAX_RATE.value,
        GovDataFields.TAXABLE_VALUE.value: ItemFields.TAXABLE_VALUE.value,
        GovDataFields.IGST.value: ItemFields.IGST.value,
        GovDataFields.CGST.value: ItemFields.CGST.value,
        GovDataFields.SGST.value: ItemFields.SGST.value,
        GovDataFields.CESS.value: ItemFields.CESS.value,
    }

    # value formatting constants
    DOCUMENT_CATEGORIES = {
        "R": "Regular B2B",
        "SEWP": "SEZ supplies with payment",
        "SEWOP": "SEZ supplies without payment",
        "DE": "Deemed Exports",
    }

    SUBCATEGORIES = {
        # "B2B": GSTR1_SubCategories.B2B_REGULAR.value,
        # "B2B": GSTR1_SubCategories.B2B_REVERSE_CHARGE.value,
        "SEWP": GSTR1_SubCategories.SEZWP.value,
        "SEWOP": GSTR1_SubCategories.SEZWOP.value,
        "DE": GSTR1_SubCategories.DE.value,
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            GovDataFields.ITEMS.value: self.format_item_wise_json_data,
            GovDataFields.INVOICE_TYPE.value: self.document_category_mapping,
            GovDataFields.POS.value: self.map_place_of_supply,
            GovDataFields.DOC_DATE.value: self.format_date,
        }

        self.data_value_formatters = {
            DataFields.ITEMS.value: self.format_item_wise_internal_data,
            DataFields.DOC_TYPE.value: self.document_category_mapping,
            DataFields.POS.value: self.map_place_of_supply,
            DataFields.DOC_DATE.value: self.format_date_reverse,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for customer_data in input_data:
            customer_gstin = customer_data.get(GovDataFields.CUST_GSTIN.value)
            # TODO: Guess customer name

            default_invoice_data = {
                DataFields.CUST_GSTIN.value: customer_gstin,
                DataFields.CUST_NAME.value: self.guess_customer_name(customer_gstin),
            }

            for invoice in customer_data.get(GovDataFields.INVOICES.value):
                invoice_data = self.format_data(invoice, default_invoice_data)
                self.update_totals(
                    invoice_data, invoice_data.get(DataFields.ITEMS.value)
                )

                subcategory_data = output.setdefault(
                    self.get_document_subcategory(invoice), {}
                )
                subcategory_data[invoice_data[DataFields.DOC_NUMBER.value]] = (
                    invoice_data
                )

        return output

    def convert_to_gov_data_format(self, input_data):
        input_data = [
            document
            for documents in input_data.values()
            for document in documents.values()
        ]
        customer_data = {}

        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)

        for invoice in input_data:
            customer = customer_data.setdefault(
                invoice[DataFields.CUST_GSTIN.value],
                {
                    GovDataFields.CUST_GSTIN.value: invoice[
                        DataFields.CUST_GSTIN.value
                    ],
                    GovDataFields.INVOICES.value: [],
                },
            )

            customer[GovDataFields.INVOICES.value].append(
                self.format_data(invoice, reverse=True)
            )

        return list(customer_data.values())

    def get_document_subcategory(self, invoice_data):
        if invoice_data.get(GovDataFields.INVOICE_TYPE.value) in self.SUBCATEGORIES:
            return self.SUBCATEGORIES[invoice_data[GovDataFields.INVOICE_TYPE.value]]

        if invoice_data.get(GovDataFields.REVERSE_CHARGE.value) == "Y":
            return GSTR1_SubCategories.B2B_REVERSE_CHARGE.value

        return GSTR1_SubCategories.B2B_REGULAR.value

    # value formatting methods

    def document_category_mapping(self, sub_category, data):
        return self.DOCUMENT_CATEGORIES.get(sub_category, sub_category)


class B2CL(DataMapper):
    DOCUMENT_CATEGORY = "B2C (Large)"
    SUBCATEGORY = GSTR1_SubCategories.B2CL.value
    DEFAULT_ITEM_AMOUNTS = {
        ItemFields.TAXABLE_VALUE.value: 0,
        ItemFields.IGST.value: 0,
        ItemFields.CESS.value: 0,
    }
    KEY_MAPPING = {
        # GovDataFields.POS.value: DataFields.POS.value,
        # GovDataFields.INVOICES.value: "invoices",
        # "flag":"flag",
        GovDataFields.DOC_NUMBER.value: DataFields.DOC_NUMBER.value,
        GovDataFields.DOC_DATE.value: DataFields.DOC_DATE.value,
        GovDataFields.DOC_VALUE.value: DataFields.DOC_VALUE.value,
        GovDataFields.ECOMMERCE_GSTIN.value: DataFields.ECOMMERCE_GSTIN.value,
        GovDataFields.DIFF_PERCENTAGE.value: DataFields.DIFF_PERCENTAGE.value,
        GovDataFields.ITEMS.value: DataFields.ITEMS.value,
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        GovDataFields.ITEM_DETAILS.value: ItemFields.ITEM_DETAILS.value,
        GovDataFields.TAX_RATE.value: ItemFields.TAX_RATE.value,
        GovDataFields.TAXABLE_VALUE.value: ItemFields.TAXABLE_VALUE.value,
        GovDataFields.IGST.value: ItemFields.IGST.value,
        GovDataFields.CESS.value: ItemFields.CESS.value,
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            GovDataFields.ITEMS.value: self.format_item_wise_json_data,
            GovDataFields.DOC_DATE.value: self.format_date,
        }
        self.data_value_formatters = {
            DataFields.ITEMS.value: self.format_item_wise_internal_data,
            DataFields.DOC_DATE.value: self.format_date_reverse,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for pos_data in input_data:
            pos = self.map_place_of_supply(pos_data.get(GovDataFields.POS.value))

            default_invoice_data = {
                DataFields.POS.value: pos,
                DataFields.DOC_TYPE.value: self.DOCUMENT_CATEGORY,
            }

            for invoice in pos_data.get(GovDataFields.INVOICES.value):
                invoice_level_data = self.format_data(invoice, default_invoice_data)
                self.update_totals(
                    invoice_level_data, invoice_level_data.get(DataFields.ITEMS.value)
                )

                output[invoice_level_data[DataFields.DOC_NUMBER.value]] = (
                    invoice_level_data
                )

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = [
            document
            for documents in input_data.values()
            for document in documents.values()
        ]
        pos_data = {}

        for invoice in input_data:
            pos = pos_data.setdefault(
                invoice[DataFields.POS.value],
                {
                    GovDataFields.POS.value: self.map_place_of_supply(
                        invoice[DataFields.POS.value]
                    ),
                    GovDataFields.INVOICES.value: [],
                },
            )

            pos[GovDataFields.INVOICES.value].append(
                self.format_data(invoice, reverse=True)
            )

        return list(pos_data.values())


class Exports(DataMapper):
    DEFAULT_ITEM_AMOUNTS = {
        ItemFields.TAXABLE_VALUE.value: 0,
        ItemFields.IGST.value: 0,
        ItemFields.CESS.value: 0,
    }
    KEY_MAPPING = {
        # GovDataFields.POS.value: DataFields.POS.value,
        # GovDataFields.INVOICES.value: "invoices",
        # "flag":"flag",
        # GovDataFields.EXPORT_TYPE.value: DataFields.DOC_TYPE.value,
        GovDataFields.DOC_NUMBER.value: DataFields.DOC_NUMBER.value,
        GovDataFields.DOC_DATE.value: DataFields.DOC_DATE.value,
        GovDataFields.DOC_VALUE.value: DataFields.DOC_VALUE.value,
        GovDataFields.SHIPPING_PORT_CODE.value: DataFields.SHIPPING_PORT_CODE.value,
        GovDataFields.SHIPPING_BILL_NUMBER.value: DataFields.SHIPPING_BILL_NUMBER.value,
        GovDataFields.SHIPPING_BILL_DATE.value: DataFields.SHIPPING_BILL_DATE.value,
        GovDataFields.ITEMS.value: DataFields.ITEMS.value,
        GovDataFields.TAXABLE_VALUE.value: ItemFields.TAXABLE_VALUE.value,
        GovDataFields.TAX_RATE.value: ItemFields.TAX_RATE.value,
        GovDataFields.IGST.value: ItemFields.IGST.value,
        GovDataFields.CESS.value: ItemFields.CESS.value,
    }

    SUBCATEGORIES = {
        "WPAY": GSTR1_SubCategories.EXPWP.value,
        "WOPAY": GSTR1_SubCategories.EXPWOP.value,
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            GovDataFields.ITEMS.value: self.format_item_wise_json_data,
            GovDataFields.DOC_DATE.value: self.format_date,
            GovDataFields.SHIPPING_BILL_DATE.value: self.format_date,
        }
        self.data_value_formatters = {
            DataFields.ITEMS.value: self.format_item_wise_internal_data,
            DataFields.DOC_DATE.value: self.format_date_reverse,
            DataFields.SHIPPING_BILL_DATE.value: self.format_date_reverse,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for export_category in input_data:
            document_type = export_category.get(GovDataFields.EXPORT_TYPE.value)
            subcategory_data = output.setdefault(
                self.SUBCATEGORIES.get(document_type, document_type), {}
            )

            default_invoice_data = {
                DataFields.DOC_TYPE.value: document_type,
            }

            for invoice in export_category.get(GovDataFields.INVOICES.value):
                invoice_level_data = self.format_data(invoice, default_invoice_data)

                self.update_totals(
                    invoice_level_data, invoice_level_data.get(DataFields.ITEMS.value)
                )
                subcategory_data[invoice_level_data[DataFields.DOC_NUMBER.value]] = (
                    invoice_level_data
                )

        return output

    def convert_to_gov_data_format(self, input_data):
        input_data = [
            document
            for documents in input_data.values()
            for document in documents.values()
        ]
        export_category_wise_data = {}

        for invoice in input_data:
            export_category = export_category_wise_data.setdefault(
                invoice[DataFields.DOC_TYPE.value],
                {
                    GovDataFields.EXPORT_TYPE.value: invoice[DataFields.DOC_TYPE.value],
                    GovDataFields.INVOICES.value: [],
                },
            )

            export_category[GovDataFields.INVOICES.value].append(
                self.format_data(invoice, reverse=True)
            )

        return list(export_category_wise_data.values())

    def format_item_wise_json_data(self, items, *args):
        return [
            {
                **self.DEFAULT_ITEM_AMOUNTS.copy(),
                **self.format_data(item),
            }
            for item in items
        ]

    def format_item_wise_internal_data(self, items, *args):
        return [self.format_data(item, reverse=True) for item in items]


class B2CS(DataMapper):
    SUBCATEGORY = GSTR1_SubCategories.B2CS.value
    KEY_MAPPING = {
        # GovDataFields.SUPPLY_TYPE.value: "supply_type",
        GovDataFields.TAXABLE_VALUE.value: ItemFields.TAXABLE_VALUE.value,
        GovDataFields.TYPE.value: DataFields.DOC_TYPE.value,
        GovDataFields.ECOMMERCE_GSTIN.value: DataFields.ECOMMERCE_GSTIN.value,
        GovDataFields.DIFF_PERCENTAGE.value: DataFields.DIFF_PERCENTAGE.value,
        GovDataFields.POS.value: DataFields.POS.value,
        GovDataFields.TAX_RATE.value: ItemFields.TAX_RATE.value,
        GovDataFields.IGST.value: ItemFields.IGST.value,
        GovDataFields.CGST.value: ItemFields.CGST.value,
        GovDataFields.SGST.value: ItemFields.SGST.value,
        GovDataFields.CESS.value: ItemFields.CESS.value,
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            GovDataFields.ITEMS.value: self.format_item_wise_json_data,
            GovDataFields.POS.value: self.map_place_of_supply,
        }
        self.data_value_formatters = {
            DataFields.ITEMS.value: self.format_item_wise_internal_data,
            DataFields.POS.value: self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)

            output[
                " - ".join(
                    (
                        invoice_data.get(DataFields.POS.value, ""),
                        str(flt(invoice_data.get(DataFields.TAX_RATE.value, ""))),
                        invoice_data.get(DataFields.ECOMMERCE_GSTIN.value, ""),
                    )
                )
            ] = [invoice_data]

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = self.aggregate_invoices(input_data[self.SUBCATEGORY])

        return [self.format_data(invoice, reverse=True) for invoice in input_data]

    def format_data(self, data, default_data=None, reverse=False):
        data = super().format_data(data, default_data, reverse)
        if not reverse:
            return data

        data[GovDataFields.SUPPLY_TYPE.value] = (
            "INTER" if data[GovDataFields.IGST.value] > 0 else "INTRA"
        )
        return data

    def aggregate_invoices(self, input_data):
        output = []

        keys = list(self.DEFAULT_ITEM_AMOUNTS.keys())

        for key, invoices in input_data.items():
            aggregated_invoice = invoices[0].copy()
            aggregated_invoice.update(
                {
                    key: sum([invoice.get(key, 0) for invoice in invoices])
                    for key in keys
                }
            )

            output.append(aggregated_invoice)

        return output


class NilRated(DataMapper):
    SUBCATEGORY = GSTR1_SubCategories.NIL_EXEMPT.value
    KEY_MAPPING = {
        GovDataFields.SUPPLY_TYPE.value: DataFields.DOC_TYPE.value,
        GovDataFields.EXEMPTED_AMOUNT.value: DataFields.EXEMPTED_AMOUNT.value,
        GovDataFields.NIL_RATED_AMOUNT.value: DataFields.NIL_RATED_AMOUNT.value,
        GovDataFields.NON_GST_AMOUNT.value: DataFields.NON_GST_AMOUNT.value,
    }

    DOCUMENT_CATEGORIES = {
        "INTRB2B": "Inter-State supplies to registered persons",
        "INTRB2C": "Inter-State supplies to unregistered persons",
        "INTRAB2B": "Intra-State supplies to registered persons",
        "INTRAB2C": "Intra-State supplies to unregistered persons",
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            GovDataFields.SUPPLY_TYPE.value: self.document_category_mapping
        }
        self.data_value_formatters = {
            DataFields.DOC_TYPE.value: self.document_category_mapping
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data[GovDataFields.INVOICES.value]:
            invoice_data = self.format_data(invoice)

            if not invoice_data:
                continue

            output.setdefault(invoice_data.get(DataFields.DOC_TYPE.value), []).append(
                invoice_data
            )

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = input_data[self.SUBCATEGORY]
        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)

        output = {GovDataFields.INVOICES.value: []}

        for document_type, invoices in input_data.items():
            invoice = self.aggregate_invoices(document_type, invoices)
            invoice = self.format_data(invoice, reverse=True)
            output[GovDataFields.INVOICES.value].append(invoice)

        return output

    def format_data(self, data, default_data=None, reverse=False):
        invoice_data = super().format_data(data, default_data, reverse)

        if reverse:
            return invoice_data

        amounts = [
            invoice_data.get(DataFields.EXEMPTED_AMOUNT.value, 0),
            invoice_data.get(DataFields.NIL_RATED_AMOUNT.value, 0),
            invoice_data.get(DataFields.NON_GST_AMOUNT.value, 0),
        ]

        if all(amount == 0 for amount in amounts):
            return

        invoice_data[DataFields.TAXABLE_VALUE.value] = sum(amounts)
        return invoice_data

    def aggregate_invoices(self, document_type, invoices):
        keys = [
            DataFields.EXEMPTED_AMOUNT.value,
            DataFields.NIL_RATED_AMOUNT.value,
            DataFields.NON_GST_AMOUNT.value,
        ]
        invoice = {key: 0 for key in keys}
        invoice[DataFields.DOC_TYPE.value] = document_type

        for inv in invoices:
            for key in keys:
                invoice[key] += inv.get(key, 0)

        return invoice

    # value formatters
    def document_category_mapping(self, doc_category, data):
        return self.DOCUMENT_CATEGORIES.get(doc_category, doc_category)


class CDNR(DataMapper):
    SUBCATEGORY = GSTR1_SubCategories.CDNR.value
    KEY_MAPPING = {
        # GovDataFields.CUST_GSTIN.value: DataFields.CUST_GSTIN.value,
        # "flag": "flag",
        # GovDataFields.NOTE_DETAILS.value: "credit_debit_note_details",
        GovDataFields.NOTE_TYPE.value: DataFields.TRANSACTION_TYPE.value,
        GovDataFields.NOTE_NUMBER.value: DataFields.DOC_NUMBER.value,
        GovDataFields.NOTE_DATE.value: DataFields.DOC_DATE.value,
        GovDataFields.POS.value: DataFields.POS.value,
        GovDataFields.REVERSE_CHARGE.value: DataFields.REVERSE_CHARGE.value,
        GovDataFields.INVOICE_TYPE.value: DataFields.DOC_TYPE.value,
        GovDataFields.DOC_VALUE.value: DataFields.DOC_VALUE.value,
        GovDataFields.DIFF_PERCENTAGE.value: DataFields.DIFF_PERCENTAGE.value,
        GovDataFields.ITEMS.value: DataFields.ITEMS.value,
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        # GovDataFields.ITEM_DETAILS.value: "item_details",
        GovDataFields.TAX_RATE.value: ItemFields.TAX_RATE.value,
        GovDataFields.TAXABLE_VALUE.value: ItemFields.TAXABLE_VALUE.value,
        GovDataFields.IGST.value: ItemFields.IGST.value,
        GovDataFields.SGST.value: ItemFields.SGST.value,
        GovDataFields.CGST.value: ItemFields.CGST.value,
        GovDataFields.CESS.value: ItemFields.CESS.value,
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

        self.json_value_formatters = {
            GovDataFields.ITEMS.value: self.format_item_wise_json_data,
            GovDataFields.NOTE_TYPE.value: self.document_type_mapping,
            GovDataFields.POS.value: self.map_place_of_supply,
            GovDataFields.INVOICE_TYPE.value: self.document_category_mapping,
            GovDataFields.DOC_VALUE.value: self.format_doc_value,
            GovDataFields.NOTE_DATE.value: self.format_date,
        }

        self.data_value_formatters = {
            DataFields.ITEMS.value: self.format_item_wise_internal_data,
            DataFields.TRANSACTION_TYPE.value: self.document_type_mapping,
            DataFields.POS.value: self.map_place_of_supply,
            DataFields.DOC_TYPE.value: self.document_category_mapping,
            DataFields.DOC_VALUE.value: lambda val, *args: abs(val),
            DataFields.DOC_DATE.value: self.format_date_reverse,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for customer_data in input_data:
            customer_gstin = customer_data.get(GovDataFields.CUST_GSTIN.value)

            for document in customer_data.get(GovDataFields.NOTE_DETAILS.value):
                document_data = self.format_data(
                    document,
                    {
                        DataFields.CUST_GSTIN.value: customer_gstin,
                        DataFields.CUST_NAME.value: self.guess_customer_name(
                            customer_gstin
                        ),
                    },
                )
                self.update_totals(
                    document_data, document_data.get(DataFields.ITEMS.value)
                )
                output[document_data[DataFields.DOC_NUMBER.value]] = document_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = list(input_data[self.SUBCATEGORY].values())
        customer_data = {}

        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)
        self.DOCUMENT_TYPES = self.reverse_dict(self.DOCUMENT_TYPES)

        for document in input_data:
            customer_gstin = document[DataFields.CUST_GSTIN.value]
            customer = customer_data.setdefault(
                customer_gstin,
                {
                    GovDataFields.CUST_GSTIN.value: customer_gstin,
                    GovDataFields.NOTE_DETAILS.value: [],
                },
            )
            customer[GovDataFields.NOTE_DETAILS.value].append(
                self.format_data(document, reverse=True)
            )

        return list(customer_data.values())

    def format_item_wise_json_data(self, items, data):
        formatted_items = super().format_item_wise_json_data(items)

        if data[GovDataFields.NOTE_TYPE.value] == "D":
            return formatted_items

        # for credit notes amounts -ve
        for item in formatted_items:
            item.update(
                {
                    key: -value
                    for key, value in item.items()
                    if key in list(self.DEFAULT_ITEM_AMOUNTS.keys())
                }
            )

        return formatted_items

    def format_item_wise_internal_data(self, items, data):
        formatted_items = super().format_item_wise_internal_data(items)

        if data[DataFields.TRANSACTION_TYPE.value] == "Debit Note":
            return formatted_items

        # for credit notes amounts -ve
        for item in formatted_items:
            item[GovDataFields.ITEM_DETAILS.value].update(
                {
                    key: abs(value)
                    for key, value in item[GovDataFields.ITEM_DETAILS.value].items()
                    if key
                    in [
                        GovDataFields.TAXABLE_VALUE.value,
                        GovDataFields.IGST.value,
                        GovDataFields.SGST.value,
                        GovDataFields.CGST.value,
                        GovDataFields.CESS.value,
                    ]
                }
            )

        return formatted_items

    def document_type_mapping(self, doc_type, data):
        return self.DOCUMENT_TYPES.get(doc_type, doc_type)

    def document_category_mapping(self, doc_category, data):
        return self.DOCUMENT_CATEGORIES.get(doc_category, doc_category)

    def format_doc_value(self, value, data):
        return -value if data[GovDataFields.NOTE_TYPE.value] == "C" else value


class CDNUR(DataMapper):
    SUBCATEGORY = GSTR1_SubCategories.CDNUR.value
    DEFAULT_ITEM_AMOUNTS = {
        ItemFields.TAXABLE_VALUE.value: 0,
        ItemFields.IGST.value: 0,
        ItemFields.CESS.value: 0,
    }
    KEY_MAPPING = {
        # "flag": "flag",
        GovDataFields.TYPE.value: DataFields.DOC_TYPE.value,
        GovDataFields.NOTE_TYPE.value: DataFields.TRANSACTION_TYPE.value,
        GovDataFields.NOTE_NUMBER.value: DataFields.DOC_NUMBER.value,
        GovDataFields.NOTE_DATE.value: DataFields.DOC_DATE.value,
        GovDataFields.DOC_VALUE.value: DataFields.DOC_VALUE.value,
        GovDataFields.POS.value: DataFields.POS.value,
        GovDataFields.DIFF_PERCENTAGE.value: DataFields.DIFF_PERCENTAGE.value,
        GovDataFields.ITEMS.value: DataFields.ITEMS.value,
        GovDataFields.TAX_RATE.value: ItemFields.TAX_RATE.value,
        GovDataFields.TAXABLE_VALUE.value: ItemFields.TAXABLE_VALUE.value,
        GovDataFields.IGST.value: ItemFields.IGST.value,
        GovDataFields.CESS.value: ItemFields.CESS.value,
    }
    DOCUMENT_TYPES = {
        "C": "Credit Note",
        "D": "Debit Note",
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            GovDataFields.ITEMS.value: self.format_item_wise_json_data,
            GovDataFields.NOTE_TYPE.value: self.document_type_mapping,
            GovDataFields.POS.value: self.map_place_of_supply,
            GovDataFields.DOC_VALUE.value: self.format_doc_value,
            GovDataFields.NOTE_DATE.value: self.format_date,
        }

        self.data_value_formatters = {
            DataFields.ITEMS.value: self.format_item_wise_internal_data,
            DataFields.TRANSACTION_TYPE.value: self.document_type_mapping,
            DataFields.POS.value: self.map_place_of_supply,
            DataFields.DOC_VALUE.value: lambda x, *args: abs(x),
            DataFields.DOC_DATE.value: self.format_date_reverse,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)
            self.update_totals(invoice_data, invoice_data.get(DataFields.ITEMS.value))
            output[invoice_data[DataFields.DOC_NUMBER.value]] = invoice_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        self.DOCUMENT_TYPES = self.reverse_dict(self.DOCUMENT_TYPES)
        input_data = list(input_data[self.SUBCATEGORY].values())
        return [self.format_data(invoice, reverse=True) for invoice in input_data]

    def format_item_wise_json_data(self, items, data):
        formatted_items = super().format_item_wise_json_data(items)

        if data[GovDataFields.NOTE_TYPE.value] == "D":
            return formatted_items

        # for credit notes amounts -ve
        for item in formatted_items:
            item.update(
                {
                    key: -value
                    for key, value in item.items()
                    if key in list(self.DEFAULT_ITEM_AMOUNTS.keys())
                }
            )

        return formatted_items

    def format_item_wise_internal_data(self, items, data):
        formatted_items = super().format_item_wise_internal_data(items)

        if data[DataFields.TRANSACTION_TYPE.value] == "Debit Note":
            return formatted_items

        # for credit notes amounts -ve
        for item in formatted_items:
            item[GovDataFields.ITEM_DETAILS.value].update(
                {
                    key: abs(value)
                    for key, value in item[GovDataFields.ITEM_DETAILS.value].items()
                    if key
                    in [
                        GovDataFields.TAXABLE_VALUE.value,
                        GovDataFields.IGST.value,
                        GovDataFields.CESS.value,
                    ]
                }
            )

        return formatted_items

    # value formatters
    def document_type_mapping(self, doc_type, data):
        return self.DOCUMENT_TYPES.get(doc_type, doc_type)

    def format_doc_value(self, value, data):
        return -value if data[GovDataFields.NOTE_TYPE.value] == "C" else value


class HSNSUM(DataMapper):
    SUBCATEGORY = GSTR1_SubCategories.HSN.value
    KEY_MAPPING = {
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        GovDataFields.HSN_CODE.value: DataFields.HSN_CODE.value,
        GovDataFields.DESCRIPTION.value: DataFields.DESCRIPTION.value,
        GovDataFields.UOM.value: DataFields.UOM.value,
        GovDataFields.QUANTITY.value: DataFields.QUANTITY.value,
        GovDataFields.DOC_VALUE.value: DataFields.TAXABLE_VALUE.value,
        GovDataFields.TAXABLE_VALUE.value: DataFields.TAXABLE_VALUE.value,
        GovDataFields.IGST.value: DataFields.IGST.value,
        GovDataFields.CGST.value: DataFields.CGST.value,
        GovDataFields.SGST.value: DataFields.SGST.value,
        GovDataFields.CESS.value: DataFields.CESS.value,
        GovDataFields.TAX_RATE.value: ItemFields.TAX_RATE.value,
    }

    def __init__(self):
        super().__init__()
        self.json_value_formatters = {GovDataFields.UOM.value: self.map_uom}
        self.data_value_formatters = {DataFields.UOM.value: self.map_uom}

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data[GovDataFields.HSN_DATA.value]:
            output[
                " - ".join(
                    (
                        invoice.get(GovDataFields.HSN_CODE.value, ""),
                        self.map_uom(invoice.get(GovDataFields.UOM.value, "")),
                        str(flt(invoice.get(GovDataFields.TAX_RATE.value))),
                    )
                )
            ] = self.format_data(invoice)

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = list(input_data[self.SUBCATEGORY].values())
        return {
            GovDataFields.HSN_DATA.value: [
                self.format_data(
                    invoice, {GovDataFields.INDEX.value: index + 1}, reverse=True
                )
                for index, invoice in enumerate(input_data)
            ]
        }

    def map_uom(self, uom, *args):
        uom = uom.upper()

        if "-" in uom:
            return uom.split("-")[0]

        if uom in UOM_MAP:
            return f"{uom}-{UOM_MAP.get(uom)}"

        return f"OTH-{UOM_MAP.get('OTH')}"


class AT(DataMapper):
    SUBCATEGORY = GSTR1_SubCategories.AT.value
    KEY_MAPPING = {
        # "flag": "flag",
        GovDataFields.POS.value: DataFields.POS.value,
        GovDataFields.DIFF_PERCENTAGE.value: DataFields.DIFF_PERCENTAGE.value,
        GovDataFields.ITEMS.value: DataFields.ITEMS.value,
        GovDataFields.TAX_RATE.value: ItemFields.TAX_RATE.value,
        GovDataFields.ADDITIONAL_AMOUNT.value: DataFields.TAXABLE_VALUE.value,
        GovDataFields.IGST.value: DataFields.IGST.value,
        GovDataFields.CGST.value: DataFields.CGST.value,
        GovDataFields.SGST.value: DataFields.SGST.value,
        GovDataFields.CESS.value: DataFields.CESS.value,
    }
    DEFAULT_ITEM_AMOUNTS = {
        DataFields.IGST.value: 0,
        DataFields.CESS.value: 0,
        DataFields.CGST.value: 0,
        DataFields.SGST.value: 0,
        DataFields.TAXABLE_VALUE.value: 0,
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            GovDataFields.ITEMS.value: self.format_item_wise_json_data,
            GovDataFields.POS.value: self.map_place_of_supply,
        }

        self.data_value_formatters = {
            DataFields.ITEMS.value: self.format_item_wise_internal_data,
            DataFields.POS.value: self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)
            items = invoice_data.pop(DataFields.ITEMS.value)

            for item in items:
                item_data = invoice_data.copy()
                item_data.update(item)
                output[
                    " - ".join(
                        (
                            invoice_data.get(DataFields.POS.value, ""),
                            str(flt(item_data.get(DataFields.TAX_RATE.value, ""))),
                        )
                    )
                ] = [item_data]

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = self.aggregate_invoices(input_data[self.SUBCATEGORY])

        pos_wise_data = {}

        for invoice in input_data:
            formatted_data = self.format_data(invoice, reverse=True)
            formatted_data.update(self.set_item_details(formatted_data))

            pos_data = pos_wise_data.setdefault(
                invoice[DataFields.POS.value],
                {
                    GovDataFields.POS.value: formatted_data[GovDataFields.POS.value],
                    GovDataFields.SUPPLY_TYPE.value: formatted_data[
                        GovDataFields.SUPPLY_TYPE.value
                    ],
                    GovDataFields.DIFF_PERCENTAGE.value: formatted_data[
                        GovDataFields.DIFF_PERCENTAGE.value
                    ],
                    GovDataFields.ITEMS.value: [],
                },
            )

            pos_data[GovDataFields.ITEMS.value].extend(
                formatted_data[GovDataFields.ITEMS.value]
            )

        return list(pos_wise_data.values())

    def set_item_details(self, invoice):
        return {
            GovDataFields.ITEMS.value: [
                {
                    key: invoice.pop(key)
                    for key in [
                        GovDataFields.IGST.value,
                        GovDataFields.CESS.value,
                        GovDataFields.CGST.value,
                        GovDataFields.SGST.value,
                        GovDataFields.ADDITIONAL_AMOUNT.value,
                        GovDataFields.TAX_RATE.value,
                    ]
                }
            ]
        }

    def format_data(self, data, default_data=None, reverse=False):
        data = super().format_data(data, default_data, reverse)
        if not reverse:
            return data

        data[GovDataFields.SUPPLY_TYPE.value] = (
            "INTER" if data[GovDataFields.IGST.value] > 0 else "INTRA"
        )
        return data

    def aggregate_invoices(self, input_data):
        keys = list(self.DEFAULT_ITEM_AMOUNTS.keys())

        output = []

        for key, invoices in input_data.items():
            place_of_supply, tax_rate = key.split(" - ")
            aggregated_invoice = invoices[0].copy()
            aggregated_invoice.update(
                {
                    key: sum([invoice.get(key, 0) for invoice in invoices])
                    for key in keys
                }
            )
            output.append(aggregated_invoice)

        return output

    def format_item_wise_json_data(self, items, *args):
        return [
            {
                **self.DEFAULT_ITEM_AMOUNTS.copy(),
                **self.format_data(item),
            }
            for item in items
        ]

    def format_item_wise_internal_data(self, items, *args):
        return [self.format_data(item, reverse=True) for item in items]


class TXPD(AT):
    SUBCATEGORY = GSTR1_SubCategories.TXP.value


class DOC_ISSUE(DataMapper):
    KEY_MAPPING = {
        # GovDataFields.INDEX.value: ItemFields.INDEX.value,
        GovDataFields.FROM_SR.value: DataFields.FROM_SR.value,
        GovDataFields.TO_SR.value: DataFields.TO_SR.value,
        GovDataFields.TOTAL_COUNT.value: DataFields.TOTAL_COUNT.value,
        GovDataFields.CANCELLED_COUNT.value: DataFields.CANCELLED_COUNT.value,
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

        for document in input_data[GovDataFields.DOC_ISSUE_DETAILS.value]:
            document_nature = self.get_document_nature(
                document.get(GovDataFields.DOC_ISSUE_NUMBER.value, "")
            )
            output.update(
                {
                    " - ".join(
                        (document_nature, doc.get(GovDataFields.FROM_SR.value))
                    ): self.format_data(
                        doc, {DataFields.DOC_TYPE.value: document_nature}
                    )
                    for doc in document[GovDataFields.DOC_ISSUE_LIST.value]
                }
            )

        return {GSTR1_SubCategories.DOC_ISSUE.value: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = input_data[GSTR1_SubCategories.DOC_ISSUE.value]
        self.DOCUMENT_NATURE = self.reverse_dict(self.DOCUMENT_NATURE)

        output = {GovDataFields.DOC_ISSUE_DETAILS.value: []}
        doc_nature_wise_data = {}

        for invoice in input_data.values():
            doc_nature_wise_data.setdefault(
                invoice[DataFields.DOC_TYPE.value], []
            ).append(invoice)

        input_data = doc_nature_wise_data

        output = {
            GovDataFields.DOC_ISSUE_DETAILS.value: [
                {
                    GovDataFields.DOC_ISSUE_NUMBER.value: self.get_document_nature(
                        doc_nature
                    ),
                    GovDataFields.DOC_ISSUE_LIST.value: [
                        self.format_data(
                            document,
                            {GovDataFields.INDEX.value: index + 1},
                            reverse=True,
                        )
                        for index, document in enumerate(documents)
                    ],
                }
                for doc_nature, documents in doc_nature_wise_data.items()
            ]
        }

        return output

    def format_data(self, data, additional_data=None, reverse=False):
        if not reverse:
            return super().format_data(data, additional_data)

        data[DataFields.CANCELLED_COUNT.value] += data.get(
            DataFields.DRAFT_COUNT.value, 0
        )

        formatted_data = super().format_data(data, additional_data, reverse)
        formatted_data[GovDataFields.NET_ISSUE.value] = formatted_data.get(
            GovDataFields.TOTAL_COUNT.value, 0
        ) - formatted_data.get(GovDataFields.CANCELLED_COUNT.value, 0)

        return formatted_data

    def get_document_nature(self, doc_nature, *args):
        return self.DOCUMENT_NATURE.get(doc_nature, doc_nature)


class SUPECOM(DataMapper):
    KEY_MAPPING = {
        GovDataFields.ECOMMERCE_GSTIN.value: DataFields.ECOMMERCE_GSTIN.value,
        GovDataFields.SUPPLIER_VALUE.value: DataFields.SUPPLIER_VALUE.value,
        "igst": ItemFields.IGST.value,
        "cgst": ItemFields.CGST.value,
        "sgst": ItemFields.SGST.value,
        "cess": ItemFields.CESS.value,
    }
    DOCUMENT_CATEGORIES = {
        GovDataFields.SUPECOM_52.value: GSTR1_SubCategories.SUPECOM_52.value,
        GovDataFields.SUPECOM_9_5.value: GSTR1_SubCategories.SUPECOM_9_5.value,
    }

    def __init__(self):
        super().__init__()

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for section, invoices in input_data.items():
            document_type = self.DOCUMENT_CATEGORIES.get(section, section)
            output[document_type] = {
                invoice.get(GovDataFields.ECOMMERCE_GSTIN.value, ""): self.format_data(
                    invoice, {DataFields.DOC_TYPE.value: document_type}
                )
                for invoice in invoices
            }

        return output

    def convert_to_gov_data_format(self, input_data):
        output = {}
        self.DOCUMENT_CATEGORIES = self.reverse_dict(self.DOCUMENT_CATEGORIES)

        for section, invoices in input_data.items():
            output[self.DOCUMENT_CATEGORIES.get(section, section)] = [
                self.format_data(invoice, reverse=True) for invoice in invoices.values()
            ]

        return output


CLASS_MAP = {
    GSTR1_Gov_Categories.B2B.value: B2B,
    GSTR1_Gov_Categories.B2CL.value: B2CL,
    GSTR1_Gov_Categories.EXP.value: Exports,
    GSTR1_Gov_Categories.B2CS.value: B2CS,
    GSTR1_Gov_Categories.NIL_EXEMPT.value: NilRated,
    GSTR1_Gov_Categories.CDNR.value: CDNR,
    GSTR1_Gov_Categories.CDNUR.value: CDNUR,
    GSTR1_Gov_Categories.HSN.value: HSNSUM,
    GSTR1_Gov_Categories.DOC_ISSUE.value: DOC_ISSUE,
    GSTR1_Gov_Categories.AT.value: AT,
    GSTR1_Gov_Categories.TXP.value: TXPD,
    GSTR1_Gov_Categories.SUPECOM.value: SUPECOM,
}


def convert_to_internal_data_format(data):
    output = {}

    for category, mapper_class in CLASS_MAP.items():
        if not data.get(category):
            continue

        output.update(
            mapper_class().convert_to_internal_data_format(data.get(category))
        )

    return output


def convert_to_gov_data_format(data):
    category_wise_data = {}
    for subcategory, category in SUB_CATEGORY_GOV_CATEGORY_MAPPING.items():
        if not data.get(subcategory.value):
            continue

        category_wise_data.setdefault(category.value, {})[subcategory.value] = data.get(
            subcategory.value, {}
        )

    output = {}
    for category, mapper_class in CLASS_MAP.items():
        if not category_wise_data.get(category):
            continue

        output[category] = mapper_class().convert_to_gov_data_format(
            category_wise_data.get(category)
        )

    return output


class RETSUM(DataMapper):
    KEY_MAPPING = {
        "sec_nm": DataFields.DESCRIPTION.value,
        "typ": DataFields.DESCRIPTION.value,
        "ttl_rec": "no_of_records",
        "ttl_val": "total_document_value",
        "ttl_igst": DataFields.IGST.value,
        "ttl_cgst": DataFields.CGST.value,
        "ttl_sgst": DataFields.SGST.value,
        "ttl_cess": DataFields.CESS.value,
        "ttl_tax": DataFields.TAXABLE_VALUE.value,
        "act_val": "actual_document_value",
        "act_igst": "actual_igst",
        "act_sgst": "actual_sgst",
        "act_cgst": "actual_cgst",
        "act_cess": "actual_cess",
        "act_tax": "actual_taxable_value",
        "ttl_expt_amt": f"total_{DataFields.EXEMPTED_AMOUNT.value}",
        "ttl_ngsup_amt": f"total_{DataFields.NON_GST_AMOUNT.value}",
        "ttl_nilsup_amt": f"total_{DataFields.NIL_RATED_AMOUNT.value}",
        "ttl_doc_issued": DataFields.TOTAL_COUNT.value,
        "ttl_doc_cancelled": DataFields.CANCELLED_COUNT.value,
    }

    SECTION_NAMES = {
        "AT": GSTR1_Categories.AT.value,
        "B2B_4A": GSTR1_SubCategories.B2B_REGULAR.value,
        "B2B_4B": GSTR1_SubCategories.B2B_REVERSE_CHARGE.value,
        "B2B_6C": GSTR1_SubCategories.DE.value,
        "B2B_SEZWOP": GSTR1_SubCategories.SEZWOP.value,
        "B2B_SEZWP": GSTR1_SubCategories.SEZWP.value,
        "B2B": GSTR1_Categories.B2B.value,
        "B2CL": GSTR1_Categories.B2CL.value,
        "B2CS": GSTR1_Categories.B2CS.value,
        "TXPD": GSTR1_Categories.TXP.value,
        "EXP": GSTR1_Categories.EXP.value,
        "CDNR": GSTR1_Categories.CDNR.value,
        "CDNUR": GSTR1_Categories.CDNUR.value,
        "SUPECOM": GSTR1_Categories.SUPECOM.value,
        "ECOM": "ECOM",
        "ECOM_REG": "ECOM_REG",
        "ECOM_DE": "ECOM_DE",
        "ECOM_SEZWOP": "ECOM_SEZWOP",
        "ECOM_SEZWP": "ECOM_SEZWP",
        "ECOM_UNREG": "ECOM_UNREG",
        "ATA": f"{GSTR1_Categories.AT.value} (Amended)",
        "B2BA_4A": f"{GSTR1_SubCategories.B2B_REGULAR.value} (Amended)",
        "B2BA_4B": f"{GSTR1_SubCategories.B2B_REVERSE_CHARGE.value} (Amended)",
        "B2BA_6C": f"{GSTR1_SubCategories.DE.value} (Amended)",
        "B2BA_SEZWOP": f"{GSTR1_SubCategories.SEZWOP.value} (Amended)",
        "B2BA_SEZWP": f"{GSTR1_SubCategories.SEZWP.value} (Amended)",
        "B2BA": f"{GSTR1_Categories.B2B.value} (Amended)",
        "B2CLA": f"{GSTR1_Categories.B2CL.value} (Amended)",
        "B2CSA": f"{GSTR1_Categories.B2CS.value} (Amended)",
        "TXPDA": f"{GSTR1_Categories.TXP.value} (Amended)",
        "EXPA": f"{GSTR1_Categories.EXP.value} (Amended)",
        "CDNRA": f"{GSTR1_Categories.CDNR.value} (Amended)",
        "CDNURA": f"{GSTR1_Categories.CDNUR.value} (Amended)",
        "SUPECOMA": f"{GSTR1_Categories.SUPECOM.value} (Amended)",
        "ECOMA": "ECOMA",
        "ECOMA_REG": "ECOMA_REG",
        "ECOMA_DE": "ECOMA_DE",
        "ECOMA_SEZWOP": "ECOMA_SEZWOP",
        "ECOMA_SEZWP": "ECOMA_SEZWP",
        "ECOMA_UNREG": "ECOMA_UNREG",
        "HSN": GSTR1_Categories.HSN.value,
        "NIL": GSTR1_Categories.NIL_EXEMPT.value,
        "DOC_ISSUE": GSTR1_Categories.DOC_ISSUE.value,
        "TTL_LIAB": "Total Liability",
    }

    SECTIONS_WITH_SUBSECTIONS = {
        "SUPECOM": {
            "SUPECOM_14A": GSTR1_SubCategories.SUPECOM_52.value,
            "SUPECOM_14B": GSTR1_SubCategories.SUPECOM_9_5.value,
        },
        "SUPECOMA": {
            "SUPECOMA_14A": f"{GSTR1_SubCategories.SUPECOM_52.value} (Amended)",
            "SUPECOMA_14B": f"{GSTR1_SubCategories.SUPECOM_9_5.value} (Amended)",
        },
        "EXP": {
            "EXPWP": GSTR1_SubCategories.EXPWP.value,
            "EXPWOP": GSTR1_SubCategories.EXPWOP.value,
        },
        "EXPA": {
            "EXPWP": f"{GSTR1_SubCategories.EXPWP.value} (Amended)",
            "EXPWOP": f"{GSTR1_SubCategories.EXPWOP.value} (Amended)",
        },
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            "sec_nm": self.map_document_types,
            "typ": self.map_document_types,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for section_data in input_data["sec_sum"]:
            section = section_data.get("sec_nm")
            output[self.SECTION_NAMES.get(section, section)] = self.format_data(
                section_data
            )

            if section not in self.SECTIONS_WITH_SUBSECTIONS:
                continue

            for subsection_data in section_data["sub_sections"]:
                formatted_data = self.format_subsection_data(section, subsection_data)
                output[formatted_data[DataFields.DESCRIPTION.value]] = formatted_data

        return output

    def format_subsection_data(self, section, subsection_data):
        subsection = subsection_data.get("typ") or subsection_data.get("sec_nm")
        formatted_data = self.format_data(subsection_data)

        formatted_data[DataFields.DESCRIPTION.value] = self.SECTIONS_WITH_SUBSECTIONS[
            section
        ].get(subsection, subsection)
        return formatted_data

    def map_document_types(self, doc_type, *args):
        return self.SECTION_NAMES.get(doc_type, doc_type)


def summarize_retsum_data(input_data):
    summarized_data = []
    total_values_keys = [
        "total_igst_amount",
        "total_cgst_amount",
        "total_sgst_amount",
        "total_cess_amount",
        "total_taxable_value",
    ]
    amended_data = {key: 0 for key in total_values_keys}

    for category in CATEGORY_SUB_CATEGORY_MAPPING:
        if category.value not in input_data:
            continue

        summarized_data.append(
            {
                **input_data.get(category.value),
                "indent": 0,
            }
        )

        amended_category_data = input_data.get(f"{category.value} (Amended)", {})
        amended_data = {
            key: amended_data[key] + amended_category_data.get(key, 0)
            for key in total_values_keys
        }

        for sub_category in CATEGORY_SUB_CATEGORY_MAPPING[category]:
            if sub_category.value not in input_data:
                continue

            summarized_data.append(
                {
                    **input_data.get(sub_category.value),
                    "indent": 1,
                }
            )

            amended_sub_category_data = input_data.get(
                f"{sub_category.value} (Amended)", {}
            )
            amended_data = {
                key: amended_data[key] + amended_sub_category_data.get(key, 0)
                for key in total_values_keys
            }

    summarized_data.extend(
        [
            {
                "description": "Total Amended",
                **amended_data,
                "indent": 0,
            },
            input_data.get("Total Liability"),
        ]
    )

    return summarized_data
