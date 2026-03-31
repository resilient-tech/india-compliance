# Income Tax Act 1961 (pre FY 2026-27)
OLD_TDS_SECTIONS = [
    "192A",
    "192B",
    "193",
    "194",
    "194A",
    "194B",
    "194BA",
    "194BB",
    "194C",
    "194D",
    "194DA",
    "194EE",
    "194F",
    "194G",
    "194H",
    "194I",
    "194I(a)",
    "194I(b)",
    "194IA",
    "194IB",
    "194IC",
    "194JA",
    "194JB",
    "194K",
    "194LA",
    "194LBA",
    "194LBB",
    "194LBC",
    "194M",
    "194N",
    "194O",
    "194P",
    "194Q",
    "194R",
    "194S",
    "194T",
    "195",
    "206C(1H)",
]

# ITA 2025 section codes per IT Rules 2026 (effective from FY 2026-27)
NEW_TDS_SECTIONS = [
    # Salary - Section 392
    "1001",  # Salary - Govt employees (non-Union)
    "1002",  # Salary - non-Govt employees
    "1003",  # Salary - Indian Govt employees
    # Resident payments - Section 393(1)
    "1004",  # EPF accumulated balance - 392(7)
    "1005",  # Commission/brokerage - insurance - Sl.1(i)
    "1006",  # Commission/brokerage - others - Sl.1(ii)
    "1008",  # Rent on machinery - Sl.2(ii).D(a)
    "1009",  # Rent on land/building - Sl.2(ii).D(b)
    "1011",  # JDA consideration - Sl.3(ii)
    "1012",  # Compensation on acquisition of immovable property - Sl.3(iii)
    "1013",  # MF/UTI units income - Sl.4(i)
    "1014",  # Business trust interest - Sl.4(ii)
    "1015",  # Business trust dividend - Sl.4(ii)
    "1016",  # Business trust renting (REIT) - Sl.4(ii)
    "1017",  # Investment fund units - Sl.4(iii)
    "1018",  # Securitisation trust income - Sl.4(iv)
    "1019",  # Interest on securities - Sl.5(i)
    "1020",  # Interest - senior citizen - Sl.5(ii).D(a)
    "1021",  # Interest - bank/PO - Sl.5(ii).D(b)
    "1022",  # Interest - others - Sl.5(iii)
    "1023",  # Contractor - Ind/HUF - Sl.6(i).D(a)
    "1024",  # Contractor - Others - Sl.6(i).D(b)
    "1026",  # Technical fees - Sl.6(iii).D(a)
    "1027",  # Professional fees - Sl.6(iii).D(b)
    "1028",  # Director remuneration - Sl.6(iii).D(b)
    "1029",  # Dividends - Sl.7
    "1030",  # Life insurance payout - Sl.8(i)
    "1031",  # Purchase of goods - Sl.8(ii)
    "1032",  # Specified senior citizen - Sl.8(iii)
    "1033",  # Business perquisites (money) - Sl.8(iv)
    "1034",  # Business perquisites (kind) - Sl.8(iv) Note 6
    "1035",  # E-commerce operator - Sl.8(v)
    "1037",  # VDA transfer (non-Ind/HUF) - Sl.8(vi)
    "1038",  # VDA transfer (kind) - Sl.8(vi) Note 6
    # Non-resident payments - Section 393(2)
    "1039",  # NR sportsperson/entertainer - Sl.1
    "1040",  # Interest on foreign currency loan - Sl.2
    "1041",  # Interest on rupee denominated bond - Sl.3
    "1042",  # Interest on IFSC bond (pre-Apr 2020) - Sl.4.E(a)
    "1043",  # Interest on IFSC bond (post-Jul 2023) - Sl.4.E(b)
    "1044",  # Infrastructure debt fund interest - Sl.5
    "1045",  # Business trust distribution (type a) - Sl.6.E(a)
    "1046",  # Business trust distribution (type b) - Sl.6.E(b)
    "1047",  # Business trust distribution (other) - Sl.7
    "1048",  # Investment fund units (NR) - Sl.8
    "1049",  # Securitisation trust (NR) - Sl.9
    "1050",  # MF units income (NR) - Sl.10
    "1051",  # Offshore fund units - Sl.11
    "1052",  # Offshore fund LTCG - Sl.12
    "1053",  # GDR interest/dividend - Sl.13
    "1054",  # GDR LTCG - Sl.14
    "1055",  # FII securities - Sl.15
    "1056",  # Specified fund securities - Sl.16
    "1057",  # Other NR payments - Sl.17
    # Any person payments - Section 393(3)
    "1058",  # Lottery/gambling winnings - Sl.1
    "1059",  # Lottery winnings (kind) - Sl.1 Note 2
    "1060",  # Online game winnings - Sl.2
    "1061",  # Online game winnings (kind) - Sl.2 Note 2
    "1062",  # Horse race winnings - Sl.3
    "1063",  # Lottery commission - Sl.4
    "1064",  # Cash withdrawal - coop - Sl.5.D(a)
    "1065",  # Cash withdrawal - others - Sl.5.D(b)
    "1066",  # NSS payments - Sl.6
    "1067",  # Partner remuneration - Sl.7
    # Form 141 sections (challan-cum-statement, no numeric return code)
    "393(1) Sl.2(i)",  # Rent by Individual/HUF (was 194IB)
    "393(1) Sl.3(i)",  # Immovable property transfer (was 194IA)
    "393(1) Sl.6(ii)",  # Contractor/professional by Ind/HUF >50L (was 194M)
]

TDS_ENTITY_TYPE = ["Individual", "Company", "Company Assessee", "No PAN / Invalid PAN"]
