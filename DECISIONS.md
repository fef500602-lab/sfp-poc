# Architecture Decision Records — SFP PoC

Registro de decisões de arquitetura, limitações conhecidas e trade-offs do projeto.
Cada entrada documenta o contexto do problema, a decisão tomada e suas consequências.

---

## ADR-001 — Uso de tree-sitter para extração de símbolos

**Data:** Abril 2026
**Status:** Vigente

### Contexto
Precisávamos extrair nomes de classes, métodos, decorators e herança de repositórios em múltiplas linguagens, sem enviar código-fonte a serviços externos.

### Decisão
Usar `tree-sitter` via Python para parsear a AST de cada arquivo e extrair apenas metadados estruturais (nomes, anotações, hierarquia). O código-fonte nunca sai da máquina local.

### Consequências
- ✅ Segurança: código-fonte não circula por APIs externas
- ✅ Custo baixo: apenas metadados são enviados à LLM
- ✅ Velocidade: extração local em segundos por repositório
- ⚠️ Compatibilidade: tree-sitter 0.25.x quebrou a API usada em 0.22.x — migração necessária (ver ADR-004)
- ⚠️ Cobertura de linguagens limitada: Kotlin, Swift e Dart têm suporte instável (ver README)

---

## ADR-002 — Arquitetura híbrida: pré-classificador determinístico + LLM

**Data:** Abril 2026
**Status:** Vigente

### Contexto
Classificar 100% dos símbolos extraídos via LLM seria caro e inconsistente. Classificar 100% deterministicamente seria impreciso para casos ambíguos (arquiteturas variadas, padrões não convencionais).

### Decisão
Pipeline em duas etapas:

1. **Extrator (tree-sitter):** pré-classifica cada símbolo com `sfp_hint`:
   - `data_function` — certeza de que é FD
   - `elementary_process` — certeza de que é EP
   - `ignore` — certeza de que não é SFP
   - `llm` — ambíguo, precisa de julgamento

2. **Analyzer (Azure OpenAI):** recebe apenas os itens com `sfp_hint: llm` e decide com contexto estrutural completo (decorators, herança, file_role, linguagem).

### Consequências
- ✅ Custo reduzido: apenas casos ambíguos consomem tokens
- ✅ Consistência: casos determinísticos não dependem de variação do modelo
- ✅ Auditabilidade: cada decisão tem rastreabilidade via `hint_reason`
- ⚠️ A LLM **não pode ser removida** do processo, nem parcialmente — é a garantia de confiabilidade para casos borderline. Otimizações (modelo menor, fine-tuning) ficam no backlog.

---

## ADR-003 — Repositórios RealWorld como base de validação

**Data:** Abril 2026
**Status:** Vigente

### Contexto
Precisávamos de uma base para validar se o pipeline mede funcionalidade e não artefatos de linguagem. A validação exige a mesma aplicação implementada em múltiplas linguagens.

### Decisão
Usar os repositórios do projeto [gothinkster/realworld](https://github.com/gothinkster/realworld) como conjunto de validação principal. A mesma aplicação (Conduit — plataforma de blogging) está disponível em Python/Django, Java/Spring, C#/ASP.NET, Node.js/Express, Kotlin/Ktor e React/JS.

### Resultado esperado
Contagens SFP similares entre linguagens para a mesma aplicação — variações indicam ruído no pipeline ou particularidades arquiteturais da implementação.

### Resultados observados (pipeline v4.3+)

| Linguagem | FD | EP | Total |
|---|---|---|---|
| Python / Django | 4 | 18 | **22** |
| Node.js / Express | 6 | 19 | **25** |
| Java / Spring | 4 | 19 | **23** |
| C# / ASP.NET | 7 | 17 | **24** |
| Kotlin / Ktor | 10 | 40 | **50** ⚠️ |

Python, Node, Java e C# convergem em 22–25 pontos. **Kotlin é outlier** — investigação em andamento (ver ADR-007).

---

## ADR-004 — Migração tree-sitter 0.22.3 → 0.25.2 e suporte Kotlin

**Data:** Maio 2026
**Status:** Vigente

### Contexto
O pacote `tree-sitter-kotlin` requer tree-sitter ≥ 0.23. A versão estável em uso (0.22.3) era incompatível. A migração para 0.25.x quebrou a API de instanciação do `Parser`.

### Decisão
- Migrar para `tree-sitter==0.25.2`
- Substituir `parser.language = language` por `Parser(language)` (nova API)
- Adicionar suporte a Kotlin com regras de pré-classificação específicas
- Reutilizar os parsers de Java para extração de base classes e decorators Kotlin (estrutura AST equivalente)

### Consequências
- ✅ Suporte a Kotlin habilitado
- ✅ `object_declaration` do Kotlin (singletons) capturado corretamente
- ⚠️ Kotlin co-localiza DTOs e entidades em pastas `models/` — todos os modelos vão à LLM (sem auto-classificação como FD)

---

## ADR-005 — Filtragem de rotas de infraestrutura

**Data:** Maio 2026
**Status:** Vigente

### Contexto
Rotas como `/health`, `/ready`, `/ping` e `/` estavam sendo extraídas e contadas como Processos Elementares. Essas rotas são infraestrutura operacional (health-check, readiness probe), não operações de negócio SFP.

### Decisão
Definir `INFRA_ROUTES = {"/", "/health", "/ready", "/healthz", "/ping"}` e filtrar nos extratores de rotas Ktor e Express antes de registrar o EP.

### Consequências
- ✅ Redução de ruído: rotas de saúde não inflam a contagem de EPs
- ✅ Compatível com Kubernetes e ambientes cloud-native

---

## ADR-006 — Deduplicação REST + GraphQL

**Data:** Maio 2026
**Status:** Vigente

### Contexto
Repositórios que expõem a mesma operação de negócio por REST e GraphQL (ex: `createArticle` em `ArticlesController.java` e `ArticleMutation.java`) geravam dupla contagem de EPs.

**Caso real identificado:** `realworld-java-spring` tem camada GraphQL coexistindo com REST — 6 EPs duplicados detectados e removidos na pipeline v4.3.

### Decisão
- Novo `file_role: "graphql"` para arquivos em pastas `graphql/`, `datafetcher/`, `datafetchers/`
- Métodos GraphQL vão à LLM com contexto de canal paralelo
- Pós-processador (`_post_process_repository`) remove EPs GraphQL cujo nome já existe confirmado em controller REST

### Consequências
- ✅ Elimina dupla contagem REST+GraphQL automaticamente
- ✅ Preserva resolvers GraphQL como EP quando não há controller REST correspondente
- ⚠️ Dedup por nome — colisões de nome entre endpoints distintos são raras mas possíveis

---

## ADR-007 — Limitação conhecida: detecção de join tables

**Data:** Maio 2026
**Status:** Parcialmente corrigido — investigação em andamento

### Contexto
Tabelas associativas many-to-many sem atributos de negócio próprios (ex: `ArticleFavorite` com apenas `articleId + userId`) não são Funções de Dados independentes pela metodologia SFP. O pipeline as classificava incorretamente como FD.

### Problema identificado
A detecção de join tables (`_is_join_table_candidate`) foi implementada nos steps 6 e 7 do `classify_hint` — que cobrem apenas classes com **anotação ORM explícita** (`@Entity`, `@Table`) ou **herança de entidade**.

Projetos que usam:
- **Java com Lombok + MyBatis/JOOQ** (sem `@Entity`)
- **C# com plain model classes** (sem Data Annotations EF)

...têm suas classes caindo no **step 9** (`file_role=model → FD`), que não executava o check de join table.

**Caso concreto — `realworld-java-spring`:**

```
ArticleFavorite  fields=['articleId', 'userId']   → era auto-FD, deveria ir à LLM
FollowRelation   fields=['userId', 'targetId']    → era auto-FD, deveria ir à LLM
```

Ambas têm apenas Foreign Keys como campos — a função `_is_join_table_candidate` retorna `True` para elas, mas nunca era chamada no step 9.

### Correção aplicada (branch: `fix/sfp-join-table-detection`)

Adicionadas 4 linhas no step 9 do `classify_hint` em `extractor.py`:

```python
# v4.3+: aplica detecção de join table também aqui, para cobrir modelos
# sem anotação ORM explícita (ex: Java com Lombok, C# sem Data Annotations).
if field_names is not None and _is_join_table_candidate(field_names):
    return "llm", (
        f"file_role=model, mas campos {field_names} indicam "
        f"possível join table → LLM decide"
    )
```

### Resultado da correção
Após rodar a pipeline completa:
- `ArticleFavorite` e `FollowRelation` → LLM classificou como **não-FD** ✅
- Java Spring: FD corrigido de **7 → 4** (Article, Tag, Comment, User — entidades reais)
- Contagem Java agora alinhada com as demais linguagens RealWorld (22–25 total)

### Limitação residual
O check de join table ainda depende de `extract_field_names` conseguir extrair os campos via AST. Se a extração retornar lista vazia (ex: classe com campos em arquivo separado, herança múltipla complexa), `_is_join_table_candidate` retorna `False` e a classe é tratada como FD. Isso é conservador — prefere contar a perder — e é aceitável para a PoC.

### Itens de backlog relacionados
- **SFP-04:** Investigar viés por linguagem — Kotlin EP=40 vs 17–19 demais (ver ADR-003)
- Avaliar cobertura de `extract_field_names` para padrões de herança complexos

---

## ADR-008 — Limitação conhecida: viés de contagem EP em Kotlin/Ktor

**Data:** Maio 2026
**Status:** Identificado — investigação pendente (SFP-04)

### Contexto
O repositório `realworld-kotlin-ktor` produz EP=40 com a pipeline v4.3+, enquanto as outras implementações da mesma aplicação convergem em 17–19 EPs. O mesmo app em Python, Java, Node.js e C# varia no máximo 2 pontos entre si. Kotlin desvia em mais do dobro.

| Linguagem | EP | Referência |
|---|---|---|
| Python / Django | 18 | ✅ baseline |
| Node.js / Express | 19 | ✅ baseline |
| Java / Spring | 19 | ✅ baseline |
| C# / ASP.NET | 17 | ✅ baseline |
| **Kotlin / Ktor** | **40** | ⚠️ outlier |

### Hipótese principal
O Ktor usa **routing funcional** — as rotas HTTP são declaradas como lambdas dentro de funções de extensão (`fun Route.articles() { get("/articles") { ... } }`). O extrator captura corretamente as 20 rotas individuais via `extract_ktor_routes`. O problema está nos **métodos da camada de serviço** enviados à LLM.

Em Ktor, diferentemente de Spring ou ASP.NET, frequentemente não existe controller separado do serviço — o serviço pode ser a única fronteira real para algumas operações. Isso faz com que a LLM classifique métodos de serviço como EPs legítimos em vez de ignorá-los como implementação interna, porque tecnicamente no Ktor eles podem ser a fronteira.

### Evidência
- **Auto-classificados (extrator):** 20 EPs — rotas Ktor com path explícito ✅
- **Adicionados pela LLM:** 20 EPs — vindos dos 198 itens enviados como `sfp_hint: llm`
- Os 20 adicionados pela LLM provêm da camada de serviço (`file_role=service`)

### Risco metodológico
Se a contagem inflar sistematicamente em Kotlin, comparações de produtividade entre times que usam Ktor vs Spring serão distorcidas — o custo por ponto de função parecerá artificialmente menor em Kotlin.

### O que investigar (SFP-04 — responsável: estagiária)
1. **Auditar os 20 EPs adicionados pela LLM** em `output/sfp/realworld-kotlin-ktor.json` — quais são? São métodos de serviço sem rota Ktor correspondente ou métodos com rota já capturada?
2. **Verificar dupla contagem:** se `createArticle` (serviço) foi classificado como EP mas `createArticles` (rota Ktor `/articles POST`) já existe como auto-EP, são o mesmo processo elementar contado duas vezes
3. **Hipótese de calibração:** adicionar regra no extrator para que métodos de serviço Kotlin com nome equivalente a uma rota já capturada vão para `ignore` em vez de `llm`
4. **Premissa crítica:** não forçar equalização de contagens entre linguagens — se o resultado calibrado ainda for 30, aceitar e documentar a diferença arquitetural

### Status atual
- Pipeline v4.3+ opera com EP=40 para Kotlin
- Resultado não invalida os demais repositórios
- Aguardando investigação antes de aplicar qualquer calibração

---

## ADR-009 — Validação com implementações alternativas da spec RealWorld (SFP-13)

**Data:** Junho 2026
**Status:** Vigente

### Contexto
Após confirmar a convergência entre Python, Java, Node.js e C# (22–25 SFP), a próxima hipótese era: a contagem é independente do **framework** dentro da mesma linguagem? Dois frameworks do mesmo ecossistema que implementam a mesma aplicação deveriam produzir contagens similares.

### Repositórios processados

| Repo | Framework | FD | EP | Total |
|---|---|---|---|---|
| conduit-python-fastapi    | Python / FastAPI    | 14 | 19 | 33 |
| conduit-typescript-nestjs | TypeScript / NestJS |  5 | 20 | 25 |
| conduit-kotlin-ktor-alt   | Kotlin / Ktor alt.  |  6 |  0 |  6 |
| conduit-kotlin-quarkus    | Kotlin / Quarkus    |  4 | 15 | 19 |

### Conclusões

- **TypeScript**: Express (25) vs NestJS (25) → Delta 0% → **CONVERGIU ✅** — metodologia é independente de framework em TypeScript
- **Python**: Django (22) vs FastAPI (33) → EPs convergem (+6%), FDs divergem (+250%) → diferença arquitetural: FastAPI usa Pydantic schemas que inflam FD; EPs OK
- **Kotlin/Quarkus**: 19 SFP → alinha com baselines Python/Java/Node/C# → confirma que o outlier EP=40 do Ktor é específico do **routing funcional do Ktor** (lambdas), não da linguagem Kotlin
- **Kotlin/Ktor alt.**: 6 SFP (⚠️ subestimado) — repositório alternativo com arquitetura minimalista, sem handlers completos

### Impacto

- Hipótese de independência de framework: **confirmada para TypeScript**, **parcialmente confirmada para Python** (EPs OK, FDs com ruído de DTOs Pydantic)
- Kotlin: o viés identificado em SFP-08/ADR-008 é **específico do Ktor** — Quarkus produz resultado dentro do range esperado

---

## ADR-010 — Estratégia de Validação em Camadas (Triangulação FSM)

**Data:** Julho 2026
**Status:** Vigente

### Contexto

O pipeline SFP (Camada 0) produz contagem automatizada e repetível. Para aumentar a confiabilidade metodológica e viabilizar uso em contratos, estimativas e benchmarking, é necessária uma segunda contagem independente. Nenhum método único cobre todos os projetos — artefatos disponíveis variam por projeto e contexto.

### Decisão: Pipeline de validações em 4 camadas

A estratégia adotada é **triangulação FSM** — conceito estabelecido na literatura de medição de software. Múltiplos métodos independentes são aplicados em sequência, do menor para o maior esforço. A sequência **para** quando dois métodos independentes concordam dentro da faixa de tolerância.

**Referências base:**
- Cuadrado-Gallego, J.J., Machado, F. et al. — "On the conversion between IFPUG and COSMIC software functional size units: A theoretical and empirical study", *Journal of Systems and Software* (JSS), vol. 81, pp. 661–672, **2008**. [PDF disponível](http://www.cc.uah.es/jjcg/Publications/jjcg/JSS2008.pdf)
- Cuadrado-Gallego, J.J. et al. — "IFPUG Function Points to COSMIC Function Points convertibility: A fine-grained statistical approach", *Information and Software Technology* (IST), vol. 98, pp. 1–14, **2018**. DOI: [10.1016/j.infsof.2018.01.005](https://www.sciencedirect.com/science/article/abs/pii/S0950584918300168)

```
Camada 0   →  Pipeline SFP (tree-sitter + Azure OpenAI)            [já implementado]
Camada 1a  →  OpenAPI/Swagger → FT (Funções de Transação)          [SFP-16]
Camada 1b  →  DDL/ER do banco → FD (Funções de Dados)              [SFP-16]
Camada 2   →  Azure DevOps PBIs → contagem por requisitos          [SFP-17]
Camada 3   →  COSMIC FSM (ISO 19761) → método ISO alternativo      [backlog futuro]
Sanidade   →  Back-calculation por esforço histórico               [a qualquer momento]
```

### Critério de parada (convergência)

Se dois métodos independentes concordam dentro de **±15%** para projetos com menos de 500 PF (ou ±10% acima de 500 PF), a validação está completa — não é necessário avançar para a próxima camada.

### Arquitetura de código

Cada validador será implementado como módulo separado em `src/validators/`:

```
src/
├── extractor/          ← Camada 0 (existente)
│   ├── extractor.py
│   └── validacao.py
├── llm/                ← Camada 0 (existente)
│   └── sfp_analyzer.py
└── validators/         ← Camadas 1-3 (a implementar)
    ├── swagger_validator.py    ← Camada 1a: FT via OpenAPI
    ├── ddl_validator.py        ← Camada 1b: FD via DDL/ER
    ├── devops_validator.py     ← Camada 2:  FT+FD via PBIs
    └── orchestrator.py         ← Convergência fuzzy entre camadas
```

Essa estrutura prepara o projeto para evolução futura na escada de maturidade AI.Gile:
- **Atual (Estágio 3):** Human in the Loop — cada módulo rodado manualmente, 
- **Próximo (Estágio 4):** `orchestrator.py` executa camadas automaticamente, escala conforme divergência
- **Futuro:** MCP server expõe o pipeline completo como ferramenta chamável por agentes

### Perguntas operacionais para cada projeto

1. Qual camada é suficiente? (depende de: custo do erro, disponibilidade de artefatos, exigência do cliente)
2. Swagger existe no projeto? (Spring Boot gera automaticamente em `/v3/api-docs`)
3. DDL está acessível? (DBA ou export do banco)
4. Há PBIs (*Product Backlog Item*) escritos no Azure DevOps?

### Consequências

- ✅ Cada projeto VNT pode ser validado no nível adequado ao seu contexto
- ✅ A estrutura `src/validators/` separa responsabilidades e permite desenvolvimento paralelo (devs do projeto)
- ✅ Prepara a arquitetura para automação futura sem reescrever o código existente
- ⚠️ Camada 3 (COSMIC) requer conhecimento específico — backlog futuro, não PoC atual
- ⚠️ Não criar manual de execução agora — README + DECISIONS.md são suficientes para a PoC

---

## ADR-011 — Fuzzy Logic como Fundação Metodológica da Convergência

**Data:** Julho 2026
**Status:** Vigente (fundamento teórico — não implementado em código ainda)

### Contexto

A contagem SFP produz um número único (ex: FD=20, EP=129). Mas toda contagem de Pontos de Função tem incerteza inerente — a própria metodologia IFPUG aceita variação de ±10% entre contadores experientes. Tratar o resultado como número exato passa uma falsa precisão.

### Referências acadêmicas

- **Yau & Tsoi** — "Fuzzy Modeling for Function Points Analysis", *Software Quality Journal*, Springer, vol. 11, pp. 199–216, **2002**. DOI: [10.1023/A:1023716628585](https://link.springer.com/article/10.1023/A:1023716628585) — referência seminal: propõe tratar a contagem de FP como distribuição fuzzy em vez de número pontual
- **Çelik, S. et al.** — "A Neuro-Fuzzy Method to Improving Backfiring Conversion Ratios" (NFFPCM — Neuro-Fuzzy Function Point Calibration Model), arXiv:1508.06191, **2015**. [arXiv](https://arxiv.org/pdf/1508.06191) — mostra 22% de melhoria no MMRE (Mean Magnitude Relative Error) após calibração fuzzy em projetos reais
- **Cuadrado-Gallego, J.J. et al.** — conversão IFPUG ↔ COSMIC com fator ≈1:1 para muitos domínios — base para usar COSMIC como validador cruzado. Ver referências completas no ADR-010.

### Decisão

Adotar o conceito de **intervalo de confiança fuzzy** na apresentação dos resultados:

```
SFP Resultado = (min, central, max)
Exemplo: FD = (17, 20, 23)  |  EP = (115, 129, 143)  |  Confiança: 72%
```

A **confiança aumenta** conforme mais camadas convergem:
- 1 método: confiança baixa (~50%)
- 2 métodos convergindo (±15%): confiança média (~75%)
- 3 métodos convergindo: confiança alta (~90%)
- COSMIC alinhado: confiança máxima (~95%)

### Implementação prática (curto prazo)

Não é necessário implementar lógica fuzzy formal. O `orchestrator.py` calcula:
1. Resultado de cada camada executada
2. Variação entre resultados (%)
3. Score de confiança baseado em quantas camadas concordam e dentro de qual faixa
4. Recomendação: "convergência suficiente" ou "avançar para próxima camada"

### Consequências

- ✅ Comunicação mais honesta com stakeholders — "149 SFP ±10%, confiança 75%" é mais útil que "149 SFP"
- ✅ Justifica metodologicamente por que múltiplas camadas são necessárias
- ✅ Alinha com literatura acadêmica de FSM — aumenta credibilidade em contextos formais
- ⚠️ Requer calibração do score de confiança com dados reais — começar com limiares conservadores

---

## Convenções deste arquivo

- Cada ADR tem um número sequencial e status: `Vigente` | `Substituído por ADR-XXX` | `Descartado`
- Novas decisões de arquitetura, limitações identificadas e trade-offs relevantes devem ser registrados aqui antes (ou junto) do PR
- O relatório Word referencia este arquivo para detalhes técnicos — o docx apresenta o resumo, o DECISIONS.md tem o raciocínio completo
