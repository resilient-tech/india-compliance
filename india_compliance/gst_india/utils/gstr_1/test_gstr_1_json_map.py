import copy

from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    GenerateGSTR1,
)
from india_compliance.gst_india.utils import get_party_for_gstin as _get_party_for_gstin
from india_compliance.gst_india.utils.gstr_1 import (
    B2BInvoiceType,
    SubCategory,
)
from india_compliance.gst_india.utils.gstr_1 import DocField as doc
from india_compliance.gst_india.utils.gstr_1 import ItemField as item
from india_compliance.gst_india.utils.gstr_1 import RawField as raw
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    get_category_wise_data,
)
from india_compliance.gst_india.utils.gstr_1.sections import (
    advances,
    b2b,
    b2cl,
    b2cs,
    cdnr,
    cdnur,
    doc_issue,
    exports,
    hsn,
    nil_rated,
    supecom,
)
from india_compliance.gst_india.utils.gstr_1.sections._shared import strip_empty
from india_compliance.gst_returns.roundtrip import assert_roundtrip

# Delhi, a state no fixture below supplies to, so every row stays inter-state
COMPANY_GSTIN = "07AAUPV7468F1ZW"


def get_party_for_gstin(gstin):
    return _get_party_for_gstin(gstin, "Customer") or "Unknown"


def normalize_data(data):
    return GenerateGSTR1().normalize_data(data)


def strip_empty_of(writer, *args, **kwargs):
    """Portal payload as get_gstr_1_json builds it: mapped, then blanks dropped."""
    return strip_empty(writer(*args, **kwargs))


def process_mapped_data(data):
    return next(iter(get_category_wise_data(normalize_data(copy.deepcopy(data))).values()))


class TestB2B(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                raw.CUST_GSTIN: "24AANFA2641L1ZF",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "S008400",
                        raw.DOC_DATE: "24-11-2016",
                        raw.DOC_VALUE: 729248.16,
                        raw.POS: "06",
                        raw.REVERSE_CHARGE: "N",
                        raw.INVOICE_TYPE: "R",
                        raw.DIFF_PERCENTAGE: 0.65,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CGST: 0,
                                    raw.SGST: 0,
                                    raw.CESS: 500,
                                },
                            },
                            {
                                raw.INDEX: 2,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CGST: 0,
                                    raw.SGST: 0,
                                    raw.CESS: 500,
                                },
                            },
                        ],
                    },
                    {
                        raw.DOC_NUMBER: "S008401",
                        raw.DOC_DATE: "24-11-2016",
                        raw.DOC_VALUE: 729248.16,
                        raw.POS: "06",
                        raw.REVERSE_CHARGE: "Y",
                        raw.INVOICE_TYPE: "R",
                        raw.DIFF_PERCENTAGE: 0.65,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CGST: 0,
                                    raw.SGST: 0,
                                    raw.CESS: 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                raw.CUST_GSTIN: "29AABCR1718E1ZL",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "S008402",
                        raw.DOC_DATE: "24-11-2016",
                        raw.DOC_VALUE: 729248.16,
                        raw.POS: "06",
                        raw.REVERSE_CHARGE: "N",
                        raw.INVOICE_TYPE: "SEWP",
                        raw.DIFF_PERCENTAGE: 0.65,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CGST: 0,
                                    raw.SGST: 0,
                                    raw.CESS: 500,
                                },
                            }
                        ],
                    },
                    {
                        raw.DOC_NUMBER: "S008403",
                        raw.DOC_DATE: "24-11-2016",
                        raw.DOC_VALUE: 729248.16,
                        raw.POS: "06",
                        raw.REVERSE_CHARGE: "N",
                        raw.INVOICE_TYPE: "DE",
                        raw.DIFF_PERCENTAGE: 0.65,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CGST: 0,
                                    raw.SGST: 0,
                                    raw.CESS: 500,
                                },
                            }
                        ],
                    },
                ],
            },
        ]
        cls.mapped_data = {
            SubCategory.B2B_REGULAR.value: {
                "S008400": {
                    doc.CUST_GSTIN: "24AANFA2641L1ZF",
                    doc.CUST_NAME: get_party_for_gstin("24AANFA2641L1ZF"),
                    doc.DOC_NUMBER: "S008400",
                    doc.DOC_DATE: "2016-11-24",
                    doc.DOC_VALUE: 729248.16,
                    doc.POS: "06-Haryana",
                    doc.REVERSE_CHARGE: "N",
                    doc.DOC_TYPE: B2BInvoiceType.R.value,
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CGST: 0,
                            item.SGST: 0,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        },
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CGST: 0,
                            item.SGST: 0,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        },
                    ],
                    doc.TAXABLE_VALUE: 20000,
                    doc.IGST: 650,
                    doc.CGST: 0,
                    doc.SGST: 0,
                    doc.CESS: 1000,
                }
            },
            SubCategory.B2B_REVERSE_CHARGE.value: {
                "S008401": {
                    doc.CUST_GSTIN: "24AANFA2641L1ZF",
                    doc.CUST_NAME: get_party_for_gstin("24AANFA2641L1ZF"),
                    doc.DOC_NUMBER: "S008401",
                    doc.DOC_DATE: "2016-11-24",
                    doc.DOC_VALUE: 729248.16,
                    doc.POS: "06-Haryana",
                    doc.REVERSE_CHARGE: "Y",
                    doc.DOC_TYPE: B2BInvoiceType.R.value,
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CGST: 0,
                            item.SGST: 0,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        }
                    ],
                    doc.TAXABLE_VALUE: 10000,
                    doc.IGST: 325,
                    doc.CGST: 0,
                    doc.SGST: 0,
                    doc.CESS: 500,
                }
            },
            SubCategory.SEZWP.value: {
                "S008402": {
                    doc.CUST_GSTIN: "29AABCR1718E1ZL",
                    doc.CUST_NAME: get_party_for_gstin("29AABCR1718E1ZL"),
                    doc.DOC_NUMBER: "S008402",
                    doc.DOC_DATE: "2016-11-24",
                    doc.DOC_VALUE: 729248.16,
                    doc.POS: "06-Haryana",
                    doc.REVERSE_CHARGE: "N",
                    doc.DOC_TYPE: B2BInvoiceType.SEWP.value,
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CGST: 0,
                            item.SGST: 0,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        }
                    ],
                    doc.TAXABLE_VALUE: 10000,
                    doc.IGST: 325,
                    doc.CGST: 0,
                    doc.SGST: 0,
                    doc.CESS: 500,
                }
            },
            SubCategory.DE.value: {
                "S008403": {
                    doc.CUST_GSTIN: "29AABCR1718E1ZL",
                    doc.CUST_NAME: get_party_for_gstin("29AABCR1718E1ZL"),
                    doc.DOC_NUMBER: "S008403",
                    doc.DOC_DATE: "2016-11-24",
                    doc.DOC_VALUE: 729248.16,
                    doc.POS: "06-Haryana",
                    doc.REVERSE_CHARGE: "N",
                    doc.DOC_TYPE: B2BInvoiceType.DE.value,
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CGST: 0,
                            item.SGST: 0,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        }
                    ],
                    doc.TAXABLE_VALUE: 10000,
                    doc.IGST: 325,
                    doc.CGST: 0,
                    doc.SGST: 0,
                    doc.CESS: 500,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = b2b.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(b2b.to_gov, process_mapped_data(self.mapped_data))
        self.assertListEqual(self.json_data, output)

    def test_losslessness_harness_on_real_data(self):
        internal = b2b.to_canonical(copy.deepcopy(self.json_data))
        gov = strip_empty_of(b2b.to_gov, process_mapped_data(internal))
        assert_roundtrip(self.json_data, gov)

        lossy = copy.deepcopy(self.json_data)
        lossy[0][raw.INVOICES][0]["extra_empty"] = ""
        gov = strip_empty_of(b2b.to_gov, process_mapped_data(b2b.to_canonical(lossy)))
        assert_roundtrip(lossy, gov)  # tolerated
        self.assertNotEqual(lossy, gov)  # not exactly equal -- a loss did occur


class TestB2CL(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                raw.POS: "05",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "92661",
                        raw.DOC_DATE: "10-01-2016",
                        raw.DOC_VALUE: 784586.33,
                        raw.DIFF_PERCENTAGE: 0.65,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CESS: 500,
                                },
                            },
                            {
                                raw.INDEX: 2,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CESS: 500,
                                },
                            },
                        ],
                    },
                    {
                        raw.DOC_NUMBER: "92662",
                        raw.DOC_DATE: "10-01-2016",
                        raw.DOC_VALUE: 784586.33,
                        raw.DIFF_PERCENTAGE: 0.65,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CESS: 500,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                raw.POS: "24",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "92663",
                        raw.DOC_DATE: "10-01-2016",
                        raw.DOC_VALUE: 784586.33,
                        raw.DIFF_PERCENTAGE: 0.65,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CESS: 500,
                                },
                            },
                            {
                                raw.INDEX: 2,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CESS: 500,
                                },
                            },
                        ],
                    },
                    {
                        raw.DOC_NUMBER: "92664",
                        raw.DOC_DATE: "10-01-2016",
                        raw.DOC_VALUE: 784586.33,
                        raw.DIFF_PERCENTAGE: 0.65,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 325,
                                    raw.CESS: 500,
                                },
                            }
                        ],
                    },
                ],
            },
        ]
        cls.mapped_data = {
            SubCategory.B2CL.value: {
                "92661": {
                    doc.POS: "05-Uttarakhand",
                    doc.DOC_TYPE: "B2C (Large)",
                    doc.DOC_NUMBER: "92661",
                    doc.DOC_DATE: "2016-01-10",
                    doc.DOC_VALUE: 784586.33,
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        },
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        },
                    ],
                    doc.TAXABLE_VALUE: 20000,
                    doc.IGST: 650,
                    doc.CESS: 1000,
                },
                "92662": {
                    doc.POS: "05-Uttarakhand",
                    doc.DOC_TYPE: "B2C (Large)",
                    doc.DOC_NUMBER: "92662",
                    doc.DOC_DATE: "2016-01-10",
                    doc.DOC_VALUE: 784586.33,
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        }
                    ],
                    doc.TAXABLE_VALUE: 10000,
                    doc.IGST: 325,
                    doc.CESS: 500,
                },
                "92663": {
                    doc.POS: "24-Gujarat",
                    doc.DOC_TYPE: "B2C (Large)",
                    doc.DOC_NUMBER: "92663",
                    doc.DOC_DATE: "2016-01-10",
                    doc.DOC_VALUE: 784586.33,
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        },
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        },
                    ],
                    doc.TAXABLE_VALUE: 20000,
                    doc.IGST: 650,
                    doc.CESS: 1000,
                },
                "92664": {
                    doc.POS: "24-Gujarat",
                    doc.DOC_TYPE: "B2C (Large)",
                    doc.DOC_NUMBER: "92664",
                    doc.DOC_DATE: "2016-01-10",
                    doc.DOC_VALUE: 784586.33,
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 325,
                            item.CESS: 500,
                            doc.TAX_RATE: 5,
                        }
                    ],
                    doc.TAXABLE_VALUE: 10000,
                    doc.IGST: 325,
                    doc.CESS: 500,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = b2cl.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(b2cl.to_gov, process_mapped_data(self.mapped_data))
        self.assertListEqual(self.json_data, output)


class TestExports(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                raw.EXPORT_TYPE: "WPAY",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "81542",
                        raw.DOC_DATE: "12-02-2016",
                        raw.DOC_VALUE: 995048.36,
                        raw.SHIPPING_PORT_CODE: "ASB991",
                        raw.SHIPPING_BILL_NUMBER: "7896542",
                        raw.SHIPPING_BILL_DATE: "04-10-2016",
                        raw.ITEMS: [
                            {
                                raw.TAXABLE_VALUE: 10000,
                                raw.TAX_RATE: 5,
                                raw.IGST: 833.33,
                                raw.CESS: 100,
                            }
                        ],
                    }
                ],
            },
            {
                raw.EXPORT_TYPE: "WOPAY",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "81543",
                        raw.DOC_DATE: "12-02-2016",
                        raw.DOC_VALUE: 995048.36,
                        raw.SHIPPING_PORT_CODE: "ASB981",
                        raw.SHIPPING_BILL_NUMBER: "7896542",
                        raw.SHIPPING_BILL_DATE: "04-10-2016",
                        raw.ITEMS: [
                            {
                                raw.TAXABLE_VALUE: 10000,
                                raw.TAX_RATE: 0,
                                raw.IGST: 0,
                                raw.CESS: 100,
                            }
                        ],
                    }
                ],
            },
        ]
        cls.mapped_data = {
            SubCategory.EXPWP.value: {
                "81542": {
                    doc.DOC_TYPE: "WPAY",
                    doc.DOC_NUMBER: "81542",
                    doc.DOC_DATE: "2016-02-12",
                    doc.DOC_VALUE: 995048.36,
                    doc.SHIPPING_PORT_CODE: "ASB991",
                    doc.SHIPPING_BILL_NUMBER: "7896542",
                    doc.SHIPPING_BILL_DATE: "2016-10-04",
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 833.33,
                            item.CESS: 100,
                            doc.TAX_RATE: 5,
                        }
                    ],
                    doc.TAXABLE_VALUE: 10000,
                    doc.IGST: 833.33,
                    doc.CESS: 100,
                }
            },
            SubCategory.EXPWOP.value: {
                "81543": {
                    doc.DOC_TYPE: "WOPAY",
                    doc.DOC_NUMBER: "81543",
                    doc.DOC_DATE: "2016-02-12",
                    doc.DOC_VALUE: 995048.36,
                    doc.SHIPPING_PORT_CODE: "ASB981",
                    doc.SHIPPING_BILL_NUMBER: "7896542",
                    doc.SHIPPING_BILL_DATE: "2016-10-04",
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: 10000,
                            item.IGST: 0,
                            item.CESS: 100,
                            doc.TAX_RATE: 0,
                        }
                    ],
                    doc.TAXABLE_VALUE: 10000,
                    doc.IGST: 0,
                    doc.CESS: 100,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = exports.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(exports.to_gov, process_mapped_data(self.mapped_data))
        self.assertListEqual(self.json_data, output)


class TestB2CS(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                raw.SUPPLY_TYPE: "INTER",
                raw.DIFF_PERCENTAGE: 0.65,
                raw.TAX_RATE: 5,
                raw.TYPE: "OE",
                raw.POS: "05",
                raw.TAXABLE_VALUE: 110,
                raw.IGST: 10,
                raw.CGST: 0,
                raw.SGST: 0,
                raw.CESS: 10,
            },
            {
                raw.SUPPLY_TYPE: "INTER",
                raw.DIFF_PERCENTAGE: 0.65,
                raw.TAX_RATE: 5,
                raw.TYPE: "OE",
                raw.TAXABLE_VALUE: 100,
                raw.IGST: 10,
                raw.CGST: 0,
                raw.SGST: 0,
                raw.CESS: 10,
                raw.POS: "06",
            },
        ]
        cls.mapped_data = {
            SubCategory.B2CS.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        doc.TAXABLE_VALUE: 110,
                        doc.DOC_TYPE: "OE",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.POS: "05-Uttarakhand",
                        doc.TAX_RATE: 5,
                        doc.IGST: 10,
                        doc.CESS: 10,
                        doc.CGST: 0,
                        doc.SGST: 0,
                    },
                ],
                "06-Haryana - 5.0": [
                    {
                        doc.TAXABLE_VALUE: 100,
                        doc.DOC_TYPE: "OE",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.POS: "06-Haryana",
                        doc.TAX_RATE: 5,
                        doc.IGST: 10,
                        doc.CESS: 10,
                        doc.CGST: 0,
                        doc.SGST: 0,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = b2cs.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(b2cs.to_gov, process_mapped_data(self.mapped_data), COMPANY_GSTIN)
        self.assertListEqual(self.json_data, output)


class TestNilRated(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            raw.INVOICES: [
                {
                    raw.SUPPLY_TYPE: "INTRB2B",
                    raw.EXEMPTED_AMOUNT: 123.45,
                    raw.NIL_RATED_AMOUNT: 1470.85,
                    raw.NON_GST_AMOUNT: 1258.5,
                },
                {
                    raw.SUPPLY_TYPE: "INTRB2C",
                    raw.EXEMPTED_AMOUNT: 123.45,
                    raw.NIL_RATED_AMOUNT: 1470.85,
                    raw.NON_GST_AMOUNT: 1258.5,
                },
            ]
        }

        cls.mapped_data = {
            SubCategory.NIL_EXEMPT.value: {
                "Inter-State supplies to registered persons": [
                    {
                        doc.DOC_TYPE: "Inter-State supplies to registered persons",
                        doc.EXEMPTED_AMOUNT: 123.45,
                        doc.NIL_RATED_AMOUNT: 1470.85,
                        doc.NON_GST_AMOUNT: 1258.5,
                        doc.TAXABLE_VALUE: 2852.8,
                    }
                ],
                "Inter-State supplies to unregistered persons": [
                    {
                        doc.DOC_TYPE: "Inter-State supplies to unregistered persons",
                        doc.EXEMPTED_AMOUNT: 123.45,
                        doc.NIL_RATED_AMOUNT: 1470.85,
                        doc.NON_GST_AMOUNT: 1258.5,
                        doc.TAXABLE_VALUE: 2852.8,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = nil_rated.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(nil_rated.to_gov, process_mapped_data(self.mapped_data))
        self.assertDictEqual(self.json_data, output)


class TestCDNR(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                raw.CUST_GSTIN: "24AANFA2641L1ZF",
                raw.NOTE_DETAILS: [
                    {
                        raw.NOTE_TYPE: "C",
                        raw.NOTE_NUMBER: "533515",
                        raw.NOTE_DATE: "23-09-2016",
                        raw.POS: "03",
                        raw.REVERSE_CHARGE: "Y",
                        raw.INVOICE_TYPE: "DE",
                        raw.DOC_VALUE: 123123,
                        raw.DIFF_PERCENTAGE: 0.65,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 10,
                                    raw.TAXABLE_VALUE: 5225.28,
                                    raw.SGST: 0,
                                    raw.CGST: 0,
                                    raw.IGST: 339.64,
                                    raw.CESS: 789.52,
                                },
                            },
                            {
                                raw.INDEX: 2,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 10,
                                    raw.TAXABLE_VALUE: 5225.28,
                                    raw.SGST: 0,
                                    raw.CGST: 0,
                                    raw.IGST: 339.64,
                                    raw.CESS: 789.52,
                                },
                            },
                        ],
                    },
                ],
            }
        ]
        cls.mapped_data = {
            SubCategory.CDNR.value: {
                "533515": {
                    doc.CUST_GSTIN: "24AANFA2641L1ZF",
                    doc.CUST_NAME: get_party_for_gstin("24AANFA2641L1ZF"),
                    doc.TRANSACTION_TYPE: "Credit Note",
                    doc.DOC_NUMBER: "533515",
                    doc.DOC_DATE: "2016-09-23",
                    doc.POS: "03-Punjab",
                    doc.REVERSE_CHARGE: "Y",
                    doc.DOC_TYPE: "Deemed Exp",
                    doc.DOC_VALUE: -123123,
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: -5225.28,
                            item.IGST: -339.64,
                            item.CGST: 0,
                            item.SGST: 0,
                            item.CESS: -789.52,
                            doc.TAX_RATE: 10,
                        },
                        {
                            item.TAXABLE_VALUE: -5225.28,
                            item.IGST: -339.64,
                            item.CGST: 0,
                            item.SGST: 0,
                            item.CESS: -789.52,
                            doc.TAX_RATE: 10,
                        },
                    ],
                    doc.TAXABLE_VALUE: -10450.56,
                    doc.IGST: -679.28,
                    doc.CGST: 0,
                    doc.SGST: 0,
                    doc.CESS: -1579.04,
                }
            }
        }

    def test_convert_to_internal_data_format(self):
        output = cdnr.to_canonical(copy.deepcopy(self.json_data))
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(cdnr.to_gov, process_mapped_data(copy.deepcopy(self.mapped_data)))
        self.assertListEqual(self.json_data, output)


class TestCDNUR(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                raw.TYPE: "B2CL",
                raw.NOTE_TYPE: "C",
                raw.NOTE_NUMBER: "533515",
                raw.NOTE_DATE: "23-09-2016",
                raw.POS: "03",
                raw.DOC_VALUE: 64646,
                raw.DIFF_PERCENTAGE: 0.65,
                raw.ITEMS: [
                    {
                        raw.INDEX: 1,
                        raw.ITEM_DETAILS: {
                            raw.TAX_RATE: 10,
                            raw.TAXABLE_VALUE: 5225.28,
                            raw.IGST: 339.64,
                            raw.CESS: 789.52,
                        },
                    }
                ],
            }
        ]

        cls.mapped_data = {
            SubCategory.CDNUR.value: {
                "533515": {
                    doc.TRANSACTION_TYPE: "Credit Note",
                    doc.DOC_TYPE: "B2CL",
                    doc.DOC_NUMBER: "533515",
                    doc.DOC_DATE: "2016-09-23",
                    doc.DOC_VALUE: -64646,
                    doc.POS: "03-Punjab",
                    doc.DIFF_PERCENTAGE: 0.65,
                    doc.ITEMS: [
                        {
                            item.TAXABLE_VALUE: -5225.28,
                            item.IGST: -339.64,
                            item.CESS: -789.52,
                            doc.TAX_RATE: 10,
                        }
                    ],
                    doc.TAXABLE_VALUE: -5225.28,
                    doc.IGST: -339.64,
                    doc.CESS: -789.52,
                }
            }
        }

    def test_convert_to_internal_data_format(self):
        output = cdnur.to_canonical(copy.deepcopy(self.json_data))
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(cdnur.to_gov, process_mapped_data(copy.deepcopy(self.mapped_data)))
        self.assertListEqual(self.json_data, output)


class TestHSNSUM(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = {
            raw.HSN_DATA: [
                {
                    raw.INDEX: 1,
                    raw.HSN_CODE: "1010",
                    raw.DESCRIPTION: "Goods Description",
                    raw.UOM: "KGS",
                    raw.QUANTITY: 2.05,
                    raw.TAXABLE_VALUE: 10.23,
                    raw.IGST: 14.52,
                    raw.CESS: 500,
                    raw.TAX_RATE: 0.1,
                },
                {
                    raw.INDEX: 2,
                    raw.HSN_CODE: "1011",
                    raw.DESCRIPTION: "Goods Description",
                    raw.UOM: "NOS",
                    raw.QUANTITY: 2.05,
                    raw.TAXABLE_VALUE: 10.23,
                    raw.IGST: 14.52,
                    raw.CESS: 500,
                    raw.TAX_RATE: 5,
                },
            ]
        }

        cls.mapped_data = {
            SubCategory.HSN.value: {
                "1010 - KGS-KILOGRAMS - 0.1": {
                    doc.DOC_TYPE: SubCategory.HSN.value,
                    doc.HSN_CODE: "1010",
                    doc.DESCRIPTION: "Goods Description",
                    doc.UOM: "KGS-KILOGRAMS",
                    doc.QUANTITY: 2.05,
                    doc.TAXABLE_VALUE: 10.23,
                    doc.IGST: 14.52,
                    doc.CESS: 500,
                    doc.TAX_RATE: 0.1,
                    doc.DOC_VALUE: 524.75,
                },
                "1011 - NOS-NUMBERS - 5.0": {
                    doc.DOC_TYPE: SubCategory.HSN.value,
                    doc.HSN_CODE: "1011",
                    doc.DESCRIPTION: "Goods Description",
                    doc.UOM: "NOS-NUMBERS",
                    doc.QUANTITY: 2.05,
                    doc.TAXABLE_VALUE: 10.23,
                    doc.IGST: 14.52,
                    doc.CESS: 500,
                    doc.TAX_RATE: 5,
                    doc.DOC_VALUE: 524.75,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = hsn.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(hsn.to_gov, process_mapped_data(self.mapped_data))
        self.assertDictEqual(self.json_data, output)


class TestHSNSUM_With_Bifurcation(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = {
            raw.HSN_B2B: [
                {
                    raw.INDEX: 1,
                    raw.HSN_CODE: "1102",
                    raw.DESCRIPTION: "Goods Description",
                    raw.UOM: "BOX",
                    raw.QUANTITY: 2,
                    raw.TAXABLE_VALUE: 100,
                    raw.CGST: 0.5,
                    raw.SGST: 0.5,
                    raw.TAX_RATE: 1,
                }
            ],
            raw.HSN_B2C: [
                {
                    raw.INDEX: 1,
                    raw.HSN_CODE: "1301",
                    raw.DESCRIPTION: "Goods Description",
                    raw.UOM: "CTN",
                    raw.QUANTITY: 2,
                    raw.TAXABLE_VALUE: 100,
                    raw.IGST: 1,
                    raw.CESS: 10,
                    raw.TAX_RATE: 1,
                },
            ],
        }

        cls.mapped_data = {
            SubCategory.HSN_B2B.value: {
                "1102 - BOX-BOX - 1.0": {
                    doc.DOC_TYPE: SubCategory.HSN_B2B.value,
                    doc.HSN_CODE: "1102",
                    doc.DESCRIPTION: "Goods Description",
                    doc.UOM: "BOX-BOX",
                    doc.QUANTITY: 2,
                    doc.TAXABLE_VALUE: 100,
                    doc.CGST: 0.5,
                    doc.SGST: 0.5,
                    doc.TAX_RATE: 1,
                    doc.DOC_VALUE: 101,
                }
            },
            SubCategory.HSN_B2C.value: {
                "1301 - CTN-CARTONS - 1.0": {
                    doc.DOC_TYPE: SubCategory.HSN_B2C.value,
                    doc.HSN_CODE: "1301",
                    doc.DESCRIPTION: "Goods Description",
                    doc.UOM: "CTN-CARTONS",
                    doc.QUANTITY: 2,
                    doc.TAXABLE_VALUE: 100,
                    doc.IGST: 1,
                    doc.CESS: 10,
                    doc.TAX_RATE: 1,
                    doc.DOC_VALUE: 111,
                },
            },
        }

    def test_convert_to_internal_data_format(self):
        output = hsn.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(hsn.to_gov, process_mapped_data(self.mapped_data))
        self.assertDictEqual(self.json_data, output)


class TestAT(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                raw.POS: "05",
                raw.SUPPLY_TYPE: "INTER",
                raw.DIFF_PERCENTAGE: 0.65,
                raw.ITEMS: [
                    {
                        raw.TAX_RATE: 5,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.IGST: 9400,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.CESS: 500,
                    },
                    {
                        raw.TAX_RATE: 6,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.IGST: 9400,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.CESS: 500,
                    },
                ],
            },
            {
                raw.POS: "24",
                raw.SUPPLY_TYPE: "INTER",
                raw.DIFF_PERCENTAGE: 0.65,
                raw.ITEMS: [
                    {
                        raw.TAX_RATE: 5,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.IGST: 9400,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.CESS: 500,
                    },
                    {
                        raw.TAX_RATE: 6,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.IGST: 9400,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.CESS: 500,
                    },
                ],
            },
        ]

        cls.mapped_data = {
            SubCategory.AT.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        doc.POS: "05-Uttarakhand",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.IGST: 9400,
                        doc.CESS: 500,
                        doc.CGST: 0,
                        doc.SGST: 0,
                        doc.TAXABLE_VALUE: 100,
                        doc.TAX_RATE: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        doc.POS: "05-Uttarakhand",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.IGST: 9400,
                        doc.CESS: 500,
                        doc.CGST: 0,
                        doc.SGST: 0,
                        doc.TAXABLE_VALUE: 100,
                        doc.TAX_RATE: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        doc.POS: "24-Gujarat",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.IGST: 9400,
                        doc.CESS: 500,
                        doc.CGST: 0,
                        doc.SGST: 0,
                        doc.TAXABLE_VALUE: 100,
                        doc.TAX_RATE: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        doc.POS: "24-Gujarat",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.IGST: 9400,
                        doc.CESS: 500,
                        doc.CGST: 0,
                        doc.SGST: 0,
                        doc.TAXABLE_VALUE: 100,
                        doc.TAX_RATE: 6,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = advances.received_to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(
            advances.received_to_gov, process_mapped_data(self.mapped_data), COMPANY_GSTIN
        )
        self.assertListEqual(self.json_data, output)


class TestTXPD(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                raw.POS: "05",
                raw.SUPPLY_TYPE: "INTER",
                raw.DIFF_PERCENTAGE: 0.65,
                raw.ITEMS: [
                    {
                        raw.TAX_RATE: 5,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.IGST: 9400,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.CESS: 500,
                    },
                    {
                        raw.TAX_RATE: 6,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.IGST: 9400,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.CESS: 500,
                    },
                ],
            },
            {
                raw.POS: "24",
                raw.SUPPLY_TYPE: "INTER",
                raw.DIFF_PERCENTAGE: 0.65,
                raw.ITEMS: [
                    {
                        raw.TAX_RATE: 5,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.IGST: 9400,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.CESS: 500,
                    },
                    {
                        raw.TAX_RATE: 6,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.IGST: 9400,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.CESS: 500,
                    },
                ],
            },
        ]

        cls.mapped_data = {
            SubCategory.TXP.value: {
                "05-Uttarakhand - 5.0": [
                    {
                        doc.POS: "05-Uttarakhand",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.IGST: -9400,
                        doc.CESS: -500,
                        doc.CGST: 0,
                        doc.SGST: 0,
                        doc.TAXABLE_VALUE: -100,
                        doc.TAX_RATE: 5,
                    },
                ],
                "05-Uttarakhand - 6.0": [
                    {
                        doc.POS: "05-Uttarakhand",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.IGST: -9400,
                        doc.CESS: -500,
                        doc.CGST: 0,
                        doc.SGST: 0,
                        doc.TAXABLE_VALUE: -100,
                        doc.TAX_RATE: 6,
                    }
                ],
                "24-Gujarat - 5.0": [
                    {
                        doc.POS: "24-Gujarat",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.IGST: -9400,
                        doc.CESS: -500,
                        doc.CGST: 0,
                        doc.SGST: 0,
                        doc.TAXABLE_VALUE: -100,
                        doc.TAX_RATE: 5,
                    }
                ],
                "24-Gujarat - 6.0": [
                    {
                        doc.POS: "24-Gujarat",
                        doc.DIFF_PERCENTAGE: 0.65,
                        doc.IGST: -9400,
                        doc.CESS: -500,
                        doc.CGST: 0,
                        doc.SGST: 0,
                        doc.TAXABLE_VALUE: -100,
                        doc.TAX_RATE: 6,
                    }
                ],
            }
        }

    def test_convert_to_internal_data_format(self):
        output = advances.adjusted_to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(
            advances.adjusted_to_gov, process_mapped_data(self.mapped_data), COMPANY_GSTIN
        )
        self.assertListEqual(self.json_data, output)


class TestDOC_ISSUE(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            raw.DOC_ISSUE_DETAILS: [
                {
                    raw.DOC_ISSUE_NUMBER: 1,
                    raw.DOC_ISSUE_LIST: [
                        {
                            raw.INDEX: 1,
                            raw.FROM_SR: "1",
                            raw.TO_SR: "10",
                            raw.TOTAL_COUNT: 10,
                            raw.CANCELLED_COUNT: 0,
                            raw.NET_ISSUE: 10,
                        },
                        {
                            raw.INDEX: 2,
                            raw.FROM_SR: "11",
                            raw.TO_SR: "20",
                            raw.TOTAL_COUNT: 10,
                            raw.CANCELLED_COUNT: 0,
                            raw.NET_ISSUE: 10,
                        },
                    ],
                },
                {
                    raw.DOC_ISSUE_NUMBER: 2,
                    raw.DOC_ISSUE_LIST: [
                        {
                            raw.INDEX: 1,
                            raw.FROM_SR: "1",
                            raw.TO_SR: "10",
                            raw.TOTAL_COUNT: 10,
                            raw.CANCELLED_COUNT: 0,
                            raw.NET_ISSUE: 10,
                        },
                        {
                            raw.INDEX: 2,
                            raw.FROM_SR: "11",
                            raw.TO_SR: "20",
                            raw.TOTAL_COUNT: 10,
                            raw.CANCELLED_COUNT: 0,
                            raw.NET_ISSUE: 10,
                        },
                    ],
                },
            ]
        }
        cls.mapped_data = {
            SubCategory.DOC_ISSUE.value: {
                "Invoices for outward supply - 1": {
                    doc.DOC_TYPE: "Invoices for outward supply",
                    doc.FROM_SR: "1",
                    doc.TO_SR: "10",
                    doc.TOTAL_COUNT: 10,
                    doc.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
                "Invoices for outward supply - 11": {
                    doc.DOC_TYPE: "Invoices for outward supply",
                    doc.FROM_SR: "11",
                    doc.TO_SR: "20",
                    doc.TOTAL_COUNT: 10,
                    doc.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
                "Invoices for inward supply from unregistered person - 1": {
                    doc.DOC_TYPE: "Invoices for inward supply from unregistered person",
                    doc.FROM_SR: "1",
                    doc.TO_SR: "10",
                    doc.TOTAL_COUNT: 10,
                    doc.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
                "Invoices for inward supply from unregistered person - 11": {
                    doc.DOC_TYPE: "Invoices for inward supply from unregistered person",
                    doc.FROM_SR: "11",
                    doc.TO_SR: "20",
                    doc.TOTAL_COUNT: 10,
                    doc.CANCELLED_COUNT: 0,
                    "net_issue": 10,
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = doc_issue.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(doc_issue.to_gov, process_mapped_data(self.mapped_data))
        self.assertDictEqual(self.json_data, output)


class TestSUPECOM(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = {
            raw.SUPECOM_52: [
                {
                    raw.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    raw.NET_TAXABLE_VALUE: 10000,
                    "igst": 1000,
                    "cgst": 0,
                    "sgst": 0,
                    "cess": 0,
                }
            ],
            raw.SUPECOM_9_5: [
                {
                    raw.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    raw.NET_TAXABLE_VALUE: 10000,
                    "igst": 1000,
                    "cgst": 0,
                    "sgst": 0,
                    "cess": 0,
                }
            ],
        }

        cls.mapped_data = {
            SubCategory.SUPECOM_52.value: {
                "20ALYPD6528PQC5": {
                    doc.DOC_TYPE: SubCategory.SUPECOM_52.value,
                    doc.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    doc.TAXABLE_VALUE: 10000,
                    doc.IGST: 1000,
                    doc.CGST: 0,
                    doc.SGST: 0,
                    doc.CESS: 0,
                }
            },
            SubCategory.SUPECOM_9_5.value: {
                "20ALYPD6528PQC5": {
                    doc.DOC_TYPE: SubCategory.SUPECOM_9_5.value,
                    doc.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    doc.TAXABLE_VALUE: 10000,
                    doc.IGST: 1000,
                    doc.CGST: 0,
                    doc.SGST: 0,
                    doc.CESS: 0,
                }
            },
        }

    def test_convert_to_internal_data_format(self):
        output = supecom.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        output = strip_empty_of(supecom.to_gov, process_mapped_data(self.mapped_data))
        self.assertDictEqual(self.json_data, output)


##### ERROR JSON TEST CASES #####


class TestHSNSUMError(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.json_data = [
            {
                raw.HSN_DATA: [
                    {
                        raw.INDEX: 1,
                        raw.HSN_CODE: "1010",
                        raw.DESCRIPTION: "Goods Description",
                        raw.UOM: "KGS",
                        raw.QUANTITY: 2.05,
                        raw.TAXABLE_VALUE: 10.23,
                        raw.IGST: 14.52,
                        raw.CESS: 500,
                        raw.TAX_RATE: 0.1,
                    },
                ],
                raw.ERROR_CD: "RET191350",
                raw.ERROR_MSG: "Length of entered HSN code is not valid as per AATO",
            },
            {
                raw.HSN_DATA: [
                    {
                        raw.INDEX: 2,
                        raw.HSN_CODE: "1011",
                        raw.DESCRIPTION: "Goods Description",
                        raw.UOM: "NOS",
                        raw.QUANTITY: 2.05,
                        raw.TAXABLE_VALUE: 10.23,
                        raw.IGST: 14.52,
                        raw.CESS: 500,
                        raw.TAX_RATE: 5,
                    }
                ],
                raw.ERROR_CD: "RET191350",
                raw.ERROR_MSG: "Length of entered HSN code is not valid as per AATO",
            },
        ]

        cls.mapped_data = {
            SubCategory.HSN.value: {
                "1010 - KGS-KILOGRAMS - 0.1": {
                    doc.DOC_TYPE: SubCategory.HSN.value,
                    doc.HSN_CODE: "1010",
                    doc.DESCRIPTION: "Goods Description",
                    doc.UOM: "KGS-KILOGRAMS",
                    doc.QUANTITY: 2.05,
                    doc.TAXABLE_VALUE: 10.23,
                    doc.IGST: 14.52,
                    doc.CESS: 500,
                    doc.TAX_RATE: 0.1,
                    doc.DOC_VALUE: 524.75,
                    doc.ERROR_CD: "RET191350",
                    doc.ERROR_MSG: "HSN Code: 1010 - Length of entered HSN code is not valid as per AATO",
                },
                "1011 - NOS-NUMBERS - 5.0": {
                    doc.DOC_TYPE: SubCategory.HSN.value,
                    doc.HSN_CODE: "1011",
                    doc.DESCRIPTION: "Goods Description",
                    doc.UOM: "NOS-NUMBERS",
                    doc.QUANTITY: 2.05,
                    doc.TAXABLE_VALUE: 10.23,
                    doc.IGST: 14.52,
                    doc.CESS: 500,
                    doc.TAX_RATE: 5,
                    doc.DOC_VALUE: 524.75,
                    doc.ERROR_CD: "RET191350",
                    doc.ERROR_MSG: "HSN Code: 1011 - Length of entered HSN code is not valid as per AATO",
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = hsn.to_canonical(self.json_data)
        self.assertDictEqual(self.mapped_data, output)
