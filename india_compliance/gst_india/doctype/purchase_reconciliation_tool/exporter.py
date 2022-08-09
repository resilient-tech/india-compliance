import openpyxl
from openpyxl.formatting.rule import Rule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.styles.differential import DifferentialStyle

import frappe


class ExcelExporter:
    def __init__(self):
        pass

    def create_workbook(self):
        wb = openpyxl.Workbook()
        return wb

    def create_worksheet(self, wb, sheet_name, position=None):
        ws = wb.create_sheet(sheet_name, position)
        return ws

    def remove_worksheet(self, workbook, sheet_name):
        workbook.remove(workbook[sheet_name])
        return workbook

    def highlight_cell(
        self,
        fill_type="solid",
        font_size=9,
        bold=True,
        color="FFFF00",
        bg_color="FFFFFF",
        text=None,
    ):
        """Hightlight cell based on text"""

        text_style = self.get_font_style(color=color)
        bg_fill = PatternFill(bgColor=bg_color, fill_type=fill_type)
        dxf = DifferentialStyle(font=text_style, fill=bg_fill)

        rule = Rule(type="containsText", operator="containsText", text=text, dxf=dxf)
        return rule

    def get_font_style(self, font_family="Calibri", font_size=9, bold=True, color=None):
        font = Font(size=font_size, name=font_family, bold=bold)
        if color:
            font.color = color
        return font

    def get_pattern_fill(self, color, fill_type="solid"):
        return PatternFill(fgColor=color, fill_type=fill_type)

    def update_header_data(
        self, ws, header_list, row=1, start_column=1, increment_by=1
    ):
        for header in header_list:
            cell = ws.cell(row=row, column=start_column)
            cell.value = header.replace("<br>", "\n")
            rule = self.highlight_cell(bg_color="e6b9b8", color="000000", text="Diff")
            ws.conditional_formatting.add("A1:Y10", rule)
            start_column += increment_by
        return ws

    def setup_header_for_invoice_data(
        self, ws, alignment="center", font_size=9, range=None, color=None
    ):

        font = self.get_font_style(font_size=font_size)

        if not range:
            return

        for row in ws[range]:
            for cell in row:
                if color:
                    cell.fill = self.get_pattern_fill(color)
                cell.font = font
                cell.alignment = Alignment(
                    horizontal=alignment, vertical=alignment, wrap_text=True
                )

    def update_data(self, ws, data_list, header, alignment="left", color=None):
        for i, data in enumerate(data_list):
            for j, value in enumerate(data):
                column_label = ws.cell(row=2, column=j + 1).value
                column = str(chr(64 + (j + 1)))
                bg_color = color or "FFFFFF"
                width = 20
                text_color = "000000"

                if "Diff" in column_label:
                    bg_color = "f2dcdb"
                    width = 12 if ws.title == "Invoice Data" else 18
                    text_color = "ff0000"
                elif j in range(7, 16):
                    bg_color = "dce6f2"
                    width = 12
                elif j in range(16, 25):
                    bg_color = "ebf1de"
                    width = 12
                bg_fill = self.get_pattern_fill(bg_color)
                font = self.get_font_style(color=text_color, bold=False)

                ws.cell(row=i + 3, column=j + 1).fill = bg_fill
                ws.cell(row=i + 3, column=j + 1).value = value
                ws.cell(row=i + 3, column=j + 1).font = font
                ws.cell(row=i + 3, column=j + 1).number_format = "0.00"
                ws.column_dimensions[column].width = width
                ws.row_dimensions[1].height = 30
                ws.row_dimensions[2].height = 30
        return ws

    def save_workbook(self, wb, file_name):
        wb.save(file_name)
        return wb

    def read_workbook(self, file_name):
        file_path = frappe.get_site_path("private", "files", file_name)
        wb = openpyxl.load_workbook(file_path, read_only=False, keep_vba=True)
        return wb

    def add_worksheet(
        self,
        data,
        header,
        sheet_name,
        position,
        range,
        header_color,
        sub_header_color=None,
        body_color="FFFFFF",
        font_size=9,
        row=1,
        start_column=1,
        increment_by=1,
        save=False,
        workbook=None,
        file_name=None,
    ):
        if not workbook:
            workbook = self.create_workbook()

        worksheet = self.create_worksheet(workbook, sheet_name, position)

        self.update_header_data(worksheet, header, row=row)
        self.setup_header_for_invoice_data(worksheet, range=range, color=header_color)
        self.update_data(worksheet, data, header, color=body_color)

        if save:
            self.save_workbook(workbook, file_name)

        return workbook


@frappe.whitelist()
def export_data_to_xlsx(args, column_widths=None):
    if isinstance(args, str):
        args = frappe.parse_json(args)

    exporter = ExcelExporter()
    workbook = exporter.create_workbook()

    # 0th index of args array contains the header data

    if args.get("match_summary"):
        match_summary = args.match_summary[1:]
        match_summary_header = args.match_summary[0]
        exporter.add_worksheet(
            data=match_summary,
            header=match_summary_header,
            sheet_name=args.sheet_names[0],
            position=0,
            range="A2:F2",
            header_color="d9d9d9",
            body_color="f2f2f2",
            row=2,
            workbook=workbook,
        )

    if args.get("supplier_summary"):
        supplier_summary = args.supplier_summary[1:]
        supplier_summary_header = args.supplier_summary[0]
        exporter.add_worksheet(
            data=supplier_summary,
            header=supplier_summary_header,
            sheet_name=args.sheet_names[1],
            position=1,
            range="A2:F2",
            header_color="d9d9d9",
            body_color="f2f2f2",
            row=2,
            workbook=workbook,
        )

    if args.get("data"):
        invoice_summary = args.data[1:]
        inv_main_header = args.data[0][0]
        inv_sub_header = args.data[0][1]

        # Invoice Summary Sheet
        ws1 = workbook.create_sheet(
            args.sheet_names[2], 2 if args.get("supplier_summary") else 1
        )

        if inv_main_header:
            exporter.update_header_data(ws1, inv_main_header, 1, 8, 9)
            exporter.setup_header_for_invoice_data(
                ws1, font_size=12, range="H1:P2", color="c6d9f1"
            )

        if inv_sub_header:
            exporter.update_header_data(ws1, inv_sub_header, 2, 1, 1)
            exporter.setup_header_for_invoice_data(
                ws1, font_size=12, range="Q1:Y2", color="d7e4bd"
            )

        if args.get("data"):
            ws1.merge_cells("H1:P1")
            ws1.merge_cells("Q1:Y1")

        exporter.setup_header_for_invoice_data(ws1, range="A2:E2", color="d9d9d9")
        exporter.setup_header_for_invoice_data(ws1, range="F2:G2", color="e6b9b8")
        exporter.setup_header_for_invoice_data(ws1, range="A2:Y2")

        exporter.update_data(ws1, invoice_summary, inv_sub_header, color="f2f2f2")

    exporter.remove_worksheet(workbook, "Sheet")
    exporter.save_workbook(workbook, f"{args.get('file_name')}.xlsx")
