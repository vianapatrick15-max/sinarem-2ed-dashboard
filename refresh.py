#!/usr/bin/env python3
"""
Pipeline de dados do Dashboard SINAREM 2026 — 2a Edicao (Aristo + MedQ).

Diferencas vs 1a edicao:
  - Inscritos vem de OUTRA planilha (Grupo Primum | Leads e Pre-Checkout 2026),
    aba "[ART] [MDQ] Sinarem 2026 2o ED" — ja curada pelo time para a 2a ed.
  - Essa aba CARREGA UTMs, entao da pra separar PAGO x ORGANICO e atribuir
    a frente (Aristo x MedQ) por lead.
  - Spend vem da MESMA planilha de gerenciador, abas DADOS_GERENCIADOR_ART e
    DADOS_GERENCIADOR_MEDQ, filtrando campanhas "sinarem" a partir de ED2_START
    (a 2a ed comeca em 24/06; a 1a ja zerou apos 18/06). Captura tanto as
    campanhas "sinarem_2ed_*" quanto as "sinarem_*" reaproveitadas na 2a ed.

Modelo de tracker AO VIVO (sem meta/projecao — campanha recem-iniciada).
Os alvos (CPL/verba/total/datas) ficam em TARGETS abaixo: deixe None para
manter o modo tracker; preencha para ligar medidores e projecao.
"""
import os, json, datetime as dt
from pathlib import Path
from collections import defaultdict

# ----------------------------- FONTES -----------------------------
HUBSPOT_SID = "1vcpyCCE0d8zvoSfZqEacvRcJ3yQQgZdogO7CJu32MwA"   # Grupo Primum | Leads
HUBSPOT_TAB = "[ART] [MDQ] Sinarem 2026 2º ED"
GER_SID     = "1uExbyUCZ3fKqfZCayHRf-UzxgafDORPmUqucFR5OKRs"   # DASH_ARISTO
GER_ART_TAB  = "DADOS_GERENCIADOR_ART"
GER_MEDQ_TAB = "DADOS_GERENCIADOR_MEDQ"

OUT = Path(__file__).parent / "data.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
LOCAL_CRED = os.path.expanduser("~/.claude/skills/ga4/credentials/ga4-instituto-andhela.json")

# ------------------------- PARAMETROS DA 2a ED -------------------------
# Janela da 2a edicao: a 1a ed zerou o spend de sinarem apos 18/06; o primeiro
# lead da 2a entrou em 23/06 e o spend "2ed" comecou em 24/06. >= 23/06 isola a 2a.
ED2_START = dt.date(2026, 6, 23)
CAMPAIGN_START = dt.date(2026, 6, 24)   # 1o dia com investimento na 2a ed

# Metas (None = modo tracker ao vivo, sem medidores/projecao). Para ligar,
# preencha CPL_TARGET / BUDGET / TOTAL_TARGET / CAPTURE_END.
CPL_TARGET   = None
BUDGET       = None
TOTAL_TARGET = None
EVENT_START  = None     # dt.date(...)
CAPTURE_END  = None     # dt.date(...)

# Perfis que contam como "publico certo" (em preparacao p/ residencia)
TARGET_PROFILES = {
    "Médico(a) em preparação para residência",
    "Estudante de Medicina (internato)",
    "Médico(a) recém-formado(a)",
    "Médico(a) em preparação para prova de título",
}
# UTM sources considerados midia PAGA (resto = organico/proprio)
PAID_SOURCES = {"meta_ads", "facebook_ads", "fb", "facebook",
                "instagram_ads", "search_ads", "adwords", "google_ads", "google"}

try:
    from zoneinfo import ZoneInfo
    TODAY = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
except Exception:
    TODAY = (dt.datetime.utcnow() - dt.timedelta(hours=3)).date()
# -----------------------------------------------------------------------

def get_client():
    import gspread
    from google.oauth2.service_account import Credentials
    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if raw:
        creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    else:
        path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH", LOCAL_CRED)
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
    return gspread.authorize(creds)

def num(x):
    if x is None: return 0.0
    s = str(x).strip().replace(".", "").replace(",", ".")
    if s in ("", "-"): return 0.0
    try: return float(s)
    except: return 0.0

def is_sinarem(c): return "sinarem" in (c or "").lower()

def daykey(s):  # "25/06/2026 13:47:09" -> "2026-06-25"
    d = s.strip().split(" ")[0]
    try:
        dd, mm, yy = d.split("/"); return f"{yy}-{mm}-{dd}"
    except: return ""

def front_of(camp, content, medium, source):
    """Atribui a frente (Aristo/MedQ) ao lead pelas UTMs. Directional."""
    c = camp.lower()
    if is_sinarem(c) and "aristo" in c: return "Aristo"
    if is_sinarem(c) and ("medq" in c or "mdq" in c): return "MedQ"
    txt = " ".join([camp, content, medium, source]).lower()
    if any(k in txt for k in ("medq", "mdq", "jota")): return "MedQ"
    if "eduq" in txt and "aristo" not in txt: return "MedQ"
    if any(k in txt for k in ("aristo", "art_", "art-", "_aristo", "art-25", "art-0", "art_0")): return "Aristo"
    return ""

def org_bucket(source):
    s = source.lower().strip()
    if s == "": return "Direto / sem origem"
    if s in ("email", "hs_email"): return "E-mail"
    if s == "hs_automation": return "Automação HubSpot"
    if s == "exec": return "Equipe / interno"
    if s in ("whatsapp_grupo", "whatsapp"): return "WhatsApp"
    if s in ("ig_bio", "ig", "org-instagram", "social", "org-site"): return "Orgânico social / site"
    if s in ("plataforma",): return "Plataforma"
    if s == "beeviral": return "Indicação"
    return "Outros"

# ===================== LEITURA =====================
gc = get_client()
ger = gc.open_by_key(GER_SID)

def read_front(title, front):
    g = ger.worksheet(title).get_all_values()
    gh = {h.strip(): i for i, h in enumerate(g[0])}
    C_DAY, C_CAMP = gh["Day"], gh["Campaign Name"]
    C_IMPR, C_SPEND, C_CLK = gh["Impressions"], gh["Amount Spent"], gh["Link Clicks"]
    C_LPV, C_AD = gh["Landing Page Views"], gh.get("Ad Name", gh.get("Ad Set Name"))
    iso = ED2_START.isoformat()
    rows = [r for r in g[1:] if len(r) > C_CAMP and is_sinarem(r[C_CAMP])
            and r[C_DAY].strip() >= iso]
    agg = {"front": front, "spend": 0.0, "impressions": 0.0, "clicks": 0.0, "lpv": 0.0}
    by_day = defaultdict(float)
    by_day_ad = defaultdict(lambda: {"spend": 0.0, "clicks": 0.0, "lpv": 0.0})
    for r in rows:
        s = num(r[C_SPEND]) if len(r) > C_SPEND else 0
        agg["spend"] += s
        agg["impressions"] += num(r[C_IMPR])
        agg["clicks"] += num(r[C_CLK]) if len(r) > C_CLK else 0
        agg["lpv"] += num(r[C_LPV]) if len(r) > C_LPV else 0
        by_day[r[C_DAY]] += s
        ad = r[C_AD] if (C_AD is not None and len(r) > C_AD) else ""
        m = by_day_ad[(r[C_DAY], ad)]
        m["spend"] += s
        if len(r) > C_CLK: m["clicks"] += num(r[C_CLK])
        if len(r) > C_LPV: m["lpv"] += num(r[C_LPV])
    return agg, by_day, by_day_ad

aristo, aristo_day, aristo_day_ads = read_front(GER_ART_TAB, "Aristo")
medq,   medq_day,   medq_day_ads   = read_front(GER_MEDQ_TAB, "MedQ")

spend = aristo["spend"] + medq["spend"]
impr  = aristo["impressions"] + medq["impressions"]
clk   = aristo["clicks"] + medq["clicks"]
lpv   = aristo["lpv"] + medq["lpv"]
spend_by_day = defaultdict(float)
for d, v in list(aristo_day.items()) + list(medq_day.items()):
    spend_by_day[d] += v

# ---------- HUBSPOT (inscritos 2a ed) ----------
hs = gc.open_by_key(HUBSPOT_SID)
h = hs.worksheet(HUBSPOT_TAB).get_all_values()
hh = {x.strip(): i for i, x in enumerate(h[0])}
H_DATA  = hh["Data de conversão recente"]
H_PERFIL = hh["Momento do Perfil"]
H_SRC, H_MED, H_CONT, H_CAMP = hh["UTM Source"], hh["UTM Medium"], hh["UTM Content"], hh["UTM Campaign"]
hrows = [r for r in h[1:] if any(c.strip() for c in r) and len(r) > H_DATA and r[H_DATA].strip()]

def cell(r, i): return r[i].strip() if i is not None and len(r) > i else ""

total_inscritos = len(hrows)
leads_by_day = defaultdict(int)
leads_pago_by_day = defaultdict(int)
leads_org_by_day = defaultdict(int)
leads_aristo_by_day = defaultdict(int)
leads_medq_by_day = defaultdict(int)
perfil_count = defaultdict(int)
org_src_count = defaultdict(int)
front_leads = {"Aristo": {"total": 0, "pago": 0, "org": 0},
               "MedQ":   {"total": 0, "pago": 0, "org": 0},
               "":       {"total": 0, "pago": 0, "org": 0}}
inscritos_pago = inscritos_org = 0

for r in hrows:
    dk = daykey(r[H_DATA])
    src = cell(r, H_SRC); med = cell(r, H_MED); cont = cell(r, H_CONT); camp = cell(r, H_CAMP)
    paid = src.lower() in PAID_SOURCES
    fr = front_of(camp, cont, med, src)
    # frente do lead p/ o split por frente: SO conta quem veio da campanha SINAREM
    # da frente (assim o CPL por frente bate com o investimento SINAREM, que e a
    # unica midia contabilizada). Quem entrou por outra campanha/organico fica
    # como "nao atribuido" no split, mas conta no total geral.
    fr_sin = fr if (is_sinarem(camp) and fr in ("Aristo", "MedQ")) else ""
    leads_by_day[dk] += 1
    if paid:
        inscritos_pago += 1; leads_pago_by_day[dk] += 1
    else:
        inscritos_org += 1; leads_org_by_day[dk] += 1
        org_src_count[org_bucket(src)] += 1
    if fr_sin == "Aristo": leads_aristo_by_day[dk] += 1
    elif fr_sin == "MedQ": leads_medq_by_day[dk] += 1
    front_leads[fr_sin]["total"] += 1
    front_leads[fr_sin]["pago" if paid else "org"] += 1
    p = cell(r, H_PERFIL)
    perfil_count[p or "Não informado"] += 1

pct_pago = round(100 * inscritos_pago / total_inscritos, 1) if total_inscritos else 0
publico_n = sum(n for p, n in perfil_count.items() if p in TARGET_PROFILES)
pct_publico = round(100 * publico_n / total_inscritos, 1) if total_inscritos else 0

cpl_blended = spend / total_inscritos if total_inscritos else 0
cpl_pago = spend / inscritos_pago if inscritos_pago else 0

# ---------- series diaria ----------
all_days = sorted(d for d in (set(spend_by_day) | set(leads_by_day)) if d)
cum_leads = cum_spend = 0
series = []
for d in all_days:
    cum_leads += leads_by_day.get(d, 0)
    cum_spend += spend_by_day.get(d, 0)
    series.append({
        "day": d,
        "leads": leads_by_day.get(d, 0),
        "leads_pago": leads_pago_by_day.get(d, 0),
        "leads_organico": leads_org_by_day.get(d, 0),
        "leads_aristo": leads_aristo_by_day.get(d, 0),
        "leads_medq": leads_medq_by_day.get(d, 0),
        "spend": round(spend_by_day.get(d, 0), 2),
        "spend_aristo": round(aristo_day.get(d, 0), 2),
        "spend_medq": round(medq_day.get(d, 0), 2),
        "cum_leads": cum_leads,
        "cum_spend": round(cum_spend, 2),
    })

# ---------- por frente (spend + leads atribuidos) ----------
def front_block(agg, fl):
    sp = agg["spend"]
    pago = fl["pago"]
    return {
        "front": agg["front"],
        "spend": round(sp, 2),
        "impressions": int(agg["impressions"]),
        "clicks": int(agg["clicks"]),
        "lpv": int(agg["lpv"]),
        "leads": fl["total"],
        "leads_pago": fl["pago"],
        "leads_org": fl["org"],
        "cpl_pago": round(sp / pago, 2) if pago else 0,
        "cpc": round(sp / agg["clicks"], 2) if agg["clicks"] else 0,
        "cplpv": round(sp / agg["lpv"], 2) if agg["lpv"] else 0,
    }
fronts = [front_block(aristo, front_leads["Aristo"]),
          front_block(medq, front_leads["MedQ"])]
share_total = aristo["spend"] + medq["spend"]
for fb in fronts:
    fb["share_spend"] = round(100 * fb["spend"] / share_total, 1) if share_total else 0

# ---------- diario por criativo ----------
ads_daily = []
for front, by_day_ad in (("Aristo", aristo_day_ads), ("MedQ", medq_day_ads)):
    for (day, ad), m in by_day_ad.items():
        ads_daily.append({"day": day, "front": front, "ad": ad,
                          "spend": round(m["spend"], 2),
                          "clicks": int(m["clicks"]), "lpv": int(m["lpv"])})
ads_daily.sort(key=lambda a: (a["day"], -a["spend"]))

perfil = sorted(({"label": p, "n": n, "pct": round(100 * n / total_inscritos, 1)}
                 for p, n in perfil_count.items()), key=lambda x: -x["n"])
org_sources = sorted(({"label": k, "n": v} for k, v in org_src_count.items()),
                     key=lambda x: -x["n"])

days_since_start = max(0, (TODAY - CAMPAIGN_START).days) + 1

targets = None
if CPL_TARGET or BUDGET or TOTAL_TARGET:
    targets = {"cpl": CPL_TARGET, "budget": BUDGET, "total": TOTAL_TARGET}

data = {
    "edition": "2ª Edição",
    "updated_at": dt.datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0).isoformat(),
    "today": TODAY.isoformat(),
    "campaign_start": CAMPAIGN_START.isoformat(),
    "event_start": EVENT_START.isoformat() if EVENT_START else None,
    "capture_end": CAPTURE_END.isoformat() if CAPTURE_END else None,
    "days_since_start": days_since_start,
    "targets": targets,
    "kpis": {
        "inscritos": total_inscritos,
        "inscritos_pago": inscritos_pago,
        "inscritos_organico": inscritos_org,
        "pct_pago": pct_pago,
        "pct_org": round(100 - pct_pago, 1) if total_inscritos else 0,
        "publico_n": publico_n,
        "pct_publico": pct_publico,
        "spend": round(spend, 2),
        "spend_aristo": round(aristo["spend"], 2),
        "spend_medq": round(medq["spend"], 2),
        "impressions": int(impr),
        "clicks": int(clk),
        "lpv": int(lpv),
        "cpl_blended": round(cpl_blended, 2),
        "cpl_pago": round(cpl_pago, 2),
        "cpc": round(spend / clk, 2) if clk else 0,
        "cplpv": round(spend / lpv, 2) if lpv else 0,
        "leads_aristo": front_leads["Aristo"]["total"],
        "leads_medq": front_leads["MedQ"]["total"],
        "leads_nao_atrib": front_leads[""]["total"],
    },
    "fronts": fronts,
    "series": series,
    "ads_daily": ads_daily,
    "perfil": perfil,
    "org_sources": org_sources,
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))

# render index.html
base = Path(__file__).parent
tpl = (base / "template.html").read_text()
(base / "index.html").write_text(tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False)))

# resumo terminal
print(f"SINAREM 2a ED | janela >= {ED2_START} | dados {TODAY}")
print(f"INSCRITOS: {total_inscritos} | publico certo {publico_n} ({pct_publico}%)")
print(f"ORIGEM: {inscritos_pago} pagos ({pct_pago}%) | {inscritos_org} organicos")
print(f"FRENTE leads: Aristo {front_leads['Aristo']['total']} | MedQ {front_leads['MedQ']['total']} | nao-atrib {front_leads['']['total']}")
print(f"SPEND: R$ {spend:,.2f} (Aristo {aristo['spend']:,.0f} + MedQ {medq['spend']:,.0f})")
print(f"CPL pago R$ {cpl_pago:,.2f} | CPL blended R$ {cpl_blended:,.2f} | CPC R$ {data['kpis']['cpc']} | custo/LPV R$ {data['kpis']['cplpv']}")
print(f"OK -> {OUT}")
