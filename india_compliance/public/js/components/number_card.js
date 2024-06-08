frappe.provide("india_compliance");

india_compliance.NumberCardManager = class NumberCardManager {
    constructor(opts) {
        Object.assign(this, opts);
        this.make_cards();
        this.show_summary();
    }

    make_cards() {
        this.$wrapper.empty();
        this.$cards = [];
        this.$summary = $(`<div class="report-summary"></div>`)
            .hide()
            .appendTo(this.$wrapper);

        this.cards.forEach(summary => {
            let number_card = frappe.utils.build_summary_item(summary);
            this.$cards.push(number_card);

            number_card.appendTo(this.$summary);
        });

        this.$summary.css({
            "border-bottom": "0px",
            "margin-left": "0px",
            "margin-right": "0px",
        });
    }

    show_summary() {
        if (this.cards.length) this.$summary.show();
    }
};
