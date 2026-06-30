// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

// GST Return Export — Phase 1 (GSTR-2A / 2B).
// Built the Purchase Reconciliation Tool way: a Single DocType whose client
// script is the tool. Filters are the DocType fields; page actions are Sync and
// Export; the summary renders into the `summary_html` area (a frappe DataTable
// in M4). Milestone 1 = scaffold: actions are inert placeholders.

frappe.ui.form.on("GST Return Export", {
    refresh(frm) {
        frm.disable_save();
        render_summary_placeholder(frm);
    },

    company(frm) {
        frm.set_value("company_gstin", null);
    },
});

function render_summary_placeholder(frm) {
    const field = frm.get_field("summary_html");
    if (!field) return;

    field.$wrapper.html(`
		<div class="text-muted" style="padding: 2.5rem 1rem; text-align: center; border: 1px dashed var(--border-color); border-radius: 8px;">
			${__("Select Company, GSTIN, GST Return and period, then Sync. The summary will appear here.")}
		</div>
	`);
}
