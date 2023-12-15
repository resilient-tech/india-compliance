import frappe


def execute():
    """
    'lr_no' field is labeled as 'Vehicle Number' in Purchase Receipt(ERPNext).
    Values will be identified using regex pattern and updated to vehicle_no field.
    REGEX pattern will identify foll0wing sequences:
    - GJO6AB1234
    - gj 06 a 1234
    - gj06-ab-1234
    - Gj06 abc 1234
    """
    REGEX_PATTERN = r"^[a-zA-Z]{2}[-\s]?[0-9]{2}[-\s]?[a-zA-Z]{1,3}[-\s]?[0-9]{4}$"
    pr = frappe.qb.DocType("Purchase Receipt")

    (
        frappe.qb.update(pr)
        .set(pr.vehicle_no, pr.lr_no)
        .where(pr.lr_no.regexp(REGEX_PATTERN))
        .run()
    )

    (frappe.qb.update(pr).set(pr.lr_no, "").where(pr.lr_no.regexp(REGEX_PATTERN)).run())
