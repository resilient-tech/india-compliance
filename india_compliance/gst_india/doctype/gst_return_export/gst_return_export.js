// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

// GST Return Export — Phase 1 (GSTR-2A / 2B). Sync runs as a background job and
// reports progress over realtime in two phases (0->100% each): FETCH (portal)
// then SAVE (DB).
const FETCH_PROGRESS = "update_2a_2b_api_progress";
const SAVE_PROGRESS = "update_2a_2b_transactions_progress";

frappe.ui.form.on("GST Return Export", {
    setup: set_realtime_listeners,

    refresh(frm) {
        frm.disable_save();
        setup_actions(frm);
        render_summary_placeholder(frm);
    },

    async company(frm) {
        frm.set_value("company_gstin", null);
        if (!frm.doc.company) return;

        const [gstin] = await india_compliance.set_gstin_options(frm);
        frm.set_value("company_gstin", gstin);
    },
});

function setup_actions(frm) {
    frm.add_custom_button(__("Sync"), () => sync_return_data(frm));
}

async function sync_return_data(frm) {
    if (!india_compliance.is_api_enabled()) {
        frappe.throw(__("Enable the GST API in GST Settings to sync from the GST Portal."));
    }

    const { company, company_gstin, gst_return, from_date, to_date } = frm.doc;
    if (!company || !company_gstin || !gst_return || !from_date || !to_date) {
        frappe.throw(__("Select Company, GSTIN, GST Return and the period before syncing."));
    }

    show_progress(frm, 0, __("Fetching data from the GST Portal"));

    const { message } = await frm.taxpayer_api_call("sync_return_data", {
        company_gstin,
        return_type: gst_return,
        date_range: [from_date, to_date],
    });

    if (message?.message) {
        frm.dashboard.hide();
        frappe.show_alert({ message: message.message, indicator: message.indicator || "blue" });
    }
}

function set_realtime_listeners(frm) {
    frappe.realtime.on(FETCH_PROGRESS, (data) => update_progress(frm, data, { is_fetch_phase: true }));
    frappe.realtime.on(SAVE_PROGRESS, (data) => update_progress(frm, data, { is_fetch_phase: false }));

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
}

function update_progress(frm, { current_progress, return_period, is_last_period }, { is_fetch_phase }) {
    show_progress(
        frm,
        current_progress,
        is_fetch_phase
            ? __("Fetching data from the GST Portal")
            : __("Saving data for return period {0}", [return_period]),
    );

    if (is_last_period) frm.last_sync_period = return_period;

    const sync_complete =
        !is_fetch_phase && current_progress === 100 && return_period === frm.last_sync_period;
    if (sync_complete) notify_sync_complete(frm);
}

function notify_sync_complete(frm) {
    setTimeout(() => {
        frm.dashboard.hide();
        frm.refresh();
        frm.dashboard.set_headline(__("Successfully Synced"));
        setTimeout(() => {
            frm.dashboard.clear_headline();
        }, 2000);
    }, 1000);
}

function show_progress(frm, percent, message) {
    frm.dashboard.show_progress(__("Sync Progress"), percent, message);
}

function render_summary_placeholder(frm) {
    frm.get_field("summary_html")?.$wrapper.html(`
		<div class="text-muted" style="padding: 2.5rem 1rem; text-align: center; border: 1px dashed var(--border-color); border-radius: 8px;">
			${__("Select Company, GSTIN, GST Return and period, then Sync. The summary will appear here.")}
		</div>
	`);
}
