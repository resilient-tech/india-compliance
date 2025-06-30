frappe.provide("india_compliance");

india_compliance.DataTableManager = class DataTableManager {
    constructor(options) {
        Object.assign(this, options);
        this.data = this.data || [];
        this.additional_total_rows = this.additional_total_rows || null;
        this.make();
    }

    make() {
        this.format_data(this.data);
        this.make_no_data();
        this.render_datatable();
        this.setup_additional_total_row();

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

    refresh(data, columns, noDataMessage) {
        this.data = data;
        if (noDataMessage) this.datatable.options.noDataMessage = noDataMessage;

        this.datatable.refresh(data, columns);
        this.refresh_additional_total_rows();
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
        const docfield = {
            options: column.options || column.doctype,
            fieldname: column.fieldname,
            fieldtype: column.fieldtype,
            link_onclick: column.link_onclick,
            precision: column.precision,
        };
        column.width = column.width || 100;

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

        let format = function (value, row, column, data) {
            if (column._value) {
                value = column._value(value, column, data);
            }

            value = frappe.format(value, column, { always_show_decimals: true }, data);

            if (column._after_format) {
                value = column._after_format(value, column, data);
            }

            return value;
        };

        return {
            id: column.fieldname,
            field: column.fieldname,
            name: column.label,
            content: column.label,
            editable: false,
            format,
            docfield,
            ...column,
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

    clear_checked_items() {
        const { rowmanager } = this.datatable;
        rowmanager
            .getCheckedRows()
            .map(rowIndex => rowmanager.checkRow(rowIndex, false));
    }

    render_datatable() {
        const datatable_options = {
            dynamicRowHeight: true,
            checkboxColumn: true,
            inlineFilters: true,
            noDataMessage: __("No Matching Data Found!"),
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

    setup_additional_total_row() {
        if (!this.additional_total_rows) return;

        const datatable = this.datatable;
        const originalRenderFooter = datatable.bodyRenderer.renderFooter;

        datatable.bodyRenderer.renderFooter = () => {
            originalRenderFooter.call(datatable.bodyRenderer);
            this.render_additional_total_rows();
        };
    }

    refresh_additional_total_rows() {
        if (!this.additional_total_rows) return;

        this.remove_additional_total_rows();
        this.render_additional_total_rows();
    }

    render_additional_total_rows() {
        if (!this.additional_total_rows) return;

        for (const row of this.additional_total_rows) {
            this.render_additional_total_row(row);
        }
    }

    render_additional_total_row(row) {
        if (row.show && !row.show()) return;

        const datatable = this.datatable;

        const total_row_data = this.get_additional_total_row_data(row);
        if (!total_row_data) return;

        const html = datatable.rowmanager.getRowHTML(total_row_data, {
            rowIndex: row.row_id,
            isTotalRow: 1,
        });

        datatable.footer.insertAdjacentHTML("beforeend", html);

        const $row = $(`[data-row-index='${row.row_id}']`);

        $row.css(row.css_styles || { "font-weight": "bold" });
    }

    remove_additional_total_rows() {
        if (!this.additional_total_rows) return;

        for (const row of this.additional_total_rows) {
            if (!row.row_id) continue;
            $(`[data-row-index='${row.row_id}']`).remove();
        }
    }

    get_additional_total_row_data(row) {
        let data = this.get_row_data(row);
        if (!data) return null;

        const row_template = this.get_row_template(row);

        const total_row_data = row_template.map(cell => {
            if (cell.content === "") return cell;

            const fieldname = cell.column.id;

            if (row.label_column === fieldname) {
                cell.content = row.label;
            } else if (
                cell.column._fieldtype === "Float" ||
                cell.column.fieldtype === "Float"
            ) {
                cell.content = data[fieldname] || 0.0;
            } else if (Object.prototype.hasOwnProperty.call(data, fieldname)) {
                cell.content = data[fieldname];
            }

            return cell;
        });

        return total_row_data;
    }

    get_row_data(row) {
        if (typeof row.data === "function") {
            return row.data();
        }

        return row.data;
    }

    get_row_template(row) {
        const datatable = this.datatable;
        const columns = datatable.getColumns();

        const row_template = columns.map(col => {
            let content = null;

            if (row?.exclude_columns.includes(col.id)) {
                content = "";
            }

            return {
                content,
                isTotalRow: 1,
                colIndex: col.colIndex,
                column: col,
            };
        });

        return row_template;
    }
};
