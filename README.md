# SFP PoC — Simple Function Points via tree-sitter

Prova de conceito para medir evolução funcional de bases de código
usando a metodologia **SFP (Simple Function Points - ISO/IFPUG)**.

---

## Objetivo

Extrair automaticamente de repositórios de código dois elementos SFP:

- **Funções de Dados (FD)** → classes e modelos de dados que representam entidades do domínio
- **Processos Elementares (EP)** → endpoints e métodos que representam operações de leitura/escrita

O resultado alimenta métricas executivas de produtividade e subsidia
estimativas de novos projetos.

---

## Metodologia SFP

O **Simple Function Points (SFP)** é um padrão ISO mantido pelo IFPUG
que simplifica a contagem de pontos de função em dois elementos:

| Elemento SFP          | O que representa             | Como identificamos              |
| --------------------- | ---------------------------- | ------------------------------- |
| Funções de Dados      | Entidades do domínio         | Classes de modelo e entidades   |
| Processos Elementares | Operações de leitura/escrita | Endpoints HTTP e métodos de ação|

### Pipeline de processamento

```
Código fonte (local)
       ↓
[tree-sitter] → extrai classes, métodos, decorators, herança e papel do arquivo
       ↓
[sfp_hint] → pré-classifica cada elemento deterministicamente
       ↓
Arquivo JSON com elementos + contexto estrutural
       ↓
[LLM Azure OpenAI] → sanitiza e conta apenas os casos ambíguos (sfp_hint: llm)
       ↓
Contagem SFP final
```

> O código fonte **nunca circula pela LLM** — apenas nomes de classes,
> métodos e metadados estruturais, garantindo segurança e baixo custo de tokens.

---

## Status do Desenvolvimento

### ✅ Etapa 1 — Repositórios públicos (Concluída)

- Definida estratégia de uso de repositórios públicos **RealWorld**
  como base de validação — mesma aplicação implementada em múltiplas
  linguagens, permitindo comparação direta entre tecnologias
- Ampliada a base com repositórios de perfis arquiteturais distintos:
  Clean Architecture em C# e o framework NestJS em TypeScript
- Incluídos três **casos de borda** para validação de robustez:
  frontend puro (React), biblioteca de framework (Express) e repositório
  sem código (apenas Markdown)
- Repositório público criado no GitHub

### ✅ Etapa 2 — Extrator tree-sitter (Concluída)

- Implementado `extractor.py` com suporte a 5 linguagens (Python, Java,
  JavaScript, TypeScript/TSX, C#)
- Resolvidos conflitos de compatibilidade entre versões do tree-sitter:
  versão `0.25.x` quebrou a API — fixado em `0.22.3` (estável)
- Adicionado filtro de pastas de teste, configuração e gerados
  (`IGNORE_DIRS`) para reduzir ruído (~30% de redução em Java)
- Implementados `validacao.py` e `diagnostico_repos.py` para inspeção
  e classificação preliminar dos resultados

### ✅ Etapa 2.5 — Enriquecimento do extrator (Concluída)

Esta etapa adicionou **contexto estrutural** à extração, transformando
o extrator de um simples listador de nomes em um pré-classificador SFP.

Cada elemento extraído agora carrega:

- `base_classes` — classes pai / interfaces implementadas
- `decorators` — annotations e decorators aplicados
- `file_role` — papel inferido do arquivo pelo caminho (`model`, `controller`,
  `service`, `feature`, `config`, `test`, `ui`, `infrastructure`, etc.)
- `sfp_hint` — pré-classificação determinística (ver seção abaixo)

#### Resultados da pré-classificação (v3.1)

| Repositório              | Linguagem  | FD total | FD → LLM | EP total | EP → LLM |
| ------------------------ | ---------- | -------- | -------- | -------- | -------- |
| realworld-java-spring    | Java       | 11       | 1 (9%)   | 94       | 10 (11%) |
| realworld-csharp-dotnet  | C#         | 7        | 0 (0%)   | 38       | 0 (0%)   |
| realworld-python-django  | Python     | 8        | 0 (0%)   | 30       | 10 (33%) |
| realworld-nodejs-express | TypeScript | 3        | 2 (67%)  | 20       | 0 (0%)   |
| csharp-clean-arch        | C#         | 22       | 7 (32%)  | 42       | 12 (29%) |
| nestjs-framework         | TypeScript | 38       | 25 (66%) | 212      | 99 (47%) |

> **FD → LLM** e **EP → LLM**: elementos que o pré-processador não classificou
> com certeza e foram enviados à LLM na Etapa 3.

#### Principais melhorias implementadas (v2.5 → v3.1)

**Java Spring**
- Adicionados decorators GraphQL DGS: `@DgsQuery`, `@DgsMutation`, `@DgsData`,
  `@DgsSubscription`
- Filtro de `@Override` — implementações de interface não são EPs independentes
- Sufixos de DTOs e infraestrutura ignorados: `Param`, `Response`, `Serializer`,
  `Cursor`, `Validator`, `Dto`, `Resource`, `Envelope`, etc.
- Inferência de `file_role: model` para pacotes `core/` (padrão Spring JDBC
  sem `@Entity`)
- Filtro de construtores Java (detectados como `method_declaration` sem tipo
  de retorno)

**TypeScript / NestJS**
- Corrigido bug crítico em `extract_decorators_ts`: a função parava ao encontrar
  o token `export` antes de alcançar o decorator pai, pois classes NestJS
  exportadas têm estrutura `export_statement → [decorator, "export", class]`.
  Solução: subir ao `grandparent` quando o `parent` é `export_statement`
- Lifecycle methods React (`render`, `componentDidMount`, etc.) adicionados ao
  filtro de métodos padrão

**React / Frontend**
- Adicionado `file_role: ui` para pastas `components/`, `pages/`, `screens/`
- Resultado correto para repositórios frontend: 0 FD / 0 EP (não há lógica
  SFP mensurável em código de apresentação)

**Express / Node.js**
- Adicionada detecção de rotas funcionais via `call_expression`
  (`router.get(path, handler)`) — padrão não capturado pelo extrator
  de declarações de método, pois rotas Express são chamadas de função,
  não declarações
- Nome do EP derivado do método HTTP + path: `GET /articles/:slug` → `getArticlesSlug`

**C# .NET**
- Filtro de construtores C# (`constructor_declaration`)
- Artefato `Task<T>` corrigido: o parser C# lia o tipo de retorno genérico
  como nome de método; `IGNORE_METHOD_NAMES["csharp"]` agora verificado
  antes da regra de `file_role: feature`
- `ServicesExtensions.cs` e similares corretamente classificados como
  `file_role: config`; corrigida prioridade de roles onde `"service"` (substring
  de `ServicesExtensions`) prevalecia sobre `"config"`
- Sufixos CQRS/MediatR ignorados: `Command`, `Query`, `Handler`, `Validator`,
  `Behaviour`, `Envelope`, `Dto`, `Vm`, etc.
- Suporte a Vertical Slice Architecture: arquivos em `Features/` têm
  `file_role: feature` — classes container são ignoradas, métodos são EPs

**Infraestrutura geral**
- `infer_file_role` refatorado com lista `HIGH_PRIORITY_ROLES` verificada
  antes do loop geral; garante que `test`, `migration`, `config`,
  `infrastructure`, `ui` e `feature` sempre têm precedência sobre `model`,
  `service` e `controller`, evitando false-matches por substring

### ✅ Etapa 3 — Integração com LLM (Concluída)

Implementado `sfp_analyzer.py` com arquitetura de duas etapas:

- **Etapa A (automática):** itens com `sfp_hint: "data_function"` ou
  `"elementary_process"` são contados diretamente, sem custo de API
- **Etapa B (LLM):** apenas itens `sfp_hint: "llm"` são enviados à Azure
  OpenAI, com contexto estrutural completo (decorators, herança, file_role,
  linguagem) e prompt especializado em metodologia SFP

#### Contagem SFP — v3.1 (antes da correção metodológica)

| Repositório              | Linguagem  | Auto | LLM env. | FD | EP  | Total SFP |
| ------------------------ | ---------- | ---- | -------- | -- | --- | --------- |
| realworld-csharp-dotnet  | C#         | 45   | 0        | 7  | 38  | **45**    |
| realworld-java-spring    | Java       | 94   | 11       | 11 | 85  | **96**    |
| realworld-python-django  | Python     | 28   | 10       | 8  | 21  | **29**    |
| realworld-nodejs-express | TypeScript | 21   | 2        | 1  | 20  | **21**    |
| csharp-clean-arch        | C#         | 45   | 19       | 17 | 32  | **49**    |
| nestjs-framework         | TypeScript | 126  | 124      | 20 | 149 | **169**   |
| **TOTAL**                |            |      |          | **64** | **345** | **409** |

> ⚠️ Os números acima apresentavam dupla contagem: métodos de Service
> eram classificados como EP além dos métodos de Controller correspondentes,
> inflando a contagem e quebrando a comparabilidade entre linguagens.

### ✅ Etapa 3.1 — Revalidação metodológica (Concluída — branch `fix/sfp-ep-boundary-revalidation`)

Identificado e corrigido defeito metodológico crítico: o extrator contava
métodos em **todas as camadas arquiteturais** como EPs, enquanto a metodologia
SFP define EP exclusivamente na **fronteira do sistema** com o usuário.

Em arquiteturas MVC em camadas (Spring Boot), tanto o Controller quanto o
Service implementavam a mesma operação — gerando dupla contagem sistemática.

**Correções implementadas (v4.0):**

- `classify_hint` separado para `controller` e `service`: métodos de controller
  continuam como `elementary_process`; métodos de service passam para `llm`
  para a LLM decidir se são fronteira real ou implementação interna
- Sufixos `repository`, `service` e `controller` adicionados a
  `IGNORE_CLASS_NAME_SUFFIXES` (Java e C#): repositórios e services não são
  Funções de Dados, mesmo em pacotes de domínio como `core/`
- System prompt do `sfp_analyzer` atualizado com regra de fronteira explícita
  e instrução de deduplicação controller vs. service

#### Contagem SFP — v4.0 (após correção metodológica)

| Repositório              | Linguagem  | Auto | LLM env. | FD | EP  | Total SFP |
| ------------------------ | ---------- | ---- | -------- | -- | --- | --------- |
| realworld-csharp-dotnet  | C#         | 45   | 0        | 7  | 38  | **45**    |
| realworld-java-spring    | Java       | 66   | 35       | 6  | 61  | **67**    |
| realworld-python-django  | Python     | 28   | 10       | 8  | 20  | **28**    |
| realworld-nodejs-express | TypeScript | 21   | 2        | 1  | 20  | **21**    |
| csharp-clean-arch        | C#         | 37   | 26       | 15 | 28  | **43**    |
| nestjs-framework         | TypeScript | 65   | 185      | 18 | 87  | **105**   |
| **TOTAL**                |            |      |          | **55** | **254** | **309** |

> **Convergência RealWorld:** Python Django (28) e Node.js Express (21)
> já convergem para a faixa esperada de ~20-25 SFP. Java Spring (67)
> ainda apresenta ruído residual de ~20 field resolvers `@DgsData` e
> métodos auxiliares de controller — endereçados no backlog v4.1.

### ✅ Etapa 3.2 — Redução de ruído e revalidação completa (Concluída)

Após a correção metodológica v4.0, foram realizadas duas rodadas adicionais
de refinamento (v4.1 e `feature/mongoose-schema-detection`) para eliminar
ruído residual e validar a premissa central do projeto.

#### O que foi identificado e corrigido (v4.1 — backlog v3.2 + v4.1)

**Java Spring — ruído nos EPs auto-classificados**

O projeto implementa duas APIs (REST + GraphQL DGS). O ruído estava nos
field resolvers `@DgsData` — resolvers internos do GraphQL que não são
operações de fronteira — e em response builders sem decorator HTTP
(`articleResponse`, `userResponse`).

Correções: `@DgsData` movido para `IGNORE_DECORATORS`; `@ExceptionHandler`
adicionado a `IGNORE_DECORATORS`; `IGNORE_METHOD_NAME_SUFFIXES` criado para
filtrar response builders por sufixo de nome de método; controller methods
Java sem decorator HTTP redirecionados para `llm`.

**C# .NET — dupla contagem em Vertical Slice Architecture**

Em VSA, cada feature contém um controller method (ex: `ArticlesController.Get`)
e um handler CQRS (ex: `Details.Handle`) representando a *mesma* operação.
Ambos eram auto-classificados como EP, gerando dupla contagem.

Correção: métodos em `feature/` sem decorator HTTP explícito passam para `llm`,
permitindo que a LLM deduplique os pares. Adicionada instrução específica de VSA
ao system prompt do `sfp_analyzer`.

**Python Django — classes abstratas e utilitárias como FD**

`TimestampedModel` (classe base abstrata de auditoria) era contada como FD.
Classes com base `Mixin` (ex: `ArticleViewSet`) eram classificadas como FD
por herança falsa com `models.Model` via substring.

Correções: `TimestampedModel`, `AbstractModel`, `BaseModel` adicionados ao
`IGNORE_CLASS_NAME_SUFFIXES["python"]`; `mixin` e `baseusermanager` adicionados
ao `IGNORE_BASE_CLASSES["python"]`; métodos DRF (`to_internal_value`,
`to_representation`, `get_queryset`) e Django signals (`receiver`) filtrados.

**TypeScript / NestJS — métodos de framework como EP**

Métodos de interface de framework (`canActivate`, `intercept`, `catch`,
`bootstrap`) e classes de infraestrutura (`ExceptionFilter`, `IoAdapter`,
`WebSocketGateway`) eram enviados à LLM desnecessariamente.

Correções: adicionados a `IGNORE_METHOD_NAMES["typescript"]` e
`IGNORE_BASE_CLASSES["typescript"]`/`IGNORE_DECORATORS["typescript"]`.

**Node.js Express — modelos TypeScript invisíveis**

O projeto usa TypeScript `interface` (não classes) para definir entidades,
seguindo a convenção `*.model.ts`. Esses arquivos estavam na pasta `routes/`,
que recebia `file_role: "controller"` — tornando as interfaces invisíveis.

Correção: padrão `.model` adicionado ao `HIGH_PRIORITY_ROLES` com alta
prioridade sobre `routes/`, garantindo que `article.model.ts` → `file_role: model`.
DTOs filtrados por sufixo (`input`, `registered`, `response`, `request`).
`IGNORE_BASE_CLASSES` atualizado com `error` (TypeScript/JS) para filtrar
classes de exceção.

#### Contagem SFP final — v4.1 (após revalidação completa)

| Repositório              | Linguagem  | Auto | LLM env. | FD | EP  | Total SFP |
| ------------------------ | ---------- | ---- | -------- | -- | --- | --------- |
| realworld-csharp-dotnet  | C#         | 7    | 38       | 7  | 17  | **24**    |
| realworld-java-spring    | Java       | 32   | 38       | 7  | 27  | **34**    |
| realworld-python-django  | Python     | 22   | 5        | 4  | 18  | **22**    |
| realworld-nodejs-express | TypeScript | 26   | 2        | 6  | 20  | **26**    |
| csharp-clean-arch        | C#         | 33   | 28       | 15 | 24  | **39**    |
| nestjs-framework         | TypeScript | 67   | 133      | 21 | 84  | **105**   |
| **TOTAL**                |            |      |          | **60** | **190** | **250** |

> **Premissa validada:** as quatro implementações REST puras da mesma
> aplicação RealWorld convergem para **22–26 SFP** independente de linguagem
> e arquitetura. Java Spring registra 34 SFP por expor também uma API GraphQL
> (7 EPs adicionais via `@DgsQuery`/`@DgsMutation`).

#### Por que NestJS (105) e C# Clean Arch (39) são maiores?

Os repositórios complementares **não implementam a mesma aplicação** que o
conjunto RealWorld — por isso a comparação direta de números não é válida.

**NestJS Framework (105 SFP)**

O repositório `nestjs-framework` é o **código-fonte do próprio framework**,
não uma aplicação de negócio. Contém mais de 10 aplicações de exemplo
empacotadas em pastas `samples/` independentes (cats-app, sql-typeorm,
mongoose, passport, graphql, microservices, etc.). A mesma entidade `User`
aparece 6 vezes — uma por exemplo. A contagem de 105 SFP representa a
soma de ~10 mini-aplicações distintas (~10 SFP cada), não uma aplicação
inflada. Em uso real, a ferramenta seria aplicada a repositórios de
aplicação, não a repositórios de framework.

**C# Clean Arch (39 SFP)**

É uma aplicação **diferente** (template de Todo + Weather, não RealWorld).
Os 39 SFP têm ruído residual: `BaseEntity`, `BaseAuditableEntity`,
`PaginatedList`, `Result` são infraestrutura contada como FD; métodos
`Map` do AutoMapper são contados como EP. As entidades e operações reais
são ~4 FDs (TodoItem, TodoList, Colour, WeatherForecast) e ~9 EPs (CRUD
de Todo + Weather). O repositório é útil para validar padrões arquiteturais
(CQRS, Clean Arch), não para benchmarking de tamanho funcional.

**Java Spring (34 SFP)**

Mesma aplicação RealWorld, mas com **duas APIs**: REST (~20 EPs) e GraphQL
DGS (~7 EPs via `@DgsQuery`/`@DgsMutation`). Excluindo o GraphQL, o projeto
ficaria em ~27 SFP — dentro da faixa esperada. A diferença é funcionalidade
real, não ruído.

**O conjunto comparável é exclusivamente o RealWorld:**

| Repo | SFP | Δ em relação à média (24) |
| ---- | --- | ------------------------- |
| Python Django | 22 | -8% |
| C# .NET | 24 | referência |
| Node.js Express | 26 | +8% |
| Java Spring | 34 | +42% justificado (REST + GraphQL) |

A variação de ±8% entre as três implementações REST puras é estatisticamente
irrelevante para uma métrica de tamanho funcional. **A premissa está validada.**

### ✅ Etapa 4 — Suporte a Kotlin (Concluída — branches `update` + `fix/kotlin-calibration`)

Adicionado suporte à linguagem Kotlin via `tree-sitter-kotlin`, com upgrade
do tree-sitter de `0.22.3` para `0.25.2`.

**O que foi implementado (branch `update`):**
- Importação e configuração do parser `tree-sitter-kotlin`
- Regras de pré-classificação Kotlin: `IGNORE_CLASS_NAME_SUFFIXES`,
  `IGNORE_METHOD_NAMES`, `DATA_FUNCTION_BASE_CLASSES`,
  `DATA_FUNCTION_DECORATORS`, `ELEMENTARY_PROCESS_DECORATORS`,
  `IGNORE_BASE_CLASSES` e `IGNORE_DECORATORS`
- Reuso dos extractores de base class e decorator do Java
  (Kotlin annotations têm a mesma estrutura AST)
- Repositório de validação: `realworld-kotlin-ktor`
  (mesma aplicação RealWorld implementada em Kotlin + Ktor)

**Calibração realizada (branch `fix/kotlin-calibration`):**

- **`IGNORE_BASE_CLASSES["kotlin"]`**: adicionadas classes base do Exposed ORM
  (`table`, `uuidtable`, `inttable`, `longtable`) — definições de tabela não
  são entidades de domínio SFP
- **`classify_hint` rule 9 — Kotlin**: projetos Kotlin colocam DTOs e entidades
  no mesmo pacote `models/`. A regra que auto-classifica tudo em `file_role:
  model` como `data_function` foi tornada específica para Kotlin: classes sem
  herança de entidade confirmada vão à LLM
- **`extract_ktor_routes()`**: nova função análoga ao `extract_express_routes()`
  para detectar o padrão Ktor — `get("/path") { ... }` — routing funcional
  direto sem objeto receptor, invisível ao detector de Express
- **Regra de controller sem decorator estendida ao Kotlin**: container functions
  `fun Route.articles(...)` eram auto-EP; agora vão para LLM (e são rejeitadas)

**Evolução dos resultados:**

| Fase | FD | EP | Total |
| ---- | -- | -- | ----- |
| Inicial (branch `update`) | 28 | 4 | 32 |
| Após calibração (branch `fix/kotlin-calibration`) | ~9 | ~20 | ~29 |

**Descobertas e limitações documentadas:**

- **Tabelas de junção como FD:** `ArticleTags`, `FavoriteArticle`, `ArticleComment`,
  `Followings` são contadas como FD pela LLM. Em SFP estrito, tabelas de junção
  sem atributos próprios não são FDs separadas — representam relacionamentos das
  entidades principais. A LLM defende que representam "grupos lógicos de dados de
  negócio", o que é metodologicamente defensável. Aceito como limitação conhecida.

- **Routing Ktor aninhado**: a implementação atual detecta apenas rotas com path
  explícito (`get("/path") { ... }`). Rotas aninhadas via `route("/prefix") { ... }`
  sem path no verbo não são capturadas. Baixo impacto no projeto RealWorld validado.

Os outros repositórios do conjunto de validação **não sofreram regressão**
com o upgrade do tree-sitter.

### ⏳ Etapas Futuras

#### Backlog Kotlin
- Refinar filtros de tabelas de junção Exposed sem atributos próprios
- Suporte a routing Ktor aninhado (`route("/prefix") { get { ... } }`)
- Validar com projetos Kotlin Spring Boot (annotations similares ao Java)

#### Roadmap técnico

- Suporte a repositórios internos via Azure DevOps
- Análise histórica por commits (evolução ao longo do tempo)
- Dashboard executivo de métricas

---

## Arquitetura do Extrator

### Sistema sfp_hint

O `sfp_hint` é a pré-classificação atribuída a cada elemento pelo extrator
antes do envio à LLM. Reduz custo e aumenta consistência ao eliminar da LLM
os casos com resposta determinística.

| Valor               | Significado                                          | Destino        |
| ------------------- | ---------------------------------------------------- | -------------- |
| `data_function`     | Certeza: é uma Função de Dados SFP                   | Conta como FD  |
| `elementary_process`| Certeza: é um Processo Elementar SFP                 | Conta como EP  |
| `ignore`            | Certeza: não é SFP (infraestrutura, teste, config)   | Descartado     |
| `llm`               | Ambíguo: precisa de julgamento da LLM                | Enviado à LLM  |

### Lógica de classificação (`classify_hint`)

A função `classify_hint` aplica as regras na seguinte ordem de prioridade:

1. `file_role` em (`migration`, `test`, `config`, `ui`, `infrastructure`) → **ignore**
2. Método em `IGNORE_METHOD_NAMES` da linguagem → **ignore**
3. `file_role == "feature"` → classes são **ignore**, métodos são **elementary_process**
4. Sufixo do nome de classe em `IGNORE_CLASS_NAME_SUFFIXES` → **ignore**
5. `base_classes` em `IGNORE_BASE_CLASSES` → **ignore**
6. `decorators` em `IGNORE_DECORATORS` → **ignore**
7. `base_classes` em `DATA_FUNCTION_BASE_CLASSES` → **data_function**
8. `decorators` em `DATA_FUNCTION_DECORATORS` → **data_function**
9. `decorators` em `ELEMENTARY_PROCESS_DECORATORS` → **elementary_process**
10. `file_role == "model"` → **data_function**
11. `file_role` em (`controller`, `service`) → **elementary_process**
12. `file_role` em (`serializer`, `repository`) → **ignore**
13. Caso nenhuma regra se aplique → **llm**

### Papel do arquivo (`file_role`)

O papel do arquivo é inferido pelo caminho, com prioridade explícita para
evitar ambiguidades por substring:

| Role             | Patterns detectados                              | Comportamento SFP              |
| ---------------- | ------------------------------------------------ | ------------------------------ |
| `test`           | test, tests, spec, mock, stub, fixture           | Tudo ignorado                  |
| `migration`      | migration, migrations                            | Tudo ignorado                  |
| `config`         | config, settings, startup, middleware, extensions| Tudo ignorado                  |
| `infrastructure` | infrastructure                                   | Tudo ignorado                  |
| `ui`             | component, page, screen, layout, widget          | Tudo ignorado                  |
| `feature`        | feature, features                                | Classes ignoradas, métodos = EP|
| `model`          | model, entity, domain, core, aggregate           | Classes = FD                   |
| `serializer`     | serial, dto, schema, mapper                      | Tudo ignorado                  |
| `repository`     | repositor, repo, dao                             | Tudo ignorado                  |
| `controller`     | view, controller, api, endpoint, route           | Métodos = EP                   |
| `service`        | service, usecase, command, query, handler        | Métodos = EP                   |

---

## Linguagens Suportadas

| Linguagem  | Framework típico  | Parser                 | Versão | Observação                              |
| ---------- | ----------------- | ---------------------- | ------ | --------------------------------------- |
| Python     | Django, FastAPI   | tree-sitter-python     | 0.21.0 | Suporte a decorators e herança          |
| Java       | Spring Boot       | tree-sitter-java       | 0.21.0 | Suporte a annotations e generics        |
| JavaScript | React, Node.js    | tree-sitter-javascript | 0.21.4 | Inclui detecção de rotas Express        |
| TypeScript | NestJS, Angular   | tree-sitter-typescript | 0.21.2 | Suporte a decorators e export_statement |
| TSX        | React TypeScript  | tree-sitter-typescript | 0.21.2 | Parser tsx separado para arquivos .tsx  |
| C#         | ASP.NET Core      | tree-sitter-c-sharp    | 0.21.3 | Suporte a atributos e VSA               |
| Kotlin     | Ktor, Spring Boot | tree-sitter-kotlin     | 1.1.0  | ⚠️ Funcional, calibração em andamento  |

---

## Linguagens Fora do Escopo da PoC

### ❌ Sem relevância para contagem SFP

Linguagens que não contêm lógica funcional mensurável pela metodologia SFP —
não possuem entidades de domínio nem operações de negócio.

| Linguagem                  | Motivo da exclusão                                            |
| -------------------------- | ------------------------------------------------------------- |
| YAML                       | Configuração de CI/CD e infraestrutura — sem lógica funcional |
| JSON                       | Dados estáticos e configuração — sem lógica funcional         |
| XML                        | Configuração de projeto e manifests — sem lógica funcional    |
| TOML                       | Configuração de projeto                                       |
| Markdown                   | Documentação                                                  |
| CSS / SCSS                 | Estilo visual — sem lógica funcional                          |
| HTML                       | Estrutura visual — sem lógica funcional                       |
| SQL                        | Fora do escopo da PoC — pode ser avaliado futuramente         |
| Shell / Batch / PowerShell | Scripts de automação — sem models ou endpoints                |
| Groovy                     | Usado em Jenkinsfiles — infraestrutura de CI/CD               |

### ⚠️ Incompatibilidade técnica com tree-sitter 0.22.3

Linguagens com interesse potencial mas bloqueadas pela versão estável do
tree-sitter fixada na PoC.

| Linguagem | Motivo técnico                                                                                 |
| --------- | ---------------------------------------------------------------------------------------------- |
| Kotlin    | Pacote `tree-sitter-kotlin` requer tree-sitter >= 0.23 — incompatível com versão estável atual |
| Swift     | Pacote `tree-sitter-swift 0.0.1` em estágio inicial — instável para uso em produção            |
| Dart      | Sem pacote disponível no PyPI                                                                  |

> Kotlin, Swift e Dart serão reavaliados quando a versão
> do tree-sitter for atualizada em etapas futuras do projeto.

### 🔶 Baixa prioridade para a PoC

Linguagens tecnicamente viáveis mas com baixa representatividade nos
projetos corporativos alvo.

| Linguagem         | Motivo                                                           |
| ----------------- | ---------------------------------------------------------------- |
| C / C++           | Raramente usados em aplicações web/mobile corporativas           |
| Java Server Pages | Tecnologia legada — baixa representatividade nos projetos atuais |
| VBScript          | Tecnologia legada                                                |
| Prolog            | Nicho — sem representatividade nos projetos da empresa           |

---

## Conjunto de Validação

### Repositórios Principais

Mesma especificação de aplicação (RealWorld) implementada em múltiplas
linguagens — permite comparação direta entre tecnologias e validação
cruzada dos resultados SFP.

| Repositório              | Linguagem  | Arquivos | Arquitetura         |
| ------------------------ | ---------- | -------- | ------------------- |
| realworld-java-spring    | Java       | 93       | Spring Boot MVC     |
| realworld-csharp-dotnet  | C#         | 64       | ASP.NET Minimal API |
| realworld-python-django  | Python     | 34       | Django REST         |
| realworld-nodejs-express | TypeScript | 28       | Express.js          |

### Repositórios Complementares

Repositórios com arquiteturas distintas dos RealWorld, incluídos para
ampliar a cobertura de padrões.

| Repositório       | Linguagem  | Arquivos | Arquitetura                    |
| ----------------- | ---------- | -------- | ------------------------------ |
| csharp-clean-arch | C#         | 130      | Clean Architecture + CQRS      |
| nestjs-framework  | TypeScript | 327      | NestJS (repositório do framework)|

### Casos de Borda (fora do conjunto de validação principal)

| Repositório        | Motivo da exclusão |
| ------------------ | ------------------ |
| realworld-react-js | **Frontend puro** — componentes UI não mapeiam para SFP. O extrator filtra corretamente (0 FD / 0 EP), mas o repositório não representa uma aplicação backend mensurável. Mantido para validar o comportamento do filtro `file_role: ui`. |
| edge-express-lib   | **Repositório de framework**, não de aplicação. Contém o código-fonte do Express.js e demos de exemplo. O extrator captura as rotas corretamente, mas os números não têm significado de negócio. **Limitação conhecida:** a ferramenta não distingue automaticamente código de framework de código de aplicação — requer triagem manual do repositório de entrada. |
| edge-only-markdown | **Sem código-fonte** — valida que o extrator não quebra com repositórios sem linguagens suportadas (resultado 0 FD / 0 EP esperado e obtido). |

---

## Como Configurar

### Pré-requisitos

- Python 3.11+
- Git

### Passo a passo

**1. Clone o repositório**

```bash
git clone https://github.com/fef500602-lab/sfp-poc.git
cd sfp-poc
```

**2. Crie e ative o ambiente virtual**

```bash
# Windows
python -m venv .venv
.venv\Scripts\Activate.ps1

# Linux/Mac
python -m venv .venv
source .venv/bin/activate
```

**3. Instale as dependências**

```bash
pip install -r requirements.txt
```

**4. Clone os repositórios para análise**

```bash
# Repositórios RealWorld (conjunto principal)
git clone https://github.com/gothinkster/spring-boot-realworld-example-app repos/realworld-java-spring
git clone https://github.com/gothinkster/aspnetcore-realworld-example-app repos/realworld-csharp-dotnet
git clone https://github.com/gothinkster/django-realworld-example-app repos/realworld-python-django
git clone https://github.com/gothinkster/node-express-realworld-example-app repos/realworld-nodejs-express

# Repositórios complementares
git clone https://github.com/gothinkster/react-redux-realworld-example-app repos/realworld-react-js
```

---

## Como Executar

**Extração via tree-sitter**

```bash
python src/extractor/extractor.py
```

**Diagnóstico detalhado por repositório**

```bash
python src/extractor/diagnostico_repos.py
```

**Resultados gerados em:**

```
output/
├── realworld-python-django.json
├── realworld-nodejs-express.json
├── realworld-react-js.json
├── realworld-java-spring.json
├── realworld-csharp-dotnet.json
├── csharp-clean-arch.json
├── nestjs-framework.json
└── consolidated_report.json
```

---

## Estrutura do Projeto

```
sfp-poc/
├── README.md                    ← documentação completa
├── requirements.txt             ← dependências Python
├── repos/                       ← repositórios analisados (git clone aqui)
├── src/
│   └── extractor/
│       ├── extractor.py         ← pipeline principal: tree-sitter + sfp_hint
│       ├── diagnostico_repos.py ← diagnóstico detalhado por repositório
│       └── validacao.py         ← validação rápida dos resultados
└── output/                      ← JSONs com resultados por repositório
```
