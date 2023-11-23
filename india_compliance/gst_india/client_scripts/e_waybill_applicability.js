class EwaybillApplicability {
    constructor(frm) {
        this.frm = frm;
    }

    is_e_waybill_applicable() {
        if (
            // Is Indian Registered Company
            !this.frm.doc.company_gstin ||
            !gst_settings.enable_e_waybill ||
            this.frm.doc.is_opening === "Yes"
        )
            return false;

        // at least one item is not a service
        for (const item of this.frm.doc.items) {
            if (
                item.gst_hsn_code &&
                !item.gst_hsn_code.startsWith("99") &&
                item.qty !== 0
            )
                return true;
        }

        return false;
    }

    is_e_waybill_generatable() {
        return this.is_e_waybill_applicable();
    }

    auto_generate_e_waybill() {
        return false;
    }
}

class SalesInvoiceEwaybill extends EwaybillApplicability {
    is_e_waybill_generatable() {
        return (
            this.is_e_waybill_applicable() &&
            this.frm.doc.customer_address &&
            this.frm.doc.company_gstin !== this.frm.doc.billing_address_gstin
        );
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
    is_e_waybill_applicable() {
        return super.is_e_waybill_applicable() && gst_settings.enable_e_waybill_from_pi;
    }

    is_e_waybill_generatable() {
        return (
            this.is_e_waybill_applicable() &&
            this.frm.doc.supplier_address &&
            this.frm.doc.company_gstin !== this.frm.doc.supplier_gstin
        );
    }
}


class PurchaseReceiptEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable() {
        return super.is_e_waybill_applicable() && gst_settings.enable_e_waybill_from_pr;
    }

    is_e_waybill_generatable() {
        return (
            this.is_e_waybill_applicable() &&
            this.frm.doc.supplier_address &&
            this.frm.doc.company_gstin !== this.frm.doc.supplier_gstin
        );
    }
}

class DeliveryNoteEwaybill extends EwaybillApplicability {
    is_e_waybill_applicable() {
        return super.is_e_waybill_applicable() && gst_settings.enable_e_waybill_from_dn;
    }

    is_e_waybill_generatable() {
        return (
            this.is_e_waybill_applicable() &&
            this.frm.doc.customer_address
        );
    }
}
