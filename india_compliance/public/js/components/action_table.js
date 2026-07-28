frappe.provide("india_compliance");

const NUMERIC_FIELDTYPES = ["Int", "Float", "Currency", "Percent"];

/**
 * Minimal table with action buttons and (optionally) editable cells.
 *
 * const table = new india_compliance.ActionTable({
 *     $wrapper: dialog.fields_dict.table.$wrapper,
 *     columns: [
 *         // read-only column (Data by default; value is HTML-escaped)
 *         { fieldname: "supplier_name", label: __("Supplier") },
 *         {
 *             fieldname: "cgst",
 *             label: __("Declared CGST"),
 *             fieldtype: "Float",
 *             editable: 1,
 *             min: 0,
 *             max: (row) => row.supplier_cgst, // value or (row) => value
 *             // muted sub-label below the cell; HTML — escape user data yourself
 *             description: (row) => `${__("books")} ${format_number(row.books_cgst)}`,
 *         },
 *     ],
 *     data: rows,
 *     actions: [
 *         {
 *             label: __("Use books value (all)"),
 *             action: (table) =>
 *                 table.data.forEach((row, i) => table.set_value(i, "cgst", row.books_cgst)),
 *         },
 *     ],
 * });
 *
 * table.get_values(); // [{ cgst: 850 }, ...] — editable fields only, aligned with data
 */
india_compliance.ActionTable = class ActionTable {
    constructor(opts) {
        Object.assign(this, { columns: [], data: [], actions: [] }, opts);
        this.render();
    }

    render() {
        const buttons = this.actions
            .map(
                (action, index) =>
                    `<button class="btn btn-xs btn-default" data-action="${index}">${action.label}</button>`,
            )
            .join(" ");

        const head = this.columns
            .map((column) => `<th class="${this.cell_class(column)}">${column.label || ""}</th>`)
            .join("");

        const body = this.data
            .map((row, index) => {
                const cells = this.columns
                    .map(
                        (column) =>
                            `<td class="${this.cell_class(column)}">${this.get_cell_html(
                                row,
                                index,
                                column,
                            )}</td>`,
                    )
                    .join("");
                return `<tr>${cells}</tr>`;
            })
            .join("");

        this.$wrapper.html(`
            ${buttons ? `<div class="mb-2">${buttons}</div>` : ""}
            <div style="max-height: 50vh; overflow: auto;">
                <table class="table table-bordered">
                    <thead><tr>${head}</tr></thead>
                    <tbody>${body}</tbody>
                </table>
            </div>
        `);

        this.$wrapper.on("click", "[data-action]", (e) => {
            e.preventDefault();
            this.actions[$(e.currentTarget).data("action")].action(this);
        });

        // live validation: repaint a row's cells as its values change
        this.$wrapper.on("input", "input[data-fieldname]", (e) =>
            this.validate_row($(e.currentTarget).data("row")),
        );
        this.validate_all();
    }

    cell_class(column) {
        return NUMERIC_FIELDTYPES.includes(column.fieldtype) ? "text-right" : "";
    }

    get_cell_html(row, index, column) {
        const cell = column.editable
            ? this.get_input_html(row, index, column)
            : this.format_value(row, column);

        if (!column.description) return cell;
        return `${cell}<small class="text-muted">${column.description(row)}</small>`;
    }

    get_input_html(row, index, column) {
        const numeric = NUMERIC_FIELDTYPES.includes(column.fieldtype);
        const attr = (name, limit) => {
            if (limit == null) return "";
            return `${name}="${typeof limit === "function" ? limit(row) : limit}"`;
        };

        return `<input
            class="form-control input-xs"
            type="${numeric ? "number" : "text"}"
            data-row="${index}"
            data-fieldname="${column.fieldname}"
            value="${frappe.utils.escape_html(row[column.fieldname] ?? "")}"
            ${attr("min", column.min)} ${attr("max", column.max)}
            ${numeric ? 'style="text-align: right; min-width: 90px;"' : ""}
        >`;
    }

    format_value(row, column) {
        const value = row[column.fieldname];
        if (column.format) return column.format(value, row);
        if (column.fieldtype) return frappe.format(value, { fieldtype: column.fieldtype });
        return `${frappe.utils.escape_html(value ?? "")}<br>`;
    }

    $input(row_index, fieldname) {
        return this.$wrapper.find(`input[data-row="${row_index}"][data-fieldname="${fieldname}"]`);
    }

    get_value(row_index, fieldname) {
        const column = this.columns.find((column) => column.fieldname === fieldname);
        const value = this.$input(row_index, fieldname).val();
        return NUMERIC_FIELDTYPES.includes(column?.fieldtype) ? flt(value) : value;
    }

    set_value(row_index, fieldname, value) {
        this.$input(row_index, fieldname).val(value);
        this.validate_row(row_index);
    }

    editable_values(index) {
        return Object.fromEntries(
            this.columns
                .filter((column) => column.editable)
                .map((column) => [column.fieldname, this.get_value(index, column.fieldname)]),
        );
    }

    get_values() {
        return this.data.map((row, index) => this.editable_values(index));
    }

    // data refs (e.g. supplier_*) + current editable values, for validation
    row_values(index) {
        return { ...this.data[index], ...this.editable_values(index) };
    }

    validate_row(index) {
        const row = this.row_values(index);
        this.columns.forEach((column) => {
            if (!column.editable || !column.validate) return;
            const valid = column.validate(row[column.fieldname], row);
            const color = valid ? "" : "var(--red-500, #e24c4c)";
            this.$input(index, column.fieldname).css("border-color", color);
        });
    }

    validate_all() {
        this.data.forEach((row, index) => this.validate_row(index));
    }

    is_valid() {
        return this.data.every((_row, index) => {
            const values = this.row_values(index);
            return this.columns.every(
                (column) =>
                    !column.editable ||
                    !column.validate ||
                    column.validate(values[column.fieldname], values),
            );
        });
    }
};
