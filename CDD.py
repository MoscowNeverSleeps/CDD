# -*- coding: utf-8 -*-

import os
import requests
from flask import Flask, jsonify, request, Response, session, redirect, url_for, send_file, g
import re

API_KEY     = os.getenv("CHECKO_API_KEY", "DVzlum5eSDKjelf2")

OFDATA_KEY  = os.getenv("OFDATA_API_KEY", "AunAtSggXmTaDTA0")
OFDATA_BASE = "https://api.ofdata.ru/v2"
OFDATA_DEBUG = True 

ENDPOINTS = {
    "arbitr":    "/legal-cases",
    "fssp":      "/enforcements",
    "inspect":   "/inspections",
    "contracts": "/contracts",  # требует law={44,94,223}
}

import logging
from datetime import datetime

def ofget(path: str, **params):
    if not OFDATA_KEY:
        return {}
    try:
        r = requests.get(f"{OFDATA_BASE}{path}", params={"key": OFDATA_KEY, **params}, timeout=25)
        r.raise_for_status()
        j = r.json()
        if OFDATA_DEBUG:
            logging.warning(f"[OFDATA] {path} {params} → {r.status_code}, keys={list(j.keys()) if isinstance(j,dict) else type(j)}")
        return j
    except Exception as e:
        logging.error(f"[OFDATA] ERR {path}: {e}")
        return {}

def _data_records(payload):
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        recs = data.get("Записи")
        return recs if isinstance(recs, list) else []
    return []

def _data_total(payload):
    if not isinstance(payload, dict):
        return 0
    data = payload.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("ЗапВсего"), (int, float)):
            return int(data["ЗапВсего"])
        recs = data.get("Записи")
        return len(recs) if isinstance(recs, list) else 0
    return 0

def _company_from(payload):
    if isinstance(payload, dict) and isinstance(payload.get("company"), dict):
        return payload["company"]
    return {}

def _parse_date(s):
    if not s:
        return None
    for cand in (str(s)[:10], str(s)):
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y.%m.%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(cand, fmt)
            except:
                pass
    return None

def _max_date_by(items, *date_keys):
    best = None
    for it in items:
        if not isinstance(it, dict): 
            continue
        for k in date_keys:
            dt = _parse_date(it.get(k))
            if dt and (best is None or dt > best):
                best = dt
    return best.date().isoformat() if best else None


def placeholder_page(title, note="Раздел в разработке."):
    inner = f"""
<section class="full-bleed bg-slate-900">
  <div class="max-w-4xl mx-auto px-6 py-24 md:py-32">
    <div class="p-8 rounded-3xl bg-slate-800/60 ring-1 ring-white/10">
      <div class="text-2xl font-extrabold">{title}</div>
      <p class="text-slate-300 mt-2">{note}</p>
      <div class="mt-6">
        <a href="/" class="px-6 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">На главную</a>
      </div>
    </div>
  </div>
</section>
"""
    return Response(page_wrap(inner, title), mimetype="text/html; charset=utf-8")

CODES_RAW = """
1110	 Нематериальные активы
1120	 Результаты исследований и разработок
1130	 Нематериальные поисковые активы
1140	 Материальные поисковые активы
1150	 Основные средства
1160	 Доходные вложения в материальные ценности
1170	 Финансовые вложения
1180	 Отложенные налоговые активы
1190	 Прочие внеоборотные активы
1100	 Итого по разделу I «Внеоборотные активы»
1210	 Запасы
1220	 Налог на добавленную стоимость по приобретённым ценностям
1230	 Дебиторская задолженность
1240	 Финансовые вложения (за исключением денежных эквивалентов)
1250	 Денежные средства и денежные эквиваленты
1260	 Прочие оборотные активы
1200	 Итого по разделу II «Оборотные активы»
1600	 Баланс (итог актива)
1310	 Уставный капитал (фонд, вклады товарищей)
1320	 Собственные акции, выкупленные у акционеров
1340	 Переоценка внеоборотных активов
1350	 Добавочный капитал
1360	 Резервный капитал
1370	 Нераспределённая прибыль (непокрытый убыток)
1300	 Итого по разделу III «Капитал и резервы»
1410	 Заемные средства (долгосрочные)
1420	 Отложенные налоговые обязательства
1430	 Оценочные обязательства
1450	 Прочие обязательства
1400	 Итого по разделу IV «Долгосрочные обязательства»
1510	 Заемные средства (краткосрочные)
1520	 Кредиторская задолженность
1530	 Доходы будущих периодов
1540	 Оценочные обязательства
1550	 Прочие обязательства
1500	 Итого по разделу V «Краткосрочные обязательства»
1700	 Баланс (итог пассива)
2110	 Выручка
2120	 Себестоимость продаж
2100	 Валовая прибыль (убыток)
2210	 Коммерческие расходы
2220	 Управленческие расходы
2200	 Прибыль (убыток) от продаж
2310	 Доходы от участия в других организациях
2320	 Проценты к получению
2330	 Проценты к уплате
2340	 Прочие доходы
2350	 Прочие расходы
2300	 Прибыль (убыток) до налогообложения
2410	 Налог на прибыль
2411	 Текущий налог на прибыль
2412	 Отложенный налог на прибыль
2460	 Прочее
2400	 Чистая прибыль (убыток)
2510	 Результат от переоценки внеоборотных активов
2520	 Результат от прочих операций, не включаемый в чистую прибыль
2530	 Налог на прибыль от операций, не включаемых в чистую прибыль
2500	 Совокупный финансовый результат периода
3100	 Величина капитала на начало периода
3200	 Величина капитала на конец предыдущего периода
3210	 Увеличение капитала – всего
3211	 Чистая прибыль
3212	 Переоценка имущества
3213	 Доходы, относящиеся на увеличение капитала
3214	 Дополнительный выпуск акций
3215	 Увеличение номинальной стоимости акций
3216	 Реорганизация юрлица
3220	 Уменьшение капитала – всего
3221	 Убыток
3222	 Переоценка имущества (уменьшение)
3223	 Расходы, уменьшающие капитал
3224	 Уменьшение номинальной стоимости акций
3225	 Уменьшение количества акций
3226	 Реорганизация
3227	 Дивиденды
3230	 Изменение добавочного капитала
3240	 Изменение резервного капитала
3310	 Увеличение капитала – всего (текущий год)
3316	 Реорганизация юрлица
3320	 Уменьшение капитала – всего
3321	 Убыток
3330	 Изменение добавочного капитала
3340	 Изменение резервного капитала
3300	 Величина капитала на конец отчетного периода
3400	 Корректировки капитала (всего)
3410	 Изменение учетной политики
3420	 Исправление ошибок
3500	 Капитал после корректировок
3501	 После корректировок (нераспределённая прибыль)
3600	 Чистые активы
4110	 Поступления от текущих операций (всего)
4111	 От продажи товаров, работ, услуг
4112	 Арендные, лицензионные, комиссионные платежи
4113	 От перепродажи финансовых вложений
4119	 Прочие поступления
4120	 Платежи (всего)
4121	 Поставщикам и подрядчикам
4122	 Оплата труда
4123	 Проценты по долговым обязательствам
4124	 Налог на прибыль организаций
4129	 Прочие платежи
4100	 Сальдо денежных потоков от текущих операций
4210	 Поступления от инвестиционных операций (всего)
4211	 От продажи внеоборотных активов
4212	 От продажи долей участия
4213	 От возврата предоставленных займов, ценных бумаг
4214	 Дивиденды, проценты, доходы от участия
4219	 Прочие поступления
4220	 Платежи по инвестиционным операциям (всего)
4221	 Приобретение внеоборотных активов
4222	 Приобретение долей участия
4223	 Предоставление займов, покупка долговых бумаг
4229	 Прочие платежи
4200	 Сальдо денежных потоков от инвестиционных операций
4310	 Поступления от финансовых операций (всего)
4311	 Получение кредитов и займов
4312	 Вклады собственников
4313	 Выпуск акций, увеличение долей
4314	 Выпуск долговых бумаг
4319	 Прочие поступления
4320	 Платежи по финансовым операциям (всего)
4321	 Выкуп долей, выход участников
4322	 Дивиденды, выплаты собственникам
4323	 Возврат кредитов и займов
4329	 Прочие платежи
4300	 Сальдо денежных потоков от финансовых операций
4400	 Сальдо денежных потоков за отчетный период
4450	 Остаток денежных средств на начало периода
4490	 Влияние изменения курса валют
4500	 Остаток денежных средств на конец периода
""".strip()

INDICATOR_NAMES = {line.split("\t",1)[0].strip(): line.split("\t",1)[1].strip()
                   for line in CODES_RAW.splitlines() if line.strip()}

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", "dev-secret-change-me")

def _ok(data=None, **kw):
    return jsonify({"ok": True, "data": data, **kw})

def _err(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code

@app.get("/api/cart")
def api_cart_get():
    items, total, balance = _cart_items_with_totals()
    return _ok({"items": items, "total": total, "balance": balance})

@app.post("/api/cart/add")
def api_cart_add():
    _ensure_state()
    j = request.get_json(force=True, silent=True) or {}
    sku = (j.get("sku") or "").strip()
    qty = int(j.get("qty") or 1)
    if sku not in CATALOG:
        return _err("Товар не найден")

    if CATALOG[sku]["type"] == "credit":
        return _ok({"redirect": url_for("balance_page")})
    session["cart"][sku] = max(1, min(99, int(session["cart"].get(sku, 0)) + qty))
    session.modified = True
    items, total, balance = _cart_items_with_totals()
    return _ok({"items": items, "total": total, "balance": balance})

@app.post("/api/cart/update")
def api_cart_update():
    _ensure_state()
    j = request.get_json(force=True, silent=True) or {}
    sku = (j.get("sku") or "").strip()
    qty = int(j.get("qty") or 1)
    if sku not in CATALOG:
        return _err("Товар не найден")
    if qty <= 0:
        session["cart"].pop(sku, None)
    else:
        session["cart"][sku] = max(1, min(99, qty))
    session.modified = True
    items, total, balance = _cart_items_with_totals()
    return _ok({"items": items, "total": total, "balance": balance})

@app.post("/api/cart/clear")
def api_cart_clear():
    session["cart"] = {}
    session.modified = True
    return _ok({"cleared": True})
    
@app.post("/api/checkout/pay-from-balance")
def api_checkout_pay_from_balance():
    _ensure_state()
    items, total, balance = _cart_items_with_totals()
    if total <= 0:
        return _err("Корзина пуста")
    if balance < total:
        return _err("Недостаточно средств на балансе")
    session["balance"] = int(balance - total)
    session["cart"] = {}
    session.modified = True
    return _ok({"paid": True, "balance": session["balance"]})

@app.post("/api/balance/topup")
def api_balance_topup():
    _ensure_state()
    j = request.get_json(force=True, silent=True) or {}
    amount = int(j.get("amount") or 0)
    method = (j.get("method") or "card").strip()
    if amount <= 0:
        return _err("Некорректная сумма")
    session["balance"] = int(session.get("balance", 0) + amount)
    session.modified = True
    return _ok({"message": f"Успешное пополнение через {method}",
                "balance": session["balance"]})

@app.get("/api/ofdata/arbitr")
def api_of_arbitr():
    inn   = request.args.get("inn","").strip()
    role  = request.args.get("role")          # plaintiff | defendant
    actual= request.args.get("actual")        # "true"/"false"
    active= request.args.get("active")
    df    = request.args.get("date_from")
    dt    = request.args.get("date_to")
    sort  = request.args.get("sort","-date")  # по доке: date | -date
    page  = int(request.args.get("page",1))
    limit = int(request.args.get("limit",20))
    if not inn: return _err("ИНН не задан")
    q = {"inn":inn, "sort":sort, "page":page, "limit":limit}
    if role:   q["role"]   = role
    if actual: q["actual"] = actual
    if active: q["active"] = active
    if df:     q["date_from"]=df
    if dt:     q["date_to"]=dt

    raw = ofget(ENDPOINTS["arbitr"], **q)
    items = _data_records(raw)
    total = _data_total(raw)
    last  = _max_date_by(items, "Дата")
    return _ok({
        "items": items,
        "total": total,
        "page":  page,
        "pages": max(1, (total + limit - 1)//limit),
        "last_date": last
    })

@app.get("/api/ofdata/enforcements")
def api_of_enf():
    inn   = request.args.get("inn","").strip()
    sort  = request.args.get("sort","-date")
    page  = int(request.args.get("page",1))
    limit = int(request.args.get("limit",20))
    if not inn: return _err("ИНН не задан")
    raw = ofget(ENDPOINTS["fssp"], inn=inn, sort=sort, page=page, limit=limit)
    items = _data_records(raw)
    total = _data_total(raw)
    last  = _max_date_by(items, "ИспПрДата")
    return _ok({
        "items": items,
        "total": total,
        "page":  page,
        "pages": max(1, (total + limit - 1)//limit),
        "last_date": last
    })

@app.get("/api/ofdata/inspections")
def api_of_insp():
    inn   = request.args.get("inn","").strip()
    sort  = request.args.get("sort","-date")
    page  = int(request.args.get("page",1))
    limit = int(request.args.get("limit",20))
    if not inn: return _err("ИНН не задан")
    raw = ofget(ENDPOINTS["inspect"], inn=inn, sort=sort, page=page, limit=limit)
    items = _data_records(raw)
    total = _data_total(raw)
    last  = _max_date_by(items, "ДатаНач")
    return _ok({
        "items": items,
        "total": total,
        "page":  page,
        "pages": max(1, (total + limit - 1)//limit),
        "last_date": last
    })

@app.get("/api/ofdata/contracts")
def api_of_contracts():
    inn   = request.args.get("inn","").strip()
    law   = request.args.get("law")          
    role  = request.args.get("role")         
    sort  = request.args.get("sort","-date") 
    page  = int(request.args.get("page",1))
    limit = int(request.args.get("limit",20))
    if not inn: return _err("ИНН не задан")

    def one(law_val, role_val):
        return ofget(ENDPOINTS["contracts"], inn=inn, law=law_val, role=role_val, sort=sort, page=page, limit=limit)

    laws  = [int(law)] if law else [44,94,223]
    roles = [role] if role else ["customer","supplier"]

    items_all = []
    total = 0
    last  = None
    for l in laws:
        for r_ in roles:
            raw = one(l, r_)
            recs = _data_records(raw)
            items_all.extend([dict(x, __law=l, __role=r_) for x in recs])
            t = _data_total(raw); total += t
            ld = _max_date_by(recs, "Дата")
            if ld and (not last or ld > last): last = ld

    if not law and not role:
        start = (page-1)*limit
        items_out = items_all[start:start+limit]
        pages = max(1, (total + limit - 1)//limit)
    else:
        items_out = items_all
        pages = max(1, (total + limit - 1)//limit)

    return _ok({
        "items": items_out,
        "total": total,
        "page":  page,
        "pages": pages,
        "last_date": last
    })
@app.get("/api/ofdata_summary")
def api_ofdata_summary():
    inn = request.args.get("inn", "").strip()
    if not inn:
        return jsonify({"ok": False, "error": "ИНН не задан"}), 400

    arbitr_raw = ofget(ENDPOINTS["arbitr"], inn=inn, sort="-date")
    arbitr_list = _data_records(arbitr_raw)        # data.Записи
    arbitr_cnt  = _data_total(arbitr_raw)          # data.ЗапВсего или len
    arbitr_last = _max_date_by(arbitr_list, "Дата")  # ключ даты по доке

    fssp_raw = ofget(ENDPOINTS["fssp"], inn=inn, sort="-date")
    fssp_list = _data_records(fssp_raw)
    fssp_cnt  = _data_total(fssp_raw)
    fssp_last = _max_date_by(fssp_list, "ИспПрДата")  # ключ даты по доке

    insp_raw = ofget(ENDPOINTS["inspect"], inn=inn, sort="-date")
    insp_list = _data_records(insp_raw)
    insp_cnt  = _data_total(insp_raw)
    insp_last = _max_date_by(insp_list, "ДатаНач")    # ключ даты по доке

    total_contracts = 0
    all_contract_rows = []
    laws  = [44, 94, 223]
    roles = ["customer", "supplier"]
    for law in laws:
        for role in roles:
            c_raw = ofget(ENDPOINTS["contracts"], inn=inn, law=law, role=role, sort="-date")
            total_contracts += _data_total(c_raw)
            all_contract_rows.extend(_data_records(c_raw))
    contracts_last = _max_date_by(all_contract_rows, "Дата")

    comp = (_company_from(arbitr_raw) or
            _company_from(fssp_raw)   or
            _company_from(insp_raw))
    if not comp:
        comp = _company_from(c_raw) if 'c_raw' in locals() else {}

    company = {
        "name":   comp.get("НаимПолн") or comp.get("НаимСокр"),
        "inn":    comp.get("ИНН") or inn,
        "ogrn":   comp.get("ОГРН"),
        "status": comp.get("Статус"),
        "addr":   comp.get("ЮрАдрес"),
        "okved":  comp.get("ОКВЭД"),
    }

    summary = {
        "company":   company,
        "arbitr":    {"count": arbitr_cnt,   "last_date": arbitr_last},
        "fssp":      {"count": fssp_cnt,     "last_date": fssp_last},
        "inspect":   {"count": insp_cnt,     "last_date": insp_last},
        "contracts": {"count": total_contracts, "last_date": contracts_last},
    }
    return jsonify({"ok": True, "summary": summary})
CATALOG = {
    "sub_month": {
        "sku": "sub_month", "title": "Подписка на месяц",
        "desc": "Доступ ко всем функциям на 30 дней", "price": 1500,
        "period": "1 месяц", "type": "subscription"
    },
    "sub_year": {
        "sku": "sub_year", "title": "Подписка на год",
        "desc": "12 месяцев доступа, приоритетная поддержка", "price": 15000,
        "period": "12 месяцев", "type": "subscription"
    },
    "check_one": {
        "sku": "check_one", "title": "Единоразовые проверки",
        "desc": "Разовая проверка контрагента по 300 ₽", "price": 300,
        "type": "credit"
    }
}

def _ensure_state():
    session.setdefault("cart", {})     # sku -> qty
    session.setdefault("balance", 0)   # RUB

def _cart_items_with_totals():
    _ensure_state()
    items, total = [], 0
    for sku, qty in session["cart"].items():
        prod = CATALOG.get(sku)
        if not prod: 
            continue
        line_total = int(prod["price"]) * int(qty)
        total += line_total
        items.append({
            "sku": sku, "title": prod["title"], "desc": prod.get("desc",""),
            "price": prod["price"], "qty": qty, "line_total": line_total,
            "type": prod.get("type","")
        })
    return items, total, session.get("balance", 0)

# ===================== API (без изменений) =====================
@app.get("/api/finances")
def api_finances():
    inn = request.args.get("inn","").strip()
    if not inn:
        return jsonify({"ok": False, "error": "ИНН не задан"}), 400
    r = requests.get(f"https://api.checko.ru/v2/finances?key={API_KEY}&inn={inn}", timeout=25)
    if r.status_code != 200:
        return jsonify({"ok": False, "error": f"Ошибка провайдера: {r.status_code}"}), 502
    payload = r.json()
    if not payload.get("data"):
        return jsonify({"ok": False, "error": "Нет данных по этому ИНН"}), 404

    def _to_float(v):
        if v is None: return 0.0
        if isinstance(v,(int,float)): return float(v)
        s = str(v).strip().replace("\xa0"," ").replace(" ","").replace(",",".")
        try: return float(s)
        except: return 0.0
    def _year_str(x):
        s=str(x); m=re.search(r"\d{4}", s); return m.group(0) if m else s

    raw_in = payload["data"]
    first_key = next(iter(raw_in)) if raw_in else ""
    looks_like_year = bool(re.fullmatch(r"\d{4}.*", str(first_key)))

    raw={}
    if looks_like_year:
        for per, m in raw_in.items():
            p=_year_str(per)
            for code, val in (m or {}).items():
                raw.setdefault(str(code),{})[p]=_to_float(val)
    else:
        for code, m in raw_in.items():
            raw[str(code)]={_year_str(per): _to_float(val) for per,val in (m or {}).items()}

    periods = sorted({p for m in raw.values() for p in m.keys()}, key=lambda x: int(x) if str(x).isdigit() else str(x))
    rows=[]
    for code, m in raw.items():
        row={"Код":code, "Показатель": f"{code}. {INDICATOR_NAMES.get(code,'')}"}
        for p in periods: row[p]=float(m.get(p,0.0) or 0.0)
        rows.append(row)

    def series(code):
        sc=str(code)
        for r_ in rows:
            if r_["Код"]==sc: return [float(r_.get(p,0.0) or 0.0) for p in periods]
        return [0.0 for _ in periods]
    def mean(code):
        s=series(code); return (sum(s)/len(s)) if s else 0.0
    def mean_nz(code):
        s=[x for x in series(code) if x not in (0, None, 0.0)]
        return (sum(s)/len(s)) if s else 0.0
    def safe_div(a,b): return (a/b) if (b not in (0,None,0.0)) else 0.0

    total_assets=mean("1600") if "1600" in raw else 0.0
    equity=mean("1300") if "1300" in raw else 0.0
    non_current=mean("1100") if "1100" in raw else 0.0
    current=mean("1200") if "1200" in raw else 0.0
    short_liab=mean("1500") if "1500" in raw else 0.0
    long_liab=mean("1400") if "1400" in raw else 0.0
    cash=mean("1250") if "1250" in raw else 0.0
    short_inv=mean("1240") if "1240" in raw else 0.0
    profit_mean=mean_nz("2400") if "2400" in raw else 0.0
    sales_mean=mean_nz("2110") if "2110" in raw else 0.0
    cost_mean=mean_nz("2120") if "2120" in raw else 0.0
    credit_mean=mean_nz("1520") if "1520" in raw else 0.0
    debit_mean=mean_nz("1230") if "1230" in raw else 0.0
    fixed_assets_mean=mean_nz("1150") if "1150" in raw else 0.0

    ratios = {
        "Коэффициент автономии": safe_div(equity,total_assets),
        "Коэф. обеспеченности СОС": safe_div((equity-non_current), current),
        "Текущая ликвидность": safe_div(current, short_liab),
        "Абсолютная ликвидность": safe_div((cash+short_inv), short_liab),
        "Финансовый рычаг": safe_div((long_liab+short_liab), equity),
        "Рентабельность продаж": safe_div(profit_mean, sales_mean),
        "ROA": safe_div(profit_mean, total_assets),
        "Фондоотдача": safe_div(sales_mean, fixed_assets_mean),
        "Материалоотдача": safe_div(sales_mean, cost_mean),
        "Дебиторка/Кредиторка": safe_div(debit_mean, credit_mean),
    }
    Z = max(current - cash - short_inv - debit_mean, 0)
    СОС = equity - non_current
    ДИ = СОС + long_liab
    ОИ = ДИ + short_liab
    if СОС > Z: stability="Абсолютная устойчивость"
    elif ДИ > Z and СОС < Z: stability="Нормальная устойчивость"
    elif ОИ > Z and ДИ < Z: stability="Неустойчивая (предкризисная)"
    else: stability="Кризисная"
    ratios["Тип финансовой устойчивости"]=stability

    sales=series("2110") if "2110" in raw else [0.0 for _ in periods]
    profit=series("2400") if "2400" in raw else [0.0 for _ in periods]
    eq_s=series("1300") if "1300" in raw else [0.0 for _ in periods]
    ta_s=series("1600") if "1600" in raw else [0.0 for _ in periods]
    cur_s=series("1200") if "1200" in raw else [0.0 for _ in periods]
    sh_s=series("1500") if "1500" in raw else [0.0 for _ in periods]
    autonomy=[safe_div(e,t) for e,t in zip(eq_s,ta_s)]
    current_ratio=[safe_div(c,s) for c,s in zip(cur_s,sh_s)]
    company=payload.get("company",{})

    return jsonify({
        "ok": True,
        "periods": periods,
        "rows": [{k:v for k,v in r.items() if k!="Код"} for r in rows],
        "company": company,
        "ratios": ratios,
        "charts": {"periods":periods,"sales":sales,"profit":profit,"autonomy":autonomy,"current_ratio":current_ratio}
  
    })

    arb_raw   = ofget("/arbitr/cases")
    fssp_raw  = ofget("/fssp/enforcements")
    insp_raw  = ofget("/inspections")
    bank_raw  = ofget("/bankruptcies")
    gz_raw    = ofget("/purchases")        # госзакупки
    rnp_raw   = ofget("/rnp")              # реестр недобросовестных поставщиков
    sanc_raw  = ofget("/sanctions")        # санкционные списки (если есть)
    lic_raw   = ofget("/licenses")         # лицензии (Росалк, Роском, ФСБ и пр., если у них есть единая точка)

    arb_items  = to_items(arb_raw)
    fssp_items = to_items(fssp_raw)
    insp_items = to_items(insp_raw)
    bank_items = to_items(bank_raw)
    gz_items   = to_items(gz_raw)
    rnp_items  = to_items(rnp_raw)
    sanc_items = to_items(sanc_raw)
    lic_items  = to_items(lic_raw)

    out = {
        "ok": True,
        "arbitr": {
            "count": len(arb_items),
            "last_date": latest_date(arb_items, "case_date", "date", "reg_date"),
        },
        "fssp": {
            "count": len(fssp_items),
            "last_date": latest_date(fssp_items, "date", "executive_proceeding_date"),
        },
        "inspections": {
            "count": len(insp_items),
            "last_date": latest_date(insp_items, "date", "decision_date"),
        },
        "bankruptcies": {
            "count": len(bank_items),
            "last_date": latest_date(bank_items, "date", "publish_date"),
        },
        "purchases": {
            "count": len(gz_items),
            "last_date": latest_date(gz_items, "publish_date", "date"),
        },
        "rnp": {
            "count": len(rnp_items),
            "last_date": latest_date(rnp_items, "date", "decision_date"),
        },
        "sanctions": {
            "count": len(sanc_items),
            "last_date": latest_date(sanc_items, "date", "included_at"),
        },
        "licenses": {
            "count": len(lic_items),
            "last_date": latest_date(lic_items, "date", "issued_at"),
        },
    }
    return jsonify(out)



BRAND_HEAD = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = { theme:{ extend:{ colors:{ brand:'#3b82f6', brand2:'#60a5fa' } } } }
</script>
<style>
/* Компактная вертикальная высота только для секции facts */
.section-facts-tight{
  padding-block: clamp(350px, 100vw, 100px);   /* было много — делаем плотнее */
}

/* Чуть меньше отступ под заголовком внутри facts */
.section-facts-tight header{
  margin-bottom: clamp(100px, 2vw, 18px);
}
/* Карточка выгоды — фиксированная структура и ровные высоты */
.benefit-card{
  display:grid;
  grid-template-rows: 68px 56px 1fr; /* одинаковая высота зоны заголовка и иконки */
  gap:18px;
  min-height:380px;                  /* можно 360–420 */
  border-radius:20px;
  background: radial-gradient(100% 80% at 80% 0%, rgba(59,130,246,.08), transparent 60%),
              rgba(15,23,42,.42);
  border:1px solid rgba(255,255,255,.12);
  box-shadow: 0 12px 40px rgba(2,6,23,.35), inset 0 1px 0 rgba(255,255,255,.06);
  backdrop-filter: blur(8px);
}

/* заголовок ровно внизу своей строки */
.benefit-card .benefit-title{ 
  align-self:end;
  text-align:center;
  line-height:1.15;
}

/* иконка идеально по центру своей строки */
.benefit-card .icon-wrap{
  align-self:center; justify-self:center;
  width:56px; height:56px; border-radius:9999px;
  background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.18);
  box-shadow:0 4px 18px rgba(59,130,246,.25); backdrop-filter: blur(4px);
}
.benefit-card .icon-wrap svg{ width:26px; height:26px; stroke:#fff; stroke-width:1.7; }

/* текст растягивается — нижние линии совпадают */
.benefit-card .benefit-text{ align-self:start; text-align:center; line-height:1.6; }

/* сетка с карточками — растянуть в высоту и сделать шире */
.benefits-grid{ display:grid; gap:24px; align-items:stretch; }
@media (min-width: 768px){ .benefits-grid{ grid-template-columns: repeat(2, minmax(0,1fr)); } }
@media (min-width: 1280px){ .benefits-grid{ grid-template-columns: repeat(4, minmax(0,1fr)); } }

/* Заголовок выравниваем по центру в своей строке */
.benefit-card h3{
  align-self:end;               /* вниз строки, чтобы отступ сверху был ровный */
  text-align:center;
  line-height:1.15;
}

/* Иконка всегда точно по центру своей строки */
.benefit-card .icon-wrap{
  align-self:center;
  justify-self:center;

  width: 56px;
  height: 56px;
  margin: 0;                    /* убираем лишние внешние отступы */
  border-radius: 9999px;
  background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.18);
  box-shadow: 0 4px 18px rgba(59,130,246,.25);
  backdrop-filter: blur(4px);
}
.benefit-card .icon-wrap svg{
  width: 26px;
  height: 26px;
  stroke:#fff; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round;
}

/* Текст растягивается до низа — у всех карточек одинаковое «дно» */
.benefit-card p{
  align-self:start;
  text-align:center;
  color: rgba(226,232,240,.92); /* бело-серый */
  line-height:1.6;
}

/* Контейнер с карточками — тянем все плитки на одну высоту */
.benefits-grid{
  display:grid;
  grid-template-columns: repeat(1, minmax(0,1fr));
  gap: 24px;
}
@media (min-width: 768px){
  .benefits-grid{ grid-template-columns: repeat(2, minmax(0,1fr)); }
}
@media (min-width: 1024px){
  .benefits-grid{ grid-template-columns: repeat(4, minmax(0,1fr)); }
}
.icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 9999px;
  margin: 14px auto 20px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.18);
  box-shadow: 0 4px 18px rgba(59, 130, 246, 0.25);
  backdrop-filter: blur(4px);
}

/* SVG-иконка */
.icon-wrap svg {
  width: 26px;
  height: 26px;
  stroke: #ffffff;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* ---- Glass panel (жирнее стекло, аккуратный градиент-бордер) ---- */
.glass {
  background: rgba(9, 14, 28, .55);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  border-radius: 24px;
  border: 1px solid rgba(96,165,250,.18);
  box-shadow:
    0 10px 30px rgba(2,6,23,.35),
    inset 0 1px 0 rgba(255,255,255,.06);
  position: relative;
}

.glass::before{
  /* «неоновый» тонкий градиент по краю */
  content:"";
  position:absolute; inset:-1px;
  border-radius: 24px;
  background: conic-gradient(
    from 180deg at 50% 50%,
    rgba(59,130,246,.35),
    rgba(96,165,250,.25),
    rgba(59,130,246,.35)
  );
  mask: linear-gradient(#0000 10px, #000 0) content-box, linear-gradient(#000, #000);
  -webkit-mask: linear-gradient(#0000 10px, #000 0) content-box, linear-gradient(#000, #000);
  -webkit-mask-composite: xor; mask-composite: exclude;
  padding: 1px; opacity:.35; pointer-events:none;
}

.glass:hover{ transform: translateY(-3px); transition: transform .25s ease; }
.glass .title { letter-spacing:.2px }

/* контейнер шире и блок выше */
.section-roomy{ padding-block: clamp(96px, 14vw, 180px); }
.maxw-xl { max-width: min(1400px, 92vw); }

/* фоновая «аура», чтобы не было пусто */
.bg-aura{
  position:absolute; inset:0; z-index:-1;
  background:
    radial-gradient(38% 24% at 20% 15%, rgba(59,130,246,.12) 0, rgba(59,130,246,0) 60%),
    radial-gradient(34% 22% at 80% 12%, rgba(96,165,250,.10) 0, rgba(96,165,250,0) 60%),
    radial-gradient(50% 60% at 50% 100%, rgba(2,6,23,.65) 0, rgba(2,6,23,.85) 60%);
}

/* карточки повыше и просторнее на больших экранах */
@media (min-width: 1024px){
  .benefit-card{ height: 300px; }
}
@media (min-width: 1280px){
  .benefit-card{ height: 320px; }
}
/* --- HOW: крупные карточки одинаковой высоты + стрелки --- */
.step-card{
  text-align:center;
  padding: clamp(22px,2.6vw,36px);
  min-height: clamp(220px, 28vh, 320px);
  display:flex; flex-direction:column; justify-content:center; align-items:center;
  border-radius: 22px;
}
.step-title{ font-weight:800; line-height:1.1 }
.step-text{ color: rgba(255,255,255,.86) }

/* стекло + обводка как на выгодах */
.step-card.glass{
  background: rgba(15,23,42,.26);
  -webkit-backdrop-filter: saturate(140%) blur(14px);
  backdrop-filter: saturate(140%) blur(14px);
  border: 1px solid rgba(255,255,255,.18);
  box-shadow: 0 18px 55px rgba(2,6,23,.45);
  position:relative;
}
.step-card.glass::before{
  content:""; position:absolute; inset:-1px; border-radius:inherit; z-index:-1;
  background: linear-gradient(135deg,#60a5fa, #3b82f6 55%, rgba(99,102,241,.9));
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude;
  padding:1px; opacity:.55;
}

/* сетка: карточка — стрелка — карточка — стрелка — карточка */
.flow-grid{
  display:grid;
  grid-template-columns: 1fr auto 1fr auto 1fr;
  gap: clamp(18px,2vw,28px);
  align-items:center;
}

/* горизонтальная стрелка */
.conn{ width: clamp(40px, 10vw, 160px); height:2px; position:relative;
  background: linear-gradient(90deg, rgba(96,165,250,.0), rgba(96,165,250,.65));
  border-radius:2px; opacity:.9;
}
.conn::after{ content:""; position:absolute; right:-8px; top:50%; transform:translateY(-50%);
  border-left:10px solid rgba(96,165,250,.85);
  border-top:6px solid transparent; border-bottom:6px solid transparent;
}

/* адаптив: в колонку без стрелок */
@media (max-width: 1024px){
  .flow-grid{ grid-template-columns: 1fr; }
  .conn{ display:none; }
}

/* крупнее секция */
.section-how-big{ padding-block: clamp(120px,16vw,220px); min-height: 90vh; }

/* акцентный градиентный бордер без разрушения blur */
.accent-ring{
  position: relative;
  border-radius: 1.25rem; /* совпадает с rounded-3xl/2xl у карточек */
}
.accent-ring::before{
  content:""; position:absolute; inset:-1px; border-radius:inherit; z-index:-1;
  background: linear-gradient(135deg,#60a5fa, #3b82f6 55%, rgba(99,102,241,.9));
  filter: saturate(130%);
  /* показываем только рамку */
  -webkit-mask: 
    linear-gradient(#000 0 0) content-box, 
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude;
  padding:1px;
  opacity: var(--ring-alpha,.55);
}
.glass-strong{
  background: rgba(15,23,42,.26);
  -webkit-backdrop-filter: saturate(140%) blur(var(--g-blur,14px));
  backdrop-filter: saturate(140%) blur(var(--g-blur,14px));
  border: 1px solid rgba(255,255,255,.18);
  box-shadow: 0 18px 55px rgba(2,6,23,.45);
}
.card-3d{ transform: translateZ(0); transition: transform .35s ease, box-shadow .35s ease; }
.card-3d:hover{ transform: translateY(-6px); box-shadow: 0 26px 75px rgba(2,6,23,.55); }

/* маленький светящийся кружок-акцент в углу карточки */


/* фон-украшение секции: мягкие пятна */
.benefits-ornament{
  position:absolute; inset:0; z-index:-1; pointer-events:none;
  background:
    radial-gradient(600px 260px at 15% 25%, rgba(59,130,246,.18), transparent 60%),
    radial-gradient(700px 300px at 85% 40%, rgba(96,165,250,.14), transparent 65%);
}
.section-huge{ padding-block: clamp(120px, 16vw, 220px); } /* масштабнее секция */

/* Единый стеклянный стиль карточек */
.glass{
  position: relative;
  background: rgba(15, 23, 42, .28);             /* тёмная база, не перекрывает фон */
  border: 1px solid rgba(255,255,255,.18);
  box-shadow: 0 12px 40px rgba(0,0,0,.35);
  -webkit-backdrop-filter: saturate(140%) blur(var(--g-blur,14px));
  backdrop-filter: saturate(140%) blur(var(--g-blur,14px));
}
/* лёгкий блик по диагонали — добавляет «стеклянности» */
.glass::after{
  content:""; position:absolute; inset:0; pointer-events:none;
  background: linear-gradient(135deg, rgba(255,255,255,.22), rgba(255,255,255,0) 55%);
  opacity:.35; mix-blend-mode:screen; border-radius: inherit;
}
/* важный момент: свой стеклянный контекст, чтобы blur работал поверх фоновой картинки */
.section-has-glass{ isolation:isolate; }
}

/* маленький круглый бейдж вместо цифр */
.icon-badge{
  width: 42px; height: 42px; border-radius: 12px;
  display:grid; place-items:center;
  background: linear-gradient(135deg,#3b82f6,#60a5fa);
  color:white; font-weight:700;
}

  body{font-family:'Inter',system-ui,Arial}

  /* полноширинные секции и анимация */
  .full-bleed{position:relative;left:50%;right:50%;margin-left:-50vw;margin-right:-50vw;width:100vw}
  .section-min{min-height:min(92vh,1200px)}
  .reveal{opacity:0;transform:translateY(32px);transition:all .7s ease}
  .reveal.visible{opacity:1;transform:none}

  /* фон-картинка */
  .bg-layer{position:absolute;inset:0;z-index:-2;background-size:cover;background-position:center;background-repeat:no-repeat}

  /* универсальная плашка (затемнение + стекло) */
  .text-plate{
    background: var(--plate-bg, rgba(2,6,23,.50));
    -webkit-backdrop-filter: blur(var(--plate-blur,8px));
    backdrop-filter: blur(var(--plate-blur,8px));
    border: 1px solid rgba(255,255,255,.12);
    box-shadow: 0 10px 30px rgba(0,0,0,.25);
  }

  /* растянуть плашку на весь блок и центрировать контент */
  .plate-full{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding-left:1.5rem;padding-right:1.5rem}

  /* полностью убрать фон/стекло у плашки */
  .plate-clear{--plate-bg:transparent;--plate-blur:0px;box-shadow:none!important;border-color:transparent!important}
  .collapsible{
    overflow: hidden;
    max-height: 0;              /* скрыт по умолчанию */
    opacity: .0;
    transition: max-height .40s ease, opacity .25s ease;
  }
  .collapsible.open{
    opacity: 1;
    .sticky-first-col th:first-child,
.sticky-first-col td:first-child{
  position: sticky; left: 0;
  background-color: rgb(15 23 42 / 0.7); /* bg-slate-900/70 */
  backdrop-filter: blur(6px);
  z-index: 1;
}
.tabular-nums{ font-variant-numeric: tabular-nums; }
  }
.sticky-first-col th:first-child,
.sticky-first-col td:first-child{
  position: sticky; left: 0;
  background-color: rgb(15 23 42 / 0.7); /* bg-slate-900/70 */
  backdrop-filter: blur(6px);
  z-index: 1;
}
.tabular-nums{ font-variant-numeric: tabular-nums; }
</style>
"""



def page_wrap(inner_html: str, title="Kontrola"):
    tpl = """<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__TITLE__</title>""" + BRAND_HEAD + """
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex flex-col">  <!-- добавили min-h-screen flex flex-col -->
__TOPBAR__
<main class="flex-1">  <!-- контент растягивается, футер уходит вниз -->
__INNER__
</main>
__FOOTER__
<script>
  const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('visible'); io.unobserve(e.target);}})},{threshold:.12});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));

  // мини-бейдж корзины
  (async ()=>{
    try{
      const r = await fetch('/api/cart');
      const j = await r.json();
      if(j.ok){
        const cnt = (j.data.items||[]).reduce((s,it)=>s+Number(it.qty||0),0);
        const a = document.querySelector('a[href="/cart"]');
        if(a && cnt>0){
          const b = document.createElement('span');
          b.className = 'ml-2 inline-flex items-center justify-center text-[10px] px-1.5 py-0.5 rounded bg-brand/80';
          b.textContent = cnt;
          a.appendChild(b);
        }
      }
    }catch(e){}
  })();
</script>
</body></html>"""
    # подставляем заранее собранные блоки
    html = tpl.replace("__TITLE__", title)\
              .replace("__INNER__", inner_html)\
              .replace("__TOPBAR__", TOPBAR)\
              .replace("__FOOTER__", FOOT_MINI)
    return html


# ---------- ГЛАВНАЯ: просто меняй URL в --bg-url у каждого блока ----------
@app.get("/")
def landing():
    html = f"""
<!-- HERO -->
<section class="relative full-bleed section-min reveal">
  <div class="bg-layer bg-center" style="background-image:url('https://www.globalinvestigations.co.uk/wp-content/uploads/2024/06/How-to-Run-a-Background-Check-on-Your-Business-Partner-1024x576.png')"></div>

  <div class="text-plate plate-full" style="--plate-bg: rgba(2,6,23,.55); --plate-blur: 12px;">
    <div class="w-[min(92%,1200px)] mx-auto py-10 md:py-16">
      <h1 class="text-5xl md:text-7xl font-extrabold leading-[1.05]">
        Моментальная проверка контрагента —<br class="hidden sm:block"/>
        <span class="text-transparent bg-clip-text bg-gradient-to-r from-brand to-brand2">
          прозрачность и безопасность для вашего бизнеса!
        </span>
      </h1>
      <p class="mt-6 text-lg md:text-xl text-white/90 max-w-3xl mx-auto">
        Вместо ручных проверок по десяткам источников — мгновенный анализ данных из ФНС,
        арбитража и реестров недобросовестных поставщиков.
      </p>
      <div class="mt-5">
        <a href="/about" class="text-white/90 underline underline-offset-4">Узнать подробнее о платформе</a>
      </div>
      <div class="mt-8 flex justify-center gap-4 flex-wrap">
        <a href="/checker" class="px-7 py-4 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold text-lg shadow-lg shadow-brand/30">Попробовать бесплатно</a>
        <a href="/pricing" class="px-7 py-4 rounded-2xl border border-white/20 hover:bg-white/5 text-lg">Тарифные планы</a>
      </div>
    </div>
  </div>
</section>

<!-- ВЫГОДЫ: шире, выше, 2×2 / 1×4, стекло + подсветка -->
<section id="benefits" class="relative full-bleed section-roomy reveal">
  <!-- фон-картинка по желанию -->
  <div class="bg-layer" style="background-image:url('/static/bg/benefits.jpg')"></div>
  <!-- мягкая аура поверх фото, чтобы не было пусто -->
  <div class="bg-aura"></div>

  <div class="relative z-10 maxw-xl mx-auto px-6">
    <h2 class="text-4xl md:text-5xl font-extrabold text-center">Выгоды для вашего бизнеса</h2>
    <p class="text-slate-300/90 text-center mt-4 text-lg md:text-xl">
      Сокращаем риски, экономим время и даём ясные выводы на базе проверенных источников.
    </p>

    <!-- сетка 2×2 на xl, 1×4 на lg, крупные карточки -->
    <div class="max-w-7xl mx-auto px-6 mt-10 benefits-grid items-stretch">

  <article class="benefit-card h-full p-7">
    <h3 class="text-2xl md:text-[26px] font-extrabold">Меньше рисков</h3>
    <div class="icon-wrap">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M12 3l7 4v5a7 7 0 0 1-7 7 7 7 0 0 1-7-7V7l7-4z"/>
        <path d="M9 12l2 2 4-4"/>
      </svg>
    </div>
    <p>Автопоиск судов, банкротств, РНП, санкций и СМИ-триггеров.</p>
  </article>

  <article class="benefit-card h-full p-7">
    <h3 class="text-2xl md:text-[26px] font-extrabold">Экономия времени</h3>
    <div class="icon-wrap">
      <svg viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9"/>
        <path d="M12 7v5l3 2"/>
      </svg>
    </div>
    <p>Одна форма вместо десятков реестров. Результат за секунды.</p>
  </article>

  <article class="benefit-card h-full p-7">
    <h3 class="text-2xl md:text-[26px] font-extrabold">Единый отчёт</h3>
    <div class="icon-wrap">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M3 3h18v18H3zM8 17v-7m4 7V7m4 10v-4"/>
      </svg>
    </div>
    <p>Графики, коэффициенты, выводы и класс устойчивости.</p>
  </article>

  <article class="benefit-card h-full p-7">
    <h3 class="text-2xl md:text-[26px] font-extrabold">Интеграции</h3>
    <div class="icon-wrap">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M9 18H5a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h4m6 7h4a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2h-4M8 12h8"/>
      </svg>
    </div>
    <p>API и веб-хуки для CRM/ERP и ваших сервисов.</p>
  </article>

</div>
  </div>
</section>

<!-- КАК ЭТО РАБОТАЕТ (ровно, крупно, без лишних значков) -->
<section id="how" class="relative full-bleed section-how-big reveal">
  <!-- фон -->
  <div class="bg-layer" style="background-image:url('https://www.cisa.gov/sites/default/files/styles/hero_large/public/2023-01/AdobeStock_226321806.jpg?h=76537120&itok=i4Dfv1rJ')"></div>
  <!-- общий читаемый слой -->
  <div class="text-plate plate-full" style="--plate-bg: rgba(2,6,23,.40); --plate-blur: 10px;">
    <div class="w-[min(96%,1400px)] mx-auto">

      <header class="text-center">
        <h2 class="text-5xl md:text-6xl font-extrabold leading-tight">Как это работает</h2>
        <p class="mt-5 text-xl md:text-2xl text-white/85">
          Три шага — и у вас готовая картина по контрагенту.
        </p>
      </header>

      <div class="mt-14 flow-grid">
        <!-- Шаг 1 -->
        <article class="step-card glass">
          <h3 class="step-title text-9xl md:text-4xl">Введите ИНН</h3>
          <p class="step-text mt-4 text-lg md:text-xl">
            Проверим формат и подготовим запросы к реестрам.
          </p>
        </article>

        <div class="conn"></div>

        <!-- Шаг 2 -->
        <article class="step-card glass">
          <h3 class="step-title text-9xl md:text-4xl">Анализ источников</h3>
          <p class="step-text mt-4 text-lg md:text-xl">
            ФНС, арбитраж, РНП, санкции, СМИ — агрегируем и очищаем.
          </p>
        </article>

        <div class="conn"></div>

        <!-- Шаг 3 -->
        <article class="step-card glass">
          <h3 class="step-title text-9xl md:text-4xl">Отчёт и выводы</h3>
          <p class="step-text mt-4 text-lg md:text-xl">
            Графики, коэффициенты, класс устойчивости и рекомендации.
          </p>
        </article>
      </div>

    </div>
  </div>
</section>

<!-- ЦИФРЫ И ФАКТЫ: крупнее, с "стеклом", визуально на уровне "Выгод" -->
<section id="facts" class="relative full-bleed reveal section-has-glass section-facts-tight">
  <div class="bg-layer" style="background-image:url('/static/bg/facts.jpg')"></div>

  <div class="text-plate plate-full" style="--plate-bg: rgba(2,6,23,.42); --plate-blur: 10px;">
    <div class="w-[min(96%,1280px)] mx-auto py-16 md:py-20">

      <header class="text-center mb-12">
        <h2 class="text-4xl md:text-5xl font-extrabold leading-tight">Цифры и факты</h2>
        <p class="mt-4 text-lg md:text-xl text-white/85">
          Жёсткие метрики, которые подтверждают стабильность и эффективность платформы.
        </p>
      </header>

      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-7 items-stretch">
        <article class="glass rounded-3xl p-10 md:p-12 text-center" style="--g-blur:14px">
          <h3 class="text-5xl md:text-6xl font-extrabold text-white mb-2">~1с</h3>
          <p class="text-xl md:text-2xl font-semibold">Среднее время ответа</p>
          <p class="mt-2 text-white/80 text-base md:text-lg">Скорость — наше всё.</p>
        </article>

        <article class="glass rounded-3xl p-10 md:p-12 text-center" style="--g-blur:14px">
          <h3 class="text-5xl md:text-6xl font-extrabold text-white mb-2">25+</h3>
          <p class="text-xl md:text-2xl font-semibold">Источников данных</p>
          <p class="mt-2 text-white/80 text-base md:text-lg">Госреестры, арбитраж, СМИ и др.</p>
        </article>

        <article class="glass rounded-3xl p-10 md:p-12 text-center" style="--g-blur:14px">
          <h3 class="text-5xl md:text-6xl font-extrabold text-white mb-2">10k+</h3>
          <p class="text-xl md:text-2xl font-semibold">Проверок в сутки</p>
          <p class="mt-2 text-white/80 text-base md:text-lg">Без деградации производительности.</p>
        </article>

        <article class="glass rounded-3xl p-10 md:p-12 text-center" style="--g-blur:14px">
          <h3 class="text-5xl md:text-6xl font-extrabold text-white mb-2">1000+</h3>
          <p class="text-xl md:text-2xl font-semibold">Довольных клиентов</p>
          <p class="mt-2 text-white/80 text-base md:text-lg">Бизнес доверяет нашим данным ежедневно.</p>
        </article>
      </div>
    </div>
  </div>
</section>
<!-- ФОРМА -->
<section id="lead" class="relative full-bleed section-min reveal">
  <!-- можно оставить без картинки; пример с мягким градиентом -->
   <div class="bg-layer" style="background-image:url('https://listentrust.com/wp-content/uploads/2024/03/Group-of-happy-call-center-smiling-business-operator-customer-support-team-phone-services-agen-working-and-talking-with-headset-on-desktop-computer-at-call-center-1024x640.jpg')"></div>

  <div class="text-plate plate-full" style="--plate-bg: rgba(2,6,23,.70); --plate-blur: 8px;">
    <div class="w-[min(90%,900px)] mx-auto py-10 md:py-14 text-left">
      <h2 class="text-2xl md:text-3xl font-extrabold mb-4 text-center">Заполните форму и мы свяжемся с вами!</h2>
      <form class="mt-6 grid md:grid-cols-2 gap-5" method="post" action="/lead">
        <input name="name" required placeholder="Ваше имя*" class="px-5 py-4 rounded-2xl bg-black/10 border border-white/10 text-white placeholder-white/60">
        <input name="company" placeholder="Название компании" class="px-5 py-4 rounded-2xl bg-black/10 border border-white/10 text-white placeholder-white/60">
        <input name="role" placeholder="Должность" class="px-5 py-4 rounded-2xl bg-black/10 border border-white/10 text-white placeholder-white/60"">
        <input name="industry" placeholder="Сфера деятельности компании" class="px-5 py-4 rounded-2xl bg-black/10 border border-white/10 text-white placeholder-white/60">
        <input name="phone" placeholder="Телефон" class="px-5 py-4 rounded-2xl bg-black/10 border border-white/10 text-white placeholder-white/60">
        <input name="email" type="email" required placeholder="Email*" class="px-5 py-4 rounded-2xl bg-black/10 border border-white/10 text-white placeholder-white/60">
        <textarea name="comment" rows="5" placeholder="Комментарии" class="md:col-span-2 px-5 py-4 rounded-2xl bg-black/10 border border-white/10 text-white placeholder-white/60"></textarea>
        <label class="md:col-span-2 flex items-start gap-3 text-sm"><input type="checkbox" required class="mt-1"><span>Соглашаюсь с условиями обработки ПДн и политикой конфиденциальности.</span></label>
        <div class="md:col-span-2"><button class="px-7 py-4 rounded-2xl bg-white text-slate-900 font-semibold text-lg">Отправить</button></div>
      </form>
    </div>
  </div>
</section>
"""
    return Response(page_wrap(html, "Kontrola — лендинг с картинками и плашкой-оверлеем"), mimetype="text/html; charset=utf-8")





TOPBAR = """
<header class="fixed top-0 inset-x-0 z-50 bg-slate-950/70 backdrop-blur border-b border-white/10">
  <div class="max-w-7xl mx-auto px-6 h-[68px] flex items-center justify-between">
    <!-- ЛОГО + НАЗВАНИЕ -->
    <a href="/" class="flex items-center gap-2 shrink-0">
      <img src="/logo.png" alt="Kontrola" class="h-12 w-12 object-contain" />
      <span class="font-extrabold tracking-tight text-lg">Kontrola</span>
    </a>

    <!-- НАВИГАЦИЯ (центр) -->
    <nav class="hidden md:flex items-center gap-8 text-sm text-slate-300">
      <a href="/about"    class="hover:text-white">О компании</a>
      <a href="/pricing"  class="hover:text-white">Тарифы</a>
      <a href="/checker"  class="hover:text-white">Проверка ИНН</a>
      <a href="/contacts" class="hover:text-white">Контакты</a>
      <a href="https://t.me/+SK172iYnnUNhYWNi" target="_blank" class="hover:text-brand transition-colors" title="Telegram">
  <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 inline-block" fill="currentColor" viewBox="0 0 24 24">
    <path d="M9.75 15.02L9.53 18.96c.5 0 .72-.21.98-.47l2.35-2.23 4.87 3.58c.89.5 1.52.24 1.75-.83l3.18-14.92.01-.01c.28-1.31-.47-1.82-1.33-1.5L1.61 9.17c-1.29.5-1.27 1.21-.22 1.53l5.75 1.79 13.34-8.41c.63-.4 1.21-.18.74.25"/>
  </svg>
</a>
<a href="mailto:info@kontrola.tech" class="hover:text-brand transition-colors" title="E-mail">
  <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 inline-block" fill="currentColor" viewBox="0 0 24 24">
    <path d="M12 13.065L.605 4.5h22.79L12 13.065zM0 5.743V20h24V5.743L12 14.308 0 5.743z"/>
  </svg>
</a>
    </nav>

    <!-- ДЕЙСТВИЯ (справа) -->
    <div class="flex items-center gap-2">
      <a href="/cart" class="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-800/60 ring-1 ring-white/10 hover:bg-slate-700/60 transition">
        <svg viewBox="0 0 24 24" class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.6">
          <circle cx="9" cy="19" r="1.6"/>
          <circle cx="17" cy="19" r="1.6"/>
          <path d="M3 4h2l1.4 8.4A2 2 0 0 0 8.4 14h7.7a2 2 0 0 0 1.9-1.5L20 8H6"/>
        </svg>
        <span class="hidden sm:inline">Корзина</span>
      </a>
      <a href="/login" class="px-3 py-2 rounded-xl border border-white/15 hover:bg-white/10 transition">Вход</a>
      <a href="/register" class="px-3 py-2 rounded-xl bg-brand text-white hover:bg-brand2 transition">Регистрация</a>
    </div>
  </div>
</header>
<div class="h-[68px]"></div>
"""

FOOT_MINI = """
<footer class="py-8 text-center text-sm text-slate-400 mt-auto">
  <div class="flex justify-center gap-5 mb-3">
    <a href="https://t.me/+SK172iYnnUNhYWNi" target="_blank" class="hover:text-brand transition-colors" title="Telegram">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 inline-block" fill="currentColor" viewBox="0 0 24 24">
        <path d="M9.75 15.02L9.53 18.96c.5 0 .72-.21.98-.47l2.35-2.23 4.87 3.58c.89.5 1.52.24 1.75-.83l3.18-14.92.01-.01c.28-1.31-.47-1.82-1.33-1.5L1.61 9.17c-1.29.5-1.27 1.21-.22 1.53l5.75 1.79 13.34-8.41c.63-.4 1.21-.18.74.25"/>
      </svg>
    </a>
    <a href="mailto:info@kontrola.tech" class="hover:text-brand transition-colors" title="E-mail">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 inline-block" fill="currentColor" viewBox="0 0 24 24">
        <path d="M12 13.065L.605 4.5h22.79L12 13.065zM0 5.743V20h24V5.743L12 14.308 0 5.743z"/>
      </svg>
    </a>
  </div>
  <div>© 2025 Kontrola — Платформа проверки контрагентов</div>
  <div class="mt-1 text-xs text-slate-500">
    <a href="/rules" class="hover:text-slate-300">Правила</a> • 
    <a href="/contacts" class="hover:text-slate-300">Контакты</a>
  </div>
</footer>
"""

# ---------- Thank you ----------
@app.post("/lead")
def lead_post():
    data = {k:(request.form.get(k) or "").strip() for k in ["name","company","role","industry","phone","email","comment"]}
    inner = f"""
<section class="full-bleed bg-slate-900">
  <div class="max-w-4xl mx-auto px-6 py-24 md:py-32">
    <div class="p-8 rounded-3xl bg-slate-800/60 ring-1 ring-white/10">
      <div class="text-2xl font-extrabold">Спасибо! Мы свяжемся с вами.</div>
      <p class="text-slate-300 mt-2">Короткое резюме отправленных данных:</p>
      <div class="mt-6 grid sm:grid-cols-2 gap-4 text-sm text-slate-300">
        <div><span class="text-slate-400">Имя:</span> {data['name'] or '—'}</div>
        <div><span class="text-slate-400">Компания:</span> {data['company'] or '—'}</div>
        <div><span class="text-slate-400">Должность:</span> {data['role'] or '—'}</div>
        <div><span class="text-slate-400">Сфера:</span> {data['industry'] or '—'}</div>
        <div><span class="text-slate-400">Телефон:</span> {data['phone'] or '—'}</div>
        <div><span class="text-slate-400">Email:</span> {data['email'] or '—'}</div>
        <div class="sm:col-span-2"><span class="text-slate-400">Комментарий:</span> {data['comment'] or '—'}</div>
      </div>
      <div class="mt-6 flex gap-3">
        <a href="/" class="px-6 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">На главную</a>
        <a href="/pricing" class="px-6 py-3 rounded-2xl border border-white/10 hover:bg-white/5">Тарифы</a>
      </div>
    </div>
  </div>
</section>
"""
    return Response(page_wrap(inner, "Спасибо!"), mimetype="text/html; charset=utf-8")

# ---------- Плейсхолдеры ----------
@app.get("/about")
def about_page():
    inner = """
<section class="full-bleed section-roomy reveal relative overflow-hidden">
  <!-- Фоновая подложка -->
  <div class="bg-layer opacity-100" style="background-image:url('https://www.investopedia.com/thmb/SPOl62NtucSLHi9-XyGJxm-Wo68=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/GettyImages-943067460-28883b8136b24330932cd4e2855c2508.jpg'); background-size:cover; background-position:center;"></div>
  <div class="bg-aura absolute inset-0"></div>

  <div class="relative z-10 max-w-7xl mx-auto px-6">
    <header class="text-center max-w-3xl mx-auto">
      <h1 class="text-5xl font-extrabold">О компании</h1>
      <p class="text-slate-300 mt-4">
        Kontrola — финтех-платформа для моментальной проверки контрагентов. Мы объединяем данные из государственных реестров, судебных дел и закупок, 
        чтобы вы могли принимать решения быстрее и безопаснее.
      </p>
    </header>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12">
      <article class="glass rounded-3xl p-8 card-3d">
        <div class="text-sm text-slate-400">Миссия</div>
        <h3 class="text-xl font-extrabold mt-1">Прозрачность для бизнеса</h3>
        <p class="text-slate-300 mt-2">Мы упрощаем due diligence — теперь проверка партнёра занимает секунды, а не часы.</p>
      </article>
      <article class="glass rounded-3xl p-8 card-3d">
        <div class="text-sm text-slate-400">Подход</div>
        <h3 class="text-xl font-extrabold mt-1">Данные без фальши</h3>
        <p class="text-slate-300 mt-2">Нормализуем и агрегируем сведения из ФНС, ФССП, КАД, ЕИС и других источников — в одном API и одном отчёте.</p>
      </article>
      <article class="glass rounded-3xl p-8 card-3d">
        <div class="text-sm text-slate-400">Надёжность</div>
        <h3 class="text-xl font-extrabold mt-1">Безопасность и контроль</h3>
        <p class="text-slate-300 mt-2">Инфраструктура в РФ, шифрование на всех уровнях, аудит доступа и регламенты ISO-уровня.</p>
      </article>
    </div>

    <section class="mt-16 grid grid-cols-1 lg:grid-cols-2 gap-8">
      <article class="glass rounded-3xl p-8">
        <h3 class="text-2xl font-extrabold">Почему нас выбирают</h3>
        <ul class="mt-4 space-y-2 text-slate-300">
          <li>• Проверка контрагента в 1 клик</li>
          <li>• Универсальные API-интеграции</li>
          <li>• Отчёты с коэффициентами и аналитикой</li>
          <li>• Поддержка в мессенджерах и по API</li>
        </ul>
      </article>
      <article class="glass rounded-3xl p-8">
        <h3 class="text-2xl font-extrabold">Эффект для бизнеса</h3>
        <p class="text-slate-300 mt-3">
          Мы помогаем компаниям снижать риски, экономить время и строить прозрачные отношения с партнёрами.
        </p>
        <div class="mt-6 grid grid-cols-3 gap-4 text-center">
          <div><div class="text-3xl font-extrabold">~1 c</div><div class="text-sm text-slate-400">скорость проверки</div></div>
          <div><div class="text-3xl font-extrabold">25+</div><div class="text-sm text-slate-400">источников</div></div>
          <div><div class="text-3xl font-extrabold">10k+</div><div class="text-sm text-slate-400">проверок/день</div></div>
        </div>
      </article>
    </section>

    <div class="mt-16 text-center">
      <a href="/checker" class="px-6 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">Попробовать проверку</a>
      <a href="/pricing" class="ml-3 px-6 py-3 rounded-2xl border border-white/15 hover:bg-white/10">Тарифы</a>
    </div>
  </div>
</section>
"""
    return Response(page_wrap(inner, "О компании — Kontrola"), mimetype="text/html; charset=utf-8")
    return Response(page_wrap(inner, "О компании — Kontrola"), mimetype="text/html; charset=utf-8")

@app.get("/pricing")
def pricing_page():
    inner = """
<section class="full-bleed section-roomy reveal">
  <div class="bg-layer" style="background-image:url('/static/bg/benefits.jpg')"></div>
  <div class="bg-aura"></div>
  <div class="relative z-10 max-w-7xl mx-auto px-6">
    <header class="text-center">
      <h1 class="text-5xl font-extrabold">Тарифные планы</h1>
      <p class="text-slate-300 mt-3">Выберите подписку или пополните баланс для разовых проверок</p>
    </header>

    <div class="mt-10 grid grid-cols-1 md:grid-cols-3 gap-6">
      <!-- Месяц -->
      <article class="glass rounded-3xl p-8 card-3d">
        <div class="text-sm text-slate-400">Подписка</div>
        <h3 class="text-2xl font-extrabold mt-1">Месяц</h3>
        <div class="mt-4 text-4xl font-extrabold">__PRICE_MONTH__ ₽<span class="text-base font-semibold text-slate-400">/мес</span></div>
        <ul class="mt-5 space-y-2 text-slate-300 text-sm">
          <li>Полный доступ 30 дней</li>
          <li>API и выгрузки</li>
          <li>Базовая поддержка</li>
        </ul>
        <button id="add-month" class="mt-6 w-full px-5 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">В корзину</button>
      </article>

      <!-- Год (выгода) -->
      <article class="glass rounded-3xl p-8 ring-2 ring-brand/40 relative card-3d">
        <span class="absolute -top-3 right-4 text-xs px-2 py-1 rounded-full bg-brand/20 text-brand ring-1 ring-brand/40">Выгода</span>
        <div class="text-sm text-slate-400">Подписка</div>
        <h3 class="text-2xl font-extrabold mt-1">Год</h3>
        <div class="mt-4 text-4xl font-extrabold">__PRICE_YEAR__ ₽<span class="text-base font-semibold text-slate-400">/год</span></div>
        <p class="mt-1 text-sm text-emerald-400">Экономия 3 000 ₽ vs помесячно</p>
        <ul class="mt-5 space-y-2 text-slate-300 text-sm">
          <li>12 месяцев доступа</li>
          <li>Приоритетная поддержка</li>
          <li>Расширенные лимиты</li>
        </ul>
        <button id="add-year" class="mt-6 w-full px-5 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">В корзину</button>
      </article>

      <!-- Единоразовые проверки (кредиты) -->
      <article class="glass rounded-3xl p-8 card-3d">
        <div class="text-sm text-slate-400">Кредиты</div>
        <h3 class="text-2xl font-extrabold mt-1">Единоразовые проверки</h3>
        <div class="mt-4 text-4xl font-extrabold">300 ₽<span class="text-base font-semibold text-slate-400">/проверка</span></div>
        <ul class="mt-5 space-y-2 text-slate-300 text-sm">
          <li>Оплата только за факт проверки</li>
          <li>Без подписки</li>
          <li>Списывается с баланса</li>
        </ul>
        <a href="/balance" class="mt-6 w-full inline-block text-center px-5 py-3 rounded-2xl border border-white/15 hover:bg-white/10">Пополнить баланс</a>
      </article>
    </div>

    <div class="mt-8 flex flex-wrap gap-3 justify-center">
      <a href="/cart" class="px-5 py-3 rounded-2xl bg-white/10 ring-1 ring-white/10 hover:bg-white/15">Перейти в корзину</a>
    </div>
  </div>
</section>

<script>
  async function add(sku){
    const r = await fetch('/api/cart/add', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({sku})});
    const j = await r.json();
    if(j.ok && j.data?.redirect){ window.location = j.data.redirect; return; }
    if(j.ok){ alert('Добавлено в корзину'); }
  }
  document.getElementById('add-month').addEventListener('click', ()=>add('sub_month'));
  document.getElementById('add-year').addEventListener('click',  ()=>add('sub_year'));
</script>
"""
    inner = inner.replace("__PRICE_MONTH__", f"{CATALOG['sub_month']['price']:,}".replace(",", " "))
    inner = inner.replace("__PRICE_YEAR__",  f"{CATALOG['sub_year']['price']:,}".replace(",", " "))
    return Response(page_wrap(inner, "Тарифы — Kontrola"), mimetype="text/html; charset=utf-8")

@app.get("/checker")
def checker_page():
    html = """
<section id="checker" class="py-14 reveal">
  <div class="max-w-7xl mx-auto px-4">
    <!-- ВВОД ИНН -->
    <div class="p-6 rounded-2xl bg-slate-800/60 ring-1 ring-white/10">
      <div class="text-sm text-slate-300">Введите ИНН</div>
      <div class="mt-2 flex gap-3 flex-wrap">
        <input id="inn" type="text"
               placeholder="Например, 7707083893"
               class="flex-1 min-w-[260px] px-4 py-3 rounded-xl bg-slate-900 border border-white/10 outline-none focus:ring-2 focus:ring-brand"/>
        <button id="btn"
                class="px-5 py-3 rounded-xl bg-gradient-to-br from-brand to-brand2 font-semibold shadow-lg shadow-brand/30">
          Проверить
        </button>
      </div>
      <div id="status" class="mt-2 text-sm text-slate-400"></div>
      <div id="company" class="mt-6"></div>
    </div>
    
    <!-- КНОПКА + ПАНЕЛЬ ОТЧЁТНОСТИ -->
<div class="mt-6">
  <button id="toggle-report"
          class="w-full px-5 py-3 rounded-xl bg-white/[0.04] hover:bg-white/[0.06] ring-1 ring-white/10 text-left flex items-center justify-between disabled:opacity-60 disabled:cursor-not-allowed"
          disabled>
    <span id="toggle-label" class="font-semibold">Показать отчётность</span>
    <span id="report-badge" class="text-xs px-2 py-1 rounded-lg bg-brand/20 text-brand">—</span>
  </button>

  <div id="report-panel" class="collapsible mt-3">
    <div class="p-4 rounded-2xl bg-slate-800/60 ring-1 ring-white/10">
      <div class="text-sm text-slate-300 mb-2">Таблица показателей</div>

      <!-- ЕДИНСТВЕННЫЙ скролл-контейнер -->
      <div id="tblWrap" class="overflow-auto rounded-lg ring-1 ring-white/10 cursor-grab">
        <table id="tbl" class="min-w-full text-sm sticky-first-col"></table>
      </div>
    </div>
  </div>
</div>

    <!-- ГРАФИКИ: вертикально, один за другим -->
<div class="flex flex-col gap-6 items-stretch mt-6">
  <div class="p-6 rounded-2xl bg-slate-800/60 ring-1 ring-white/10 relative">
    <div id="ph1" class="absolute inset-0 flex items-center justify-center text-slate-400">
      Загрузите данные — здесь появятся графики выручки и прибыли
    </div>
    <canvas id="chart1" height="200"></canvas>
  </div>

  <div class="p-6 rounded-2xl bg-slate-800/60 ring-1 ring-white/10 relative">
    <div id="ph2" class="absolute inset-0 flex items-center justify-center text-slate-400">
      Загрузите данные — здесь появятся коэффициенты на графике
    </div>
    <canvas id="chart2" height="200"></canvas>
  </div>
</div>
<!-- ВНЕШНИЕ ПОКАЗАТЕЛИ (OFDATA) -->
<div id="external-panels" class="mt-6 space-y-6">
  <!-- Госзакупки -->
  <section class="p-6 rounded-2xl bg-slate-800/60 ring-1 ring-white/10">
    <div class="flex items-center justify-between">
      <h3 class="text-lg font-bold">Госзакупки (ЕИС)</h3>
      <div id="gp-badge" class="text-xs px-2 py-1 rounded-lg bg-brand/20 text-brand">—</div>
    </div>
    <div id="gp-cnts" class="mt-3 grid sm:grid-cols-2 gap-3 text-sm text-slate-300">
      <div>Как поставщик: <span id="gp-supp-cnt" class="font-semibold">—</span>,
          сумма: <span id="gp-supp-sum" class="font-semibold">—</span></div>
      <div>Как заказчик: <span id="gp-cust-cnt" class="font-semibold">—</span>,
          сумма: <span id="gp-cust-sum" class="font-semibold">—</span></div>
    </div>
    <div class="mt-3">
  <button class="px-4 py-2 rounded-xl bg-white/5 ring-1 ring-white/10 hover:bg-white/10"
          data-open="contracts">Показать детали</button>
</div>
<div id="list-contracts" class="mt-3 hidden">
  <div class="flex gap-2 flex-wrap text-sm">
    <select id="flt-law" class="px-2 py-1 rounded-lg bg-white/5 ring-1 ring-white/10">
      <option value="">law: все</option><option>44</option><option>94</option><option>223</option>
    </select>
    <select id="flt-role" class="px-2 py-1 rounded-lg bg-white/5 ring-1 ring-white/10">
      <option value="">role: обе</option><option value="customer">customer</option><option value="supplier">supplier</option>
    </select>
  </div>
  <div class="mt-2 overflow-auto ring-1 ring-white/10 rounded-lg">
    <table id="tbl-contracts" class="min-w-full text-sm"></table>
  </div>
  <div class="mt-2 flex items-center gap-2 text-sm">
    <button class="px-3 py-1 rounded-lg bg-white/5 ring-1 ring-white/10" data-prev="contracts">Назад</button>
    <span id="pg-contracts"></span>
    <button class="px-3 py-1 rounded-lg bg-white/5 ring-1 ring-white/10" data-next="contracts">Вперёд</button>
  </div>
</div>
  </section>

  <!-- Проверки -->
  <section class="p-6 rounded-2xl bg-slate-800/60 ring-1 ring-white/10">
    <div class="flex items-center justify-between">
      <h3 class="text-lg font-bold">Проверки (ФГИС ЕРП)</h3>
      <div id="insp-badge" class="text-xs px-2 py-1 rounded-lg bg-brand/20 text-brand">—</div>
    </div>
    <div id="insp-info" class="mt-3 text-sm text-slate-300">—</div>
    <div class="mt-3">
  <button class="px-4 py-2 rounded-xl bg-white/5 ring-1 ring-white/10 hover:bg-white/10" data-open="inspections">Показать детали</button>
</div>
<div id="list-inspections" class="mt-3 hidden">
  <div class="overflow-auto ring-1 ring-white/10 rounded-lg">
    <table id="tbl-inspections" class="min-w-full text-sm"></table>
  </div>
  <div class="mt-2 flex items-center gap-2 text-sm">
    <button class="px-3 py-1 rounded-lg bg-white/5 ring-1 ring-white/10" data-prev="inspections">Назад</button>
    <span id="pg-inspections"></span>
    <button class="px-3 py-1 rounded-lg bg-white/5 ring-1 ring-white/10" data-next="inspections">Вперёд</button>
  </div>
</div>

  </section>

  <!-- Исполн. производства -->
  <section class="p-6 rounded-2xl bg-slate-800/60 ring-1 ring-white/10">
    <div class="flex items-center justify-between">
      <h3 class="text-lg font-bold">Исполнительные производства (ФССП)</h3>
      <div id="enf-badge" class="text-xs px-2 py-1 rounded-lg bg-brand/20 text-brand">—</div>
    </div>
    <div id="enf-info" class="mt-3 text-sm text-slate-300">—</div>
    <div class="mt-3">
  <button class="px-4 py-2 rounded-xl bg-white/5 ring-1 ring-white/10 hover:bg-white/10" data-open="enforcements">Показать детали</button>
</div>
<div id="list-enforcements" class="mt-3 hidden">
  <div class="overflow-auto ring-1 ring-white/10 rounded-lg">
    <table id="tbl-enforcements" class="min-w-full text-sm"></table>
  </div>
  <div class="mt-2 flex items-center gap-2 text-sm">
    <button class="px-3 py-1 rounded-lg bg-white/5 ring-1 ring-white/10" data-prev="enforcements">Назад</button>
    <span id="pg-enforcements"></span>
    <button class="px-3 py-1 rounded-lg bg-white/5 ring-1 ring-white/10" data-next="enforcements">Вперёд</button>
  </div>
</div>
  </section>

  <!-- Арбитраж -->
  <section class="p-6 rounded-2xl bg-slate-800/60 ring-1 ring-white/10">
    <div class="flex items-center justify-between">
      <h3 class="text-lg font-bold">Арбитражные дела (КАД)</h3>
      <div id="lc-badge" class="text-xs px-2 py-1 rounded-lg bg-brand/20 text-brand">—</div>
    </div>
    <div id="lc-info" class="mt-3 text-sm text-slate-300">—</div>
    <div class="mt-3">
  <button class="px-4 py-2 rounded-xl bg-white/5 ring-1 ring-white/10 hover:bg-white/10" data-open="arbitr">Показать детали</button>
</div>
<div id="list-arbitr" class="mt-3 hidden">
  <div class="overflow-auto ring-1 ring-white/10 rounded-lg">
    <table id="tbl-arbitr" class="min-w-full text-sm"></table>
  </div>
  <div class="mt-2 flex items-center gap-2 text-sm">
    <button class="px-3 py-1 rounded-lg bg-white/5 ring-1 ring-white/10" data-prev="arbitr">Назад</button>
    <span id="pg-arbitr"></span>
    <button class="px-3 py-1 rounded-lg bg-white/5 ring-1 ring-white/10" data-next="arbitr">Вперёд</button>
  </div>
</div>
  </section>
</div>

    <!-- КОЭФФИЦИЕНТЫ -->
    <div class="mt-6 p-6 rounded-2xl bg-slate-800/60 ring-1 ring-white/10">
      <div class="font-bold">Финансовые коэффициенты</div>
      <div id="ratios" class="mt-3 space-y-1 text-slate-400">
        Пока пусто — выполните проверку.
      </div>
    </div>

  </div>
</section>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
  // мини-хелперы
  const $  = (s) => document.querySelector(s);
  const fmt = (n) => (typeof n === 'number') ? n.toLocaleString('ru-RU') : (n || '');

  let ch1, ch2;

  // плавное открытие/закрытие панели
  function setOpen(el, open){
    if(open){
      el.classList.add('open');
      el.style.maxHeight = el.scrollHeight + 'px';
    }else{
      el.style.maxHeight = '0px';
      el.addEventListener('transitionend', () => el.classList.remove('open'), {once:true});
    }
  }

  // элементы панели отчётности
  const panel      = document.getElementById('report-panel');
  const toggleBtn  = document.getElementById('toggle-report');
  const toggleLbl  = document.getElementById('toggle-label');
  const badge      = document.getElementById('report-badge');
  let panelOpen = false;
  function setToggleLabel(){
    toggleLbl.textContent = panelOpen ? 'Скрыть отчётность' : 'Показать отчётность';
  }
  toggleBtn.addEventListener('click', () => {
    panelOpen = !panelOpen;
    setOpen(panel, panelOpen);
    setToggleLabel();
  });
  panel.classList.remove('open');
  setToggleLabel();

  // DRAG-TO-SCROLL для таблицы + Shift+колесо для горизонтали
  (function() {
    const wrap = document.getElementById('tblWrap');
    if (!wrap) return;

    let isDown = false;
    let startX = 0;
    let scrollLeft = 0;

    wrap.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      isDown = true;
      wrap.classList.add('cursor-grabbing','select-none');
      startX = e.pageX - wrap.getBoundingClientRect().left;
      scrollLeft = wrap.scrollLeft;
      e.preventDefault();
    });
    wrap.addEventListener('mousemove', (e) => {
      if (!isDown) return;
      const x = e.pageX - wrap.getBoundingClientRect().left;
      const walk = (x - startX) * 1.2;
      wrap.scrollLeft = scrollLeft - walk;
    });
    ['mouseup','mouseleave'].forEach(ev => wrap.addEventListener(ev, () => {
      isDown = false;
      wrap.classList.remove('cursor-grabbing','select-none');
    }));
    wrap.addEventListener('wheel', (e) => {
      if (e.shiftKey && Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        wrap.scrollLeft += e.deltaY;
        e.preventDefault();
      }
    }, { passive: false });
  })();

  async function loadOFDATA(inn){
    try{
      const r = await fetch('/api/ofdata_summary?inn=' + encodeURIComponent(inn));
      const j = await r.json();
      if(!j.ok) return;
      const s = j.summary || {};
      // бейджи-итоги
      const set = (id, val) => { const el=document.getElementById(id); if(el) el.textContent = val; };
      set('lc-badge',   (s.arbitr?.count ?? '—'));
      set('enf-badge',  (s.fssp?.count ?? '—'));
      set('insp-badge', (s.inspect?.count ?? '—'));
      set('gp-badge',   (s.contracts?.count ?? '—'));

      // подписи «последняя дата»
      const txt = (v)=> 'последняя дата: ' + (v?.last_date || '—');
      const s_ar = s.arbitr || {}, s_fs = s.fssp || {}, s_in = s.inspect || {}, s_gz = s.contracts || {};
      const setHTML = (id, html) => { const el=$(id); if(el) el.innerHTML = html; };
      setHTML('#lc-info',  txt(s_ar));
      setHTML('#enf-info', txt(s_fs));
      setHTML('#insp-info',txt(s_in));
      // госзакупки блок (можно расширить по ролям, если API вернёт раздельно)
      setHTML('#gp-cnts', `
        <div>Контрактов всего: <span class="font-semibold">${s_gz.count ?? '—'}</span></div>
        <div class="text-slate-400">${txt(s_gz)}</div>
      `);
    }catch(e){
      console.error(e);
    }
  }

  async function run(){
    const inn = $('#inn').value.trim();
    if(!inn){ $('#status').textContent = 'Введите ИНН.'; return; }
    $('#status').textContent = 'Загружаем…';

    try{
      // 1) финансы (checko)
      const res = await fetch('/api/finances?inn=' + encodeURIComponent(inn));
      const j = await res.json();
      if(!j.ok){ $('#status').textContent = j.error || 'Ошибка'; return; }
      $('#status').textContent = '';

      // карточка компании
      const c = j.company || {};
      $('#company').innerHTML = `
        <div class="p-4 rounded-2xl bg-white/5 ring-1 ring-white/10">
          <div class="flex items-baseline justify-between gap-3 flex-wrap">
            <div class="text-xl font-extrabold">${c['НаимПолн'] || ''}</div>
            <div class="text-xs px-3 py-1 rounded-full bg-brand/15 text-brand ring-1 ring-brand/30">
              ИНН: ${c['ИНН'] || inn}${c['ОГРН'] ? ' • ОГРН: ' + c['ОГРН'] : ''}
            </div>
          </div>
          <div class="text-slate-400 mt-1">Статус: ${c['Статус'] || '—'} • Дата регистрации: ${c['ДатаРег'] || '—'}</div>
          <div class="text-slate-400 mt-1">Адрес: ${c['ЮрАдрес'] || '—'}</div>
        </div>
      `;

      // таблица показателей
      const tbl = $('#tbl');
      const periods = j.periods;
      const inputRows = j.rows || [];
      const filtered = inputRows.filter(r => periods.some(p => Number(r[p] || 0) !== 0));

      badge.textContent = filtered.length ? filtered.length : '—';
      toggleBtn.disabled = filtered.length === 0;

      const thead = `
        <thead class="sticky top-0 z-10 backdrop-blur bg-slate-900/70 text-slate-300 text-xs">
          <tr>
            <th class="px-3 py-2 border-b border-white/10 text-left sticky left-0 bg-slate-900/70 z-[2] min-w-[260px]">
              Показатель
            </th>
            ${periods.map(p => `<th class="px-3 py-2 border-b border-white/10 text-right min-w-[96px]">${p}</th>`).join('')}
          </tr>
        </thead>`;
      const tbody = `
        <tbody class="text-sm">
          ${filtered.map((r, i) => `
            <tr class="${i % 2 ? 'bg-white/0' : 'bg-white/[0.02]'} hover:bg-white/[0.04]">
              <td class="px-3 py-2 border-b border-white/10 sticky left-0 bg-slate-900/70 z-[1] font-medium">
                ${r['Показатель']}
              </td>
              ${periods.map(p => `
                <td class="px-3 py-2 border-b border-white/10 text-right tabular-nums">${fmt(r[p] || 0)}</td>
              `).join('')}
            </tr>
          `).join('')}
        </tbody>`;
      tbl.innerHTML = thead + tbody;

      if(panelOpen){
        requestAnimationFrame(()=>{ panel.style.maxHeight = panel.scrollHeight + 'px'; });
      }

      // коэффициенты
      const rbox = $('#ratios');
      const entries = Object.entries(j.ratios || {});
      let ratiosHtml = entries.map(([k,v])=>{
        if(typeof v === 'number') v = Number.isFinite(v) ? v.toFixed(2) : '—';
        return `<div class="flex justify-between text-sm">
                  <span class="text-slate-300">${k}</span>
                  <span class="font-semibold">${v}</span>
                </div>`;
      }).join('');
      if(!ratiosHtml) ratiosHtml = '<div class="text-slate-400">Данных недостаточно</div>';
      rbox.innerHTML = ratiosHtml;
      rbox.classList.remove('text-slate-400');

      // графики (вертикально, один под другим)
      const P = j.charts.periods;

      if(ch1) ch1.destroy();
      ch1 = new Chart(document.getElementById('chart1').getContext('2d'), {
        type:'line',
        data:{ labels:P, datasets:[
          { label:'Выручка (2110)',        data:j.charts.sales,  tension:.3 },
          { label:'Чистая прибыль (2400)', data:j.charts.profit, tension:.3 }
        ]},
        options:{ responsive:true, plugins:{ legend:{ position:'bottom' }}, scales:{ y:{ beginAtZero:false }}}
      });
      document.getElementById('ph1').style.display='none';

      if(ch2) ch2.destroy();
      ch2 = new Chart(document.getElementById('chart2').getContext('2d'), {
        type:'line',
        data:{ labels:P, datasets:[
          { label:'Коэф. автономии',     data:j.charts.autonomy,     tension:.3 },
          { label:'Текущая ликвидность', data:j.charts.current_ratio, tension:.3 }
        ]},
        options:{ responsive:true, plugins:{ legend:{ position:'bottom' }}, scales:{ y:{ beginAtZero:true }}}
      });
      document.getElementById('ph2').style.display='none';

      // 2) внешние показатели (OFDATA)
      await loadOFDATA(inn);

    }catch(e){
      console.error(e);
      $('#status').textContent = 'Не удалось загрузить данные.';
    }
  }

  document.getElementById('btn').addEventListener('click', run);
  document.getElementById('inn').addEventListener('keydown', e => { if(e.key==='Enter') run(); });
  const state = {
    currentInn: "", 
    pages: {arbitr:1, enforcements:1, inspections:1, contracts:1},
    limits: 20
  };

  // включаем детали-контейнер
  document.querySelectorAll('[data-open]').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const kind = btn.getAttribute('data-open');
      document.getElementById('list-'+kind).classList.toggle('hidden');
      await renderList(kind, 1);
    });
  });
  // пагинация
  document.querySelectorAll('[data-prev]').forEach(btn=>{
    btn.addEventListener('click', ()=>{ const k=btn.getAttribute('data-prev'); if(state.pages[k]>1){ renderList(k, state.pages[k]-1); }});
  });
  document.querySelectorAll('[data-next]').forEach(btn=>{
    btn.addEventListener('click', ()=>{ const k=btn.getAttribute('data-next'); renderList(k, state.pages[k]+1); });
  });

  // колонки под каждое API
  function renderTable(el, head, rowsHtml){
    el.innerHTML = `
      <thead class="sticky top-0 z-10 backdrop-blur bg-slate-900/70 text-slate-300 text-xs">
        <tr>${head.map(h=>`<th class="px-3 py-2 border-b border-white/10 text-left">${h}</th>`).join('')}</tr>
      </thead>
      <tbody class="text-sm">${rowsHtml}</tbody>`;
  }

  async function renderList(kind, page){
    const inn = document.querySelector('#inn').value.trim();
    if(!inn) return;
    state.currentInn = inn;

    let url = `/api/ofdata/${kind}?inn=${encodeURIComponent(inn)}&limit=${state.limits}&page=${page}`;

    // фильтры для contracts
    if(kind==='contracts'){
      const lawSel  = document.getElementById('flt-law');
      const roleSel = document.getElementById('flt-role');
      const law  = lawSel ? (lawSel.value||"") : "";
      const role = roleSel ? (roleSel.value||"") : "";
      if(law)  url += `&law=${law}`;
      if(role) url += `&role=${role}`;
    }

    const r = await fetch(url);
    const j = await r.json();
    if(!j.ok) return;
    state.pages[kind] = j.data.page;

    // контрактЫ
    if(kind==='contracts'){
      const tbl = document.getElementById('tbl-contracts');
      const head = ['Дата','РегНомер','Цена, ₽','Заказчик','Поставщик','EIS','law','role'];
      const rows = (j.data.items||[]).map(x=>{
        const supplier = (Array.isArray(x['Постав']) && x['Постав'][0]?.['НаимПолн']) || '';
        const customer = (x['Заказ'] && (x['Заказ']['НаимПолн']||x['Заказ']['НаимСокр'])) || '';
        const eis = x['СтрЕИС'] ? `<a class="underline" target="_blank" href="${x['СтрЕИС']}">ссылка</a>` : '';
        return `<tr class="hover:bg-white/[0.04]">
          <td class="px-3 py-2 border-b border-white/10">${x['Дата']||''}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['РегНомер']||''}</td>
          <td class="px-3 py-2 border-b border-white/10 text-right">${(x['Цена']||0).toLocaleString('ru-RU')}</td>
          <td class="px-3 py-2 border-b border-white/10">${customer}</td>
          <td class="px-3 py-2 border-b border-white/10">${supplier}</td>
          <td class="px-3 py-2 border-b border-white/10">${eis}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['__law']||''}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['__role']||''}</td>
        </tr>`;
      }).join('');
      renderTable(tbl, head, rows);
      document.getElementById('pg-contracts').textContent = `${j.data.page} / ${j.data.pages}`;
      return;
    }

    // Проверки
    if(kind==='inspections'){
      const tbl = document.getElementById('tbl-inspections');
      const head = ['ДатаНач','Номер','Статус','Наруш','Орган контроля'];
      const rows = (j.data.items||[]).map(x=>{
        const org = x['ОргКонтр']?.['Наим'] || '';
        return `<tr class="hover:bg-white/[0.04]">
          <td class="px-3 py-2 border-b border-white/10">${x['ДатаНач']||''}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['Номер']||''}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['Статус']||''}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['Наруш']===true?'да':x['Наруш']===false?'нет':'—'}</td>
          <td class="px-3 py-2 border-b border-white/10">${org}</td>
        </tr>`;
      }).join('');
      renderTable(tbl, head, rows);
      document.getElementById('pg-inspections').textContent = `${j.data.page} / ${j.data.pages}`;
      return;
    }

    // ФССП
    if(kind==='enforcements'){
      const tbl = document.getElementById('tbl-enforcements');
      const head = ['Дата','№ исп. пр.','Предмет','Долг, ₽','Остаток, ₽','Отдел приставов'];
      const rows = (j.data.items||[]).map(x=>{
        return `<tr class="hover:bg-white/[0.04]">
          <td class="px-3 py-2 border-b border-white/10">${x['ИспПрДата']||''}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['ИспПрНомер']||''}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['ПредмИсп']||''}</td>
          <td class="px-3 py-2 border-b border-white/10 text-right">${(x['СумДолг']||0).toLocaleString('ru-RU')}</td>
          <td class="px-3 py-2 border-b border-white/10 text-right">${(x['ОстЗадолж']||0).toLocaleString('ru-RU')}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['СудПристНаим']||''}</td>
        </tr>`;
      }).join('');
      renderTable(tbl, head, rows);
      document.getElementById('pg-enforcements').textContent = `${j.data.page} / ${j.data.pages}`;
      return;
    }

    // Арбитраж
    if(kind==='arbitr'){
      const tbl = document.getElementById('tbl-arbitr');
      const head = ['Дата','Номер дела','Суд','Сумма иска, ₽','КАД'];
      const rows = (j.data.items||[]).map(x=>{
        const kad = x['СтрКАД'] ? `<a class="underline" target="_blank" href="${x['СтрКАД']}">ссылка</a>` : '';
        return `<tr class="hover:bg-white/[0.04]">
          <td class="px-3 py-2 border-b border-white/10">${x['Дата']||''}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['Номер']||''}</td>
          <td class="px-3 py-2 border-b border-white/10">${x['Суд']||''}</td>
          <td class="px-3 py-2 border-b border-white/10 text-right">${(x['СуммИск']||0).toLocaleString('ru-RU')}</td>
          <td class="px-3 py-2 border-b border-white/10">${kad}</td>
        </tr>`;
      }).join('');
      renderTable(tbl, head, rows);
      document.getElementById('pg-arbitr').textContent = `${j.data.page} / ${j.data.pages}`;
      return;
    }
  }
</script>
"""
    return Response(page_wrap(html, "Проверка ИНН — Kontrola"), mimetype="text/html; charset=utf-8")

@app.get("/contacts")
def contacts_page():
    inner = """
<section class="full-bleed section-roomy reveal">
  <div class="max-w-6xl mx-auto px-6">
    <header class="text-center max-w-2xl mx-auto">
      <h1 class="text-5xl font-extrabold">Контакты</h1>
      <p class="text-slate-300 mt-3">Свяжитесь с нами удобным способом. Обычно отвечаем в течение рабочего часа.</p>
    </header>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-10">
      <article class="glass rounded-3xl p-6">
        <div class="text-sm text-slate-400">Email</div>
        <h3 class="text-xl font-extrabold mt-1">
          <a href="mailto:info@kontrola.tech" class="underline">info@kontrola.tech</a>
        </h3>
        <p class="text-slate-300 mt-2">Общие вопросы и партнёрства</p>
      </article>

      <article class="glass rounded-3xl p-6">
        <div class="text-sm text-slate-400">Поддержка</div>
        <h3 class="text-xl font-extrabold mt-1">
          <a href="https://t.me/prvrrln" target="_blank" class="underline">@prvrrln</a>
        </h3>
        <p class="text-slate-300 mt-2">Telegram: помощь и онбординг</p>
      </article>

      <article class="glass rounded-3xl p-6">
        <div class="text-sm text-slate-400">График</div>
        <h3 class="text-xl font-extrabold mt-1">Пн–Пт, 10:00–19:00 (MSK)</h3>
        <p class="text-slate-300 mt-2">В нерабочее время — через Telegram</p>
      </article>
    </div>

    <section class="mt-10 grid grid-cols-1 lg:grid-cols-2 gap-6">
      <article class="glass rounded-3xl p-6">
        <h3 class="text-2xl font-extrabold">Быстрый запрос</h3>
        <form class="mt-4 grid sm:grid-cols-2 gap-4" method="post" action="/lead">
          <input name="name" required placeholder="Ваше имя*" class="px-4 py-3 rounded-2xl bg-slate-900 border border-white/10">
          <input name="email" required type="email" placeholder="Email*" class="px-4 py-3 rounded-2xl bg-slate-900 border border-white/10">
          <input name="company" placeholder="Компания" class="px-4 py-3 rounded-2xl bg-slate-900 border border-white/10">
          <input name="phone" placeholder="Телефон" class="px-4 py-3 rounded-2xl bg-slate-900 border border-white/10">
          <textarea name="comment" rows="4" placeholder="Коротко опишите вопрос" class="sm:col-span-2 px-4 py-3 rounded-2xl bg-slate-900 border border-white/10"></textarea>
          <label class="sm:col-span-2 flex items-start gap-2 text-sm text-slate-300">
            <input type="checkbox" required class="mt-1"> Соглашаюсь с условиями обработки ПДн.
          </label>
          <div class="sm:col-span-2">
            <button class="px-6 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">Отправить</button>
          </div>
        </form>
      </article>

      <article class="glass rounded-3xl p-6">
        <h3 class="text-2xl font-extrabold">Реквизиты</h3>
        <ul class="mt-3 space-y-2 text-slate-300">
          <li>ООО «Контрола»</li>
          <li>ИНН 7700000000 • ОГРН 1234567890123</li>
          <li>Юр. адрес: 101000, г. Москва</li>
          <li>Банк: ТОЧКА ПАО БАНКА «ФК Открытие»</li>
          <li>Р/с: 40702XXXXXXXXXXXX</li>
          <li>БИК: 044525999</li>
        </ul>
        
      </article>
    </section>
  </div>
</section>
"""
    return Response(page_wrap(inner, "Контакты — Kontrola"), mimetype="text/html; charset=utf-8")

@app.get("/rules")
def rules_page():
    inner = """
<section class="full-bleed section-roomy reveal">
  <div class="max-w-4xl mx-auto px-6">
    <header class="text-center">
      <h1 class="text-5xl font-extrabold">Правила и политика</h1>
      <p class="text-slate-300 mt-3">Краткая версия условий использования сервиса и обработки данных.</p>
    </header>

    <article class="glass rounded-3xl p-8 mt-8 space-y-6 leading-relaxed">
      <section>
        <h2 class="text-2xl font-extrabold">1. Термины</h2>
        <p class="text-slate-300 mt-2">«Сервис» — платформа Kontrola. «Пользователь» — лицо, принимающее условия и использующее сервис.</p>
      </section>

      <section>
        <h2 class="text-2xl font-extrabold">2. Доступ и тарифы</h2>
        <p class="text-slate-300 mt-2">Доступ предоставляется по подписке или за разовые списания с баланса. Стоимость и состав услуг см. в разделе «Тарифы».</p>
      </section>

      <section>
        <h2 class="text-2xl font-extrabold">3. Источники данных</h2>
        <p class="text-slate-300 mt-2">Мы агрегируем публичные реестры и открытые источники. Результаты проверки — информационные сведения, не являются юридическим заключением.</p>
      </section>

      <section>
        <h2 class="text-2xl font-extrabold">4. Ответственность</h2>
        <p class="text-slate-300 mt-2">Сервис предоставляется «как есть». Мы стремимся к актуальности данных, но не гарантируем отсутствие ошибок источников или задержек публикаций.</p>
      </section>

      <section>
        <h2 class="text-2xl font-extrabold">5. Персональные данные</h2>
        <p class="text-slate-300 mt-2">Обрабатываем ПДн в объёме, необходимом для работы сервиса и поддержки. Основания: согласие пользователя и исполнение договора-оферты.</p>
      </section>

      <section>
        <h2 class="text-2xl font-extrabold">6. Безопасность</h2>
        <p class="text-slate-300 mt-2">Используем шифрование трафика, сегментацию окружений и регламенты доступа. Журналы действий храним ограниченное время.</p>
      </section>

      <section>
        <h2 class="text-2xl font-extrabold">7. Оплаты и возвраты</h2>
        <p class="text-slate-300 mt-2">Оплата подписки и пополнений — безналичными способами. Возвраты по неоказанной части услуги рассматриваются по заявке в поддержку.</p>
      </section>

      <section>
        <h2 class="text-2xl font-extrabold">8. Контакты</h2>
        <p class="text-slate-300 mt-2">Для юридических запросов: <a href="mailto:hello@kontrola.example" class="underline">hello@kontrola.example</a>, тема «Юридический вопрос».</p>
      </section>

      <p class="text-slate-400 text-sm">Последнее обновление: 2025-01-15. Полная версия документов будет опубликована дополнительно.</p>
    </article>

    <div class="text-center mt-8">
      <a href="/pricing" class="px-6 py-3 rounded-2xl border border-white/15 hover:bg-white/10">К тарифам</a>
      <a href="/contacts" class="ml-2 px-6 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">Связаться</a>
    </div>
  </div>
</section>
"""
    return Response(page_wrap(inner, "Правила — Kontrola"), mimetype="text/html; charset=utf-8")

@app.get("/social/vk")
def vk_page():
    return placeholder_page("VK", "Готовим страницу сообщества.")

@app.get("/social/tg")
def tg_page():
    return placeholder_page("Telegram", "Скоро заработает канал/поддержка.")
@app.get("/cart")
def cart_page():
    inner = """
<section class="full-bleed section-roomy reveal">
  <div class="max-w-5xl mx-auto px-6">
    <h1 class="text-4xl font-extrabold mb-6">Корзина</h1>

    <div id="cart-box" class="p-6 rounded-2xl bg-slate-800/60 ring-1 ring-white/10">
      Загрузка…
    </div>

    <div class="mt-6 flex gap-3 flex-wrap">
      <a href="/pricing" class="px-5 py-3 rounded-2xl border border-white/15 hover:bg-white/10">К тарифам</a>
      <a href="/balance" class="px-5 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">Пополнить баланс</a>
    </div>
  </div>
</section>

<script>
  const fmt = (n)=> (n||0).toLocaleString('ru-RU');

  async function load(){
    const r = await fetch('/api/cart');
    const j = await r.json();
    if(!j.ok){ document.getElementById('cart-box').textContent = 'Ошибка'; return; }
    const d = j.data;
    const rows = (d.items||[]).map(it => `
      <tr class="hover:bg-white/[0.04]">
        <td class="px-3 py-2 border-b border-white/10">${it.title}</td>
        <td class="px-3 py-2 border-b border-white/10 text-slate-400">${it.desc||''}</td>
        <td class="px-3 py-2 border-b border-white/10 text-right">${fmt(it.price)} ₽</td>
        <td class="px-3 py-2 border-b border-white/10 text-right">
          <input data-sku="${it.sku}" type="number" min="1" max="99" value="${it.qty}" class="w-16 px-2 py-1 rounded bg-white/10 ring-1 ring-white/10 text-right">
        </td>
        <td class="px-3 py-2 border-b border-white/10 text-right font-semibold">${fmt(it.line_total)} ₽</td>
      </tr>
    `).join('');

    const html = `
      <div class="overflow-auto rounded-xl ring-1 ring-white/10">
        <table class="min-w-full text-sm">
          <thead class="sticky top-0 z-10 backdrop-blur bg-slate-900/70 text-slate-300 text-xs">
            <tr>
              <th class="px-3 py-2 border-b border-white/10 text-left">Товар</th>
              <th class="px-3 py-2 border-b border-white/10 text-left">Описание</th>
              <th class="px-3 py-2 border-b border-white/10 text-right">Цена</th>
              <th class="px-3 py-2 border-b border-white/10 text-right">Кол-во</th>
              <th class="px-3 py-2 border-b border-white/10 text-right">Сумма</th>
            </tr>
          </thead>
          <tbody>${rows || '<tr><td colspan="5" class="px-3 py-4 text-center text-slate-400">Корзина пуста</td></tr>'}</tbody>
        </table>
      </div>

      <div class="mt-4 flex items-center justify-between flex-wrap gap-3">
        <div class="text-slate-300">Баланс: <span id="balance" class="font-semibold">${fmt(d.balance)} ₽</span></div>
        <div class="text-right">
          <div class="text-sm text-slate-400">Итого</div>
          <div class="text-2xl font-extrabold"><span id="total">${fmt(d.total)} ₽</span></div>
        </div>
      </div>

      <div class="mt-4 flex gap-3 flex-wrap">
        <button id="btn-clear" class="px-4 py-2 rounded-xl bg-white/5 ring-1 ring-white/10 hover:bg-white/10">Очистить</button>
        <a href="/balance" class="px-4 py-2 rounded-xl border border-white/15 hover:bg-white/10">Пополнить баланс</a>
        <button id="btn-pay" class="px-5 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">Оплатить с баланса</button>
      </div>
    `;
    document.getElementById('cart-box').innerHTML = html;

    // обработчики
    document.querySelectorAll('input[data-sku]').forEach(inp=>{
      inp.addEventListener('change', async ()=>{
        const sku = inp.getAttribute('data-sku');
        const qty = Math.max(1, Math.min(99, parseInt(inp.value||1)));
        const r = await fetch('/api/cart/update', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({sku, qty})});
        const jj = await r.json(); if(jj.ok) load();
      });
    });
    document.getElementById('btn-clear').onclick = async () => { await fetch('/api/cart/clear', {method:'POST'}); load(); };
    document.getElementById('btn-pay').onclick = async () => {
      const r = await fetch('/api/checkout/pay-from-balance', {method:'POST'});
      const jj = await r.json();
      if(jj.ok){ alert('Оплачено. Спасибо!'); load(); } else { alert(jj.error || 'Ошибка'); }
    };
  }
  load();
</script>
"""
    return Response(page_wrap(inner, "Корзина — Kontrola"), mimetype="text/html; charset=utf-8")
@app.get("/balance")
def balance_page():
    inner = """
<section class="full-bleed section-roomy reveal">
  <div class="max-w-3xl mx-auto px-6">
    <h1 class="text-4xl font-extrabold mb-2">Пополнение баланса</h1>
    <p class="text-slate-300 mb-6">Способы: банковская карта, СБП, счёт Юр.лица (эмуляция).</p>

    <div class="grid gap-6">
      <div class="glass rounded-3xl p-6">
        <label class="block text-sm text-slate-300 mb-2">Сумма, ₽</label>
        <input id="amount" type="number" min="100" step="100" value="300"
               class="w-full px-4 py-3 rounded-xl bg-slate-900 border border-white/10 outline-none focus:ring-2 focus:ring-brand"/>
        <div class="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <button data-method="card" class="px-5 py-3 rounded-2xl bg-gradient-to-br from-brand to-brand2 font-semibold">Картой</button>
          <button data-method="sbp"  class="px-5 py-3 rounded-2xl bg-white/10 ring-1 ring-white/10 hover:bg-white/15">СБП</button>
          <button data-method="invoice" class="px-5 py-3 rounded-2xl bg-white/10 ring-1 ring-white/10 hover:bg-white/15">Счёт юр.лица</button>
        </div>
        <div id="bal-status" class="mt-4 text-slate-300">Текущий баланс: <span id="cur-balance">—</span></div>
      </div>

      <div class="glass rounded-3xl p-6">
        <h3 class="text-lg font-bold">Единоразовые проверки</h3>
        <p class="text-slate-300 mt-1">Цена: 300 ₽/проверка. После пополнения — списывается по факту.</p>
        <a href="/pricing" class="mt-4 inline-block px-5 py-3 rounded-2xl border border-white/15 hover:bg-white/10">Вернуться к тарифам</a>
      </div>
    </div>
  </div>
</section>

<script>
  const fmt = (n)=> (n||0).toLocaleString('ru-RU') + ' ₽';
  async function refresh(){
    const r = await fetch('/api/cart');
    const j = await r.json();
    if(j.ok){ document.getElementById('cur-balance').textContent = fmt(j.data.balance); }
  }
  async function topup(method){
    const amount = Math.max(100, parseInt(document.getElementById('amount').value||0));
    const r = await fetch('/api/balance/topup', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({amount, method})});
    const j = await r.json();
    if(j.ok){ alert(j.data.message); refresh(); } else { alert(j.error || 'Ошибка'); }
  }
  document.querySelectorAll('button[data-method]').forEach(b=>{
    b.addEventListener('click', ()=> topup(b.getAttribute('data-method')));
  });
  refresh();
</script>
"""
    return Response(page_wrap(inner, "Пополнение баланса — Kontrola"), mimetype="text/html; charset=utf-8")
@app.get("/login")
def login_page():
    return placeholder_page("Вход", "Страница авторизации.")

@app.get("/register")
def register_page():
    return placeholder_page("Регистрация", "Создание нового аккаунта.")

# -------------- запуск --------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=True)


