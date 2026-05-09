# Adidas War Room — Handoff de Projeto

> Use este documento como contexto inicial ao retomar o projeto em outro ambiente (Claude Code, IDE, ou nova sessão).

## Quem é o cliente

**Adidas** — patrocinador FIFA Tier 1 do Mundial 2026 (rights globais de apparel, footwear e match ball). Categoria: Sportswear.

Mercados monitorados: **BR, MX, AR, CO**.

## O que é o projeto

Dashboard de Competitive Intelligence focado no ciclo da **FIFA World Cup 2026**. Auto-coleta de fontes públicas, atualização hora em hora, deploy automático.

A Adidas é o oficial; o foco da inteligência é detectar **ambush marketing** dos competidores e calibrar resposta.

## Arquitetura

```
collector.py  --->  data/latest.json  --->  index.html
Python 3.11      (commitado)              (Vercel)
     |
GitHub Actions
(cron 5 * * * *)
```

**Stack:** idêntica ao template Coca-Cola War Room (Python collector + GitHub Actions cron + JSON commitado + HTML estático em Vercel).

## Concorrentes monitorados (10)

| # | Marca | Categoria | Status no Mundial 2026 |
|---|---|---|---|
| 1 | **Nike** | Sportswear | Selecao oficial CBF (Brasil) / Ambush em MX/AR/CO |
| 2 | **Puma** | Sportswear | Ambush total |
| 3 | **New Balance** | Sportswear | Ambush total |
| 4 | **Under Armour** | Sportswear | Ambush total |
| 5 | **Mizuno** | Sportswear | Ambush total |
| 6 | **Asics** | Sportswear | Ambush total |
| 7 | **Umbro** | Sportswear | Ambush total |
| 8 | **Penalty** | Sportswear (BR local) | Ambush total |
| 9 | **Olympikus** | Sportswear (BR local) | Ambush total |
| 10 | **Joma** | Sportswear | Ambush total |

**Detalhe estratégico:** Adidas tem licença oficial em 3 das 4 seleções LATAM (MX, AR, CO). Nike só BR. Em MX/AR/CO, qualquer movimento da Nike é puro ambush.

## Métrica especial — Lançamentos Oficiais

Substitui o conceito de "latas comemorativas" do template original. Detecta:
- **Camisas/jerseys** das seleções (queries: "camisa selecao 2026", "jersey mundial 2026", "kit oficial")
- **Chuteiras** signature e Mundial-themed (Predator, Mercurial, signature de Vini Jr/Messi/Mbappé)
- **Bolas oficiais** Mundial (Adidas faz a bola do FIFA WC)

Detectado em: Mercado Libre (BR/MX/AR/CO) + cross-reference com news. Cada drop é evento de bilhões de impressions globais.

## Identidade visual

- Paleta: Black (#000) / Dark gray (#1A1A1A) / Medium gray (#333) — esquema Performance
- Logo: 3-stripes Performance (Wikimedia hot-link, com `filter: invert(1)` no CSS pra virar branco no header escuro)
- Fonte: Inter (do template original)

## Fontes de dados (idem template)

| Fonte | Função | Status |
|---|---|---|
| Google News (RSS) | Notícias por marca/mercado | OK |
| GDELT | Notícias internacionais | Rate-limited frequentemente |
| INPI proxy | Registros de marca | OK |
| Mercado Libre | Lançamentos oficiais (jerseys/chuteiras/bolas) | OK |
| YouTube RSS | Vídeos oficiais dos canais | OK |
| Meta Ad Library | Anúncios ativos no Facebook/Instagram | OK (token compartilhado) |
| Google Trends interest_over_time | Search Interest por marca | OK |
| Wikipedia pageviews | Tráfego em páginas | OK |

## Credenciais

- **Meta Ad Library token:** compartilhado via `C:\Users\vinic\.warroom\meta-token.txt` (mesmo do cocacola-warroom — gerado pelo Edson Loiola, app `569179675436325`, expira ~07/06/2026). Aplicado automaticamente como `META_AD_LIBRARY_TOKEN` no GitHub Secrets deste repo durante a Fase 5 do agente.

## URLs

- **Repo:** https://github.com/vinicanola/adidas-warroom *(preenchido após Fase 5)*
- **Dashboard:** https://adidas-warroom.vercel.app *(preenchido após Fase 6)*
- **GitHub Actions:** https://github.com/vinicanola/adidas-warroom/actions

## Limitações conhecidas

1. **Token Meta expira em ~07/06/2026** — Edson re-gera, sobrescrever `C:\Users\vinic\.warroom\meta-token.txt`, depois rodar `gh secret set META_AD_LIBRARY_TOKEN --repo vinicanola/adidas-warroom --body $(Get-Content C:\Users\vinic\.warroom\meta-token.txt -Raw).Trim()`.
2. **Mizuno e Asics** — fortes em running, fracos em soccer. Provavelmente vão aparecer com 0 signals (filtro is_relevant exige contexto futebol). Isso é correto/desejado.
3. **YouTube handles** — alguns podem não resolver na 1ª run (`@MizunoOfficial`, `@OlympikusOficial`). Coletor degrada graceful — não quebra, só pula.
4. **Nike** tem comportamento bipolar: aparece como Selecao em BR (legítimo) e ambush em MX/AR/CO. Dashboard já trata via `classify_sponsorship` market-aware.

## Como retomar

```powershell
git clone https://github.com/vinicanola/adidas-warroom.git
cd adidas-warroom
code .
# No Claude Code: "Leia HANDOFF.md e me da resumo do estado atual"
```

---

*Doc gerado em 2026-05-09 via agente warroom-builder.*
