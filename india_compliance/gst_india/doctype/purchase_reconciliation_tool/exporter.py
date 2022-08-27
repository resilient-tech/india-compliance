from io import BytesIO

import openpyxl
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import frappe


class ExcelExporter:
    def __init__(self):
        self.wb = openpyxl.Workbook()

    def create_sheet(self, **kwargs):
        """
        create worksheet
        :param sheet_name - name for the worksheet
        :param filters - A data dictionary to added in sheet
        :param merged_headers - A dict of List
            @example: {
                'label': [column1, colum2]
            }
        :param headers: A List of dictionary (cell properties will be optional)
        :param data: A list of dictionary to append data to sheet
        """

        Worksheet().create(workbook=self.wb, **kwargs)

    def save_workbook(self, file_name=None):
        """Save workbook"""
        if file_name:
            self.wb.save(file_name)
            return self.wb

        xlsx_file = BytesIO()
        self.wb.save(xlsx_file)
        return xlsx_file

    def remove_sheet(self, sheet_name):
        """Remove worksheet"""
        if sheet_name in self.wb.sheetnames:
            self.wb.remove(self.wb[sheet_name])

    def export(self, file_name):
        # write out response as a xlsx type
        if file_name[-4:] != ".xlsx":
            file_name = f"{file_name}.xlsx"

        xlsx_file = self.save_workbook()

        frappe.local.response["filename"] = file_name
        frappe.local.response["filecontent"] = xlsx_file.getvalue()
        frappe.local.response["type"] = "binary"


class Worksheet:
    data_format = frappe._dict(
        {
            "font_family": "Calibri",
            "font_size": 9,
            "bold": True,
            "horizontal": "general",
            "number_format": "General",
            "width": 20,
            "height": 20,
            "vertical": "center",
            "wrap_text": False,
            "bg_color": "f2f2f2",
        }
    )

    header_format = frappe._dict(
        {
            "font_family": "Calibri",
            "font_size": 9,
            "bold": True,
            "horizontal": "center",
            "width": 20,
            "height": 30,
            "vertical": "center",
            "wrap_text": True,
            "bg_color": "d9d9d9",
        }
    )

    def __init__(self):
        self.row_dimension = 1
        self.column_dimension = 1

    def create(
        self,
        workbook,
        sheet_name,
        headers,
        data,
        filters=None,
        merged_headers=None,
        add_totals=True,
    ):
        """Create worksheet"""
        self.headers = headers

        self.ws = workbook.create_sheet(sheet_name)
        self.add_data(filters)
        self.add_merged_header(merged_headers)
        self.add_data(headers, is_header=True)
        self.add_data(data, is_data=True)

        if add_totals:
            self.add_total_row()

        self.apply_conditional_formatting()

    def add_merged_header(self, merged_headers):
        if not merged_headers:
            return

        for key, value in merged_headers.items():
            merge_from_idx = self.get_column_index(value[0])
            merge_to_idx = self.get_column_index(value[1])

            range = self.get_range(
                start_row=self.row_dimension,
                start_column=merge_from_idx,
                end_row=self.row_dimension,
                end_column=merge_to_idx,
            )

            self.ws.cell(row=self.row_dimension, column=merge_from_idx).value = key

            self.ws.merge_cells(range)

            self.apply_format(
                row=self.row_dimension,
                column=merge_from_idx,
                index=merge_from_idx,
                is_header=True,
            )

        self.row_dimension += 1

    def add_data(self, data, is_header=False, is_data=False, is_total=False):
        if not data:
            return

        if is_data:
            self.data_row = self.row_dimension

        parsed_data = self.parse_data(data, is_header)

        for row in parsed_data:
            for j, val in enumerate(row, 1):
                cell = self.ws.cell(row=self.row_dimension, column=j)
                self.apply_format(
                    row=self.row_dimension,
                    column=j,
                    index=j - 1,
                    is_header=is_header,
                    is_data=is_data,
                    is_total=is_total,
                )
                cell.value = val

            self.row_dimension += 1

    def add_total_row(self):
        """Add total row to the sheet"""

        total_row = self.get_totals()

        self.add_data(total_row, is_header=True, is_total=True)

    def apply_format(
        self, row, column, index, is_header=False, is_data=False, is_total=False
    ):
        """Get style if defined or apply default format to the cell"""

        style = self.data_format

        if is_header:
            style = self.get_header_style(index)
            if is_total:
                style.update({"horizontal": "general", "height": 20})
        elif is_data:
            style = self.get_data_style(index)
            style.update({"bold": False})
        else:
            style.update(
                {
                    "bg_color": None,
                }
            )
        self.apply_style(row, column, style)

    def get_totals(self):
        """build total row array of fields to be calculated"""
        total_row = []

        for idx, property in enumerate(self.headers, 1):
            if idx == 1:
                total_row.append("Totals")
            elif property.get("fieldtype") in ("Float", "Int"):
                range = self.get_range(self.data_row, idx, self.ws.max_row, idx)
                total_row.append(f"=SUM({range})")
            else:
                total_row.append("")

        return total_row

    def get_header_style(self, index):
        properties = self.headers[index]

        header_style = self.header_format.copy()

        if header_format := properties.get("header_format"):
            header_style.update(header_format)

        return header_style

    def get_data_style(self, index):
        properties = self.headers[index]

        data_style = self.data_format.copy()

        if data_format := properties.get("data_format"):
            data_style.update(data_format)

        return data_style

    def apply_style(self, row, column, style):
        """Apply style to cell"""

        cell = self.ws.cell(row=row, column=column)
        cell.font = Font(
            name=style.get("font_family"),
            size=style.get("font_size"),
            bold=style.get("bold"),
        )
        cell.alignment = Alignment(
            horizontal=style.get("horizontal"),
            vertical=style.get("vertical"),
            wrap_text=style.get("wrap_text"),
        )
        cell.number_format = style.get("number_format") or "General"

        if style.get("bg_color"):
            cell.fill = PatternFill(
                fill_type="solid",
                fgColor=style.get("bg_color"),
            )

        self.ws.column_dimensions[get_column_letter(column)].width = style.get("width")
        self.ws.row_dimensions[row].height = style.get("height")

    def apply_conditional_formatting(self):
        """Apply conditional formatting to cell"""

        for i, row in enumerate(self.headers, 1):
            if "formula" not in row.get("data_format"):
                continue

            formula = row.get("data_format").get("formula")
            compare_field = row.get("data_format").get("compare_field")

            start_column = self.get_column_index(row["fieldname"])
            end_column = self.get_column_index(compare_field) or self.ws.max_column

            range = self.get_range(
                start_row=self.data_row,
                start_column=start_column,
                end_row=self.ws.max_row,
                end_column=end_column - 1,
            )

            self.ws.conditional_formatting.add(
                range,
                FormulaRule(
                    formula=[formula],
                    stopIfTrue=True,
                    font=Font(
                        name=self.data_format.get("font_family"),
                        size=self.data_format.get("font_size"),
                        bold=True,
                        color="FF0000",
                    ),
                ),
            )

    def parse_data(self, data, is_header=False):
        """Convert data to List of Lists"""
        csv_list = []

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, list):
                    # To get keys from Merged headers having keys and list of columns to merge
                    csv_list.append(list(data.keys()))
                    return csv_list
                else:
                    # To get filters value key as Label and it's value
                    csv_list.append([key, value])

        if isinstance(data, list):
            # For Headers and Data
            csv_list = self.build_csv_array(data, is_header)

        return csv_list

    def build_csv_array(self, data, is_header=False):
        """Builds a csv data array"""
        csv_array = []
        csv_row = []

        for row in data:
            if isinstance(row, dict):
                if is_header:
                    # Fetch label from list of dict from headers
                    csv_row.append(row.get("label"))
                else:
                    # Fetch only values from list of dictionary
                    csv_array.append(list(row.values()))
            else:
                # If it's a single list with element only
                csv_array.append(data)
                break

        # Only append to csv_array if csv_row has multiple values
        if len(csv_row) >= 1:
            csv_array.append(csv_row)

        return csv_array

    def get_range(self, start_row, start_column, end_row, end_column, freeze=False):
        start_column_letter = get_column_letter(start_column)
        end_column_letter = get_column_letter(end_column)

        if freeze:
            return f"${start_column_letter}${start_row}:${end_column_letter}${end_row}"

        return f"{start_column_letter}{start_row}:{end_column_letter}{end_row}"

    def get_column_index(self, column_name):
        """Get column index from column name"""
        for (idx, field) in enumerate(self.headers, 1):
            if field["fieldname"] == column_name:
                return idx
