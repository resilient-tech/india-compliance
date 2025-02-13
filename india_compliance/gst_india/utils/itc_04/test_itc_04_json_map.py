import copy

from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    GenerateGSTR1,
)
from india_compliance.gst_india.utils.itc_04 import (
    GovDataField,
    GovDataField_SE,
    ITC04_DataField,
    ITC04_ItemField,
    ITC04JsonKey,
)
from india_compliance.gst_india.utils.itc_04.itc_04_json_map import (
    FGReceived,
    RMSent,
)


def normalize_data(data):
    return GenerateGSTR1().normalize_data(data)


class TestFGReceived(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                GovDataField.JOB_WORKER_STATE_CODE.value: "24",
                GovDataField.JOB_WORKER_GSTIN.value: "24AABCD8856A8FG",
                GovDataField.ITEMS.value: [
                    {
                        GovDataField.JOB_WORK_CHALLAN_DATE.value: "12-06-2024",
                        GovDataField.ORIGINAL_CHALLAN_NUMBER.value: "124",
                        GovDataField.UOM.value: "BAG",
                        GovDataField.ORIGINAL_CHALLAN_DATE.value: "10-06-2024",
                        GovDataField.QUANTITY.value: 15,
                        GovDataField.NATURE_OF_JOB.value: "WORK",
                        GovDataField.JOB_WORK_CHALLAN_NUMBER.value: "1236",
                        GovDataField.DESCRIPTION.value: "New -17",
                    },
                    {
                        GovDataField.JOB_WORK_CHALLAN_DATE.value: "12-06-2024",
                        GovDataField.ORIGINAL_CHALLAN_NUMBER.value: "124",
                        GovDataField.UOM.value: "BAG",
                        GovDataField.ORIGINAL_CHALLAN_DATE.value: "10-06-2024",
                        GovDataField.QUANTITY.value: 10,
                        GovDataField.NATURE_OF_JOB.value: "WORK",
                        GovDataField.JOB_WORK_CHALLAN_NUMBER.value: "1236",
                        GovDataField.DESCRIPTION.value: "New -18",
                    },
                ],
            }
        ]
        cls.mapped_data = {
            ITC04JsonKey.FG_RECEIVED.value: {
                "124 - 1236": {
                    ITC04_DataField.ORIGINAL_CHALLAN_NUMBER.value: "124",
                    ITC04_DataField.JOB_WORK_CHALLAN_NUMBER.value: "1236",
                    ITC04_DataField.JOB_WORKER_GSTIN.value: "24AABCD8856A8FG",
                    ITC04_DataField.JOB_WORKER_STATE_CODE.value: "24-Gujarat",
                    ITC04_DataField.ITEMS.value: [
                        {
                            ITC04_DataField.ORIGINAL_CHALLAN_DATE.value: "10-06-2024",
                            ITC04_DataField.JOB_WORK_CHALLAN_DATE.value: "12-06-2024",
                            ITC04_ItemField.NATURE_OF_JOB.value: "WORK",
                            ITC04_ItemField.UOM.value: "BAG-BAGS",
                            ITC04_ItemField.QUANTITY.value: 15.0,
                            ITC04_ItemField.DESCRIPTION.value: "New -17",
                        },
                        {
                            ITC04_DataField.ORIGINAL_CHALLAN_DATE.value: "10-06-2024",
                            ITC04_DataField.JOB_WORK_CHALLAN_DATE.value: "12-06-2024",
                            ITC04_ItemField.NATURE_OF_JOB.value: "WORK",
                            ITC04_ItemField.UOM.value: "BAG-BAGS",
                            ITC04_ItemField.QUANTITY.value: 10.0,
                            ITC04_ItemField.DESCRIPTION.value: "New -18",
                        },
                    ],
                },
            }
        }

    def test_convert_to_internal_data_format(self):
        output = FGReceived().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        normalized_data = normalize_data(copy.deepcopy(self.mapped_data))
        output = FGReceived().convert_to_gov_data_format(
            normalized_data.get(ITC04JsonKey.FG_RECEIVED.value)
        )
        self.assertListEqual(self.json_data, output)


class TestRMSent(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.json_data = [
            {
                GovDataField.JOB_WORKER_STATE_CODE.value: "27",
                GovDataField_SE.ORIGINAL_CHALLAN_NUMBER.value: "A4",
                GovDataField_SE.ORIGINAL_CHALLAN_DATE.value: "12-09-2017",
                GovDataField_SE.ITEMS.value: [
                    {
                        GovDataField.GOODS_TYPE.value: "7b",
                        GovDataField.DESCRIPTION.value: "qwqwqwe",
                        GovDataField.UOM.value: "BTL",
                        GovDataField.QUANTITY.value: 1243,
                        GovDataField.TAXABLE_VALUE.value: 10.2,
                        GovDataField.CGST.value: 0,
                        GovDataField.SGST.value: 0,
                        GovDataField.IGST.value: 10,
                        GovDataField.CESS_AMOUNT.value: 0,
                    },
                ],
            }
        ]
        cls.mapped_data = {
            ITC04JsonKey.RM_SENT.value: {
                "A4": {
                    ITC04_DataField.JOB_WORKER_STATE_CODE.value: "27-Maharashtra",
                    ITC04_DataField.ORIGINAL_CHALLAN_NUMBER.value: "A4",
                    ITC04_DataField.ORIGINAL_CHALLAN_DATE.value: "12-09-2017",
                    ITC04_DataField.ITEMS.value: [
                        {
                            ITC04_ItemField.TAXABLE_VALUE.value: 10.2,
                            ITC04_ItemField.IGST.value: 10,
                            ITC04_ItemField.CGST.value: 0,
                            ITC04_ItemField.SGST.value: 0,
                            ITC04_ItemField.CESS_AMOUNT.value: 0,
                            ITC04_ItemField.UOM.value: "BTL-BOTTLES",
                            ITC04_ItemField.QUANTITY.value: 1243.0,
                            ITC04_ItemField.DESCRIPTION.value: "qwqwqwe",
                            ITC04_ItemField.GOODS_TYPE.value: "7b",
                        },
                    ],
                    ITC04_DataField.TAXABLE_VALUE.value: 10.2,
                    ITC04_DataField.IGST.value: 10,
                    ITC04_DataField.CGST.value: 0,
                    ITC04_DataField.SGST.value: 0,
                    ITC04_DataField.CESS_AMOUNT.value: 0,
                },
            },
        }

    def test_convert_to_internal_data_format(self):
        output = RMSent().convert_to_internal_data_format(self.json_data)
        self.assertDictEqual(self.mapped_data, output)

    def test_convert_to_gov_data_format(self):
        normalized_data = normalize_data(copy.deepcopy(self.mapped_data))
        output = RMSent().convert_to_gov_data_format(
            normalized_data.get(ITC04JsonKey.RM_SENT.value)
        )
        self.assertListEqual(self.json_data, output)
