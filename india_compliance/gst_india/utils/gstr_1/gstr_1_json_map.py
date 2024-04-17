from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from india_compliance.gst_india.constants import STATE_NUMBERS, UOM_MAP
from india_compliance.gst_india.utils.gstr_1 import (
    SUB_CATEGORY_GOV_CATEGORY_MAPPING,
    DataFields,
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

    def __init__(self):
        self.set_total_defaults()

        self.json_value_formatters = {}
        self.data_value_formatters = {}
        # value formatting constants

        self.STATE_NUMBERS = {v: k for k, v in STATE_NUMBERS.items()}

    def format_data(self, data, default_data=None, reverse=False):
        output = {}

        if default_data:
            output.update(default_data)

        key_mapping = self.KEY_MAPPING.copy()

        if reverse:
            key_mapping = {v: k for k, v in key_mapping.items()}

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

    # common value formatters
    def map_place_of_supply(self, pos, *args):
        if pos.isnumeric():
            return f"{pos}-{self.STATE_NUMBERS.get(pos)}"

        return pos.split("-")[0]

    def format_item_wise_json_data(self, items, *args):
        return [
            {
                "idx": item["num"],
                **self.DEFAULT_ITEM_AMOUNTS.copy(),
                **self.format_data(item.get("itm_det", {})),
            }
            for item in items
        ]

    def format_item_wise_internal_data(self, items, *args):
        return [
            {"num": item["idx"], "itm_det": self.format_data(item, reverse=True)}
            for item in items
        ]


class B2B(DataMapper):
    KEY_MAPPING = {
        # "ctin": "customer_gstin",
        # "inv": "invoices",
        # "flag":"flag",
        "inum": DataFields.DOC_NUMBER.value,
        "idt": DataFields.DOC_DATE.value,
        "val": DataFields.DOC_VALUE.value,
        "pos": DataFields.POS.value,
        "rchrg": DataFields.REVERSE_CHARGE.value,
        "etin": DataFields.ECOMMERCE_GSTIN.value,
        "inv_typ": DataFields.DOC_TYPE.value,
        "diff_percent": DataFields.DIFF_PERCENTAGE.value,
        "itms": DataFields.ITEMS.value,
        # "num": "idx",
        "itm_det": ItemFields.ITEM_DETAILS.value,
        "rt": ItemFields.TAX_RATE.value,
        "txval": ItemFields.TAXABLE_VALUE.value,
        "iamt": ItemFields.IGST.value,
        "camt": ItemFields.CGST.value,
        "samt": ItemFields.SGST.value,
        "csamt": ItemFields.CESS.value,
    }

    # value formatting constants
    DOCUMENT_CATEGORIES = {
        "R": "Regular B2B",
        "SEZWP": "SEZ supplies with payment",
        "SEWOP": "SEZ supplies without payment",
        "DE": "Deemed Exports",
    }

    SUBCATEGORIES = {
        # "B2B": GSTR1_SubCategories.B2B_REGULAR.value,
        # "B2B": GSTR1_SubCategories.B2B_REVERSE_CHARGE.value,
        "SEZWP": GSTR1_SubCategories.SEZWP.value,
        "SEWOP": GSTR1_SubCategories.SEZWOP.value,
        "DE": GSTR1_SubCategories.DE.value,
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            "itms": self.format_item_wise_json_data,
            "inv_typ": self.document_category_mapping,
            "pos": self.map_place_of_supply,
        }

        self.data_value_formatters = {
            "items": self.format_item_wise_internal_data,
            "document_type": self.document_category_mapping,
            "place_of_supply": self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for customer_data in input_data:
            customer_gstin = customer_data.get("ctin")
            # TODO: Guess customer name

            default_invoice_data = {
                DataFields.CUST_GSTIN.value: customer_gstin,
            }

            for invoice in customer_data.get("inv"):
                invoice_data = self.format_data(invoice, default_invoice_data)
                self.update_totals(invoice_data, invoice_data.get("items"))

                subcategory_data = output.setdefault(
                    self.get_document_subcategory(invoice), {}
                )
                subcategory_data[invoice_data["document_number"]] = invoice_data

        return output

    def convert_to_gov_data_format(self, input_data):
        input_data = [
            document
            for documents in input_data.values()
            for document in documents.values()
        ]
        customer_data = {}

        self.DOCUMENT_CATEGORIES = {v: k for k, v in self.DOCUMENT_CATEGORIES.items()}

        for invoice in input_data:
            customer = customer_data.setdefault(
                invoice["customer_gstin"],
                {"ctin": invoice["customer_gstin"], "inv": []},
            )

            customer["inv"].append(self.format_data(invoice, reverse=True))

        return list(customer_data.values())

    def get_document_subcategory(self, invoice_data):
        if invoice_data.get("inv_typ") in self.SUBCATEGORIES:
            return self.SUBCATEGORIES[invoice_data["inv_typ"]]

        if invoice_data.get("rchrg") == "Y":
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
        # "pos": "place_of_supply",
        # "inv": "invoices",
        # "flag":"flag",
        "inum": DataFields.DOC_NUMBER.value,
        "idt": DataFields.DOC_DATE.value,
        "val": DataFields.DOC_VALUE.value,
        "etin": DataFields.ECOMMERCE_GSTIN.value,
        "diff_percent": DataFields.DIFF_PERCENTAGE.value,
        "itms": DataFields.ITEMS.value,
        # "num": "idx",
        "itm_det": ItemFields.ITEM_DETAILS.value,
        "rt": ItemFields.TAX_RATE.value,
        "txval": ItemFields.TAXABLE_VALUE.value,
        "iamt": ItemFields.IGST.value,
        "csamt": ItemFields.CESS.value,
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {"itms": self.format_item_wise_json_data}
        self.data_value_formatters = {"items": self.format_item_wise_internal_data}

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for pos_data in input_data:
            pos = self.map_place_of_supply(pos_data.get("pos"))

            default_invoice_data = {
                DataFields.POS.value: pos,
                DataFields.DOC_TYPE.value: self.DOCUMENT_CATEGORY,
            }

            for invoice in pos_data.get("inv"):
                invoice_level_data = self.format_data(invoice, default_invoice_data)
                self.update_totals(invoice_level_data, invoice_level_data.get("items"))

                output[invoice_level_data["document_number"]] = invoice_level_data

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
                invoice["place_of_supply"],
                {
                    "pos": self.map_place_of_supply(invoice["place_of_supply"]),
                    "inv": [],
                },
            )

            pos["inv"].append(self.format_data(invoice, reverse=True))

        return list(pos_data.values())


class Exports(DataMapper):
    DEFAULT_ITEM_AMOUNTS = {
        ItemFields.TAXABLE_VALUE.value: 0,
        ItemFields.IGST.value: 0,
        ItemFields.CESS.value: 0,
    }
    KEY_MAPPING = {
        # "pos": "place_of_supply",
        # "inv": "invoices",
        # "flag":"flag",
        # "exp_typ": "document_type",
        "inum": DataFields.DOC_NUMBER.value,
        "idt": DataFields.DOC_DATE.value,
        "val": DataFields.DOC_VALUE.value,
        "sbpcode": DataFields.SHIPPING_PORT_CODE.value,
        "sbnum": DataFields.SHIPPING_BILL_NUMBER.value,
        "sbdt": DataFields.SHIPPING_BILL_DATE.value,
        "itms": DataFields.ITEMS.value,
        "txval": ItemFields.TAXABLE_VALUE.value,
        "rt": ItemFields.TAX_RATE.value,
        "iamt": ItemFields.IGST.value,
        "csamt": ItemFields.CESS.value,
    }

    SUBCATEGORIES = {
        "WPAY": GSTR1_SubCategories.EXPWP.value,
        "WOPAY": GSTR1_SubCategories.EXPWOP.value,
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {"itms": self.format_item_wise_json_data}
        self.data_value_formatters = {"items": self.format_item_wise_internal_data}

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for export_category in input_data:
            document_type = export_category.get("exp_typ")
            subcategory_data = output.setdefault(
                self.SUBCATEGORIES.get(document_type, document_type), {}
            )

            default_invoice_data = {
                DataFields.DOC_TYPE.value: document_type,
            }

            for invoice in export_category.get("inv"):
                invoice_level_data = self.format_data(invoice, default_invoice_data)

                self.update_totals(invoice_level_data, invoice_level_data.get("items"))
                subcategory_data[invoice_level_data["document_number"]] = (
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
                invoice["document_type"],
                {"exp_typ": invoice["document_type"], "inv": []},
            )

            export_category["inv"].append(self.format_data(invoice, reverse=True))

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
        # "sply_ty": "supply_type",
        "txval": ItemFields.TAXABLE_VALUE.value,
        "typ": DataFields.DOC_TYPE.value,
        "etin": DataFields.ECOMMERCE_GSTIN.value,
        "diff_percent": DataFields.DIFF_PERCENTAGE.value,
        "pos": DataFields.POS.value,
        "rt": ItemFields.TAX_RATE.value,
        "iamt": ItemFields.IGST.value,
        "camt": ItemFields.CGST.value,
        "samt": ItemFields.SGST.value,
        "csamt": ItemFields.CESS.value,
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            "itms": self.format_item_wise_json_data,
            "pos": self.map_place_of_supply,
        }
        self.data_value_formatters = {
            "items": self.format_item_wise_internal_data,
            "place_of_supply": self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)

            output.setdefault(
                " - ".join(
                    (
                        invoice_data.get("place_of_supply", ""),
                        str(flt(invoice_data.get("tax_rate", ""))),
                        invoice_data.get("ecommerce_gstin", ""),
                    )
                ),
                [],
            ).append(invoice_data)

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = [
            invoice
            for invoices in list(input_data[self.SUBCATEGORY].values())
            for invoice in invoices
        ]

        return [self.format_data(invoice, reverse=True) for invoice in input_data]

    def format_data(self, data, default_data=None, reverse=False):
        data = super().format_data(data, default_data, reverse)
        if not reverse:
            return data

        data["sply_ty"] = "INTER" if data["iamt"] > 0 else "INTRA"
        return data


class NilRated(DataMapper):
    SUBCATEGORY = GSTR1_SubCategories.NIL_EXEMPT.value
    KEY_MAPPING = {
        "sply_ty": DataFields.DOC_TYPE.value,
        "expt_amt": DataFields.EXEMPTED_AMOUNT.value,
        "nil_amt": DataFields.NIL_RATED_AMOUNT.value,
        "ngsup_amt": DataFields.NON_GST_AMOUNT.value,
    }

    DOCUMENT_CATEGORIES = {
        "INTRB2B": "Inter-State supplies to registered persons",
        "INTRB2C": "Inter-State supplies to unregistered persons",
        "INTRAB2B": "Intra-State supplies to registered persons",
        "INTRAB2C": "Intra-State supplies to unregistered persons",
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {"sply_ty": self.document_category_mapping}
        self.data_value_formatters = {"document_type": self.document_category_mapping}

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data["inv"]:
            invoice_data = self.format_data(invoice)
            output.setdefault(invoice_data.get("document_type"), []).append(
                invoice_data
            )

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = input_data[self.SUBCATEGORY]
        self.DOCUMENT_CATEGORIES = {v: k for k, v in self.DOCUMENT_CATEGORIES.items()}

        output = {"inv": []}

        for document_type, invoices in input_data.items():
            invoice = self.aggregate_invoices(document_type, invoices)
            invoice = self.format_data(invoice, reverse=True)
            output["inv"].append(invoice)

        return output

    def format_data(self, data, default_data=None, reverse=False):
        invoice_data = super().format_data(data, default_data, reverse)

        if reverse:
            return invoice_data

        invoice_data["total_taxable_value"] = sum(
            [
                invoice_data.get("exempted_amount", 0),
                invoice_data.get("nil_rated_amount", 0),
                invoice_data.get("non_gst_amount", 0),
            ]
        )

        return invoice_data

    def aggregate_invoices(self, document_type, invoices):
        keys = ["exempted_amount", "nil_rated_amount", "non_gst_amount"]
        invoice = {key: 0 for key in keys}
        invoice["document_type"] = document_type

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
        # "ctin": "customer_gstin",
        # "flag": "flag",
        # "nt": "credit_debit_note_details",
        "ntty": DataFields.TRANSACTION_TYPE.value,
        "nt_num": DataFields.DOC_NUMBER.value,
        "nt_dt": DataFields.DOC_DATE.value,
        "pos": DataFields.POS.value,
        "rchrg": DataFields.REVERSE_CHARGE.value,
        "inv_typ": DataFields.DOC_TYPE.value,
        "val": DataFields.DOC_VALUE.value,
        "diff_percent": DataFields.DIFF_PERCENTAGE.value,
        "itms": DataFields.ITEMS.value,
        # "num": "idx",
        # "itm_det": "item_details",
        "rt": ItemFields.TAX_RATE.value,
        "txval": ItemFields.TAXABLE_VALUE.value,
        "iamt": ItemFields.IGST.value,
        "samt": ItemFields.SGST.value,
        "camt": ItemFields.CGST.value,
        "csamt": ItemFields.CESS.value,
    }

    DOCUMENT_CATEGORIES = {
        "R": "Regular B2B",
        "SEZWP": "SEZ supplies with payment",
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
            "itms": self.format_item_wise_json_data,
            "ntty": self.document_type_mapping,
            "pos": self.map_place_of_supply,
            "inv_typ": self.document_category_mapping,
            "val": self.format_doc_value,
        }

        self.data_value_formatters = {
            "items": self.format_item_wise_internal_data,
            "transaction_type": self.document_type_mapping,
            "place_of_supply": self.map_place_of_supply,
            "document_type": self.document_category_mapping,
            "document_value": lambda val, *args: abs(val),
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for customer_data in input_data:
            customer_gstin = customer_data.get("ctin")

            for document in customer_data.get("nt"):
                document_data = self.format_data(
                    document, {"customer_gstin": customer_gstin}
                )
                self.update_totals(document_data, document_data.get("items"))
                output[document_data["document_number"]] = document_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = list(input_data[self.SUBCATEGORY].values())
        customer_data = {}

        self.DOCUMENT_CATEGORIES = {v: k for k, v in self.DOCUMENT_CATEGORIES.items()}
        self.DOCUMENT_TYPES = {v: k for k, v in self.DOCUMENT_TYPES.items()}

        for document in input_data:
            customer_gstin = document["customer_gstin"]
            customer = customer_data.setdefault(
                customer_gstin, {"ctin": customer_gstin, "nt": []}
            )
            customer["nt"].append(self.format_data(document, reverse=True))

        return list(customer_data.values())

    def format_item_wise_json_data(self, items, data):
        formatted_items = super().format_item_wise_json_data(items)

        if data["ntty"] == "D":
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

        if data["transaction_type"] == "Debit Note":
            return formatted_items

        # for credit notes amounts -ve
        for item in formatted_items:
            item["itm_det"].update(
                {
                    key: abs(value)
                    for key, value in item["itm_det"].items()
                    if key in ["txval", "iamt", "samt", "camt", "csamt"]
                }
            )

        return formatted_items

    def document_type_mapping(self, doc_type, data):
        return self.DOCUMENT_TYPES.get(doc_type, doc_type)

    def document_category_mapping(self, doc_category, data):
        return self.DOCUMENT_CATEGORIES.get(doc_category, doc_category)

    def format_doc_value(self, value, data):
        return -value if data["ntty"] == "C" else value


class CDNUR(DataMapper):
    SUBCATEGORY = GSTR1_SubCategories.CDNUR.value
    DEFAULT_ITEM_AMOUNTS = {
        ItemFields.TAXABLE_VALUE.value: 0,
        ItemFields.IGST.value: 0,
        ItemFields.CESS.value: 0,
    }
    KEY_MAPPING = {
        # "flag": "flag",
        "typ": DataFields.DOC_TYPE.value,
        "ntty": DataFields.TRANSACTION_TYPE.value,
        "nt_num": DataFields.DOC_NUMBER.value,
        "nt_dt": DataFields.DOC_DATE.value,
        "val": DataFields.DOC_VALUE.value,
        "pos": DataFields.POS.value,
        "diff_percent": DataFields.DIFF_PERCENTAGE.value,
        "itms": DataFields.ITEMS.value,
        "rt": ItemFields.TAX_RATE.value,
        "txval": ItemFields.TAXABLE_VALUE.value,
        "iamt": ItemFields.IGST.value,
        "csamt": ItemFields.CESS.value,
    }
    DOCUMENT_TYPES = {
        "C": "Credit Note",
        "D": "Debit Note",
    }

    def __init__(self):
        super().__init__()

        self.json_value_formatters = {
            "itms": self.format_item_wise_json_data,
            "ntty": self.document_type_mapping,
            "pos": self.map_place_of_supply,
            "val": self.format_doc_value,
        }

        self.data_value_formatters = {
            "items": self.format_item_wise_internal_data,
            "transaction_type": self.document_type_mapping,
            "place_of_supply": self.map_place_of_supply,
            "document_value": lambda x, *args: abs(x),
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)
            self.update_totals(invoice_data, invoice_data.get("items"))
            output[invoice_data["document_number"]] = invoice_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        self.DOCUMENT_TYPES = {v: k for k, v in self.DOCUMENT_TYPES.items()}
        input_data = list(input_data[self.SUBCATEGORY].values())
        return [self.format_data(invoice, reverse=True) for invoice in input_data]

    def format_item_wise_json_data(self, items, data):
        formatted_items = super().format_item_wise_json_data(items)

        if data["ntty"] == "D":
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

        if data["transaction_type"] == "Debit Note":
            return formatted_items

        # for credit notes amounts -ve
        for item in formatted_items:
            item["itm_det"].update(
                {
                    key: abs(value)
                    for key, value in item["itm_det"].items()
                    if key in ["txval", "iamt", "csamt"]
                }
            )

        return formatted_items

    # value formatters
    def document_type_mapping(self, doc_type, data):
        return self.DOCUMENT_TYPES.get(doc_type, doc_type)

    def format_doc_value(self, value, data):
        return -value if data["ntty"] == "C" else value


class HSNSUM(DataMapper):
    SUBCATEGORY = GSTR1_SubCategories.HSN.value
    KEY_MAPPING = {
        "num": ItemFields.INDEX.value,
        "hsn_sc": DataFields.HSN_CODE.value,
        "desc": DataFields.DESCRIPTION.value,
        "uqc": DataFields.UOM.value,
        "qty": DataFields.QUANTITY.value,
        "val": DataFields.TAXABLE_VALUE.value,
        "txval": DataFields.TAXABLE_VALUE.value,
        "iamt": DataFields.IGST.value,
        "camt": DataFields.CGST.value,
        "samt": DataFields.SGST.value,
        "csamt": DataFields.CESS.value,
        "rt": ItemFields.TAX_RATE.value,
    }

    def __init__(self):
        super().__init__()
        self.json_value_formatters = {"uqc": self.map_uom}
        self.data_value_formatters = {"uom": self.map_uom}

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data["data"]:
            output.setdefault(
                " - ".join(
                    (
                        invoice.get("hsn_sc", ""),
                        self.map_uom(invoice.get("uqc", "")),
                        str(invoice.get("rt")),
                    )
                ),
                [],
            ).append(self.format_data(invoice))

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = [
            invoice
            for invoices in list(input_data[self.SUBCATEGORY].values())
            for invoice in invoices
        ]
        return {
            "data": [self.format_data(invoice, reverse=True) for invoice in input_data]
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
        "pos": DataFields.POS.value,
        "diff_percent": DataFields.DIFF_PERCENTAGE.value,
        "itms": DataFields.ITEMS.value,
        "rt": ItemFields.TAX_RATE.value,
        "ad_amt": DataFields.TAXABLE_VALUE.value,
        "iamt": DataFields.IGST.value,
        "camt": DataFields.CGST.value,
        "samt": DataFields.SGST.value,
        "csamt": DataFields.CESS.value,
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
            "itms": self.format_item_wise_json_data,
            "pos": self.map_place_of_supply,
        }

        self.data_value_formatters = {
            "items": self.format_item_wise_internal_data,
            "place_of_supply": self.map_place_of_supply,
        }

    def convert_to_internal_data_format(self, input_data):
        output = {}

        for invoice in input_data:
            invoice_data = self.format_data(invoice)
            items = invoice_data.pop("items")

            for item in items:
                item_data = invoice_data.copy()
                item_data.update(item)
                output[
                    " - ".join(
                        (
                            invoice_data.get("place_of_supply", ""),
                            str(flt(item_data.get("tax_rate", ""))),
                        )
                    )
                ] = item_data

        return {self.SUBCATEGORY: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = list(input_data[self.SUBCATEGORY].values())

        pos_wise_data = {}

        for invoice in input_data:
            formatted_data = self.format_data(invoice, reverse=True)
            formatted_data.update(self.set_item_details(formatted_data))

            pos_data = pos_wise_data.setdefault(
                invoice["place_of_supply"],
                {
                    "pos": formatted_data["pos"],
                    "sply_ty": formatted_data["sply_ty"],
                    "diff_percent": formatted_data["diff_percent"],
                    "itms": [],
                },
            )

            pos_data["itms"].extend(formatted_data["itms"])

        return list(pos_wise_data.values())

    def set_item_details(self, invoice):
        return {
            "itms": [
                {
                    key: invoice.pop(key)
                    for key in ["iamt", "csamt", "camt", "samt", "ad_amt", "rt"]
                }
            ]
        }

    def format_data(self, data, default_data=None, reverse=False):
        data = super().format_data(data, default_data, reverse)
        if not reverse:
            return data

        data["sply_ty"] = "INTER" if data["iamt"] > 0 else "INTRA"
        return data

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
        "num": ItemFields.INDEX.value,
        "from": DataFields.FROM_SR.value,
        "to": DataFields.TO_SR.value,
        "totnum": DataFields.TOTAL_COUNT.value,
        "cancel": DataFields.CANCELLED_COUNT.value,
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

        for document in input_data["doc_det"]:
            document_nature = self.get_document_nature(document.get("doc_num", ""))
            output.update(
                {
                    " - ".join((document_nature, doc.get("from"))): self.format_data(
                        doc, {"document_nature": document_nature}
                    )
                    for doc in document["docs"]
                }
            )

        return {GSTR1_SubCategories.DOC_ISSUE.value: output}

    def convert_to_gov_data_format(self, input_data):
        input_data = input_data[GSTR1_SubCategories.DOC_ISSUE.value]
        self.DOCUMENT_NATURE = {v: k for k, v in self.DOCUMENT_NATURE.items()}

        output = {"doc_det": []}
        doc_nature_wise_data = {}

        for invoice in input_data.values():
            doc_nature_wise_data.setdefault(invoice["document_nature"], []).append(
                invoice
            )

        input_data = doc_nature_wise_data

        output = {
            "doc_det": [
                {
                    "doc_num": self.get_document_nature(doc_nature),
                    "docs": [
                        self.format_data(document, reverse=True)
                        for document in documents
                    ],
                }
                for doc_nature, documents in doc_nature_wise_data.items()
            ]
        }

        return output

    def format_data(self, data, additional_data=None, reverse=False):
        if not reverse:
            return super().format_data(data, additional_data)

        data["cancelled_count"] += data.get("draft_count", 0)

        formatted_data = super().format_data(data, additional_data, reverse)
        formatted_data["net_issue"] = formatted_data.get(
            "totnum", 0
        ) - formatted_data.get("cancel", 0)

        return formatted_data

    def get_document_nature(self, doc_nature, *args):
        return self.DOCUMENT_NATURE.get(doc_nature, doc_nature)


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


class TestB2B(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                "ctin": "01AABCE2207R1Z5",
                "inv": [
                    {
                        "inum": "S008400",
                        "idt": "24-11-2016",
                        "val": 729248.16,
                        "pos": "06",
                        "rchrg": "N",
                        "etin": "01AABCE5507R1C4",
                        "inv_typ": "R",
                        "diff_percent": 0.65,
                        "itms": [
                            {
                                "num": 1,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "camt": 0,
                                    "samt": 0,
                                    "csamt": 500,
                                },
                            },
                            {
                                "num": 2,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "camt": 0,
                                    "samt": 0,
                                    "csamt": 500,
                                },
                            },
                        ],
                    },
                    {
                        "inum": "S008401",
                        "idt": "24-11-2016",
                        "val": 729248.16,
                        "pos": "06",
                        "rchrg": "Y",
                        "etin": "01AABCE5507R1C4",
                        "inv_typ": "R",
                        "diff_percent": 0.65,
                        "itms": [
                            {
                                "num": 1,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "camt": 0,
                                    "samt": 0,
                                    "csamt": 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                "ctin": "01AABCE2207R1Z6",
                "inv": [
                    {
                        "inum": "S008402",
                        "idt": "24-11-2016",
                        "val": 729248.16,
                        "pos": "06",
                        "rchrg": "N",
                        "etin": "01AABCE5507R1C4",
                        "inv_typ": "SEZWP",
                        "diff_percent": 0.65,
                        "itms": [
                            {
                                "num": 1,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "camt": 0,
                                    "samt": 0,
                                    "csamt": 500,
                                },
                            }
                        ],
                    },
                    {
                        "inum": "S008403",
                        "idt": "24-11-2016",
                        "val": 729248.16,
                        "pos": "06",
                        "rchrg": "N",
                        "etin": "01AABCE5507R1C4",
                        "inv_typ": "DE",
                        "diff_percent": 0.65,
                        "itms": [
                            {
                                "num": 1,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "camt": 0,
                                    "samt": 0,
                                    "csamt": 500,
                                },
                            }
                        ],
                    },
                ],
            },
        ]
        cls.mapped_data = {
            "B2B Regular": {
                "S008400": {
                    "customer_gstin": "01AABCE2207R1Z5",
                    "document_number": "S008400",
                    "document_date": "24-11-2016",
                    "document_value": 729248.16,
                    "place_of_supply": "06-Haryana",
                    "reverse_charge": "N",
                    "ecommerce_gstin": "01AABCE5507R1C4",
                    "document_type": "Regular B2B",
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cgst_amount": 0,
                            "sgst_amount": 0,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        },
                        {
                            "idx": 2,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cgst_amount": 0,
                            "sgst_amount": 0,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        },
                    ],
                    "total_taxable_value": 20000,
                    "total_igst_amount": 650,
                    "total_cgst_amount": 0,
                    "total_sgst_amount": 0,
                    "total_cess_amount": 1000,
                }
            },
            "B2B Reverse Charge": {
                "S008401": {
                    "customer_gstin": "01AABCE2207R1Z5",
                    "document_number": "S008401",
                    "document_date": "24-11-2016",
                    "document_value": 729248.16,
                    "place_of_supply": "06-Haryana",
                    "reverse_charge": "Y",
                    "ecommerce_gstin": "01AABCE5507R1C4",
                    "document_type": "Regular B2B",
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cgst_amount": 0,
                            "sgst_amount": 0,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        }
                    ],
                    "total_taxable_value": 10000,
                    "total_igst_amount": 325,
                    "total_cgst_amount": 0,
                    "total_sgst_amount": 0,
                    "total_cess_amount": 500,
                }
            },
            "SEZ with payment": {
                "S008402": {
                    "customer_gstin": "01AABCE2207R1Z6",
                    "document_number": "S008402",
                    "document_date": "24-11-2016",
                    "document_value": 729248.16,
                    "place_of_supply": "06-Haryana",
                    "reverse_charge": "N",
                    "ecommerce_gstin": "01AABCE5507R1C4",
                    "document_type": "SEZ supplies with payment",
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cgst_amount": 0,
                            "sgst_amount": 0,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        }
                    ],
                    "total_taxable_value": 10000,
                    "total_igst_amount": 325,
                    "total_cgst_amount": 0,
                    "total_sgst_amount": 0,
                    "total_cess_amount": 500,
                }
            },
            "Deemed Exports": {
                "S008403": {
                    "customer_gstin": "01AABCE2207R1Z6",
                    "document_number": "S008403",
                    "document_date": "24-11-2016",
                    "document_value": 729248.16,
                    "place_of_supply": "06-Haryana",
                    "reverse_charge": "N",
                    "ecommerce_gstin": "01AABCE5507R1C4",
                    "document_type": "Deemed Exports",
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cgst_amount": 0,
                            "sgst_amount": 0,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        }
                    ],
                    "total_taxable_value": 10000,
                    "total_igst_amount": 325,
                    "total_cgst_amount": 0,
                    "total_sgst_amount": 0,
                    "total_cess_amount": 500,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = B2B().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = B2B().convert_to_gov_data_format(self.mapped_data)
        self.assertListEqual(self.json_data, output)


class TestB2CL(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                "pos": "05",
                "inv": [
                    {
                        "inum": "92661",
                        "idt": "10-01-2016",
                        "val": 784586.33,
                        "etin": "27AHQPA8875L1CU",
                        "diff_percent": 0.65,
                        "itms": [
                            {
                                "num": 1,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "csamt": 500,
                                },
                            },
                            {
                                "num": 2,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "csamt": 500,
                                },
                            },
                        ],
                    },
                    {
                        "inum": "92662",
                        "idt": "10-01-2016",
                        "val": 784586.33,
                        "etin": "27AHQPA8875L1CU",
                        "diff_percent": 0.65,
                        "itms": [
                            {
                                "num": 1,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "csamt": 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                "pos": "24",
                "inv": [
                    {
                        "inum": "92663",
                        "idt": "10-01-2016",
                        "val": 784586.33,
                        "etin": "27AHQPA8875L1CU",
                        "diff_percent": 0.65,
                        "itms": [
                            {
                                "num": 1,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "csamt": 500,
                                },
                            },
                            {
                                "num": 2,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "csamt": 500,
                                },
                            },
                        ],
                    },
                    {
                        "inum": "92664",
                        "idt": "10-01-2016",
                        "val": 784586.33,
                        "etin": "27AHQPA8875L1CU",
                        "diff_percent": 0.65,
                        "itms": [
                            {
                                "num": 1,
                                "itm_det": {
                                    "rt": 5,
                                    "txval": 10000,
                                    "iamt": 325,
                                    "csamt": 500,
                                },
                            }
                        ],
                    },
                ],
            },
        ]
        cls.mapped_data = {
            "B2C (Large)": {
                "92661": {
                    "place_of_supply": "05-Uttarakhand",
                    "document_type": "B2C (Large)",
                    "document_number": "92661",
                    "document_date": "10-01-2016",
                    "document_value": 784586.33,
                    "ecommerce_gstin": "27AHQPA8875L1CU",
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        },
                        {
                            "idx": 2,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        },
                    ],
                    "total_taxable_value": 20000,
                    "total_igst_amount": 650,
                    "total_cess_amount": 1000,
                },
                "92662": {
                    "place_of_supply": "05-Uttarakhand",
                    "document_type": "B2C (Large)",
                    "document_number": "92662",
                    "document_date": "10-01-2016",
                    "document_value": 784586.33,
                    "ecommerce_gstin": "27AHQPA8875L1CU",
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        }
                    ],
                    "total_taxable_value": 10000,
                    "total_igst_amount": 325,
                    "total_cess_amount": 500,
                },
                "92663": {
                    "place_of_supply": "24-Gujarat",
                    "document_type": "B2C (Large)",
                    "document_number": "92663",
                    "document_date": "10-01-2016",
                    "document_value": 784586.33,
                    "ecommerce_gstin": "27AHQPA8875L1CU",
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        },
                        {
                            "idx": 2,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        },
                    ],
                    "total_taxable_value": 20000,
                    "total_igst_amount": 650,
                    "total_cess_amount": 1000,
                },
                "92664": {
                    "place_of_supply": "24-Gujarat",
                    "document_type": "B2C (Large)",
                    "document_number": "92664",
                    "document_date": "10-01-2016",
                    "document_value": 784586.33,
                    "ecommerce_gstin": "27AHQPA8875L1CU",
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": 10000,
                            "igst_amount": 325,
                            "cess_amount": 500,
                            "tax_rate": 5,
                        }
                    ],
                    "total_taxable_value": 10000,
                    "total_igst_amount": 325,
                    "total_cess_amount": 500,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = B2CL().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = B2CL().convert_to_gov_data_format(self.mapped_data)
        self.assertListEqual(self.json_data, output)


class TestExports(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                "exp_typ": "WPAY",
                "inv": [
                    {
                        "inum": "81542",
                        "idt": "12-02-2016",
                        "val": 995048.36,
                        "sbpcode": "ASB991",
                        "sbnum": "7896542",
                        "sbdt": "04-10-2016",
                        "itms": [
                            {"txval": 10000, "rt": 5, "iamt": 833.33, "csamt": 100}
                        ],
                    }
                ],
            },
            {
                "exp_typ": "WOPAY",
                "inv": [
                    {
                        "inum": "81543",
                        "idt": "12-02-2016",
                        "val": 995048.36,
                        "sbpcode": "ASB981",
                        "sbnum": "7896542",
                        "sbdt": "04-10-2016",
                        "itms": [{"txval": 10000, "rt": 0, "iamt": 0, "csamt": 100}],
                    }
                ],
            },
        ]
        cls.mapped_data = {
            "Exports with payment": {
                "81542": {
                    "document_type": "WPAY",
                    "document_number": "81542",
                    "document_date": "12-02-2016",
                    "document_value": 995048.36,
                    "shipping_port_code": "ASB991",
                    "shipping_bill_number": "7896542",
                    "shipping_bill_date": "04-10-2016",
                    "items": [
                        {
                            "taxable_value": 10000,
                            "igst_amount": 833.33,
                            "cess_amount": 100,
                            "tax_rate": 5,
                        }
                    ],
                    "total_taxable_value": 10000,
                    "total_igst_amount": 833.33,
                    "total_cess_amount": 100,
                }
            },
            "Exports without payment": {
                "81543": {
                    "document_type": "WOPAY",
                    "document_number": "81543",
                    "document_date": "12-02-2016",
                    "document_value": 995048.36,
                    "shipping_port_code": "ASB981",
                    "shipping_bill_number": "7896542",
                    "shipping_bill_date": "04-10-2016",
                    "items": [
                        {
                            "taxable_value": 10000,
                            "igst_amount": 0,
                            "cess_amount": 100,
                            "tax_rate": 0,
                        }
                    ],
                    "total_taxable_value": 10000,
                    "total_igst_amount": 0,
                    "total_cess_amount": 100,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = Exports().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = Exports().convert_to_gov_data_format(self.mapped_data)
        self.assertListEqual(self.json_data, output)


class TestB2CS(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                "sply_ty": "INTER",
                "diff_percent": 0.65,
                "rt": 5,
                "typ": "E",
                "etin": "01AABCE5507R1C4",
                "pos": "05",
                "txval": 110,
                "iamt": 10,
                "csamt": 10,
            },
            {
                "sply_ty": "INTER",
                "diff_percent": 0.65,
                "rt": 5,
                "typ": "OE",
                "txval": 100,
                "iamt": 10,
                "csamt": 10,
                "pos": "05",
            },
        ]
        cls.mapped_data = {
            "B2C (Others)": {
                "05-Uttarakhand - 5.0 - 01AABCE5507R1C4": [
                    {
                        "taxable_value": 110,
                        "document_type": "E",
                        "ecommerce_gstin": "01AABCE5507R1C4",
                        "diff_percentage": 0.65,
                        "place_of_supply": "05-Uttarakhand",
                        "tax_rate": 5,
                        "igst_amount": 10,
                        "cess_amount": 10,
                    }
                ],
                "05-Uttarakhand - 5.0 - ": [
                    {
                        "taxable_value": 100,
                        "document_type": "OE",
                        "diff_percentage": 0.65,
                        "place_of_supply": "05-Uttarakhand",
                        "tax_rate": 5,
                        "igst_amount": 10,
                        "cess_amount": 10,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = B2CS().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = B2CS().convert_to_gov_data_format(self.mapped_data)
        self.assertListEqual(self.json_data, output)


class TestNilRated(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            "inv": [
                {
                    "sply_ty": "INTRB2B",
                    "expt_amt": 123.45,
                    "nil_amt": 1470.85,
                    "ngsup_amt": 1258.5,
                },
                {
                    "sply_ty": "INTRB2C",
                    "expt_amt": 123.45,
                    "nil_amt": 1470.85,
                    "ngsup_amt": 1258.5,
                },
            ]
        }

        cls.mapped_data = {
            "Nil-Rated, Exempted, Non-GST": {
                "Inter-State supplies to registered persons": [
                    {
                        "document_type": "Inter-State supplies to registered persons",
                        "exempted_amount": 123.45,
                        "nil_rated_amount": 1470.85,
                        "non_gst_amount": 1258.5,
                        "total_taxable_value": 2852.8,
                    }
                ],
                "Inter-State supplies to unregistered persons": [
                    {
                        "document_type": "Inter-State supplies to unregistered persons",
                        "exempted_amount": 123.45,
                        "nil_rated_amount": 1470.85,
                        "non_gst_amount": 1258.5,
                        "total_taxable_value": 2852.8,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = NilRated().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = NilRated().convert_to_gov_data_format(self.mapped_data)
        self.assertDictEqual(self.json_data, output)


class TestCDNR(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                "ctin": "01AAAAP1208Q1ZS",
                "nt": [
                    {
                        "ntty": "C",
                        "nt_num": "533515",
                        "nt_dt": "23-09-2016",
                        "pos": "03",
                        "rchrg": "Y",
                        "inv_typ": "DE",
                        "val": 123123,
                        "diff_percent": 0.65,
                        "itms": [
                            {
                                "num": 1,
                                "itm_det": {
                                    "rt": 10,
                                    "txval": 5225.28,
                                    "samt": 0,
                                    "camt": 0,
                                    "iamt": 339.64,
                                    "csamt": 789.52,
                                },
                            },
                            {
                                "num": 2,
                                "itm_det": {
                                    "rt": 10,
                                    "txval": 5225.28,
                                    "samt": 0,
                                    "camt": 0,
                                    "iamt": 339.64,
                                    "csamt": 789.52,
                                },
                            },
                        ],
                    },
                ],
            }
        ]
        cls.mappped_data = {
            "Credit/Debit Notes (Registered)": {
                "533515": {
                    "customer_gstin": "01AAAAP1208Q1ZS",
                    "transaction_type": "Credit Note",
                    "document_number": "533515",
                    "document_date": "23-09-2016",
                    "place_of_supply": "03-Punjab",
                    "reverse_charge": "Y",
                    "document_type": "Deemed Exports",
                    "document_value": -123123,
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": -5225.28,
                            "igst_amount": -339.64,
                            "cgst_amount": 0,
                            "sgst_amount": 0,
                            "cess_amount": -789.52,
                            "tax_rate": 10,
                        },
                        {
                            "idx": 2,
                            "taxable_value": -5225.28,
                            "igst_amount": -339.64,
                            "cgst_amount": 0,
                            "sgst_amount": 0,
                            "cess_amount": -789.52,
                            "tax_rate": 10,
                        },
                    ],
                    "total_taxable_value": -10450.56,
                    "total_igst_amount": -679.28,
                    "total_cgst_amount": 0,
                    "total_sgst_amount": 0,
                    "total_cess_amount": -1579.04,
                }
            }
        }

    def test_convert_to_internal_data_format(self):
        output = CDNR().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mappped_data, output)

    def test_convert_to_gov_data_format(self):
        output = CDNR().convert_to_gov_data_format(self.mappped_data)
        self.assertListEqual(self.json_data, output)


class TestCDNUR(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                "typ": "B2CL",
                "ntty": "C",
                "nt_num": "533515",
                "nt_dt": "23-09-2016",
                "pos": "03",
                "val": 64646,
                "diff_percent": 0.65,
                "itms": [
                    {
                        "num": 1,
                        "itm_det": {
                            "rt": 10,
                            "txval": 5225.28,
                            "iamt": 339.64,
                            "csamt": 789.52,
                        },
                    }
                ],
            }
        ]

        cls.mapped_data = {
            "Credit/Debit Notes (Unregistered)": {
                "533515": {
                    "transaction_type": "Credit Note",
                    "document_type": "B2CL",
                    "document_number": "533515",
                    "document_date": "23-09-2016",
                    "document_value": -64646,
                    "place_of_supply": "03-Punjab",
                    "diff_percentage": 0.65,
                    "items": [
                        {
                            "idx": 1,
                            "taxable_value": -5225.28,
                            "igst_amount": -339.64,
                            "cess_amount": -789.52,
                            "tax_rate": 10,
                        }
                    ],
                    "total_taxable_value": -5225.28,
                    "total_igst_amount": -339.64,
                    "total_cess_amount": -789.52,
                }
            }
        }

    def test_convert_to_internal_data_format(self):
        output = CDNUR().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = CDNUR().convert_to_gov_data_format(self.mapped_data)
        self.assertListEqual(self.json_data, output)


class TestHSNSUM(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = {
            "data": [
                {
                    "num": 1,
                    "hsn_sc": "1010",
                    "desc": "Goods Description",
                    "uqc": "KGS",
                    "qty": 2.05,
                    "txval": 10.23,
                    "iamt": 14.52,
                    "csamt": 500,
                    "rt": 0.1,
                }
            ]
        }

        cls.mapped_data = {
            "HSN Summary": {
                "1010 - KGS-KILOGRAMS - 0.1": [
                    {
                        "idx": 1,
                        "hsn_code": "1010",
                        "description": "Goods Description",
                        "uom": "KGS-KILOGRAMS",
                        "quantity": 2.05,
                        "total_taxable_value": 10.23,
                        "total_igst_amount": 14.52,
                        "total_cess_amount": 500,
                        "tax_rate": 0.1,
                    }
                ]
            }
        }

    def test_convert_to_internal_data_format(self):
        output = HSNSUM().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = HSNSUM().convert_to_gov_data_format(self.mapped_data)
        self.assertDictEqual(self.json_data, output)


class TestAT(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                "pos": "05",
                "sply_ty": "INTER",
                "diff_percent": 0.65,
                "itms": [
                    {
                        "rt": 5,
                        "ad_amt": 100,
                        "iamt": 9400,
                        "camt": 0,
                        "samt": 0,
                        "csamt": 500,
                    },
                    {
                        "rt": 6,
                        "ad_amt": 100,
                        "iamt": 9400,
                        "camt": 0,
                        "samt": 0,
                        "csamt": 500,
                    },
                ],
            },
            {
                "pos": "24",
                "sply_ty": "INTER",
                "diff_percent": 0.65,
                "itms": [
                    {
                        "rt": 5,
                        "ad_amt": 100,
                        "iamt": 9400,
                        "camt": 0,
                        "samt": 0,
                        "csamt": 500,
                    },
                    {
                        "rt": 6,
                        "ad_amt": 100,
                        "iamt": 9400,
                        "camt": 0,
                        "samt": 0,
                        "csamt": 500,
                    },
                ],
            },
        ]

        cls.mapped_data = {
            "Advances Received": {
                "05-Uttarakhand - 5.0": {
                    "place_of_supply": "05-Uttarakhand",
                    "diff_percentage": 0.65,
                    "total_igst_amount": 9400,
                    "total_cess_amount": 500,
                    "total_cgst_amount": 0,
                    "total_sgst_amount": 0,
                    "total_taxable_value": 100,
                    "tax_rate": 5,
                },
                "05-Uttarakhand - 6.0": {
                    "place_of_supply": "05-Uttarakhand",
                    "diff_percentage": 0.65,
                    "total_igst_amount": 9400,
                    "total_cess_amount": 500,
                    "total_cgst_amount": 0,
                    "total_sgst_amount": 0,
                    "total_taxable_value": 100,
                    "tax_rate": 6,
                },
                "24-Gujarat - 5.0": {
                    "place_of_supply": "24-Gujarat",
                    "diff_percentage": 0.65,
                    "total_igst_amount": 9400,
                    "total_cess_amount": 500,
                    "total_cgst_amount": 0,
                    "total_sgst_amount": 0,
                    "total_taxable_value": 100,
                    "tax_rate": 5,
                },
                "24-Gujarat - 6.0": {
                    "place_of_supply": "24-Gujarat",
                    "diff_percentage": 0.65,
                    "total_igst_amount": 9400,
                    "total_cess_amount": 500,
                    "total_cgst_amount": 0,
                    "total_sgst_amount": 0,
                    "total_taxable_value": 100,
                    "tax_rate": 6,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = AT().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = AT().convert_to_gov_data_format(self.mapped_data)
        self.assertListEqual(self.json_data, output)


class TestDOC_ISSUE(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            "doc_det": [
                {
                    "doc_num": 1,
                    "docs": [
                        {
                            "num": 1,
                            "from": "1",
                            "to": "10",
                            "totnum": 10,
                            "cancel": 0,
                            "net_issue": 10,
                        },
                        {
                            "num": 2,
                            "from": "11",
                            "to": "20",
                            "totnum": 10,
                            "cancel": 0,
                            "net_issue": 10,
                        },
                    ],
                },
                {
                    "doc_num": 2,
                    "docs": [
                        {
                            "num": 1,
                            "from": "1",
                            "to": "10",
                            "totnum": 10,
                            "cancel": 0,
                            "net_issue": 10,
                        },
                        {
                            "num": 2,
                            "from": "11",
                            "to": "20",
                            "totnum": 10,
                            "cancel": 0,
                            "net_issue": 10,
                        },
                    ],
                },
            ]
        }
        cls.mapped_data = {
            "Document Issued": {
                "Invoices for outward supply - 1": {
                    "document_nature": "Invoices for outward supply",
                    "idx": 1,
                    "from_sr_no": "1",
                    "to_sr_no": "10",
                    "total_count": 10,
                    "cancelled_count": 0,
                },
                "Invoices for outward supply - 11": {
                    "document_nature": "Invoices for outward supply",
                    "idx": 2,
                    "from_sr_no": "11",
                    "to_sr_no": "20",
                    "total_count": 10,
                    "cancelled_count": 0,
                },
                "Invoices for inward supply from unregistered person - 1": {
                    "document_nature": "Invoices for inward supply from unregistered person",
                    "idx": 1,
                    "from_sr_no": "1",
                    "to_sr_no": "10",
                    "total_count": 10,
                    "cancelled_count": 0,
                },
                "Invoices for inward supply from unregistered person - 11": {
                    "document_nature": "Invoices for inward supply from unregistered person",
                    "idx": 2,
                    "from_sr_no": "11",
                    "to_sr_no": "20",
                    "total_count": 10,
                    "cancelled_count": 0,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = DOC_ISSUE().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = DOC_ISSUE().convert_to_gov_data_format(self.mapped_data)
        self.assertDictEqual(self.json_data, output)
