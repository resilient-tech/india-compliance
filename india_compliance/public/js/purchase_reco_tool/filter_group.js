frappe.provide("india_compliance");

india_compliance.FILTER_OPERATORS = {
    "=": (expected_value, value) => value == expected_value,
    "!=": (expected_value, value) => value != expected_value,
    ">": (expected_value, value) => value > expected_value,
    "<": (expected_value, value) => value < expected_value,
    ">=": (expected_value, value) => value >= expected_value,
    "<=": (expected_value, value) => value <= expected_value,
    like: (expected_value, value) => _like(expected_value, value),
    "not like": (expected_value, value) => !_like(expected_value, value),
    in: (expected_values, value) => expected_values.includes(value),
    "not in": (expected_values, value) => !expected_values.includes(value),
    is: (expected_value, value) => {
        if (expected_value === "set") {
            return !!value;
        } else {
            return !value;
        }
    },
};

class _Filter extends frappe.ui.Filter {
    set_conditions_from_config() {
        if (this.filter_list.filter_options) {
            Object.assign(this, this.filter_list.filter_options);
        }

        this.conditions = this.conditions.filter(
            condition => india_compliance.FILTER_OPERATORS[condition && condition[0]]
        );
    }
}

india_compliance.FilterGroup = class FilterGroup extends frappe.ui.FilterGroup {
    _push_new_filter(...args) {
        const Filter = frappe.ui.Filter;
        try {
            frappe.ui.Filter = _Filter;
            return super._push_new_filter(...args);
        } finally {
            frappe.ui.Filter = Filter;
        }
    }
};

function _like(expected_value, value) {
    expected_value = expected_value.toLowerCase();
    value = value.toLowerCase();

    if (!expected_value.endsWith("%")) return value.endsWith(expected_value.slice(1));

    if (!expected_value.startsWith("%"))
        return value.startsWith(expected_value.slice(0, -1));

    return value.includes(expected_value.slice(1, -1));
}
