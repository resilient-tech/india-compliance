# Just for reference
# SUPPLY_TYPES = {"Inward": "I", "Outward": "O"}
#
# DOCUMENT_TYPES = {
#     "Tax Invoice": "INV",
#     "Bill of Supply": "BIL",
#     "Bill of Entry": "BOE",
#     "Delivery Challan": "CHL",
#     "Others": "OTH",
# }
#
# DATETIME_FORMAT = "%d/%m/%Y %I:%M:%S %p"
selling_address = {
    "bill_from": "company_address",
    "bill_to": "customer_address",
    "ship_from": "dispatch_address_name",
    "ship_to": "shipping_address_name",
}

buying_address = {
    "bill_from": "supplier_address",
    "bill_to": "billing_address",
    "ship_from": "supplier_address",
    "ship_to": "shipping_address",
}

ADDRESS_FIELDS = {
    "Sales Invoice": selling_address,
    "Purchase Invoice": buying_address,
    "Delivery Note": selling_address,
    "Purchase Receipt": buying_address,
}
PERMITTED_DOCTYPES = list(ADDRESS_FIELDS.keys())

CANCEL_REASON_CODES = {
    "Duplicate": "1",
    "Order Cancelled": "2",
    "Data Entry Mistake": "3",
    "Others": "4",
}

UPDATE_VEHICLE_REASON_CODES = {
    "Due to Break Down": "1",
    "Due to Trans Shipment": "2",
    "First Time": "4",
    "Others": "3",
}

EXTEND_VALIDITY_REASON_CODES = {
    "Natural Calamity": 1,
    "Law and Order Situation": 2,
    "Transshipment": 4,
    "Accident": 5,
    "Others": 99,
}

SUPPLY_TYPES = {
    "I": "Inward",
    "O": "Outward",
}

SUB_SUPPLY_TYPES = {
    "Supply": 1,
    "Import": 2,
    "Export": 3,
    "Job Work": 4,
    "For Own Use": 5,
    "Job Work Returns": 6,
    "Sales Return": 7,
    "Others": 8,
    "SKD/CKD": 9,
    "Line Sales": 10,
    "Recipient Not Known": 11,
    "Exhibition or Fairs": 12,
}


TRANSPORT_MODES = {"Road": 1, "Rail": 2, "Air": 3, "Ship": 4, "In Transit": 5}
TRANSPORT_TYPES = {
    1: "Regular",
    2: "Bill To - Ship To",
    3: "Bill From - Dispatch From",
    4: "Combination of 2 and 3",
}
VEHICLE_TYPES = {"Regular": "R", "Over Dimensional Cargo (ODC)": "O"}

TRANSIT_TYPES = {"Road": "R", "Warehouse": "W", "Others": "O"}
CONSIGNMENT_STATUS = {"In Movement": "M", "In Transit": "T"}

ITEM_LIMIT = 250
