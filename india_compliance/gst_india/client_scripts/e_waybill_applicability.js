class EwaybillApplicability {
    constructor(frm) {
        this.frm = frm;
    }

    is_e_waybill_applicable(show_message = false) {
        this.frm._ewb_message_list = [];

        if (!gst_settings.enable_e_waybill) return false;

        let is_ewb_applicable = true;
        let message_list = [];

        if (!this.frm.doc.company_gstin) {
            is_ewb_applicable = false;
            message_list.push(__("Company GSTIN is not set. Ensure it's set in Company Address."));
        }

        if (this.frm.doc.is_opening === "Yes") {
            is_ewb_applicable = false;
            message_list.push(
                __("e-Waybill cannot be generated for transaction with 'Is Opening Entry' set to Yes."),
            );
        }

        // at least one item is not a service
        is_ewb_applicable = this.has_goods_item(is_ewb_applicable, message_list);

        if (show_message) this.frm._ewb_message_list.push(...message_list);

        return is_ewb_applicable;
    }

    get_items() {
        return this.frm.doc[india_compliance.get_items_fieldname(this.frm.doctype)] || [];
    }

    has_goods_item(is_ewb_applicable, message_list) {
        let has_goods_item = false;
        for (const item of this.get_items()) {
            if (item.gst_hsn_code && !item.gst_hsn_code.startsWith("99") && item.qty !== 0) {
                has_goods_item = true;
                break;
            }
        }

        if (!has_goods_item) {
            is_ewb_applicable = false;
            message_list.push(__("All items are service items (HSN code starts with 99)."));
        }

        return is_ewb_applicable;
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_applicable = this.is_e_waybill_applicable(show_message);
        let message_list = [];

        let is_invalid_invoice_number = india_compliance.validate_invoice_number(this.frm.doc.name);

        if (is_invalid_invoice_number.length > 0) {
            is_ewb_applicable = false;
            message_list.push(...is_invalid_invoice_number);
        }

        if (!is_ewb_applicable) {
            this.frm._ewb_message_list.push(...message_list);
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
            message_list.push(__("Customer Address is mandatory to generate e-Waybill."));
        }

        if (this.frm.doc.company_gstin === this.frm.doc.billing_address_gstin) {
            is_ewb_generatable = false;
            message_list.push(__("Company GSTIN and Billing Address GSTIN are same."));
        }

        if (show_message) {
            this.frm._ewb_message_list.push(...message_list);
        }

        return is_ewb_generatable;
    }

    async auto_generate_e_waybill() {
        if (
            this.frm.doc.is_return ||
            this.frm.doc.is_debit_note ||
            this.frm.doc.ewaybill ||
            !india_compliance.is_api_enabled() ||
            !gst_settings.auto_generate_e_waybill ||
            !this.is_e_waybill_generatable() ||
            !(await has_e_waybill_threshold_met(this.frm)) ||
            is_e_invoice_applicable(this.frm)
        )
            return false;

        return true;
    }
}

class PurchaseInvoiceEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable(show_message = false) {
        return super.is_e_waybill_applicable(show_message) && gst_settings.enable_e_waybill_from_pi;
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];
        if (!this.frm.doc.supplier_address) {
            is_ewb_generatable = false;
            message_list.push(__("Supplier Address is mandatory to generate e-Waybill."));
        }

        if (this.frm.doc.company_gstin === this.frm.doc.supplier_gstin) {
            is_ewb_generatable = false;
            message_list.push(__("Company GSTIN and Supplier GSTIN are same."));
        }

        if (show_message) {
            this.frm._ewb_message_list.push(...message_list);
        }

        return is_ewb_generatable;
    }

    is_e_waybill_api_enabled() {
        return super.is_e_waybill_api_enabled() && gst_settings.enable_e_waybill_from_pi;
    }
}

class PurchaseReceiptEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable(show_message = false) {
        return super.is_e_waybill_applicable(show_message) && gst_settings.enable_e_waybill_from_pr;
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];
        if (!this.frm.doc.supplier_address) {
            is_ewb_generatable = false;
            message_list.push(__("Supplier Address is mandatory to generate e-Waybill."));
        }

        if (this.frm.doc.company_gstin === this.frm.doc.supplier_gstin) {
            is_ewb_generatable = false;
            message_list.push(__("Company GSTIN and Supplier GSTIN are same."));
        }

        if (show_message) {
            this.frm._ewb_message_list.push(...message_list);
        }

        return is_ewb_generatable;
    }

    is_e_waybill_api_enabled() {
        return super.is_e_waybill_api_enabled() && gst_settings.enable_e_waybill_from_pr;
    }
}

class DeliveryNoteEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable(show_message = false) {
        return super.is_e_waybill_applicable(show_message) && gst_settings.enable_e_waybill_from_dn;
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];
        if (!this.frm.doc.customer_address) {
            is_ewb_generatable = false;
            message_list.push(__("Customer Address is mandatory to generate e-Waybill."));
        }

        if (show_message) {
            this.frm._ewb_message_list.push(...message_list);
        }

        return is_ewb_generatable;
    }

    is_e_waybill_api_enabled() {
        return super.is_e_waybill_api_enabled() && gst_settings.enable_e_waybill_from_dn;
    }
}

class StockEntryEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable(show_message = false) {
        this.frm._ewb_message_list = [];

        if (
            !gst_settings.enable_e_waybill ||
            !gst_settings.enable_e_waybill_for_sc ||
            !india_compliance.E_WAYBILL_STOCK_ENTRY_PURPOSES.includes(this.frm.doc.purpose)
        )
            return false;

        let is_ewb_applicable = true;
        let message_list = [];
        const is_return = this.frm.doc.is_return;

        if (is_return && !this.frm.doc.bill_to_gstin) {
            is_ewb_applicable = false;
            message_list.push(__("Bill To GSTIN is not set. Ensure it's set in Bill To Address."));
        }

        if (!is_return && !this.frm.doc.bill_from_gstin) {
            is_ewb_applicable = false;
            message_list.push(__("Bill From GSTIN is not set. Ensure it's set in Bill From Address."));
        }

        const same_gstin = this.frm.doc.bill_from_gstin === this.frm.doc.bill_to_gstin;
        const applicable_for_same_gstin = !(
            is_return || india_compliance.SUBCONTRACTING_PURPOSES.includes(this.frm.doc.purpose)
        );

        if (same_gstin && !applicable_for_same_gstin) {
            is_ewb_applicable = false;
            message_list.push(__("Bill From GSTIN and Bill To GSTIN are same."));
        }

        if (this.frm.doc.is_opening === "Yes") {
            is_ewb_applicable = false;
            message_list.push(
                __("e-Waybill cannot be generated for transaction with 'Is Opening Entry' set to Yes."),
            );
        }

        // at least one item is not a service
        is_ewb_applicable = this.has_goods_item(is_ewb_applicable, message_list);

        if (show_message) this.frm._ewb_message_list.push(...message_list);

        return is_ewb_applicable;
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];

        if (!this.frm.doc.bill_to_address) {
            is_ewb_generatable = false;
            message_list.push(__("Bill To address is mandatory to generate e-Waybill."));
        }

        if (show_message) {
            this.frm._ewb_message_list.push(...message_list);
        }

        return is_ewb_generatable;
    }

    is_e_waybill_api_enabled() {
        return (
            india_compliance.E_WAYBILL_STOCK_ENTRY_PURPOSES.includes(this.frm.doc.purpose) &&
            super.is_e_waybill_api_enabled() &&
            gst_settings.enable_e_waybill_for_sc
        );
    }
}

class AssetMovementEwaybill extends EwaybillApplicability {
    is_inward() {
        return this.frm.doc.purpose === "Receipt";
    }

    is_e_waybill_applicable(show_message = false) {
        // company_gstin is referred to as the generator of the e-Waybill, same as `onload`
        this.frm.doc.company_gstin = this.is_inward()
            ? this.frm.doc.bill_to_gstin
            : this.frm.doc.bill_from_gstin;

        return (
            super.is_e_waybill_applicable(show_message) && gst_settings.enable_e_waybill_from_asset_movement
        );
    }

    is_e_waybill_generatable(show_message = false) {
        // Do we have everything needed to generate e-Waybill for asset movement
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];
        const [party_field, party_label] = this.is_inward()
            ? ["bill_from_address", "Bill From"]
            : ["bill_to_address", "Bill To"];

        if (!this.frm.doc[party_field]) {
            is_ewb_generatable = false;
            message_list.push(`${party_label} address is mandatory to generate e-Waybill.`);
        }

        if (show_message) {
            this.frm._ewb_message += message_list.map((message) => `<li>${message}</li>`).join("");
        }

        return is_ewb_generatable;
    }

    is_e_waybill_api_enabled() {
        return super.is_e_waybill_api_enabled() && gst_settings.enable_e_waybill_from_asset_movement;
    }
}

class SubcontractingReceiptEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable(show_message = false) {
        return super.is_e_waybill_applicable(show_message) && gst_settings.enable_e_waybill_for_sc;
    }

    is_e_waybill_generatable(show_message = false) {
        let is_ewb_generatable = this.is_e_waybill_applicable(show_message);

        let message_list = [];

        if (!this.frm.doc.supplier_address) {
            is_ewb_generatable = false;
            message_list.push(__("Supplier address is mandatory for e-waybill generation."));
        }

        if (show_message) {
            this.frm._ewb_message_list.push(...message_list);
        }

        return is_ewb_generatable;
    }

    is_e_waybill_api_enabled() {
        return super.is_e_waybill_api_enabled() && gst_settings.enable_e_waybill_for_sc;
    }
}
