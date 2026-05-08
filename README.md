# SFP PoC — Simple Function Points via tree-sitter

Prova de conceito para medir automaticamente a complexidade funcional de
repositórios de código pela metodologia **SFP (Simple Function Points — ISO 20926 / IFPUG)**,
sem expor o código-fonte a serviços externos.

---

## Quick Start

### Pré-requisitos

- Python 3.11+
- Git

### Configuração

```bash
# 1. Clone o repositório
git clone https://github.com/fef500602-lab/sfp-poc.git
cd sfp-poc

# 2. Crie e ative o ambiente virtual
python -m venv .venv
source .venv/bin/activate          # Linux/Mac
# .venv\Scripts\Activate.ps1      # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Clone os repositórios de validação (conjunto RealWorld)
git clone https://github.com/gothinkster/spring-boot-realworld-example-app       repos/realworld-java-spring
git clone https://github.com/gothinkster/aspnetcore-realworld-example-app         repos/realworld-csharp-dotnet
git clone https://github.com/gothinkster/django-realworld-example-app             repos/realworld-python-django
git clone https://github.com/gothinkster/node-express-realworld-example-app      repos/realworld-nodejs-express
```

### Execução

```bash
# Extração via tree-sitter (gera JSONs em output/)
python src/extractor/extractor.py

# Diagnóstico detalhado por repositório
python src/extractor/diagnostico_repos.py

# Análise SFP via Azure OpenAI (classifica itens ambíguos)
python src/llm/sfp_analyzer.py
```

Resultados gerados em `output/`:

```
output/
├── realworld-python-django.json
├── realworld-nodejs-express.json
├── realworld-java-spring.json
├── realworld-csharp-dotnet.json
├── csharp-clean-arch.json
├── nestjs-framework.json
└── consolidated_report.json
```

---

## Objetivo

Extrair automaticamente de repositórios de código dois elementos SFP:

- **Funções de Dados (FD)** → classes e modelos de dados que representam entidades do domínio
- **Processos Elementares (EP)** → endpoints e métodos que representam operações de leitura/escrita

O resultado alimenta métricas executivas de produtividade e subsidia estimativas de novos projetos.

---

## Metodologia SFP

O **Simple Function Points (SFP)** é um padrão ISO mantido pelo IFPUG que simplifica
a contagem de pontos de função em dois elementos:

| Elemento SFP          | O que representa             | Como identificamos               |
| --------------------- | ---------------------------- | -------------------------------- |
| Funções de Dados      | Entidades do domínio         | Classes de modelo e entidades    |
| Processos Elementares | Operações de leitura/escrita | Endpoints HTTP e métodos de ação |

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
[LLM Azure OpenAI] → classifica apenas os casos ambíguos (sfp_hint: llm)
       ↓
Contagem SFP final
```

> O código-fonte **nunca circula pela LLM** — apenas nomes de classes,
> métodos e metadados estruturais, garantindo segurança e baixo custo de tokens.

---

## Arquitetura do Extrator

### Sistema sfp_hint

O `sfp_hint` é a pré-classificação atribuída a cada elemento pelo extrator
antes do envio à LLM. Elimina da LLM os casos com resposta determinística,
reduzindo custo e aumentando consistência.

| Valor                | Significado                                        | Destino       |
| -------------------- | -------------------------------------------------- | ------------- |
| `data_function`      | Certeza: é uma Função de Dados SFP                 | Conta como FD |
| `elementary_process` | Certeza: é um Processo Elementar SFP               | Conta como EP |
| `ignore`             | Certeza: não é SFP (infraestrutura, teste, config) | Descartado    |
| `llm`                | Ambíguo: precisa de julgamento da LLM              | Enviado à LLM |

### Lógica de classificação (`classify_hint`)

A função aplica regras na seguinte ordem de prioridade:

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

| Role             | Patterns detectados                               | Comportamento SFP               |
| ---------------- | ------------------------------------------------- | ------------------------------- |
| `test`           | test, tests, spec, mock, stub, fixture            | Tudo ignorado                   |
| `migration`      | migration, migrations                             | Tudo ignorado                   |
| `config`         | config, settings, startup, middleware, extensions | Tudo ignorado                   |
| `infrastructure` | infrastructure                                    | Tudo ignorado                   |
| `ui`             | component, page, screen, layout, widget           | Tudo ignorado                   |
| `feature`        | feature, features                                 | Classes ignoradas, métodos = EP |
| `model`          | model, entity, domain, core, aggregate            | Classes = FD                    |
| `serializer`     | serial, dto, schema, mapper                       | Tudo ignorado                   |
| `repository`     | repositor, repo, dao                              | Tudo ignorado                   |
| `controller`     | view, controller, api, endpoint, route            | Métodos = EP                    |
| `service`        | service, usecase, command, query, handler         | Métodos = EP                    |

---

## Conjunto de Validação

### Repositórios Principais (RealWorld)

Mesma especificação de aplicação implementada em múltiplas linguagens —
permite comparação direta entre tecnologias e validação cruzada dos resultados SFP.

| Repositório              | Linguagem  | Arquivos | Arquitetura         |
| ------------------------ | ---------- | -------- | ------------------- |
| realworld-java-spring    | Java       | 93       | Spring Boot MVC     |
| realworld-csharp-dotnet  | C#         | 64       | ASP.NET Minimal API |
| realworld-python-django  | Python     | 34       | Django REST         |
| realworld-nodejs-express | TypeScript | 28       | Express.js          |
| realworld-kotlin-ktor    | Kotlin     | —        | Ktor                |

### Repositórios Complementares

Repositórios com arquiteturas distintas, incluídos para ampliar a cobertura de padrões.

| Repositório       | Linguagem  | Arquivos | Arquitetura                      |
| ----------------- | ---------- | -------- | -------------------------------- |
| csharp-clean-arch | C#         | 130      | Clean Architecture + CQRS        |
| nestjs-framework  | TypeScript | 327      | NestJS (repositório do framework) |

### Casos de Borda

| Repositório        | Motivo da exclusão do conjunto principal |
| ------------------ | ---------------------------------------- |
| realworld-react-js | **Frontend puro** — 0 FD / 0 EP. Mantido para validar o filtro `file_role: ui`. |
| edge-express-lib   | **Repositório de framework**, não de aplicação. Limitação conhecida: a ferramenta não distingue automaticamente código de framework de código de aplicação — requer triagem manual. |
| edge-only-markdown | **Sem código-fonte** — valida que o extrator não quebra com repositórios sem linguagens suportadas. |

---

## Resultados (v4.1 — final)

### Conjunto RealWorld (comparável)

A premissa central era que a mesma aplicação, implementada em linguagens diferentes,
deve produzir contagens SFP comparáveis. Após revalidação metodológica completa,
a premissa foi confirmada:

| Repositório              | Linguagem  | FD | EP | Total SFP |
| ------------------------ | ---------- | -- | -- | --------- |
| realworld-python-django  | Python     | 4  | 18 | **22**    |
| realworld-csharp-dotnet  | C#         | 7  | 17 | **24**    |
| realworld-nodejs-express | TypeScript | 6  | 20 | **26**    |
| realworld-java-spring    | Java       | 7  | 27 | **34** *  |
| realworld-kotlin-ktor    | Kotlin     | 9  | 24 | **33** *  |

> \* Java Spring e Kotlin Ktor apresentam SFP ligeiramente superior por exporem
> funcionalidade adicional além da spec REST básica (GraphQL DGS e modelos de junção,
> respectivamente). Desconsiderando esses itens, ambos convergem para ~27 SFP.

A variação de ±8% entre as três implementações REST puras (Python, C#, Node.js)
é estatisticamente irrelevante para uma métrica de tamanho funcional.
**A premissa está validada.**

### Repositórios complementares (não comparáveis entre si)

| Repositório       | FD | EP | Total SFP | Observação                              |
| ----------------- | -- | -- | --------- | --------------------------------------- |
| csharp-clean-arch | 15 | 24 | **39**    | Aplicação diferente (Todo + Weather)    |
| nestjs-framework  | 21 | 84 | **105**   | ~10 mini-aplicações de exemplo empacotadas |

> Esses repositórios não implementam a mesma aplicação que o conjunto RealWorld.
> A comparação direta de números não é válida. Ver interpretação detalhada abaixo.

### Por que NestJS (105) e C# Clean Arch (39) são maiores?

**NestJS Framework (105 SFP):** o repositório é o código-fonte do próprio framework,
não uma aplicação de negócio. Contém mais de 10 aplicações de exemplo independentes em `samples/`
(cats-app, sql-typeorm, mongoose, passport, graphql, auth-jwt, etc.).
A mesma entidade `User` aparece 6 vezes — uma por exemplo.
A conta correta é 105 ÷ ~10 exemplos ≈ 10 SFP por mini-aplicação, em linha com os RealWorld.

**C# Clean Arch (39 SFP):** aplicação diferente (Todo + Weather). Tem ruído residual
identificado: `BaseEntity`, `BaseAuditableEntity`, `PaginatedList`, `Result` são
infraestrutura contada como FD; métodos `Map` do AutoMapper são contados como EP.
As entidades e operações reais são ~4 FDs e ~9 EPs. O repositório é válido para
testar padrões arquiteturais (CQRS, Clean Arch), não para benchmarking de tamanho funcional.

---

## Linguagens Suportadas

| Linguagem  | Framework típico  | Parser                 | Versão | Observação                               |
| ---------- | ----------------- | ---------------------- | ------ | ---------------------------------------- |
| Python     | Django, FastAPI   | tree-sitter-python     | 0.21.0 | Suporte a decorators e herança           |
| Java       | Spring Boot       | tree-sitter-java       | 0.21.0 | Suporte a annotations e generics         |
| JavaScript | React, Node.js    | tree-sitter-javascript | 0.21.4 | Inclui detecção de rotas Express         |
| TypeScript | NestJS, Angular   | tree-sitter-typescript | 0.21.2 | Suporte a decorators e export_statement  |
| TSX        | React TypeScript  | tree-sitter-typescript | 0.21.2 | Parser tsx separado para arquivos `.tsx` |
| C#         | ASP.NET Core      | tree-sitter-c-sharp    | 0.21.3 | Suporte a atributos e VSA                |
| Kotlin     | Ktor, Spring Boot | tree-sitter-kotlin     | 1.1.0  | ⚠️ Funcional, calibração em andamento   |

> **Nota:** a adição de Kotlin exigiu upgrade do tree-sitter de `0.22.3` para `0.25.2`.
> Os demais parsers não sofreram regressão com o upgrade.

---

## Status do Desenvolvimento

| Etapa   | Descrição                                              | Status          |
| ------- | ------------------------------------------------------ | --------------- |
| Etapa 1 | Repositórios públicos e base de validação RealWorld    | ✅ Concluída    |
| Etapa 2 | Extrator tree-sitter (Python, Java, JS, TS, C#)        | ✅ Concluída    |
| Etapa 2.5 | Enriquecimento: `sfp_hint`, `file_role`, decorators  | ✅ Concluída    |
| Etapa 3 | Integração Azure OpenAI — `sfp_analyzer.py`            | ✅ Concluída    |
| Etapa 3.1 | Revalidação metodológica — fronteira do sistema      | ✅ Concluída    |
| Etapa 3.2 | Redução de ruído e revalidação completa (v4.1)       | ✅ Concluída    |
| Etapa 4 | Suporte a Kotlin via `tree-sitter-kotlin`              | ✅ Concluída    |
| Etapa 5 | Repositórios internos via Azure DevOps                 | ⏳ Pendente     |
| Etapa 6 | Análise histórica por commits + dashboard executivo    | ⏳ Pendente     |

> Para o histórico detalhado de mudanças entre versões (v2.5 → v3.1 → v4.0 → v4.1),
> consulte o [CHANGELOG.md](./CHANGELOG.md).

### Roadmap — Etapas Futuras

**Etapa 5 — Repositórios internos:**
- Integração com Azure DevOps para análise automática de repositórios da empresa
- Pipeline de coleta sem acesso manual ao código

**Etapa 6 — Análise histórica e dashboard:**
- Extração por commits para medir evolução funcional ao longo do tempo
- Dashboard executivo com séries históricas de SFP por projeto
- Benchmarking de produtividade entre projetos (SFP por sprint)

**Backlog Kotlin:**
- Refinar filtros de tabelas de junção Exposed sem atributos próprios
- Suporte a routing Ktor aninhado (`route("/prefix") { get { ... } }`)
- Validar com projetos Kotlin Spring Boot (annotations similares ao Java)

---

## Estrutura do Projeto

```
sfp-poc/
├── README.md                    ← documentação principal
├── CHANGELOG.md                 ← histórico de versões
├── requirements.txt             ← dependências Python
├── repos/                       ← repositórios analisados (git clone aqui)
├── src/
│   ├── extractor/
│   │   ├── extractor.py         ← pipeline principal: tree-sitter + sfp_hint
│   │   ├── diagnostico_repos.py ← diagnóstico detalhado por repositório
│   │   └── validacao.py         ← validação rápida dos resultados
│   └── llm/
│       └── sfp_analyzer.py      ← integração Azure OpenAI
└── output/                      ← JSONs com resultados por repositório
```

---

## Linguagens Fora do Escopo

### Sem relevância para contagem SFP

Linguagens que não contêm lógica funcional mensurável — não possuem entidades de domínio
nem operações de negócio.

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

### Baixa prioridade para a PoC

| Linguagem         | Motivo                                                           |
| ----------------- | ---------------------------------------------------------------- |
| Swift             | Pacote `tree-sitter-swift` em estágio inicial — instável         |
| Dart              | Sem pacote disponível no PyPI                                    |
| C / C++           | Raramente usados em aplicações web/mobile corporativas           |
| Java Server Pages | Tecnologia legada — baixa representatividade nos projetos atuais |
| VBScript          | Tecnologia legada                                                |
| Prolog            | Nicho — sem representatividade nos projetos da empresa           |
