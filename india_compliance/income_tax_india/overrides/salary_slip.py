import frappe
from frappe import _
from frappe.utils import date_diff, flt, nowdate
from erpnext.hr.utils import get_salary_assignment
from erpnext.payroll.doctype.salary_structure.salary_structure import make_salary_slip


def calculate_annual_eligible_hra_exemption(doc):
    basic_component, hra_component = frappe.db.get_value(
        "Company", doc.company, ["basic_component", "hra_component"]
    )
    if not (basic_component and hra_component):
        frappe.throw(_("Please mention Basic and HRA component in Company"))
    annual_exemption, monthly_exemption, hra_amount = 0, 0, 0
    if hra_component and basic_component:
        assignment = get_salary_assignment(doc.employee, nowdate())
        if assignment:
            hra_component_exists = frappe.db.exists(
                "Salary Detail",
                {
                    "parent": assignment.salary_structure,
                    "salary_component": hra_component,
                    "parentfield": "earnings",
                    "parenttype": "Salary Structure",
                },
            )

            if hra_component_exists:
                basic_amount, hra_amount = get_component_amt_from_salary_slip(
                    doc.employee,
                    assignment.salary_structure,
                    basic_component,
                    hra_component,
                )
                if hra_amount:
                    if doc.monthly_house_rent:
                        annual_exemption = calculate_hra_exemption(
                            assignment.salary_structure,
                            basic_amount,
                            hra_amount,
                            doc.monthly_house_rent,
                            doc.rented_in_metro_city,
                        )
                        if annual_exemption > 0:
                            monthly_exemption = annual_exemption / 12
                        else:
                            annual_exemption = 0

        elif doc.docstatus == 1:
            frappe.throw(
                _(
                    "Salary Structure must be submitted before submission of Tax Ememption Declaration"
                )
            )

    return frappe._dict(
        {
            "hra_amount": hra_amount,
            "annual_exemption": annual_exemption,
            "monthly_exemption": monthly_exemption,
        }
    )


def get_component_amt_from_salary_slip(
    employee, salary_structure, basic_component, hra_component
):
    salary_slip = make_salary_slip(
        salary_structure, employee=employee, for_preview=1, ignore_permissions=True
    )
    basic_amt, hra_amt = 0, 0
    for earning in salary_slip.earnings:
        if earning.salary_component == basic_component:
            basic_amt = earning.amount
        elif earning.salary_component == hra_component:
            hra_amt = earning.amount
        if basic_amt and hra_amt:
            return basic_amt, hra_amt
    return basic_amt, hra_amt


def calculate_hra_exemption(
    salary_structure, basic, monthly_hra, monthly_house_rent, rented_in_metro_city
):
    # TODO make this configurable
    exemptions = []
    frequency = frappe.get_value(
        "Salary Structure", salary_structure, "payroll_frequency"
    )
    # case 1: The actual amount allotted by the employer as the HRA.
    exemptions.append(get_annual_component_pay(frequency, monthly_hra))

    actual_annual_rent = monthly_house_rent * 12
    annual_basic = get_annual_component_pay(frequency, basic)

    # case 2: Actual rent paid less 10% of the basic salary.
    exemptions.append(flt(actual_annual_rent) - flt(annual_basic * 0.1))
    # case 3: 50% of the basic salary, if the employee is staying in a metro city (40% for a non-metro city).
    exemptions.append(
        annual_basic * 0.5 if rented_in_metro_city else annual_basic * 0.4
    )
    # return minimum of 3 cases
    return min(exemptions)


def get_annual_component_pay(frequency, amount):
    if frequency == "Daily":
        return amount * 365
    elif frequency == "Weekly":
        return amount * 52
    elif frequency == "Fortnightly":
        return amount * 26
    elif frequency == "Monthly":
        return amount * 12
    elif frequency == "Bimonthly":
        return amount * 6


def calculate_hra_exemption_for_period(doc):
    monthly_rent, eligible_hra = 0, 0
    if doc.house_rent_payment_amount:
        validate_house_rent_dates(doc)
        # TODO receive rented months or validate dates are start and end of months?
        # Calc monthly rent, round to nearest .5
        factor = flt(date_diff(doc.rented_to_date, doc.rented_from_date) + 1) / 30
        factor = round(factor * 2) / 2
        monthly_rent = doc.house_rent_payment_amount / factor
        # update field used by calculate_annual_eligible_hra_exemption
        doc.monthly_house_rent = monthly_rent
        exemptions = calculate_annual_eligible_hra_exemption(doc)

        if exemptions["monthly_exemption"]:
            # calc total exemption amount
            eligible_hra = exemptions["monthly_exemption"] * factor
        exemptions["monthly_house_rent"] = monthly_rent
        exemptions["total_eligible_hra_exemption"] = eligible_hra
        return exemptions


def validate_house_rent_dates(doc):
    if not doc.rented_to_date or not doc.rented_from_date:
        frappe.throw(_("House rented dates required for exemption calculation"))

    if date_diff(doc.rented_to_date, doc.rented_from_date) < 14:
        frappe.throw(_("House rented dates should be atleast 15 days apart"))

    proofs = frappe.db.sql(
        """
		select name
		from `tabEmployee Tax Exemption Proof Submission`
		where
			docstatus=1 and employee=%(employee)s and payroll_period=%(payroll_period)s
			and (rented_from_date between %(from_date)s and %(to_date)s or rented_to_date between %(from_date)s and %(to_date)s)
	""",
        {
            "employee": doc.employee,
            "payroll_period": doc.payroll_period,
            "from_date": doc.rented_from_date,
            "to_date": doc.rented_to_date,
        },
    )

    if proofs:
        frappe.throw(
            _("House rent paid days overlapping with {0}").format(proofs[0][0])
        )
