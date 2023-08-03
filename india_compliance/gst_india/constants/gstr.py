import frappe

from india_compliance.gst_india.constants import STATE_NUMBERS

ORIGINAL_VS_AMENDED = {
    # original: amended
    "B2B": "B2BA",
    "CDNR": "CDNRA",
    "ISD": "ISDA",
    "IMPG": "",
    "IMPGSEZ": "",
}

# Map of API values to doctype values
API_VALUES_MAP = frappe._dict(
    {
        "Y_N_to_check": {"Y": 1, "N": 0},
        "yes_no": {"Y": "Yes", "N": "No"},
        "gst_category": {
            "R": "Regular",
            "SEZWP": "SEZ supplies with payment of tax",
            "SEZWOP": "SEZ supplies with out payment of tax",
            "DE": "Deemed exports",
            "CBW": "Intra-State Supplies attracting IGST",
        },
        "states": {value: f"{value}-{key}" for key, value in STATE_NUMBERS.items()},
        "note_type": {"C": "Credit Note", "D": "Debit Note"},
        "isd_type_2a": {"ISDCN": "ISD Credit Note", "ISD": "ISD Invoice"},
        "isd_type_2b": {"ISDC": "ISD Credit Note", "ISDI": "ISD Invoice"},
        "amend_type": {
            "R": "Receiver GSTIN Amended",
            "N": "Invoice Number Amended",
            "D": "Other Details Amended",
        },
        "diff_percentage": {
            1: 1,
            0.65: 0.65,
            None: 1,
        },
        "itc_unavailability_reason": {
            "P": "POS and supplier state are same but recipient state is different",
            "C": "Return filed post annual cut-off",
        },
    }
)
