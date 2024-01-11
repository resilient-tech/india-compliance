import frappe


def execute():
    frappe.db.sql(
        """
        UPDATE `tabSingles` AS t1
        SET `value` = (
            SELECT IFNULL(
                (SELECT `value` FROM `tabSingles` AS t2
                WHERE t2.`doctype` = 'GST Settings'
                AND t2.`field` = 'enable_retry_e_invoice_generation'), 0)
        )
        WHERE t1.`doctype` = 'GST Settings'
        AND t1.`field` = 'enable_retry_einv_ewb_generation'
    """
    )
