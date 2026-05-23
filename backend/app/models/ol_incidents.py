"""
Read-only ORM mapping for the OL_INCIDENTS table in vedanta (SQL Server).

All date columns (OCCUREDDATE, REPORTEDDATE, etc.) are stored as VARCHAR in the
source table; comparisons use YEAR (int) and MONTH (int) which are typed correctly.
YEAR is also stored as VARCHAR — cast to Integer when doing numeric comparisons.
"""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase


class SSMSBase(DeclarativeBase):
    pass


class OLIncident(SSMSBase):
    __tablename__ = "OL_INCIDENTS"

    # Only INCROWID is used as the ORM identity — the source table has no PK
    # constraint, but SQLAlchemy needs one for session tracking.
    INCROWID = Column(Integer, primary_key=True)

    VNAME = Column(String)
    BUNAME = Column(String)
    SINAME = Column(String)
    PRIORITY = Column(String)
    STATUS = Column(String)
    INCIDENTTYPENAME = Column(String)
    INCIDENTCATNAME = Column(String)
    INCIDENTTITLE = Column(String)
    INCIDENTDETAILS = Column(String)

    # Dates are stored as VARCHAR "YYYY-MM-DD"
    OCCUREDDATE = Column(String)
    OCCUREDTIME = Column(String)
    REPORTEDDATE = Column(String)
    REPORTEDTIME = Column(String)
    LASTUPDATEDDATE = Column(String)
    LASTUPDATEDTIME = Column(String)

    MONTH = Column(Integer)         # properly typed int
    QUARTER = Column(String)        # "Q1" … "Q4"
    YEAR = Column(String)           # stored as varchar — cast when comparing numerically

    LNAME = Column(String)
    LEVELNAME = Column(String)      # "Low" / "Medium" / "High"
    ZNAME = Column(String)
    INCIDENTID = Column(Integer)
    REPORTEDBY = Column(String)
    INCIDENTTYPENAME_DISPLAY = Column(String)
    INCIDENTCATNAME_DISPLAY = Column(String)
    INCIDENTCOUNT = Column(Integer)
    MONTHNAME = Column(String)
    VCODE = Column(String)
    BUCODE = Column(String)
    SICODE = Column(String)
    DSRDATE = Column(String)
