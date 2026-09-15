// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

const FETCH_PROGRESS = "update_2a_2b_api_progress";
const SAVE_PROGRESS = "update_2a_2b_transactions_progress";
const DOWNLOAD_MESSAGE = "gstr_2a_2b_download_message";
const REGENERATE_2B = "regenerate_gstr_2b";
const EXPORT_READY = "gst_return_export_ready";
const EXPORT_MODULE = "india_compliance.gst_india.doctype.gst_return_export.gst_return_export";
const TAX_FIELDS = ["igst", "cgst", "sgst", "cess"];
const GROUP_BY_LABELS = {
    monthly: "Monthly",
    quarterly: "Quarterly",
    half_yearly: "Half Yearly",
    yearly: "Yearly",
    all: "All",
};
const GROUP_BY_ALL = "all";
const MONTH_FORMAT = "MM-YYYY";

// ---- form handlers: each hands off to the current return type's view

frappe.ui.form.on("GST Return Export", {
    setup(frm) {
        frm._assets = frappe.require(["gst_return_export.bundle.js", "india_compliance.bundle.css"]);
        set_realtime_listeners(frm);
        frm.doc.company ||= frappe.defaults.get_user_default("Company");
        load_period_bounds(frm);
        frm.trigger("company");
    },

    refresh(frm) {
        frm.disable_save();
        frm.page.clear_indicator();
        apply_month_pickers(frm);

        const view = get_view(frm);
        view.setup_actions();
        view.refresh_view();
    },

    async company(frm) {
        frm.set_value("company_gstin", null);
        if (!frm.doc.company) return;

        const [gstin] = await india_compliance.set_gstin_options(frm);
        frm.set_value("company_gstin", gstin);
    },

    company_gstin: (frm) => get_view(frm).refresh_view(),

    gst_return: (frm) => load_period_bounds(frm),

    from_date: (frm) => on_period_change(frm),

    to_date: (frm) => on_period_change(frm),
});

// ---- month pickers

async function load_period_bounds(frm) {
    const return_type = frm.doc.gst_return;
    if (return_type) {
        const { message } = await frm.call("get_period_bounds", { return_type });
        if (frm.doc.gst_return !== return_type) return;
        frm._bounds = message;
    }

    on_period_change(frm);
}

function on_period_change(frm) {
    const bounds = frm._bounds;
    if (bounds) {
        const { first, latest } = bounds;
        const from_date = clamp(frm.doc.from_date || fiscal_year_start(latest), first, latest);
        if (from_date !== frm.doc.from_date) return frm.set_value("from_date", from_date);

        const to_date = clamp(frm.doc.to_date || latest, first, latest);
        if (to_date !== frm.doc.to_date) return frm.set_value("to_date", to_date);
    }

    apply_month_pickers(frm);
    get_view(frm).refresh_view();
}

function apply_month_pickers(frm) {
    const to_obj = (value) => (value ? frappe.datetime.str_to_obj(value) : false);
    const first = to_obj(frm._bounds?.first);
    const latest = to_obj(frm._bounds?.latest || frappe.datetime.get_today());
    const { from_date, to_date } = frm.fields_dict;

    for (const field of [from_date, to_date]) {
        Object.assign(field, { parse: parse_month, format_for_input: format_month });
    }

    from_date.datepicker?.update({ minDate: first, maxDate: to_obj(frm.doc.to_date) || latest });
    to_date.datepicker?.update({ minDate: to_obj(frm.doc.from_date) || first, maxDate: latest });
}

// dates are "YYYY-MM-DD", so plain string order is date order
function clamp(value, low, high) {
    return value < low ? low : value > high ? high : value;
}

function fiscal_year_start(date) {
    const month = moment(date);
    return month_start([month.month() >= 3 ? month.year() : month.year() - 1, 3, 1]);
}

function month_start(date) {
    return moment(date).startOf("month").format("YYYY-MM-DD");
}

function parse_month(value) {
    const date = moment(value, [MONTH_FORMAT, "YYYY-MM-DD"], true);
    return date.isValid() ? month_start(date) : "";
}

function format_month(value) {
    return value ? moment(value).format(MONTH_FORMAT) : "";
}

function format_period(period) {
    return period && period.length === 6 ? `${period.slice(0, 2)}-${period.slice(2)}` : period;
}

// ---- realtime

function set_realtime_listeners(frm) {
    frappe.realtime.on(FETCH_PROGRESS, (data) => get_view(frm).update_progress?.(data, true));
    frappe.realtime.on(SAVE_PROGRESS, (data) => get_view(frm).update_progress?.(data, false));

    frappe.realtime.on(DOWNLOAD_MESSAGE, (message) => {
        frm.dashboard.hide();
        frappe.msgprint(message);
    });

    frappe.realtime.on(REGENERATE_2B, ({ return_period }) => {
        frm.dashboard.hide();
        frappe.show_alert({
            message: __("GSTR-2B for {0} isn't generated on the portal yet.", [return_period]),
            indicator: "orange",
        });
    });

    frappe.realtime.on(EXPORT_READY, on_export_ready);
}

function on_export_ready({ file_name, request, error }) {
    if (error) {
        frappe.show_alert({ message: __("Export failed: {0}", [error]), indicator: "red" });
        return;
    }

    frappe.show_alert({ message: __("Export ready: {0}", [file_name]), indicator: "green" });

    open_url_post(`/api/method/${EXPORT_MODULE}.download_export_file`, request);
}

// ---- views

class ReturnExportView {
    constructor(frm) {
        this.frm = frm;
        this.return_type = frm.doc.gst_return;
        this.sync_status = null;
    }

    setup_actions() {
        this.frm.add_custom_button(__("Sync"), () => this.sync());
        this.frm
            .add_custom_button(__("Export to Excel"), () => this.export_to_excel())
            .addClass("btn-primary");
    }

    get_filters() {
        const { company_gstin, gst_return, from_date, to_date } = this.frm.doc;
        if (!company_gstin || !gst_return || !from_date || !to_date) return null;
        return { company_gstin, return_type: gst_return, from_date, to_date };
    }

    async fetch_sync_status() {
        const filters = this.get_filters();
        if (!filters) return null;

        const { message } = await this.frm.call("get_sync_status", filters);
        this.sync_status = message;
        return message;
    }

    async refresh_view() {
        if (!this.get_filters()) {
            this.sync_status = null;
            this.remove_missing_sync_alert();
            return this.render_placeholder();
        }

        // a later change may answer first; only the newest draws
        const render = (this.frm._render_seq = (this.frm._render_seq || 0) + 1);
        const [, { message: summary }] = await Promise.all([
            this.fetch_sync_status(),
            this.frm.call("get_summary", this.get_filters()),
        ]);
        if (render !== this.frm._render_seq) return;

        await this.frm._assets;
        this.render_missing_sync_alert();
        this.render_summary(summary);
    }

    render_placeholder(message) {
        const fallback = __("Select Company, GSTIN, GST Return and the period to see the summary.");
        this.render_summary_wrapper(`<p class="text-muted">${message || fallback}</p>`);
    }

    render_summary_wrapper(inner_html) {
        const $wrapper = this.frm.get_field("summary_html")?.$wrapper;
        $wrapper?.html(`
            <div class="gst-return-summary">
                <div class="summary-heading">${__("Summary")}</div>
                ${inner_html}
            </div>`);
        return $wrapper;
    }

    render_missing_sync_alert() {
        this.remove_missing_sync_alert();

        const { frm } = this;
        if (!frm.layout?.wrapper || !this.sync_status?.has_missing_sync) return;

        const action = india_compliance.is_api_enabled()
            ? `<a href="#" class="alert-link gst-export-sync-now">${__("Sync now")}</a>`
            : "";
        const $alert = $(`
            <div class="gst-export-sync-alert alert alert-primary fade show d-flex align-items-center justify-content-between border-0" role="alert">
                <div>${__("Some months in the selected period aren't synced yet.")}</div>
                ${action}
            </div>
        `).prependTo(frm.layout.wrapper);

        $alert.find(".gst-export-sync-now").on("click", (event) => {
            event.preventDefault();
            this.sync();
        });
    }

    remove_missing_sync_alert() {
        this.frm.layout?.wrapper?.find(".gst-export-sync-alert").remove();
    }

    async sync() {
        if (!india_compliance.is_api_enabled()) {
            frappe.throw(__("Enable the GST API in GST Settings to sync from the GST Portal."));
        }
        if (!this.get_filters()) {
            frappe.throw(__("Select Company, GSTIN, GST Return and the period before syncing."));
        }

        const status = await this.fetch_sync_status();
        this.open_sync_dialog(status?.periods || []);
    }

    async export_to_excel() {
        const filters = this.get_filters();
        if (!filters) {
            frappe.throw(__("Select Company, GSTIN, GST Return and the period before exporting."));
        }

        const status = await this.fetch_sync_status();
        this.render_missing_sync_alert();

        const periods = status?.periods || [];
        const synced = periods.filter((period) => period.synced);
        if (synced.length < periods.length) {
            this.warn_missing_sync(periods);
            if (!synced.length) return;
        }

        const group_by = periods.length > 1 ? await this.ask_group_by() : GROUP_BY_ALL;
        if (!group_by) return;

        const { message } = await frappe.call({
            method: `${EXPORT_MODULE}.export_return_as_excel`,
            args: { ...filters, group_by },
        });
        if (message?.request) return on_export_ready(message); // already built, download now
        if (message?.message) {
            frappe.show_alert({ message: message.message, indicator: "blue" });
        }
    }

    ask_group_by() {
        return new Promise((resolve) => {
            let chosen = null;
            const dialog = new frappe.ui.Dialog({
                title: __("Export to Excel"),
                fields: [
                    {
                        fieldname: "group_by",
                        fieldtype: "Select",
                        label: __("One file"),
                        default: GROUP_BY_ALL,
                        reqd: 1,
                        options: Object.entries(GROUP_BY_LABELS).map(([value, label]) => ({
                            label: __(label),
                            value,
                        })),
                    },
                    {
                        fieldname: "help",
                        fieldtype: "HTML",
                        options: `<p class="text-muted small">${__(
                            "Multiple files are downloaded as a zip. All puts every month in a single file.",
                        )}</p>`,
                    },
                ],
                primary_action_label: __("Export"),
                primary_action: ({ group_by }) => {
                    chosen = group_by;
                    dialog.hide();
                },
            });

            dialog.$wrapper.on("hidden.bs.modal", () => resolve(chosen));
            dialog.show();
        });
    }

    warn_missing_sync(periods) {
        const missing = periods
            .filter((period) => !period.synced)
            .map((period) => format_period(period.period));
        if (!missing.length) return;

        frappe.show_alert({
            message: __("Not synced yet: {0}. Use Sync to fetch it from the GST Portal.", [
                missing.join(", "),
            ]),
            indicator: "orange",
        });
    }

    open_sync_dialog() {
        frappe.throw(__("Syncing isn't available for {0} yet.", [this.return_type]));
    }

    render_summary() {
        this.render_placeholder(__("Summary isn't available for {0} yet.", [this.return_type]));
    }
}

class GSTR2View extends ReturnExportView {
    open_sync_dialog(periods) {
        if (!periods.length) {
            frappe.show_alert({
                message: __("No months in the selected period are available on the GST Portal yet."),
                indicator: "orange",
            });
            return;
        }

        const { frm } = this;
        const dialog = new frappe.ui.Dialog({
            title: __("Sync from GST Portal"),
            fields: [
                {
                    fieldname: "periods",
                    fieldtype: "MultiCheck",
                    label: __("Months"),
                    columns: 1,
                    sort_options: false,
                    select_all: 1,
                    options: periods.map((period) => ({
                        value: period.period,
                        checked: !period.synced,
                        label: this.sync_option_label(period),
                    })),
                },
            ],
            primary_action_label: __("Sync"),
            primary_action: async () => {
                const selected = dialog.get_value("periods") || [];
                if (!selected.length) {
                    frappe.show_alert({ message: __("Select at least one month."), indicator: "orange" });
                    return;
                }

                dialog.hide();
                this.show_progress(0, __("Fetching data from the GST Portal"));

                const { message } = await frm.taxpayer_api_call("sync_return_data", {
                    ...this.get_filters(),
                    periods: selected,
                });
                if (message?.message) {
                    frm.dashboard.hide();
                    frappe.show_alert({ message: message.message, indicator: message.indicator || "blue" });
                }
            },
        });

        dialog.show();
    }

    sync_option_label(period) {
        let status = __("Not synced");
        if (period.synced) {
            status = period.last_updated_on
                ? __("Last synced on {0}", [frappe.datetime.str_to_user(period.last_updated_on)])
                : __("Synced");
        }
        const month = frappe.utils.escape_html(format_period(period.period));
        status = frappe.utils.escape_html(status);
        return `${month} <span style="color: var(--text-light); font-weight: 400;">· ${status}</span>`;
    }

    show_progress(percent, message) {
        this.frm.dashboard.show_progress(__("Sync Progress"), percent, message);
    }

    update_progress({ current_progress, return_period, is_last_period }, is_fetch_phase) {
        const percent = is_fetch_phase ? current_progress / 2 : 50 + current_progress / 2;
        const message = is_fetch_phase
            ? __("Fetching data from the GST Portal")
            : __("Saving data for return period {0}", [return_period]);
        this.show_progress(percent, message);

        if (is_last_period) this.last_return_period = return_period;

        // the save phase closes only on the last month's final event
        const sync_complete =
            !is_fetch_phase && current_progress === 100 && return_period === this.last_return_period;
        if (sync_complete) this.on_sync_complete();
    }

    on_sync_complete() {
        setTimeout(() => {
            this.frm.dashboard.hide();
            this.frm.dashboard.set_headline(__("Successfully Synced"));
            this.refresh_view();
            setTimeout(() => this.frm.dashboard.clear_headline(), 2000);
        }, 1000);
    }

    render_summary(data) {
        const has_data = (data?.sections || []).length > 0;
        const body = has_data
            ? `<div class="section-table"></div>`
            : `<p class="text-muted">${__(
                  "No data synced yet — click Sync to fetch it from the GST Portal.",
              )}</p>`;
        const $wrapper = this.render_summary_wrapper(this.itc_summary_html(data) + body);

        this.render_itc_summary($wrapper, data);
        if (has_data) {
            this.render_section_table($wrapper.find(".section-table"), data.sections, data.totals);
        }
    }

    // 2A has no ITC summary; 2B fills these
    itc_summary_html() {
        return "";
    }
    render_itc_summary() {}

    render_section_table($wrapper, sections, totals) {
        const data = [];
        for (const section of sections) {
            data.push({ ...section, indent: 0 });
            for (const month of section.months) {
                data.push({ ...month, section: format_period(month.period), indent: 1 });
            }
        }

        const table = new india_compliance.DataTableManager({
            $wrapper,
            data,
            columns: [
                { label: __("Section"), fieldname: "section", fieldtype: "Data", width: 240 },
                { label: __("Documents"), fieldname: "documents", fieldtype: "Int", width: 110 },
                { label: __("Taxable Value"), fieldname: "taxable_value", fieldtype: "Float", width: 160 },
                ...TAX_FIELDS.map((field) => ({
                    label: field.toUpperCase(),
                    fieldname: field,
                    fieldtype: "Float",
                    width: 120,
                })),
            ],
            options: {
                checkboxColumn: false,
                serialNoColumn: false,
                inlineFilters: false,
                treeView: true,
                showTotalRow: true,
                clusterize: false,
                cellHeight: 34,
                hooks: {
                    columnTotal: (_, row) =>
                        row.column.fieldname === "section" ? __("Total") : totals[row.column.fieldname] ?? "",
                },
            },
        });

        table.datatable.rowmanager.collapseAllNodes();
        this.render_expand_button($wrapper, table.datatable.rowmanager);
    }

    render_expand_button($wrapper, rowmanager) {
        let expanded = false;
        const $button = $(
            `<button class="btn btn-xs btn-default section-table-footer">${__("Expand All")}</button>`,
        ).insertAfter($wrapper);

        $button.on("click", () => {
            expanded = !expanded;
            rowmanager[expanded ? "expandAllNodes" : "collapseAllNodes"]();
            $button.text(expanded ? __("Collapse All") : __("Expand All"));
        });
    }
}

class GSTR2BView extends GSTR2View {
    itc_summary_html(data) {
        return data?.itc ? `<div class="itc-summary"></div>` : "";
    }

    render_itc_summary($wrapper, data) {
        if (data?.itc) this.render_itc_cards($wrapper.find(".itc-summary"), data.itc);
    }

    render_itc_cards($wrapper, itc) {
        new india_compliance.NumberCardManager({
            $wrapper,
            cards: [
                { label: __("ITC Available"), value: itc.available, datatype: "Float" },
                { label: __("ITC Not Available"), value: itc.not_available, datatype: "Float" },
                { label: __("ITC Reversal"), value: itc.reversal, datatype: "Float" },
            ],
        });
    }
}

// one view per return type; GSTR-1/3B: subclass ReturnExportView and register here
const RETURN_VIEWS = {
    "GSTR-2A": GSTR2View,
    "GSTR-2B": GSTR2BView,
};

function get_view(frm) {
    if (!frm._view || frm._view.return_type !== frm.doc.gst_return) {
        const View = RETURN_VIEWS[frm.doc.gst_return] || ReturnExportView;
        frm._view = new View(frm);
    }
    return frm._view;
}
