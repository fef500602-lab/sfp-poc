# CHANGELOG — SFP PoC

Histórico de versões do pipeline SFP (Simple Function Points via tree-sitter + Azure OpenAI).
Cada entrada registra as mudanças, impacto nos números e contexto de decisão.

---

## v4.5 — Junho 2026 — Validação de independência de framework (SFP-13)

### O que mudou

**extractor.py**

- `IGNORE_CLASS_NAME_SUFFIXES["python"]`: adicionados sufixos FastAPI/Pydantic que representam DTOs de transporte, não entidades de domínio — `inresponse`, `forresponse`, `increate`, `inupdate`, `inlogin`, `withtoken`, `filters`, `settings`, `mixin`
- `IGNORE_BASE_CLASSES["python"]`: adicionadas bases FastAPI — `basesettings`, `appsettings`, `rwschema`, `enum`
- `HIGH_PRIORITY_ROLES`: adicionados `dependency` e `dependencies` (DI do FastAPI) e `errors` (error handlers) como papéis de infraestrutura — funções nesses diretórios deixam de ser classificadas como EPs
- Corrigido bug `j` (stray character) em `_post_process_repository` que causaria `NameError` em runtime
- Restaurado bloco `if __name__ == "__main__":` truncado durante rebase

**Repositórios processados (novos)**

| Repo | Framework | FD | EP | Total |
|---|---|---|---|---|
| conduit-python-fastapi    | Python / FastAPI   | 14 | 19 | 33 |
| conduit-typescript-nestjs | TypeScript / NestJS |  5 | 20 | 25 |
| conduit-kotlin-ktor-alt   | Kotlin / Ktor alt. |  6 |  0 |  6 |
| conduit-kotlin-quarkus    | Kotlin / Quarkus   |  4 | 15 | 19 |

**DECISIONS.md**: ADR-009 adicionado com resultados e conclusões de SFP-13.

### Impacto nos números

| Par comparado | Antes (bug) | Após correção | Veredicto |
|---|---|---|---|
| FastAPI EPs | 82 | 19 | Convergência com Django (18) ✅ |
| NestJS Total | — | 25 | Convergência com Express (25) ✅ |
| Quarkus Total | — | 19 | Dentro do range (22–25) ✅ |

### Baselines RealWorld — sem regressão

| Repositório | FD | EP | Total |
|---|---|---|---|
| realworld-python-django   |  4 | 18 | 22 |
| realworld-nodejs-express  |  6 | 19 | 25 |
| realworld-java-spring     |  4 | 19 | 23 |
| realworld-csharp-dotnet   |  7 | 17 | 24 |
| realworld-kotlin-ktor     |  6 | 40 | 46 ⚠️ |

---

## v4.4 — Maio 2026 — Suporte a Kotlin com calibração completa (Etapa 4)

### O que mudou

**Migração tree-sitter 0.22.3 → 0.25.2**

- `tree-sitter-kotlin` exige `>= 0.23` — migração necessária para suportar Kotlin
- API de instanciação do `Parser` atualizada: `Parser(language)` substitui `parser.language = language`

**extractor.py — suporte Kotlin**

- `object_declaration` (singletons Kotlin) capturado como classe
- Anotações Kotlin (`@GET`, `@POST`, etc.) mapeadas via parser Java (AST equivalente)
- Routing funcional Ktor: `extract_ktor_routes()` detecta rotas declaradas como lambdas (`get("/articles") { ... }`)
- Regras C# adicionadas em `IGNORE_CLASS_NAME_SUFFIXES`: `client`, `schemes`, `names`, `provider`
- Regras Java adicionadas em `IGNORE_METHOD_NAMES`: `isempty`, `dofilter`, `init`, `destroy` (lifecycle `javax.servlet.Filter`)

### Impacto nos números

- Kotlin/Ktor adicionado ao conjunto de validação com EP=40 (outlier — investigação em SFP-09)
- Baselines Python, Java, C# e TypeScript sem alteração

---

## v4.3 — Maio 2026 — Correção join table + DECISIONS.md (SFP-08 / SFP-00c)

### O que mudou

**extractor.py — `classify_hint()` step 9**

Gap identificado: `_is_join_table_candidate()` era chamada apenas nos steps 6/7 (classes com `@Entity`/`@Table`), mas não no step 9 (`file_role=model → FD` direto). Classes Java com Lombok (sem `@Entity`) e C# sem Data Annotations caíam no step 9 como FD automático sem verificação.

Correção: adicionado check no step 9 — se `field_names` indica join table, o item vai para LLM em vez de ser marcado FD automaticamente.

**DECISIONS.md criado**

ADRs 001 a 008 documentados: tree-sitter, arquitetura híbrida, repositórios RealWorld, migração de versão, filtro de rotas de infraestrutura, deduplicação GraphQL, gap join table e outlier Kotlin/Ktor.

### Impacto nos números

| Repositório | FD antes | FD após | Causa |
|---|---|---|---|
| realworld-java-spring | 7 | 4 | `ArticleFavorite` e `FollowRelation` → LLM → não-FD |

---

## v4.2 — Maio 2026 — Proposta tech lead: arquitetura híbrida (SFP-07)

### O que mudou

**Arquitetura do pipeline**

Introdução do modelo híbrido determinístico + LLM:

- `classify_hint()` retorna tupla `(hint, reason)` — rastreabilidade por elemento
- `sfp_hint` assume 4 valores: `data_function`, `elementary_process`, `ignore`, `llm`
- Apenas itens com `sfp_hint: llm` são enviados à LLM, reduzindo custo e aumentando consistência

**extractor.py**

- `INFRA_ROUTES = {"/", "/health", "/ready", "/healthz", "/ping"}` — rotas de health-check filtradas antes de registrar EP
- `file_role: "graphql"` adicionado para arquivos em `graphql/`, `datafetcher/`, `datafetchers/`
- `_post_process_repository()`: pós-processador que remove EPs GraphQL cujo nome já existe confirmado em controller REST (deduplicação REST+GraphQL)

**sfp_analyzer.py**

- `llm_reason` capturado por elemento — justificativa da LLM registrada no JSON de saída
- System prompt atualizado com regra de fronteira do sistema e deduplicação

### Impacto nos números

| Repositório | Total antes | Total após | Principal mudança |
|---|---|---|---|
| realworld-java-spring | ~34 | 23 | 6 EPs GraphQL deduplicados + rotas infra filtradas |
| realworld-kotlin-ktor | — | 50 | Routing Ktor detectado pela primeira vez |

---

## v4.1 — Maio 2026 — Revalidação metodológica completa (Etapa 3.2)

### O que mudou

Correção de quatro grupos de ruído residual após v4.0:

1. **Java Spring** — field resolvers GraphQL (`@DgsData`) e response builders removidos como EP
2. **C# ASP.NET** — dupla contagem de handlers CQRS corrigida
3. **Python Django** — classes abstratas de auditoria (`TimeStampedModel`, etc.) excluídas como FD
4. **TypeScript Node.js** — interfaces em `*.model.ts` (invisíveis ao tree-sitter) tratadas corretamente

### Impacto nos números

| Repositório | Total antes | Total após |
|---|---|---|
| realworld-java-spring     | 67 | 34 |
| realworld-csharp-dotnet   | 45 | 24 |

---

## v4.0 — Maio 2026 — Fronteira do sistema (Etapa 3.1)

### O que mudou

Identificado e corrigido o defeito principal do pipeline: dupla contagem de camadas arquiteturais (controller + service). A metodologia SFP define EP exclusivamente na fronteira do sistema — métodos de serviço sem exposição direta na API não são EPs independentes.

- System prompt da LLM atualizado com regra de fronteira explícita
- Métodos de serviço passam para revisão LLM com contexto de `file_role`

### Impacto nos números

| Repositório | Total antes | Total após |
|---|---|---|
| realworld-java-spring | 96 | 67 |

---

## v3.0 — Abril/Maio 2026 — Integração Azure OpenAI (Etapa 3)

### O que mudou

- Implementado `sfp_analyzer.py`: envio dos elementos `sfp_hint: llm` para Azure OpenAI
- Contexto estrutural completo enviado por elemento: `file_role`, `decorators`, `base_classes`, `hint_reason`
- Código-fonte nunca circula pela LLM — apenas nomes e metadados estruturais
- Resultados salvos em `output/sfp/<repo>.json` com `sfp_final` e `llm_reason` por elemento

---

## v2.0 — Abril 2026 — Extrator tree-sitter completo (Etapas 1-2)

### O que mudou

- `extractor.py` implementado com suporte a Python, Java, JavaScript, TypeScript/TSX e C#
- `tree-sitter` fixado em `0.22.3` (estável — v0.25.x quebrou a API em uso)
- Sistema `sfp_hint` com pré-classificação determinística, `file_role`, `decorators` e `base_classes`
- Filtros de arquivos de teste, configuração e infraestrutura aplicados
- Repositórios RealWorld definidos como conjunto de validação principal

---

## Convenções deste arquivo

- Versões seguem o padrão `v<major>.<minor>` onde `minor` representa iterações de calibração
- Cada entrada inclui impacto quantitativo nos números SFP quando aplicável
- Para contexto de decisão e trade-offs, consultar `DECISIONS.md`
