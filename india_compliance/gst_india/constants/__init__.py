import re

GST_ACCOUNT_FIELDS = (
    "cgst_account",
    "sgst_account",
    "igst_account",
    "cess_account",
    "cess_non_advol_account",
)

GST_CATEGORY = [
    "Registered Regular",
    "Registered Composition",
    "Unregistered",
    "SEZ",
    "Overseas",
    "Deemed Export",
    "UIN Holders",
    "Tax Deductor",
]

# URL Ref : https://developer.gst.gov.in/apiportal/taxpayer/returns

NORMAL = "^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}(?![C])[Z1-9A-J]{1}[0-9A-Z]{1}$"  # Normal but not TCS
GOVT_DEPTID = "^[0-9]{2}[A-Z]{4}[0-9]{5}[A-Z]{1}[0-9]{1}[Z]{1}[0-9]{1}$"
UNBODY = re.compile("^[0-9]{4}[A-Z]{3}[0-9]{5}[UO]{1}[N][A-Z0-9]{1}$")
TDS = re.compile("^[0-9]{2}[A-Z]{4}[A-Z0-9]{1}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[D][0-9A-Z]$")
# Not allowed in GSTR1 B2B
NRI_ID = "^[0-9]{4}[A-Z]{3}[0-9]{5}[N][R][0-9A-Z]{1}$"
OIDAR = "^[9][9][0-9]{2}[A-Z]{3}[0-9]{5}[O][S][0-9A-Z]{1}$"
TCS = re.compile("^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[C]{1}[0-9A-Z]{1}$")
PAN_NUMBER = re.compile("^[A-Z]{5}[0-9]{4}[A-Z]{1}$")

registered = re.compile(f"{NORMAL}|{GOVT_DEPTID}")
overseas = re.compile(f"{NRI_ID}|{OIDAR}")

GSTIN_FORMAT = {
    "Registered Regular": registered,
    "Registered Composition": registered,
    "SEZ": registered,
    "Overseas": overseas,
    "Deemed Export": registered,
    "UIN Holders": UNBODY,
    "Tax Deductor": TDS,
}

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
