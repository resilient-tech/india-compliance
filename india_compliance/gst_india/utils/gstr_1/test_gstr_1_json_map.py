import copy

from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    GenerateGSTR1,
)
from india_compliance.gst_india.utils import get_party_for_gstin as _get_party_for_gstin
from india_compliance.gst_india.utils.gstr_1 import GovDataField as gov_f
from india_compliance.gst_india.utils.gstr_1 import (
    GSTR1_B2B_InvoiceType,
)
from india_compliance.gst_india.utils.gstr_1 import GSTR1_DataField as inv_f
from india_compliance.gst_india.utils.gstr_1 import GSTR1_ItemField as item_f
from india_compliance.gst_india.utils.gstr_1 import (
    GSTR1_SubCategory,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    AT,
    B2B,
    B2CL,
    B2CS,
    CDNR,
    CDNUR,
    DOC_ISSUE,
    HSNSUM,
    SUPECOM,
    TXPD,
    Exports,
    NilRated,
    get_category_wise_data,
)


def get_party_for_gstin(gstin):
    return _get_party_for_gstin(gstin, "Customer") or "Unknown"


def normalize_data(data):
    return GenerateGSTR1().normalize_data(data)


def process_mapped_data(data):
    return list(get_category_wise_data(normalize_data(copy.deepcopy(data))).values())[0]


class TestB2B(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                gov_f.CUST_GSTIN: "24AANFA2641L1ZF",
                gov_f.INVOICES: [
                    {
                        gov_f.DOC_NUMBER: "S008400",
                        gov_f.DOC_DATE: "24-11-2016",
                        gov_f.DOC_VALUE: 729248.16,
                        gov_f.POS: "06",
                        gov_f.REVERSE_CHARGE: "N",
                        gov_f.INVOICE_TYPE: "R",
                        gov_f.DIFF_PERCENTAGE: 0.65,
                        gov_f.ITEMS: [
                            {
                                gov_f.INDEX: 1,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CGST: 0,
                                    gov_f.SGST: 0,
                                    gov_f.CESS: 500,
                                },
                            },
                            {
                                gov_f.INDEX: 2,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CGST: 0,
                                    gov_f.SGST: 0,
                                    gov_f.CESS: 500,
                                },
                            },
                        ],
                    },
                    {
                        gov_f.DOC_NUMBER: "S008401",
                        gov_f.DOC_DATE: "24-11-2016",
                        gov_f.DOC_VALUE: 729248.16,
                        gov_f.POS: "06",
                        gov_f.REVERSE_CHARGE: "Y",
                        gov_f.INVOICE_TYPE: "R",
                        gov_f.DIFF_PERCENTAGE: 0.65,
                        gov_f.ITEMS: [
                            {
                                gov_f.INDEX: 1,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CGST: 0,
                                    gov_f.SGST: 0,
                                    gov_f.CESS: 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                gov_f.CUST_GSTIN: "29AABCR1718E1ZL",
                gov_f.INVOICES: [
                    {
                        gov_f.DOC_NUMBER: "S008402",
                        gov_f.DOC_DATE: "24-11-2016",
                        gov_f.DOC_VALUE: 729248.16,
                        gov_f.POS: "06",
                        gov_f.REVERSE_CHARGE: "N",
                        gov_f.INVOICE_TYPE: "SEWP",
                        gov_f.DIFF_PERCENTAGE: 0.65,
                        gov_f.ITEMS: [
                            {
                                gov_f.INDEX: 1,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CGST: 0,
                                    gov_f.SGST: 0,
                                    gov_f.CESS: 500,
                                },
                            }
                        ],
                    },
                    {
                        gov_f.DOC_NUMBER: "S008403",
                        gov_f.DOC_DATE: "24-11-2016",
                        gov_f.DOC_VALUE: 729248.16,
                        gov_f.POS: "06",
                        gov_f.REVERSE_CHARGE: "N",
                        gov_f.INVOICE_TYPE: "DE",
                        gov_f.DIFF_PERCENTAGE: 0.65,
                        gov_f.ITEMS: [
                            {
                                gov_f.INDEX: 1,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CGST: 0,
                                    gov_f.SGST: 0,
                                    gov_f.CESS: 500,
                                },
                            }
                        ],
                    },
                ],
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategory.B2B_REGULAR.value: {
                "S008400": {
                    inv_f.CUST_GSTIN: "24AANFA2641L1ZF",
                    inv_f.CUST_NAME: get_party_for_gstin("24AANFA2641L1ZF"),
                    inv_f.DOC_NUMBER: "S008400",
                    inv_f.DOC_DATE: "2016-11-24",
                    inv_f.DOC_VALUE: 729248.16,
                    inv_f.POS: "06-Haryana",
                    inv_f.REVERSE_CHARGE: "N",
                    inv_f.DOC_TYPE: GSTR1_B2B_InvoiceType.R.value,
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CGST: 0,
                            item_f.SGST: 0,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        },
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CGST: 0,
                            item_f.SGST: 0,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        },
                    ],
                    inv_f.TAXABLE_VALUE: 20000,
                    inv_f.IGST: 650,
                    inv_f.CGST: 0,
                    inv_f.SGST: 0,
                    inv_f.CESS: 1000,
                }
            },
            GSTR1_SubCategory.B2B_REVERSE_CHARGE.value: {
                "S008401": {
                    inv_f.CUST_GSTIN: "24AANFA2641L1ZF",
                    inv_f.CUST_NAME: get_party_for_gstin("24AANFA2641L1ZF"),
                    inv_f.DOC_NUMBER: "S008401",
                    inv_f.DOC_DATE: "2016-11-24",
                    inv_f.DOC_VALUE: 729248.16,
                    inv_f.POS: "06-Haryana",
                    inv_f.REVERSE_CHARGE: "Y",
                    inv_f.DOC_TYPE: GSTR1_B2B_InvoiceType.R.value,
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CGST: 0,
                            item_f.SGST: 0,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        }
                    ],
                    inv_f.TAXABLE_VALUE: 10000,
                    inv_f.IGST: 325,
                    inv_f.CGST: 0,
                    inv_f.SGST: 0,
                    inv_f.CESS: 500,
                }
            },
            GSTR1_SubCategory.SEZWP.value: {
                "S008402": {
                    inv_f.CUST_GSTIN: "29AABCR1718E1ZL",
                    inv_f.CUST_NAME: get_party_for_gstin("29AABCR1718E1ZL"),
                    inv_f.DOC_NUMBER: "S008402",
                    inv_f.DOC_DATE: "2016-11-24",
                    inv_f.DOC_VALUE: 729248.16,
                    inv_f.POS: "06-Haryana",
                    inv_f.REVERSE_CHARGE: "N",
                    inv_f.DOC_TYPE: GSTR1_B2B_InvoiceType.SEWP.value,
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CGST: 0,
                            item_f.SGST: 0,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        }
                    ],
                    inv_f.TAXABLE_VALUE: 10000,
                    inv_f.IGST: 325,
                    inv_f.CGST: 0,
                    inv_f.SGST: 0,
                    inv_f.CESS: 500,
                }
            },
            GSTR1_SubCategory.DE.value: {
                "S008403": {
                    inv_f.CUST_GSTIN: "29AABCR1718E1ZL",
                    inv_f.CUST_NAME: get_party_for_gstin("29AABCR1718E1ZL"),
                    inv_f.DOC_NUMBER: "S008403",
                    inv_f.DOC_DATE: "2016-11-24",
                    inv_f.DOC_VALUE: 729248.16,
                    inv_f.POS: "06-Haryana",
                    inv_f.REVERSE_CHARGE: "N",
                    inv_f.DOC_TYPE: GSTR1_B2B_InvoiceType.DE.value,
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CGST: 0,
                            item_f.SGST: 0,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        }
                    ],
                    inv_f.TAXABLE_VALUE: 10000,
                    inv_f.IGST: 325,
                    inv_f.CGST: 0,
                    inv_f.SGST: 0,
                    inv_f.CESS: 500,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = B2B().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = B2B().convert_to_gov_data_format(process_mapped_data(self.mapped_data))
        self.assertListEqual(self.json_data, output)


class TestB2CL(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                gov_f.POS: "05",
                gov_f.INVOICES: [
                    {
                        gov_f.DOC_NUMBER: "92661",
                        gov_f.DOC_DATE: "10-01-2016",
                        gov_f.DOC_VALUE: 784586.33,
                        gov_f.DIFF_PERCENTAGE: 0.65,
                        gov_f.ITEMS: [
                            {
                                gov_f.INDEX: 1,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CESS: 500,
                                },
                            },
                            {
                                gov_f.INDEX: 2,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CESS: 500,
                                },
                            },
                        ],
                    },
                    {
                        gov_f.DOC_NUMBER: "92662",
                        gov_f.DOC_DATE: "10-01-2016",
                        gov_f.DOC_VALUE: 784586.33,
                        gov_f.DIFF_PERCENTAGE: 0.65,
                        gov_f.ITEMS: [
                            {
                                gov_f.INDEX: 1,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CESS: 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                gov_f.POS: "24",
                gov_f.INVOICES: [
                    {
                        gov_f.DOC_NUMBER: "92663",
                        gov_f.DOC_DATE: "10-01-2016",
                        gov_f.DOC_VALUE: 784586.33,
                        gov_f.DIFF_PERCENTAGE: 0.65,
                        gov_f.ITEMS: [
                            {
                                gov_f.INDEX: 1,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CESS: 500,
                                },
                            },
                            {
                                gov_f.INDEX: 2,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CESS: 500,
                                },
                            },
                        ],
                    },
                    {
                        gov_f.DOC_NUMBER: "92664",
                        gov_f.DOC_DATE: "10-01-2016",
                        gov_f.DOC_VALUE: 784586.33,
                        gov_f.DIFF_PERCENTAGE: 0.65,
                        gov_f.ITEMS: [
                            {
                                gov_f.INDEX: 1,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 5,
                                    gov_f.TAXABLE_VALUE: 10000,
                                    gov_f.IGST: 325,
                                    gov_f.CESS: 500,
                                },
                            }
                        ],
                    },
                ],
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategory.B2CL.value: {
                "92661": {
                    inv_f.POS: "05-Uttarakhand",
                    inv_f.DOC_TYPE: "B2C (Large)",
                    inv_f.DOC_NUMBER: "92661",
                    inv_f.DOC_DATE: "2016-01-10",
                    inv_f.DOC_VALUE: 784586.33,
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        },
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        },
                    ],
                    inv_f.TAXABLE_VALUE: 20000,
                    inv_f.IGST: 650,
                    inv_f.CESS: 1000,
                },
                "92662": {
                    inv_f.POS: "05-Uttarakhand",
                    inv_f.DOC_TYPE: "B2C (Large)",
                    inv_f.DOC_NUMBER: "92662",
                    inv_f.DOC_DATE: "2016-01-10",
                    inv_f.DOC_VALUE: 784586.33,
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        }
                    ],
                    inv_f.TAXABLE_VALUE: 10000,
                    inv_f.IGST: 325,
                    inv_f.CESS: 500,
                },
                "92663": {
                    inv_f.POS: "24-Gujarat",
                    inv_f.DOC_TYPE: "B2C (Large)",
                    inv_f.DOC_NUMBER: "92663",
                    inv_f.DOC_DATE: "2016-01-10",
                    inv_f.DOC_VALUE: 784586.33,
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        },
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        },
                    ],
                    inv_f.TAXABLE_VALUE: 20000,
                    inv_f.IGST: 650,
                    inv_f.CESS: 1000,
                },
                "92664": {
                    inv_f.POS: "24-Gujarat",
                    inv_f.DOC_TYPE: "B2C (Large)",
                    inv_f.DOC_NUMBER: "92664",
                    inv_f.DOC_DATE: "2016-01-10",
                    inv_f.DOC_VALUE: 784586.33,
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 325,
                            item_f.CESS: 500,
                            inv_f.TAX_RATE: 5,
                        }
                    ],
                    inv_f.TAXABLE_VALUE: 10000,
                    inv_f.IGST: 325,
                    inv_f.CESS: 500,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = B2CL().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = B2CL().convert_to_gov_data_format(
            process_mapped_data(self.mapped_data)
        )
        self.assertListEqual(self.json_data, output)


class TestExports(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                gov_f.EXPORT_TYPE: "WPAY",
                gov_f.INVOICES: [
                    {
                        gov_f.DOC_NUMBER: "81542",
                        gov_f.DOC_DATE: "12-02-2016",
                        gov_f.DOC_VALUE: 995048.36,
                        gov_f.SHIPPING_PORT_CODE: "ASB991",
                        gov_f.SHIPPING_BILL_NUMBER: "7896542",
                        gov_f.SHIPPING_BILL_DATE: "04-10-2016",
                        gov_f.ITEMS: [
                            {
                                gov_f.TAXABLE_VALUE: 10000,
                                gov_f.TAX_RATE: 5,
                                gov_f.IGST: 833.33,
                                gov_f.CESS: 100,
                            }
                        ],
                    }
                ],
            },
            {
                gov_f.EXPORT_TYPE: "WOPAY",
                gov_f.INVOICES: [
                    {
                        gov_f.DOC_NUMBER: "81543",
                        gov_f.DOC_DATE: "12-02-2016",
                        gov_f.DOC_VALUE: 995048.36,
                        gov_f.SHIPPING_PORT_CODE: "ASB981",
                        gov_f.SHIPPING_BILL_NUMBER: "7896542",
                        gov_f.SHIPPING_BILL_DATE: "04-10-2016",
                        gov_f.ITEMS: [
                            {
                                gov_f.TAXABLE_VALUE: 10000,
                                gov_f.TAX_RATE: 0,
                                gov_f.IGST: 0,
                                gov_f.CESS: 100,
                            }
                        ],
                    }
                ],
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategory.EXPWP.value: {
                "81542": {
                    inv_f.DOC_TYPE: "WPAY",
                    inv_f.DOC_NUMBER: "81542",
                    inv_f.DOC_DATE: "2016-02-12",
                    inv_f.DOC_VALUE: 995048.36,
                    inv_f.SHIPPING_PORT_CODE: "ASB991",
                    inv_f.SHIPPING_BILL_NUMBER: "7896542",
                    inv_f.SHIPPING_BILL_DATE: "2016-10-04",
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 833.33,
                            item_f.CESS: 100,
                            inv_f.TAX_RATE: 5,
                        }
                    ],
                    inv_f.TAXABLE_VALUE: 10000,
                    inv_f.IGST: 833.33,
                    inv_f.CESS: 100,
                }
            },
            GSTR1_SubCategory.EXPWOP.value: {
                "81543": {
                    inv_f.DOC_TYPE: "WOPAY",
                    inv_f.DOC_NUMBER: "81543",
                    inv_f.DOC_DATE: "2016-02-12",
                    inv_f.DOC_VALUE: 995048.36,
                    inv_f.SHIPPING_PORT_CODE: "ASB981",
                    inv_f.SHIPPING_BILL_NUMBER: "7896542",
                    inv_f.SHIPPING_BILL_DATE: "2016-10-04",
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: 10000,
                            item_f.IGST: 0,
                            item_f.CESS: 100,
                            inv_f.TAX_RATE: 0,
                        }
                    ],
                    inv_f.TAXABLE_VALUE: 10000,
                    inv_f.IGST: 0,
                    inv_f.CESS: 100,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = Exports().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = Exports().convert_to_gov_data_format(
            process_mapped_data(self.mapped_data)
        )
        self.assertListEqual(self.json_data, output)


class TestB2CS(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                gov_f.SUPPLY_TYPE: "INTER",
                gov_f.DIFF_PERCENTAGE: 0.65,
                gov_f.TAX_RATE: 5,
                gov_f.TYPE: "OE",
                gov_f.POS: "05",
                gov_f.TAXABLE_VALUE: 110,
                gov_f.IGST: 10,
                gov_f.CGST: 0,
                gov_f.SGST: 0,
                gov_f.CESS: 10,
            },
            {
                gov_f.SUPPLY_TYPE: "INTER",
                gov_f.DIFF_PERCENTAGE: 0.65,
                gov_f.TAX_RATE: 5,
                gov_f.TYPE: "OE",
                gov_f.TAXABLE_VALUE: 100,
                gov_f.IGST: 10,
                gov_f.CGST: 0,
                gov_f.SGST: 0,
                gov_f.CESS: 10,
                gov_f.POS: "06",
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategory.B2CS.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        inv_f.TAXABLE_VALUE: 110,
                        inv_f.DOC_TYPE: "OE",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.POS: "05-Uttarakhand",
                        inv_f.TAX_RATE: 5,
                        inv_f.IGST: 10,
                        inv_f.CESS: 10,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                    },
                ],
                "06-Haryana - 5.0": [
                    {
                        inv_f.TAXABLE_VALUE: 100,
                        inv_f.DOC_TYPE: "OE",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.POS: "06-Haryana",
                        inv_f.TAX_RATE: 5,
                        inv_f.IGST: 10,
                        inv_f.CESS: 10,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = B2CS().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = B2CS().convert_to_gov_data_format(
            process_mapped_data(self.mapped_data)
        )
        self.assertListEqual(self.json_data, output)


class TestNilRated(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            gov_f.INVOICES: [
                {
                    gov_f.SUPPLY_TYPE: "INTRB2B",
                    gov_f.EXEMPTED_AMOUNT: 123.45,
                    gov_f.NIL_RATED_AMOUNT: 1470.85,
                    gov_f.NON_GST_AMOUNT: 1258.5,
                },
                {
                    gov_f.SUPPLY_TYPE: "INTRB2C",
                    gov_f.EXEMPTED_AMOUNT: 123.45,
                    gov_f.NIL_RATED_AMOUNT: 1470.85,
                    gov_f.NON_GST_AMOUNT: 1258.5,
                },
            ]
        }

        cls.mapped_data = {
            GSTR1_SubCategory.NIL_EXEMPT.value: {
                "Inter-State supplies to registered persons": [
                    {
                        inv_f.DOC_TYPE: "Inter-State supplies to registered persons",
                        inv_f.EXEMPTED_AMOUNT: 123.45,
                        inv_f.NIL_RATED_AMOUNT: 1470.85,
                        inv_f.NON_GST_AMOUNT: 1258.5,
                        inv_f.TAXABLE_VALUE: 2852.8,
                    }
                ],
                "Inter-State supplies to unregistered persons": [
                    {
                        inv_f.DOC_TYPE: "Inter-State supplies to unregistered persons",
                        inv_f.EXEMPTED_AMOUNT: 123.45,
                        inv_f.NIL_RATED_AMOUNT: 1470.85,
                        inv_f.NON_GST_AMOUNT: 1258.5,
                        inv_f.TAXABLE_VALUE: 2852.8,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = NilRated().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = NilRated().convert_to_gov_data_format(
            process_mapped_data(self.mapped_data)
        )
        self.assertDictEqual(self.json_data, output)


class TestCDNR(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                gov_f.CUST_GSTIN: "24AANFA2641L1ZF",
                gov_f.NOTE_DETAILS: [
                    {
                        gov_f.NOTE_TYPE: "C",
                        gov_f.NOTE_NUMBER: "533515",
                        gov_f.NOTE_DATE: "23-09-2016",
                        gov_f.POS: "03",
                        gov_f.REVERSE_CHARGE: "Y",
                        gov_f.INVOICE_TYPE: "DE",
                        gov_f.DOC_VALUE: 123123,
                        gov_f.DIFF_PERCENTAGE: 0.65,
                        gov_f.ITEMS: [
                            {
                                gov_f.INDEX: 1,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 10,
                                    gov_f.TAXABLE_VALUE: 5225.28,
                                    gov_f.SGST: 0,
                                    gov_f.CGST: 0,
                                    gov_f.IGST: 339.64,
                                    gov_f.CESS: 789.52,
                                },
                            },
                            {
                                gov_f.INDEX: 2,
                                gov_f.ITEM_DETAILS: {
                                    gov_f.TAX_RATE: 10,
                                    gov_f.TAXABLE_VALUE: 5225.28,
                                    gov_f.SGST: 0,
                                    gov_f.CGST: 0,
                                    gov_f.IGST: 339.64,
                                    gov_f.CESS: 789.52,
                                },
                            },
                        ],
                    },
                ],
            }
        ]
        cls.mapped_data = {
            GSTR1_SubCategory.CDNR.value: {
                "533515": {
                    inv_f.CUST_GSTIN: "24AANFA2641L1ZF",
                    inv_f.CUST_NAME: get_party_for_gstin("24AANFA2641L1ZF"),
                    inv_f.TRANSACTION_TYPE: "Credit Note",
                    inv_f.DOC_NUMBER: "533515",
                    inv_f.DOC_DATE: "2016-09-23",
                    inv_f.POS: "03-Punjab",
                    inv_f.REVERSE_CHARGE: "Y",
                    inv_f.DOC_TYPE: "Deemed Exports",
                    inv_f.DOC_VALUE: -123123,
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: -5225.28,
                            item_f.IGST: -339.64,
                            item_f.CGST: 0,
                            item_f.SGST: 0,
                            item_f.CESS: -789.52,
                            inv_f.TAX_RATE: 10,
                        },
                        {
                            item_f.TAXABLE_VALUE: -5225.28,
                            item_f.IGST: -339.64,
                            item_f.CGST: 0,
                            item_f.SGST: 0,
                            item_f.CESS: -789.52,
                            inv_f.TAX_RATE: 10,
                        },
                    ],
                    inv_f.TAXABLE_VALUE: -10450.56,
                    inv_f.IGST: -679.28,
                    inv_f.CGST: 0,
                    inv_f.SGST: 0,
                    inv_f.CESS: -1579.04,
                }
            }
        }

    def test_convert_to_internal_data_format(self):
        output = CDNR().convert_to_internal_data_format(copy.deepcopy(self.json_data))
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = CDNR().convert_to_gov_data_format(
            process_mapped_data(copy.deepcopy(self.mapped_data))
        )
        self.assertListEqual(self.json_data, output)


class TestCDNUR(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                gov_f.TYPE: "B2CL",
                gov_f.NOTE_TYPE: "C",
                gov_f.NOTE_NUMBER: "533515",
                gov_f.NOTE_DATE: "23-09-2016",
                gov_f.POS: "03",
                gov_f.DOC_VALUE: 64646,
                gov_f.DIFF_PERCENTAGE: 0.65,
                gov_f.ITEMS: [
                    {
                        gov_f.INDEX: 1,
                        gov_f.ITEM_DETAILS: {
                            gov_f.TAX_RATE: 10,
                            gov_f.TAXABLE_VALUE: 5225.28,
                            gov_f.IGST: 339.64,
                            gov_f.CESS: 789.52,
                        },
                    }
                ],
            }
        ]

        cls.mapped_data = {
            GSTR1_SubCategory.CDNUR.value: {
                "533515": {
                    inv_f.TRANSACTION_TYPE: "Credit Note",
                    inv_f.DOC_TYPE: "B2CL",
                    inv_f.DOC_NUMBER: "533515",
                    inv_f.DOC_DATE: "2016-09-23",
                    inv_f.DOC_VALUE: -64646,
                    inv_f.POS: "03-Punjab",
                    inv_f.DIFF_PERCENTAGE: 0.65,
                    inv_f.ITEMS: [
                        {
                            item_f.TAXABLE_VALUE: -5225.28,
                            item_f.IGST: -339.64,
                            item_f.CESS: -789.52,
                            inv_f.TAX_RATE: 10,
                        }
                    ],
                    inv_f.TAXABLE_VALUE: -5225.28,
                    inv_f.IGST: -339.64,
                    inv_f.CESS: -789.52,
                }
            }
        }

    def test_convert_to_internal_data_format(self):
        output = CDNUR().convert_to_internal_data_format(copy.deepcopy(self.json_data))
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = CDNUR().convert_to_gov_data_format(
            process_mapped_data(copy.deepcopy(self.mapped_data))
        )
        self.assertListEqual(self.json_data, output)


class TestHSNSUM(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = {
            gov_f.HSN_DATA: [
                {
                    gov_f.INDEX: 1,
                    gov_f.HSN_CODE: "1010",
                    gov_f.DESCRIPTION: "Goods Description",
                    gov_f.UOM: "KGS",
                    gov_f.QUANTITY: 2.05,
                    gov_f.TAXABLE_VALUE: 10.23,
                    gov_f.IGST: 14.52,
                    gov_f.CESS: 500,
                    gov_f.TAX_RATE: 0.1,
                },
                {
                    gov_f.INDEX: 2,
                    gov_f.HSN_CODE: "1011",
                    gov_f.DESCRIPTION: "Goods Description",
                    gov_f.UOM: "NOS",
                    gov_f.QUANTITY: 2.05,
                    gov_f.TAXABLE_VALUE: 10.23,
                    gov_f.IGST: 14.52,
                    gov_f.CESS: 500,
                    gov_f.TAX_RATE: 5,
                },
            ]
        }

        cls.mapped_data = {
            GSTR1_SubCategory.HSN.value: {
                "1010 - KGS-KILOGRAMS - 0.1": {
                    inv_f.DOC_TYPE: GSTR1_SubCategory.HSN.value,
                    inv_f.HSN_CODE: "1010",
                    inv_f.DESCRIPTION: "Goods Description",
                    inv_f.UOM: "KGS-KILOGRAMS",
                    inv_f.QUANTITY: 2.05,
                    inv_f.TAXABLE_VALUE: 10.23,
                    inv_f.IGST: 14.52,
                    inv_f.CESS: 500,
                    inv_f.TAX_RATE: 0.1,
                    inv_f.DOC_VALUE: 524.75,
                },
                "1011 - NOS-NUMBERS - 5.0": {
                    inv_f.DOC_TYPE: GSTR1_SubCategory.HSN.value,
                    inv_f.HSN_CODE: "1011",
                    inv_f.DESCRIPTION: "Goods Description",
                    inv_f.UOM: "NOS-NUMBERS",
                    inv_f.QUANTITY: 2.05,
                    inv_f.TAXABLE_VALUE: 10.23,
                    inv_f.IGST: 14.52,
                    inv_f.CESS: 500,
                    inv_f.TAX_RATE: 5,
                    inv_f.DOC_VALUE: 524.75,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = HSNSUM().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = HSNSUM().convert_to_gov_data_format(
            process_mapped_data(self.mapped_data)
        )
        self.assertDictEqual(self.json_data, output)


class TestHSNSUM_With_Bifurcation(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = {
            gov_f.HSN_B2B: [
                {
                    gov_f.INDEX: 1,
                    gov_f.HSN_CODE: "1102",
                    gov_f.DESCRIPTION: "Goods Description",
                    gov_f.UOM: "BOX",
                    gov_f.QUANTITY: 2,
                    gov_f.TAXABLE_VALUE: 100,
                    gov_f.CGST: 0.5,
                    gov_f.SGST: 0.5,
                    gov_f.TAX_RATE: 1,
                }
            ],
            gov_f.HSN_B2C: [
                {
                    gov_f.INDEX: 1,
                    gov_f.HSN_CODE: "1301",
                    gov_f.DESCRIPTION: "Goods Description",
                    gov_f.UOM: "CTN",
                    gov_f.QUANTITY: 2,
                    gov_f.TAXABLE_VALUE: 100,
                    gov_f.IGST: 1,
                    gov_f.CESS: 10,
                    gov_f.TAX_RATE: 1,
                },
            ],
        }

        cls.mapped_data = {
            GSTR1_SubCategory.HSN_B2B.value: {
                "1102 - BOX-BOX - 1.0": {
                    inv_f.DOC_TYPE: GSTR1_SubCategory.HSN_B2B.value,
                    inv_f.HSN_CODE: "1102",
                    inv_f.DESCRIPTION: "Goods Description",
                    inv_f.UOM: "BOX-BOX",
                    inv_f.QUANTITY: 2,
                    inv_f.TAXABLE_VALUE: 100,
                    inv_f.CGST: 0.5,
                    inv_f.SGST: 0.5,
                    inv_f.TAX_RATE: 1,
                    inv_f.DOC_VALUE: 101,
                }
            },
            GSTR1_SubCategory.HSN_B2C.value: {
                "1301 - CTN-CARTONS - 1.0": {
                    inv_f.DOC_TYPE: GSTR1_SubCategory.HSN_B2C.value,
                    inv_f.HSN_CODE: "1301",
                    inv_f.DESCRIPTION: "Goods Description",
                    inv_f.UOM: "CTN-CARTONS",
                    inv_f.QUANTITY: 2,
                    inv_f.TAXABLE_VALUE: 100,
                    inv_f.IGST: 1,
                    inv_f.CESS: 10,
                    inv_f.TAX_RATE: 1,
                    inv_f.DOC_VALUE: 111,
                },
            },
        }

    def test_convert_to_internal_data_format(self):
        output = HSNSUM().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = HSNSUM().convert_to_gov_data_format(
            process_mapped_data(self.mapped_data)
        )
        self.assertDictEqual(self.json_data, output)


class TestAT(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                gov_f.POS: "05",
                gov_f.SUPPLY_TYPE: "INTER",
                gov_f.DIFF_PERCENTAGE: 0.65,
                gov_f.ITEMS: [
                    {
                        gov_f.TAX_RATE: 5,
                        gov_f.ADVANCE_AMOUNT: 100,
                        gov_f.IGST: 9400,
                        gov_f.CGST: 0,
                        gov_f.SGST: 0,
                        gov_f.CESS: 500,
                    },
                    {
                        gov_f.TAX_RATE: 6,
                        gov_f.ADVANCE_AMOUNT: 100,
                        gov_f.IGST: 9400,
                        gov_f.CGST: 0,
                        gov_f.SGST: 0,
                        gov_f.CESS: 500,
                    },
                ],
            },
            {
                gov_f.POS: "24",
                gov_f.SUPPLY_TYPE: "INTER",
                gov_f.DIFF_PERCENTAGE: 0.65,
                gov_f.ITEMS: [
                    {
                        gov_f.TAX_RATE: 5,
                        gov_f.ADVANCE_AMOUNT: 100,
                        gov_f.IGST: 9400,
                        gov_f.CGST: 0,
                        gov_f.SGST: 0,
                        gov_f.CESS: 500,
                    },
                    {
                        gov_f.TAX_RATE: 6,
                        gov_f.ADVANCE_AMOUNT: 100,
                        gov_f.IGST: 9400,
                        gov_f.CGST: 0,
                        gov_f.SGST: 0,
                        gov_f.CESS: 500,
                    },
                ],
            },
        ]

        cls.mapped_data = {
            GSTR1_SubCategory.AT.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        inv_f.POS: "05-Uttarakhand",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.IGST: 9400,
                        inv_f.CESS: 500,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                        inv_f.TAXABLE_VALUE: 100,
                        inv_f.TAX_RATE: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        inv_f.POS: "05-Uttarakhand",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.IGST: 9400,
                        inv_f.CESS: 500,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                        inv_f.TAXABLE_VALUE: 100,
                        inv_f.TAX_RATE: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        inv_f.POS: "24-Gujarat",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.IGST: 9400,
                        inv_f.CESS: 500,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                        inv_f.TAXABLE_VALUE: 100,
                        inv_f.TAX_RATE: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        inv_f.POS: "24-Gujarat",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.IGST: 9400,
                        inv_f.CESS: 500,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                        inv_f.TAXABLE_VALUE: 100,
                        inv_f.TAX_RATE: 6,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = AT().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = AT().convert_to_gov_data_format(process_mapped_data(self.mapped_data))
        self.assertListEqual(self.json_data, output)


class TestTXPD(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                gov_f.POS: "05",
                gov_f.SUPPLY_TYPE: "INTER",
                gov_f.DIFF_PERCENTAGE: 0.65,
                gov_f.ITEMS: [
                    {
                        gov_f.TAX_RATE: 5,
                        gov_f.ADVANCE_AMOUNT: 100,
                        gov_f.IGST: 9400,
                        gov_f.CGST: 0,
                        gov_f.SGST: 0,
                        gov_f.CESS: 500,
                    },
                    {
                        gov_f.TAX_RATE: 6,
                        gov_f.ADVANCE_AMOUNT: 100,
                        gov_f.IGST: 9400,
                        gov_f.CGST: 0,
                        gov_f.SGST: 0,
                        gov_f.CESS: 500,
                    },
                ],
            },
            {
                gov_f.POS: "24",
                gov_f.SUPPLY_TYPE: "INTER",
                gov_f.DIFF_PERCENTAGE: 0.65,
                gov_f.ITEMS: [
                    {
                        gov_f.TAX_RATE: 5,
                        gov_f.ADVANCE_AMOUNT: 100,
                        gov_f.IGST: 9400,
                        gov_f.CGST: 0,
                        gov_f.SGST: 0,
                        gov_f.CESS: 500,
                    },
                    {
                        gov_f.TAX_RATE: 6,
                        gov_f.ADVANCE_AMOUNT: 100,
                        gov_f.IGST: 9400,
                        gov_f.CGST: 0,
                        gov_f.SGST: 0,
                        gov_f.CESS: 500,
                    },
                ],
            },
        ]

        cls.mapped_data = {
            GSTR1_SubCategory.TXP.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        inv_f.POS: "05-Uttarakhand",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.IGST: -9400,
                        inv_f.CESS: -500,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                        inv_f.TAXABLE_VALUE: -100,
                        inv_f.TAX_RATE: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        inv_f.POS: "05-Uttarakhand",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.IGST: -9400,
                        inv_f.CESS: -500,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                        inv_f.TAXABLE_VALUE: -100,
                        inv_f.TAX_RATE: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        inv_f.POS: "24-Gujarat",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.IGST: -9400,
                        inv_f.CESS: -500,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                        inv_f.TAXABLE_VALUE: -100,
                        inv_f.TAX_RATE: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        inv_f.POS: "24-Gujarat",
                        inv_f.DIFF_PERCENTAGE: 0.65,
                        inv_f.IGST: -9400,
                        inv_f.CESS: -500,
                        inv_f.CGST: 0,
                        inv_f.SGST: 0,
                        inv_f.TAXABLE_VALUE: -100,
                        inv_f.TAX_RATE: 6,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = TXPD().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = TXPD().convert_to_gov_data_format(
            process_mapped_data(self.mapped_data)
        )
        self.assertListEqual(self.json_data, output)


class TestDOC_ISSUE(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            gov_f.DOC_ISSUE_DETAILS: [
                {
                    gov_f.DOC_ISSUE_NUMBER: 1,
                    gov_f.DOC_ISSUE_LIST: [
                        {
                            gov_f.INDEX: 1,
                            gov_f.FROM_SR: "1",
                            gov_f.TO_SR: "10",
                            gov_f.TOTAL_COUNT: 10,
                            gov_f.CANCELLED_COUNT: 0,
                            gov_f.NET_ISSUE: 10,
                        },
                        {
                            gov_f.INDEX: 2,
                            gov_f.FROM_SR: "11",
                            gov_f.TO_SR: "20",
                            gov_f.TOTAL_COUNT: 10,
                            gov_f.CANCELLED_COUNT: 0,
                            gov_f.NET_ISSUE: 10,
                        },
                    ],
                },
                {
                    gov_f.DOC_ISSUE_NUMBER: 2,
                    gov_f.DOC_ISSUE_LIST: [
                        {
                            gov_f.INDEX: 1,
                            gov_f.FROM_SR: "1",
                            gov_f.TO_SR: "10",
                            gov_f.TOTAL_COUNT: 10,
                            gov_f.CANCELLED_COUNT: 0,
                            gov_f.NET_ISSUE: 10,
                        },
                        {
                            gov_f.INDEX: 2,
                            gov_f.FROM_SR: "11",
                            gov_f.TO_SR: "20",
                            gov_f.TOTAL_COUNT: 10,
                            gov_f.CANCELLED_COUNT: 0,
                            gov_f.NET_ISSUE: 10,
                        },
                    ],
                },
            ]
        }
        cls.mapped_data = {
            GSTR1_SubCategory.DOC_ISSUE.value: {
                "Invoices for outward supply - 1": {
                    inv_f.DOC_TYPE: "Invoices for outward supply",
                    inv_f.FROM_SR: "1",
                    inv_f.TO_SR: "10",
                    inv_f.TOTAL_COUNT: 10,
                    inv_f.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
                "Invoices for outward supply - 11": {
                    inv_f.DOC_TYPE: "Invoices for outward supply",
                    inv_f.FROM_SR: "11",
                    inv_f.TO_SR: "20",
                    inv_f.TOTAL_COUNT: 10,
                    inv_f.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
                "Invoices for inward supply from unregistered person - 1": {
                    inv_f.DOC_TYPE: "Invoices for inward supply from unregistered person",
                    inv_f.FROM_SR: "1",
                    inv_f.TO_SR: "10",
                    inv_f.TOTAL_COUNT: 10,
                    inv_f.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
                "Invoices for inward supply from unregistered person - 11": {
                    inv_f.DOC_TYPE: "Invoices for inward supply from unregistered person",
                    inv_f.FROM_SR: "11",
                    inv_f.TO_SR: "20",
                    inv_f.TOTAL_COUNT: 10,
                    inv_f.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = DOC_ISSUE().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = DOC_ISSUE().convert_to_gov_data_format(
            process_mapped_data(self.mapped_data)
        )
        self.assertDictEqual(self.json_data, output)


class TestSUPECOM(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            gov_f.SUPECOM_52: [
                {
                    gov_f.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    gov_f.NET_TAXABLE_VALUE: 10000,
                    "igst": 1000,
                    "cgst": 0,
                    "sgst": 0,
                    "cess": 0,
                }
            ],
            gov_f.SUPECOM_9_5: [
                {
                    gov_f.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    gov_f.NET_TAXABLE_VALUE: 10000,
                    "igst": 1000,
                    "cgst": 0,
                    "sgst": 0,
                    "cess": 0,
                }
            ],
        }

        cls.mapped_data = {
            GSTR1_SubCategory.SUPECOM_52.value: {
                "20ALYPD6528PQC5": {
                    inv_f.DOC_TYPE: GSTR1_SubCategory.SUPECOM_52.value,
                    inv_f.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    inv_f.TAXABLE_VALUE: 10000,
                    item_f.IGST: 1000,
                    item_f.CGST: 0,
                    item_f.SGST: 0,
                    item_f.CESS: 0,
                }
            },
            GSTR1_SubCategory.SUPECOM_9_5.value: {
                "20ALYPD6528PQC5": {
                    inv_f.DOC_TYPE: GSTR1_SubCategory.SUPECOM_9_5.value,
                    inv_f.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    inv_f.TAXABLE_VALUE: 10000,
                    item_f.IGST: 1000,
                    item_f.CGST: 0,
                    item_f.SGST: 0,
                    item_f.CESS: 0,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = SUPECOM().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = SUPECOM().convert_to_gov_data_format(
            process_mapped_data(self.mapped_data)
        )
        self.assertDictEqual(self.json_data, output)


##### ERROR JSON TEST CASES #####


class TestHSNSUMError(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                gov_f.HSN_DATA: [
                    {
                        gov_f.INDEX: 1,
                        gov_f.HSN_CODE: "1010",
                        gov_f.DESCRIPTION: "Goods Description",
                        gov_f.UOM: "KGS",
                        gov_f.QUANTITY: 2.05,
                        gov_f.TAXABLE_VALUE: 10.23,
                        gov_f.IGST: 14.52,
                        gov_f.CESS: 500,
                        gov_f.TAX_RATE: 0.1,
                    },
                ],
                gov_f.ERROR_CD: "RET191350",
                gov_f.ERROR_MSG: "Length of entered HSN code is not valid as per AATO",
            },
            {
                gov_f.HSN_DATA: [
                    {
                        gov_f.INDEX: 2,
                        gov_f.HSN_CODE: "1011",
                        gov_f.DESCRIPTION: "Goods Description",
                        gov_f.UOM: "NOS",
                        gov_f.QUANTITY: 2.05,
                        gov_f.TAXABLE_VALUE: 10.23,
                        gov_f.IGST: 14.52,
                        gov_f.CESS: 500,
                        gov_f.TAX_RATE: 5,
                    }
                ],
                gov_f.ERROR_CD: "RET191350",
                gov_f.ERROR_MSG: "Length of entered HSN code is not valid as per AATO",
            },
        ]

        cls.mapped_data = {
            GSTR1_SubCategory.HSN.value: {
                "1010 - KGS-KILOGRAMS - 0.1": {
                    inv_f.DOC_TYPE: GSTR1_SubCategory.HSN.value,
                    inv_f.HSN_CODE: "1010",
                    inv_f.DESCRIPTION: "Goods Description",
                    inv_f.UOM: "KGS-KILOGRAMS",
                    inv_f.QUANTITY: 2.05,
                    inv_f.TAXABLE_VALUE: 10.23,
                    inv_f.IGST: 14.52,
                    inv_f.CESS: 500,
                    inv_f.TAX_RATE: 0.1,
                    inv_f.DOC_VALUE: 524.75,
                    inv_f.ERROR_CD: "RET191350",
                    inv_f.ERROR_MSG: "HSN Code: 1010 - Length of entered HSN code is not valid as per AATO",
                },
                "1011 - NOS-NUMBERS - 5.0": {
                    inv_f.DOC_TYPE: GSTR1_SubCategory.HSN.value,
                    inv_f.HSN_CODE: "1011",
                    inv_f.DESCRIPTION: "Goods Description",
                    inv_f.UOM: "NOS-NUMBERS",
                    inv_f.QUANTITY: 2.05,
                    inv_f.TAXABLE_VALUE: 10.23,
                    inv_f.IGST: 14.52,
                    inv_f.CESS: 500,
                    inv_f.TAX_RATE: 5,
                    inv_f.DOC_VALUE: 524.75,
                    inv_f.ERROR_CD: "RET191350",
                    inv_f.ERROR_MSG: "HSN Code: 1011 - Length of entered HSN code is not valid as per AATO",
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = HSNSUM().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)
