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
git clone https://github.com/gothinkster/spring-boot-realworld-example-app      repos/realworld-java-spring
git clone https://github.com/gothinkster/aspnetcore-realworld-example-app        repos/realworld-csharp-dotnet
git clone https://github.com/gothinkster/django-realworld-example-app            repos/realworld-python-django
git clone https://github.com/gothinkster/node-express-realworld-example-app     repos/realworld-nodejs-express
git clone https://github.com/gothinkster/realworld-kotlin-ktor                  repos/realworld-kotlin-ktor
```

### Execução

```bash
# Extração via tree-sitter (gera JSONs em output/)
python src/extractor/extractor.py

# Diagnóstico detalhado por repositório
python src/extractor/diagnostico_repos.py

# Análise SFP via Azure OpenAI (classifica casos ambíguos)
python src/llm/sfp_analyzer.py
```

Resultados gerados em `output/`:

```
output/
├── realworld-python-django.json       ← extração bruta por repo
├── realworld-nodejs-express.json
├── realworld-java-spring.json
├── realworld-csharp-dotnet.json
├── realworld-kotlin-ktor.json
├── consolidated_report.json
└── sfp/
    ├── realworld-python-django.json   ← resultado final com classificação LLM
    ├── realworld-java-spring.json
    ├── ...
    └── sfp_consolidated.json
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
[classify_hint] → pré-classifica cada elemento deterministicamente
       | hint_reason: registra qual regra disparou (auditoria completa)
       ↓
Arquivo JSON com elementos + contexto estrutural (sfp_hint, file_role, decorators)
       ↓
[LLM Azure OpenAI] → classifica apenas os casos ambíguos (sfp_hint: llm)
       | llm_reason: justificativa do modelo por elemento
       ↓
[post-processor] → remove duplicatas REST + GraphQL
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
reduzindo custo e aumentando consistência. Cada decisão é registrada no campo
`hint_reason`, permitindo rastreabilidade completa de qualquer elemento.

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
10. `file_role == "model"` + campos indicam join table → **llm** (v4.3)
11. `file_role == "model"` → **data_function**
12. `file_role` em (`controller`, `service`) → **elementary_process**
13. `file_role` em (`serializer`, `repository`) → **ignore**
14. Caso nenhuma regra se aplique → **llm**

> Para decisões de arquitetura, limitações conhecidas e trade-offs,
> consulte [DECISIONS.md](./DECISIONS.md).

### Papel do arquivo (`file_role`)

| Role             | Patterns detectados                               | Comportamento SFP                                   |
| ---------------- | ------------------------------------------------- | --------------------------------------------------- |
| `test`           | test, tests, spec, mock, stub, fixture            | Tudo ignorado                                       |
| `migration`      | migration, migrations                             | Tudo ignorado                                       |
| `config`         | config, settings, startup, middleware, extensions | Tudo ignorado                                       |
| `infrastructure` | infrastructure                                    | Tudo ignorado                                       |
| `ui`             | component, page, screen, layout, widget           | Tudo ignorado                                       |
| `graphql`        | graphql, datafetcher, datafetchers                | Métodos → LLM (verifica dupla contagem REST+GraphQL) |
| `feature`        | feature, features                                 | Classes ignoradas, métodos = EP                     |
| `model`          | model, entity, domain, core, aggregate            | Classes = FD (com detecção de join tables)          |
| `serializer`     | serial, dto, schema, mapper                       | Tudo ignorado                                       |
| `repository`     | repositor, repo, dao                              | Tudo ignorado                                       |
| `controller`     | view, controller, api, endpoint, route            | Métodos = EP                                        |
| `service`        | service, usecase, command, query, handler         | Métodos → LLM (fronteira do sistema)                |

---

## Conjunto de Validação

### Repositórios RealWorld (conjunto principal)

Mesma especificação de aplicação (Conduit) implementada em múltiplas linguagens —
permite comparação direta entre tecnologias e validação cruzada dos resultados SFP.

| Repositório              | Linguagem  | Arquivos | Arquitetura         |
| ------------------------ | ---------- | -------- | ------------------- |
| realworld-java-spring    | Java       | 93       | Spring Boot MVC     |
| realworld-csharp-dotnet  | C#         | 64       | ASP.NET Minimal API |
| realworld-python-django  | Python     | 34       | Django REST         |
| realworld-nodejs-express | TypeScript | 28       | Express.js          |
| realworld-kotlin-ktor    | Kotlin     | —        | Ktor                |

### Repositórios Complementares

| Repositório       | Linguagem  | Arquivos | Arquitetura                       |
| ----------------- | ---------- | -------- | --------------------------------- |
| csharp-clean-arch | C#         | 130      | Clean Architecture + CQRS         |
| nestjs-framework  | TypeScript | 327      | NestJS (repositório do framework) |

### Casos de Borda

| Repositório        | Motivo da exclusão do conjunto principal |
| ------------------ | ---------------------------------------- |
| realworld-react-js | **Frontend puro** — 0 FD / 0 EP. Mantido para validar o filtro `file_role: ui`. |
| edge-express-lib   | **Repositório de framework**, não de aplicação. |
| edge-only-markdown | **Sem código-fonte** — valida que o extrator não quebra com repositórios sem linguagens suportadas. |

---

## Resultados (v4.3+)

### Conjunto RealWorld (comparável)

| Repositório              | Linguagem  | FD | EP | Total SFP |
| ------------------------ | ---------- | -- | -- | --------- |
| realworld-python-django  | Python     | 4  | 18 | **22**    |
| realworld-nodejs-express | TypeScript | 6  | 19 | **25**    |
| realworld-java-spring    | Java       | 4  | 19 | **23**    |
| realworld-csharp-dotnet  | C#         | 7  | 17 | **24**    |
| realworld-kotlin-ktor    | Kotlin     | 10 | 40 | **50** ⚠️ |

> **Kotlin/Ktor é outlier** — EP=40 vs 17–19 das outras implementações.
> Investigação em andamento (SFP-09) — ver ADR-008 em [DECISIONS.md](./DECISIONS.md).

A variação de ≤ 10% entre Python, Node.js, Java e C# (22–25 SFP) confirma
que a metodologia é independente de linguagem para esse conjunto.

### Repositórios complementares

| Repositório       | FD | EP | Total SFP | Observação                                 |
| ----------------- | -- | -- | --------- | ------------------------------------------ |
| csharp-clean-arch | 15 | 24 | **39**    | Aplicação diferente (Todo + Weather)       |
| nestjs-framework  | 21 | 84 | **105**   | ~10 mini-aplicações de exemplo empacotadas |

---

## Linguagens Suportadas

| Linguagem  | Framework típico  | Parser                 | Versão | Status                              |
| ---------- | ----------------- | ---------------------- | ------ | ----------------------------------- |
| Python     | Django, FastAPI   | tree-sitter-python     | 0.21.0 | ✅ Estável                          |
| Java       | Spring Boot       | tree-sitter-java       | 0.21.0 | ✅ Estável                          |
| JavaScript | React, Node.js    | tree-sitter-javascript | 0.21.4 | ✅ Estável                          |
| TypeScript | NestJS, Angular   | tree-sitter-typescript | 0.21.2 | ✅ Estável                          |
| TSX        | React TypeScript  | tree-sitter-typescript | 0.21.2 | ✅ Estável                          |
| C#         | ASP.NET Core      | tree-sitter-c-sharp    | 0.21.3 | ✅ Estável                          |
| Kotlin     | Ktor, Spring Boot | tree-sitter-kotlin     | 1.1.0  | ✅ Suportado — outlier EP em estudo |

> A adição de Kotlin exigiu upgrade do tree-sitter de `0.22.3` para `0.25.2`.

---

## Status do Desenvolvimento

| Etapa     | Descrição                                                       | Status       |
| --------- | --------------------------------------------------------------- | ------------ |
| Etapa 1   | Repositórios públicos e base de validação RealWorld             | ✅ Concluída |
| Etapa 2   | Extrator tree-sitter — Python, Java, JS, TS, C#                 | ✅ Concluída |
| Etapa 2.5 | Enriquecimento: `sfp_hint`, `file_role`, decorators             | ✅ Concluída |
| Etapa 3   | Integração Azure OpenAI — `sfp_analyzer.py`                     | ✅ Concluída |
| Etapa 3.1 | Revalidação metodológica — fronteira do sistema                 | ✅ Concluída |
| Etapa 3.2 | Redução de ruído residual — v4.1                                | ✅ Concluída |
| Etapa 4   | Suporte a Kotlin + upgrade tree-sitter 0.25.2                   | ✅ Concluída |
| Etapa 4.1 | Arquitetura híbrida: `hint_reason`, dedup GraphQL, INFRA_ROUTES | ✅ Concluída |
| Etapa 4.2 | Correção gap join tables no `classify_hint` step 9 — v4.3      | ✅ Concluída |
| Etapa 5   | Repositórios internos via Azure DevOps                          | ⏳ Pendente  |
| Etapa 6   | Análise histórica por commits + dashboard executivo             | ⏳ Pendente  |

> Para o histórico detalhado de mudanças entre versões,
> consulte o [CHANGELOG.md](./CHANGELOG.md).

---

## Estrutura do Projeto

```
sfp-poc/
├── README.md                    ← documentação principal (este arquivo)
├── CHANGELOG.md                 ← histórico de versões por sprint
├── DECISIONS.md                 ← ADRs: decisões de arquitetura e limitações conhecidas
├── requirements.txt             ← dependências Python
├── repos/                       ← repositórios analisados (git clone aqui)
├── src/
│   ├── extractor/
│   │   ├── extractor.py         ← pipeline principal: tree-sitter + sfp_hint
│   │   ├── diagnostico_repos.py ← diagnóstico detalhado por repositório
│   │   └── validacao.py         ← validação rápida dos resultados
│   └── llm/
│       └── sfp_analyzer.py      ← integração Azure OpenAI + geração de relatório
└── output/
    ├── <repo>.json              ← extração bruta por repositório
    ├── consolidated_report.json
    └── sfp/
        ├── <repo>.json          ← resultado final com classificação LLM
        └── sfp_consolidated.json
```

---

## Linguagens Fora do Escopo

### Sem relevância para contagem SFP

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

### Baixa prioridade / suporte instável

| Linguagem         | Motivo                                                           |
| ----------------- | ---------------------------------------------------------------- |
| Swift             | Pacote `tree-sitter-swift` em estágio inicial — instável         |
| Dart              | Sem pacote disponível no PyPI                                    |
| C / C++           | Raramente usados em aplicações web/mobile corporativas           |
| Java Server Pages | Tecnologia legada — baixa representatividade nos projetos atuais |
| VBScript          | Tecnologia legada                                                |
| Prolog            | Nicho — sem representatividade nos projetos da empresa           |
