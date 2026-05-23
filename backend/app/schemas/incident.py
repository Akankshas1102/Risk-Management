from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class IncidentRaw(BaseModel):
    """Direct mapping of one CSV row — types reflect what pandas reads off disk."""

    INCROWID: int
    VNAME: str
    BUNAME: str
    SINAME: Optional[str] = None          # 1 null in dataset
    PRIORITY: str                          # constant "LOW" — kept for schema fidelity
    STATUS: str
    INCIDENTTYPENAME: str
    INCIDENTCATNAME: str
    INCIDENTTITLE: str
    INCIDENTDETAILS: Optional[str] = None  # 2 nulls
    OCCUREDDATE: str                       # "YYYY-MM-DD" strings in source
    OCCUREDTIME: Optional[str] = None      # 10 nulls
    REPORTEDDATE: str
    REPORTEDTIME: Optional[str] = None     # 10 nulls
    LASTUPDATEDDATE: str
    LASTUPDATEDTIME: str
    MONTH: int
    QUARTER: str                           # "Q1" … "Q4"
    YEAR: int
    LNAME: str
    LEVELNAME: str                         # Low / Medium / High / edge cases
    ZNAME: Optional[str] = None           # 1 null
    INCIDENTID: int
    REPORTEDBY: str
    INCIDENTTYPENAME_DISPLAY: str
    INCIDENTCATNAME_DISPLAY: str
    INCIDENTCOUNT: int
    MONTHNAME: str
    VCODE: str
    BUCODE: str
    SICODE: Optional[str] = None          # 1 null
    DSRDATE: Optional[str] = None         # ~33% null


# Canonical severity ordering used downstream
SEVERITY_ORDER = ("low", "medium", "high", "major", "minor", "unknown")


class IncidentClean(BaseModel):
    """
    Cleaned, typed representation of an incident.

    Transformations applied vs IncidentRaw:
    - PRIORITY dropped (constant column)
    - All three date columns parsed to `date`
    - LEVELNAME → severity (normalised string)
    - SINAME → site_name (stripped / upper-cased; real mapping injected later)
    - reporting_lag_days derived from reported - occurred dates
    - is_partial_period flagged for the current incomplete quarter
    """

    incrow_id: int
    incident_id: int
    vname: str
    vcode: str
    buname: str
    bucode: str
    site_name: str                         # normalised SINAME
    sicode: Optional[str] = None
    status: str
    incident_type: str                     # INCIDENTTYPENAME
    incident_type_display: str             # INCIDENTTYPENAME_DISPLAY
    incident_category: str                 # INCIDENTCATNAME
    incident_category_display: str         # INCIDENTCATNAME_DISPLAY
    incident_title: str
    incident_details: Optional[str] = None
    occurred_date: date
    occurred_time: Optional[str] = None
    reported_date: date
    reported_time: Optional[str] = None
    last_updated_date: date
    month: int
    month_name: str
    quarter: str
    year: int
    severity: str = Field(
        description="Normalised from LEVELNAME: low | medium | high | major | minor | unknown"
    )
    lname: str
    zone: Optional[str] = None            # ZNAME
    reported_by: str
    incident_count: int
    dsr_date: Optional[date] = None
    reporting_lag_days: int               # reported_date - occurred_date in days
    is_partial_period: bool               # True when quarter has not yet closed
