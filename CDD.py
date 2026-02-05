import requests
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table, no_update
from dash.dependencies import Input, Output, State
import pandas as pd

import os
import io
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


API_KEY = "DVzlum5eSDKjelf2"
code_file = "code.txt"

indicator_names = {}
with open(code_file, encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) == 2:
            code, name = parts
            indicator_names[code] = name

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.FLATLY,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css",
    ],
    suppress_callback_exceptions=True
)
server = app.server

app.layout = dbc.Container([
    html.H1("Безопасность сделки — легко", className="text-center my-4"),
    html.H4("test 7721546864", className="text-center my-4"),

    dbc.InputGroup([
        dbc.InputGroupText("Введите ИНН:"),
        dbc.Input(id="inn-input", type="text", placeholder="10 цифр"),
        dbc.Button("Загрузить", id="load-button", n_clicks=0, color="primary")
    ], className="mb-4"),

    html.Div(id="company-info"),

    dcc.Store(id="report-store"),
    dcc.Download(id="download-company-pdf"),

    dbc.Row([
        dbc.Col(
            html.Div(id="ratios-output"),
            width=4,
            className="ps-2"
        ),

        dbc.Col(
            dash_table.DataTable(
                id="finance-table",
                columns=[],
                data=[],
                fixed_columns={'headers': True, 'data': 1},
                style_table={"overflowX": "auto", "minWidth": "100%"},
                style_cell={"textAlign": "center", "padding": "6px", "fontFamily": "Arial, sans-serif"},
                style_data={"whiteSpace": "normal", "height": "auto", "lineHeight": "15px"},
                style_cell_conditional=[
                    {
                        "if": {"column_id": "Показатель"},
                        "textAlign": "left",
                        "width": "300px",
                        "maxWidth": "300px",
                        "whiteSpace": "normal",
                        "height": "auto",
                    }
                ],
                css=[
                    {
                        "selector": ".dash-spreadsheet td div",
                        "rule": "white-space: inherit; overflow: hidden; text-overflow: ellipsis;"
                    }
                ],
                style_header={"backgroundColor": "#e1e1e1", "fontWeight": "bold"}
            ),
            width=8,
            className="pe-2"
        )
    ], className="mt-4"),

    html.Div(id="selected-inn", className="mt-3 text-center fw-bold")
], fluid=True)

RATIO_FORMULAS = {
    "Коэффициент финансовой устойчивости":"Доля стабильных источников финансирования активов \n(1300 + 1400) / 1700",
    "Коэффициент автономии":"Степень независимости компании от заемного капитала \n1300 / 1600",
    "Коэффициент обеспеченности собственными средствами":"Степень покрытия оборотных активов собственными ресурсами \n(1300 - 1100) / 1200",
    "Отношение дебиторской задолженности к активам":"Доля средств, отвлеченных в расчеты \n1230 / 1600",
    "Коэффициент соотношения заемного и собственного капитала":"Степень финансовой зависимости предприятия \n(1410 + 1510) / 1300",
    "Коэффициент абсолютной ликвидности":"Степень способности погашать краткосрочные обязательства \n(1250 + 1240) / 1500",
    "Коэффициент текущей ликвидности":"Степень достаточности оборотных активов для расчетов \n1200 / 1500",
    "Коэффициент обеспеченности обязательств активами":"Степень покрытия долгов стоимостью имущества \n(1600 - 1220) / (1520 + 1510 + 1550 + 1400)",
    "Степень платежеспособности по текущим обязательствам":"Степень погашения краткосрочной задолженности компанией \n(1510 + 1520 + 1550) / (2110 / 12)",
    "Коэффициент утраты платежеспособности":"Коэффициент риска ухудшения расчетной дисциплины предприятия \n(КТЛк + 3 х (КТЛк - КТЛн)) / 2",
    "Рентабельность продаж, %":"Доля прибыли в выручке \n(2110 - 2120 - 2210 - 2220) / 2110",
    "Рентабельность затрат, %":"Процент эффективности понесенных производственных расходов \n(2110 - 2120 - 2210 - 2220) / (2120 + 2210 + 2220)",
    "Рентабельность активов, %":"Процент доходности использования всего имущества \n2400 / ((1600н + 1600к) / 2)",
    "Рентабельность собственного капитала, %":"Процент прибыльности вложений собственников компании \n2400 / ((1300н + 1300к) / 2)",
    "Оборачиваемость дебиторской задолженности":"Отражение скорости возврата средств от покупателей \n2110 / ((1230н + 1230к) / 2)",
    "Оборачиваемость кредиторской задолженности":"Коэффициент интенсивности погашения обязательств перед поставщиками \n2120 / ((1520н + 1520к) / 2)",
    "Коэффициент финансового рычага":"Степень влияния заемных средств на доходность \n(1400 + 1500) / 1300",
    "Тип финансовой устойчивости":"Определяет общее состояние структуры капитала предприятия \nСравнение запасов с источниками формирования"

}

@app.callback(
    Output("finance-table", "columns"),
    Output("finance-table", "data"),
    Output("company-info", "children"),
    Output("selected-inn", "children"),
    Output("ratios-output", "children"),
    Output("report-store", "data"),
    Input("load-button", "n_clicks"),
    State("inn-input", "value")
)
def update_table(n_clicks, inn):
    if not inn:
        return [], [], "", "", "", {}

    url = f"https://api.checko.ru/v2/finances?key={API_KEY}&inn={inn}"
    response = requests.get(url)
    if response.status_code != 200:
        return [], [], "", f"Ошибка: {response.status_code}", "", {}

    data = response.json()
    if "data" not in data or not data["data"]:
        return [], [], "", "Нет данных по этому ИНН.", "", {}

    df = pd.DataFrame(data["data"]).fillna(0)
    df.reset_index(inplace=True)
    df.rename(columns={"index": "Код"}, inplace=True)
    df["Код"] = df["Код"].astype(str)

    numeric_cols = [c for c in df.columns if c != "Код"]
    df["Показатель"] = df["Код"].apply(
        lambda x: f"{x}. {indicator_names.get(x, '')}" if x in indicator_names else None
    )
    df = df.dropna(subset=["Показатель"])
    df = df[["Показатель"] + numeric_cols]

    year_cols = [c for c in df.columns if c != "Показатель"]
    year_cols_str = [str(c) for c in year_cols]

    def pick_years(cols_str):
        if "2024" in cols_str and "2023" in cols_str:
            return "2024", "2023"
        nums = []
        for x in cols_str:
            try:
                nums.append(int(x))
            except Exception:
                pass
        nums = sorted(set(nums))
        if len(nums) >= 2:
            return str(nums[-1]), str(nums[-2])
        if len(nums) == 1:
            return str(nums[0]), str(nums[0])
        return None, None

    year_cur, year_prev = pick_years(year_cols_str)
    if not year_cur:
        return [], [], "", "Нет годовых колонок в данных.", "", {}

    df_idx = df.set_index("Показатель")

    def val(code: str, year: str):
        row_key = None
        for k in df_idx.index:
            if str(k).startswith(code):
                row_key = k
                break
        if row_key is None:
            return 0

        col = None
        if year in df_idx.columns:
            col = year
        else:
            for c in df_idx.columns:
                if str(c) == str(year):
                    col = c
                    break
        if col is None:
            return 0

        try:
            return float(df_idx.at[row_key, col]) or 0
        except Exception:
            return 0

    def avg_period(code: str, year_end: str, year_start_proxy: str | None):
        end_v = val(code, year_end)
        start_v = val(code, year_start_proxy) if year_start_proxy else end_v
        return (start_v + end_v) / 2

    def calc_ratios_for_year(y: str, y_prev_for_start: str | None):
        total_assets = val("1600", y)
        equity = val("1300", y)
        non_current = val("1100", y)
        current = val("1200", y)
        short_liab = val("1500", y)
        long_liab = val("1400", y)

        cash = val("1250", y)
        short_inv = val("1240", y)

        debit = val("1230", y)
        credit = val("1520", y)

        bal_total = val("1700", y)
        vat = val("1220", y)

        loans_lt = val("1410", y)
        loans_st = val("1510", y)
        other_st = val("1550", y)

        sales = val("2110", y)
        cost = val("2120", y)
        sell_exp = val("2210", y)
        admin_exp = val("2220", y)
        profit_net = val("2400", y)

        profit_sales = sales - cost - sell_exp - admin_exp

        avg_assets = avg_period("1600", y, y_prev_for_start)
        avg_equity = avg_period("1300", y, y_prev_for_start)
        avg_ar = avg_period("1230", y, y_prev_for_start)
        avg_ap = avg_period("1520", y, y_prev_for_start)

        k_tl = (current / short_liab) if short_liab else 0
        prev_current = val("1200", y_prev_for_start) if y_prev_for_start else 0
        prev_short_liab = val("1500", y_prev_for_start) if y_prev_for_start else 0
        k_tl_prev = (prev_current / prev_short_liab) if prev_short_liab else 0

        ratios = {
            "Коэффициент финансовой устойчивости": (equity + long_liab) / bal_total if bal_total else 0,
            "Коэффициент автономии": equity / total_assets if total_assets else 0,
            "Коэффициент обеспеченности собственными средствами": ((equity - non_current) / current) if current else 0,
            "Отношение дебиторской задолженности к активам": debit / total_assets if total_assets else 0,
            "Коэффициент соотношения заемного и собственного капитала": ((loans_lt + loans_st) / equity) if equity else 0,
            "Коэффициент абсолютной ликвидности": ((cash + short_inv) / short_liab) if short_liab else 0,
            "Коэффициент текущей ликвидности": k_tl,
            "Коэффициент обеспеченности обязательств активами": (
                (total_assets - vat) / (credit + loans_st + other_st + long_liab)
                if (credit + loans_st + other_st + long_liab) else 0
            ),
            "Степень платежеспособности по текущим обязательствам": (
                (loans_st + credit + other_st) / (sales / 12) if sales else 0
            ),
            "Коэффициент утраты платежеспособности": (k_tl + 3 * (k_tl - k_tl_prev)) / 2,
            "Рентабельность продаж, %": (profit_sales / sales * 100) if sales else 0,
            "Рентабельность затрат, %": (
                profit_sales / (cost + sell_exp + admin_exp) * 100
                if (cost + sell_exp + admin_exp) else 0
            ),
            "Рентабельность активов, %": (profit_net / avg_assets * 100) if avg_assets else 0,
            "Рентабельность собственного капитала, %": (profit_net / avg_equity * 100) if avg_equity else 0,
            "Оборачиваемость дебиторской задолженности": (sales / avg_ar) if avg_ar else 0,
            "Оборачиваемость кредиторской задолженности": (cost / avg_ap) if avg_ap else 0,
            "Коэффициент финансового рычага": (long_liab + short_liab) / equity if equity else 0,
        }

        Z = current - cash - short_inv - debit
        if Z < 0:
            Z = 0
        СОС = equity - non_current
        ДИ = СОС + long_liab
        ОИ = ДИ + short_liab

        if СОС > Z:
            stability = "Абсолютная устойчивость"
        elif ДИ > Z and СОС < Z:
            stability = "Нормальная устойчивость"
        elif ОИ > Z and ДИ < Z:
            stability = "Неустойчивая (предкризисная)"
        else:
            stability = "Кризисная"

        ratios["Тип финансовой устойчивости"] = stability
        return ratios

    ratios_cur = calc_ratios_for_year(year_cur, year_prev)

    year_prev_prev = None
    try:
        yp = int(year_prev)
        ypp = str(yp - 1)
        if ypp in year_cols_str:
            year_prev_prev = ypp
    except Exception:
        pass

    ratios_prev = calc_ratios_for_year(year_prev, year_prev_prev or year_prev)

    def fmt(v):
        if isinstance(v, (int, float)):
            return f"{v:.2f}"
        return str(v)

    all_keys = list(dict.fromkeys(list(ratios_cur.keys()) + list(ratios_prev.keys())))
    rows = []
    for k in all_keys:
        formula = RATIO_FORMULAS.get(k, "Формула не задана")
        rows.append(
            html.Tr([
                html.Td(k, title=f"Формула расчёта:\n{formula}", style={"textAlign": "left", "cursor": "help"}),
                html.Td(fmt(ratios_cur.get(k, 0)), style={"textAlign": "center"}),
                html.Td(fmt(ratios_prev.get(k, 0)), style={"textAlign": "center"}),
            ])
        )

    ratios_table = dbc.Table(
        [
            html.Thead(
                html.Tr([
                    html.Th("Показатель", style={"textAlign": "left"}),
                    html.Th(year_cur, style={"textAlign": "center"}),
                    html.Th(year_prev, style={"textAlign": "center"}),
                ])
            ),
            html.Tbody(rows)
        ],
        bordered=True,
        striped=True,
        hover=True,
        size="sm",
        style={"width": "100%"}
    )

    company = data.get("company", {})

    pdf_btn = dbc.Button(
        [html.I(className="bi bi-floppy me-1"), "Справка (PDF)"],
        id="download-pdf-btn",
        color="secondary",
        size="sm",
        className="px-2",
        style={"minWidth": "150px"}
    )

    company_card = dbc.Card(
        [
            dbc.CardHeader(
                dbc.Row(
                    [
                        dbc.Col(html.H4(company.get("НаимПолн", ""), className="mb-0"), width=True),
                        dbc.Col(pdf_btn, width="auto"),
                    ],
                    align="center",
                    className="g-2"
                )
            ),
            dbc.CardBody([
                html.P(f"ИНН: {company.get('ИНН', '')}"),
                html.P(f"ОГРН: {company.get('ОГРН', '')}"),
                html.P(f"Дата регистрации: {company.get('ДатаРег', '')}"),
                html.P(f"Статус: {company.get('Статус', '')}"),
                html.P(f"Адрес: {company.get('ЮрАдрес', '')}")
            ])
        ],
        className="mb-4"
    )

    ratios_card = dbc.Card(
        [
            dbc.CardHeader(html.H3(
                "Финансовые коэффициенты и показатели устойчивости",
                className="text-center mb-0"
            )),
            dbc.CardBody(ratios_table)
        ],
        className="mb-4"
    )

    years_num = []
    for y in year_cols_str:
        try:
            years_num.append(int(y))
        except Exception:
            pass
    years_num = sorted(set(years_num))
    last5 = [str(x) for x in years_num[-5:]] if years_num else []

    def series_by_code(code: str):
        return [val(code, y) for y in last5]

    net_assets = []
    for y in last5:
        net_assets.append(val("1300", y) + val("1530", y))

    metrics = {
        "years": last5,
        "Выручка (2110)": series_by_code("2110"),
        "Чистая прибыль (2400)": series_by_code("2400"),
        "Себестоимость (1300 + 1530)": net_assets,
        "Дебит. долг (1230)": series_by_code("1230"),
        "Кредит. долг (1520)": series_by_code("1520"),
    }

    report_store = {
        "company": company,
        "inn": inn,

        "year_cur": year_cur,
        "year_prev": year_prev,

        "ratios_order": all_keys,
        "ratios_cur": ratios_cur,
        "ratios_prev": ratios_prev,

        "metrics": metrics
    }

    columns = [{"name": col, "id": col} for col in df.columns]
    data_records = df.to_dict("records")
    selected = html.P(f"Выбран ИНН: {inn}", className="fw-bold text-center")

    return columns, data_records, [company_card], [selected], [ratios_card], report_store


@app.callback(
    Output("download-company-pdf", "data"),
    Input("download-pdf-btn", "n_clicks"),
    State("report-store", "data"),
    prevent_initial_call=True
)
def download_company_pdf(n_clicks, report):
    if not n_clicks:
        return no_update
    if not report:
        return no_update

    company = report.get("company", {})
    metrics = report.get("metrics", {})
    years = metrics.get("years", [])

    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_font = os.path.join(script_dir, "Times New Roman.ttf")
    system_font = r"C:\Windows\Fonts\times.ttf"

    font_path = local_font if os.path.exists(local_font) else system_font
    if not os.path.exists(font_path):
        raise FileNotFoundError(
            f'Не найден "Times New Roman.ttf".\n'
            f'Положи файл рядом с {os.path.basename(__file__)}: {local_font}\n'
            f'или проверь системный: {system_font}'
        )

    try:
        pdfmetrics.getFont("TNR")
    except Exception:
        pdfmetrics.registerFont(TTFont("TNR", font_path))

    formed_dt = datetime.now(ZoneInfo("Europe/Riga"))
    formed_str = formed_dt.strftime("%d.%m.%Y %H:%M")

    img_buf = io.BytesIO()
    if years:
        plt.figure(figsize=(11.0, 5.5))  

        s_rev = metrics.get("Выручка (2110)", [])
        s_profit = metrics.get("Чистая прибыль (2400)", [])
        s_na = metrics.get("Себестоимость (1300 + 1530)", [])
        s_ar = metrics.get("Дебит. долг (1230)", [])
        s_ap = metrics.get("Кредит. долг (1520)", [])

        plt.plot(years, s_rev, marker="o", label="Выручка")
        plt.plot(years, s_profit, marker="o", label="Чистая прибыль")
        plt.plot(years, s_na, marker="o", label="Себестоимость")
        plt.plot(years, s_ar, marker="o", label="Дебит. долг")
        plt.plot(years, s_ap, marker="o", label="Кредит. долг")

        max_val = 0
        for s in (s_rev, s_profit, s_na, s_ar, s_ap):
            for v in s:
                try:
                    max_val = max(max_val, abs(float(v)))
                except Exception:
                    pass

        if max_val >= 1e12:
            div, unit = 1e12, "трлн руб."
        elif max_val >= 1e9:
            div, unit = 1e9, "млрд руб."
        elif max_val >= 1e6:
            div, unit = 1e6, "млн руб."
        else:
            div, unit = 1, "руб."

        def yfmt(x, _pos):
            v = x / div
            if abs(v) >= 100:
                return f"{v:,.0f}".replace(",", " ")
            if abs(v) >= 10:
                return f"{v:,.1f}".replace(",", " ")
            return f"{v:,.2f}".replace(",", " ")

        ax = plt.gca()
        ax.yaxis.set_major_formatter(FuncFormatter(yfmt))
        ax.set_ylabel(unit)
        ax.yaxis.offsetText.set_visible(False)

        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()

        plt.savefig(img_buf, format="png", dpi=170)
        plt.close()
        img_buf.seek(0)
    else:
        img_buf = None

    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    styles = getSampleStyleSheet()
    for s in styles.byName.values():
        s.fontName = "TNR"

    story = []
    story.append(Paragraph("Справка о компании", styles["Title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Дата формирования: {formed_str}", styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"<b>Наименование:</b> {company.get('НаимПолн', '')}", styles["Normal"]))
    story.append(Paragraph(f"<b>ИНН:</b> {company.get('ИНН', '')}", styles["Normal"]))
    story.append(Paragraph(f"<b>ОГРН:</b> {company.get('ОГРН', '')}", styles["Normal"]))
    story.append(Paragraph(f"<b>Дата регистрации:</b> {company.get('ДатаРег', '')}", styles["Normal"]))
    story.append(Paragraph(f"<b>Статус:</b> {company.get('Статус', '')}", styles["Normal"]))
    story.append(Paragraph(f"<b>Адрес:</b> {company.get('ЮрАдрес', '')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Финансовые коэффициенты", styles["Heading2"]))
    story.append(Spacer(1, 6))

    year_cur = report.get("year_cur", "")
    year_prev = report.get("year_prev", "")
    ratios_order = report.get("ratios_order", [])
    ratios_cur = report.get("ratios_cur", {})
    ratios_prev = report.get("ratios_prev", {})

    def fmt_ratio(v):
        if isinstance(v, (int, float)):
            return f"{v:.2f}"
        return str(v)

    t = [["Показатель", year_cur, year_prev]]
    for k in ratios_order:
        t.append([k, fmt_ratio(ratios_cur.get(k, 0)), fmt_ratio(ratios_prev.get(k, 0))])

    MAX_ROWS = 45
    if len(t) > MAX_ROWS + 1:
        t = t[:MAX_ROWS + 1]
        t.append(["…", "…", "…"])

    tbl = Table(t, repeatRows=1, colWidths=[105 * mm, 37 * mm, 37 * mm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "TNR"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(tbl)

    if img_buf is not None:
        story.append(PageBreak())
        story.append(Paragraph("Динамика ключевых показателей (последние 5 лет)", styles["Heading2"]))
        story.append(Spacer(1, 6))

        story.append(Image(img_buf, width=260 * mm, height=140 * mm))

    def _on_page(canvas, _doc):
        canvas.setFont("TNR", 9)

    def _on_page_land(canvas, _doc):
        canvas.setFont("TNR", 9)
        w, _h = landscape(A4)
        canvas.drawRightString(w - 15 * mm, 10 * mm, f"Сформировано: {formed_str}")

    if img_buf is None:
        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    else:
        split_idx = None
        for i, el in enumerate(story):
            if isinstance(el, PageBreak):
                split_idx = i
                break

        portrait_story = story[:split_idx]  
        landscape_story = story[split_idx + 1:]  

        buf1 = io.BytesIO()
        doc1 = SimpleDocTemplate(
            buf1, pagesize=A4,
            leftMargin=15 * mm, rightMargin=15 * mm,
            topMargin=15 * mm, bottomMargin=15 * mm
        )
        doc1.build(portrait_story, onFirstPage=_on_page, onLaterPages=_on_page)

        buf2 = io.BytesIO()
        doc2 = SimpleDocTemplate(
            buf2, pagesize=landscape(A4),
            leftMargin=15 * mm, rightMargin=15 * mm,
            topMargin=15 * mm, bottomMargin=15 * mm
        )
        doc2.build(landscape_story, onFirstPage=_on_page_land, onLaterPages=_on_page_land)

        try:
            from pypdf import PdfReader, PdfWriter
        except Exception:
            pdf_bytes = buf1.getvalue()
            inn = company.get("ИНН", report.get("inn", ""))
            filename = f"spravka_{inn}_{formed_dt.strftime('%Y-%m-%d_%H-%M')}.pdf"
            return dcc.send_bytes(pdf_bytes, filename)

        r1 = PdfReader(buf1)
        r2 = PdfReader(buf2)
        w = PdfWriter()
        for p in r1.pages:
            w.add_page(p)
        for p in r2.pages:
            w.add_page(p)

        out = io.BytesIO()
        w.write(out)
        pdf_bytes = out.getvalue()

        inn = company.get("ИНН", report.get("inn", ""))
        filename = f"spravka_{inn}_{formed_dt.strftime('%Y-%m-%d_%H-%M')}.pdf"
        return dcc.send_bytes(pdf_bytes, filename)

    pdf_bytes = pdf_buf.getvalue()
    pdf_buf.close()

    inn = company.get("ИНН", report.get("inn", ""))
    filename = f"spravka_{inn}_{formed_dt.strftime('%Y-%m-%d_%H-%M')}.pdf"
    return dcc.send_bytes(pdf_bytes, filename)


if __name__ == '__main__':
    app.run(debug=True)


