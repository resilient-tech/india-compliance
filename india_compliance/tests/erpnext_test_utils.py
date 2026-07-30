import frappe
from erpnext.buying.doctype.purchase_order.mapper import get_mapped_subcontracting_order
from frappe.utils import getdate, nowdate


# from erpnext.projects.doctype.project.test_project import make_project
def create_task(
    subject,
    start=None,
    end=None,
    depends_on=None,
    project=None,
    parent_task=None,
    is_group=0,
    is_template=0,
    begin=0,
    duration=0,
    save=True,
    priority=None,
):
    if not frappe.db.exists("Task", subject):
        task = frappe.new_doc("Task")
        task.status = "Open"
        task.subject = subject
        task.exp_start_date = start or nowdate()
        task.exp_end_date = end or nowdate()
        task.project = (
            project or None if is_template else frappe.get_value("Project", {"project_name": "_Test Project"})
        )
        task.is_template = is_template
        task.start = begin
        task.duration = duration
        task.is_group = is_group
        task.parent_task = parent_task
        task.priority = priority
        if save:
            task.save()
    else:
        task = frappe.get_doc("Task", subject)

    if depends_on:
        task.append("depends_on", {"task": depends_on})
        if save:
            task.save()
    return task


def make_project_template(project_template_name, project_tasks=None):
    if project_tasks is None:
        project_tasks = []
    if not frappe.db.exists("Project Template", project_template_name):
        project_tasks = project_tasks or [
            create_task(subject="_Test Template Task 1", is_template=1, begin=0, duration=3),
            create_task(subject="_Test Template Task 2", is_template=1, begin=0, duration=2),
        ]
        doc = frappe.get_doc(doctype="Project Template", name=project_template_name)
        for task in project_tasks:
            doc.append("tasks", {"task": task.name})
        doc.insert()

    return frappe.get_doc("Project Template", project_template_name)


def make_project(args):
    args = frappe._dict(args)

    if args.project_name and frappe.db.exists("Project", {"project_name": args.project_name}):
        return frappe.get_doc("Project", {"project_name": args.project_name})

    project = frappe.get_doc(
        doctype="Project",
        project_name=args.project_name,
        status="Open",
        expected_start_date=args.start_date,
        company=args.company or "_Test Company",
    )

    if args.project_template_name:
        template = make_project_template(args.project_template_name)
        project.project_template = template.name

    project.insert()

    return project


# from erpnext.accounts.doctype.account.test_account import create_account
def create_account(**kwargs):
    account = frappe.db.get_value(
        "Account", filters={"account_name": kwargs.get("account_name"), "company": kwargs.get("company")}
    )
    if account:
        account = frappe.get_doc("Account", account)
        account.update(
            dict(
                is_group=kwargs.get("is_group", 0),
                parent_account=kwargs.get("parent_account"),
            )
        )
        account.save()
        return account.name
    else:
        account = frappe.get_doc(
            doctype="Account",
            is_group=kwargs.get("is_group", 0),
            account_name=kwargs.get("account_name"),
            account_type=kwargs.get("account_type"),
            parent_account=kwargs.get("parent_account"),
            company=kwargs.get("company"),
            account_currency=kwargs.get("account_currency"),
        )

        account.save()
        return account.name


# from erpnext.accounts.doctype.journal_entry.test_journal_entry import make_journal_entry
def make_journal_entry(
    account1,
    account2,
    amount,
    cost_center=None,
    posting_date=None,
    exchange_rate=1,
    save=True,
    submit=False,
    project=None,
    company=None,
    voucher_type="Journal Entry",
):
    if not cost_center:
        cost_center = "_Test Cost Center - _TC"

    jv = frappe.new_doc("Journal Entry")
    jv.posting_date = posting_date or nowdate()
    jv.company = company or "_Test Company"
    jv.voucher_type = voucher_type
    jv.remark = "test"
    jv.multi_currency = 1
    jv.set(
        "accounts",
        [
            {
                "account": account1,
                "cost_center": cost_center,
                "project": project,
                "debit_in_account_currency": amount if amount > 0 else 0,
                "credit_in_account_currency": abs(amount) if amount < 0 else 0,
                "exchange_rate": exchange_rate,
            },
            {
                "account": account2,
                "cost_center": cost_center,
                "project": project,
                "credit_in_account_currency": amount if amount > 0 else 0,
                "debit_in_account_currency": abs(amount) if amount < 0 else 0,
                "exchange_rate": exchange_rate,
            },
        ],
    )
    if save or submit:
        jv.insert()

        if submit:
            jv.submit()

    return jv


# from erpnext.setup.doctype.transaction_deletion_record.test_transaction_deletion_record import
# create_and_submit_transaction_deletion_doc
def create_and_submit_transaction_deletion_doc(company):
    tdr = frappe.get_doc(
        {
            "doctype": "Transaction Deletion Record",
            "company": company,
            "process_in_single_transaction": 1,
        }
    )
    tdr.insert()

    tdr.generate_to_delete_list()
    tdr.reload()

    tdr.process_in_single_transaction = 1
    tdr.submit()
    tdr.reload()
    return tdr


# from erpnext.controllers.tests.test_subcontracting_controller import get_rm_items
def get_rm_items(supplied_items):
    rm_items = []

    for item in supplied_items:
        rm_items.append(
            {
                "main_item_code": item.main_item_code,
                "item_code": item.rm_item_code,
                "qty": item.required_qty,
                "rate": item.rate,
                "stock_uom": item.stock_uom,
                "warehouse": item.reserve_warehouse,
                "use_serial_batch_fields": 0,
            }
        )

    return rm_items


# from erpnext.manufacturing.doctype.production_plan.test_production_plan import make_bom
def make_bom(**args):
    args = frappe._dict(args)

    bom = frappe.get_doc(
        {
            "doctype": "BOM",
            "is_default": 1,
            "item": args.item,
            "currency": args.currency or "USD",
            "quantity": args.quantity or 1,
            "company": args.company or "_Test Company",
            "routing": args.routing,
            "with_operations": args.with_operations or 0,
            "process_loss_percentage": args.process_loss_percentage or 0,
        }
    )

    if args.operating_cost_per_bom_quantity:
        bom.fg_based_operating_cost = 1
        bom.operating_cost_per_bom_quantity = args.operating_cost_per_bom_quantity

    for item in args.raw_materials:
        item_doc = frappe.get_doc("Item", item)
        bom.append(
            "items",
            {
                "item_code": item,
                "qty": args.rm_qty or 1.0,
                "uom": item_doc.stock_uom,
                "stock_uom": item_doc.stock_uom,
                "rate": item_doc.valuation_rate or args.rate,
                "source_warehouse": args.source_warehouse,
            },
        )

    if args.scrap_items:
        for item in args.scrap_items:
            item_doc = frappe.get_doc("Item", item)
            bom.append(
                "secondary_items",
                {
                    "secondary_item_type": "Scrap",
                    "item_code": item,
                    "item_name": item,
                    "uom": item_doc.stock_uom,
                    "stock_uom": item_doc.stock_uom,
                    "qty": args.scrap_qty or 1,
                    "cost_allocation_per": args.scrap_cost_allocation_per or 10,
                    "process_loss_per": args.scrap_process_loss_per or 10,
                },
            )

    if not args.do_not_save:
        bom.insert(ignore_permissions=True)

        if not args.do_not_submit:
            bom.submit()

    if args.set_as_default_bom and not args.do_not_save and not args.do_not_submit:
        frappe.set_value("Item", args.item, "default_bom", bom.name)

    return bom


# from erpnext.subcontracting.doctype.subcontracting_order.test_subcontracting_order import create_subcontracting_order
def create_subcontracting_order(**args):
    args = frappe._dict(args)
    sco = get_mapped_subcontracting_order(source_name=args.po_name)

    for item in sco.items:
        item.include_exploded_items = args.get("include_exploded_items", 1)

    if args.warehouse:
        for item in sco.items:
            item.warehouse = args.warehouse
    else:
        warehouse = frappe.get_value("Purchase Order", args.po_name, "set_warehouse")
        if warehouse:
            for item in sco.items:
                item.warehouse = warehouse
        else:
            po = frappe.get_doc("Purchase Order", args.po_name)
            warehouses = []
            for item in po.items:
                warehouses.append(item.warehouse)

            for idx, val in enumerate(sco.items):
                val.warehouse = warehouses[idx]

    warehouses = set()
    for item in sco.items:
        warehouses.add(item.warehouse)

    if len(warehouses) == 1:
        sco.set_warehouse = next(iter(warehouses))

    if not args.do_not_save:
        sco.insert()
        if not args.do_not_submit:
            sco.submit()

    return sco


# from erpnext.accounts.doctype.payment_reconciliation.test_payment_reconciliation import create_fiscal_year
def create_fiscal_year(company, year_start_date, year_end_date):
    fy_docname = frappe.db.exists(
        "Fiscal Year", {"year_start_date": year_start_date, "year_end_date": year_end_date}
    )
    if not fy_docname:
        fy_doc = frappe.get_doc(
            {
                "doctype": "Fiscal Year",
                "year": f"{getdate(year_start_date).year}-{getdate(year_end_date).year}",
                "year_start_date": year_start_date,
                "year_end_date": year_end_date,
                "companies": [{"company": company}],
            }
        ).save()
        return fy_doc
    else:
        fy_doc = frappe.get_doc("Fiscal Year", fy_docname)
        if not frappe.db.exists("Fiscal Year Company", {"parent": fy_docname, "company": company}):
            fy_doc.append("companies", {"company": company})
            fy_doc.save()
        return fy_doc


# from erpnext.assets.doctype.asset.test_asset import create_asset
def create_asset(**args):
    args = frappe._dict(args)

    asset = frappe.get_doc(
        {
            "doctype": "Asset",
            "asset_name": args.asset_name or "Macbook Pro 1",
            "asset_category": args.asset_category,
            "item_code": args.item_code,
            "company": args.company or "_Test Indian Registered Company",
            "purchase_date": args.purchase_date or args.available_for_use_date,
            "available_for_use_date": args.available_for_use_date,
            "calculate_depreciation": args.calculate_depreciation or 0,
            "opening_accumulated_depreciation": args.opening_accumulated_depreciation or 0,
            "opening_number_of_booked_depreciations": args.opening_number_of_booked_depreciations or 0,
            "net_purchase_amount": args.net_purchase_amount or 100000,
            "purchase_amount": args.purchase_amount or args.net_purchase_amount or 100000,
            "location": args.location,
            "cost_center": args.cost_center,
            "asset_owner": args.asset_owner or "Company",
            "asset_type": args.asset_type or "",
            "asset_quantity": args.get("asset_quantity") or 1,
        }
    )

    if asset.calculate_depreciation:
        # a row may set only what differs; the rest falls back to args
        def value(row, fieldname, default=None):
            return row.get(fieldname) or args.get(fieldname) or default

        for finance_book in args.finance_books or [{}]:
            row = frappe._dict(finance_book)
            asset.append(
                "finance_books",
                {
                    "finance_book": value(row, "finance_book"),
                    "depreciation_method": value(row, "depreciation_method", "Written Down Value"),
                    "frequency_of_depreciation": value(row, "frequency_of_depreciation", 12),
                    "total_number_of_depreciations": value(row, "total_number_of_depreciations", 5),
                    "expected_value_after_useful_life": value(row, "expected_value_after_useful_life", 0),
                    "depreciation_start_date": value(
                        row, "depreciation_start_date", args.available_for_use_date
                    ),
                    "daily_prorata_based": value(row, "daily_prorata_based", 0),
                    "rate_of_depreciation": value(row, "rate_of_depreciation", 0),
                },
            )

    if not args.do_not_save:
        asset.insert()

    if args.submit:
        asset.submit()

    return asset


# from erpnext.assets.doctype.asset.test_asset import set_depreciation_settings_in_company
def set_depreciation_settings_in_company(company, accounts):
    frappe.db.set_value(
        "Company",
        company,
        {
            "accumulated_depreciation_account": accounts["accumulated_depreciation_account"],
            "depreciation_expense_account": accounts["depreciation_expense_account"],
            "disposal_account": accounts["disposal_account"],
            "depreciation_cost_center": accounts["depreciation_cost_center"],
        },
    )
    frappe.db.set_single_value("Accounts Settings", "book_asset_depreciation_entry_automatically", 1)
