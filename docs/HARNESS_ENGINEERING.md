# Harness Engineering — MIQA Backend

> **STATUS: NOVO / NÃO TESTADO** — Implementado em 2026-03-16. Precisa ser validado antes de depender disso em PRs reais.

## O que foi adicionado

| Arquivo | Propósito |
|---|---|
| `risk-policy.json` | Contrato central: define risk tiers por path e quais checks são obrigatórios por tier |
| `.github/workflows/risk-policy-gate.yml` | Preflight gate — roda primeiro, detecta tier, bloqueia merge se checks faltarem |
| `.github/workflows/ci.yml` | CI principal — lint + testes Python (roda após gate) |
| `.github/workflows/review-rerun.yml` | Solicita re-review ao code review agent quando novo commit é pushed (com SHA dedupe) |

## Como funciona o fluxo

```
PR aberto / commit pushed
        ↓
  risk-policy-gate   ← roda SEMPRE primeiro
        ↓
  Detecta tier (high / medium / low)
        ↓
  ┌─────────────────────────────────┐
  │ high  → ci/lint + ci/test       │
  │ medium → ci/test                │
  │ low   → só o gate               │
  └─────────────────────────────────┘
        ↓
  review-rerun (se novo commit → pede re-review)
```

## Risk tiers definidos

**High** (AI core, DB, Filecoin, config):
- `local_processing/**` — modelos de IA, heurísticas
- `db/migrations/**` e `db/repository.py` — schema e queries
- `filecoin/**` — publicação IPFS/Filecoin
- `config/**` — configuração do sistema
- `main.py` — entry point

**Medium** (infra de runtime):
- `cloud_client/**`, `connectivity/**`, `metrics/**`, `edge/**`

**Low** (docs, utils, requirements):
- `docs/**`, `utils/**`, `*.md`, `requirements.txt`

## TODO — o que precisa ser testado

- [ ] Abrir um PR de teste e verificar se `risk-policy-gate` aparece nos checks do GitHub
- [ ] Verificar se a detecção de tier está correta para mudanças em `local_processing/`
- [ ] Verificar se `ci / test` roda corretamente (precisa de testes criados — ver README Development Status)
- [ ] Configurar Branch Protection Rules no GitHub:
  - Settings → Branches → main → Require status checks
  - Adicionar: `risk-policy-gate`, `ci / test`, `ci / lint`
- [ ] Testar `review-rerun` com um code review agent (ex: CodeRabbitAI)

## Próximos passos sugeridos

1. **Criar testes** — o item P1 do README. Sem testes, o `ci / test` passa vazio.
2. **Ativar Branch Protection** — sem isso, os workflows rodam mas não bloqueiam merge.
3. **Plugar code review agent** — CodeRabbitAI tem plano gratuito para open source.

## Referência

Baseado no padrão descrito em: [Code Factory: How to setup your repo so your agent can auto write and review 100% of your code](https://twitter.com/) (thread, 2026-03)
