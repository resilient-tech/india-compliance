import frappe
from frappe.utils import flt, get_currency_precision, getdate

PAYMENT = "Payment"
CREDIT_NOTE = "Credit Note"
WRITE_OFF = "Write Off"

INVOICE_DOCTYPE = {"Supplier": "Purchase Invoice", "Customer": "Sales Invoice"}
ACCOUNT_TYPE = {"Supplier": "Payable", "Customer": "Receivable"}
PAYMENT_DOCTYPES = ("Journal Entry", "Payment Entry")


class VoucherLedger(frappe._dict):
    def balance_on(self, date=None):
        date = getdate(date) if date else None
        return flt(
            sum(entry.amount for entry in self.entries if not date or entry.posting_date <= date),
            self.precision,
        )

    def paid_on(self):
        """Ledger date on which the balance last came down to zero or below; None while open."""
        balance, paid_on = 0, None

        for entry in self.entries:
            balance = flt(balance + entry.amount, self.precision)
            paid_on = None if balance > 0 else entry.posting_date

        return paid_on

    def settled(self, from_date=None, to_date=None, kinds=None):
        from_date = getdate(from_date) if from_date else None
        to_date = getdate(to_date) if to_date else None

        return flt(
            sum(
                settlement.amount
                for settlement in self.settlements
                if (not from_date or settlement.posting_date >= from_date)
                and (not to_date or settlement.posting_date <= to_date)
                and (not kinds or settlement.kind in kinds)
            ),
            self.precision,
        )


def get_voucher_ledgers(
    company, party_type="Supplier", from_date=None, parties=None, vouchers=None
) -> dict[tuple, VoucherLedger]:
    """Ledger rows per voucher, keyed (voucher_type, voucher_no, party), classified as ERPNext's Accounts Payable / Receivable report does."""
    invoice_doctype = INVOICE_DOCTYPE[party_type]
    ple, query = get_ledger_query(company, party_type, parties)

    if from_date:
        # a voucher's settlements can be dated before it (an advance linked later), so filter vouchers, not rows
        vouchers = get_vouchers_from(ple, query, from_date, vouchers)
        if not vouchers:
            return {}

    returns = get_linked_returns(invoice_doctype, company, parties, vouchers)

    if vouchers:
        vouchers = [*vouchers, *((invoice_doctype, name) for name in returns)]

    rows = get_ledger_rows(ple, query, vouchers)
    precision = get_currency_precision() or 2
    ledgers = {}

    for row in rows:
        row.posting_date = getdate(row.posting_date)
        voucher_no = row.against_voucher_no
        if row.against_voucher_type == invoice_doctype and voucher_no in returns:
            voucher_no = returns[voucher_no]

        key = (row.against_voucher_type, voucher_no, row.party)
        ledger = ledgers.get(key)
        if not ledger:
            ledger = ledgers[key] = VoucherLedger(
                voucher_type=row.against_voucher_type,
                voucher_no=voucher_no,
                party=row.party,
                precision=precision,
                entries=[],
                settlements=[],
            )

        ledger.entries.append(row)
        if kind := get_settlement_kind(row, voucher_no):
            ledger.settlements.append(
                frappe._dict(
                    posting_date=row.posting_date,
                    amount=-row.amount,
                    kind=kind,
                    voucher_type=row.voucher_type,
                    voucher_no=row.voucher_no,
                )
            )

    set_write_offs(ledgers, rows, invoice_doctype)
    return ledgers


def get_unallocated(ledgers, on_date=None) -> dict[str, float]:
    """Credit left on vouchers that settle no bill (advances, unlinked returns), per party."""
    unallocated = {}

    for ledger in ledgers.values():
        balance = ledger.balance_on(on_date)
        if balance < 0:
            unallocated[ledger.party] = unallocated.get(ledger.party, 0) - balance

    return unallocated


def get_settlement_kind(row, voucher_no):
    if row.amount > 0:
        if row.voucher_type in PAYMENT_DOCTYPES and row.voucher_no != row.against_voucher_no:
            return PAYMENT

        return None

    if row.voucher_type not in INVOICE_DOCTYPE.values():
        return PAYMENT

    if row.voucher_no == row.against_voucher_no == voucher_no:
        return PAYMENT

    return CREDIT_NOTE


def set_write_offs(ledgers, rows, invoice_doctype):
    journals = {row.voucher_no for row in rows if row.voucher_type == "Journal Entry"}
    write_off_journals = set(
        frappe.get_all(
            "Journal Entry",
            filters={"name": ("in", journals), "voucher_type": "Write Off Entry"},
            pluck="name",
        )
        if journals
        else []
    )

    own_rows = {
        ledger.voucher_no
        for ledger in ledgers.values()
        if ledger.voucher_type == invoice_doctype
        and any(s.voucher_no == ledger.voucher_no for s in ledger.settlements)
    }
    bill_write_offs = dict(
        frappe.get_all(
            invoice_doctype,
            filters={"name": ("in", own_rows), "base_write_off_amount": (">", 0)},
            fields=["name", "base_write_off_amount"],
            as_list=True,
        )
        if own_rows
        else []
    )

    for ledger in ledgers.values():
        write_off = flt(bill_write_offs.get(ledger.voucher_no))

        for settlement in ledger.settlements:
            if settlement.voucher_type == "Journal Entry" and settlement.voucher_no in write_off_journals:
                settlement.kind = WRITE_OFF

            elif write_off and settlement.voucher_no == ledger.voucher_no and settlement.amount == write_off:
                settlement.kind = WRITE_OFF
                write_off = 0


def get_linked_returns(invoice_doctype, company, parties, vouchers) -> dict[str, str]:
    filters = {
        "company": company,
        "is_return": 1,
        "docstatus": 1,
        "update_outstanding_for_self": 0,
        "return_against": ("is", "set"),
    }

    if vouchers:
        bills = [voucher_no for voucher_type, voucher_no in vouchers if voucher_type == invoice_doctype]
        if not bills:
            return {}

        filters["return_against"] = ("in", bills)

    if parties:
        filters["supplier" if invoice_doctype == "Purchase Invoice" else "customer"] = ("in", parties)

    return dict(
        frappe.get_all(invoice_doctype, filters=filters, fields=["name", "return_against"], as_list=True)
    )


def get_ledger_query(company, party_type, parties):
    ple = frappe.qb.DocType("Payment Ledger Entry")
    query = (
        frappe.qb.from_(ple)
        .where(ple.delinked == 0)
        .where(ple.company == company)
        .where(ple.party_type == party_type)
        # post-dated rows are left out, as in ERPNext's report run for today
        .where(ple.posting_date <= getdate())
    )

    # same accounts as ERPNext's report: those of this type today, all when the company has none
    accounts = frappe.get_all(
        "Account", filters={"company": company, "account_type": ACCOUNT_TYPE[party_type]}, pluck="name"
    )
    if accounts:
        query = query.where(ple.account.isin(accounts))

    if parties:
        query = query.where(ple.party.isin(parties))

    return ple, query


def get_vouchers_from(ple, query, from_date, vouchers):
    posted = set(
        query.select(ple.voucher_type, ple.voucher_no)
        .distinct()
        .where(ple.voucher_type == ple.against_voucher_type)
        .where(ple.voucher_no == ple.against_voucher_no)
        .where(ple.posting_date >= getdate(from_date))
        .run()
    )

    if vouchers:
        posted &= {tuple(voucher) for voucher in vouchers}

    return list(posted)


def get_ledger_rows(ple, query, vouchers):
    query = query.select(
        ple.voucher_type,
        ple.voucher_no,
        ple.against_voucher_type,
        ple.against_voucher_no,
        ple.party,
        ple.posting_date,
        ple.amount,
    ).orderby(ple.posting_date, ple.creation)

    if not vouchers:
        return query.run(as_dict=True)

    # a (type, name) tuple filter skips the index on MariaDB: thousands of vouchers took seconds
    vouchers = {tuple(voucher) for voucher in vouchers}
    rows = (
        query.where(ple.against_voucher_type.isin({voucher_type for voucher_type, _ in vouchers}))
        .where(ple.against_voucher_no.isin({voucher_no for _, voucher_no in vouchers}))
        .run(as_dict=True)
    )
    return [row for row in rows if (row.against_voucher_type, row.against_voucher_no) in vouchers]
