frappe.provide("india_compliance");

india_compliance.ViewGroup = class ViewGroup {
    constructor(options) {
        Object.assign(this, options);
        this.views = {};
        this.render();
    }

    render() {
        $(this.$wrapper).append(
            `
            <div class= "view-group">
                <div class="view-switch"></div>
            </div>
            `
        );

        this.view_group_container = $(`
            <ul
                class= "nav custom-tabs rounded-sm border d-inline-flex"
                id = "custom-tabs"
                role = "tablist"
            ></ul>
        `).appendTo(this.$wrapper.find(`.view-switch`));

        this.make_views();
        this.setup_events();
    }

    set_active_view(view) {
        this.active_view = view;
        this.views[`${view}_view`].children().tab("show");
    }

    make_views() {
        this.view_names.forEach(view => {
            this.views[`${view}_view`] = $(
                `
                <li class="nav-item show">
                    <a
                        class="nav-link ${this.active_view === view ? "active" : ""}"
                        id = "gstr-1-__${view}-view"
                        data-toggle="tab"
                        data-fieldname="${view}"
                        href="#gstr-1-__${view}-view"
                        role="tab"
                        aria-controls="gstr-1-__${view}-view"
                        aria-selected="true"
            >
            ${frappe.unscrub(view)}
                    </a>
                </li>
            `
            ).appendTo(this.view_group_container);
        });
    }

    setup_events() {
        this.view_group_container.off("click").on("click", ".nav-link", e => {
            e.preventDefault();
            e.stopImmediatePropagation();

            this.target = $(e.currentTarget);
            const target_view = this.target.attr("data-fieldname");

            this.set_active_view(target_view);
            this.callback && this.callback(target_view);
        });
    }

    disable_view(view, title) {
        this.views[`${view}_view`].attr("title", title);
        this.views[`${view}_view`].find(".nav-link").addClass("disabled");
    }

    enable_view(view) {
        this.views[`${view}_view`].removeAttr("title");
        this.views[`${view}_view`].find(".nav-link").removeClass("disabled");
    }
}