# Dashboard — SINAREM 2026 · 2ª Edição (Captação do Simulado)

Tracker ao vivo da captação da **2ª edição** do SINAREM (simulado nacional de
residência — Aristo + MedQ). Atualiza sozinho **de hora em hora** via GitHub
Action, lendo as planilhas de acompanhamento e republicando no GitHub Pages.

- **Link:** https://vianapatrick15-max.github.io/sinarem-2ed-dashboard/
- **Janela da 2ª edição:** a partir de **23/06/2026** (a 1ª edição zerou o
  investimento após 18/06; o investimento "2ed" começou em 24/06).

## Fontes
- **Inscritos (HubSpot):** planilha *Grupo Primum | Leads e Pré-Checkout 2026*
  (`1vcpyCCE0d8zvoSfZqEacvRcJ3yQQgZdogO7CJu32MwA`), aba
  `[ART] [MDQ] Sinarem 2026 2º ED` — já curada pelo time para a 2ª edição.
- **Investimento (Meta):** planilha *DASH_ARISTO*
  (`1uExbyUCZ3fKqfZCayHRf-UzxgafDORPmUqucFR5OKRs`), abas
  `DADOS_GERENCIADOR_ART` e `DADOS_GERENCIADOR_MEDQ`, filtrando campanhas que
  contêm `sinarem` a partir de 23/06 (captura tanto `sinarem_2ed_*` quanto as
  `sinarem_*` reaproveitadas na 2ª ed).

## Modelagem
- **Visão geral:** leads captados, investimento, CPL (pago e blended),
  qualidade do público e split de origem — tudo somando as duas frentes.
- **Pago x orgânico:** a aba HubSpot da 2ª ed **carrega UTM**, então dá pra
  separar. *Pago* = UTM source de mídia (`meta_ads`, `search_ads`, `adwords`…);
  *orgânico* = e-mail, base, redes, direto (resto). Orgânicos não têm custo de
  mídia.
- **Aristo x MedQ:** o **investimento** de cada frente vem limpo do gerenciador.
  Os **leads** são atribuídos pela UTM do contato (campanha/conteúdo que cita
  aristo → Aristo; medq/mdq/jota → MedQ); leads sem UTM de frente ficam fora do
  split, mas contam no total. Por isso o CPL por frente é **direcional** — o
  número firme é o CPL geral.
- **Qualidade ("público certo"):** Momento do Perfil em preparação para
  residência (preparação p/ residência + internato + recém-formado + prova de
  título).

## Modo tracker (sem meta)
A 2ª edição começou em 24/06 e ainda não tem meta de CPL/verba/inscritos nem
data de prova definidas, então o dash roda como **tracker ao vivo** — sem
medidores de meta nem projeção. Para **ligar metas/projeção**, preencha no topo
do `refresh.py`: `CPL_TARGET`, `BUDGET`, `TOTAL_TARGET`, `CAPTURE_END`
(e opcional `EVENT_START`). O template liga os medidores sozinho quando os
alvos existem.

## Como funciona
- `refresh.py` lê as planilhas, calcula os indicadores e gera `data.json` +
  `index.html` (auto-contido, gráficos em SVG nativo, sem dependências externas).
- O Action roda `refresh.py` no cron e commita o resultado; o Pages serve o
  `index.html`.

## Rodar local
```
pip install -r requirements.txt
python refresh.py   # usa a credencial local da service account (ga4-instituto-andhela)
```
