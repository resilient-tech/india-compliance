from india_compliance.gst_india.api_classes.base import BaseAPI


class PublicAPI(BaseAPI):
    API_NAME = "GST Public"
    BASE_PATH = "commonapi"

    def get_gstin_info(self, gstin):
        return self.get("search", params={"action": "TP", "gstin": gstin})
