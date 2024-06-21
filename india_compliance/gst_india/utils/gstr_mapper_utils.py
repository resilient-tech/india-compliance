from frappe.utils import flt


class GSTRDataMapper:
    def convert_to_internal_data_format(self, gov_data):
        """
        Converts Gov data format to internal data format for all categories
        """
        output = {}

        for category, mapper_class in self.CLASS_MAP.items():
            if not gov_data.get(category):
                continue

            output.update(
                mapper_class().convert_to_internal_data_format(gov_data.get(category))
            )

        return output

    def get_category_wise_data(
        self,
        subcategory_wise_data: dict,
    ) -> dict:
        """
        returns category wise data from subcategory wise data

        Args:
            subcategory_wise_data (dict): subcategory wise data
            mapping (dict): subcategory to category mapping
            with_subcategory (bool): include subcategory level data

        Returns:
            dict: category wise data

        Example (with_subcategory=True):
            {
                "B2B, SEZ, DE": {
                    "B2B": data,
                    ...
                }
                ...
            }

        Example (with_subcategory=False):
            {
                "B2B, SEZ, DE": data,
                ...
            }
        """
        category_wise_data = {}
        for subcategory, category in self.mapping.items():
            if not subcategory_wise_data.get(subcategory.value):
                continue

            category_wise_data.setdefault(category.value, []).extend(
                subcategory_wise_data.get(subcategory.value, [])
            )

        return category_wise_data

    def convert_to_gov_data_format(
        self, internal_data: dict, company_gstin: str
    ) -> dict:
        """
        converts internal data format to Gov data format for all categories
        """

        output = {}
        for category, mapper_class in self.CLASS_MAP.items():
            if not internal_data.get(category):
                continue

            output[category] = mapper_class().convert_to_gov_data_format(
                internal_data.get(category), company_gstin=company_gstin
            )

        return output

    def summarize_retsum_data(
        self,
        input_data,
    ):
        if not input_data:
            return []

        summarized_data = []
        total_values_keys = [
            "total_igst_amount",
            "total_cgst_amount",
            "total_sgst_amount",
            "total_cess_amount",
            "total_taxable_value",
        ]
        amended_data = {key: 0 for key in total_values_keys}

        input_data = {row.get("description"): row for row in input_data}

        def _sum(row):
            return flt(sum([row.get(key, 0) for key in total_values_keys]), 2)

        for category, sub_categories in self.category_sub_category_mapping.items():
            category = category.value
            if category not in input_data:
                continue

            # compute total liability and total amended data
            amended_category_data = input_data.get(f"{category} (Amended)", {})
            for key in total_values_keys:
                amended_data[key] += amended_category_data.get(key, 0)

            # add category data
            if _sum(input_data[category]) == 0:
                continue

            summarized_data.append({**input_data.get(category), "indent": 0})

            # add subcategory data
            for sub_category in sub_categories:
                sub_category = sub_category.value
                if sub_category not in input_data:
                    continue

                if _sum(input_data[sub_category]) == 0:
                    continue

                summarized_data.append(
                    {
                        **input_data.get(sub_category),
                        "indent": 1,
                        "consider_in_total_taxable_value": (
                            False
                            if sub_category
                            in self.subcategory_not_considered_in_total_taxable_value
                            else True
                        ),
                        "consider_in_total_tax": (
                            False
                            if sub_category
                            in self.subcategory_not_considered_in_total_tax
                            else True
                        ),
                    }
                )

        # add total amendment liability
        if _sum(amended_data) != 0:
            summarized_data.extend(
                [
                    {
                        "description": "Net Liability from Amendments",
                        **amended_data,
                        "indent": 0,
                        "consider_in_total_taxable_value": True,
                        "consider_in_total_tax": True,
                        "no_of_records": 0,
                    }
                ]
            )

        return summarized_data
