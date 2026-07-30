frappe.provide("india_compliance");

india_compliance.ViewGroup = class ViewGroup {
    constructor(options) {
        Object.assign(this, options);
        this.views = {};
        this.render();
    }

    render() {
        // frappe's segmented control: a rail with one pressed pill
        this.view_group_container = $(
            `<div class="view-group es-tab-buttons" role="radiogroup"></div>`,
        ).appendTo(this.$wrapper);

        this.make_views();
        this.setup_events();
    }

    set_active_view(view) {
        this.active_view = view;

        Object.entries(this.views).forEach(([name, $pill]) => {
            const active = name === `${view}_view`;
            $pill.attr("data-state", active ? "active" : "inactive").attr("aria-checked", active);
        });
    }

    make_views() {
        this.view_names.forEach((view) => {
            const active = this.active_view === view;

            this.views[`${view}_view`] = $(`
                <button
                    class="es-pill"
                    role="radio"
                    data-fieldname="${view}"
                    data-state="${active ? "active" : "inactive"}"
                    aria-checked="${active}"
                >
                    ${frappe.unscrub(view)}
                </button>
            `).appendTo(this.view_group_container);
        });
    }

    setup_events() {
        this.view_group_container.off("click").on("click", ".es-pill", (e) => {
            e.preventDefault();
            e.stopImmediatePropagation();

            const target_view = $(e.currentTarget).attr("data-fieldname");

            this.set_active_view(target_view);
            this.callback && this.callback(target_view);
        });
    }

    disable_view(view, title) {
        this.views[`${view}_view`].attr({ title, "data-disabled": "" });
    }

    enable_view(view) {
        this.views[`${view}_view`].removeAttr("title").removeAttr("data-disabled");
    }
};
