frappe.provide("ic")

ic.DataTableManager = class DataTableManager {
    constructor(options) {
        Object.assign(this, options);
        this.data = this.data || [];
        this.make();
    }

    make() {
        this.format_data(this.data);
        this.make_no_data();
        this.render_datatable();

        this.columns_dict = {};
        for (const column of this.datatable.getColumns()) {
            const fieldname = column.field || column.id;
            this.columns_dict[fieldname] = column;
            this.columns_dict[fieldname].$filter_input = $(
                `.dt-row-filter .dt-cell--col-${column.colIndex} .dt-filter`,
                this.$datatable
            )[0];
        }
    }

    get_column(fieldname) {
        return this.columns_dict[fieldname];
    }

    get_filter_input(fieldname) {
        return this.get_column(fieldname).$filter_input;
    }

    make_no_data() {
        this.$no_data =
            this.$no_data ||
            $('<div class="text-muted text-center">No Matching Data Found!</div>');

        this.$wrapper.parent().append(this.$no_data);

        this.$no_data.hide();
    }

    get_dt_columns() {
        if (!this.columns) return [];
        return this.columns.map(this.get_dt_column);
    }

    get_dt_column(column) {
        const title = __(column.label || toTitle(column.fieldname));
        column.fieldname ||= frappe.scrub(title);

        const docfield = {
            options: column.options || column.doctype,
            fieldname: column.fieldname,
            fieldtype: column.fieldtype,
            link_onclick: column.link_onclick,
            precision: column.precision,
        };
        const align =
            frappe.model.is_numeric_field(docfield) || docfield.fieldtype === "Date"
                ? "right"
                : "left";

        let compareFn = null;
        if (docfield.fieldtype === "Date") {
            compareFn = (cell, keyword) => {
                if (!cell.content) return null;
                if (keyword.length !== "YYYY-MM-DD".length) return null;

                const keywordValue = frappe.datetime.user_to_obj(keyword);
                const cellValue = frappe.datetime.str_to_obj(cell.content);
                return [+cellValue, +keywordValue];
            };
        }

        let formatter = column.format;
        if (!formatter) {
            formatter = (value, row, column, data) => {
                let doc = null;
                if (Array.isArray(row)) {
                    doc = row.reduce((acc, curr) => {
                        if (!curr.column.docfield) return acc;
                        acc[curr.column.docfield.fieldname] = curr.content;
                        return acc;
                    }, {});
                } else {
                    doc = row;
                }

                return frappe.format(
                    value,
                    column.docfield,
                    { always_show_decimals: true },
                    doc
                );
            };
        }

        return {
            id: column.fieldname,
            field: column.fieldname,
            name: title,
            content: title,
            docfield,
            width: column.width || 150,
            editable: !!column.editable,
            align,
            compareValue: compareFn,
            format: formatter,
            dropdown: column.dropdown,
        };
    }

    format_data() {
        if (!Array.isArray(this.data)) {
            this.data = Object.values(this.data);
        }

        if (!this.format_row) return;

        this.data = this.data.map(this.format_row);
    }

    get_checked_items() {
        const indices = this.datatable.rowmanager.getCheckedRows();
        return indices.map(index => this.data[index]);
    }

    render_datatable() {
        const datatable_options = {
            dynamicRowHeight: true,
            checkboxColumn: true,
            inlineFilters: true,
            noDataMessage: "No Matching Data Found!",
            // clusterize: false,
            events: {
                onCheckRow: () => {
                    const checked_items = this.get_checked_items();
                    // this.toggle_actions_menu_button(checked_items.length > 0);
                },
            },
            cellHeight: 34,
            ...this.options,
            columns: this.get_dt_columns(),
            data: this.data,
        };
        this.datatable = new frappe.DataTable(this.$wrapper.get(0), datatable_options);
        this.$datatable = $(`.${this.datatable.style.scopeClass}`);
    }
}