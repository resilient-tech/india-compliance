from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.constants.e_waybill import SUB_SUPPLY_TYPES


def add_spacing(string, interval):
    """
    Add spaces to string at specified intervals
    (https://stackoverflow.com/a/65979478/4767738)
    """

    string = str(string)
    return " ".join(string[i : i + interval] for i in range(0, len(string), interval))


def get_state(state_number):
    """Get state from State Number"""

    state_number = str(state_number)

    for state, code in STATE_NUMBERS.items():
        if code == state_number:
            return state


def get_sub_supply_type(code):
    code = int(code)

    for sub_supply_type, code_number in SUB_SUPPLY_TYPES.items():
        if code_number == code:
            return sub_supply_type
