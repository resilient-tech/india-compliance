// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

// GST Return Export tool (GSTR-2A / 2B). Sync fetches fresh from the portal in a
// background job (realtime progress) and stores a summary; Show Summary reads it.
const FETCH_PROGRESS = "update_2a_2b_api_progress";
const SAVE_PROGRESS = "update_2a_2b_transactions_progress";

const TAX_FIELDS = ["igst", "cgst", "sgst", "cess"];

frappe.ui.form.on("GST Return Export", {
    setup(frm) {
        frappe.require(["gst_return_export.bundle.css", "gst_return_export.bundle.js"]);
        frm.events.set_realtime_listeners(frm);
        frm.doc.company ||= frappe.defaults.get_user_default("Company");
        frm.trigger("company");
    },

    refresh(frm) {
        frm.disable_save(); // for `Not Saved` and Doctype behaves like a report
        frm.page.clear_indicator();
        frm.events.setup_actions(frm);
        render_summary_placeholder(frm);
    },

    async company(frm) {
        frm.set_value("company_gstin", null);
        if (!frm.doc.company) return;

        const [gstin] = await india_compliance.set_gstin_options(frm);
        frm.set_value("company_gstin", gstin);
    },

    setup_actions(frm) {
        frm.add_custom_button(__("Show Summary"), () => render_summary(frm));
        frm.add_custom_button(__("Export to Excel"), () => export_return_excel(frm));
        frm.add_custom_button(__("Sync"), () => frm.events.sync_return_data(frm)).addClass("btn-primary");
    },

    async sync_return_data(frm) {
        if (!india_compliance.is_api_enabled()) {
            frappe.throw(__("Enable the GST API in GST Settings to sync from the GST Portal."));
        }

        const { company, company_gstin, gst_return, from_date, to_date } = frm.doc;
        if (!company || !company_gstin || !gst_return || !from_date || !to_date) {
            frappe.throw(__("Select Company, GSTIN, GST Return and the period before syncing."));
        }

        const { message } = await fetch_summary(frm);
        open_sync_dialog(frm, message?.periods || []);
    },

    set_realtime_listeners(frm) {
        frappe.realtime.on(FETCH_PROGRESS, (data) => frm.events.update_progress(frm, data, true));
        frappe.realtime.on(SAVE_PROGRESS, (data) => frm.events.update_progress(frm, data, false));

        frappe.realtime.on("gstr_2a_2b_download_message", (message) => {
            frm.dashboard.hide();
            frappe.msgprint(message);
        });

        frappe.realtime.on("regenerate_gstr_2b", ({ return_period }) => {
            frm.dashboard.hide();
            frappe.show_alert({
                message: __("GSTR-2B for {0} isn't generated on the portal yet.", [return_period]),
                indicator: "orange",
            });
        });

        frappe.realtime.on("gst_return_export_ready", ({ file_url, file_name, error }) => {
            if (error) {
                frappe.show_alert({ message: __("Export failed: {0}", [error]), indicator: "red" });
                return;
            }
            frappe.show_alert({ message: __("Export ready: {0}", [file_name]), indicator: "green" });
            const link = document.createElement("a");
            link.href = file_url;
            link.download = file_name;
            document.body.appendChild(link);
            link.click();
            link.remove();
        });
    },

    update_progress(frm, { current_progress, return_period, is_last_period }, is_fetch_phase) {
        const percent = is_fetch_phase ? current_progress / 2 : 50 + current_progress / 2;
        const message = is_fetch_phase
            ? __("Fetching data from the GST Portal")
            : __("Saving data for return period {0}", [return_period]);

        frm.events.show_progress(frm, percent, message);

        if (is_last_period) frm.flag_last_return_period = return_period;

        const sync_complete =
            !is_fetch_phase && current_progress === 100 && return_period === frm.flag_last_return_period;
        if (!sync_complete) return;

        setTimeout(() => {
            frm.dashboard.hide();
            frm.dashboard.set_headline(__("Successfully Synced"));
            render_summary(frm);
            setTimeout(() => frm.dashboard.clear_headline(), 2000);
        }, 1000);
    },

    show_progress(frm, percent, message) {
        frm.dashboard.show_progress(__("Sync Progress"), percent, message);
    },
});

function fetch_summary(frm) {
    return frm.call("get_summary", {
        company_gstin: frm.doc.company_gstin,
        return_type: frm.doc.gst_return,
        date_range: [frm.doc.from_date, frm.doc.to_date],
    });
}

async function export_return_excel(frm) {
    const { company_gstin, gst_return, from_date, to_date } = frm.doc;
    if (!company_gstin || !gst_return || !from_date || !to_date) {
        frappe.throw(__("Select Company, GSTIN, GST Return and the period before exporting."));
    }

    const { message } = await frappe.call({
        method: "india_compliance.gst_india.doctype.gst_return_export.gstr_2_export.export_return_as_excel",
        args: { company_gstin, return_type: gst_return, date_range: [from_date, to_date] },
    });
    if (message?.message) {
        frappe.show_alert({ message: message.message, indicator: "blue" });
    }
}

async function render_summary(frm) {
    const { company_gstin, gst_return, from_date, to_date } = frm.doc;
    if (!company_gstin || !gst_return || !from_date || !to_date) {
        frappe.show_alert({
            message: __("Select Company, GSTIN, GST Return and the period first."),
            indicator: "orange",
        });
        return;
    }

    const { message } = await fetch_summary(frm);
    render_range_summary(frm, message, gst_return);
}

function render_range_summary(frm, data, gst_return) {
    const periods = data?.periods || [];
    if (!periods.length) return render_summary_placeholder(frm);

    const is_2b = gst_return === "GSTR-2B";
    const has_data = data.sections.length > 0;

    set_summary_html(
        frm,
        (is_2b && data.itc ? `<div class="itc-summary"></div>` : "") +
            (has_data
                ? `<div class="section-table"></div>`
                : `<p class="text-muted">${__(
                      "No data synced yet — click Sync to fetch it from the GST Portal.",
                  )}</p>`),
    );

    const $wrapper = frm.get_field("summary_html").$wrapper;
    if (is_2b && data.itc) mount_itc_cards($wrapper.find(".itc-summary"), data.itc);
    if (has_data) mount_section_table($wrapper.find(".section-table"), data.sections, data.totals);

    const unsynced = periods.filter((p) => !p.synced).map((p) => format_period(p.period));
    if (unsynced.length) {
        frappe.show_alert({
            message: __("Not synced yet: {0}. Use Sync to fetch.", [unsynced.join(", ")]),
            indicator: "orange",
        });
    }
}

function open_sync_dialog(frm, periods) {
    if (!periods.length) {
        frappe.show_alert({ message: __("No months in the selected period."), indicator: "orange" });
        return;
    }

    const dialog = new frappe.ui.Dialog({
        title: __("Sync from GST Portal"),
        fields: [
            {
                fieldname: "periods",
                fieldtype: "MultiCheck",
                label: __("Months"),
                columns: 1,
                sort_options: false,
                options: periods.map((p) => ({
                    value: p.period,
                    checked: !p.synced,
                    label: `${format_period(p.period)} · ${
                        p.synced
                            ? __("synced {0}", [frappe.datetime.str_to_user(p.last_updated_on)])
                            : __("not synced")
                    }`,
                })),
            },
        ],
        primary_action_label: __("Sync"),
        async primary_action() {
            const selected = dialog.get_value("periods") || [];
            if (!selected.length) {
                frappe.show_alert({ message: __("Select at least one month."), indicator: "orange" });
                return;
            }

            dialog.hide();
            frm.events.show_progress(frm, 0, __("Fetching data from the GST Portal"));

            const { message } = await frm.taxpayer_api_call("sync_return_data", {
                company_gstin: frm.doc.company_gstin,
                return_type: frm.doc.gst_return,
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

function mount_section_table($wrapper, sections, totals) {
    const cells = (row) => ({
        documents: row.documents,
        taxable_value: row.taxable_value,
        igst: row.igst,
        cgst: row.cgst,
        sgst: row.sgst,
        cess: row.cess,
    });

    const data = [];
    for (const section of sections) {
        data.push({ section: section.section, indent: 0, ...cells(section) });
        for (const month of section.months) {
            data.push({ section: format_period(month.period), indent: 1, ...cells(month) });
        }
    }

    new india_compliance.DataTableManager({
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
                    row.column.fieldname === "section" ? __("Total") : totals[row.column.fieldname] ?? 0,
            },
        },
    });
}

function set_summary_html(frm, inner_html) {
    frm.get_field("summary_html")?.$wrapper.html(`
        <div class="gst-return-summary">
            <div class="summary-heading">${__("Summary")}</div>
            ${inner_html}
        </div>`);
}

function mount_itc_cards($wrapper, itc) {
    new india_compliance.NumberCardManager({
        $wrapper,
        cards: [
            { label: __("ITC Available"), value: itc.available, datatype: "Float" },
            { label: __("ITC Not Available"), value: itc.not_available, datatype: "Float" },
            { label: __("ITC Reversal"), value: itc.reversal, datatype: "Float" },
        ],
    });
}

function render_summary_placeholder(frm, message) {
    const default_message = __(
        "Click Show Summary to view the last synced data, or Sync to fetch it fresh from the GST Portal.",
    );
    set_summary_html(frm, `<p class="text-muted">${message || default_message}</p>`);
}

function format_period(period) {
    return period && period.length === 6 ? `${period.slice(0, 2)}-${period.slice(2)}` : period;
}
