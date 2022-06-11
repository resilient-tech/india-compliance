from india_compliance.gst_india.api_classes.base import BaseAPI


class PublicAPI(BaseAPI):
    def setup(self):
        self.api_name = "GST Public"
        self.base_path = "commonapi"

    def get_gstin_info(self, gstin):
        return self.get("search", params={"action": "TP", "gstin": gstin})
