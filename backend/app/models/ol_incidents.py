"""
ORM mapping for the ol_incidents table in PostgreSQL (vedanta_risk).

Data source: data/raw/OL_INCIDENTS_20260518_142042.csv loaded via
scripts/load_csv_to_db.py.  The table is read-only — this app never writes
to ol_incidents.

Column names in Postgres are lowercase (standard convention). Python attributes
are uppercase to preserve compatibility with existing API + ML code that
references OLIncident.SINAME, OLIncident.BUNAME, etc.
"""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class OLIncident(Base):
    __tablename__ = "ol_incidents"

    # Explicit column name mapping: Python attribute (uppercase) → Postgres column (lowercase)
    INCROWID = Column("incrowid", Integer, primary_key=True)

    VNAME     = Column("vname",     String)
    BUNAME    = Column("buname",    String)
    SINAME    = Column("siname",    String)
    PRIORITY  = Column("priority",  String)
    STATUS    = Column("status",    String)

    INCIDENTTYPENAME = Column("incidenttypename", String)
    INCIDENTCATNAME  = Column("incidentcatname",  String)
    INCIDENTTITLE    = Column("incidenttitle",    String)
    INCIDENTDETAILS  = Column("incidentdetails",  String)

    # Dates stored as VARCHAR "YYYY-MM-DD"
    OCCUREDDATE    = Column("occureddate",    String)
    OCCUREDTIME    = Column("occuredtime",    String)
    REPORTEDDATE   = Column("reporteddate",   String)
    REPORTEDTIME   = Column("reportedtime",   String)
    LASTUPDATEDDATE = Column("lastupdateddate", String)
    LASTUPDATEDTIME = Column("lastupdatedtime", String)

    MONTH   = Column("month",   Integer)   # 1–12
    QUARTER = Column("quarter", String)    # "Q1"…"Q4"
    YEAR    = Column("year",    String)    # stored as varchar e.g. "2024"

    LNAME    = Column("lname",    String)
    LEVELNAME = Column("levelname", String)   # "Low" / "Medium" / "High"
    ZNAME    = Column("zname",    String)
    INCIDENTID = Column("incidentid", Integer)
    REPORTEDBY = Column("reportedby", String)

    INCIDENTTYPENAME_DISPLAY = Column("incidenttypename_display", String)
    INCIDENTCATNAME_DISPLAY  = Column("incidentcatname_display",  String)
    INCIDENTCOUNT = Column("incidentcount", Integer)
    MONTHNAME     = Column("monthname",     String)
    VCODE  = Column("vcode",  String)
    BUCODE = Column("bucode", String)
    SICODE = Column("sicode", String)
    DSRDATE = Column("dsrdate", String)
