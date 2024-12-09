import frappe
<<<<<<< HEAD
=======
from frappe.model.document import bulk_insert
from frappe.model.naming import _generate_random_string
>>>>>>> c95f60da (fix: use bulk insert to ignore validations)


def execute():
    if not frappe.db.table_exists("Bill of Entry Taxes"):
        return

    boe_taxes = frappe.qb.DocType("Bill of Entry Taxes")
    boe_taxes_docs = frappe.qb.from_(boe_taxes).select("*").run(as_dict=True)

<<<<<<< HEAD
=======
    ic_taxes_names = set(
        frappe.get_all("India Compliance Taxes and Charges", pluck="name")
    )
    ic_taxes = []

>>>>>>> c95f60da (fix: use bulk insert to ignore validations)
    for doc in boe_taxes_docs:
        ic_taxes_doc = frappe.get_doc(
            {
                **doc,
                "doctype": "India Compliance Taxes and Charges",
<<<<<<< HEAD
                "name": None,
                "base_total": doc.total,
            }
        )
        ic_taxes_doc.insert(ignore_if_duplicate=True)

    # Drop the old table
    frappe.db.delete("Bill of Entry Taxes")
=======
                "name": set_name(doc.name, ic_taxes_names),
                "base_total": doc.total,
            }
        )

        ic_taxes.append(ic_taxes_doc)

    bulk_insert("India Compliance Taxes and Charges", ic_taxes)

    # Drop the old table
    frappe.db.delete("Bill of Entry Taxes")


def set_name(name, names):
    new_name = name
    while new_name in names:
        new_name = _generate_random_string(10)

    names.add(new_name)
    return new_name
>>>>>>> c95f60da (fix: use bulk insert to ignore validations)
