import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils.data import getdate

from india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_beta import get_period
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    GSTR1BooksData,
    convert_to_internal_data_format,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice

INVOICES = [
    {
        # Nil-Rated
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Unregistered Customer",
        "place_of_supply": "29-Karnataka",
        "is_out_state": 1,
        "items": [
            {
                "item_code": "_Test Nil Rated Item",
                "rate": 90,
                "qty": 500,
            },
        ],
    },
    {
        # B2CL
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Unregistered Customer",
        "place_of_supply": "29-Karnataka",
        "is_out_state": 1,
        "items": [
            {
                "item_code": "_Test Trading Goods 1",
                "rate": 1000,
                "qty": 450,
            },
        ],
    },
    {
        # B2CS
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Unregistered Customer",
        "place_of_supply": "24-Gujarat",
        "is_in_state": 1,
        "items": [
            {
                "item_code": "_Test Trading Goods 1",
                "rate": 10,
                "qty": 50,
            },
        ],
    },
    {
        # B2B Regular
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Registered Composition Customer",
        "place_of_supply": "24-Gujarat",
        "is_out_state": 0,
        "items": [
            {
                "item_code": "_Test Trading Goods 1",
                "rate": 200,
                "qty": 210,
            },
        ],
    },
    {
        # SEZWOP
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Registered Customer",
        "place_of_supply": "29-Karnataka",
        "is_export_with_gst": 0,
        "gst_category": "SEZ",
        "items": [
            {
                "item_code": "_Test Trading Goods 1",
                "rate": 520,
                "qty": 80,
            }
        ],
    },
    {
        # SEZWP
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Registered Customer",
        "place_of_supply": "29-Karnataka",
        "is_out_state": 1,
        "gst_category": "SEZ",
        "is_export_with_gst": 1,
        "items": [
            {
                "item_code": "_Test Trading Goods 1",
                "rate": 500,
                "qty": 50,
            }
        ],
    },
    {
        # EXPWOP
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Foreign Customer",
        "place_of_supply": "96-Other Countries",
        "items": [
            {
                "item_code": "_Test Trading Goods 1",
                "rate": 110,
                "qty": 40,
            },
        ],
    },
    {
        # EXPWP
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Foreign Customer",
        "place_of_supply": "96-Other Countries",
        "is_export_with_gst": 1,
        "items": [
            {
                "item_code": "_Test Trading Goods 1",
                "rate": 520,
                "qty": 100,
            },
        ],
    },
    {
        # CDNUR
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Foreign Customer",
        "place_of_supply": "96-Other Countries",
        "is_return": 1,
        "items": [
            {
                "item_code": "_Test Trading Goods 1",
                "rate": 500,
                "qty": -120,
            },
        ],
    },
    {
        # CDNR
        "company_gstin": "24AAQCA8719H1ZC",
        "customer": "_Test Registered Composition Customer",
        "place_of_supply": "29-Karnataka",
        "is_return": 1,
        "is_out_state": 1,
        "items": [
            {
                "item_code": "_Test Trading Goods 1",
                "rate": 500,
                "qty": -100,
            },
        ],
    },
]

GSTR1_JSON = {
    "gstin": "24AAQCA8719H1ZC",
    "fp": "062024",
    "b2b": [
        {
            "ctin": "24AANCA4892J1Z8",
            "inv": [
                {
                    "inum": "SINV-19-01064",
                    "idt": "06-06-2024",
                    "val": 29500,
                    "pos": "29",
                    "rchrg": "N",
                    "inv_typ": "SEWP",
                    "itms": [
                        {
                            "num": 1,
                            "itm_det": {
                                "rt": 18,
                                "txval": 25000,
                                "iamt": 4500,
                                "camt": 0,
                                "samt": 0,
                                "csamt": 0,
                            },
                        }
                    ],
                },
                {
                    "inum": "SINV-19-01063",
                    "idt": "06-06-2024",
                    "val": 35000,
                    "pos": "29",
                    "rchrg": "N",
                    "inv_typ": "SEWOP",
                    "itms": [
                        {
                            "num": 1,
                            "itm_det": {
                                "rt": 0,
                                "txval": 35000,
                                "iamt": 0,
                                "camt": 0,
                                "samt": 0,
                                "csamt": 0,
                            },
                        }
                    ],
                },
            ],
        }
    ],
    "b2cl": [
        {
            "pos": "29",
            "inv": [
                {
                    "inum": "SINV-19-01060",
                    "idt": "06-06-2024",
                    "val": 531000,
                    "itms": [
                        {
                            "num": 1,
                            "itm_det": {
                                "rt": 18,
                                "txval": 450000,
                                "iamt": 81000,
                                "csamt": 0,
                            },
                        }
                    ],
                }
            ],
        }
    ],
    "exp": [
        {
            "exp_typ": "WPAY",
            "inv": [
                {
                    "inum": "SINV-19-01066",
                    "idt": "06-06-2024",
                    "val": 50000,
                    "itms": [{"txval": 50000, "rt": 0, "iamt": 0, "csamt": 0}],
                }
            ],
        },
        {
            "exp_typ": "WOPAY",
            "inv": [
                {
                    "inum": "SINV-19-01065",
                    "idt": "06-06-2024",
                    "val": 4000,
                    "itms": [{"txval": 4000, "rt": 0, "iamt": 0, "csamt": 0}],
                }
            ],
        },
    ],
    "b2cs": [
        {
            "txval": 500,
            "typ": "OE",
            "pos": "24",
            "rt": 18,
            "iamt": 0,
            "camt": 45,
            "samt": 45,
            "csamt": 0,
            "sply_ty": "INTRA",
        },
        {
            "txval": -40000,
            "typ": "OE",
            "pos": "29",
            "rt": 18,
            "iamt": -7200,
            "camt": 0,
            "samt": 0,
            "csamt": 0,
            "sply_ty": "INTRA",
        },
    ],
    "nil": {
        "inv": [
            {
                "sply_ty": "Inter-State to unregistered persons",
                "expt_amt": 0,
                "nil_amt": 45000,
                "ngsup_amt": 0,
            },
            {
                "sply_ty": "Intra-State to unregistered persons",
                "expt_amt": 0,
                "nil_amt": 40000,
                "ngsup_amt": 0,
            },
        ]
    },
    "cdnur": [
        {
            "typ": "EXPWOP",
            "ntty": "C",
            "nt_num": "SINV-19-01067",
            "nt_dt": "06-06-2024",
            "val": 50000,
            "pos": "96",
            "itms": [
                {"num": 1, "itm_det": {"rt": 0, "txval": 50000, "iamt": 0, "csamt": 0}}
            ],
        }
    ],
    "hsn": {
        "data": [
            {
                "num": 1,
                "hsn_sc": "61149090",
                "desc": "OTHER GARMENTS, KNITTED OR CRO",
                "uqc": "NOS",
                "qty": 810,
                "txval": 124000,
                "iamt": 0,
                "camt": 0,
                "samt": 0,
                "csamt": 0,
                "rt": 0,
            },
            {
                "num": 2,
                "hsn_sc": "61149090",
                "desc": "OTHER GARMENTS, KNITTED OR CRO",
                "uqc": "NOS",
                "qty": 470,
                "txval": 435500,
                "iamt": 78300,
                "camt": 45,
                "samt": 45,
                "csamt": 0,
                "rt": 18,
            },
        ]
    },
    "doc_issue": {
        "doc_det": [
            {
                "doc_num": 5,
                "docs": [
                    {
                        "num": 1,
                        "from": "SINV-19-01067",
                        "to": "SINV-19-01068",
                        "totnum": 2,
                        "cancel": 0,
                        "net_issue": 2,
                    }
                ],
            },
            {
                "doc_num": 1,
                "docs": [
                    {
                        "num": 1,
                        "from": "SINV-19-01059",
                        "to": "SINV-19-01066",
                        "totnum": 8,
                        "cancel": 0,
                        "net_issue": 8,
                    }
                ],
            },
        ]
    },
}

EXPECTED_RECONCILE_DATA = {
    "SEZ With Payment of Tax": [
        {
            "transaction_type": "Invoice",
            "customer_gstin": "24AANCA4892J1Z8",
            "customer_name": "_Test Registered Customer",
            "document_value": 29500.0,
            "place_of_supply": "29-Karnataka",
            "reverse_charge": "N",
            "document_type": "SEZ supplies with payment",
            "total_taxable_value": 25000.0,
            "total_igst_amount": 4500.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": "24AANCA4892J1Z8",
                "customer_name": "_Test Registered Customer",
                "document_value": 29500.0,
                "place_of_supply": "29-Karnataka",
                "reverse_charge": "N",
                "document_type": "SEZ supplies with payment",
                "total_taxable_value": 25000.0,
                "total_igst_amount": 4500.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 25000.0,
                        "igst_amount": 4500.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "transaction_type": "Invoice",
            "customer_gstin": "24AANCA4892J1Z8",
            "customer_name": "_Test Registered Customer",
            "document_value": 29500.0,
            "place_of_supply": "29-Karnataka",
            "reverse_charge": "N",
            "document_type": "SEZ supplies with payment",
            "total_taxable_value": 25000.0,
            "total_igst_amount": 4500.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": "24AANCA4892J1Z8",
                "customer_name": "_Test Registered Customer",
                "document_value": 29500.0,
                "place_of_supply": "29-Karnataka",
                "reverse_charge": "N",
                "document_type": "SEZ supplies with payment",
                "total_taxable_value": 25000.0,
                "total_igst_amount": 4500.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 25000.0,
                        "igst_amount": 4500.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "customer_gstin": "24AANCA4892J1Z8",
            "customer_name": "_Test Registered Customer",
            "document_date": "2024-06-06",
            "document_value": -29500.0,
            "place_of_supply": "29-Karnataka",
            "reverse_charge": "N",
            "document_type": "SEZ supplies with payment",
            "total_taxable_value": -25000.0,
            "total_igst_amount": -4500.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "match_status": "Missing in Books",
            "differences": [],
            "books": {},
            "gov": {
                "customer_gstin": "24AANCA4892J1Z8",
                "customer_name": "_Test Registered Customer",
                "document_date": "2024-06-06",
                "document_value": 29500,
                "place_of_supply": "29-Karnataka",
                "reverse_charge": "N",
                "document_type": "SEZ supplies with payment",
                "items": [
                    {
                        "taxable_value": 25000,
                        "igst_amount": 4500,
                        "cgst_amount": 0,
                        "sgst_amount": 0,
                        "cess_amount": 0,
                        "tax_rate": 18,
                    }
                ],
                "total_taxable_value": 25000,
                "total_igst_amount": 4500,
                "total_cgst_amount": 0,
                "total_sgst_amount": 0,
                "total_cess_amount": 0,
            },
        },
    ],
    "SEZ Without Payment of Tax": [
        {
            "transaction_type": "Invoice",
            "customer_gstin": "24AANCA4892J1Z8",
            "customer_name": "_Test Registered Customer",
            "document_value": 41600.0,
            "place_of_supply": "29-Karnataka",
            "reverse_charge": "N",
            "document_type": "SEZ supplies without payment",
            "total_taxable_value": 41600.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": "24AANCA4892J1Z8",
                "customer_name": "_Test Registered Customer",
                "document_value": 41600.0,
                "place_of_supply": "29-Karnataka",
                "reverse_charge": "N",
                "document_type": "SEZ supplies without payment",
                "total_taxable_value": 41600.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 41600.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "transaction_type": "Invoice",
            "customer_gstin": "24AANCA4892J1Z8",
            "customer_name": "_Test Registered Customer",
            "document_value": 41600.0,
            "place_of_supply": "29-Karnataka",
            "reverse_charge": "N",
            "document_type": "SEZ supplies without payment",
            "total_taxable_value": 41600.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": "24AANCA4892J1Z8",
                "customer_name": "_Test Registered Customer",
                "document_value": 41600.0,
                "place_of_supply": "29-Karnataka",
                "reverse_charge": "N",
                "document_type": "SEZ supplies without payment",
                "total_taxable_value": 41600.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 41600.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "customer_gstin": "24AANCA4892J1Z8",
            "customer_name": "_Test Registered Customer",
            "document_date": "2024-06-06",
            "document_value": -35000.0,
            "place_of_supply": "29-Karnataka",
            "reverse_charge": "N",
            "document_type": "SEZ supplies without payment",
            "total_taxable_value": -35000.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "match_status": "Missing in Books",
            "differences": [],
            "books": {},
            "gov": {
                "customer_gstin": "24AANCA4892J1Z8",
                "customer_name": "_Test Registered Customer",
                "document_date": "2024-06-06",
                "document_value": 35000,
                "place_of_supply": "29-Karnataka",
                "reverse_charge": "N",
                "document_type": "SEZ supplies without payment",
                "items": [
                    {
                        "taxable_value": 35000,
                        "igst_amount": 0,
                        "cgst_amount": 0,
                        "sgst_amount": 0,
                        "cess_amount": 0,
                        "tax_rate": 0,
                    }
                ],
                "total_taxable_value": 35000,
                "total_igst_amount": 0,
                "total_cgst_amount": 0,
                "total_sgst_amount": 0,
                "total_cess_amount": 0,
            },
        },
    ],
    "Export With Payment of Tax": [
        {
            "transaction_type": "Invoice",
            "customer_gstin": None,
            "customer_name": "_Test Foreign Customer",
            "document_value": 52000.0,
            "place_of_supply": "96-Other Countries",
            "reverse_charge": "N",
            "document_type": "WPAY",
            "total_taxable_value": 52000.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": None,
                "customer_name": "_Test Foreign Customer",
                "document_value": 52000.0,
                "place_of_supply": "96-Other Countries",
                "reverse_charge": "N",
                "document_type": "WPAY",
                "total_taxable_value": 52000.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 52000.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "transaction_type": "Invoice",
            "customer_gstin": None,
            "customer_name": "_Test Foreign Customer",
            "document_value": 52000.0,
            "place_of_supply": "96-Other Countries",
            "reverse_charge": "N",
            "document_type": "WPAY",
            "total_taxable_value": 52000.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": None,
                "customer_name": "_Test Foreign Customer",
                "document_value": 52000.0,
                "place_of_supply": "96-Other Countries",
                "reverse_charge": "N",
                "document_type": "WPAY",
                "total_taxable_value": 52000.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 52000.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "document_type": "WPAY",
            "document_date": "2024-06-06",
            "document_value": -50000.0,
            "total_taxable_value": -50000.0,
            "total_igst_amount": 0.0,
            "total_cess_amount": 0.0,
            "match_status": "Missing in Books",
            "differences": [],
            "books": {},
            "gov": {
                "document_type": "WPAY",
                "document_date": "2024-06-06",
                "document_value": 50000,
                "items": [
                    {
                        "taxable_value": 50000,
                        "igst_amount": 0,
                        "cess_amount": 0,
                        "tax_rate": 0,
                    }
                ],
                "total_taxable_value": 50000,
                "total_igst_amount": 0,
                "total_cess_amount": 0,
            },
        },
    ],
    "Export Without Payment of Tax": [
        {
            "transaction_type": "Invoice",
            "customer_gstin": None,
            "customer_name": "_Test Foreign Customer",
            "document_value": 4400.0,
            "place_of_supply": "96-Other Countries",
            "reverse_charge": "N",
            "document_type": "WOPAY",
            "total_taxable_value": 4400.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": None,
                "customer_name": "_Test Foreign Customer",
                "document_value": 4400.0,
                "place_of_supply": "96-Other Countries",
                "reverse_charge": "N",
                "document_type": "WOPAY",
                "total_taxable_value": 4400.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 4400.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "transaction_type": "Invoice",
            "customer_gstin": None,
            "customer_name": "_Test Foreign Customer",
            "document_value": 4400.0,
            "place_of_supply": "96-Other Countries",
            "reverse_charge": "N",
            "document_type": "WOPAY",
            "total_taxable_value": 4400.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": None,
                "customer_name": "_Test Foreign Customer",
                "document_value": 4400.0,
                "place_of_supply": "96-Other Countries",
                "reverse_charge": "N",
                "document_type": "WOPAY",
                "total_taxable_value": 4400.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 4400.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "document_type": "WOPAY",
            "document_date": "2024-06-06",
            "document_value": -4000.0,
            "total_taxable_value": -4000.0,
            "total_igst_amount": 0.0,
            "total_cess_amount": 0.0,
            "match_status": "Missing in Books",
            "differences": [],
            "books": {},
            "gov": {
                "document_type": "WOPAY",
                "document_date": "2024-06-06",
                "document_value": 4000,
                "items": [
                    {
                        "taxable_value": 4000,
                        "igst_amount": 0,
                        "cess_amount": 0,
                        "tax_rate": 0,
                    }
                ],
                "total_taxable_value": 4000,
                "total_igst_amount": 0,
                "total_cess_amount": 0,
            },
        },
    ],
    "B2C (Large)": [
        {
            "transaction_type": "Invoice",
            "customer_gstin": None,
            "customer_name": "_Test Unregistered Customer",
            "document_value": 531000.0,
            "place_of_supply": "29-Karnataka",
            "reverse_charge": "N",
            "document_type": None,
            "total_taxable_value": 450000.0,
            "total_igst_amount": 81000.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": None,
                "customer_name": "_Test Unregistered Customer",
                "document_value": 531000.0,
                "place_of_supply": "29-Karnataka",
                "reverse_charge": "N",
                "document_type": None,
                "total_taxable_value": 450000.0,
                "total_igst_amount": 81000.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 450000.0,
                        "igst_amount": 81000.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "transaction_type": "Invoice",
            "customer_gstin": None,
            "customer_name": "_Test Unregistered Customer",
            "document_value": 531000.0,
            "place_of_supply": "29-Karnataka",
            "reverse_charge": "N",
            "document_type": None,
            "total_taxable_value": 450000.0,
            "total_igst_amount": 81000.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": None,
                "customer_name": "_Test Unregistered Customer",
                "document_value": 531000.0,
                "place_of_supply": "29-Karnataka",
                "reverse_charge": "N",
                "document_type": None,
                "total_taxable_value": 450000.0,
                "total_igst_amount": 81000.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": 450000.0,
                        "igst_amount": 81000.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "place_of_supply": "29-Karnataka",
            "document_type": "B2C (Large)",
            "document_date": "2024-06-06",
            "document_value": -531000.0,
            "total_taxable_value": -450000.0,
            "total_igst_amount": -81000.0,
            "total_cess_amount": 0.0,
            "match_status": "Missing in Books",
            "differences": [],
            "books": {},
            "gov": {
                "place_of_supply": "29-Karnataka",
                "document_type": "B2C (Large)",
                "document_date": "2024-06-06",
                "document_value": 531000,
                "items": [
                    {
                        "taxable_value": 450000,
                        "igst_amount": 81000,
                        "cess_amount": 0,
                        "tax_rate": 18,
                    }
                ],
                "total_taxable_value": 450000,
                "total_igst_amount": 81000,
                "total_cess_amount": 0,
            },
        },
    ],
    "B2C (Others)": [
        {
            "total_taxable_value": -60000.0,
            "document_type": "OE",
            "place_of_supply": "29-Karnataka",
            "tax_rate": 18,
            "total_igst_amount": -10800.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "match_status": "Mismatch",
            "differences": ["Total Taxable Value", "Total Igst Amount"],
            "books": {
                "customer_name": "_Test Registered Composition Customer",
                "document_type": "OE",
                "transaction_type": "Credit Note",
                "place_of_supply": "29-Karnataka",
                "tax_rate": 36.0,
                "ecommerce_gstin": None,
                "total_taxable_value": -100000.0,
                "total_igst_amount": -18000.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
            },
            "gov": {
                "total_taxable_value": -40000,
                "document_type": "OE",
                "place_of_supply": "29-Karnataka",
                "tax_rate": 18,
                "total_igst_amount": -7200,
                "total_cgst_amount": 0,
                "total_sgst_amount": 0,
                "total_cess_amount": 0,
            },
        },
        {
            "total_taxable_value": 500.0,
            "document_type": "OE",
            "place_of_supply": "24-Gujarat",
            "tax_rate": 18,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 45.0,
            "total_sgst_amount": 45.0,
            "total_cess_amount": 0.0,
            "match_status": "Mismatch",
            "differences": [
                "Total Taxable Value",
                "Total Cgst Amount",
                "Total Sgst Amount",
            ],
            "books": {
                "customer_name": "_Test Unregistered Customer",
                "document_type": "OE",
                "transaction_type": "Invoice",
                "place_of_supply": "24-Gujarat",
                "tax_rate": 36.0,
                "ecommerce_gstin": None,
                "total_taxable_value": 1000.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 90.0,
                "total_sgst_amount": 90.0,
                "total_cess_amount": 0.0,
            },
            "gov": {
                "total_taxable_value": 500,
                "document_type": "OE",
                "place_of_supply": "24-Gujarat",
                "tax_rate": 18,
                "total_igst_amount": 0,
                "total_cgst_amount": 45,
                "total_sgst_amount": 45,
                "total_cess_amount": 0,
            },
        },
    ],
    "Nil-Rated, Exempted, Non-GST": [
        {
            "document_type": "Intra-State to unregistered persons",
            "exempted_amount": 0.0,
            "nil_rated_amount": 44000.0,
            "non_gst_amount": 0.0,
            "total_taxable_value": 44000.0,
            "match_status": "Mismatch",
            "differences": ["Nil Rated Amount", "Total Taxable Value"],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": None,
                "customer_name": "_Test Registered Composition Customer",
                "document_value": 84000.0,
                "place_of_supply": "24-Gujarat",
                "reverse_charge": "N",
                "document_type": "Intra-State to unregistered persons",
                "total_taxable_value": 84000.0,
                "nil_rated_amount": 84000.0,
                "exempted_amount": 0,
                "non_gst_amount": 0,
            },
            "gov": {
                "document_type": "Intra-State to unregistered persons",
                "exempted_amount": 0,
                "nil_rated_amount": 40000,
                "non_gst_amount": 0,
                "total_taxable_value": 40000,
            },
        },
        {
            "document_type": "Inter-State to unregistered persons",
            "exempted_amount": 0.0,
            "nil_rated_amount": 45000.0,
            "non_gst_amount": 0.0,
            "total_taxable_value": 45000.0,
            "match_status": "Mismatch",
            "differences": ["Nil Rated Amount", "Total Taxable Value"],
            "books": {
                "transaction_type": "Invoice",
                "customer_gstin": None,
                "customer_name": "_Test Unregistered Customer",
                "document_value": 90000.0,
                "place_of_supply": "29-Karnataka",
                "reverse_charge": "N",
                "document_type": "Inter-State to unregistered persons",
                "total_taxable_value": 90000.0,
                "nil_rated_amount": 90000.0,
                "exempted_amount": 0,
                "non_gst_amount": 0,
            },
            "gov": {
                "document_type": "Inter-State to unregistered persons",
                "exempted_amount": 0,
                "nil_rated_amount": 45000,
                "non_gst_amount": 0,
                "total_taxable_value": 45000,
            },
        },
    ],
    "Credit/Debit Notes (Unregistered)": [
        {
            "transaction_type": "Credit Note",
            "customer_gstin": None,
            "customer_name": "_Test Foreign Customer",
            "document_value": -60000.0,
            "place_of_supply": "96-Other Countries",
            "reverse_charge": "N",
            "document_type": "EXPWOP",
            "total_taxable_value": -60000.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Credit Note",
                "customer_gstin": None,
                "customer_name": "_Test Foreign Customer",
                "document_value": -60000.0,
                "place_of_supply": "96-Other Countries",
                "reverse_charge": "N",
                "document_type": "EXPWOP",
                "total_taxable_value": -60000.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": -60000.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "transaction_type": "Credit Note",
            "customer_gstin": None,
            "customer_name": "_Test Foreign Customer",
            "document_value": -60000.0,
            "place_of_supply": "96-Other Countries",
            "reverse_charge": "N",
            "document_type": "EXPWOP",
            "total_taxable_value": -60000.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "diff_percentage": 0.0,
            "match_status": "Missing in GSTR-1",
            "differences": [],
            "books": {
                "transaction_type": "Credit Note",
                "customer_gstin": None,
                "customer_name": "_Test Foreign Customer",
                "document_value": -60000.0,
                "place_of_supply": "96-Other Countries",
                "reverse_charge": "N",
                "document_type": "EXPWOP",
                "total_taxable_value": -60000.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "diff_percentage": 0,
                "items": [
                    {
                        "taxable_value": -60000.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            "gov": {},
        },
        {
            "document_type": "EXPWOP",
            "transaction_type": "Credit Note",
            "document_date": "2024-06-06",
            "document_value": 50000.0,
            "place_of_supply": "96-Other Countries",
            "total_taxable_value": 50000.0,
            "total_igst_amount": 0.0,
            "total_cess_amount": 0.0,
            "match_status": "Missing in Books",
            "differences": [],
            "books": {},
            "gov": {
                "document_type": "EXPWOP",
                "transaction_type": "Credit Note",
                "document_date": "2024-06-06",
                "document_value": -50000,
                "place_of_supply": "96-Other Countries",
                "items": [
                    {
                        "taxable_value": -50000,
                        "igst_amount": 0,
                        "cess_amount": 0,
                        "tax_rate": 0,
                    }
                ],
                "total_taxable_value": -50000,
                "total_igst_amount": 0,
                "total_cess_amount": 0,
            },
        },
    ],
    "HSN Summary": [
        {
            "hsn_code": "61149090",
            "description": "OTHER GARMENTS, KNITTED OR CRO",
            "uom": "NOS-NUMBERS",
            "quantity": 430.0,
            "total_taxable_value": 415500.0,
            "total_igst_amount": 74700.0,
            "total_cgst_amount": 45.0,
            "total_sgst_amount": 45.0,
            "total_cess_amount": 0.0,
            "tax_rate": 18,
            "document_value": 490290.0,
            "match_status": "Mismatch",
            "differences": [
                "Quantity",
                "Total Taxable Value",
                "Total Igst Amount",
                "Total Cgst Amount",
                "Total Sgst Amount",
                "Document Value",
            ],
            "books": {
                "hsn_code": "61149090",
                "description": "OTHER GARMENTS, KNITTED OR CROCHETED - OF OTHER TEXTILE MATERIALS : OTHER",
                "uom": "NOS-NUMBERS",
                "quantity": 900.0,
                "tax_rate": 18.0,
                "total_taxable_value": 851000.0,
                "total_igst_amount": 153000.0,
                "total_cgst_amount": 90.0,
                "total_sgst_amount": 90.0,
                "total_cess_amount": 0.0,
                "document_value": 1004180.0,
            },
            "gov": {
                "hsn_code": "61149090",
                "description": "OTHER GARMENTS, KNITTED OR CRO",
                "uom": "NOS-NUMBERS",
                "quantity": 470,
                "total_taxable_value": 435500,
                "total_igst_amount": 78300,
                "total_cgst_amount": 45,
                "total_sgst_amount": 45,
                "total_cess_amount": 0,
                "tax_rate": 18,
                "document_value": 513890,
            },
        },
        {
            "hsn_code": "61149090",
            "description": "OTHER GARMENTS, KNITTED OR CRO",
            "uom": "NOS-NUMBERS",
            "quantity": 810.0,
            "total_taxable_value": 126000.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
            "tax_rate": 0,
            "document_value": 126000.0,
            "match_status": "Mismatch",
            "differences": ["Quantity", "Total Taxable Value", "Document Value"],
            "books": {
                "hsn_code": "61149090",
                "description": "OTHER GARMENTS, KNITTED OR CROCHETED - OF OTHER TEXTILE MATERIALS : OTHER",
                "uom": "NOS-NUMBERS",
                "quantity": 1620.0,
                "tax_rate": 0.0,
                "total_taxable_value": 250000.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "document_value": 250000.0,
            },
            "gov": {
                "hsn_code": "61149090",
                "description": "OTHER GARMENTS, KNITTED OR CRO",
                "uom": "NOS-NUMBERS",
                "quantity": 810,
                "total_taxable_value": 124000,
                "total_igst_amount": 0,
                "total_cgst_amount": 0,
                "total_sgst_amount": 0,
                "total_cess_amount": 0,
                "tax_rate": 0,
                "document_value": 124000,
            },
        },
    ],
}


class TestGSTR1(FrappeTestCase):
    TODAY = getdate()
    GSTIN = "24AAQCA8719H1ZC"
    COMPANY = "_Test Indian Registered Company"
    filters = frappe._dict(
        {
            "company": COMPANY,
            "company_gstin": GSTIN,
            "from_date": TODAY,
            "to_date": TODAY,
        }
    )

    @classmethod
    @change_settings("GST Settings", {"analyze_filed_data": 1})
    def setUpClass(cls):
        super().setUpClass()
        TestGSTR1().create_sales_invoices()

    def create_sales_invoices(self):
        for invoice in INVOICES:
            create_sales_invoice(**invoice)

    def get_books_data(self):
        return GSTR1BooksData(self.filters).prepare_mapped_data()

    def get_gstr1_data(self):
        return convert_to_internal_data_format(GSTR1_JSON)

    def get_reconcile_data(self, gstr1_data, books_data):
        doc = frappe.new_doc("GSTR-1 Log")
        doc.is_latest_data = 0
        doc.filing_status = "Filed"

        period = get_period(self.TODAY.strftime("%B"), self.TODAY.year)
        doc.name = f"{period}-{self.GSTIN}"

        reconcile_data = doc.get_reconcile_gstr1_data(gstr1_data, books_data)

        return doc.normalize_data(reconcile_data)

    def test_gstr1(self):
        gstr1_data = self.get_gstr1_data()
        books_data = self.get_books_data()
        reconile_data = self.get_reconcile_data(gstr1_data, books_data)
        for subcategory, values in EXPECTED_RECONCILE_DATA.items():
            for index, row in enumerate(values):
                self.assertPartialDict(row, reconile_data[subcategory][index])

    def assertPartialDict(self, d1, d2):
        self.assertIsInstance(d1, dict, "First argument is not a dictionary")
        self.assertIsInstance(d2, dict, "Second argument is not a dictionary")

        if d1 != d2:
            for key in d1:
                if isinstance(d1[key], dict) and isinstance(d2[key], dict):
                    self.assertPartialDict(d1[key], d2[key])
                elif d1[key] != d2[key]:
                    standardMsg = f"{key}: {d1[key]} != {d2[key]}"
                    self.fail(standardMsg)
