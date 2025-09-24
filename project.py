import requests
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import pandas as pd

API_KEY = "DVzlum5eSDKjelf2"
code_file = "code.txt"

# Загружаем справочник кодов
indicator_names = {}
with open(code_file, encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) == 2:
            code, name = parts
            indicator_names[code] = name

app = dash.Dash(__name__, suppress_callback_exceptions=True)

app.layout = html.Div([
    html.H1("Финансовая отчетность", style={"textAlign": "center"}),

    # Поле для ввода ИНН
    html.Div([
        html.Label("Введите ИНН:"),
        dcc.Input(id="inn-input", type="text"),
        html.Button("Загрузить", id="load-button")
    ], style={"marginBottom": "20px"}),

    # Блок для информации о компании
    html.Div(id="company-info", style={"backgroundColor": "#f9f9f9", "padding": "10px", "marginBottom": "20px"}),

    # Таблица с отчетностью
    dash_table.DataTable(
        id="finance-table",
        columns=[],
        data=[],
        style_table={"overflowX": "auto", "width": "100%"},
        style_cell={
            "textAlign": "center",
            "padding": "5px",
            "minWidth": "80px", "width": "120px", "maxWidth": "200px",
            "whiteSpace": "normal"
        },
        style_cell_conditional=[
            {"if": {"column_id": "Показатель"}, "textAlign": "left", "width": "300px"}
        ],
        style_header={"backgroundColor": "#e1e1e1", "fontWeight": "bold"},
    ),

    html.Div(id="selected-inn", style={"marginTop": "20px", "fontWeight": "bold"})
])


@app.callback(
    Output("finance-table", "columns"),
    Output("finance-table", "data"),
    Output("company-info", "children"),
    Output("selected-inn", "children"),
    Input("load-button", "n_clicks"),
    State("inn-input", "value")
)
def update_table(n_clicks, inn):
    if not inn:
        return [], [], "", "Тестовый ИНН 5042162595"

    # Запрос к API
    url = f"https://api.checko.ru/v2/finances?key={API_KEY}&inn={inn}"
    response = requests.get(url)

    if response.status_code != 200:
        return [], [], "", f"Ошибка: {response.status_code}"

    data = response.json()

    # Преобразуем данные в DataFrame
    df = pd.DataFrame(data["data"]).fillna(0).astype(int)
    df.reset_index(inplace=True)
    df.rename(columns={"index": "Код"}, inplace=True)

    df["Показатель"] = df["Код"].map(lambda x: f"{x}. {indicator_names[x]}" if x in indicator_names else None)
    df = df.dropna(subset=["Показатель"])
    df = df[["Показатель"] + [col for col in df.columns if col not in ["Код", "Показатель"]]]

    columns = [{"name": col, "id": col} for col in df.columns]
    data_records = df.to_dict("records")

    # Информация о компании
    company = data["company"]
    company_info = [
        html.H3(company.get("НаимПолн", "")),
        html.P(f'ИНН: {company.get("ИНН", "")} | ОГРН: {company.get("ОГРН", "")}'),
        html.P(f'Дата регистрации: {company.get("ДатаРег", "")}'),
        html.P(f'Статус: {company.get("Статус", "")}'),
        html.P(f'Адрес: {company.get("ЮрАдрес", "")}')
    ]

    return columns, data_records, company_info, f"Выбран ИНН: {inn}"

server = app.server

if __name__ == "__main__":
    app.run_server(debug=True)

