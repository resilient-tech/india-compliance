frappe.provide("india_compliance");

india_compliance.quick_info_popover = class QuickInfoPopover {
	constructor(frm, field_dict) {
        /**
	 * Setup tooltip for fields to show details
	 * @param {Object} frm          Form object
	 * @param {Object} field_dict   Dictionary of fields with info to show
	 */

		this.frm = frm;
		this.field_dict = field_dict;
		this.make();
	}
	make() {
		this.create_info_popover();
	}
	create_info_popover() {
		if (!this.field_dict) return;

		for (const [field, info] of Object.entries(this.field_dict)) {
			this.create_info_icon(field);

			if (!this.info_btn) return;

			this.info_btn.popover({
				trigger: "hover",
				placement: "top",
				content: () => this.get_content_html(field, info),
				html: true,
			});
		}
	}
	create_info_icon(field) {
		let field_area = this.frm.get_field(field).$wrapper.find(".clearfix");
		this.info_btn = $(`<i class="fa fa-info-circle"></i>`).appendTo(field_area);
	}
	get_content_html(field, info) {
		let field_lable = frappe.meta.get_label(this.frm.doctype, field);

		return `
			<div class="quick-info-popover">
				<div class="preview-field">
					<div class="preview-label text-muted">${__(field_lable)}</div>
					<hr>
					<div class="preview-value">${info}</div>
				</div>
			`;
	}
};
