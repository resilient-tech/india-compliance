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

FILTER_GROUP_BUTTON = $(
    `
    <div class="custom-button-group">
        <div class="filter-selector">
            <div class="btn-group">
                <button class="btn btn-default btn-sm filter-button">
                    <span class="filter-icon">
                        ${frappe.utils.icon("filter")}
                    </span>
                    <span class="button-label hidden-xs">
                        ${__("Filter")}
                    <span>
                </button>
                <button class="btn btn-default btn-sm filter-x-button" title="${__("Clear all filters")}">
                    <span class="filter-icon">
                        ${frappe.utils.icon("filter-x")}
                    </span>
                </button>
            </div>
        </div>
    </div>
    `
)

class _Filter extends frappe.ui.Filter {
    set_conditions_from_config() {
        let filter_options = this.filter_list.filter_options;
        if (filter_options) {
            filter_options = { ...filter_options };
            if (this.fieldname && this.fieldname !== "name")
                delete filter_options.fieldname;

            Object.assign(this, filter_options);
        }

        this.conditions = this.conditions.filter(
            condition => india_compliance.FILTER_OPERATORS[condition && condition[0]]
        );
    }
}

india_compliance.FilterGroup = class FilterGroup extends frappe.ui.FilterGroup {

    constructor(opts) {
        if (!opts.parent)
            frappe.throw(__("india_compliance.FilterGroup: Parent element not found"));

        FILTER_GROUP_BUTTON.appendTo(opts.parent);

        Object.assign(opts, {
            filter_button: FILTER_GROUP_BUTTON.find(".filter-button"),
            filter_x_button: FILTER_GROUP_BUTTON.find(".filter-x-button"),
        });

        super(opts);
    }

    _push_new_filter(...args) {
        const Filter = frappe.ui.Filter;
        try {
            frappe.ui.Filter = _Filter;
            return super._push_new_filter(...args);
        } finally {
            frappe.ui.Filter = Filter;
        }
    }

    set_clear_all_filters_event() {
        if (!this.filter_x_button) return;

        super.set_clear_all_filters_event();

        this.filter_x_button.on("click", () => {
            this.on_change();
        });
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
