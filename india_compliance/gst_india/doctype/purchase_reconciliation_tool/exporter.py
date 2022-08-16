import openpyxl
from openpyxl.formatting.rule import Rule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.utils import get_column_letter

import frappe


class ExcelExporter:
    def __init__(
        self,
        sheets,
        filters,
        merged_headers,
        headers,
        data,
        file_name,
    ):
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

    def build_csv_array(self, data):
        """Builds an array of csv data"""
        csv_array = []

        for row in data:
            csv_array.append(self.build_csv_row(row))
        return csv_array

    def build_csv_row(self, row, header=False):
        """Builds a csv row"""
        csv_row = []

        for data in row:
            if header:
                csv_row.append(data.get("label"))
        return csv_row

    def add_header(self, headers):
        headers = []
        for header in headers:
            pass

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

        if text:
            rule = Rule(
                type="containsText", operator="containsText", text=text, dxf=dxf
            )
        else:
            rule = Rule(type="cells", dxf=dxf)
        return rule

    def get_font_style(self, font_family="Calibri", font_size=9, bold=True, color=None):
        font = Font(size=font_size, name=font_family, bold=bold)
        if color:
            font.color = color
        return font

    def get_pattern_fill(self, color, fill_type="solid"):
        if not color:
            return None
        return PatternFill(fgColor=color, fill_type=fill_type)

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

    def get_range(self, start_row, start_column, end_row, end_column):
        start_column_letter = get_column_letter(start_column)
        end_column_letter = get_column_letter(end_column)
        range = f"{start_column_letter}{start_row}:{end_column_letter}{end_row}"
        return range

    def add_background_color(self, ws, additional_style):
        for style in additional_style:
            min_row = style.get("min_row")
            max_row = style.get("max_row")
            min_col = style.get("min_col")
            max_col = style.get("max_col")
            bg_color = style.get("bg_color")

            for row in ws.iter_rows(
                min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col
            ):
                for cell in row:
                    self.apply_format(ws, cell=cell, bg_color=bg_color, update=True)

            if style.get("move_range"):
                move_col = style.get("move_col")
                range = self.get_range(min_row, min_col, max_row, max_col)
                print(range)
                ws.move_range(range, rows=0, cols=move_col)

    def apply_format(
        self,
        ws,
        cell,
        text_color="000000",
        bg_color=None,
        bold=False,
        column_widths=None,
        wrap_text=True,
        vertical="bottom",
        horizontal="general",
        column=None,
        update=False,
    ):
        if update:
            if bg_color:
                cell.fill = self.get_pattern_fill(bg_color)
            return ws

        cell.number_format = "0.00"
        cell.font = self.get_font_style(color=text_color, bold=bold)
        cell.alignment = Alignment(
            horizontal=horizontal, vertical=vertical, wrap_text=wrap_text
        )

        if bg_color:
            cell.fill = self.get_pattern_fill(bg_color)

        if column_widths:
            for i, column_width in enumerate(column_widths, 1):  # ,1 to start at 1
                ws.column_dimensions[get_column_letter(i)].width = column_width

        ws.row_dimensions[4].height = 30
        ws.row_dimensions[5].height = 30

        return ws

    def append_data(
        self,
        ws,
        data,
        add_row=1,
        add_column=1,
        is_common_header=False,
        column_widths=None,
        bg_color=None,
        wrap_text=True,
        horizontal="general",
        vertical="bottom",
    ):
        """data is a list of lists"""

        for i, row in enumerate(data):
            for j, val in enumerate(row):
                cell = ws.cell(row=i + add_row, column=j + add_column)
                if isinstance(val, str):
                    val = val.replace("<br>", "\n")
                cell.value = val

                bold = True if is_common_header else False
                self.apply_format(
                    ws,
                    cell,
                    column=j + add_column,
                    bold=bold,
                    column_widths=column_widths,
                    bg_color=bg_color,
                    wrap_text=wrap_text,
                    horizontal=horizontal,
                    vertical=vertical,
                )
        return ws

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
        sheet_name,
        position,
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
        self.append_data(
            worksheet, data, add_row=row, add_column=start_column, is_common_header=True
        )

        # self.update_header_data(worksheet, header, row=row)
        # self.setup_header_for_invoice_data(worksheet, range=range, color=header_color)
        # self.update_data(worksheet, data, header, color=body_color)

        if save:
            self.save_workbook(workbook, file_name)

        return workbook


@frappe.whitelist()
def export_data_to_xlsx(args, column_widths=None):
    if isinstance(args, str):
        args = frappe.parse_json(args)

    exporter = ExcelExporter()
    workbook = exporter.create_workbook()

    for i, sheet_name in enumerate(args.get("sheet_names")):
        worksheet = exporter.create_worksheet(workbook, sheet_name, i)
        exporter.append_data(
            worksheet,
            data=args.get("common_header"),
            add_row=1,
            add_column=1,
            is_common_header=True,
            wrap_text=False,
            horizontal="left",
        )

        # 0th index of args array contains the header data
        if sheet_name == "Summary Data" and args.get("match_summary"):
            data = args.match_summary[1:]
            data_header = [args.match_summary[0]]
            column_widths = [20, 20, 12, 18, 18, 12]
            header_color = "d9d9d9"
            body_color = "f2f2f2"
            add_row = 5
            additional_style = [
                {
                    "min_row": 6,
                    "min_col": 4,
                    "max_col": 5,
                    "bg_color": "f2dcdb",
                }
            ]

        if sheet_name == "Supplier Data" and args.get("supplier_summary"):
            data = args.supplier_summary[1:]
            data_header = [args.supplier_summary[0]]
            column_widths = [20, 20, 12, 12, 18, 18, 12]
            header_color = "d9d9d9"
            body_color = "f2f2f2"
            add_row = 5
            additional_style = [
                {
                    "min_row": 6,
                    "min_col": 5,
                    "max_col": 6,
                    "bg_color": "f2dcdb",
                }
            ]

        if sheet_name == "Invoice Data" and args.get("data"):
            data = args.data[1:]
            data_header = args.data[0]

            # column_widths
            isup_pr_column_widths = [12] * 18
            column_widths = [20, 20, 20, 15, 11, 12, 12]
            column_widths.extend(isup_pr_column_widths)
            add_row = 4
            additional_style = [
                {
                    "min_row": 6,
                    "min_col": 6,
                    "max_col": 7,
                    "bg_color": "f2dcdb",
                },
                {
                    "min_row": 4,
                    "max_row": 4,
                    "min_col": 1,
                    "max_col": 2,
                    "move_col": 7,
                    "bg_color": "c6d9f1",
                    "move_range": True,
                },
            ]

        # To add header data to the sheet
        exporter.append_data(
            worksheet,
            data_header,
            add_row=add_row,
            add_column=1,
            is_common_header=True,
            column_widths=column_widths,
            bg_color=header_color,
            horizontal="center",
            vertical="center",
        )

        # To add data to the sheet
        exporter.append_data(
            worksheet,
            data,
            add_row=6,
            add_column=1,
            is_common_header=False,
            column_widths=column_widths,
            bg_color=body_color,
            wrap_text=False,
        )

        rule = exporter.highlight_cell(bg_color="e6b9b8", color="000000", text="Diff")
        worksheet.conditional_formatting.add("A1:Y10", rule)

        # To add additional background color to the sheet
        exporter.add_background_color(worksheet, additional_style)

    # if args.get("supplier_summary"):
    #     supplier_summary = args.supplier_summary[1:]
    #     supplier_summary_header = args.supplier_summary[0]
    #     exporter.add_worksheet(
    #         data=supplier_summary,
    #         header=supplier_summary_header,
    #         sheet_name=args.sheet_names[1],
    #         position=1,
    #         range="A2:F2",
    #         header_color="d9d9d9",
    #         body_color="f2f2f2",
    #         row=2,
    #         workbook=workbook,
    #     )

    # if args.get("data"):
    #     invoice_summary = args.data[1:]
    #     inv_main_header = args.data[0][0]
    #     inv_sub_header = args.data[0][1]

    #     # Invoice Summary Sheet
    #     ws1 = workbook.create_sheet(
    #         args.sheet_names[2], 2 if args.get("supplier_summary") else 1
    #     )

    #     if inv_main_header:
    #         exporter.update_header_data(ws1, inv_main_header, 1, 8, 9)
    #         exporter.setup_header_for_invoice_data(
    #             ws1, font_size=12, range="H1:P2", color="c6d9f1"
    #         )

    #     if inv_sub_header:
    #         exporter.update_header_data(ws1, inv_sub_header, 2, 1, 1)
    #         exporter.setup_header_for_invoice_data(
    #             ws1, font_size=12, range="Q1:Y2", color="d7e4bd"
    #         )

    #     if args.get("data"):
    #         ws1.merge_cells("H1:P1")
    #         ws1.merge_cells("Q1:Y1")

    #     exporter.setup_header_for_invoice_data(ws1, range="A2:E2", color="d9d9d9")
    #     exporter.setup_header_for_invoice_data(ws1, range="F2:G2", color="e6b9b8")
    #     exporter.setup_header_for_invoice_data(ws1, range="A2:Y2")

    #     exporter.update_data(ws1, invoice_summary, inv_sub_header, color="f2f2f2")

    exporter.remove_worksheet(workbook, "Sheet")
    exporter.save_workbook(workbook, f"{args.get('file_name')}.xlsx")
