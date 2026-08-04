frappe.provide("india_compliance");

// only reads, never gets picked
const NOTE = "note__autocomplete_option";

/**
 * Autocomplete that shows its filters, the way link fields do.
 *
 * Give it fully qualified filters, the shape frm.set_query builds, and every
 * set_data() ends the list with "Filtered by: ...". Blank values are left out.
 *
 *     field.set_filters([
 *         ["Purchase Invoice", "supplier_gstin", "like", gstin],
 *         ["Purchase Invoice", "posting_date", "between", [from_date, to_date]],
 *     ]);
 *     field.set_data(options);
 */
india_compliance.Autocomplete = class Autocomplete extends frappe.ui.form.ControlAutocomplete {
    set_filters(filters) {
        // presented on the next set_data
        this._filters = filters;
    }

    async set_data(data) {
        this._options = data || [];

        const note = await this.get_filter_note();
        super.set_data(note ? [...this._options, note] : this._options);
    }

    async get_filter_note() {
        const filters = (this._filters || []).filter(([, , , value]) => has_value(value));

        const text = [
            this._options.length ? "" : __("No documents found."),
            filters.length ? await this.get_filter_description(filters) : "",
        ]
            .filter(Boolean)
            .join(" ");

        if (!text) return null;

        return {
            html: `<span class="text-muted" style="line-height: 1.5">${text}</span>`,
            value: NOTE,
            action: () => {},
        };
    }

    // borrowed, so the sentence reads exactly like a link field's
    get_filter_description(filters) {
        return frappe.ui.form.ControlLink.prototype.get_filter_description.call(this, filters);
    }

    // it asks for a doctype to fill in short filters, ours already carry one
    get_options() {
        return "";
    }

    get_awesomplete_settings() {
        const settings = super.get_awesomplete_settings();
        const { filter, item } = settings;

        return Object.assign(settings, {
            // a note is not an option, so typing never hides it
            filter(option, input) {
                if (option.value === NOTE) return true;
                return filter.call(this, option, input);
            },

            item(option) {
                if (option.value !== NOTE) return item.call(this, option);

                const note = this.get_item(option.value);
                return $("<li></li>")
                    .data("item.autocomplete", note)
                    .prop("aria-selected", "false")
                    .html(`<a><p>${note.html}</p></a>`)
                    .get(0);
            },
        });
    }

    setup_awesomplete() {
        super.setup_awesomplete();

        // picking a note must not put it in the field
        this.$input.on("awesomplete-select", (e) => {
            if (e.originalEvent.text.value !== NOTE) return;

            e.preventDefault();
            return false;
        });
    }
};

// a range needs both ends, an empty array must not read as "undefined"
function has_value(value) {
    if (Array.isArray(value)) return value.length && value.every(has_value);
    return Boolean(value) || value === 0;
}
