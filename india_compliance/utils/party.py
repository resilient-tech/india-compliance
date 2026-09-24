# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from india_compliance.gst_india.overrides.transaction import get_gst_details
from india_compliance.income_tax_india.overrides.party import get_msme_details


def update_party_details(party_details, doctype, company):
    party_details.update(get_gst_details(party_details, doctype, company, update_place_of_supply=True))
    party_details.update(get_msme_details(party_details))
