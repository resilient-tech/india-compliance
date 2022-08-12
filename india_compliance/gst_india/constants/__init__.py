import re

from erpnext.stock.get_item_details import sales_doctypes

TIMEZONE = "Asia/Kolkata"

ABBREVIATIONS = {"SEZ", "GST", "CGST", "SGST", "IGST", "CESS", "HSN"}

GST_ACCOUNT_FIELDS = (
    "cgst_account",
    "sgst_account",
    "igst_account",
    "cess_account",
    "cess_non_advol_account",
)

GST_TAX_TYPES = tuple(field[:-8] for field in GST_ACCOUNT_FIELDS)

GST_PARTY_TYPES = ("Customer", "Supplier", "Company")

GST_CATEGORIES = {
    "Registered Regular": "B2B",
    "Registered Composition": "B2B",
    "Unregistered": "B2C",
    "SEZ": "SEZ",
    "Overseas": "EXP",
    "Deemed Export": "DEXP",
    "UIN Holders": "B2B",
    "Tax Deductor": "B2B",
}

OVERSEAS_GST_CATEGORIES = {"Overseas", "SEZ"}

EXPORT_TYPES = (
    "WOP",  # Without Payment of Tax [0]
    "WP",  # With Payment of Tax [1]
)

STATE_NUMBERS = {
    "Andaman and Nicobar Islands": "35",
    "Andhra Pradesh": "37",
    "Arunachal Pradesh": "12",
    "Assam": "18",
    "Bihar": "10",
    "Chandigarh": "04",
    "Chhattisgarh": "22",
    "Dadra and Nagar Haveli and Daman and Diu": "26",
    "Delhi": "07",
    "Goa": "30",
    "Gujarat": "24",
    "Haryana": "06",
    "Himachal Pradesh": "02",
    "Jammu and Kashmir": "01",
    "Jharkhand": "20",
    "Karnataka": "29",
    "Kerala": "32",
    "Ladakh": "38",
    "Lakshadweep Islands": "31",
    "Madhya Pradesh": "23",
    "Maharashtra": "27",
    "Manipur": "14",
    "Meghalaya": "17",
    "Mizoram": "15",
    "Nagaland": "13",
    "Odisha": "21",
    "Other Territory": "97",
    "Pondicherry": "34",
    "Punjab": "03",
    "Rajasthan": "08",
    "Sikkim": "11",
    "Tamil Nadu": "33",
    "Telangana": "36",
    "Tripura": "16",
    "Uttar Pradesh": "09",
    "Uttarakhand": "05",
    "West Bengal": "19",
}

# REGEX PATTERNS (https://developer.gst.gov.in/apiportal/taxpayer/returns)

NORMAL = (  # Normal but not TCS
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z1-9ABD-J]{1}[0-9A-Z]{1}$"
)
GOVT_DEPTID = r"^[0-9]{2}[A-Z]{4}[0-9]{5}[A-Z]{1}[0-9]{1}[Z]{1}[0-9]{1}$"
REGISTERED = re.compile(rf"{NORMAL}|{GOVT_DEPTID}")

# Not allowed in GSTR1 B2B
NRI_ID = r"^[0-9]{4}[A-Z]{3}[0-9]{5}[N][R][0-9A-Z]{1}$"
OIDAR = r"^[9][9][0-9]{2}[A-Z]{3}[0-9]{5}[O][S][0-9A-Z]{1}$"
OVERSEAS = re.compile(rf"{NRI_ID}|{OIDAR}")

UNBODY = re.compile(r"^[0-9]{4}[A-Z]{3}[0-9]{5}[UO]{1}[N][A-Z0-9]{1}$")
TDS = re.compile(r"^[0-9]{2}[A-Z]{4}[A-Z0-9]{1}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[D][0-9A-Z]$")

GSTIN_FORMATS = {
    "Registered Regular": REGISTERED,
    "Registered Composition": REGISTERED,
    "SEZ": REGISTERED,
    "Overseas": OVERSEAS,
    "Deemed Export": REGISTERED,
    "UIN Holders": UNBODY,
    "Tax Deductor": TDS,
}

TCS = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[C]{1}[0-9A-Z]{1}$")
PAN_NUMBER = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
PINCODE_FORMAT = re.compile(r"^[1-9][0-9]{5}$")

# Maximum length must be 16 characters. First character must be alphanumeric.
# Subsequent characters can be alphanumeric, hyphens or slashes.
GST_INVOICE_NUMBER_FORMAT = re.compile(r"^[^\W_][A-Za-z0-9\-\/]{0,15}$")

# used to extract Distance (whole number) from string
DISTANCE_REGEX = re.compile(r"\d+")

INVOICE_DOCTYPES = {"Sales Invoice", "Purchase Invoice"}
SALES_DOCTYPES = set(sales_doctypes)

BUG_REPORT_URL = "https://github.com/resilient-tech/india-compliance/issues/new"
