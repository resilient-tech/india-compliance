from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.utils import get_party_for_gstin as _get_party_for_gstin
from india_compliance.gst_india.utils.gstr_1 import (
    GovDataFields,
    GSTR1_B2B_InvoiceTypes,
    GSTR1_DataFields,
    GSTR1_ItemFields,
    GSTR1_SubCategories,
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
                        GovDataFields.INVOICE_TYPE.value: "SEWP",
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
                    GSTR1_DataFields.CUST_GSTIN.value: "24AANFA2641L1ZF",
                    GSTR1_DataFields.CUST_NAME.value: get_party_for_gstin(
                        "24AANFA2641L1ZF"
                    ),
                    GSTR1_DataFields.DOC_NUMBER.value: "S008400",
                    GSTR1_DataFields.DOC_DATE.value: "2016-11-24",
                    GSTR1_DataFields.DOC_VALUE.value: 729248.16,
                    GSTR1_DataFields.POS.value: "06-Haryana",
                    GSTR1_DataFields.REVERSE_CHARGE.value: "N",
                    GSTR1_DataFields.DOC_TYPE.value: GSTR1_B2B_InvoiceTypes.R.value,
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CGST.value: 0,
                            GSTR1_ItemFields.SGST.value: 0,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        },
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CGST.value: 0,
                            GSTR1_ItemFields.SGST.value: 0,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        },
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 20000,
                    GSTR1_DataFields.IGST.value: 650,
                    GSTR1_DataFields.CGST.value: 0,
                    GSTR1_DataFields.SGST.value: 0,
                    GSTR1_DataFields.CESS.value: 1000,
                }
            },
            GSTR1_SubCategories.B2B_REVERSE_CHARGE.value: {
                "S008401": {
                    GSTR1_DataFields.CUST_GSTIN.value: "24AANFA2641L1ZF",
                    GSTR1_DataFields.CUST_NAME.value: get_party_for_gstin(
                        "24AANFA2641L1ZF"
                    ),
                    GSTR1_DataFields.DOC_NUMBER.value: "S008401",
                    GSTR1_DataFields.DOC_DATE.value: "2016-11-24",
                    GSTR1_DataFields.DOC_VALUE.value: 729248.16,
                    GSTR1_DataFields.POS.value: "06-Haryana",
                    GSTR1_DataFields.REVERSE_CHARGE.value: "Y",
                    GSTR1_DataFields.DOC_TYPE.value: GSTR1_B2B_InvoiceTypes.R.value,
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CGST.value: 0,
                            GSTR1_ItemFields.SGST.value: 0,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataFields.IGST.value: 325,
                    GSTR1_DataFields.CGST.value: 0,
                    GSTR1_DataFields.SGST.value: 0,
                    GSTR1_DataFields.CESS.value: 500,
                }
            },
            GSTR1_SubCategories.SEZWP.value: {
                "S008402": {
                    GSTR1_DataFields.CUST_GSTIN.value: "29AABCR1718E1ZL",
                    GSTR1_DataFields.CUST_NAME.value: get_party_for_gstin(
                        "29AABCR1718E1ZL"
                    ),
                    GSTR1_DataFields.DOC_NUMBER.value: "S008402",
                    GSTR1_DataFields.DOC_DATE.value: "2016-11-24",
                    GSTR1_DataFields.DOC_VALUE.value: 729248.16,
                    GSTR1_DataFields.POS.value: "06-Haryana",
                    GSTR1_DataFields.REVERSE_CHARGE.value: "N",
                    GSTR1_DataFields.DOC_TYPE.value: GSTR1_B2B_InvoiceTypes.SEWP.value,
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CGST.value: 0,
                            GSTR1_ItemFields.SGST.value: 0,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataFields.IGST.value: 325,
                    GSTR1_DataFields.CGST.value: 0,
                    GSTR1_DataFields.SGST.value: 0,
                    GSTR1_DataFields.CESS.value: 500,
                }
            },
            GSTR1_SubCategories.DE.value: {
                "S008403": {
                    GSTR1_DataFields.CUST_GSTIN.value: "29AABCR1718E1ZL",
                    GSTR1_DataFields.CUST_NAME.value: get_party_for_gstin(
                        "29AABCR1718E1ZL"
                    ),
                    GSTR1_DataFields.DOC_NUMBER.value: "S008403",
                    GSTR1_DataFields.DOC_DATE.value: "2016-11-24",
                    GSTR1_DataFields.DOC_VALUE.value: 729248.16,
                    GSTR1_DataFields.POS.value: "06-Haryana",
                    GSTR1_DataFields.REVERSE_CHARGE.value: "N",
                    GSTR1_DataFields.DOC_TYPE.value: GSTR1_B2B_InvoiceTypes.DE.value,
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CGST.value: 0,
                            GSTR1_ItemFields.SGST.value: 0,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataFields.IGST.value: 325,
                    GSTR1_DataFields.CGST.value: 0,
                    GSTR1_DataFields.SGST.value: 0,
                    GSTR1_DataFields.CESS.value: 500,
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
                    GSTR1_DataFields.POS.value: "05-Uttarakhand",
                    GSTR1_DataFields.DOC_TYPE.value: "B2C (Large)",
                    GSTR1_DataFields.DOC_NUMBER.value: "92661",
                    GSTR1_DataFields.DOC_DATE.value: "2016-01-10",
                    GSTR1_DataFields.DOC_VALUE.value: 784586.33,
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        },
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        },
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 20000,
                    GSTR1_DataFields.IGST.value: 650,
                    GSTR1_DataFields.CESS.value: 1000,
                },
                "92662": {
                    GSTR1_DataFields.POS.value: "05-Uttarakhand",
                    GSTR1_DataFields.DOC_TYPE.value: "B2C (Large)",
                    GSTR1_DataFields.DOC_NUMBER.value: "92662",
                    GSTR1_DataFields.DOC_DATE.value: "2016-01-10",
                    GSTR1_DataFields.DOC_VALUE.value: 784586.33,
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataFields.IGST.value: 325,
                    GSTR1_DataFields.CESS.value: 500,
                },
                "92663": {
                    GSTR1_DataFields.POS.value: "24-Gujarat",
                    GSTR1_DataFields.DOC_TYPE.value: "B2C (Large)",
                    GSTR1_DataFields.DOC_NUMBER.value: "92663",
                    GSTR1_DataFields.DOC_DATE.value: "2016-01-10",
                    GSTR1_DataFields.DOC_VALUE.value: 784586.33,
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        },
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        },
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 20000,
                    GSTR1_DataFields.IGST.value: 650,
                    GSTR1_DataFields.CESS.value: 1000,
                },
                "92664": {
                    GSTR1_DataFields.POS.value: "24-Gujarat",
                    GSTR1_DataFields.DOC_TYPE.value: "B2C (Large)",
                    GSTR1_DataFields.DOC_NUMBER.value: "92664",
                    GSTR1_DataFields.DOC_DATE.value: "2016-01-10",
                    GSTR1_DataFields.DOC_VALUE.value: 784586.33,
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 325,
                            GSTR1_ItemFields.CESS.value: 500,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataFields.IGST.value: 325,
                    GSTR1_DataFields.CESS.value: 500,
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
                    GSTR1_DataFields.DOC_TYPE.value: "WPAY",
                    GSTR1_DataFields.DOC_NUMBER.value: "81542",
                    GSTR1_DataFields.DOC_DATE.value: "2016-02-12",
                    GSTR1_DataFields.DOC_VALUE.value: 995048.36,
                    GSTR1_DataFields.SHIPPING_PORT_CODE.value: "ASB991",
                    GSTR1_DataFields.SHIPPING_BILL_NUMBER.value: "7896542",
                    GSTR1_DataFields.SHIPPING_BILL_DATE.value: "2016-10-04",
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 833.33,
                            GSTR1_ItemFields.CESS.value: 100,
                            GSTR1_DataFields.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataFields.IGST.value: 833.33,
                    GSTR1_DataFields.CESS.value: 100,
                }
            },
            GSTR1_SubCategories.EXPWOP.value: {
                "81543": {
                    GSTR1_DataFields.DOC_TYPE.value: "WOPAY",
                    GSTR1_DataFields.DOC_NUMBER.value: "81543",
                    GSTR1_DataFields.DOC_DATE.value: "2016-02-12",
                    GSTR1_DataFields.DOC_VALUE.value: 995048.36,
                    GSTR1_DataFields.SHIPPING_PORT_CODE.value: "ASB981",
                    GSTR1_DataFields.SHIPPING_BILL_NUMBER.value: "7896542",
                    GSTR1_DataFields.SHIPPING_BILL_DATE.value: "2016-10-04",
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemFields.IGST.value: 0,
                            GSTR1_ItemFields.CESS.value: 100,
                            GSTR1_DataFields.TAX_RATE.value: 0,
                        }
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataFields.IGST.value: 0,
                    GSTR1_DataFields.CESS.value: 100,
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
                GovDataFields.TYPE.value: "OE",
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
                GovDataFields.POS.value: "06",
            },
        ]
        cls.mapped_data = {
            GSTR1_SubCategories.B2CS.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        GSTR1_DataFields.TAXABLE_VALUE.value: 110,
                        GSTR1_DataFields.DOC_TYPE.value: "OE",
                        GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataFields.POS.value: "05-Uttarakhand",
                        GSTR1_DataFields.TAX_RATE.value: 5,
                        GSTR1_DataFields.IGST.value: 10,
                        GSTR1_DataFields.CESS.value: 10,
                        GSTR1_DataFields.CGST.value: 0,
                        GSTR1_DataFields.SGST.value: 0,
                    },
                ],
                "06-Haryana - 5.0": [
                    {
                        GSTR1_DataFields.TAXABLE_VALUE.value: 100,
                        GSTR1_DataFields.DOC_TYPE.value: "OE",
                        GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataFields.POS.value: "06-Haryana",
                        GSTR1_DataFields.TAX_RATE.value: 5,
                        GSTR1_DataFields.IGST.value: 10,
                        GSTR1_DataFields.CESS.value: 10,
                        GSTR1_DataFields.CGST.value: 0,
                        GSTR1_DataFields.SGST.value: 0,
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
                        GSTR1_DataFields.DOC_TYPE.value: "Inter-State supplies to registered persons",
                        GSTR1_DataFields.EXEMPTED_AMOUNT.value: 123.45,
                        GSTR1_DataFields.NIL_RATED_AMOUNT.value: 1470.85,
                        GSTR1_DataFields.NON_GST_AMOUNT.value: 1258.5,
                        GSTR1_DataFields.TAXABLE_VALUE.value: 2852.8,
                    }
                ],
                "Inter-State supplies to unregistered persons": [
                    {
                        GSTR1_DataFields.DOC_TYPE.value: "Inter-State supplies to unregistered persons",
                        GSTR1_DataFields.EXEMPTED_AMOUNT.value: 123.45,
                        GSTR1_DataFields.NIL_RATED_AMOUNT.value: 1470.85,
                        GSTR1_DataFields.NON_GST_AMOUNT.value: 1258.5,
                        GSTR1_DataFields.TAXABLE_VALUE.value: 2852.8,
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
                    GSTR1_DataFields.CUST_GSTIN.value: "24AANFA2641L1ZF",
                    GSTR1_DataFields.CUST_NAME.value: get_party_for_gstin(
                        "24AANFA2641L1ZF"
                    ),
                    GSTR1_DataFields.TRANSACTION_TYPE.value: "Credit Note",
                    GSTR1_DataFields.DOC_NUMBER.value: "533515",
                    GSTR1_DataFields.DOC_DATE.value: "2016-09-23",
                    GSTR1_DataFields.POS.value: "03-Punjab",
                    GSTR1_DataFields.REVERSE_CHARGE.value: "Y",
                    GSTR1_DataFields.DOC_TYPE.value: "Deemed Exports",
                    GSTR1_DataFields.DOC_VALUE.value: -123123,
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: -5225.28,
                            GSTR1_ItemFields.IGST.value: -339.64,
                            GSTR1_ItemFields.CGST.value: 0,
                            GSTR1_ItemFields.SGST.value: 0,
                            GSTR1_ItemFields.CESS.value: -789.52,
                            GSTR1_DataFields.TAX_RATE.value: 10,
                        },
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: -5225.28,
                            GSTR1_ItemFields.IGST.value: -339.64,
                            GSTR1_ItemFields.CGST.value: 0,
                            GSTR1_ItemFields.SGST.value: 0,
                            GSTR1_ItemFields.CESS.value: -789.52,
                            GSTR1_DataFields.TAX_RATE.value: 10,
                        },
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: -10450.56,
                    GSTR1_DataFields.IGST.value: -679.28,
                    GSTR1_DataFields.CGST.value: 0,
                    GSTR1_DataFields.SGST.value: 0,
                    GSTR1_DataFields.CESS.value: -1579.04,
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
                    GSTR1_DataFields.TRANSACTION_TYPE.value: "Credit Note",
                    GSTR1_DataFields.DOC_TYPE.value: "B2CL",
                    GSTR1_DataFields.DOC_NUMBER.value: "533515",
                    GSTR1_DataFields.DOC_DATE.value: "2016-09-23",
                    GSTR1_DataFields.DOC_VALUE.value: -64646,
                    GSTR1_DataFields.POS.value: "03-Punjab",
                    GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataFields.ITEMS.value: [
                        {
                            GSTR1_ItemFields.TAXABLE_VALUE.value: -5225.28,
                            GSTR1_ItemFields.IGST.value: -339.64,
                            GSTR1_ItemFields.CESS.value: -789.52,
                            GSTR1_DataFields.TAX_RATE.value: 10,
                        }
                    ],
                    GSTR1_DataFields.TAXABLE_VALUE.value: -5225.28,
                    GSTR1_DataFields.IGST.value: -339.64,
                    GSTR1_DataFields.CESS.value: -789.52,
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
                    GovDataFields.INDEX.value: 2,
                    GovDataFields.HSN_CODE.value: "1011",
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
                    GSTR1_DataFields.HSN_CODE.value: "1010",
                    GSTR1_DataFields.DESCRIPTION.value: "Goods Description",
                    GSTR1_DataFields.UOM.value: "KGS-KILOGRAMS",
                    GSTR1_DataFields.QUANTITY.value: 2.05,
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10.23,
                    GSTR1_DataFields.IGST.value: 14.52,
                    GSTR1_DataFields.CESS.value: 500,
                    GSTR1_DataFields.TAX_RATE.value: 0.1,
                },
                "1011 - NOS-NUMBERS - 5.0": {
                    GSTR1_DataFields.HSN_CODE.value: "1011",
                    GSTR1_DataFields.DESCRIPTION.value: "Goods Description",
                    GSTR1_DataFields.UOM.value: "NOS-NUMBERS",
                    GSTR1_DataFields.QUANTITY.value: 2.05,
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10.23,
                    GSTR1_DataFields.IGST.value: 14.52,
                    GSTR1_DataFields.CESS.value: 500,
                    GSTR1_DataFields.TAX_RATE.value: 5,
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
                        GSTR1_DataFields.POS.value: "05-Uttarakhand",
                        GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataFields.IGST.value: 9400,
                        GSTR1_DataFields.CESS.value: 500,
                        GSTR1_DataFields.CGST.value: 0,
                        GSTR1_DataFields.SGST.value: 0,
                        GSTR1_DataFields.TAXABLE_VALUE.value: 100,
                        GSTR1_DataFields.TAX_RATE.value: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        GSTR1_DataFields.POS.value: "05-Uttarakhand",
                        GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataFields.IGST.value: 9400,
                        GSTR1_DataFields.CESS.value: 500,
                        GSTR1_DataFields.CGST.value: 0,
                        GSTR1_DataFields.SGST.value: 0,
                        GSTR1_DataFields.TAXABLE_VALUE.value: 100,
                        GSTR1_DataFields.TAX_RATE.value: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        GSTR1_DataFields.POS.value: "24-Gujarat",
                        GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataFields.IGST.value: 9400,
                        GSTR1_DataFields.CESS.value: 500,
                        GSTR1_DataFields.CGST.value: 0,
                        GSTR1_DataFields.SGST.value: 0,
                        GSTR1_DataFields.TAXABLE_VALUE.value: 100,
                        GSTR1_DataFields.TAX_RATE.value: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        GSTR1_DataFields.POS.value: "24-Gujarat",
                        GSTR1_DataFields.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataFields.IGST.value: 9400,
                        GSTR1_DataFields.CESS.value: 500,
                        GSTR1_DataFields.CGST.value: 0,
                        GSTR1_DataFields.SGST.value: 0,
                        GSTR1_DataFields.TAXABLE_VALUE.value: 100,
                        GSTR1_DataFields.TAX_RATE.value: 6,
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
                    GSTR1_DataFields.DOC_TYPE.value: "Invoices for outward supply",
                    GSTR1_DataFields.FROM_SR.value: "1",
                    GSTR1_DataFields.TO_SR.value: "10",
                    GSTR1_DataFields.TOTAL_COUNT.value: 10,
                    GSTR1_DataFields.CANCELLED_COUNT.value: 0,
                },
                "Invoices for outward supply - 11": {
                    GSTR1_DataFields.DOC_TYPE.value: "Invoices for outward supply",
                    GSTR1_DataFields.FROM_SR.value: "11",
                    GSTR1_DataFields.TO_SR.value: "20",
                    GSTR1_DataFields.TOTAL_COUNT.value: 10,
                    GSTR1_DataFields.CANCELLED_COUNT.value: 0,
                },
                "Invoices for inward supply from unregistered person - 1": {
                    GSTR1_DataFields.DOC_TYPE.value: "Invoices for inward supply from unregistered person",
                    GSTR1_DataFields.FROM_SR.value: "1",
                    GSTR1_DataFields.TO_SR.value: "10",
                    GSTR1_DataFields.TOTAL_COUNT.value: 10,
                    GSTR1_DataFields.CANCELLED_COUNT.value: 0,
                },
                "Invoices for inward supply from unregistered person - 11": {
                    GSTR1_DataFields.DOC_TYPE.value: "Invoices for inward supply from unregistered person",
                    GSTR1_DataFields.FROM_SR.value: "11",
                    GSTR1_DataFields.TO_SR.value: "20",
                    GSTR1_DataFields.TOTAL_COUNT.value: 10,
                    GSTR1_DataFields.CANCELLED_COUNT.value: 0,
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
                    GovDataFields.NET_TAXABLE_VALUE.value: 10000,
                    "igst": 1000,
                    "cgst": 0,
                    "sgst": 0,
                    "cess": 0,
                }
            ],
            GovDataFields.SUPECOM_9_5.value: [
                {
                    GovDataFields.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    GovDataFields.NET_TAXABLE_VALUE.value: 10000,
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
                    GSTR1_DataFields.DOC_TYPE.value: GSTR1_SubCategories.SUPECOM_52.value,
                    GSTR1_DataFields.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10000,
                    GSTR1_ItemFields.IGST.value: 1000,
                    GSTR1_ItemFields.CGST.value: 0,
                    GSTR1_ItemFields.SGST.value: 0,
                    GSTR1_ItemFields.CESS.value: 0,
                }
            },
            GSTR1_SubCategories.SUPECOM_9_5.value: {
                "20ALYPD6528PQC5": {
                    GSTR1_DataFields.DOC_TYPE.value: GSTR1_SubCategories.SUPECOM_9_5.value,
                    GSTR1_DataFields.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    GSTR1_DataFields.TAXABLE_VALUE.value: 10000,
                    GSTR1_ItemFields.IGST.value: 1000,
                    GSTR1_ItemFields.CGST.value: 0,
                    GSTR1_ItemFields.SGST.value: 0,
                    GSTR1_ItemFields.CESS.value: 0,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = SUPECOM().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = SUPECOM().convert_to_gov_data_format(self.mapped_data)
        self.assertDictEqual(self.json_data, output)
