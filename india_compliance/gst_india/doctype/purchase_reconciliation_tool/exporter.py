import openpyxl

# from openpyxl.formatting.rule import Rule
from openpyxl.styles import Alignment, Font, PatternFill

# from openpyxl.styles.differential import DifferentialStyle
from openpyxl.utils import get_column_letter


class ExcelExporter:
    def __init__(self):
        pass

    def get_workbook(self, workbook=None):
        if not workbook:
            workbook = openpyxl.Workbook()

        return workbook

    def make_xlsx(self, *args, **kwargs):
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
        self.column_dimension = 1

    def create_worksheet(
        self,
        workbook,
        sheet_name,
        data,
        headers,
        filters=None,
        merged_headers=None,
    ):
        """Create worksheet"""
        self.headers = headers
        self.data = data

        ws = workbook.create_sheet(sheet_name)

        if filters:
            self.filters = filters
            self.add_data(ws, self.filters)

        if merged_headers:
            self.merged_headers = merged_headers
            self.add_data(ws, self.merged_headers, merge=True)

        self.add_data(ws, self.headers, is_header=True)
        self.add_data(ws, self.data)

        return ws

    def add_data(self, ws, data, is_header=False, merge=False):
        """Adds header data to the sheet"""
        parsed_data = self.parse_data(data, is_header)

        for i, row in enumerate(parsed_data, 1):
            for j, val in enumerate(row):
                cell = ws.cell(row=self.row_dimension, column=j + 1)

                if merge:
                    self.append_merged_header(ws)
                else:
                    self.get_properties(column=j)
                    self.apply_style(
                        ws,
                        self.row_dimension,
                        j + 1,
                        font_size=self.font_size,
                        bold=self.bold,
                        horizontal_align=self.align_header,
                        width=self.width,
                        bg_color=self.bg_color,
                        format=self.format,
                    )
                    cell.value = val
            self.row_dimension += 1
        return ws

    def append_merged_header(self, ws):
        for key, value in self.merged_headers.items():
            start_column = self.get_column_index(value[0])
            end_column = self.get_column_index(value[1])

            range = self.get_range(
                start_row=self.row_dimension,
                start_column=start_column,
                end_row=self.row_dimension,
                end_column=end_column,
            )

            ws.cell(row=self.row_dimension, column=start_column).value = key
            ws.merge_cells(range)
            self.apply_style(ws, self.row_dimension, start_column)

    def get_column_index(self, column_name):
        """Get column index from column name"""
        for (idx, field) in enumerate(self.headers, 1):
            if field["fieldname"] == column_name:
                return idx

    def apply_style(
        self,
        ws,
        row,
        column,
        font_family="Calibri",
        font_size=9,
        bold=True,
        horizontal_align="general",
        vertical_align="bottom",
        width=20,
        bg_color=None,
        border=None,
        format=None,
    ):
        """Apply style to cell"""
        cell = ws.cell(row=row, column=column)
        cell.font = Font(
            name=font_family,
            size=font_size,
            bold=bold,
        )
        cell.alignment = Alignment(
            horizontal=horizontal_align,
            vertical=vertical_align,
        )
        cell.number_format = format if format else "General"

        if bg_color:
            cell.fill = PatternFill(
                fill_type="solid",
                fgColor=bg_color,
            )
        ws.column_dimensions[get_column_letter(column)].width = width

    def get_properties(self, column=None):
        """Get all properties defined in a header for cell"""
        if not column:
            column = self.column_dimension

        properties = self.headers[column]

        self.bg_color = properties.get("bg_color")
        self.font_family = properties.get("font_family")
        self.font_size = properties.get("font_size")
        self.bold = properties.get("bold")
        self.align_header = properties.get("align_header")
        self.align_data = properties.get("align_data")
        self.format = properties.get("format")
        self.width = properties.get("width") or 20
        self.height = properties.get("height")

    def parse_data(self, data, is_header=False):
        """Convert data to List of Lists"""
        csv_list = []

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, list):
                    csv_list.append(list(data.keys()))
                    return csv_list
                else:
                    csv_list.append([key, value])

        if isinstance(data, list):
            if is_header:
                csv_list.append(self.build_csv_header(data))
            else:
                csv_list = self.build_csv_array(data)
        return csv_list

    def build_csv_array(self, data):
        """Builds a csv data array"""
        csv_array = []

        for row in data:
            csv_array.append(list(row.values()))

        return csv_array

    def build_csv_header(self, row):
        """Builds a csv row"""
        csv_row = []

        for data in row:
            csv_row.append(data.get("label"))
        return csv_row

    def get_range(self, start_row, start_column, end_row, end_column):
        start_column_letter = get_column_letter(start_column)
        end_column_letter = get_column_letter(end_column)

        range = f"{start_column_letter}{start_row}:{end_column_letter}{end_row}"

        return range
