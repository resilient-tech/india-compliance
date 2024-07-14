import copy

from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    GenerateGSTR1,
)
from india_compliance.gst_india.utils import get_party_for_gstin as _get_party_for_gstin
from india_compliance.gst_india.utils.gstr_1 import (
    SUB_CATEGORY_GOV_CATEGORY_MAPPING,
    GovDataField,
    GSTR1_B2B_InvoiceType,
    GSTR1_DataField,
    GSTR1_ItemField,
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
    return list(
        get_category_wise_data(
            normalize_data(copy.deepcopy(data)), SUB_CATEGORY_GOV_CATEGORY_MAPPING
        ).values()
    )[0]


class TestB2B(FrappeTestCase):
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
                    GSTR1_DataField.CUST_GSTIN.value: "24AANFA2641L1ZF",
                    GSTR1_DataField.CUST_NAME.value: get_party_for_gstin(
                        "24AANFA2641L1ZF"
                    ),
                    GSTR1_DataField.DOC_NUMBER.value: "S008400",
                    GSTR1_DataField.DOC_DATE.value: "2016-11-24",
                    GSTR1_DataField.DOC_VALUE.value: 729248.16,
                    GSTR1_DataField.POS.value: "06-Haryana",
                    GSTR1_DataField.REVERSE_CHARGE.value: "N",
                    GSTR1_DataField.DOC_TYPE.value: GSTR1_B2B_InvoiceType.R.value,
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CGST.value: 0,
                            GSTR1_ItemField.SGST.value: 0,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        },
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CGST.value: 0,
                            GSTR1_ItemField.SGST.value: 0,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        },
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 20000,
                    GSTR1_DataField.IGST.value: 650,
                    GSTR1_DataField.CGST.value: 0,
                    GSTR1_DataField.SGST.value: 0,
                    GSTR1_DataField.CESS.value: 1000,
                }
            },
            GSTR1_SubCategory.B2B_REVERSE_CHARGE.value: {
                "S008401": {
                    GSTR1_DataField.CUST_GSTIN.value: "24AANFA2641L1ZF",
                    GSTR1_DataField.CUST_NAME.value: get_party_for_gstin(
                        "24AANFA2641L1ZF"
                    ),
                    GSTR1_DataField.DOC_NUMBER.value: "S008401",
                    GSTR1_DataField.DOC_DATE.value: "2016-11-24",
                    GSTR1_DataField.DOC_VALUE.value: 729248.16,
                    GSTR1_DataField.POS.value: "06-Haryana",
                    GSTR1_DataField.REVERSE_CHARGE.value: "Y",
                    GSTR1_DataField.DOC_TYPE.value: GSTR1_B2B_InvoiceType.R.value,
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CGST.value: 0,
                            GSTR1_ItemField.SGST.value: 0,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataField.IGST.value: 325,
                    GSTR1_DataField.CGST.value: 0,
                    GSTR1_DataField.SGST.value: 0,
                    GSTR1_DataField.CESS.value: 500,
                }
            },
            GSTR1_SubCategory.SEZWP.value: {
                "S008402": {
                    GSTR1_DataField.CUST_GSTIN.value: "29AABCR1718E1ZL",
                    GSTR1_DataField.CUST_NAME.value: get_party_for_gstin(
                        "29AABCR1718E1ZL"
                    ),
                    GSTR1_DataField.DOC_NUMBER.value: "S008402",
                    GSTR1_DataField.DOC_DATE.value: "2016-11-24",
                    GSTR1_DataField.DOC_VALUE.value: 729248.16,
                    GSTR1_DataField.POS.value: "06-Haryana",
                    GSTR1_DataField.REVERSE_CHARGE.value: "N",
                    GSTR1_DataField.DOC_TYPE.value: GSTR1_B2B_InvoiceType.SEWP.value,
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CGST.value: 0,
                            GSTR1_ItemField.SGST.value: 0,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataField.IGST.value: 325,
                    GSTR1_DataField.CGST.value: 0,
                    GSTR1_DataField.SGST.value: 0,
                    GSTR1_DataField.CESS.value: 500,
                }
            },
            GSTR1_SubCategory.DE.value: {
                "S008403": {
                    GSTR1_DataField.CUST_GSTIN.value: "29AABCR1718E1ZL",
                    GSTR1_DataField.CUST_NAME.value: get_party_for_gstin(
                        "29AABCR1718E1ZL"
                    ),
                    GSTR1_DataField.DOC_NUMBER.value: "S008403",
                    GSTR1_DataField.DOC_DATE.value: "2016-11-24",
                    GSTR1_DataField.DOC_VALUE.value: 729248.16,
                    GSTR1_DataField.POS.value: "06-Haryana",
                    GSTR1_DataField.REVERSE_CHARGE.value: "N",
                    GSTR1_DataField.DOC_TYPE.value: GSTR1_B2B_InvoiceType.DE.value,
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CGST.value: 0,
                            GSTR1_ItemField.SGST.value: 0,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataField.IGST.value: 325,
                    GSTR1_DataField.CGST.value: 0,
                    GSTR1_DataField.SGST.value: 0,
                    GSTR1_DataField.CESS.value: 500,
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
                    GSTR1_DataField.POS.value: "05-Uttarakhand",
                    GSTR1_DataField.DOC_TYPE.value: "B2C (Large)",
                    GSTR1_DataField.DOC_NUMBER.value: "92661",
                    GSTR1_DataField.DOC_DATE.value: "2016-01-10",
                    GSTR1_DataField.DOC_VALUE.value: 784586.33,
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        },
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        },
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 20000,
                    GSTR1_DataField.IGST.value: 650,
                    GSTR1_DataField.CESS.value: 1000,
                },
                "92662": {
                    GSTR1_DataField.POS.value: "05-Uttarakhand",
                    GSTR1_DataField.DOC_TYPE.value: "B2C (Large)",
                    GSTR1_DataField.DOC_NUMBER.value: "92662",
                    GSTR1_DataField.DOC_DATE.value: "2016-01-10",
                    GSTR1_DataField.DOC_VALUE.value: 784586.33,
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataField.IGST.value: 325,
                    GSTR1_DataField.CESS.value: 500,
                },
                "92663": {
                    GSTR1_DataField.POS.value: "24-Gujarat",
                    GSTR1_DataField.DOC_TYPE.value: "B2C (Large)",
                    GSTR1_DataField.DOC_NUMBER.value: "92663",
                    GSTR1_DataField.DOC_DATE.value: "2016-01-10",
                    GSTR1_DataField.DOC_VALUE.value: 784586.33,
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        },
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        },
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 20000,
                    GSTR1_DataField.IGST.value: 650,
                    GSTR1_DataField.CESS.value: 1000,
                },
                "92664": {
                    GSTR1_DataField.POS.value: "24-Gujarat",
                    GSTR1_DataField.DOC_TYPE.value: "B2C (Large)",
                    GSTR1_DataField.DOC_NUMBER.value: "92664",
                    GSTR1_DataField.DOC_DATE.value: "2016-01-10",
                    GSTR1_DataField.DOC_VALUE.value: 784586.33,
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 325,
                            GSTR1_ItemField.CESS.value: 500,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataField.IGST.value: 325,
                    GSTR1_DataField.CESS.value: 500,
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
                    GSTR1_DataField.DOC_TYPE.value: "WPAY",
                    GSTR1_DataField.DOC_NUMBER.value: "81542",
                    GSTR1_DataField.DOC_DATE.value: "2016-02-12",
                    GSTR1_DataField.DOC_VALUE.value: 995048.36,
                    GSTR1_DataField.SHIPPING_PORT_CODE.value: "ASB991",
                    GSTR1_DataField.SHIPPING_BILL_NUMBER.value: "7896542",
                    GSTR1_DataField.SHIPPING_BILL_DATE.value: "2016-10-04",
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 833.33,
                            GSTR1_ItemField.CESS.value: 100,
                            GSTR1_DataField.TAX_RATE.value: 5,
                        }
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataField.IGST.value: 833.33,
                    GSTR1_DataField.CESS.value: 100,
                }
            },
            GSTR1_SubCategory.EXPWOP.value: {
                "81543": {
                    GSTR1_DataField.DOC_TYPE.value: "WOPAY",
                    GSTR1_DataField.DOC_NUMBER.value: "81543",
                    GSTR1_DataField.DOC_DATE.value: "2016-02-12",
                    GSTR1_DataField.DOC_VALUE.value: 995048.36,
                    GSTR1_DataField.SHIPPING_PORT_CODE.value: "ASB981",
                    GSTR1_DataField.SHIPPING_BILL_NUMBER.value: "7896542",
                    GSTR1_DataField.SHIPPING_BILL_DATE.value: "2016-10-04",
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: 10000,
                            GSTR1_ItemField.IGST.value: 0,
                            GSTR1_ItemField.CESS.value: 100,
                            GSTR1_DataField.TAX_RATE.value: 0,
                        }
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: 10000,
                    GSTR1_DataField.IGST.value: 0,
                    GSTR1_DataField.CESS.value: 100,
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
                        GSTR1_DataField.TAXABLE_VALUE.value: 110,
                        GSTR1_DataField.DOC_TYPE.value: "OE",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.POS.value: "05-Uttarakhand",
                        GSTR1_DataField.TAX_RATE.value: 5,
                        GSTR1_DataField.IGST.value: 10,
                        GSTR1_DataField.CESS.value: 10,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
                    },
                ],
                "06-Haryana - 5.0": [
                    {
                        GSTR1_DataField.TAXABLE_VALUE.value: 100,
                        GSTR1_DataField.DOC_TYPE.value: "OE",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.POS.value: "06-Haryana",
                        GSTR1_DataField.TAX_RATE.value: 5,
                        GSTR1_DataField.IGST.value: 10,
                        GSTR1_DataField.CESS.value: 10,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
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
                        GSTR1_DataField.DOC_TYPE.value: "Inter-State supplies to registered persons",
                        GSTR1_DataField.EXEMPTED_AMOUNT.value: 123.45,
                        GSTR1_DataField.NIL_RATED_AMOUNT.value: 1470.85,
                        GSTR1_DataField.NON_GST_AMOUNT.value: 1258.5,
                        GSTR1_DataField.TAXABLE_VALUE.value: 2852.8,
                    }
                ],
                "Inter-State supplies to unregistered persons": [
                    {
                        GSTR1_DataField.DOC_TYPE.value: "Inter-State supplies to unregistered persons",
                        GSTR1_DataField.EXEMPTED_AMOUNT.value: 123.45,
                        GSTR1_DataField.NIL_RATED_AMOUNT.value: 1470.85,
                        GSTR1_DataField.NON_GST_AMOUNT.value: 1258.5,
                        GSTR1_DataField.TAXABLE_VALUE.value: 2852.8,
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
                    GSTR1_DataField.CUST_GSTIN.value: "24AANFA2641L1ZF",
                    GSTR1_DataField.CUST_NAME.value: get_party_for_gstin(
                        "24AANFA2641L1ZF"
                    ),
                    GSTR1_DataField.TRANSACTION_TYPE.value: "Credit Note",
                    GSTR1_DataField.DOC_NUMBER.value: "533515",
                    GSTR1_DataField.DOC_DATE.value: "2016-09-23",
                    GSTR1_DataField.POS.value: "03-Punjab",
                    GSTR1_DataField.REVERSE_CHARGE.value: "Y",
                    GSTR1_DataField.DOC_TYPE.value: "Deemed Exports",
                    GSTR1_DataField.DOC_VALUE.value: -123123,
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: -5225.28,
                            GSTR1_ItemField.IGST.value: -339.64,
                            GSTR1_ItemField.CGST.value: 0,
                            GSTR1_ItemField.SGST.value: 0,
                            GSTR1_ItemField.CESS.value: -789.52,
                            GSTR1_DataField.TAX_RATE.value: 10,
                        },
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: -5225.28,
                            GSTR1_ItemField.IGST.value: -339.64,
                            GSTR1_ItemField.CGST.value: 0,
                            GSTR1_ItemField.SGST.value: 0,
                            GSTR1_ItemField.CESS.value: -789.52,
                            GSTR1_DataField.TAX_RATE.value: 10,
                        },
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: -10450.56,
                    GSTR1_DataField.IGST.value: -679.28,
                    GSTR1_DataField.CGST.value: 0,
                    GSTR1_DataField.SGST.value: 0,
                    GSTR1_DataField.CESS.value: -1579.04,
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
                    GSTR1_DataField.TRANSACTION_TYPE.value: "Credit Note",
                    GSTR1_DataField.DOC_TYPE.value: "B2CL",
                    GSTR1_DataField.DOC_NUMBER.value: "533515",
                    GSTR1_DataField.DOC_DATE.value: "2016-09-23",
                    GSTR1_DataField.DOC_VALUE.value: -64646,
                    GSTR1_DataField.POS.value: "03-Punjab",
                    GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                    GSTR1_DataField.ITEMS.value: [
                        {
                            GSTR1_ItemField.TAXABLE_VALUE.value: -5225.28,
                            GSTR1_ItemField.IGST.value: -339.64,
                            GSTR1_ItemField.CESS.value: -789.52,
                            GSTR1_DataField.TAX_RATE.value: 10,
                        }
                    ],
                    GSTR1_DataField.TAXABLE_VALUE.value: -5225.28,
                    GSTR1_DataField.IGST.value: -339.64,
                    GSTR1_DataField.CESS.value: -789.52,
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
                    GovDataField.TAX_RATE.value: 5.0,
                },
            ]
        }

        cls.mapped_data = {
            GSTR1_SubCategory.HSN.value: {
                "1010 - KGS-KILOGRAMS - 0.1": {
                    GSTR1_DataField.HSN_CODE.value: "1010",
                    GSTR1_DataField.DESCRIPTION.value: "Goods Description",
                    GSTR1_DataField.UOM.value: "KGS-KILOGRAMS",
                    GSTR1_DataField.QUANTITY.value: 2.05,
                    GSTR1_DataField.TAXABLE_VALUE.value: 10.23,
                    GSTR1_DataField.IGST.value: 14.52,
                    GSTR1_DataField.CESS.value: 500,
                    GSTR1_DataField.TAX_RATE.value: 0.1,
                    GSTR1_DataField.DOC_VALUE.value: 524.75,
                },
                "1011 - NOS-NUMBERS - 5.0": {
                    GSTR1_DataField.HSN_CODE.value: "1011",
                    GSTR1_DataField.DESCRIPTION.value: "Goods Description",
                    GSTR1_DataField.UOM.value: "NOS-NUMBERS",
                    GSTR1_DataField.QUANTITY.value: 2.05,
                    GSTR1_DataField.TAXABLE_VALUE.value: 10.23,
                    GSTR1_DataField.IGST.value: 14.52,
                    GSTR1_DataField.CESS.value: 500,
                    GSTR1_DataField.TAX_RATE.value: 5,
                    GSTR1_DataField.DOC_VALUE.value: 524.75,
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


class TestAT(FrappeTestCase):
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
                        GSTR1_DataField.POS.value: "05-Uttarakhand",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.IGST.value: 9400,
                        GSTR1_DataField.CESS.value: 500,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
                        GSTR1_DataField.TAXABLE_VALUE.value: 100,
                        GSTR1_DataField.TAX_RATE.value: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        GSTR1_DataField.POS.value: "05-Uttarakhand",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.IGST.value: 9400,
                        GSTR1_DataField.CESS.value: 500,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
                        GSTR1_DataField.TAXABLE_VALUE.value: 100,
                        GSTR1_DataField.TAX_RATE.value: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        GSTR1_DataField.POS.value: "24-Gujarat",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.IGST.value: 9400,
                        GSTR1_DataField.CESS.value: 500,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
                        GSTR1_DataField.TAXABLE_VALUE.value: 100,
                        GSTR1_DataField.TAX_RATE.value: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        GSTR1_DataField.POS.value: "24-Gujarat",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.IGST.value: 9400,
                        GSTR1_DataField.CESS.value: 500,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
                        GSTR1_DataField.TAXABLE_VALUE.value: 100,
                        GSTR1_DataField.TAX_RATE.value: 6,
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
                        GSTR1_DataField.POS.value: "05-Uttarakhand",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.IGST.value: -9400,
                        GSTR1_DataField.CESS.value: -500,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
                        GSTR1_DataField.TAXABLE_VALUE.value: -100,
                        GSTR1_DataField.TAX_RATE.value: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        GSTR1_DataField.POS.value: "05-Uttarakhand",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.IGST.value: -9400,
                        GSTR1_DataField.CESS.value: -500,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
                        GSTR1_DataField.TAXABLE_VALUE.value: -100,
                        GSTR1_DataField.TAX_RATE.value: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        GSTR1_DataField.POS.value: "24-Gujarat",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.IGST.value: -9400,
                        GSTR1_DataField.CESS.value: -500,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
                        GSTR1_DataField.TAXABLE_VALUE.value: -100,
                        GSTR1_DataField.TAX_RATE.value: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        GSTR1_DataField.POS.value: "24-Gujarat",
                        GSTR1_DataField.DIFF_PERCENTAGE.value: 0.65,
                        GSTR1_DataField.IGST.value: -9400,
                        GSTR1_DataField.CESS.value: -500,
                        GSTR1_DataField.CGST.value: 0,
                        GSTR1_DataField.SGST.value: 0,
                        GSTR1_DataField.TAXABLE_VALUE.value: -100,
                        GSTR1_DataField.TAX_RATE.value: 6,
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
                    GSTR1_DataField.DOC_TYPE.value: "Invoices for outward supply",
                    GSTR1_DataField.FROM_SR.value: "1",
                    GSTR1_DataField.TO_SR.value: "10",
                    GSTR1_DataField.TOTAL_COUNT.value: 10,
                    GSTR1_DataField.CANCELLED_COUNT.value: 0,
                    "net_issue": 10,
                },
                "Invoices for outward supply - 11": {
                    GSTR1_DataField.DOC_TYPE.value: "Invoices for outward supply",
                    GSTR1_DataField.FROM_SR.value: "11",
                    GSTR1_DataField.TO_SR.value: "20",
                    GSTR1_DataField.TOTAL_COUNT.value: 10,
                    GSTR1_DataField.CANCELLED_COUNT.value: 0,
                    "net_issue": 10,
                },
                "Invoices for inward supply from unregistered person - 1": {
                    GSTR1_DataField.DOC_TYPE.value: "Invoices for inward supply from unregistered person",
                    GSTR1_DataField.FROM_SR.value: "1",
                    GSTR1_DataField.TO_SR.value: "10",
                    GSTR1_DataField.TOTAL_COUNT.value: 10,
                    GSTR1_DataField.CANCELLED_COUNT.value: 0,
                    "net_issue": 10,
                },
                "Invoices for inward supply from unregistered person - 11": {
                    GSTR1_DataField.DOC_TYPE.value: "Invoices for inward supply from unregistered person",
                    GSTR1_DataField.FROM_SR.value: "11",
                    GSTR1_DataField.TO_SR.value: "20",
                    GSTR1_DataField.TOTAL_COUNT.value: 10,
                    GSTR1_DataField.CANCELLED_COUNT.value: 0,
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
                    GSTR1_DataField.DOC_TYPE.value: GSTR1_SubCategory.SUPECOM_52.value,
                    GSTR1_DataField.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    GSTR1_DataField.TAXABLE_VALUE.value: 10000,
                    GSTR1_ItemField.IGST.value: 1000,
                    GSTR1_ItemField.CGST.value: 0,
                    GSTR1_ItemField.SGST.value: 0,
                    GSTR1_ItemField.CESS.value: 0,
                }
            },
            GSTR1_SubCategory.SUPECOM_9_5.value: {
                "20ALYPD6528PQC5": {
                    GSTR1_DataField.DOC_TYPE.value: GSTR1_SubCategory.SUPECOM_9_5.value,
                    GSTR1_DataField.ECOMMERCE_GSTIN.value: "20ALYPD6528PQC5",
                    GSTR1_DataField.TAXABLE_VALUE.value: 10000,
                    GSTR1_ItemField.IGST.value: 1000,
                    GSTR1_ItemField.CGST.value: 0,
                    GSTR1_ItemField.SGST.value: 0,
                    GSTR1_ItemField.CESS.value: 0,
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
