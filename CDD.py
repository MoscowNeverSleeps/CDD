import requests
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import pandas as pd

API_KEY = "DVzlum5eSDKjelf2"
code_file = "code.txt"

indicator_names = {}
with open(code_file, encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) == 2:
            code, name = parts
            indicator_names[code] = name

# Используем светлую Bootstrap-тему (Flatly) для современного минималистичного дизайна
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY], suppress_callback_exceptions=True)
server = app.server

app.layout = dbc.Container([
    html.H1("Безопасность сделки — легко", className="text-center my-4"),
    
    # Поле ввода ИНН + кнопка
    dbc.InputGroup([
        dbc.InputGroupText("Введите ИНН:"),
        dbc.Input(id="inn-input", type="text", placeholder="10 цифр"),
        dbc.Button("Загрузить", id="load-button", n_clicks=0, color="primary")
    ], className="mb-4"),

    # Карточка компании
    html.Div(id="company-info"),
    dbc.Row([
        # Правая колонка — основная таблица показателей
        dbc.Col(
            dash_table.DataTable(
                id="finance-table",
                columns=[],
                data=[],
                fixed_columns={'headers': True, 'data': 1},  # 👈 закрепляем первый столбец
                style_table={
                    "overflowX": "auto",
                    "minWidth": "100%",
                },
                style_cell={
                    "textAlign": "center",
                    "padding": "6px",
                    "fontFamily": "Arial, sans-serif",
                    "minWidth": "120px",
                    "width": "120px",
                    "maxWidth": "180px",
                    "whiteSpace": "normal"
                },
                style_cell_conditional=[
                    {"if": {"column_id": "Показатель"}, "textAlign": "left", "width": "300px"}
                ],
                style_header={"backgroundColor": "#e1e1e1", "fontWeight": "bold"},
            )

            width=8,
            className="ps-2"  # небольшой отступ слева
        ),
                # Левая колонка — финансовые коэффициенты
        dbc.Col(
            html.Div(id="ratios-output"),
            width=4,
            className="pe-2"  # небольшой отступ справа
        )
    ], className="mt-4"),

    # Подпись выбранного ИНН
    html.Div(id="selected-inn", className="mt-3 text-center fw-bold")
], fluid=True)

@app.callback(
    Output("finance-table", "columns"),
    Output("finance-table", "data"),
    Output("company-info", "children"),
    Output("selected-inn", "children"),
    Output("ratios-output", "children"),
    Input("load-button", "n_clicks"),
    State("inn-input", "value")
)
def update_table(n_clicks, inn):
    if not inn:
        return [], [], "", "", ""
    url = f"https://api.checko.ru/v2/finances?key={API_KEY}&inn={inn}"
    response = requests.get(url)
    if response.status_code != 200:
        return [], [], "", f"Ошибка: {response.status_code}", ""
    data = response.json()
    if "data" not in data or not data["data"]:
        return [], [], "", "Нет данных по этому ИНН.", ""

    # Преобразуем данные API в DataFrame
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

    # Расчёт финансовых коэффициентов
    vals = df.set_index("Показатель").iloc[:, 1:].mean(axis=1).to_dict()
    def val(code):
        for k, v in vals.items():
            if k.startswith(code):
                return v
        return 0
    total_assets = val("1600")
    equity = val("1300")
    non_current = val("1100")
    current = val("1200")
    short_liab = val("1500")
    long_liab = val("1400")
    cash = val("1250")
    short_inv = val("1240")
    profit = val("2400")
    sales = val("2110")
    cost = val("2120")
    credit = val("1520")
    debit = val("1230")
    fixed_assets = val("1150")

    ratios = {
        "Коэффициент автономии": equity / total_assets if total_assets else 0,
        "Коэффициент обеспеченности СОС": (equity - non_current) / current if current else 0,
        "Коэффициент текущей ликвидности": current / short_liab if short_liab else 0,
        "Коэффициент абсолютной ликвидности": (cash + short_inv) / short_liab if short_liab else 0,
        "Коэффициент финансовой независимости": equity / total_assets if total_assets else 0,
        "Коэффициент финансового рычага": (long_liab + short_liab) / equity if equity else 0,
        "Рентабельность продаж": profit / sales if sales else 0,
        "Рентабельность активов": profit / total_assets if total_assets else 0,
        "Рентабельность осн. деятельности": val("2200") / sales if sales else 0,
        "Дебиторская/Кредиторская задолж.": debit / credit if credit else 0,
        "Оборачиваемость оборотных активов": sales / current if current else 0,
        "Фондоотдача": sales / fixed_assets if fixed_assets else 0,
        "Материалоотдача": sales / cost if cost else 0,
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

    # Карточка с информацией о компании
    company = data.get("company", {})
    company_card = dbc.Card(
        [
            dbc.CardHeader(html.H4(company.get("НаимПолн", ""), className="mb-0")),
            dbc.CardBody([
                html.P(f"ИНН: {company.get('ИНН', '')}"),
                html.P(f"ОГРН: {company.get('ОГРН', '')}"),
                html.P(f"Дата регистрации: {company.get('ДатаРег', '')}"),
                html.P(f"Статус: {company.get('Статус', '')}"),
                html.P(f"Адрес: {company.get('ЮрАдрес', '')}")
            ])
        ], className="mb-4"
    )

    # Таблица финансовых коэффициентов
    rows = []
    for k, v in ratios.items():
        rows.append(html.Tr([html.Td(k), html.Td(f"{v:.2f}" if isinstance(v, (int, float)) else v)]))
    ratios_table = dbc.Table(
        [html.Thead(html.Tr([html.Th("Показатель"), html.Th("Значение")]))] +
        [html.Tbody(rows)],
        bordered=True, striped=True
    )
    ratios_card = dbc.Card(
        [
            dbc.CardHeader(html.H3(
                "Финансовые коэффициенты и показатели устойчивости",
                className="text-center mb-0"
            )),
            dbc.CardBody(ratios_table)
        ], className="mb-4"
    )

    columns = [{"name": col, "id": col} for col in df.columns]
    data_records = df.to_dict("records")
    selected = html.P(f"Выбран ИНН: {inn}", className="fw-bold text-center")
    return columns, data_records, [company_card], [selected], [ratios_card]

if __name__ == '__main__':
    app.run_server(debug=True)



