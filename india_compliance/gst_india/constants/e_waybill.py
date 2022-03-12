TRANSPORT_MODES = {"Road": 1, "Rail": 2, "Air": 3, "Ship": 4}
VEHICLE_TYPES = {"Regular": "R", "Over Dimensional Cargo (ODC)": "O"}
SUPPLY_TYPE = {"Inward": "I", "Outward": "O"}
DOC_TYPE = {
    "Tax Invoice": "INV",
    "Bill of Supply": "BIL",
    "Bill of Entry": "BOE",
    "Delivery Challan": "CHL",
    "Others": "OTH",
}

E_WAYBILL_INVOICE = {
    "userGstin": "company_gstin",
    "supplyType": "supply_type",
    "subSupplyType": "sub_supply_type",
    "subSupplyDesc": "",  # sub_supply_desc needed only for sub_supply_type = OTHER
    "docType": "document_type",
    "docNo": "name",
    "docDate": "invoice_date",
    "transType": "transaction_type",
    "fromTrdName": "company",
    "fromGstin": "company_gstin",
    "fromAddr1": "from_address_1",
    "fromAddr2": "from_address_2",
    "fromPlace": "from_city",
    "fromPincode": "from_pincode",
    "fromStateCode": "from_state_code",
    "actualFromStateCode": "actual_from_state_code",
    "toTrdName": "customer_name",
    "toGstin": "billing_address_gstin",
    "toAddr1": "to_address_1",
    "toAddr2": "to_address_2",
    "toPlace": "to_city",
    "toPincode": "to_pincode",
    "toStateCode": "to_state_code",
    "actualToStateCode": "actual_to_state_code",
    "totalValue": "base_total",
    "cgstValue": "total_cgst_amount",
    "sgstValue": "total_sgst_amount",
    "igstValue": "total_igst_amount",
    "cessValue": "total_cess_amount",
    "TotNonAdvolVal": "total_cess_non_advol_amount",
    "OthValue": "rounding_adjustment",
    "totInvValue": "base_grand_total",
    "transMode": "mode_of_transport",
    "transDistance": "distance",
    "transporterName": "transporter_name",
    "transporterId": "transporter_gstin",
    "transDocNo": "lr_no",
    "transDocDate": "lr_date_str",
    "vehicleNo": "vehicle_no",
    "vehicleType": "vehicle_type",
    "itemList": "",
}

E_WAYBILL_ITEM = {
    "productName": "",
    "productDesc": "item_name",
    "hsnCode": "hsn_code",
    "qtyUnit": "uom",  # TODO: Imporve UOM to accomodate GST Convensions
    "quantity": "qty",
    "taxableAmount": "taxable_value",
    "sgstRate": "sgst_rate",
    "cgstRate": "cgst_rate",
    "igstRate": "igst_rate",
    "cessRate": "cess_rate",
    "cessNonAdvol": "cess_non_advol_rate",
}
