frappe.provide("ic");

ic.NumberCardManager = class NumberCardManager {
	constructor(opts) {
		Object.assign(this, opts);
		this.make_cards();
	}

	make_cards() {
		/**
		opts passed to each card
			$wrapper: The div that holds the cards
			cards: A List of dictionary to show information in the card
			sucess: Valid condition to highlight the values in the card
		**/

		this.$wrapper.empty();
		this.$cards = [];
		this.$summary = $(`<div class="report-summary"></div>`)
			.hide()
			.appendTo(this.$wrapper);
		var card_data = this.cards;

		card_data.forEach((summary) => {
			let number_card = new ic.NumberCard(summary);
			this.$cards.push(number_card);

			number_card.$card.appendTo(this.$summary);
		});

		this.$cards.forEach((number_card) => {
			number_card.set_value_color(
				this.condition
					? "text-success"
					: "text-danger"
			);
		});

		this.$summary.css({"border-bottom": "0px", "margin-left": "0px", "margin-right": "0px"});
		this.$summary.show();
	}
};

ic.NumberCard = class NumberCard {
	constructor(options) {
		this.$card = frappe.utils.build_summary_item(options);
	}

	set_value(value) {
		this.$card.find("div").text(value);
	}

	set_value_color(color) {
		this.$card
			.find("div")
			.removeClass("text-danger text-success")
			.addClass(`${color}`);
	}

	set_indicator(color) {
		this.$card
			.find("span")
			.removeClass("indicator red green")
			.addClass(`indicator ${color}`);
	}
};