"""Credit and debit notes from registered suppliers. An invoice in every way but the number,
type and date, so the b2b details do the base work."""

from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import GST_CATEGORY, add_original_details
from india_compliance.gst_returns.fields.gstr2 import NOTE_TYPE
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.fields.gstr2 import RawField2a as raw2a
from india_compliance.gst_returns.fields.gstr2 import RawField2b as raw2b
from india_compliance.gst_returns.steps import decode, take

from . import b2b

NOTE_KEYS_2A = {
    raw2a.NOTE_NUMBER: doc.BILL_NO,
    raw2a.NOTE_TYPE: doc.DOC_TYPE,
    raw2a.NOTE_DATE: doc.BILL_DATE,
}

ORIGINAL_KEYS_2A = {
    raw2a.ORIGINAL_NOTE_NUMBER: doc.ORIGINAL_BILL_NO,
    raw2a.ORIGINAL_NOTE_DATE: doc.ORIGINAL_BILL_DATE,
}


def get_note_details_2a(note, gstr):
    details = b2b.get_invoice_details_2a(note, gstr)
    details.update(take(note, NOTE_KEYS_2A))
    decode(details, doc.DOC_TYPE, NOTE_TYPE)
    details[doc.BILL_DATE] = parse_datetime(details[doc.BILL_DATE], day_first=True)

    return details


def get_amended_note_details_2a(note, gstr):
    details = add_original_details(get_note_details_2a(note, gstr), note, ORIGINAL_KEYS_2A)
    details[doc.ORIGINAL_DOC_TYPE] = NOTE_TYPE.get(note.get(raw2a.NOTE_TYPE))

    return details


# "typ" carries the note type here; the supply type moves to "suptyp"
NOTE_KEYS_2B = {
    raw2b.NOTE_NUMBER: doc.BILL_NO,
    raw2b.INVOICE_TYPE: doc.DOC_TYPE,
    raw2b.SUPPLY_TYPE: doc.SUPPLY_TYPE,
}

ORIGINAL_KEYS_2B = {
    raw2b.ORIGINAL_NOTE_NUMBER: doc.ORIGINAL_BILL_NO,
    raw2b.ORIGINAL_NOTE_DATE: doc.ORIGINAL_BILL_DATE,
    raw2b.ORIGINAL_NOTE_TYPE: doc.ORIGINAL_DOC_TYPE,
}


def get_note_details_2b(note, gstr):
    details = b2b.get_invoice_details_2b(note, gstr)
    details.update(take(note, NOTE_KEYS_2B))
    decode(details, doc.DOC_TYPE, NOTE_TYPE)
    decode(details, doc.SUPPLY_TYPE, GST_CATEGORY)

    return details


def get_amended_note_details_2b(note, gstr):
    details = add_original_details(get_note_details_2b(note, gstr), note, ORIGINAL_KEYS_2B)
    decode(details, doc.ORIGINAL_DOC_TYPE, NOTE_TYPE)

    return details
