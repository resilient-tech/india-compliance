// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

// GST Return Export tool (GSTR-2A / 2B). Sync fetches fresh from the portal in a
// background job (realtime progress) and stores a summary; Show Summary reads it.
const FETCH_PROGRESS = "update_2a_2b_api_progress";
const SAVE_PROGRESS = "update_2a_2b_transactions_progress";

const TAX_FIELDS = ["igst", "cgst", "sgst", "cess"];

// Drives the section-wise table header, body and total row from one definition.
const SUMMARY_COLUMNS = [
    { key: "section", label: "Section" },
    { key: "suppliers", label: "Suppliers" },
    { key: "documents", label: "Documents" },
    { key: "taxable_value", label: "Taxable Value", currency: true },
    ...TAX_FIELDS.map((field) => ({ key: field, label: field.toUpperCase(), currency: true })),
];

frappe.ui.form.on("GST Return Export", {
    setup(frm) {
        frappe.require("gst_return_export.bundle.css");
        frm.events.set_realtime_listeners(frm);
        frm.doc.company ||= frappe.defaults.get_user_default("Company");
        frm.trigger("company");
    },

    refresh(frm) {
        frm.disable_save();
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

        frm.events.show_progress(frm, 0, __("Fetching data from the GST Portal"));

        const { message } = await frm.taxpayer_api_call("sync_return_data", {
            company_gstin,
            return_type: gst_return,
            date_range: [from_date, to_date],
        });

        if (message?.message) {
            frm.dashboard.hide();
            frappe.show_alert({ message: message.message, indicator: message.indicator || "blue" });
        }
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

async function render_summary(frm) {
    const { company_gstin, gst_return, from_date, to_date } = frm.doc;
    if (!company_gstin || !gst_return || !from_date || !to_date) {
        frappe.show_alert({
            message: __("Select Company, GSTIN, GST Return and the period first."),
            indicator: "orange",
        });
        return;
    }

    const { message } = await frm.call("get_summary", {
        company_gstin,
        return_type: gst_return,
        date_range: [from_date, to_date],
    });

    const summaries = message?.summaries || [];
    if (!summaries.length) {
        return render_summary_placeholder(
            frm,
            __("No summary found for this period yet. Click Sync to fetch it from the GST Portal."),
        );
    }

    const html = summaries.map((summary) => render_period_block(summary, gst_return)).join("");
    set_summary_html(frm, html);
}

function set_summary_html(frm, inner_html) {
    frm.get_field("summary_html")?.$wrapper.html(`
        <div class="gst-return-summary">
            <div class="summary-heading">${__("Summary")}</div>
            ${inner_html}
        </div>`);
}

function render_period_block(summary, gst_return) {
    const is_2b = gst_return === "GSTR-2B";
    const status = summary.last_updated_on
        ? __("Last synced {0}", [frappe.datetime.str_to_user(summary.last_updated_on)])
        : "";

    return `
        <div class="period-block">
            <div class="period-title">${gst_return} &middot; ${format_period(summary.period)}</div>
            ${is_2b && summary.itc ? render_itc_cards(summary.itc) : ""}
            ${render_section_table(summary)}
            <div class="text-muted sync-status">${status}</div>
        </div>`;
}

function render_itc_cards(itc) {
    const breakup = (bucket) =>
        TAX_FIELDS.map((f) => `<span>${f.toUpperCase()} ${format_number(bucket[f])}</span>`).join("");

    const card = (label, bucket) => `
        <div class="itc-card">
            <div class="text-muted itc-card__label">${label}</div>
            <div class="itc-card__total">${format_number(bucket.total)}</div>
            <div class="text-muted itc-card__breakup">${breakup(bucket)}</div>
        </div>`;

    return `
        <div class="itc-cards">
            ${card(__("ITC Available"), itc.available)}
            ${card(__("ITC Not Available"), itc.not_available)}
            ${card(__("ITC Reversal"), itc.reversal)}
        </div>`;
}

function render_section_table(summary) {
    const cell = (row, col) => `<td>${col.currency ? format_number(row[col.key]) : row[col.key] ?? ""}</td>`;
    const table_row = (row) => `<tr>${SUMMARY_COLUMNS.map((col) => cell(row, col)).join("")}</tr>`;

    const header = SUMMARY_COLUMNS.map((col) => `<th>${__(col.label)}</th>`).join("");
    const body = summary.sections.map(table_row).join("");
    const total = table_row({ ...summary.totals, section: __("Total") });

    return `
        <table class="table table-bordered section-table">
            <thead><tr>${header}</tr></thead>
            <tbody>${body}</tbody>
            <tfoot>${total}</tfoot>
        </table>`;
}

function render_summary_placeholder(frm, message) {
    const default_message = __(
        "Click Show Summary to view the last synced data, or Sync to fetch it fresh from the GST Portal.",
    );
    set_summary_html(frm, `<div class="text-muted summary-placeholder">${message || default_message}</div>`);
}

function format_period(period) {
    return period && period.length === 6 ? `${period.slice(0, 2)}-${period.slice(2)}` : period;
}
