# Adidas Competitive War Room — FIFA World Cup 2026

Dashboard ao vivo de inteligência competitiva para Adidas, monitorando concorrentes (Nike, Puma, New Balance, Under Armour, e marcas locais LATAM) durante o ciclo do Mundial 2026 nos mercados Brasil, México, Argentina e Colômbia.

Adidas é **FIFA Tier 1 Partner** (apparel, footwear, match ball oficial). O foco do dashboard é detectar **ambush marketing** dos competidores e calibrar resposta.

**Stack:** Static HTML + GitHub Actions + Vercel · 100% fontes públicas · Custo: R$ 0/mês

## Arquitetura

```
GitHub Actions (a cada hora)
        |
        v
  collector.py  -->  data/latest.json
        |                 |
        | git commit      |
        v                 v
  GitHub repo  -->  Vercel auto-deploy  -->  https://adidas-warroom.vercel.app
                                                       |
                                                       v
                                                  Time WPP + Adidas
```

## Concorrentes monitorados

10 marcas: Nike, Puma, New Balance, Under Armour, Mizuno, Asics, Umbro, Penalty (BR), Olympikus (BR), Joma. Detalhes e tier classification em [HANDOFF.md](HANDOFF.md).

## Métrica especial — Lançamentos Oficiais

Em vez de "latas comemorativas" (template Coca), este war room detecta **drops de produto** (camisas das seleções, chuteiras signature, bolas oficiais). Mais relevante pra Sportswear x Mundial.

## Fontes públicas

| Fonte | Cobertura | Auth |
|---|---|---|
| Google News RSS | Notícias por marca x mercado | Não |
| GDELT 2.0 DOC | Cobertura global de eventos | Não |
| INPI (via Google) | Registros de marca BR | Não |
| Mercado Livre API | Lançamentos novos em e-commerce | Não |
| YouTube RSS | Uploads dos canais oficiais | Não |
| Meta Ad Library | Anúncios ativos no FB/Instagram | User Token (compartilhado) |
| Google Trends | Search Interest | Não |
| Wikipedia pageviews | Tráfego em páginas de marca | Não |

## Setup

Repo já criado e linkado ao Vercel via agente `warroom-builder`. Para retomar localmente:

```powershell
git clone https://github.com/vinicanola/adidas-warroom.git
cd adidas-warroom
code .
```

Para rodar o collector localmente:

```powershell
pip install -r requirements.txt
$env:META_AD_LIBRARY_TOKEN = (Get-Content C:\Users\vinic\.warroom\meta-token.txt -Raw).Trim()
python collector.py
```

## Desenvolvimento

- **Cron:** `5 * * * *` (UTC). Workflow auto-trigger também em commit em `collector.py`.
- **Adicionar concorrente:** edite `COMPETITORS` em `collector.py` + `META_BRAND_PAGE_KEYWORDS` (mesmo arquivo) + lista `colors` em `index.html`.
- **Mudar paleta visual:** ajuste `:root` vars em `index.html` linha 12.

## Manutenção

| Frequência | Ação | Owner |
|---|---|---|
| ~30 dias | Renovar token Meta (Edson re-gera, atualizar `~/.warroom/meta-token.txt` + `gh secret set` no repo) | Vini |
| Mensal | Revisar lista de concorrentes (entrou/saiu) | CI Lead |
| Trimestral | Auditar fontes (taxa de relevância) | CI Lead |

## Notas

- **Token Meta:** compartilhado com `cocacola-warroom` via `C:\Users\vinic\.warroom\meta-token.txt`. Ver [HANDOFF.md](HANDOFF.md) §Credenciais.
- **Mizuno e Asics:** podem aparecer com 0 signals (fortes em running, fracos em soccer). Filtro `is_relevant` faz o trabalho — esperado.
- **Nike:** comportamento bipolar. Selecao oficial em BR, ambush em MX/AR/CO. Já tratado por `classify_sponsorship` market-aware.

---

*Gerado via agente `warroom-builder` em 2026-05-09.*
