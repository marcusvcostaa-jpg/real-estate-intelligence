"""Synthetic PPR-format data (real header/encoding, invented rows). Never loaded into the
operational database."""

import io
import zipfile

HEADER = (
    '"Date of Sale (dd/mm/yyyy)","Address","County","Eircode","Price (€)",'
    '"Not Full Market Price","VAT Exclusive","Description of Property",'
    '"Property Size Description"'
)
ROWS = [
    '"03/01/2024","1 Example Road, Dublin 8","Dublin","D08 XY12","€450,000.00","No","No",'
    '"Second-Hand Dwelling house /Apartment",""',
    '"05/02/2024","Apt 4, Sample Court, Dublin 2","Dublin","","€310,500.00","Yes","Yes",'
    '"New Dwelling house /Apartment","greater than or equal to 38 sq metres and less than '
    '125 sq metres"',
    # Two identical rows: units sold together. Both must be kept.
    '"10/03/2024","Unit 1, Test Quay, Dublin 1","Dublin","","€250,000.00","No","Yes",'
    '"New Dwelling house /Apartment",""',
    '"10/03/2024","Unit 1, Test Quay, Dublin 1","Dublin","","€250,000.00","No","Yes",'
    '"New Dwelling house /Apartment",""',
    '"11/03/2024","2 Placeholder Lane, Cork","Cork","","€200,000.00","No","No",'
    '"Second-Hand Dwelling house /Apartment",""',
]
CSV_TEXT = "\r\n".join([HEADER, *ROWS]) + "\r\n"


def ppr_zip(csv_text: str = CSV_TEXT) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("PPR-ALL.csv", csv_text.encode("cp1252"))
    return buf.getvalue()
