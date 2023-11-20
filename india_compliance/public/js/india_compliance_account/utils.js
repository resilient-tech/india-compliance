import { get_invoice_history, send_invoice_email } from './services/AccountService';

export const getReadableNumber = function (num, precision = 2) {
    return format_number(num, null, precision);
};