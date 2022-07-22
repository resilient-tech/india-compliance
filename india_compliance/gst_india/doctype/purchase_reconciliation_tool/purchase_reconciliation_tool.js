// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

// TODO: change the namespace
// TODO: replace the demo data
frappe.provide("reco_tool");

const tooltip_info = {
    purchase_period: "Returns purchases during this period where no match is found.",
    inward_supply_period:
        "Returns all documents from GSTR 2A/2B during this return period.",
};

const api_enabled = ic.is_api_enabled();

const ReturnType = {
    GSTR2A: "GSTR2a",
    GSTR2B: "GSTR2b",
};

frappe.ui.form.on("Purchase Reconciliation Tool", {
    async setup(frm) {
        await frappe.require("purchase_reco_tool.bundle.js");
        frm.purchase_reconciliation_tool = new PurchaseReconciliationTool(frm);
    },

    async company(frm) {
        if (frm.doc.company) {
            const options = await set_gstin_options(frm);
            frm.set_value("company_gstin", options[0]);
        }
    },

    refresh(frm) {
        ic.setup_tooltip(frm, tooltip_info);

        fetch_date_range(frm, "purchase");
        fetch_date_range(frm, "inward_supply");

        api_enabled
            ? frm.add_custom_button("Download", () => show_gstr_dialog(frm))
            : frm.add_custom_button("Upload", () => show_gstr_dialog(frm, false));

        // if (frm.doc.company) set_gstin_options(frm);
    },

    purchase_period(frm) {
        fetch_date_range(frm, "purchase");
    },

    inward_supply_period(frm) {
        fetch_date_range(frm, "inward_supply");
    },
});

class PurchaseReconciliationTool {
    constructor(frm) {
        this.frm = frm;
        this.render_tab_group();
        this.render_data_tables();
    }

    render_tab_group() {
        this.tab_group = new frappe.ui.FieldGroup({
            fields: [
                //hack: for the FieldGroup(Layout) to avoid rendering default tab
                {
                    label: "Summary",
                    fieldtype: "Tab Break",
                    fieldname: "summary",
                    active: 1,
                },
                {
                    fieldtype: "HTML",
                    fieldname: "summary_data",
                },
                {
                    label: "Supplier Level",
                    fieldtype: "Tab Break",
                    fieldname: "supplier_level",
                },
                {
                    fieldtype: "HTML",
                    fieldname: "supplier_level_data",
                },
                {
                    label: "Invoice Level",
                    fieldtype: "Tab Break",
                    fieldname: "invoice_level",
                },
                {
                    fieldtype: "HTML",
                    fieldname: "invoice_level_data",
                },
            ],
            body: this.frm.get_field("summary_data").$wrapper,
            frm: this.frm,
        });

        this.tab_group.make();

        // make tabs_dict for easy access
        this.tabs = Object.fromEntries(
            this.tab_group.tabs.map(tab => [tab.df.fieldname, tab])
        );
    }

    render_data_tables() {
        this.tabs.summary.data_table_manager = new ic.DataTableManager({
            $wrapper: this.tab_group.get_field("summary_data").$wrapper,
            columns: [
                {
                    label: "Match Type",
                    fieldname: "isup_match_status",
                    width: 200,
                },
                {
                    label: "No. of Docs (2A/2B | PR)",
                    fieldname: "no_of_docs",
                    width: 180,
                },
                {
                    label: "Tax Diff (2A/2B - PR)",
                    fieldname: "tax_diff",
                    width: 180,
                },
            ],
            data: this.get_summary_data(),
        });

        this.tabs.supplier_level.data_table_manager = new ic.DataTableManager({
            $wrapper: this.tab_group.get_field("supplier_level_data").$wrapper,
            columns: [
                {
                    label: "Supplier",
                    fieldname: "supplier",
                    fieldtype: "Link",
                    width: 200,
                    format: (value, row, column, data) => {
                        if (data && column.field === "supplier") {
                            column.docfield.link_onclick = `reco_tool.apply_filters(${JSON.stringify(
                                {
                                    tab: "invoice_level",
                                    filters: {
                                        supplier_name: data.supplier_gstin,
                                    },
                                }
                            )})`;
                        }

                        const content = `
                            ${data.supplier_name}
                            <br />
                            <span style="font-size: 0.9em">
                                ${data.supplier_gstin || ""}
                            </span>
                        `;

                        return frappe.form.get_formatter(column.docfield.fieldtype)(
                            content,
                            column.docfield,
                            { always_show_decimals: true },
                            data
                        );
                    },
                    dropdown: false,
                },
                {
                    label: "No. of Docs (2A/2B | PR)",
                    fieldname: "no_of_docs",
                    width: 180,
                },
                {
                    label: "Tax Diff (2A/2B - PR)",
                    fieldname: "tax_diff",
                    width: 180,
                },
                {
                    fieldname: "document_value_diff",
                    label: "Document Diff (2A/2B - PR)",
                    width: 200,
                },
                {
                    label: "Download",
                    fieldname: "download",
                    fieldtype: "html",
                    width: 100,
                },
                {
                    label: "Email",
                    fieldname: "email",
                    fieldtype: "html",
                    width: 100,
                },
            ],
            options: {
                cellHeight: 55,
            },
            data: this.get_supplier_level_data(),
        });
        this.tabs.invoice_level.data_table_manager = new ic.DataTableManager({
            $wrapper: this.tab_group.get_field("invoice_level_data").$wrapper,
            columns: [
                {
                    fieldname: "view",
                    fieldtype: "html",
                    width: 60,
                    align: "center",
                    format: (...args) => get_formatted(...args, "eye", reco_tool.show_detailed_dialog),
                },
                {
                    label: "Supplier",
                    fieldname: "supplier_name",
                    width: 200,
                    format: (value, row, column, data) => {
                        const content = `
                            ${data.supplier_name}
                            <br />
                            <span style="font-size: 0.9em">
                                ${data.supplier_gstin || ""}
                            </span>
                        `;

                        return frappe.form.get_formatter(column.docfield.fieldtype)(
                            content,
                            column.docfield,
                            { always_show_decimals: true },
                            data
                        );
                    },
                    dropdown: false,
                },
                {
                    label: "Bill No.",
                    fieldname: "bill_no",
                    width: 120,
                },
                {
                    label: "Date",
                    fieldname: "bill_date",
                    width: 120,
                },
                {
                    label: "Match Status",
                    fieldname: "isup_match_status",
                    width: 120,
                },
                {
                    label: "Purchase Invoice",
                    fieldname: "name",
                    // fieldtype: "Link",
                    // doctype: "Purchase Invoice",
                    align: "center",
                    width: 150,
                    format: (value, row, column, data) => {
                        const content = `<button class="btn">
                                <i class="fa fa-link"></i>
                            </button>`;

                        return frappe.form.get_formatter(column.docfield.fieldtype)(
                            content,
                            column.docfield,
                            { always_show_decimals: true },
                            data
                        );
                    },
                },
                {
                    label: "Inward Supply",
                    fieldname: "isup_name",
                    fieldtype: "Link",
                    doctype: "Inward Supply",
                    width: 150,
                },
                {
                    label: "Tax Diff (2A/2B - PR)",
                    fieldname: "tax_diff",
                    width: 180,
                },
                {
                    fieldname: "document_value_diff",
                    label: "Document Diff (2A/2B - PR)",
                    width: 180,
                },
                {
                    fieldname: "differences",
                    label: "Differences",
                },
                {
                    label: "Action",
                    fieldname: "isup_action",
                },
            ],
            options: {
                cellHeight: 55,
            },
            data: this.get_invoice_level_data(),
        });
    }

    get_summary_data() {
        return [
            {
                supplier_name: "K Vijay Ispat Udyog",
                supplier_gstin: "27AALFK9932E1Z0",
                match_status: "Success",
                no_of_inward_supp: 4,
                no_of_doc_purchase: 150,
            },
        ];
    }

    get_supplier_level_data() {
        return [
            {
                supplier_name: "K Vijay Ispat Udyog",
                supplier_gstin: "27AALFK9932E1Z0",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "Padmavati Steel and Engg Co",
                supplier_gstin: "27AADPD5694C1ZV",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Sainest Tubes Pvt Ltd",
                supplier_gstin: "24AAECS5018D1ZS",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Shreya Pipe and Fittings",
                supplier_gstin: "24ADVFS4123J1ZQ",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Xiaomi Technology India Private Limited",
                supplier_gstin: "27AAACX1645B1ZO",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Kulubi Steel",
                supplier_gstin: "24AABFK8892P1ZK",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Infiniti Retail Limited CROMA",
                supplier_gstin: "24AACCV1726H1ZK",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "TCR Advanced Engineering Pvt Ltd",
                supplier_gstin: "24AABCT3473E1ZL",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Sai Steel and Engineering Co",
                supplier_gstin: "27ADLFS6197C1ZN",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Kushal Copper Corporation",
                supplier_gstin: "27AAFFK2716A1ZU",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "SKM Impex - A Div of SKM Steels Ltd",
                supplier_gstin: "27AADCS7801F1ZG",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "Moreshwar Engineers and Manufacturers",
                supplier_gstin: "24BNLPS8562C1ZP",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Modsonic Instruments Mfg Co Pvt Ltd",
                supplier_gstin: "24AACCM4706A1Z5",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Hytech Pipe Fitting Pvt Ltd",
                supplier_gstin: "24AAFCH1103D1ZG",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Sun Metal and Alloys",
                supplier_gstin: "27ADAFS4139H1Z2",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Shiv Shakti Enterprises",
                supplier_gstin: "24ACGPB2963D1Z4",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Reliable Stainless",
                supplier_gstin: "27AAZFR4704P1Z8",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Zip Technologies (Amazon)",
                supplier_gstin: "07AAAFZ1851A1ZK",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Armko Pipe Fittings (I) Pvt Ltd",
                supplier_gstin: "27AATCA0302R1ZB",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Arbuda Sales Agency",
                supplier_gstin: "24AACFA7093D1ZR",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Krupali Roadways",
                supplier_gstin: "24CTUPP4692N1ZK",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "M K Ispats",
                supplier_gstin: "27BYMPK9036R1ZE",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Associated Road Carriers Ltd",
                supplier_gstin: "36AACCA4861C1Z0",
                no_of_doc_purchase: 5,
            },
            {
                supplier_name: "Quick Sales and Services",
                supplier_gstin: "24CGTPM5713R1ZJ",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Rajdhani Roadlines",
                supplier_gstin: "24AGOPP6299C3ZX",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Sanghvi Industrial Corporation",
                supplier_gstin: "27AAAPB8774G1ZP",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Genius Trading Co",
                supplier_gstin: "27EHLPK1784F1Z1",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "SS Tube",
                supplier_gstin: "27AZJPS4427R1ZF",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Unicorn Steel India",
                supplier_gstin: "27AICPD6478K1ZY",
                no_of_doc_purchase: 7,
            },
            {
                supplier_name: "Krishna Traders",
                supplier_gstin: "24COOPS7720F1ZN",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Array Energy Solution",
                supplier_gstin: "24BNAPT4657C1Z3",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "VRP TELEMATICS PRIVATE LIMITED",
                supplier_gstin: "24AACCV5763A1ZL",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Dynamic Forge and Fittings I Pvt Ltd",
                supplier_gstin: "24AADCD2719H1ZY",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Gayatri Graphics",
                supplier_gstin: "24ATCPS3705K1ZN",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Amar Equipments Pvt Ltd",
                supplier_gstin: "27AADCA0201H1ZE",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Nageshwar Steels",
                supplier_gstin: "24AAGFN7225G1ZE",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "SKM Impex - A Div of SKM Steels Ltd",
                supplier_gstin: "24AADCS7801F1ZM",
                no_of_doc_purchase: 16,
            },
            {
                supplier_name: "Phone World",
                supplier_gstin: "24FBAPS4876L1Z1",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Sanghvi Forging and Engineering Ltd",
                supplier_gstin: "24AADCS2903E1ZV",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Shree Laxmi Global Logistics Private Limited",
                supplier_gstin: "27AAACU5182C1ZH",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Shree Laxmi Global Logistics Private Limited",
                supplier_gstin: "27AAWCS9887J1ZY",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Shree Laxmi Global Logistics Private Limited",
                supplier_gstin: "27AACCO6217A1ZV",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Umakant Booksellers and Stationers",
                supplier_gstin: "24AAXPT5104F1ZI",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Xcel Profile",
                supplier_gstin: "24AYCPP9731B2ZK",
                no_of_doc_purchase: 5,
            },
            {
                supplier_name: "Shiv Aum Steels Pvt Ltd",
                supplier_gstin: "27AAFCS9987G1ZL",
                no_of_doc_purchase: 4,
            },
            {
                supplier_name: "Faiz Engineering and Trading Co.",
                supplier_gstin: "24BPXPP5388B1ZC",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Honest Surgical Co",
                supplier_gstin: "24AZDPM1803F1ZW",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "M S Enterprise",
                supplier_gstin: "24ALCPP3148H1Z8",
                no_of_doc_purchase: 9,
            },
            {
                supplier_name: "Shree Ganesh Heat Treatment",
                supplier_gstin: "24COFPP3749L1ZH",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Sanjay Bonny Forge Pvt Ltd",
                supplier_gstin: "27AAKCS3246H1Z6",
                no_of_doc_purchase: 4,
            },
            {
                supplier_name: "Metallica Metals India",
                supplier_gstin: "27AAGFM6458A1ZC",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "B R Logistics",
                supplier_gstin: "27ABZPY0827F1ZZ",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Alisha Plastics",
                supplier_gstin: "24CCWPP2634K1Z1",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "Shankarbhai Desai & Sons",
                supplier_gstin: "24AENPD0387C1ZV",
                no_of_doc_purchase: 8,
            },
            {
                supplier_name: "TCI Freight",
                supplier_gstin: "24AAACT7966R1ZH",
                no_of_doc_purchase: 4,
            },
            {
                supplier_name: "P K Enterprise",
                supplier_gstin: "24CBFPR3680H1ZH",
                no_of_doc_purchase: 42,
            },
            {
                supplier_name: "Keval Electric",
                supplier_gstin: "24ARXPP8336L1ZU",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Shree Laxmi Global Logistics Private Limited",
                supplier_gstin: "27AABCO1164H1ZM",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Shree Laxmi Global Logistics Private Limited",
                supplier_gstin: "27AABCE2879H1ZG",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Pari Computers Pvt Ltd",
                supplier_gstin: "27AACCP5489K1ZT",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Patson Pipes and Tubes",
                supplier_gstin: "24AAFFP6265R1ZK",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Santosh Steels",
                supplier_gstin: "27AAAFS3466L1ZV",
                no_of_doc_purchase: 4,
            },
            {
                supplier_name: "Surbhi Computers",
                supplier_gstin: "23ADSPJ1561E1ZQ",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Appario Retail Private Ltd",
                supplier_gstin: "24AALCA0171E1Z5",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Forge Cast Alloy Pvt Ltd",
                supplier_gstin: "27AABCF2875J1ZE",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "K B Engineers",
                supplier_gstin: "24AGRPC4267G1ZD",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Tube Traders",
                supplier_gstin: "24AACFT5218P1ZW",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Pattech Fitwell Tube Components",
                supplier_gstin: "24AAOFP2063N1ZV",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Capricorn Identity Services Pvt Ltd",
                supplier_gstin: "07AAVCS8838C1ZR",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Patni and Sons",
                supplier_gstin: "24AOXPP8810N2Z0",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "Sanghvi Office Equipments Pvt. Ltd",
                supplier_gstin: "24AABCS5513Q1Z4",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "Devki Nandan J Gupta Metals LLP",
                supplier_gstin: "27AAKFD5904A1ZS",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "Hilti India Pvt Ltd",
                supplier_gstin: "27AAACH3583Q1Z0",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "V Trans India Ltd",
                supplier_gstin: "27AAACV1559Q2ZP",
                no_of_doc_purchase: 6,
            },
            {
                supplier_name: "Rai Road Lines",
                supplier_gstin: "24ACNPR8089F1Z0",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Neminath Traders",
                supplier_gstin: "24ABVPJ7716N1ZX",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Pratap Sales Corporation",
                supplier_gstin: "24ADVPC8766H1Z1",
                no_of_doc_purchase: 5,
            },
            {
                supplier_name: "Asbestos Engineering Co",
                supplier_gstin: "24AYWPS8436Q1Z3",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Arihant Fasteners",
                supplier_gstin: "24AACFA8028Q1Z7",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "Sai NDT Services",
                supplier_gstin: "24ABPFS1716F2Z7",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Bhaven Enterprise",
                supplier_gstin: "24AAQPP6652F1ZE",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "Nidhi Transport Service",
                supplier_gstin: "24ABVPB2674D2ZQ",
                no_of_doc_purchase: 55,
            },
            {
                supplier_name: "Viraansh Automobiles LLP",
                supplier_gstin: "24AAQFV6875Q1ZX",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Shree Khodiyar Transport",
                supplier_gstin: "24AOYPP5222R1Z0",
                no_of_doc_purchase: 24,
            },
            {
                supplier_name: "Go Digit General Insurance Ltd",
                supplier_gstin: "29AACCO4128Q1ZW",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Karan Enterprise",
                supplier_gstin: "24AJEPS2985B1Z8",
                no_of_doc_purchase: 3,
            },
            {
                supplier_name: "New Light Trading Co",
                supplier_gstin: "27AAPPK5796C1Z9",
                no_of_doc_purchase: 7,
            },
            {
                supplier_name: "Artee Engineers",
                supplier_gstin: "27AAUPT8710G1Z3",
                no_of_doc_purchase: 24,
            },
            {
                supplier_name: "Shree Rajesh Pipe Fittings & Flanges",
                supplier_gstin: "27BJFPR1685D1Z2",
                no_of_doc_purchase: 22,
            },
            {
                supplier_name: "VRT Logistic",
                supplier_gstin: "27CBYPK4332A1ZM",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Triveni Boiler Pvt Ltd",
                supplier_gstin: "24AAECT6387N1ZO",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "The Tool Shop",
                supplier_gstin: "33AWRPA6154E1ZP",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Sheetal Wood Packaging",
                supplier_gstin: "24ATGPP3906R1Z5",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Press",
                supplier_gstin: "24AGZPP0419P1ZN",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Mohandas & Sons",
                supplier_gstin: "27AAAFM1588M1ZW",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "M Desai & Co",
                supplier_gstin: "24AAHFM0964G1ZE",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "Kajal Plastics",
                supplier_gstin: "24AYGPS3586F1Z5",
                no_of_doc_purchase: 4,
            },
            {
                supplier_name: "BT Water Treatment Pvt Ltd",
                supplier_gstin: "24AADCB3208R1ZL",
                no_of_doc_purchase: 2,
            },
            {
                supplier_name: "Bluechip Computer System",
                supplier_gstin: "24AANFB3091M1Z6",
                no_of_doc_purchase: 1,
            },
            {
                supplier_name: "State Bank of India",
                supplier_gstin: "27AAACS8577K2ZO",
                no_of_doc_purchase: 13,
            },
        ];
    }

    get_invoice_level_data() {
        return [
            {
                supplier_name: "K Vijay Ispat Udyog",
                supplier_gstin: "27AALFK9932E1Z0",
                bill_no: "PINV-20-00517",
                bill_date: "2020-11-21",
            },
            {
                supplier_name: "Padmavati Steel and Engg Co",
                supplier_gstin: "27AADPD5694C1ZV",
                bill_no: "PINV-20-00519",
                bill_date: "2020-11-20",
            },
            {
                supplier_name: "Shikhar Steel Corporation",
                supplier_gstin: "27AVGPB2421B1ZE",
                bill_no: "PINV-20-00441",
                bill_date: "2020-09-29",
            },
            {
                supplier_name: "Shikhar Steel Corporation",
                supplier_gstin: "27AVGPB2421B1ZE",
                bill_no: "PINV-20-00433",
                bill_date: "2020-09-25",
            },
            {
                supplier_name: "Shikhar Steel Corporation",
                supplier_gstin: "27AVGPB2421B1ZE",
                bill_no: "PINV-20-00389",
                bill_date: "2020-09-14",
            },
            {
                supplier_name: "Shikhar Steel Corporation",
                supplier_gstin: "27AVGPB2421B1ZE",
                bill_no: "PINV-20-00395",
                bill_date: "2020-09-14",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00479",
                bill_date: "2020-10-10",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00465",
                bill_date: "2020-10-09",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00478",
                bill_date: "2020-10-07",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00451",
                bill_date: "2020-10-07",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00450",
                bill_date: "2020-10-05",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00449",
                bill_date: "2020-10-02",
            },
            {
                supplier_name: "Sanjay Bonny Forge Pvt Ltd",
                supplier_gstin: "27AAKCS3246H1Z6",
                bill_no: "PINV-20-00442",
                bill_date: "2020-09-24",
            },
            {
                supplier_name: "Shah Metal and Tubes",
                supplier_gstin: "27ABSFS1482R1Z3",
                bill_no: "PINV-20-00510",
                bill_date: "2020-11-06",
            },
            {
                supplier_name: "Divya Metal India",
                supplier_gstin: "27APUPB5857M1Z3",
                bill_no: "PINV-20-00379",
                bill_date: "2020-09-11",
            },
            {
                supplier_name: "Divya Metal India",
                supplier_gstin: "27APUPB5857M1Z3",
                bill_no: "PINV-20-00313",
                bill_date: "2020-08-21",
            },
            {
                supplier_name: "Sainest Tubes Pvt Ltd",
                supplier_gstin: "24AAECS5018D1ZS",
                bill_no: "PINV-20-00514",
                bill_date: "2020-11-10",
            },
            {
                supplier_name: "Shankarbhai Desai & Sons",
                supplier_gstin: "24AENPD0387C1ZV",
                bill_no: "PINV-20-00509",
                bill_date: "2020-11-12",
            },
            {
                supplier_name: "Jayesh Engineering",
                supplier_gstin: "24ADNPT6484F1Z1",
                bill_no: "PINV-20-00498",
                bill_date: "2020-11-01",
            },
            {
                supplier_name: "Nidhi Transport Service",
                supplier_gstin: "24ABVPB2674D2ZQ",
                bill_no: "PINV-20-00508",
                bill_date: "2020-11-09",
            },
            {
                supplier_name: "Shreya Pipe and Fittings",
                supplier_gstin: "24ADVFS4123J1ZQ",
                bill_no: "PINV-20-00507",
                bill_date: "2020-11-09",
            },
            {
                supplier_name: "Tapan Enterprise",
                supplier_gstin: "24AEPPS0534Q1ZW",
                bill_no: "PINV-20-00504",
                bill_date: "2020-10-17",
            },
            {
                supplier_name: "Natwarlal Hiralal Shah",
                supplier_gstin: "24AFRPS0569Q1ZH",
                bill_no: "PINV-20-00503",
                bill_date: "2020-11-07",
            },
            {
                supplier_name: "S B Associates",
                supplier_gstin: "24ADCPG1409L1ZX",
                bill_no: "PINV-20-00500",
                bill_date: "2020-11-02",
            },
            {
                supplier_name: "Jayhind Metal and Tubes",
                supplier_gstin: "27AAIPS6329N1ZY",
                bill_no: "PINV-20-00406",
                bill_date: "2020-09-17",
            },
            {
                supplier_name: "K B Forge Industries",
                supplier_gstin: "24ACRPC1838M1ZD",
                bill_no: "PINV-20-00488",
                bill_date: "2020-10-29",
            },
            {
                supplier_name: "K B Forge Industries",
                supplier_gstin: "24ACRPC1838M1ZD",
                bill_no: "PINV-20-00435",
                bill_date: "2020-09-24",
            },
            {
                supplier_name: "Metro Forge India",
                supplier_gstin: "27AAIPB2425N1ZQ",
                bill_no: "PINV-20-00360",
                bill_date: "2020-09-07",
            },
            {
                supplier_name: "P K Enterprise",
                supplier_gstin: "24CBFPR3680H1ZH",
                bill_no: "PINV-20-00495",
                bill_date: "2020-10-29",
            },
            {
                supplier_name: "Krit Corporation",
                supplier_gstin: "24CASPS4511C1ZR",
                bill_no: "PINV-20-00494",
                bill_date: "2020-11-05",
            },
            {
                supplier_name: "Raj Enterprise",
                supplier_gstin: "24BFHPK5295N1ZV",
                bill_no: "PINV-20-00491",
                bill_date: "2020-10-31",
            },
            {
                supplier_name: "SKM Impex - A Div of SKM Steels Ltd",
                supplier_gstin: "24AADCS7801F1ZM",
                bill_no: "PINV-20-00484",
                bill_date: "2020-10-29",
            },
            {
                supplier_name: "Topaz Piping Industries",
                supplier_gstin: "24AAFFT1047H1ZF",
                bill_no: "PINV-20-00485",
                bill_date: "2020-10-30",
            },
            {
                supplier_name: "S M Heat Treatment Works",
                supplier_gstin: "24BWGPP6376K1ZY",
                bill_no: "PINV-20-00486",
                bill_date: "2020-10-28",
            },
            {
                supplier_name: "Shree Bajrang Transport",
                supplier_gstin: "24AFSPB1574M1Z6",
                bill_no: "PINV-20-00489",
                bill_date: "2020-10-30",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00487",
                bill_date: "2020-10-29",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00482",
                bill_date: "2020-10-24",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00476",
                bill_date: "2020-10-16",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00475",
                bill_date: "2020-10-15",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00474",
                bill_date: "2020-10-15",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00461",
                bill_date: "2020-10-09",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00460",
                bill_date: "2020-10-09",
            },
            {
                supplier_name: "Mitesh Metal and Alloys",
                supplier_gstin: "27AIXPB6461D1Z3",
                bill_no: "PINV-20-00351",
                bill_date: "2020-09-06",
            },
            {
                supplier_name: "Mitesh Metal and Alloys",
                supplier_gstin: "27AIXPB6461D1Z3",
                bill_no: "PINV-19-00595",
                bill_date: "2019-08-22",
            },
            {
                supplier_name: "Shah Metal and Tubes",
                supplier_gstin: "27ABSFS1482R1Z3",
                bill_no: "PINV-20-00483",
                bill_date: "2020-10-28",
            },
            {
                supplier_name: "Xiaomi Technology India Private Limited",
                supplier_gstin: "27AAACX1645B1ZO",
                bill_no: "PINV-20-00301",
                bill_date: "2020-08-19",
            },
            {
                supplier_name: "Hanco Pipe and Fitting",
                supplier_gstin: "27CVQPK3283C1ZD",
                bill_no: "PINV-20-00293",
                bill_date: "2020-08-19",
            },
            {
                supplier_name: "Shiv Shakti Pipe Fittings",
                supplier_gstin: "27BKFPP9735B1ZZ",
                bill_no: "PINV-20-00325",
                bill_date: "2020-08-28",
            },
            {
                supplier_name: "Hytech Pipe Fitting Pvt Ltd",
                supplier_gstin: "24AAFCH1103D1ZG",
                bill_no: "PINV-20-00477",
                bill_date: "2020-10-19",
            },
            {
                supplier_name: "Shah Metal and Tubes",
                supplier_gstin: "27ABSFS1482R1Z3",
                bill_no: "PINV-20-00481",
                bill_date: "2020-10-22",
            },
            {
                supplier_name: "Shah Metal and Tubes",
                supplier_gstin: "27ABSFS1482R1Z3",
                bill_no: "PINV-20-00471",
                bill_date: "2020-10-14",
            },
            {
                supplier_name: "Express Roadlines",
                supplier_gstin: "24AGCPP3351K1ZF",
                bill_no: "PINV-20-00480",
                bill_date: "2020-10-07",
            },
            {
                supplier_name: "R K Distributors",
                supplier_gstin: "24ABZPA5599C1ZC",
                bill_no: "PINV-20-00434",
                bill_date: "2020-09-28",
            },
            {
                supplier_name: "Shikhar Steel Corporation",
                supplier_gstin: "27AVGPB2421B1ZE",
                bill_no: "PINV-20-00312",
                bill_date: "2020-08-20",
            },
            {
                supplier_name: "Shikhar Steel Corporation",
                supplier_gstin: "27AVGPB2421B1ZE",
                bill_no: "PINV-20-00277",
                bill_date: "2020-08-10",
            },
            {
                supplier_name: "Shikhar Steel Corporation",
                supplier_gstin: "27AVGPB2421B1ZE",
                bill_no: "PINV-20-00269",
                bill_date: "2020-08-05",
            },
            {
                supplier_name: "P K Enterprise",
                supplier_gstin: "24CBFPR3680H1ZH",
                bill_no: "PINV-20-00420",
                bill_date: "2020-09-17",
            },
            {
                supplier_name: "Karan Enterprise",
                supplier_gstin: "24AJEPS2985B1Z8",
                bill_no: "PINV-20-00458",
                bill_date: "2020-10-07",
            },
            {
                supplier_name: "Jayhind Metal and Tubes",
                supplier_gstin: "27AAIPS6329N1ZY",
                bill_no: "PINV-20-00314",
                bill_date: "2020-08-21",
            },
            {
                supplier_name: "Divya Metal India",
                supplier_gstin: "27APUPB5857M1Z3",
                bill_no: "PINV-20-00287",
                bill_date: "2020-08-18",
            },
            {
                supplier_name: "Natwarlal Hiralal Shah",
                supplier_gstin: "24AFRPS0569Q1ZH",
                bill_no: "PINV-20-00470",
                bill_date: "2020-10-14",
            },
            {
                supplier_name: "Kulubi Steel",
                supplier_gstin: "24AABFK8892P1ZK",
                bill_no: "PINV-20-00469",
                bill_date: "2020-10-16",
            },
            {
                supplier_name: "Nidhi Transport Service",
                supplier_gstin: "24ABVPB2674D2ZQ",
                bill_no: "PINV-20-00468",
                bill_date: "2020-10-16",
            },
            {
                supplier_name: "Santosh Steels",
                supplier_gstin: "27AAAFS3466L1ZV",
                bill_no: "PINV-20-00467",
                bill_date: "2020-10-14",
            },
            {
                supplier_name: "Shreeji Enterprises",
                supplier_gstin: "24ABBFS8099M1ZH",
                bill_no: "PINV-20-00466",
                bill_date: "2020-10-14",
            },
            {
                supplier_name: "Bureau Veritas India Private Ltd",
                supplier_gstin: "24AABCB6767B2ZX",
                bill_no: "PINV-20-00464",
                bill_date: "2020-10-08",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00432",
                bill_date: "2020-09-28",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00427",
                bill_date: "2020-09-23",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00417",
                bill_date: "2020-09-22",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00416",
                bill_date: "2020-09-22",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00415",
                bill_date: "2020-09-18",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00414",
                bill_date: "2020-09-17",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00377",
                bill_date: "2020-09-04",
            },
            {
                supplier_name: "Met Heat Engineers Pvt Ltd",
                supplier_gstin: "24AABCM3871D1ZS",
                bill_no: "PINV-20-00376",
                bill_date: "2020-09-03",
            },
            {
                supplier_name: "Sanjay Forge Pvt Ltd",
                supplier_gstin: "27AADCS7826G1Z5",
                bill_no: "PINV-20-00456",
                bill_date: "2020-03-20",
            },
            {
                supplier_name: "Sanjay Forge Pvt Ltd",
                supplier_gstin: "27AADCS7826G1Z5",
                bill_no: "PINV-R-20-00003",
                bill_date: "2020-03-20",
            },
            {
                supplier_name: "Sanjay Bonny Forge Pvt Ltd",
                supplier_gstin: "27AAKCS3246H1Z6",
                bill_no: "PINV-20-00278",
                bill_date: "2020-08-10",
            },
            {
                supplier_name: "Rajdhan Metal",
                supplier_gstin: "27AAEPJ8093L1Z6",
                bill_no: "PINV-20-00455",
                bill_date: "2020-10-03",
            },
            {
                supplier_name: "S B Associates",
                supplier_gstin: "24ADCPG1409L1ZX",
                bill_no: "PINV-20-00454",
                bill_date: "2020-10-01",
            },
            {
                supplier_name: "S M Heat Treatment Works",
                supplier_gstin: "24BWGPP6376K1ZY",
                bill_no: "PINV-20-00453",
                bill_date: "2020-10-06",
            },
            {
                supplier_name: "Nidhi Transport Service",
                supplier_gstin: "24ABVPB2674D2ZQ",
                bill_no: "PINV-20-00452",
                bill_date: "2020-10-07",
            },
            {
                supplier_name: "Rai Crane Service",
                supplier_gstin: "24AIXPR1887P1Z0",
                bill_no: "PINV-20-00446",
                bill_date: "2020-10-06",
            },
            {
                supplier_name: "Shree Khodiyar Transport",
                supplier_gstin: "24AOYPP5222R1Z0",
                bill_no: "PINV-20-00443",
                bill_date: "2020-10-03",
            },
            {
                supplier_name: "V Trans India Ltd",
                supplier_gstin: "27AAACV1559Q2ZP",
                bill_no: "PINV-20-00444",
                bill_date: "2020-09-29",
            },
            {
                supplier_name: "Tapan Enterprise",
                supplier_gstin: "24AEPPS0534Q1ZW",
                bill_no: "PINV-20-00439-1",
                bill_date: "2020-09-09",
            },
            {
                supplier_name: "Raj Enterprise",
                supplier_gstin: "24BFHPK5295N1ZV",
                bill_no: "PINV-20-00440",
                bill_date: "2020-09-30",
            },
            {
                supplier_name: "Shreeji Trading Company",
                supplier_gstin: "24AATPM0382J1ZE",
                bill_no: "PINV-20-00437",
                bill_date: "2020-09-30",
            },
            {
                supplier_name: "New Light Tube Corporation",
                supplier_gstin: "27AHLPK8194K1ZK",
                bill_no: "PINV-20-00392",
                bill_date: "2020-08-24",
            },
            {
                supplier_name: "P K Enterprise",
                supplier_gstin: "24CBFPR3680H1ZH",
                bill_no: "PINV-20-00422",
                bill_date: "2020-09-01",
            },
            {
                supplier_name: "P K Enterprise",
                supplier_gstin: "24CBFPR3680H1ZH",
                bill_no: "PINV-20-00421",
                bill_date: "2020-09-01",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00429",
                bill_date: "2020-09-30",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00426",
                bill_date: "2020-09-28",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00410",
                bill_date: "2020-09-19",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00409",
                bill_date: "2020-09-18",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00397",
                bill_date: "2020-09-16",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00396",
                bill_date: "2020-09-16",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00390",
                bill_date: "2020-09-15",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00383",
                bill_date: "2020-09-12",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00369",
                bill_date: "2020-09-09",
            },
            {
                supplier_name: "Time Transport Co",
                supplier_gstin: "24AADFT5917A1ZK",
                bill_no: "PINV-20-00368",
                bill_date: "2020-09-08",
            },
        ];
    }
}

async function fetch_date_range(frm, field_prefix) {
    const from_date_field = field_prefix + "_from_date";
    const to_date_field = field_prefix + "_to_date";
    const period = frm.doc[field_prefix + "_period"];
    if (period == "Custom") return;

    const { message } = await frm.call("get_date_range", { period });
    if (!message) return;

    frm.set_value(from_date_field, message[0]);
    frm.set_value(to_date_field, message[1]);
}

function get_gstr_dialog_fields() {
    return [
        {
            label: "GST Return Type",
            fieldname: "return_type",
            fieldtype: "Select",
            default: ReturnType.GSTR2B,
            options: [
                { label: "GSTR 2A", value: ReturnType.GSTR2A },
                { label: "GSTR 2B", value: ReturnType.GSTR2B },
            ],
        },
        {
            fieldtype: "Column Break",
        },
        {
            label: "Fiscal Year",
            fieldname: "fiscal_year",
            fieldtype: "Link",
            options: "Fiscal Year",
            default: frappe.defaults.get_default("fiscal_year"),
            get_query() {
                return {
                    filters: {
                        year_end_date: [">", "2017-06-30"],
                    },
                };
            },
        },
    ];
}

function get_history_fields(for_download = true) {
    const label = for_download ? "Download History" : "Upload History";

    return [
        { label, fieldtype: "Section Break" },
        { label, fieldname: "history", fieldtype: "HTML" },
    ];
}

function show_gstr_dialog(frm, for_download = true) {
    let dialog;
    if (for_download) {
        dialog = _show_download_gstr_dialog();
    } else {
        dialog = _show_upload_gstr_dialog();
        dialog.fields_dict.attach_file.df.onchange = () => {
            const attached_file = dialog.get_value("attach_file");
            if (!attached_file) return;
            fetch_return_period_from_file(frm, dialog);
        };
    }

    dialog.fields_dict.fiscal_year.df.onchange = () => {
        fetch_download_history(frm, dialog, for_download);
    };

    dialog.fields_dict.return_type.df.onchange = () => {
        set_dialog_actions(frm, dialog, for_download);
        fetch_download_history(frm, dialog, for_download);
    };

    set_dialog_actions(frm, dialog, for_download);
    fetch_download_history(frm, dialog, for_download);
}

function set_dialog_actions(frm, dialog, for_download) {
    const return_type = dialog.get_value("return_type");

    if (for_download) {
        if (return_type === ReturnType.GSTR2A) {
            dialog.set_primary_action(__("Download All"), () => {
                download_gstr(
                    frm,
                    dialog.get_value("return_type"),
                    dialog.get_value("fiscal_year"),
                    false
                );
                dialog.hide();
            });
            dialog.set_secondary_action_label(__("Download Missing"));
            dialog.set_secondary_action(() => {
                download_gstr(
                    frm,
                    dialog.get_value("return_type"),
                    dialog.get_value("fiscal_year"),
                    true
                );
                dialog.hide();
            });
        } else if (return_type === ReturnType.GSTR2B) {
            dialog.set_primary_action(__("Download"), () => {
                download_gstr(
                    frm,
                    dialog.get_value("return_type"),
                    dialog.get_value("fiscal_year"),
                    true
                );
                dialog.hide();
            });
            dialog.set_secondary_action_label(null);
            dialog.set_secondary_action(null);
        }
    } else {
        dialog.set_primary_action(__("Upload"), () => {
            const file_path = dialog.get_value("attach_file");
            const period = dialog.get_value("period");
            if (!file_path) frappe.throw(__("Please select a file first!"));
            if (!period)
                frappe.throw(
                    __(
                        "Could not fetch period from file, make sure you have selected the correct file!"
                    )
                );
            upload_gstr(frm, return_type, period, file_path);
            dialog.hide();
        });
    }
}

function _show_download_gstr_dialog() {
    const dialog = new frappe.ui.Dialog({
        title: __("Download Data from GSTN"),
        fields: [...get_gstr_dialog_fields(), ...get_history_fields()],
    });
    return dialog.show();
}

function _show_upload_gstr_dialog() {
    const dialog = new frappe.ui.Dialog({
        title: __("Upload Data"),
        fields: [
            ...get_gstr_dialog_fields(),
            {
                label: "Period",
                fieldname: "period",
                fieldtype: "Data",
                read_only: 1,
            },
            {
                fieldtype: "Section Break",
            },
            {
                label: "Attach File",
                fieldname: "attach_file",
                fieldtype: "Attach",
                description: "Attach .json file here",
                options: { restrictions: { allowed_file_types: [".json"] } },
            },
            ...get_history_fields(false),
        ],
    });
    return dialog.show();
}

async function fetch_download_history(frm, dialog, for_download = true) {
    const { message } = await frm.call("get_import_history", {
        return_type: dialog.get_value("return_type"),
        fiscal_year: dialog.get_value("fiscal_year"),
        for_download: for_download,
    });

    if (!message) return;
    dialog.fields_dict.history.set_value(message);
}

async function fetch_return_period_from_file(frm, dialog) {
    const return_type = dialog.get_value("return_type");
    const file_path = dialog.get_value("attach_file");
    const { message } = await frm.call("get_return_period_from_file", {
        return_type,
        file_path,
    });

    if (!message) {
        dialog.get_field("attach_file").clear_attachment();
        frappe.throw(
            __(
                "Please make sure you have uploaded the correct file. File Uploaded is not for {0}",
                [return_type]
            )
        );

        return dialog.hide();
    }

    await dialog.set_value("period", message);
    dialog.refresh();
}

async function download_gstr(
    frm,
    return_type,
    fiscal_year,
    only_missing = true,
    otp = null
) {
    let method;
    const args = { fiscal_year, otp };
    if (return_type === ReturnType.GSTR2A) {
        method = "download_gstr_2a";
        args.force = !only_missing;
    } else {
        method = "download_gstr_2b";
    }

    reco_tool.show_progress(frm, "download");
    const { message } = await frm.call(method, args);
    if (message && message.errorCode == "RETOTPREQUEST") {
        const otp = await get_gstin_otp();
        if (otp) download_gstr(frm, return_type, fiscal_year, only_missing, otp);
        return;
    }
}

function get_gstin_otp() {
    return new Promise(resolve => {
        frappe.prompt(
            {
                fieldtype: "Data",
                label: "One Time Password",
                fieldname: "otp",
                reqd: 1,
                description:
                    "An OTP has been sent to your registered mobile/email for further authentication. Please provide OTP.",
            },
            function ({ otp }) {
                resolve(otp);
            },
            "Enter OTP"
        );
    });
}

function upload_gstr(frm, return_type, period, file_path) {
    reco_tool.show_progress(frm, "upload");
    frm.call("upload_gstr", { return_type, period, file_path });
}

// TODO: refactor progress
reco_tool.show_progress = function (frm, type) {
    if (type == "download") {
        frappe.run_serially([
            () => update_progress(frm, "update_api_progress"),
            () => update_progress(frm, "update_transactions_progress"),
        ]);
    } else if (type == "upload") {
        update_progress(frm, "update_transactions_progress");
    }
};

function update_progress(frm, method) {
    frappe.realtime.on(method, data => {
        const { current_progress } = data;
        const message =
            method == "update_api_progress"
                ? __("Fetching data from GSTN")
                : __("Updating Inward Supply for Return Period {0}", [
                      data.return_period,
                  ]);

        frm.dashboard.show_progress("Import GSTR Progress", current_progress, message);
        frm.page.set_indicator(__("In Progress"), "orange");
        if (data.is_last_period) {
            frm.flag_last_return_period = data.return_period;
        }
        if (
            current_progress == 100 &&
            method != "update_api_progress" &&
            frm.flag_last_return_period == data.return_period
        ) {
            setTimeout(() => {
                frm.dashboard.hide();
                frm.refresh();
                frm.page.set_indicator(__("Success"), "green");
                frm.dashboard.set_headline("Successfully Imported");
                setTimeout(() => {
                    frm.page.clear_headline();
                }, 2000);
                frm.save();
            }, 1000);
        }
    });
}

reco_tool.apply_filters = function ({ tab, filters }) {
    if (!cur_frm) return;

    // Switch to the tab
    const { tabs } = cur_frm.purchase_reconciliation_tool;
    tab = tabs && (tabs[tab] || Object.values(tabs).find(tab => tab.is_active()));
    tab.set_active();

    // apply filters
    const _filters = {};
    for (const [fieldname, filter] of Object.entries(filters)) {
        const column = tab.data_table_manager.get_column(fieldname);
        column.$filter_input.value = filter;
        _filters[column.colIndex] = filter;
    }

    tab.data_table_manager.datatable.columnmanager.applyFilter(_filters);
};

function get_formatted(value, row, column, data, icon, callback) {
    /**
     * Returns custom ormated value for the row.
     * @param {string} value        Current value of the row.
     * @param {object} row          All values of current row
     * @param {object} column       All properties of current column
     * @param {object} data         All values in its core form for current row
     * @param {string} icon         Return icon (font-awesome) as the content
     * @param {function} callback   Callback on click of icon
     */

    let content;
    if (icon && callback) content = get_icon(icon, callback, data);
    if (value) content = value;

    return frappe.form.get_formatter(column.docfield.fieldtype)(
        content,
        column.docfield,
        { always_show_decimals: true },
        data
    );
}

function get_icon(icon, callback, data) {
    console.log(`${callback}${(data)}`, callback(data));
    return `<button class="btn" title="hello" onclick="${callback}${(data)}">
                <i class="fa fa-${icon}"></i>
            </button>`;
}

reco_tool.show_detailed_dialog = function (data) {
    console.log("trial:", data);
    const actions = {
        primary_action_label: 'Accept My Values',
        secondary_action_label: 'Unlink',
    };

    var d = new frappe.ui.Dialog({
        title: "Detail View",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "detail_view",
            }
        ],
        primary_action: function () {
            d.hide();
        },
        primary_action_label: __(actions.primary_action_label),
        secondary_action: function () {
            d.hide();
        },
        secondary_action_label: __(actions.secondary_action_label),
    });
    d.fields_dict.detail_view.$wrapper.html(get_content_html(data));
    d.show();
};

function get_content_html(data) {
    let content_html = "";

    content_html += `
        <div class="container">
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>Description</th>
                    <th>2A / 2B</th>
                    <th>Purchase</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Links</td>
                    <td></td>
                    <td></td>
                </tr>
                <tr>
                    <td>Bill No</td>
                    <td>${data.bill_no}</td>
                    <td>${data.bill_no}</td>
                </tr>
                <tr>
                    <td>Bill Date</td>
                    <td>${ frappe.format(`${data.bill_date}`, {'fieldtype': 'Date'}) }</td>
                    <td>${ frappe.format(`${data.bill_date}`, {'fieldtype': 'Date'}) }</td>
                </tr>
                <tr>
                    <td>CGST</td>
                    <td>${data.cgst}</td>
                    <td>${data.cgst}</td>
                </tr>
                <tr>
                    <td>SGST</td>
                    <td>${data.sgst}</td>
                    <td>${data.sgst}</td>
                </tr>
                <tr>
                    <td>IGST</td>
                    <td>${data.igst}</td>
                    <td>${data.igst}</td>
                </tr>
                <tr>
                    <td>CESS</td>
                    <td>${data.cess}</td>
                    <td>${data.cess}</td>
                </tr>
                <tr>
                    <td>Tax Diff</td>
                    <td>${data.tax_diff}</td>
                    <td>${data.tax_diff}</td>
                </tr>
                <tr>
                    <td>Total Value</td>
                    <td>${data.total_value}</td>
                    <td>${data.total_value}</td>
                </tr>
                <tr>
                    <td>Value Diff</td>
                    <td>${data.value_diff}</td>
                    <td>${data.value_diff}</td>
                </tr>
                <tr>
                    <td>Differences</td>
                    <td>${data.differences}</td>
                    <td>${data.differences}</td>
                </tr>
            </tbody>
        </table>
    </div>
    `;
    return content_html;
}