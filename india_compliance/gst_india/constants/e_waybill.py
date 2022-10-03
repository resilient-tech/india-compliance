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


TRANSPORT_MODES = {"Road": 1, "Rail": 2, "Air": 3, "Ship": 4}
TRANSPORT_TYPES = {
    1: "Regular",
    2: "Bill To - Ship To",
    3: "Bill From - Dispatch From",
    4: "Combination of 2 and 3",
}
VEHICLE_TYPES = {"Regular": "R", "Over Dimensional Cargo (ODC)": "O"}

UOMS = {
    "BAG": "BAGS",
    "BAL": "BALE",
    "BDL": "BUNDLES",
    "BKL": "BUCKLES",
    "BOU": "BILLION OF UNITS",
    "BOX": "BOX",
    "BTL": "BOTTLES",
    "BUN": "BUNCHES",
    "CAN": "CANS",
    "CBM": "CUBIC METERS",
    "CCM": "CUBIC CENTIMETERS",
    "CMS": "CENTIMETERS",
    "CTN": "CARTONS",
    "DOZ": "DOZENS",
    "DRM": "DRUMS",
    "GGK": "GREAT GROSS",
    "GMS": "GRAMMES",
    "GRS": "GROSS",
    "GYD": "GROSS YARDS",
    "KGS": "KILOGRAMS",
    "KLR": "KILOLITRE",
    "KME": "KILOMETRE",
    "LTR": "LITRES",
    "MLT": "MILILITRE",
    "MTR": "METERS",
    "MTS": "METRIC TON",
    "NOS": "NUMBERS",
    "OTH": "OTHERS",
    "PAC": "PACKS",
    "PCS": "PIECES",
    "PRS": "PAIRS",
    "QTL": "QUINTAL",
    "ROL": "ROLLS",
    "SET": "SETS",
    "SQF": "SQUARE FEET",
    "SQM": "SQUARE METERS",
    "SQY": "SQUARE YARDS",
    "TBS": "TABLETS",
    "TGM": "TEN GROSS",
    "THD": "THOUSANDS",
    "TON": "TONNES",
    "TUB": "TUBES",
    "UGS": "US GALLONS",
    "UNT": "UNITS",
    "YDS": "YARDS",
}

ITEM_LIMIT = 250
