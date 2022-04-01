from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.constants.e_waybill import SUB_SUPPLY_TYPES


def add_spacing(string, interval):
    """
    Add spaces to string at specified intervals
    (https://stackoverflow.com/a/65979478/4767738)
    """

    string = str(string)
    return " ".join(string[i : i + interval] for i in range(0, len(string), interval))


def get_state(state_code):
    """Get state from State Code"""

    state_code = str(state_code)

    for state, code in STATE_NUMBERS.items():
        if code == state_code:
            return state


def get_sub_supply_type(code):
    return SUB_SUPPLY_TYPES[int(code)]
