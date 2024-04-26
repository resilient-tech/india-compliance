from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.utils import get_party_for_gstin as _get_party_for_gstin
from india_compliance.gst_india.utils.gstr_1 import (
    DataFields,
    GovDataFields,
    GSTR1_SubCategories,
    ItemFields,
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
    Exports,
    NilRated,
)


def get_party_for_gstin(gstin):
    return _get_party_for_gstin(gstin, "Customer") or "Unknown"


class TestB2B(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                GovDataFields.CUST_GSTIN.value: "24AANFA2641L1ZF",
                GovDataFields.INVOICES.value: [
                    {
                        GovDataFields.DOC_NUMBER.value: "S008400",
                        GovDataFields.DOC_DATE.value: "24-11-2016",
                        GovDataFields.DOC_VALUE.value: 729248.16,
                        GovDataFields.POS.value: "06",
                        GovDataFields.REVERSE_CHARGE.value: "N",
                        GovDataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                        GovDataFields.INVOICE_TYPE.value: "R",
                        GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.INDEX.value: 1,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CGST.value: 0,
                                    GovDataFields.SGST.value: 0,
                                    GovDataFields.CESS.value: 500,
                                },
                            },
                            {
                                GovDataFields.INDEX.value: 2,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CGST.value: 0,
                                    GovDataFields.SGST.value: 0,
                                    GovDataFields.CESS.value: 500,
                                },
                            },
                        ],
                    },
                    {
                        GovDataFields.DOC_NUMBER.value: "S008401",
                        GovDataFields.DOC_DATE.value: "24-11-2016",
                        GovDataFields.DOC_VALUE.value: 729248.16,
                        GovDataFields.POS.value: "06",
                        GovDataFields.REVERSE_CHARGE.value: "Y",
                        GovDataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                        GovDataFields.INVOICE_TYPE.value: "R",
                        GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.INDEX.value: 1,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CGST.value: 0,
                                    GovDataFields.SGST.value: 0,
                                    GovDataFields.CESS.value: 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                GovDataFields.CUST_GSTIN.value: "29AABCR1718E1ZL",
                GovDataFields.INVOICES.value: [
                    {
                        GovDataFields.DOC_NUMBER.value: "S008402",
                        GovDataFields.DOC_DATE.value: "24-11-2016",
                        GovDataFields.DOC_VALUE.value: 729248.16,
                        GovDataFields.POS.value: "06",
                        GovDataFields.REVERSE_CHARGE.value: "N",
                        GovDataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                        GovDataFields.INVOICE_TYPE.value: "SEZWP",
                        GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.INDEX.value: 1,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CGST.value: 0,
                                    GovDataFields.SGST.value: 0,
                                    GovDataFields.CESS.value: 500,
                                },
                            }
                        ],
                    },
                    {
                        GovDataFields.DOC_NUMBER.value: "S008403",
                        GovDataFields.DOC_DATE.value: "24-11-2016",
                        GovDataFields.DOC_VALUE.value: 729248.16,
                        GovDataFields.POS.value: "06",
                        GovDataFields.REVERSE_CHARGE.value: "N",
                        GovDataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                        GovDataFields.INVOICE_TYPE.value: "DE",
                        GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.INDEX.value: 1,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CGST.value: 0,
                                    GovDataFields.SGST.value: 0,
                                    GovDataFields.CESS.value: 500,
                                },
                            }
                        ],
                    },
                ],
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategories.B2B_REGULAR.value: {
                "S008400": {
                    DataFields.CUST_GSTIN.value: "24AANFA2641L1ZF",
                    DataFields.CUST_NAME.value: get_party_for_gstin("24AANFA2641L1ZF"),
                    DataFields.DOC_NUMBER.value: "S008400",
                    DataFields.DOC_DATE.value: "2016-11-24",
                    DataFields.DOC_VALUE.value: 729248.16,
                    DataFields.POS.value: "06-Haryana",
                    DataFields.REVERSE_CHARGE.value: "N",
                    DataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                    DataFields.DOC_TYPE.value: "Regular B2B",
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CGST.value: 0,
                            ItemFields.SGST.value: 0,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        },
                        {
                            ItemFields.INDEX.value: 2,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CGST.value: 0,
                            ItemFields.SGST.value: 0,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        },
                    ],
                    DataFields.TAXABLE_VALUE.value: 20000,
                    DataFields.IGST.value: 650,
                    DataFields.CGST.value: 0,
                    DataFields.SGST.value: 0,
                    DataFields.CESS.value: 1000,
                }
            },
            GSTR1_SubCategories.B2B_REVERSE_CHARGE.value: {
                "S008401": {
                    DataFields.CUST_GSTIN.value: "24AANFA2641L1ZF",
                    DataFields.CUST_NAME.value: get_party_for_gstin("24AANFA2641L1ZF"),
                    DataFields.DOC_NUMBER.value: "S008401",
                    DataFields.DOC_DATE.value: "2016-11-24",
                    DataFields.DOC_VALUE.value: 729248.16,
                    DataFields.POS.value: "06-Haryana",
                    DataFields.REVERSE_CHARGE.value: "Y",
                    DataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                    DataFields.DOC_TYPE.value: "Regular B2B",
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CGST.value: 0,
                            ItemFields.SGST.value: 0,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    DataFields.TAXABLE_VALUE.value: 10000,
                    DataFields.IGST.value: 325,
                    DataFields.CGST.value: 0,
                    DataFields.SGST.value: 0,
                    DataFields.CESS.value: 500,
                }
            },
            GSTR1_SubCategories.SEZWP.value: {
                "S008402": {
                    DataFields.CUST_GSTIN.value: "29AABCR1718E1ZL",
                    DataFields.CUST_NAME.value: get_party_for_gstin("29AABCR1718E1ZL"),
                    DataFields.DOC_NUMBER.value: "S008402",
                    DataFields.DOC_DATE.value: "2016-11-24",
                    DataFields.DOC_VALUE.value: 729248.16,
                    DataFields.POS.value: "06-Haryana",
                    DataFields.REVERSE_CHARGE.value: "N",
                    DataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                    DataFields.DOC_TYPE.value: "SEZ supplies with payment",
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CGST.value: 0,
                            ItemFields.SGST.value: 0,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    DataFields.TAXABLE_VALUE.value: 10000,
                    DataFields.IGST.value: 325,
                    DataFields.CGST.value: 0,
                    DataFields.SGST.value: 0,
                    DataFields.CESS.value: 500,
                }
            },
            GSTR1_SubCategories.DE.value: {
                "S008403": {
                    DataFields.CUST_GSTIN.value: "29AABCR1718E1ZL",
                    DataFields.CUST_NAME.value: get_party_for_gstin("29AABCR1718E1ZL"),
                    DataFields.DOC_NUMBER.value: "S008403",
                    DataFields.DOC_DATE.value: "2016-11-24",
                    DataFields.DOC_VALUE.value: 729248.16,
                    DataFields.POS.value: "06-Haryana",
                    DataFields.REVERSE_CHARGE.value: "N",
                    DataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                    DataFields.DOC_TYPE.value: "Deemed Exports",
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CGST.value: 0,
                            ItemFields.SGST.value: 0,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    DataFields.TAXABLE_VALUE.value: 10000,
                    DataFields.IGST.value: 325,
                    DataFields.CGST.value: 0,
                    DataFields.SGST.value: 0,
                    DataFields.CESS.value: 500,
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
                GovDataFields.POS.value: "05",
                GovDataFields.INVOICES.value: [
                    {
                        GovDataFields.DOC_NUMBER.value: "92661",
                        GovDataFields.DOC_DATE.value: "10-01-2016",
                        GovDataFields.DOC_VALUE.value: 784586.33,
                        GovDataFields.ECOMMERCE_GSTIN.value: "27AHQPA8875L1CU",
                        GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.INDEX.value: 1,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CESS.value: 500,
                                },
                            },
                            {
                                GovDataFields.INDEX.value: 2,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CESS.value: 500,
                                },
                            },
                        ],
                    },
                    {
                        GovDataFields.DOC_NUMBER.value: "92662",
                        GovDataFields.DOC_DATE.value: "10-01-2016",
                        GovDataFields.DOC_VALUE.value: 784586.33,
                        GovDataFields.ECOMMERCE_GSTIN.value: "27AHQPA8875L1CU",
                        GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.INDEX.value: 1,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CESS.value: 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                GovDataFields.POS.value: "24",
                GovDataFields.INVOICES.value: [
                    {
                        GovDataFields.DOC_NUMBER.value: "92663",
                        GovDataFields.DOC_DATE.value: "10-01-2016",
                        GovDataFields.DOC_VALUE.value: 784586.33,
                        GovDataFields.ECOMMERCE_GSTIN.value: "27AHQPA8875L1CU",
                        GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.INDEX.value: 1,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CESS.value: 500,
                                },
                            },
                            {
                                GovDataFields.INDEX.value: 2,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CESS.value: 500,
                                },
                            },
                        ],
                    },
                    {
                        GovDataFields.DOC_NUMBER.value: "92664",
                        GovDataFields.DOC_DATE.value: "10-01-2016",
                        GovDataFields.DOC_VALUE.value: 784586.33,
                        GovDataFields.ECOMMERCE_GSTIN.value: "27AHQPA8875L1CU",
                        GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.INDEX.value: 1,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 5,
                                    GovDataFields.TAXABLE_VALUE.value: 10000,
                                    GovDataFields.IGST.value: 325,
                                    GovDataFields.CESS.value: 500,
                                },
                            }
                        ],
                    },
                ],
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategories.B2CL.value: {
                "92661": {
                    DataFields.POS.value: "05-Uttarakhand",
                    DataFields.DOC_TYPE.value: "B2C (Large)",
                    DataFields.DOC_NUMBER.value: "92661",
                    DataFields.DOC_DATE.value: "2016-01-10",
                    DataFields.DOC_VALUE.value: 784586.33,
                    DataFields.ECOMMERCE_GSTIN.value: "27AHQPA8875L1CU",
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        },
                        {
                            ItemFields.INDEX.value: 2,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        },
                    ],
                    DataFields.TAXABLE_VALUE.value: 20000,
                    DataFields.IGST.value: 650,
                    DataFields.CESS.value: 1000,
                },
                "92662": {
                    DataFields.POS.value: "05-Uttarakhand",
                    DataFields.DOC_TYPE.value: "B2C (Large)",
                    DataFields.DOC_NUMBER.value: "92662",
                    DataFields.DOC_DATE.value: "2016-01-10",
                    DataFields.DOC_VALUE.value: 784586.33,
                    DataFields.ECOMMERCE_GSTIN.value: "27AHQPA8875L1CU",
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    DataFields.TAXABLE_VALUE.value: 10000,
                    DataFields.IGST.value: 325,
                    DataFields.CESS.value: 500,
                },
                "92663": {
                    DataFields.POS.value: "24-Gujarat",
                    DataFields.DOC_TYPE.value: "B2C (Large)",
                    DataFields.DOC_NUMBER.value: "92663",
                    DataFields.DOC_DATE.value: "2016-01-10",
                    DataFields.DOC_VALUE.value: 784586.33,
                    DataFields.ECOMMERCE_GSTIN.value: "27AHQPA8875L1CU",
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        },
                        {
                            ItemFields.INDEX.value: 2,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        },
                    ],
                    DataFields.TAXABLE_VALUE.value: 20000,
                    DataFields.IGST.value: 650,
                    DataFields.CESS.value: 1000,
                },
                "92664": {
                    DataFields.POS.value: "24-Gujarat",
                    DataFields.DOC_TYPE.value: "B2C (Large)",
                    DataFields.DOC_NUMBER.value: "92664",
                    DataFields.DOC_DATE.value: "2016-01-10",
                    DataFields.DOC_VALUE.value: 784586.33,
                    DataFields.ECOMMERCE_GSTIN.value: "27AHQPA8875L1CU",
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 325,
                            ItemFields.CESS.value: 500,
                            DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    DataFields.TAXABLE_VALUE.value: 10000,
                    DataFields.IGST.value: 325,
                    DataFields.CESS.value: 500,
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
                GovDataFields.EXPORT_TYPE.value: "WPAY",
                GovDataFields.INVOICES.value: [
                    {
                        GovDataFields.DOC_NUMBER.value: "81542",
                        GovDataFields.DOC_DATE.value: "12-02-2016",
                        GovDataFields.DOC_VALUE.value: 995048.36,
                        GovDataFields.SHIPPING_PORT_CODE.value: "ASB991",
                        GovDataFields.SHIPPING_BILL_NUMBER.value: "7896542",
                        GovDataFields.SHIPPING_BILL_DATE.value: "04-10-2016",
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.TAXABLE_VALUE.value: 10000,
                                GovDataFields.TAX_RATE.value: 5,
                                GovDataFields.IGST.value: 833.33,
                                GovDataFields.CESS.value: 100,
                            }
                        ],
                    }
                ],
            },
            {
                GovDataFields.EXPORT_TYPE.value: "WOPAY",
                GovDataFields.INVOICES.value: [
                    {
                        GovDataFields.DOC_NUMBER.value: "81543",
                        GovDataFields.DOC_DATE.value: "12-02-2016",
                        GovDataFields.DOC_VALUE.value: 995048.36,
                        GovDataFields.SHIPPING_PORT_CODE.value: "ASB981",
                        GovDataFields.SHIPPING_BILL_NUMBER.value: "7896542",
                        GovDataFields.SHIPPING_BILL_DATE.value: "04-10-2016",
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.TAXABLE_VALUE.value: 10000,
                                GovDataFields.TAX_RATE.value: 0,
                                GovDataFields.IGST.value: 0,
                                GovDataFields.CESS.value: 100,
                            }
                        ],
                    }
                ],
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategories.EXPWP.value: {
                "81542": {
                    DataFields.DOC_TYPE.value: "WPAY",
                    DataFields.DOC_NUMBER.value: "81542",
                    DataFields.DOC_DATE.value: "2016-02-12",
                    DataFields.DOC_VALUE.value: 995048.36,
                    DataFields.SHIPPING_PORT_CODE.value: "ASB991",
                    DataFields.SHIPPING_BILL_NUMBER.value: "7896542",
                    DataFields.SHIPPING_BILL_DATE.value: "2016-10-04",
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 833.33,
                            ItemFields.CESS.value: 100,
                            DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    DataFields.TAXABLE_VALUE.value: 10000,
                    DataFields.IGST.value: 833.33,
                    DataFields.CESS.value: 100,
                }
            },
            GSTR1_SubCategories.EXPWOP.value: {
                "81543": {
                    DataFields.DOC_TYPE.value: "WOPAY",
                    DataFields.DOC_NUMBER.value: "81543",
                    DataFields.DOC_DATE.value: "2016-02-12",
                    DataFields.DOC_VALUE.value: 995048.36,
                    DataFields.SHIPPING_PORT_CODE.value: "ASB981",
                    DataFields.SHIPPING_BILL_NUMBER.value: "7896542",
                    DataFields.SHIPPING_BILL_DATE.value: "2016-10-04",
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.TAXABLE_VALUE.value: 10000,
                            ItemFields.IGST.value: 0,
                            ItemFields.CESS.value: 100,
                            DataFields.TAX_RATE.value: 0,
                        }
                    ],
                    DataFields.TAXABLE_VALUE.value: 10000,
                    DataFields.IGST.value: 0,
                    DataFields.CESS.value: 100,
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
                GovDataFields.SUPPLY_TYPE.value: "INTER",
                GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                GovDataFields.TAX_RATE.value: 5,
                GovDataFields.TYPE.value: "E",
                GovDataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                GovDataFields.POS.value: "05",
                GovDataFields.TAXABLE_VALUE.value: 110,
                GovDataFields.IGST.value: 10,
                GovDataFields.CGST.value: 0,
                GovDataFields.SGST.value: 0,
                GovDataFields.CESS.value: 10,
            },
            {
                GovDataFields.SUPPLY_TYPE.value: "INTER",
                GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                GovDataFields.TAX_RATE.value: 5,
                GovDataFields.TYPE.value: "OE",
                GovDataFields.TAXABLE_VALUE.value: 100,
                GovDataFields.IGST.value: 10,
                GovDataFields.CGST.value: 0,
                GovDataFields.SGST.value: 0,
                GovDataFields.CESS.value: 10,
                GovDataFields.POS.value: "05",
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategories.B2CS.value: {
                "05-Uttarakhand - 5.0 - 01AABCE5507R1C4": [
                    {
                        ItemFields.TAXABLE_VALUE.value: 110,
                        DataFields.DOC_TYPE.value: "E",
                        DataFields.ECOMMERCE_GSTIN.value: "01AABCE5507R1C4",
                        DataFields.DIFF_PERCENTAGE.value: 0.65,
                        DataFields.POS.value: "05-Uttarakhand",
                        DataFields.TAX_RATE.value: 5,
                        ItemFields.IGST.value: 10,
                        ItemFields.CESS.value: 10,
                        ItemFields.CGST.value: 0,
                        ItemFields.SGST.value: 0,
                    },
                ],
                "05-Uttarakhand - 5.0 - ": [
                    {
                        ItemFields.TAXABLE_VALUE.value: 100,
                        DataFields.DOC_TYPE.value: "OE",
                        DataFields.DIFF_PERCENTAGE.value: 0.65,
                        DataFields.POS.value: "05-Uttarakhand",
                        DataFields.TAX_RATE.value: 5,
                        ItemFields.IGST.value: 10,
                        ItemFields.CESS.value: 10,
                        ItemFields.CGST.value: 0,
                        ItemFields.SGST.value: 0,
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
            GovDataFields.INVOICES.value: [
                {
                    GovDataFields.SUPPLY_TYPE.value: "INTRB2B",
                    GovDataFields.EXEMPTED_AMOUNT.value: 123.45,
                    GovDataFields.NIL_RATED_AMOUNT.value: 1470.85,
                    GovDataFields.NON_GST_AMOUNT.value: 1258.5,
                },
                {
                    GovDataFields.SUPPLY_TYPE.value: "INTRB2C",
                    GovDataFields.EXEMPTED_AMOUNT.value: 123.45,
                    GovDataFields.NIL_RATED_AMOUNT.value: 1470.85,
                    GovDataFields.NON_GST_AMOUNT.value: 1258.5,
                },
            ]
        }

        cls.mapped_data = {
            GSTR1_SubCategories.NIL_EXEMPT.value: {
                "Inter-State supplies to registered persons": [
                    {
                        DataFields.DOC_TYPE.value: "Inter-State supplies to registered persons",
                        DataFields.EXEMPTED_AMOUNT.value: 123.45,
                        DataFields.NIL_RATED_AMOUNT.value: 1470.85,
                        DataFields.NON_GST_AMOUNT.value: 1258.5,
                        DataFields.TAXABLE_VALUE.value: 2852.8,
                    }
                ],
                "Inter-State supplies to unregistered persons": [
                    {
                        DataFields.DOC_TYPE.value: "Inter-State supplies to unregistered persons",
                        DataFields.EXEMPTED_AMOUNT.value: 123.45,
                        DataFields.NIL_RATED_AMOUNT.value: 1470.85,
                        DataFields.NON_GST_AMOUNT.value: 1258.5,
                        DataFields.TAXABLE_VALUE.value: 2852.8,
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
                GovDataFields.CUST_GSTIN.value: "24AANFA2641L1ZF",
                GovDataFields.NOTE_DETAILS.value: [
                    {
                        GovDataFields.NOTE_TYPE.value: "C",
                        GovDataFields.NOTE_NUMBER.value: "533515",
                        GovDataFields.NOTE_DATE.value: "23-09-2016",
                        GovDataFields.POS.value: "03",
                        GovDataFields.REVERSE_CHARGE.value: "Y",
                        GovDataFields.INVOICE_TYPE.value: "DE",
                        GovDataFields.DOC_VALUE.value: 123123,
                        GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                        GovDataFields.ITEMS.value: [
                            {
                                GovDataFields.INDEX.value: 1,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 10,
                                    GovDataFields.TAXABLE_VALUE.value: 5225.28,
                                    GovDataFields.SGST.value: 0,
                                    GovDataFields.CGST.value: 0,
                                    GovDataFields.IGST.value: 339.64,
                                    GovDataFields.CESS.value: 789.52,
                                },
                            },
                            {
                                GovDataFields.INDEX.value: 2,
                                GovDataFields.ITEM_DETAILS.value: {
                                    GovDataFields.TAX_RATE.value: 10,
                                    GovDataFields.TAXABLE_VALUE.value: 5225.28,
                                    GovDataFields.SGST.value: 0,
                                    GovDataFields.CGST.value: 0,
                                    GovDataFields.IGST.value: 339.64,
                                    GovDataFields.CESS.value: 789.52,
                                },
                            },
                        ],
                    },
                ],
            }
        ]
        cls.mappped_data = {
            GSTR1_SubCategories.CDNR.value: {
                "533515": {
                    DataFields.CUST_GSTIN.value: "24AANFA2641L1ZF",
                    DataFields.CUST_NAME.value: get_party_for_gstin("24AANFA2641L1ZF"),
                    DataFields.TRANSACTION_TYPE.value: "Credit Note",
                    DataFields.DOC_NUMBER.value: "533515",
                    DataFields.DOC_DATE.value: "2016-09-23",
                    DataFields.POS.value: "03-Punjab",
                    DataFields.REVERSE_CHARGE.value: "Y",
                    DataFields.DOC_TYPE.value: "Deemed Exports",
                    DataFields.DOC_VALUE.value: -123123,
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: -5225.28,
                            ItemFields.IGST.value: -339.64,
                            ItemFields.CGST.value: 0,
                            ItemFields.SGST.value: 0,
                            ItemFields.CESS.value: -789.52,
                            DataFields.TAX_RATE.value: 10,
                        },
                        {
                            ItemFields.INDEX.value: 2,
                            ItemFields.TAXABLE_VALUE.value: -5225.28,
                            ItemFields.IGST.value: -339.64,
                            ItemFields.CGST.value: 0,
                            ItemFields.SGST.value: 0,
                            ItemFields.CESS.value: -789.52,
                            DataFields.TAX_RATE.value: 10,
                        },
                    ],
                    DataFields.TAXABLE_VALUE.value: -10450.56,
                    DataFields.IGST.value: -679.28,
                    DataFields.CGST.value: 0,
                    DataFields.SGST.value: 0,
                    DataFields.CESS.value: -1579.04,
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
                GovDataFields.TYPE.value: "B2CL",
                GovDataFields.NOTE_TYPE.value: "C",
                GovDataFields.NOTE_NUMBER.value: "533515",
                GovDataFields.NOTE_DATE.value: "23-09-2016",
                GovDataFields.POS.value: "03",
                GovDataFields.DOC_VALUE.value: 64646,
                GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                GovDataFields.ITEMS.value: [
                    {
                        GovDataFields.INDEX.value: 1,
                        GovDataFields.ITEM_DETAILS.value: {
                            GovDataFields.TAX_RATE.value: 10,
                            GovDataFields.TAXABLE_VALUE.value: 5225.28,
                            GovDataFields.IGST.value: 339.64,
                            GovDataFields.CESS.value: 789.52,
                        },
                    }
                ],
            }
        ]

        cls.mapped_data = {
            GSTR1_SubCategories.CDNUR.value: {
                "533515": {
                    DataFields.TRANSACTION_TYPE.value: "Credit Note",
                    DataFields.DOC_TYPE.value: "B2CL",
                    DataFields.DOC_NUMBER.value: "533515",
                    DataFields.DOC_DATE.value: "2016-09-23",
                    DataFields.DOC_VALUE.value: -64646,
                    DataFields.POS.value: "03-Punjab",
                    DataFields.DIFF_PERCENTAGE.value: 0.65,
                    DataFields.ITEMS.value: [
                        {
                            ItemFields.INDEX.value: 1,
                            ItemFields.TAXABLE_VALUE.value: -5225.28,
                            ItemFields.IGST.value: -339.64,
                            ItemFields.CESS.value: -789.52,
                            DataFields.TAX_RATE.value: 10,
                        }
                    ],
                    DataFields.TAXABLE_VALUE.value: -5225.28,
                    DataFields.IGST.value: -339.64,
                    DataFields.CESS.value: -789.52,
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
            GovDataFields.HSN_DATA.value: [
                {
                    GovDataFields.INDEX.value: 1,
                    GovDataFields.HSN_CODE.value: "1010",
                    GovDataFields.DESCRIPTION.value: "Goods Description",
                    GovDataFields.UOM.value: "KGS",
                    GovDataFields.QUANTITY.value: 2.05,
                    GovDataFields.TAXABLE_VALUE.value: 10.23,
                    GovDataFields.IGST.value: 14.52,
                    GovDataFields.CESS.value: 500,
                    GovDataFields.TAX_RATE.value: 0.1,
                },
                {
                    GovDataFields.INDEX.value: 1,
                    GovDataFields.HSN_CODE.value: "999512",
                    GovDataFields.DESCRIPTION.value: "Goods Description",
                    GovDataFields.UOM.value: "NOS",
                    GovDataFields.QUANTITY.value: 2.05,
                    GovDataFields.TAXABLE_VALUE.value: 10.23,
                    GovDataFields.IGST.value: 14.52,
                    GovDataFields.CESS.value: 500,
                    GovDataFields.TAX_RATE.value: 5.0,
                },
            ]
        }

        cls.mapped_data = {
            GSTR1_SubCategories.HSN.value: {
                "1010 - KGS-KILOGRAMS - 0.1": {
                    ItemFields.INDEX.value: 1,
                    DataFields.HSN_CODE.value: "1010",
                    DataFields.DESCRIPTION.value: "Goods Description",
                    DataFields.UOM.value: "KGS-KILOGRAMS",
                    DataFields.QUANTITY.value: 2.05,
                    DataFields.TAXABLE_VALUE.value: 10.23,
                    DataFields.IGST.value: 14.52,
                    DataFields.CESS.value: 500,
                    DataFields.TAX_RATE.value: 0.1,
                },
                "999512 - NOS-NUMBERS - 5.0": {
                    ItemFields.INDEX.value: 1,
                    DataFields.HSN_CODE.value: "999512",
                    DataFields.DESCRIPTION.value: "Goods Description",
                    DataFields.UOM.value: "NOS-NUMBERS",
                    DataFields.QUANTITY.value: 2.05,
                    DataFields.TAXABLE_VALUE.value: 10.23,
                    DataFields.IGST.value: 14.52,
                    DataFields.CESS.value: 500,
                    DataFields.TAX_RATE.value: 5,
                },
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
                GovDataFields.POS.value: "05",
                GovDataFields.SUPPLY_TYPE.value: "INTER",
                GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                GovDataFields.ITEMS.value: [
                    {
                        GovDataFields.TAX_RATE.value: 5,
                        GovDataFields.ADDITIONAL_AMOUNT.value: 100,
                        GovDataFields.IGST.value: 9400,
                        GovDataFields.CGST.value: 0,
                        GovDataFields.SGST.value: 0,
                        GovDataFields.CESS.value: 500,
                    },
                    {
                        GovDataFields.TAX_RATE.value: 6,
                        GovDataFields.ADDITIONAL_AMOUNT.value: 100,
                        GovDataFields.IGST.value: 9400,
                        GovDataFields.CGST.value: 0,
                        GovDataFields.SGST.value: 0,
                        GovDataFields.CESS.value: 500,
                    },
                ],
            },
            {
                GovDataFields.POS.value: "24",
                GovDataFields.SUPPLY_TYPE.value: "INTER",
                GovDataFields.DIFF_PERCENTAGE.value: 0.65,
                GovDataFields.ITEMS.value: [
                    {
                        GovDataFields.TAX_RATE.value: 5,
                        GovDataFields.ADDITIONAL_AMOUNT.value: 100,
                        GovDataFields.IGST.value: 9400,
                        GovDataFields.CGST.value: 0,
                        GovDataFields.SGST.value: 0,
                        GovDataFields.CESS.value: 500,
                    },
                    {
                        GovDataFields.TAX_RATE.value: 6,
                        GovDataFields.ADDITIONAL_AMOUNT.value: 100,
                        GovDataFields.IGST.value: 9400,
                        GovDataFields.CGST.value: 0,
                        GovDataFields.SGST.value: 0,
                        GovDataFields.CESS.value: 500,
                    },
                ],
            },
        ]

        cls.mapped_data = {
            GSTR1_SubCategories.AT.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        DataFields.POS.value: "05-Uttarakhand",
                        DataFields.DIFF_PERCENTAGE.value: 0.65,
                        DataFields.IGST.value: 9400,
                        DataFields.CESS.value: 500,
                        DataFields.CGST.value: 0,
                        DataFields.SGST.value: 0,
                        DataFields.TAXABLE_VALUE.value: 100,
                        DataFields.TAX_RATE.value: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        DataFields.POS.value: "05-Uttarakhand",
                        DataFields.DIFF_PERCENTAGE.value: 0.65,
                        DataFields.IGST.value: 9400,
                        DataFields.CESS.value: 500,
                        DataFields.CGST.value: 0,
                        DataFields.SGST.value: 0,
                        DataFields.TAXABLE_VALUE.value: 100,
                        DataFields.TAX_RATE.value: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        DataFields.POS.value: "24-Gujarat",
                        DataFields.DIFF_PERCENTAGE.value: 0.65,
                        DataFields.IGST.value: 9400,
                        DataFields.CESS.value: 500,
                        DataFields.CGST.value: 0,
                        DataFields.SGST.value: 0,
                        DataFields.TAXABLE_VALUE.value: 100,
                        DataFields.TAX_RATE.value: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        DataFields.POS.value: "24-Gujarat",
                        DataFields.DIFF_PERCENTAGE.value: 0.65,
                        DataFields.IGST.value: 9400,
                        DataFields.CESS.value: 500,
                        DataFields.CGST.value: 0,
                        DataFields.SGST.value: 0,
                        DataFields.TAXABLE_VALUE.value: 100,
                        DataFields.TAX_RATE.value: 6,
                    }
                ],
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
            GovDataFields.DOC_ISSUE_DETAILS.value: [
                {
                    GovDataFields.DOC_ISSUE_NUMBER.value: 1,
                    GovDataFields.DOC_ISSUE_LIST.value: [
                        {
                            GovDataFields.INDEX.value: 1,
                            GovDataFields.FROM_SR.value: "1",
                            GovDataFields.TO_SR.value: "10",
                            GovDataFields.TOTAL_COUNT.value: 10,
                            GovDataFields.CANCELLED_COUNT.value: 0,
                            GovDataFields.NET_ISSUE.value: 10,
                        },
                        {
                            GovDataFields.INDEX.value: 2,
                            GovDataFields.FROM_SR.value: "11",
                            GovDataFields.TO_SR.value: "20",
                            GovDataFields.TOTAL_COUNT.value: 10,
                            GovDataFields.CANCELLED_COUNT.value: 0,
                            GovDataFields.NET_ISSUE.value: 10,
                        },
                    ],
                },
                {
                    GovDataFields.DOC_ISSUE_NUMBER.value: 2,
                    GovDataFields.DOC_ISSUE_LIST.value: [
                        {
                            GovDataFields.INDEX.value: 1,
                            GovDataFields.FROM_SR.value: "1",
                            GovDataFields.TO_SR.value: "10",
                            GovDataFields.TOTAL_COUNT.value: 10,
                            GovDataFields.CANCELLED_COUNT.value: 0,
                            GovDataFields.NET_ISSUE.value: 10,
                        },
                        {
                            GovDataFields.INDEX.value: 2,
                            GovDataFields.FROM_SR.value: "11",
                            GovDataFields.TO_SR.value: "20",
                            GovDataFields.TOTAL_COUNT.value: 10,
                            GovDataFields.CANCELLED_COUNT.value: 0,
                            GovDataFields.NET_ISSUE.value: 10,
                        },
                    ],
                },
            ]
        }
        cls.mapped_data = {
            GSTR1_SubCategories.DOC_ISSUE.value: {
                "Invoices for outward supply - 1": {
                    DataFields.DOCUMENT_NATURE.value: "Invoices for outward supply",
                    ItemFields.INDEX.value: 1,
                    DataFields.FROM_SR.value: "1",
                    DataFields.TO_SR.value: "10",
                    DataFields.TOTAL_COUNT.value: 10,
                    DataFields.CANCELLED_COUNT.value: 0,
                },
                "Invoices for outward supply - 11": {
                    DataFields.DOCUMENT_NATURE.value: "Invoices for outward supply",
                    ItemFields.INDEX.value: 2,
                    DataFields.FROM_SR.value: "11",
                    DataFields.TO_SR.value: "20",
                    DataFields.TOTAL_COUNT.value: 10,
                    DataFields.CANCELLED_COUNT.value: 0,
                },
                "Invoices for inward supply from unregistered person - 1": {
                    DataFields.DOCUMENT_NATURE.value: "Invoices for inward supply from unregistered person",
                    ItemFields.INDEX.value: 1,
                    DataFields.FROM_SR.value: "1",
                    DataFields.TO_SR.value: "10",
                    DataFields.TOTAL_COUNT.value: 10,
                    DataFields.CANCELLED_COUNT.value: 0,
                },
                "Invoices for inward supply from unregistered person - 11": {
                    DataFields.DOCUMENT_NATURE.value: "Invoices for inward supply from unregistered person",
                    ItemFields.INDEX.value: 2,
                    DataFields.FROM_SR.value: "11",
                    DataFields.TO_SR.value: "20",
                    DataFields.TOTAL_COUNT.value: 10,
                    DataFields.CANCELLED_COUNT.value: 0,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = DOC_ISSUE().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = DOC_ISSUE().convert_to_gov_data_format(self.mapped_data)
        self.assertDictEqual(self.json_data, output)


class TestSUPECOM(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            GovDataFields.SUPECOM_52.value: [
                {
                    GovDataFields.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    GovDataFields.SUPPLIER_VALUE.value: 10000,
                    "igst": 1000,
                    "cgst": 0,
                    "sgst": 0,
                    "cess": 0,
                }
            ],
            GovDataFields.SUPECOM_9_5.value: [
                {
                    GovDataFields.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    GovDataFields.SUPPLIER_VALUE.value: 10000,
                    "igst": 1000,
                    "cgst": 0,
                    "sgst": 0,
                    "cess": 0,
                }
            ],
        }

        cls.mapped_data = {
            GSTR1_SubCategories.SUPECOM_52.value: {
                "20ALYPD6528PQC5": {
                    DataFields.DOC_TYPE.value: GSTR1_SubCategories.SUPECOM_52.value,
                    DataFields.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    DataFields.SUPPLIER_VALUE.value: 10000,
                    ItemFields.IGST.value: 1000,
                    ItemFields.CGST.value: 0,
                    ItemFields.SGST.value: 0,
                    ItemFields.CESS.value: 0,
                }
            },
            GSTR1_SubCategories.SUPECOM_9_5.value: {
                "20ALYPD6528PQC5": {
                    DataFields.DOC_TYPE.value: GSTR1_SubCategories.SUPECOM_9_5.value,
                    DataFields.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    DataFields.SUPPLIER_VALUE.value: 10000,
                    ItemFields.IGST.value: 1000,
                    ItemFields.CGST.value: 0,
                    ItemFields.SGST.value: 0,
                    ItemFields.CESS.value: 0,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = SUPECOM().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = SUPECOM().convert_to_gov_data_format(self.mapped_data)
        self.assertDictEqual(self.json_data, output)
