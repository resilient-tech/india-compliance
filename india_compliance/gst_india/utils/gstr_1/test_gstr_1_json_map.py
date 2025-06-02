import copy

from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    GenerateGSTR1,
)
from india_compliance.gst_india.utils import get_party_for_gstin as _get_party_for_gstin
from india_compliance.gst_india.utils.gstr_1 import (
    GovDataField,
    GSTR1_B2B_InvoiceType,
)
from india_compliance.gst_india.utils.gstr_1 import GSTR1_DataField as df
from india_compliance.gst_india.utils.gstr_1 import GSTR1_ItemField as _if
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


class TestB2B(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                GovDataField.CUST_GSTIN.value: "24AANFA2641L1ZF",
                GovDataField.INVOICES.value: [
                    {
                        GovDataField.DOC_NUMBER.value: "S008400",
                        GovDataField.DOC_DATE.value: "24-11-2016",
                        GovDataField.DOC_VALUE.value: 729248.16,
                        GovDataField.POS.value: "06",
                        GovDataField.REVERSE_CHARGE.value: "N",
                        GovDataField.INVOICE_TYPE.value: "R",
                        GovDataField.DIFF_PERCENTAGE.value: 0.65,
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.INDEX.value: 1,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CGST.value: 0,
                                    GovDataField.SGST.value: 0,
                                    GovDataField.CESS.value: 500,
                                },
                            },
                            {
                                GovDataField.INDEX.value: 2,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CGST.value: 0,
                                    GovDataField.SGST.value: 0,
                                    GovDataField.CESS.value: 500,
                                },
                            },
                        ],
                    },
                    {
                        GovDataField.DOC_NUMBER.value: "S008401",
                        GovDataField.DOC_DATE.value: "24-11-2016",
                        GovDataField.DOC_VALUE.value: 729248.16,
                        GovDataField.POS.value: "06",
                        GovDataField.REVERSE_CHARGE.value: "Y",
                        GovDataField.INVOICE_TYPE.value: "R",
                        GovDataField.DIFF_PERCENTAGE.value: 0.65,
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.INDEX.value: 1,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CGST.value: 0,
                                    GovDataField.SGST.value: 0,
                                    GovDataField.CESS.value: 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                GovDataField.CUST_GSTIN.value: "29AABCR1718E1ZL",
                GovDataField.INVOICES.value: [
                    {
                        GovDataField.DOC_NUMBER.value: "S008402",
                        GovDataField.DOC_DATE.value: "24-11-2016",
                        GovDataField.DOC_VALUE.value: 729248.16,
                        GovDataField.POS.value: "06",
                        GovDataField.REVERSE_CHARGE.value: "N",
                        GovDataField.INVOICE_TYPE.value: "SEWP",
                        GovDataField.DIFF_PERCENTAGE.value: 0.65,
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.INDEX.value: 1,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CGST.value: 0,
                                    GovDataField.SGST.value: 0,
                                    GovDataField.CESS.value: 500,
                                },
                            }
                        ],
                    },
                    {
                        GovDataField.DOC_NUMBER.value: "S008403",
                        GovDataField.DOC_DATE.value: "24-11-2016",
                        GovDataField.DOC_VALUE.value: 729248.16,
                        GovDataField.POS.value: "06",
                        GovDataField.REVERSE_CHARGE.value: "N",
                        GovDataField.INVOICE_TYPE.value: "DE",
                        GovDataField.DIFF_PERCENTAGE.value: 0.65,
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.INDEX.value: 1,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CGST.value: 0,
                                    GovDataField.SGST.value: 0,
                                    GovDataField.CESS.value: 500,
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
                    df.CUST_GSTIN: "24AANFA2641L1ZF",
                    df.CUST_NAME: get_party_for_gstin("24AANFA2641L1ZF"),
                    df.DOC_NUMBER: "S008400",
                    df.DOC_DATE: "2016-11-24",
                    df.DOC_VALUE: 729248.16,
                    df.POS: "06-Haryana",
                    df.REVERSE_CHARGE: "N",
                    df.DOC_TYPE: GSTR1_B2B_InvoiceType.R.value,
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CGST: 0,
                            _if.SGST: 0,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        },
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CGST: 0,
                            _if.SGST: 0,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        },
                    ],
                    df.TAXABLE_VALUE: 20000,
                    df.IGST: 650,
                    df.CGST: 0,
                    df.SGST: 0,
                    df.CESS: 1000,
                }
            },
            GSTR1_SubCategory.B2B_REVERSE_CHARGE.value: {
                "S008401": {
                    df.CUST_GSTIN: "24AANFA2641L1ZF",
                    df.CUST_NAME: get_party_for_gstin("24AANFA2641L1ZF"),
                    df.DOC_NUMBER: "S008401",
                    df.DOC_DATE: "2016-11-24",
                    df.DOC_VALUE: 729248.16,
                    df.POS: "06-Haryana",
                    df.REVERSE_CHARGE: "Y",
                    df.DOC_TYPE: GSTR1_B2B_InvoiceType.R.value,
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CGST: 0,
                            _if.SGST: 0,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        }
                    ],
                    df.TAXABLE_VALUE: 10000,
                    df.IGST: 325,
                    df.CGST: 0,
                    df.SGST: 0,
                    df.CESS: 500,
                }
            },
            GSTR1_SubCategory.SEZWP.value: {
                "S008402": {
                    df.CUST_GSTIN: "29AABCR1718E1ZL",
                    df.CUST_NAME: get_party_for_gstin("29AABCR1718E1ZL"),
                    df.DOC_NUMBER: "S008402",
                    df.DOC_DATE: "2016-11-24",
                    df.DOC_VALUE: 729248.16,
                    df.POS: "06-Haryana",
                    df.REVERSE_CHARGE: "N",
                    df.DOC_TYPE: GSTR1_B2B_InvoiceType.SEWP.value,
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CGST: 0,
                            _if.SGST: 0,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        }
                    ],
                    df.TAXABLE_VALUE: 10000,
                    df.IGST: 325,
                    df.CGST: 0,
                    df.SGST: 0,
                    df.CESS: 500,
                }
            },
            GSTR1_SubCategory.DE.value: {
                "S008403": {
                    df.CUST_GSTIN: "29AABCR1718E1ZL",
                    df.CUST_NAME: get_party_for_gstin("29AABCR1718E1ZL"),
                    df.DOC_NUMBER: "S008403",
                    df.DOC_DATE: "2016-11-24",
                    df.DOC_VALUE: 729248.16,
                    df.POS: "06-Haryana",
                    df.REVERSE_CHARGE: "N",
                    df.DOC_TYPE: GSTR1_B2B_InvoiceType.DE.value,
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CGST: 0,
                            _if.SGST: 0,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        }
                    ],
                    df.TAXABLE_VALUE: 10000,
                    df.IGST: 325,
                    df.CGST: 0,
                    df.SGST: 0,
                    df.CESS: 500,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = B2B().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = B2B().convert_to_gov_data_format(process_mapped_data(self.mapped_data))
        self.assertListEqual(self.json_data, output)


class TestB2CL(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                GovDataField.POS.value: "05",
                GovDataField.INVOICES.value: [
                    {
                        GovDataField.DOC_NUMBER.value: "92661",
                        GovDataField.DOC_DATE.value: "10-01-2016",
                        GovDataField.DOC_VALUE.value: 784586.33,
                        GovDataField.DIFF_PERCENTAGE.value: 0.65,
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.INDEX.value: 1,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CESS.value: 500,
                                },
                            },
                            {
                                GovDataField.INDEX.value: 2,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CESS.value: 500,
                                },
                            },
                        ],
                    },
                    {
                        GovDataField.DOC_NUMBER.value: "92662",
                        GovDataField.DOC_DATE.value: "10-01-2016",
                        GovDataField.DOC_VALUE.value: 784586.33,
                        GovDataField.DIFF_PERCENTAGE.value: 0.65,
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.INDEX.value: 1,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CESS.value: 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                GovDataField.POS.value: "24",
                GovDataField.INVOICES.value: [
                    {
                        GovDataField.DOC_NUMBER.value: "92663",
                        GovDataField.DOC_DATE.value: "10-01-2016",
                        GovDataField.DOC_VALUE.value: 784586.33,
                        GovDataField.DIFF_PERCENTAGE.value: 0.65,
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.INDEX.value: 1,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CESS.value: 500,
                                },
                            },
                            {
                                GovDataField.INDEX.value: 2,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CESS.value: 500,
                                },
                            },
                        ],
                    },
                    {
                        GovDataField.DOC_NUMBER.value: "92664",
                        GovDataField.DOC_DATE.value: "10-01-2016",
                        GovDataField.DOC_VALUE.value: 784586.33,
                        GovDataField.DIFF_PERCENTAGE.value: 0.65,
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.INDEX.value: 1,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 5,
                                    GovDataField.TAXABLE_VALUE.value: 10000,
                                    GovDataField.IGST.value: 325,
                                    GovDataField.CESS.value: 500,
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
                    df.POS: "05-Uttarakhand",
                    df.DOC_TYPE: "B2C (Large)",
                    df.DOC_NUMBER: "92661",
                    df.DOC_DATE: "2016-01-10",
                    df.DOC_VALUE: 784586.33,
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        },
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        },
                    ],
                    df.TAXABLE_VALUE: 20000,
                    df.IGST: 650,
                    df.CESS: 1000,
                },
                "92662": {
                    df.POS: "05-Uttarakhand",
                    df.DOC_TYPE: "B2C (Large)",
                    df.DOC_NUMBER: "92662",
                    df.DOC_DATE: "2016-01-10",
                    df.DOC_VALUE: 784586.33,
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        }
                    ],
                    df.TAXABLE_VALUE: 10000,
                    df.IGST: 325,
                    df.CESS: 500,
                },
                "92663": {
                    df.POS: "24-Gujarat",
                    df.DOC_TYPE: "B2C (Large)",
                    df.DOC_NUMBER: "92663",
                    df.DOC_DATE: "2016-01-10",
                    df.DOC_VALUE: 784586.33,
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        },
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        },
                    ],
                    df.TAXABLE_VALUE: 20000,
                    df.IGST: 650,
                    df.CESS: 1000,
                },
                "92664": {
                    df.POS: "24-Gujarat",
                    df.DOC_TYPE: "B2C (Large)",
                    df.DOC_NUMBER: "92664",
                    df.DOC_DATE: "2016-01-10",
                    df.DOC_VALUE: 784586.33,
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 325,
                            _if.CESS: 500,
                            df.TAX_RATE: 5,
                        }
                    ],
                    df.TAXABLE_VALUE: 10000,
                    df.IGST: 325,
                    df.CESS: 500,
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


class TestExports(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                GovDataField.EXPORT_TYPE.value: "WPAY",
                GovDataField.INVOICES.value: [
                    {
                        GovDataField.DOC_NUMBER.value: "81542",
                        GovDataField.DOC_DATE.value: "12-02-2016",
                        GovDataField.DOC_VALUE.value: 995048.36,
                        GovDataField.SHIPPING_PORT_CODE.value: "ASB991",
                        GovDataField.SHIPPING_BILL_NUMBER.value: "7896542",
                        GovDataField.SHIPPING_BILL_DATE.value: "04-10-2016",
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.TAXABLE_VALUE.value: 10000,
                                GovDataField.TAX_RATE.value: 5,
                                GovDataField.IGST.value: 833.33,
                                GovDataField.CESS.value: 100,
                            }
                        ],
                    }
                ],
            },
            {
                GovDataField.EXPORT_TYPE.value: "WOPAY",
                GovDataField.INVOICES.value: [
                    {
                        GovDataField.DOC_NUMBER.value: "81543",
                        GovDataField.DOC_DATE.value: "12-02-2016",
                        GovDataField.DOC_VALUE.value: 995048.36,
                        GovDataField.SHIPPING_PORT_CODE.value: "ASB981",
                        GovDataField.SHIPPING_BILL_NUMBER.value: "7896542",
                        GovDataField.SHIPPING_BILL_DATE.value: "04-10-2016",
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.TAXABLE_VALUE.value: 10000,
                                GovDataField.TAX_RATE.value: 0,
                                GovDataField.IGST.value: 0,
                                GovDataField.CESS.value: 100,
                            }
                        ],
                    }
                ],
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategory.EXPWP.value: {
                "81542": {
                    df.DOC_TYPE: "WPAY",
                    df.DOC_NUMBER: "81542",
                    df.DOC_DATE: "2016-02-12",
                    df.DOC_VALUE: 995048.36,
                    df.SHIPPING_PORT_CODE: "ASB991",
                    df.SHIPPING_BILL_NUMBER: "7896542",
                    df.SHIPPING_BILL_DATE: "2016-10-04",
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 833.33,
                            _if.CESS: 100,
                            df.TAX_RATE: 5,
                        }
                    ],
                    df.TAXABLE_VALUE: 10000,
                    df.IGST: 833.33,
                    df.CESS: 100,
                }
            },
            GSTR1_SubCategory.EXPWOP.value: {
                "81543": {
                    df.DOC_TYPE: "WOPAY",
                    df.DOC_NUMBER: "81543",
                    df.DOC_DATE: "2016-02-12",
                    df.DOC_VALUE: 995048.36,
                    df.SHIPPING_PORT_CODE: "ASB981",
                    df.SHIPPING_BILL_NUMBER: "7896542",
                    df.SHIPPING_BILL_DATE: "2016-10-04",
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: 10000,
                            _if.IGST: 0,
                            _if.CESS: 100,
                            df.TAX_RATE: 0,
                        }
                    ],
                    df.TAXABLE_VALUE: 10000,
                    df.IGST: 0,
                    df.CESS: 100,
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


class TestB2CS(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                GovDataField.SUPPLY_TYPE.value: "INTER",
                GovDataField.DIFF_PERCENTAGE.value: 0.65,
                GovDataField.TAX_RATE.value: 5,
                GovDataField.TYPE.value: "OE",
                GovDataField.POS.value: "05",
                GovDataField.TAXABLE_VALUE.value: 110,
                GovDataField.IGST.value: 10,
                GovDataField.CGST.value: 0,
                GovDataField.SGST.value: 0,
                GovDataField.CESS.value: 10,
            },
            {
                GovDataField.SUPPLY_TYPE.value: "INTER",
                GovDataField.DIFF_PERCENTAGE.value: 0.65,
                GovDataField.TAX_RATE.value: 5,
                GovDataField.TYPE.value: "OE",
                GovDataField.TAXABLE_VALUE.value: 100,
                GovDataField.IGST.value: 10,
                GovDataField.CGST.value: 0,
                GovDataField.SGST.value: 0,
                GovDataField.CESS.value: 10,
                GovDataField.POS.value: "06",
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategory.B2CS.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        df.TAXABLE_VALUE: 110,
                        df.DOC_TYPE: "OE",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.POS: "05-Uttarakhand",
                        df.TAX_RATE: 5,
                        df.IGST: 10,
                        df.CESS: 10,
                        df.CGST: 0,
                        df.SGST: 0,
                    },
                ],
                "06-Haryana - 5.0": [
                    {
                        df.TAXABLE_VALUE: 100,
                        df.DOC_TYPE: "OE",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.POS: "06-Haryana",
                        df.TAX_RATE: 5,
                        df.IGST: 10,
                        df.CESS: 10,
                        df.CGST: 0,
                        df.SGST: 0,
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


class TestNilRated(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            GovDataField.INVOICES.value: [
                {
                    GovDataField.SUPPLY_TYPE.value: "INTRB2B",
                    GovDataField.EXEMPTED_AMOUNT.value: 123.45,
                    GovDataField.NIL_RATED_AMOUNT.value: 1470.85,
                    GovDataField.NON_GST_AMOUNT.value: 1258.5,
                },
                {
                    GovDataField.SUPPLY_TYPE.value: "INTRB2C",
                    GovDataField.EXEMPTED_AMOUNT.value: 123.45,
                    GovDataField.NIL_RATED_AMOUNT.value: 1470.85,
                    GovDataField.NON_GST_AMOUNT.value: 1258.5,
                },
            ]
        }

        cls.mapped_data = {
            GSTR1_SubCategory.NIL_EXEMPT.value: {
                "Inter-State supplies to registered persons": [
                    {
                        df.DOC_TYPE: "Inter-State supplies to registered persons",
                        df.EXEMPTED_AMOUNT: 123.45,
                        df.NIL_RATED_AMOUNT: 1470.85,
                        df.NON_GST_AMOUNT: 1258.5,
                        df.TAXABLE_VALUE: 2852.8,
                    }
                ],
                "Inter-State supplies to unregistered persons": [
                    {
                        df.DOC_TYPE: "Inter-State supplies to unregistered persons",
                        df.EXEMPTED_AMOUNT: 123.45,
                        df.NIL_RATED_AMOUNT: 1470.85,
                        df.NON_GST_AMOUNT: 1258.5,
                        df.TAXABLE_VALUE: 2852.8,
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


class TestCDNR(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                GovDataField.CUST_GSTIN.value: "24AANFA2641L1ZF",
                GovDataField.NOTE_DETAILS.value: [
                    {
                        GovDataField.NOTE_TYPE.value: "C",
                        GovDataField.NOTE_NUMBER.value: "533515",
                        GovDataField.NOTE_DATE.value: "23-09-2016",
                        GovDataField.POS.value: "03",
                        GovDataField.REVERSE_CHARGE.value: "Y",
                        GovDataField.INVOICE_TYPE.value: "DE",
                        GovDataField.DOC_VALUE.value: 123123,
                        GovDataField.DIFF_PERCENTAGE.value: 0.65,
                        GovDataField.ITEMS.value: [
                            {
                                GovDataField.INDEX.value: 1,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 10,
                                    GovDataField.TAXABLE_VALUE.value: 5225.28,
                                    GovDataField.SGST.value: 0,
                                    GovDataField.CGST.value: 0,
                                    GovDataField.IGST.value: 339.64,
                                    GovDataField.CESS.value: 789.52,
                                },
                            },
                            {
                                GovDataField.INDEX.value: 2,
                                GovDataField.ITEM_DETAILS.value: {
                                    GovDataField.TAX_RATE.value: 10,
                                    GovDataField.TAXABLE_VALUE.value: 5225.28,
                                    GovDataField.SGST.value: 0,
                                    GovDataField.CGST.value: 0,
                                    GovDataField.IGST.value: 339.64,
                                    GovDataField.CESS.value: 789.52,
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
                    df.CUST_GSTIN: "24AANFA2641L1ZF",
                    df.CUST_NAME: get_party_for_gstin("24AANFA2641L1ZF"),
                    df.TRANSACTION_TYPE: "Credit Note",
                    df.DOC_NUMBER: "533515",
                    df.DOC_DATE: "2016-09-23",
                    df.POS: "03-Punjab",
                    df.REVERSE_CHARGE: "Y",
                    df.DOC_TYPE: "Deemed Exports",
                    df.DOC_VALUE: -123123,
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: -5225.28,
                            _if.IGST: -339.64,
                            _if.CGST: 0,
                            _if.SGST: 0,
                            _if.CESS: -789.52,
                            df.TAX_RATE: 10,
                        },
                        {
                            _if.TAXABLE_VALUE: -5225.28,
                            _if.IGST: -339.64,
                            _if.CGST: 0,
                            _if.SGST: 0,
                            _if.CESS: -789.52,
                            df.TAX_RATE: 10,
                        },
                    ],
                    df.TAXABLE_VALUE: -10450.56,
                    df.IGST: -679.28,
                    df.CGST: 0,
                    df.SGST: 0,
                    df.CESS: -1579.04,
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


class TestCDNUR(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                GovDataField.TYPE.value: "B2CL",
                GovDataField.NOTE_TYPE.value: "C",
                GovDataField.NOTE_NUMBER.value: "533515",
                GovDataField.NOTE_DATE.value: "23-09-2016",
                GovDataField.POS.value: "03",
                GovDataField.DOC_VALUE.value: 64646,
                GovDataField.DIFF_PERCENTAGE.value: 0.65,
                GovDataField.ITEMS.value: [
                    {
                        GovDataField.INDEX.value: 1,
                        GovDataField.ITEM_DETAILS.value: {
                            GovDataField.TAX_RATE.value: 10,
                            GovDataField.TAXABLE_VALUE.value: 5225.28,
                            GovDataField.IGST.value: 339.64,
                            GovDataField.CESS.value: 789.52,
                        },
                    }
                ],
            }
        ]

        cls.mapped_data = {
            GSTR1_SubCategory.CDNUR.value: {
                "533515": {
                    df.TRANSACTION_TYPE: "Credit Note",
                    df.DOC_TYPE: "B2CL",
                    df.DOC_NUMBER: "533515",
                    df.DOC_DATE: "2016-09-23",
                    df.DOC_VALUE: -64646,
                    df.POS: "03-Punjab",
                    df.DIFF_PERCENTAGE: 0.65,
                    df.ITEMS: [
                        {
                            _if.TAXABLE_VALUE: -5225.28,
                            _if.IGST: -339.64,
                            _if.CESS: -789.52,
                            df.TAX_RATE: 10,
                        }
                    ],
                    df.TAXABLE_VALUE: -5225.28,
                    df.IGST: -339.64,
                    df.CESS: -789.52,
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


class TestHSNSUM(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = {
            GovDataField.HSN_DATA.value: [
                {
                    GovDataField.INDEX.value: 1,
                    GovDataField.HSN_CODE.value: "1010",
                    GovDataField.DESCRIPTION.value: "Goods Description",
                    GovDataField.UOM.value: "KGS",
                    GovDataField.QUANTITY.value: 2.05,
                    GovDataField.TAXABLE_VALUE.value: 10.23,
                    GovDataField.IGST.value: 14.52,
                    GovDataField.CESS.value: 500,
                    GovDataField.TAX_RATE.value: 0.1,
                },
                {
                    GovDataField.INDEX.value: 2,
                    GovDataField.HSN_CODE.value: "1011",
                    GovDataField.DESCRIPTION.value: "Goods Description",
                    GovDataField.UOM.value: "NOS",
                    GovDataField.QUANTITY.value: 2.05,
                    GovDataField.TAXABLE_VALUE.value: 10.23,
                    GovDataField.IGST.value: 14.52,
                    GovDataField.CESS.value: 500,
                    GovDataField.TAX_RATE.value: 5,
                },
            ]
        }

        cls.mapped_data = {
            GSTR1_SubCategory.HSN.value: {
                "1010 - KGS-KILOGRAMS - 0.1": {
                    df.DOC_TYPE: GSTR1_SubCategory.HSN.value,
                    df.HSN_CODE: "1010",
                    df.DESCRIPTION: "Goods Description",
                    df.UOM: "KGS-KILOGRAMS",
                    df.QUANTITY: 2.05,
                    df.TAXABLE_VALUE: 10.23,
                    df.IGST: 14.52,
                    df.CESS: 500,
                    df.TAX_RATE: 0.1,
                    df.DOC_VALUE: 524.75,
                },
                "1011 - NOS-NUMBERS - 5.0": {
                    df.DOC_TYPE: GSTR1_SubCategory.HSN.value,
                    df.HSN_CODE: "1011",
                    df.DESCRIPTION: "Goods Description",
                    df.UOM: "NOS-NUMBERS",
                    df.QUANTITY: 2.05,
                    df.TAXABLE_VALUE: 10.23,
                    df.IGST: 14.52,
                    df.CESS: 500,
                    df.TAX_RATE: 5,
                    df.DOC_VALUE: 524.75,
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


class TestHSNSUM_With_Bifurcation(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = {
            GovDataField.HSN_B2B.value: [
                {
                    GovDataField.INDEX.value: 1,
                    GovDataField.HSN_CODE.value: "1102",
                    GovDataField.DESCRIPTION.value: "Goods Description",
                    GovDataField.UOM.value: "BOX",
                    GovDataField.QUANTITY.value: 2,
                    GovDataField.TAXABLE_VALUE.value: 100,
                    GovDataField.CGST.value: 0.5,
                    GovDataField.SGST.value: 0.5,
                    GovDataField.TAX_RATE.value: 1,
                }
            ],
            GovDataField.HSN_B2C.value: [
                {
                    GovDataField.INDEX.value: 1,
                    GovDataField.HSN_CODE.value: "1301",
                    GovDataField.DESCRIPTION.value: "Goods Description",
                    GovDataField.UOM.value: "CTN",
                    GovDataField.QUANTITY.value: 2,
                    GovDataField.TAXABLE_VALUE.value: 100,
                    GovDataField.IGST.value: 1,
                    GovDataField.CESS.value: 10,
                    GovDataField.TAX_RATE.value: 1,
                },
            ],
        }

        cls.mapped_data = {
            GSTR1_SubCategory.HSN_B2B.value: {
                "1102 - BOX-BOX - 1.0": {
                    df.DOC_TYPE: GSTR1_SubCategory.HSN_B2B.value,
                    df.HSN_CODE: "1102",
                    df.DESCRIPTION: "Goods Description",
                    df.UOM: "BOX-BOX",
                    df.QUANTITY: 2,
                    df.TAXABLE_VALUE: 100,
                    df.CGST: 0.5,
                    df.SGST: 0.5,
                    df.TAX_RATE: 1,
                    df.DOC_VALUE: 101,
                }
            },
            GSTR1_SubCategory.HSN_B2C.value: {
                "1301 - CTN-CARTONS - 1.0": {
                    df.DOC_TYPE: GSTR1_SubCategory.HSN_B2C.value,
                    df.HSN_CODE: "1301",
                    df.DESCRIPTION: "Goods Description",
                    df.UOM: "CTN-CARTONS",
                    df.QUANTITY: 2,
                    df.TAXABLE_VALUE: 100,
                    df.IGST: 1,
                    df.CESS: 10,
                    df.TAX_RATE: 1,
                    df.DOC_VALUE: 111,
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


class TestAT(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                GovDataField.POS.value: "05",
                GovDataField.SUPPLY_TYPE.value: "INTER",
                GovDataField.DIFF_PERCENTAGE.value: 0.65,
                GovDataField.ITEMS.value: [
                    {
                        GovDataField.TAX_RATE.value: 5,
                        GovDataField.ADVANCE_AMOUNT.value: 100,
                        GovDataField.IGST.value: 9400,
                        GovDataField.CGST.value: 0,
                        GovDataField.SGST.value: 0,
                        GovDataField.CESS.value: 500,
                    },
                    {
                        GovDataField.TAX_RATE.value: 6,
                        GovDataField.ADVANCE_AMOUNT.value: 100,
                        GovDataField.IGST.value: 9400,
                        GovDataField.CGST.value: 0,
                        GovDataField.SGST.value: 0,
                        GovDataField.CESS.value: 500,
                    },
                ],
            },
            {
                GovDataField.POS.value: "24",
                GovDataField.SUPPLY_TYPE.value: "INTER",
                GovDataField.DIFF_PERCENTAGE.value: 0.65,
                GovDataField.ITEMS.value: [
                    {
                        GovDataField.TAX_RATE.value: 5,
                        GovDataField.ADVANCE_AMOUNT.value: 100,
                        GovDataField.IGST.value: 9400,
                        GovDataField.CGST.value: 0,
                        GovDataField.SGST.value: 0,
                        GovDataField.CESS.value: 500,
                    },
                    {
                        GovDataField.TAX_RATE.value: 6,
                        GovDataField.ADVANCE_AMOUNT.value: 100,
                        GovDataField.IGST.value: 9400,
                        GovDataField.CGST.value: 0,
                        GovDataField.SGST.value: 0,
                        GovDataField.CESS.value: 500,
                    },
                ],
            },
        ]

        cls.mapped_data = {
            GSTR1_SubCategory.AT.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        df.POS: "05-Uttarakhand",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.IGST: 9400,
                        df.CESS: 500,
                        df.CGST: 0,
                        df.SGST: 0,
                        df.TAXABLE_VALUE: 100,
                        df.TAX_RATE: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        df.POS: "05-Uttarakhand",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.IGST: 9400,
                        df.CESS: 500,
                        df.CGST: 0,
                        df.SGST: 0,
                        df.TAXABLE_VALUE: 100,
                        df.TAX_RATE: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        df.POS: "24-Gujarat",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.IGST: 9400,
                        df.CESS: 500,
                        df.CGST: 0,
                        df.SGST: 0,
                        df.TAXABLE_VALUE: 100,
                        df.TAX_RATE: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        df.POS: "24-Gujarat",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.IGST: 9400,
                        df.CESS: 500,
                        df.CGST: 0,
                        df.SGST: 0,
                        df.TAXABLE_VALUE: 100,
                        df.TAX_RATE: 6,
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


class TestTXPD(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                GovDataField.POS.value: "05",
                GovDataField.SUPPLY_TYPE.value: "INTER",
                GovDataField.DIFF_PERCENTAGE.value: 0.65,
                GovDataField.ITEMS.value: [
                    {
                        GovDataField.TAX_RATE.value: 5,
                        GovDataField.ADVANCE_AMOUNT.value: 100,
                        GovDataField.IGST.value: 9400,
                        GovDataField.CGST.value: 0,
                        GovDataField.SGST.value: 0,
                        GovDataField.CESS.value: 500,
                    },
                    {
                        GovDataField.TAX_RATE.value: 6,
                        GovDataField.ADVANCE_AMOUNT.value: 100,
                        GovDataField.IGST.value: 9400,
                        GovDataField.CGST.value: 0,
                        GovDataField.SGST.value: 0,
                        GovDataField.CESS.value: 500,
                    },
                ],
            },
            {
                GovDataField.POS.value: "24",
                GovDataField.SUPPLY_TYPE.value: "INTER",
                GovDataField.DIFF_PERCENTAGE.value: 0.65,
                GovDataField.ITEMS.value: [
                    {
                        GovDataField.TAX_RATE.value: 5,
                        GovDataField.ADVANCE_AMOUNT.value: 100,
                        GovDataField.IGST.value: 9400,
                        GovDataField.CGST.value: 0,
                        GovDataField.SGST.value: 0,
                        GovDataField.CESS.value: 500,
                    },
                    {
                        GovDataField.TAX_RATE.value: 6,
                        GovDataField.ADVANCE_AMOUNT.value: 100,
                        GovDataField.IGST.value: 9400,
                        GovDataField.CGST.value: 0,
                        GovDataField.SGST.value: 0,
                        GovDataField.CESS.value: 500,
                    },
                ],
            },
        ]

        cls.mapped_data = {
            GSTR1_SubCategory.TXP.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        df.POS: "05-Uttarakhand",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.IGST: -9400,
                        df.CESS: -500,
                        df.CGST: 0,
                        df.SGST: 0,
                        df.TAXABLE_VALUE: -100,
                        df.TAX_RATE: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        df.POS: "05-Uttarakhand",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.IGST: -9400,
                        df.CESS: -500,
                        df.CGST: 0,
                        df.SGST: 0,
                        df.TAXABLE_VALUE: -100,
                        df.TAX_RATE: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        df.POS: "24-Gujarat",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.IGST: -9400,
                        df.CESS: -500,
                        df.CGST: 0,
                        df.SGST: 0,
                        df.TAXABLE_VALUE: -100,
                        df.TAX_RATE: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        df.POS: "24-Gujarat",
                        df.DIFF_PERCENTAGE: 0.65,
                        df.IGST: -9400,
                        df.CESS: -500,
                        df.CGST: 0,
                        df.SGST: 0,
                        df.TAXABLE_VALUE: -100,
                        df.TAX_RATE: 6,
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


class TestDOC_ISSUE(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            GovDataField.DOC_ISSUE_DETAILS.value: [
                {
                    GovDataField.DOC_ISSUE_NUMBER.value: 1,
                    GovDataField.DOC_ISSUE_LIST.value: [
                        {
                            GovDataField.INDEX.value: 1,
                            GovDataField.FROM_SR.value: "1",
                            GovDataField.TO_SR.value: "10",
                            GovDataField.TOTAL_COUNT.value: 10,
                            GovDataField.CANCELLED_COUNT.value: 0,
                            GovDataField.NET_ISSUE.value: 10,
                        },
                        {
                            GovDataField.INDEX.value: 2,
                            GovDataField.FROM_SR.value: "11",
                            GovDataField.TO_SR.value: "20",
                            GovDataField.TOTAL_COUNT.value: 10,
                            GovDataField.CANCELLED_COUNT.value: 0,
                            GovDataField.NET_ISSUE.value: 10,
                        },
                    ],
                },
                {
                    GovDataField.DOC_ISSUE_NUMBER.value: 2,
                    GovDataField.DOC_ISSUE_LIST.value: [
                        {
                            GovDataField.INDEX.value: 1,
                            GovDataField.FROM_SR.value: "1",
                            GovDataField.TO_SR.value: "10",
                            GovDataField.TOTAL_COUNT.value: 10,
                            GovDataField.CANCELLED_COUNT.value: 0,
                            GovDataField.NET_ISSUE.value: 10,
                        },
                        {
                            GovDataField.INDEX.value: 2,
                            GovDataField.FROM_SR.value: "11",
                            GovDataField.TO_SR.value: "20",
                            GovDataField.TOTAL_COUNT.value: 10,
                            GovDataField.CANCELLED_COUNT.value: 0,
                            GovDataField.NET_ISSUE.value: 10,
                        },
                    ],
                },
            ]
        }
        cls.mapped_data = {
            GSTR1_SubCategory.DOC_ISSUE.value: {
                "Invoices for outward supply - 1": {
                    df.DOC_TYPE: "Invoices for outward supply",
                    df.FROM_SR: "1",
                    df.TO_SR: "10",
                    df.TOTAL_COUNT: 10,
                    df.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
                "Invoices for outward supply - 11": {
                    df.DOC_TYPE: "Invoices for outward supply",
                    df.FROM_SR: "11",
                    df.TO_SR: "20",
                    df.TOTAL_COUNT: 10,
                    df.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
                "Invoices for inward supply from unregistered person - 1": {
                    df.DOC_TYPE: "Invoices for inward supply from unregistered person",
                    df.FROM_SR: "1",
                    df.TO_SR: "10",
                    df.TOTAL_COUNT: 10,
                    df.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
                "Invoices for inward supply from unregistered person - 11": {
                    df.DOC_TYPE: "Invoices for inward supply from unregistered person",
                    df.FROM_SR: "11",
                    df.TO_SR: "20",
                    df.TOTAL_COUNT: 10,
                    df.CANCELLED_COUNT: 0,
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


class TestSUPECOM(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            GovDataField.SUPECOM_52.value: [
                {
                    GovDataField.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    GovDataField.NET_TAXABLE_VALUE.value: 10000,
                    "igst": 1000,
                    "cgst": 0,
                    "sgst": 0,
                    "cess": 0,
                }
            ],
            GovDataField.SUPECOM_9_5.value: [
                {
                    GovDataField.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    GovDataField.NET_TAXABLE_VALUE.value: 10000,
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
                    df.DOC_TYPE: GSTR1_SubCategory.SUPECOM_52.value,
                    df.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    df.TAXABLE_VALUE: 10000,
                    _if.IGST: 1000,
                    _if.CGST: 0,
                    _if.SGST: 0,
                    _if.CESS: 0,
                }
            },
            GSTR1_SubCategory.SUPECOM_9_5.value: {
                "20ALYPD6528PQC5": {
                    df.DOC_TYPE: GSTR1_SubCategory.SUPECOM_9_5.value,
                    df.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    df.TAXABLE_VALUE: 10000,
                    _if.IGST: 1000,
                    _if.CGST: 0,
                    _if.SGST: 0,
                    _if.CESS: 0,
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


class TestHSNSUMError(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                GovDataField.HSN_DATA.value: [
                    {
                        GovDataField.INDEX.value: 1,
                        GovDataField.HSN_CODE.value: "1010",
                        GovDataField.DESCRIPTION.value: "Goods Description",
                        GovDataField.UOM.value: "KGS",
                        GovDataField.QUANTITY.value: 2.05,
                        GovDataField.TAXABLE_VALUE.value: 10.23,
                        GovDataField.IGST.value: 14.52,
                        GovDataField.CESS.value: 500,
                        GovDataField.TAX_RATE.value: 0.1,
                    },
                ],
                GovDataField.ERROR_CD.value: "RET191350",
                GovDataField.ERROR_MSG.value: "Length of entered HSN code is not valid as per AATO",
            },
            {
                GovDataField.HSN_DATA.value: [
                    {
                        GovDataField.INDEX.value: 2,
                        GovDataField.HSN_CODE.value: "1011",
                        GovDataField.DESCRIPTION.value: "Goods Description",
                        GovDataField.UOM.value: "NOS",
                        GovDataField.QUANTITY.value: 2.05,
                        GovDataField.TAXABLE_VALUE.value: 10.23,
                        GovDataField.IGST.value: 14.52,
                        GovDataField.CESS.value: 500,
                        GovDataField.TAX_RATE.value: 5,
                    }
                ],
                GovDataField.ERROR_CD.value: "RET191350",
                GovDataField.ERROR_MSG.value: "Length of entered HSN code is not valid as per AATO",
            },
        ]

        cls.mapped_data = {
            GSTR1_SubCategory.HSN.value: {
                "1010 - KGS-KILOGRAMS - 0.1": {
                    df.DOC_TYPE: GSTR1_SubCategory.HSN.value,
                    df.HSN_CODE: "1010",
                    df.DESCRIPTION: "Goods Description",
                    df.UOM: "KGS-KILOGRAMS",
                    df.QUANTITY: 2.05,
                    df.TAXABLE_VALUE: 10.23,
                    df.IGST: 14.52,
                    df.CESS: 500,
                    df.TAX_RATE: 0.1,
                    df.DOC_VALUE: 524.75,
                    df.ERROR_CD: "RET191350",
                    df.ERROR_MSG: "Length of entered HSN code is not valid as per AATO",
                },
                "1011 - NOS-NUMBERS - 5.0": {
                    df.DOC_TYPE: GSTR1_SubCategory.HSN.value,
                    df.HSN_CODE: "1011",
                    df.DESCRIPTION: "Goods Description",
                    df.UOM: "NOS-NUMBERS",
                    df.QUANTITY: 2.05,
                    df.TAXABLE_VALUE: 10.23,
                    df.IGST: 14.52,
                    df.CESS: 500,
                    df.TAX_RATE: 5,
                    df.DOC_VALUE: 524.75,
                    df.ERROR_CD: "RET191350",
                    df.ERROR_MSG: "Length of entered HSN code is not valid as per AATO",
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = HSNSUM().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)
