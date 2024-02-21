class EwaybillApplicability {
    constructor(frm) {
        this.frm = frm;
    }

    is_e_waybill_applicable(show_message = false) {
        if (!gst_settings.enable_e_waybill) return false;

        let is_ewb_applicable = true;
        let message_list = [];

        if (!this.frm.doc.company_gstin) {
            is_ewb_applicable = false;
            message_list.push(
                "Company GSTIN is not set. Ensure its set in Company Address."
            );
        }

        if (this.frm.doc.is_opening === "Yes") {
            is_ewb_applicable = false;
            message_list.push(
                "e-Waybill cannot be generated for transaction with 'Is Opening Entry' set to Yes."
            );
        }

        // at least one item is not a service
        let has_goods_item = false;
        for (const item of this.frm.doc.items) {
            if (
                item.gst_hsn_code &&
                !item.gst_hsn_code.startsWith("99") &&
                item.qty !== 0
            ) {
                has_goods_item = true;
                break;
            }
        }

        if (!has_goods_item) {
            is_ewb_applicable = false;
            message_list.push("All items are service items (HSN code starts with 99).");
        }

        this.frm._ewb_message = "";
        if (show_message) {
            this.frm._ewb_message = message_list
                .map(message => `<li>${message}</li>`)
                .join("");
        }

        return is_ewb_applicable;
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_applicable = this.is_e_waybill_applicable(show_message);
        let message_list = [];

        let is_invalid_invoice_number = india_compliance.validate_invoice_number(
            this.frm.doc.name
        );

        if (is_invalid_invoice_number.length > 0) {
            is_ewb_applicable = false;
            message_list.push(...is_invalid_invoice_number);
        }

        if (!is_ewb_applicable) {
            this.frm._ewb_message += message_list
                .map(message => `<li>${message}</li>`)
                .join("");
        }

        return is_ewb_applicable;
    }

    auto_generate_e_waybill() {
        return false;
    }

    is_e_waybill_api_enabled() {
        return gst_settings.enable_api && gst_settings.enable_e_waybill;
    }
}

class SalesInvoiceEwaybill extends EwaybillApplicability {
    is_e_waybill_generatable(show_message = false) {
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];
        if (!this.frm.doc.customer_address) {
            is_ewb_generatable = false;
            message_list.push("Customer Address is mandatory to generate e-Waybill.");
        }

        if (this.frm.doc.company_gstin === this.frm.doc.billing_address_gstin) {
            is_ewb_generatable = false;
            message_list.push("Company GSTIN and Billing Address GSTIN are same.");
        }

        if (show_message) {
            this.frm._ewb_message += message_list
                .map(message => `<li>${message}</li>`)
                .join("");
        }

        return is_ewb_generatable;
    }

    auto_generate_e_waybill() {
        if (
            this.frm.doc.is_return ||
            this.frm.doc.is_debit_note ||
            this.frm.doc.ewaybill ||
            !india_compliance.is_api_enabled() ||
            !gst_settings.auto_generate_e_waybill ||
            !this.is_e_waybill_generatable() ||
            !has_e_waybill_threshold_met(this.frm) ||
            is_e_invoice_applicable(this.frm)
        )
            return false;

        return true;
    }
}

class PurchaseInvoiceEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable(show_message = false) {
        return (
            super.is_e_waybill_applicable(show_message) &&
            gst_settings.enable_e_waybill_from_pi
        );
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];
        if (!this.frm.doc.supplier_address) {
            is_ewb_generatable = false;
            message_list.push("Supplier Address is mandatory to generate e-Waybill.");
        }

        if (this.frm.doc.company_gstin === this.frm.doc.supplier_gstin) {
            is_ewb_generatable = false;
            message_list.push("Company GSTIN and Supplier GSTIN are same.");
        }

        if (show_message) {
            this.frm._ewb_message += message_list
                .map(message => `<li>${message}</li>`)
                .join("");
        }

        return is_ewb_generatable;
    }

    is_e_waybill_api_enabled() {
        return (
            super.is_e_waybill_api_enabled() && gst_settings.enable_e_waybill_from_pi
        );
    }
}

class PurchaseReceiptEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable(show_message = false) {
        return (
            super.is_e_waybill_applicable(show_message) &&
            gst_settings.enable_e_waybill_from_pr
        );
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];
        if (!this.frm.doc.supplier_address) {
            is_ewb_generatable = false;
            message_list.push("Supplier Address is mandatory to generate e-Waybill.");
        }

        if (this.frm.doc.company_gstin === this.frm.doc.supplier_gstin) {
            is_ewb_generatable = false;
            message_list.push("Company GSTIN and Supplier GSTIN are same.");
        }

        if (show_message) {
            this.frm._ewb_message += message_list
                .map(message => `<li>${message}</li>`)
                .join("");
        }

        return is_ewb_generatable;
    }

    is_e_waybill_api_enabled() {
        return (
            super.is_e_waybill_api_enabled() && gst_settings.enable_e_waybill_from_pr
        );
    }
}

class DeliveryNoteEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable(show_message = false) {
        return (
            super.is_e_waybill_applicable(show_message) &&
            gst_settings.enable_e_waybill_from_dn
        );
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];
        if (!this.frm.doc.customer_address) {
            is_ewb_generatable = false;
            message_list.push("Customer Address is mandatory to generate e-Waybill.");
        }

        if (show_message) {
            this.frm._ewb_message += message_list
                .map(message => `<li>${message}</li>`)
                .join("");
        }

        return is_ewb_generatable;
    }

    is_e_waybill_api_enabled() {
        return (
            super.is_e_waybill_api_enabled() && gst_settings.enable_e_waybill_from_dn
        );
    }
}
