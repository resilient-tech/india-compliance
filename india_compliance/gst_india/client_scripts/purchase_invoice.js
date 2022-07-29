frappe.ui.form.on("Purchase Invoice", {
    before_save: function (frm) {
        // hack: values set in frm.doc are not available after save
        if (frm._inward_supply) frm.doc._inward_supply = frm._inward_supply;
    },

    on_submit: function (frm) {
        if (!frm._inward_supply) return;

        frm._inward_supply.name = frm.doc.name;
        // go back to previous page and match the invoice with the inward supply
        setTimeout(() => {
            window.history.back();
            setTimeout(() => {
                const reco_frm = cur_frm;
                if (!reco_frm.purchase_reconciliation_tool) return;
                reco_tool.link_documents(
                    reco_frm,
                    frm._inward_supply.name,
                    frm._inward_supply.isup_name,
                    false
                );
            }, 2000);
        }, 2000);
    },
});
