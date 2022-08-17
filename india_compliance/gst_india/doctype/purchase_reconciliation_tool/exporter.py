import openpyxl

# from openpyxl.formatting.rule import Rule
# from openpyxl.styles import Alignment, Font, PatternFill
# from openpyxl.styles.differential import DifferentialStyle
# from openpyxl.utils import get_column_letter


class ExcelExporter:
    def __init__(self):
        pass

    def get_workbook(self, workbook=None):
        if not workbook:
            workbook = openpyxl.Workbook()

        return workbook

    def create_worksheet(self, *args, **kwargs):
        """
        Make xlsx file
        :param workbook - Object of excel file/ workbook
        :param sheet_name - name for the worksheet
        :param filters - A data dictionary to added in sheet
        :param merged_headers - A dict of List
            @example: {
                'label': [column1, colum2]
            }
        :param headers: A List of dictionary (cell properties will be optional)
        :param data: A list of dictionary to append data to sheet
        :param file_name: Name of excel file/workbook
        """
        # Create workbook if not passed or return existing workbook
        wb = self.get_workbook(kwargs.get("workbook"))

        # ToDo: Create a new sheet
        cs = CreateWorksheet()
        cs.create_worksheet(
            wb,
            sheet_name=kwargs.get("sheet_name"),
            filters=kwargs.get("filters"),
            merged_headers=kwargs.get("merged_headers"),
            headers=kwargs.get("headers"),
            data=kwargs.get("data"),
        )

        self.save_workbook(wb, kwargs.get("file_name"))
        return wb

    def save_workbook(self, wb, file_name):
        """Save workbook"""
        if file_name[-4:] != ".xlsx":
            file_name = f"{file_name}.xlsx"

        wb.save(file_name)

    def remove_worksheet(self, wb, sheet_name):
        """Remove worksheet"""
        if sheet_name in wb.sheetnames:
            wb.remove(wb[sheet_name])


class CreateWorksheet:
    def __init__(self):
        self.row_dimension = 1

    def create_worksheet(
        self,
        workbook,
        sheet_name,
        filters,
        headers,
        data,
        merged_headers=None,
    ):
        """Create worksheet"""
        ws = workbook.create_sheet(sheet_name)
        self.add_data(ws, filters)
        return ws

    def add_data(self, ws, data):
        """Adds header data to the sheet"""
        data = self.parse_dict(data)

        for i, row in enumerate(data):
            ws.append(row)
            self.row_dimension += i

        return ws

    def parse_dict(self, data):
        """Convert Dictionary Key-value dictionary to List of Lists"""
        csv_list = []

        if isinstance(data, dict):
            for key, value in data.items():
                csv_list.append([key, value])

        return csv_list

    def build_csv_array(self, data):
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

    # def apply_format(
    #     self,
    #     ws,
    #     row=None,
    #     column=None,
    #     bold=True,
    #     font_size=9,
    #     column_widths=None,
    #     wrap_text=False,
    #     align_header="center",
    #     align_data="general",
    # ):
    #     """Applies formatting to the cell"""
    #     default_bold_font = self.get_font_style()

    #     if row_dimensions is not None:
    #         ws.row_dimensions[row].font = default_bold_font
    #         ws.row_dimensions[row].alignment = Alignment(horizontal=align_header)
    #         return row_dimensions

    #     if update:
    #         if bg_color:
    #             cell.fill = self.get_pattern_fill(bg_color)
    #         return ws

    #     cell.number_format = "0.00"
    #     cell.font = self.get_font_style(color=text_color, bold=bold)
    #     cell.alignment = Alignment(
    #         horizontal=horizontal, vertical=vertical, wrap_text=wrap_text
    #     )

    #     if bg_color:
    #         cell.fill = self.get_pattern_fill(bg_color)

    #     if column_widths:
    #         for i, column_width in enumerate(column_widths, 1):  # ,1 to start at 1
    #             ws.column_dimensions[get_column_letter(i)].width = column_width

    #     ws.row_dimensions[4].height = 30
    #     ws.row_dimensions[5].height = 30

    #     return ws

    # def highlight_cell(
    #     self,
    #     fill_type="solid",
    #     font_size=9,
    #     bold=True,
    #     color="FFFF00",
    #     bg_color="FFFFFF",
    #     text=None,
    # ):
    #     """Hightlight cell based on text"""

    #     text_style = self.get_font_style(color=color)
    #     bg_fill = PatternFill(bgColor=bg_color, fill_type=fill_type)
    #     dxf = DifferentialStyle(font=text_style, fill=bg_fill)

    #     if text:
    #         rule = Rule(
    #             type="containsText", operator="containsText", text=text, dxf=dxf
    #         )
    #     else:
    #         rule = Rule(type="cells", dxf=dxf)
    #     return rule

    # def get_font_style(self, font_family="Calibri", font_size=9, bold=True):
    #     font = Font(size=font_size, name=font_family, bold=bold)
    #     return font

    # def get_pattern_fill(self, color, fill_type="solid"):
    #     if not color:
    #         return None
    #     return PatternFill(fgColor=color, fill_type=fill_type)

    # def get_range(self, start_row, start_column, end_row, end_column):
    #     start_column_letter = get_column_letter(start_column)
    #     end_column_letter = get_column_letter(end_column)
    #     range = f"{start_column_letter}{start_row}:{end_column_letter}{end_row}"
    #     return range

    # def add_background_color(self, ws, additional_style):
    #     for style in additional_style:
    #         min_row = style.get("min_row")
    #         max_row = style.get("max_row")
    #         min_col = style.get("min_col")
    #         max_col = style.get("max_col")
    #         bg_color = style.get("bg_color")

    #         for row in ws.iter_rows(
    #             min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col
    #         ):
    #             for cell in row:
    #                 self.apply_format(ws, cell=cell, bg_color=bg_color, update=True)

    #         if style.get("move_range"):
    #             move_col = style.get("move_col")
    #             range = self.get_range(min_row, min_col, max_row, max_col)
    #             print(range)
    #             ws.move_range(range, rows=0, cols=move_col)
