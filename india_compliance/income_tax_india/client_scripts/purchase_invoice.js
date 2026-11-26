india_compliance.set_msme_due_date = ({ purchase_invoice, due_date }) => {
    frappe.hide_msgprint();

    const frm = frappe.views.formview["Purchase Invoice"]?.frm;
    if (frm?.doc.name !== purchase_invoice || frm.doc.docstatus !== 0) return;

    const schedule = frm.doc.payment_schedule || [];
    if (!schedule.length) return frm.set_value("due_date", due_date);

    const last_row = schedule.reduce((last, row) => (row.due_date > last.due_date ? row : last));
    frappe.model.set_value(last_row.doctype, last_row.name, "due_date", due_date);

    frm.doc.due_date = due_date;
    frm.refresh_field("due_date");
};
