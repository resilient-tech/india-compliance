import { get_invoice_history, send_invoice_email } from './services/AccountService';

export const getReadableNumber = function (num, precision = 2) {
    return format_number(num, null, precision);
};

export const get_invoice_history_dialog = function (default_email=null) {
    const invoiceHistoryDialog = new frappe.ui.Dialog({
        title: __("Invoice History"),
        fields: get_invoice_history_dialog_fields(default_email),
        primary_action_label: __("Get Invoice History"),
        primary_action: async (values) => {
            const { from_date, to_date } = values;

            const response = await get_invoice_history(from_date, to_date);
            const data = response.message || [];

            const invoiceHistoryTable = frappe.render_template(INVOICE_HISTORY_TABLE, { data_array: data.length > 0 ? data : null });
            invoiceHistoryDialog.fields_dict.invoice_history.html(invoiceHistoryTable);

            invoiceHistoryDialog.fields_dict.invoice_history.df.hidden = 0;

            invoiceHistoryDialog.fields_dict.invoice_history.$wrapper.ready(function () {
                $('.get-invoice').click(async function () {
                    const invoice_name = $(this).data('invoice-name');
                    const email = invoiceHistoryDialog.get_value('email');

                    const response = await send_invoice_email(invoice_name, email);

                    if (response.success) {
                        frappe.msgprint({
                            title: __("Success"),
                            message: __("Invoice will be sent to your email address"),
                            indicator: "green",
                        });
                    }
                });
            });

            invoiceHistoryDialog.refresh();
        },
    });
    return invoiceHistoryDialog;
}

const INVOICE_HISTORY_TABLE = `
    {% if data_array %}
        <div class="invoice-table">
            <table class="table table-bordered">
                <thead>
                    <tr>
                        <th class="text-center">Name</th>
                        <th class="text-center">Posting Date</th>
                        <th class="text-center">Credits</th>
                        <th class="text-center">Grand Total</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {% for data in data_array %}
                    <tr>
                        <td class="text-center">{{ data.name }}</td>
                        <td class="text-center">{{ data.posting_date }}</td>
                        <td class="text-center">{{ data.credits }}</td>
                        <td class="text-center">{{ data.grand_total }}</td>
                        <td>
                            <button
                                class="btn btn-primary get-invoice"
                                data-invoice-name="{{ data.name }}"
                            >
                                Get Invoice
                            </button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <p class="text-center">
            No invoices found! <i class="fa fa-soundcloud" aria-hidden="true"></i>
        </p>
    {% endif %}
`

function get_invoice_history_dialog_fields(default_email=null) {
    return [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
        },
        {
            fieldname: "email",
            label: __("Email"),
            fieldtype: "Data",
            description: __("Invoice will be sent to this email address"),
            options: "Email",
            default: default_email,
        },
        {
            fieldtype: "Column Break"
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today(),
        },
        {
            label: __("Invoice History"),
            fieldtype: "Section Break",
        },
        {
            fieldname: "invoice_history",
            label: __("Invoice History"),
            fieldtype: "HTML",
            hidden: 1,
        }
    ];
}
