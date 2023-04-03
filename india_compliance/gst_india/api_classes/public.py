from india_compliance.gst_india.api_classes.base import BaseAPI


class PublicAPI(BaseAPI):
    API_NAME = "GST Public"
    BASE_PATH = "commonapi"

    def get_gstin_info(self, gstin):
        response = self.get("search", params={"action": "TP", "gstin": gstin})
        if self.sandbox_mode:
            response.update(
                {
                    "tradeNam": "Resilient Tech",
                    "lgnm": "Resilient Tech",
                }
            )

        return response
