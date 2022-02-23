from india_compliance.gst_india.utils import get_place_of_supply

def set_place_of_supply(doc, method=None):
	doc.place_of_supply = get_place_of_supply(doc, doc.doctype)
