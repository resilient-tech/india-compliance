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

DELIVERY_NOTE_FIELDS = [
    {
        "fieldname": "distance",
        "label": "Distance (in km)",
        "fieldtype": "Int",
        "insert_after": "vehicle_no",
        "print_hide": 1,
        "description": (
            "Set as zero to update distance as per the e-Waybill portal (if available)"
        ),
    },
    {
        "fieldname": "gst_transporter_id",
        "label": "GST Transporter ID",
        "fieldtype": "Data",
        "insert_after": "transporter",
        "fetch_from": "transporter.gst_transporter_id",
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "mode_of_transport",
        "label": "Mode of Transport",
        "fieldtype": "Select",
        "options": "\nRoad\nAir\nRail\nShip",
        "default": "Road",
        "insert_after": "transporter_name",
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "gst_vehicle_type",
        "label": "GST Vehicle Type",
        "fieldtype": "Select",
        "options": "Regular\nOver Dimensional Cargo (ODC)",
        "depends_on": 'eval:["Road", "Ship"].includes(doc.mode_of_transport)',
        "read_only_depends_on": "eval: doc.mode_of_transport == 'Ship'",
        "default": "Regular",
        "insert_after": "lr_date",
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "ewaybill",
        "label": "e-Waybill No.",
        "fieldtype": "Data",
        "depends_on": "eval: doc.docstatus === 1 || doc.ewaybill",
        "allow_on_submit": 1,
        "insert_after": "customer_name",
        "translatable": 0,
        "no_copy": 1,
    },
]

SALES_INVOICE_FIELDS = [
    {
        "fieldname": "transporter_info",
        "label": "Transporter Info",
        "fieldtype": "Section Break",
        "insert_after": "terms",
        "collapsible": 1,
        "collapsible_depends_on": "transporter",
        "print_hide": 1,
    },
    {
        "fieldname": "transporter",
        "label": "Transporter",
        "fieldtype": "Link",
        "insert_after": "transporter_info",
        "options": "Supplier",
        "print_hide": 1,
    },
    {
        "fieldname": "driver",
        "label": "Driver",
        "fieldtype": "Link",
        "insert_after": "gst_transporter_id",
        "options": "Driver",
        "print_hide": 1,
    },
    {
        "fieldname": "lr_no",
        "label": "Transport Receipt No",
        "fieldtype": "Data",
        "insert_after": "driver",
        "print_hide": 1,
        "translatable": 0,
        "length": 30,
    },
    {
        "fieldname": "vehicle_no",
        "label": "Vehicle No",
        "fieldtype": "Data",
        "insert_after": "lr_no",
        "print_hide": 1,
        "translatable": 0,
        "length": 15,
    },
    {
        "fieldname": "transporter_col_break",
        "fieldtype": "Column Break",
        "insert_after": "distance",
    },
    {
        "fieldname": "transporter_name",
        "label": "Transporter Name",
        "fieldtype": "Small Text",
        "insert_after": "transporter_col_break",
        "fetch_from": "transporter.name",
        "read_only": 1,
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "driver_name",
        "label": "Driver Name",
        "fieldtype": "Small Text",
        "insert_after": "mode_of_transport",
        "fetch_from": "driver.full_name",
        "print_hide": 1,
        "translatable": 0,
    },
    {
        "fieldname": "lr_date",
        "label": "Transport Receipt Date",
        "fieldtype": "Date",
        "insert_after": "driver_name",
        "default": "Today",
        "print_hide": 1,
    },
]

E_WAYBILL_FIELDS = {
    "Sales Invoice": SALES_INVOICE_FIELDS + DELIVERY_NOTE_FIELDS,
    "Delivery Note": DELIVERY_NOTE_FIELDS,
}
