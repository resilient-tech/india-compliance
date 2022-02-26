frappe.pages["login"].on_page_load = function (wrapper) {
    new AspLogin(wrapper);
};

class AspLogin {
    constructor(wrapper) {
        this.wrapper = $(wrapper);
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: "",
            single_column: true,
        });

        this.main_section = this.wrapper.find(".layout-main-section");
        this.wrapper.bind("show", () => {
            this.show();
        });
    }

    show() {
        this.main_section.empty().append(frappe.render_template("login"));
    }
}
