"""Synthetic São Paulo ITBI workbook (real header and sheet layout, invented rows). Never loaded
into the operational database."""

import io
from datetime import datetime

import openpyxl

HEADER = [
    "Nº do Cadastro (SQL)", "Nome do Logradouro", "Número", "Complemento", "Bairro",
    "Referência", "CEP", "Natureza de Transação",
    "Valor de Transação (declarado pelo contribuinte)", "Data de Transação",
    "Valor Venal de Referência", "Proporção Transmitida (%)",
    "Valor Venal de Referência (proporcional)", "Base de Cálculo adotada",
    "Tipo de Financiamento", "Valor Financiado", "Cartório de Registro", "Matrícula do Imóvel",
    "Situação do SQL", "Área do Terreno (m2)", "Testada (m)", "Fração Ideal",
    "Área Construída (m2)", "Uso (IPTU)", "Descrição do uso (IPTU)", "Padrão (IPTU)",
    "Descrição do padrão (IPTU)", "ACC (IPTU)",
]  # fmt: skip


def row(sql, street, number, compl, bairro, cep, nature, value, when, share, fraction, land,
        built, use, use_desc):  # fmt: skip
    return [
        sql, street, number, compl, bairro, None, cep, nature, value, when, 100000, share,
        100000 * share / 100, value, None, 0, "1º Cartório de Registro de Imóvel", 1234,
        "Ativo Predial", land, 10, fraction, built, use, use_desc, 20, "RESIDENCIAL VERTICAL", 2000,
    ]  # fmt: skip


APT = "APARTAMENTO EM CONDOMÍNIO (EXIGE FRAÇÃO IDEAL)"
ROWS = [
    # Whole condo unit, sold twice (same SQL, different complement spelling).
    row(1234567890, "R EXEMPLO", 10, "AP 12 E 1VG", "VILA TESTE", 1234000, "1.Compra e venda",
        500000, datetime(2025, 3, 1), 100, 0.02, 2000, 80, 20, APT),
    row(1234567890, "R EXEMPLO", 10, "AP 12", None, 1234000, "1.Compra e venda",
        650000.5, datetime(2026, 1, 15), 100, 0.02, 2000, 80, 20, APT),
    # Off-plan units declared as a fraction of the plot's SQL: unit is part of the identity.
    row(9876543210, "AV MODELO", 500, "AP 101 TORRE A", None, 4500100, "1.Compra e venda",
        400000, datetime(2026, 2, 1), 0.01, 1, 5000, 0, 0, "TERRENO"),
    row(9876543210, "AV MODELO", 500, "AP 102 TORRE A", None, 4500100, "1.Compra e venda",
        410000, datetime(2026, 2, 1), 0.01, 1, 5000, 0, 0, "TERRENO"),
    # A house (not in a condominium): land area is the house's plot.
    row(5550001112, "R FICTICIA", 7, None, "JD AMOSTRA", 5500000, "1.Compra e venda",
        900000, datetime(2026, 2, 10), 100, 1, 250, 180, 10, "RESIDÊNCIA"),
    # Capital contribution: transacted value, not a market sale.
    row(5550001112, "R FICTICIA", 7, None, "JD AMOSTRA", 5500000,
        "20.Realização ou integralização de capital ", 300000, datetime(2026, 3, 1), 100, 1, 250,
        180, 10, "RESIDÊNCIA"),
]  # fmt: skip
# Shifted row as seen in the real file (split complement + a party name): must be skipped.
MALFORMED = [4200800000, "R DESLOCADA", 1, "AP", " 25 - T1", "VL X", None, 4021050,
             "EMPRESA FICTICIA LTDA", "2-Escritura", 46062, 9679471, 3.63]  # fmt: skip


def itbi_xlsx(rows=ROWS, header=HEADER, extra_rows=()) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "JAN-2026"
    sheet.append(header)
    for r in [*rows, *extra_rows]:
        sheet.append(r)
    legend = workbook.create_sheet("LEGENDA")
    legend.append([None, "LEGENDA"])
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


INDEX_HTML = """<p>os arquivos (em formatos Excel/xlsx e ODS):</p>
<p>2026 (<a href="https://example.test/itbi/GUIAS%20(30092026).xlsx" target="_blank">Excel/xlsx</a>)
(<a href="https://example.test/itbi/GUIAS%20(30092026).ods">ODS</a>)</p>
<p><strong>2025</strong> (<a href="https://example.test/itbi/GUIAS DE ITBI 2025 XLS.xlsx">
<span>Excel/xlsx</span></a>) (<a href="https://example.test/itbi/2025.ods">ODS</a>)</p>
<p>2024 (<a href="https://example.test/itbi/GUIAS-2024.xlsx">Excel/xlsx</a>)</p>
<p>2023 (<a href="https://example.test/itbi/GUIAS-2023.xlsx">Excel/xlsx</a>)</p>
<p>2022 (<a href="https://example.test/itbi/GUIAS-2022.xlsx">Excel/xlsx</a>)</p>
<p>2021 (<a href="https://example.test/itbi/GUIAS-2021.xlsx">Excel/xlsx</a>)</p>
"""
