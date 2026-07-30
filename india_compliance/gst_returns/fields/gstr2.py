"""GSTR-2A/2B/IMS categories. Raw/Doc/Item fields are raw literals in mappers, extracted in PR-6."""

from enum import Enum


class Category(Enum):
    B2B = "B2B"
    B2BA = "B2BA"
    CDNR = "CDNR"
    CDNRA = "CDNRA"
    ISD = "ISD"
    ISDA = "ISDA"  # 2B only
    IMPG = "IMPG"
    IMPGSEZ = "IMPGSEZ"

    # IMS
    B2BCN = "B2BCN"
    B2BCNA = "B2BCNA"
    B2BDN = "B2BDN"
    B2BDNA = "B2BDNA"

    # 2A only
    ECOM = "ECOM"
    ECOMA = "ECOMA"
    TDS = "TDS"
    TCS = "TCS"
