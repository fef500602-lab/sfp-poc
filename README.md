# SFP PoC — Simple Function Points via tree-sitter

Prova de conceito para medir evolução funcional de bases de código
usando a metodologia **SFP (Simple Function Points - ISO/IFPUG)**.

---

## Objetivo

Extrair automaticamente de repositórios de código dois elementos SFP:

- **Funções de Dados** → classes e modelos de dados
- **Processos Elementares** → endpoints e métodos de operação

O resultado alimenta métricas executivas de produtividade e subsidia
estimativas de novos projetos.

---

## Metodologia SFP

O **Simple Function Points (SFP)** é um padrão ISO mantido pelo IFPUG
que simplifica a contagem de pontos de função em dois elementos:

| Elemento SFP          | O que representa             | Como identificamos  |
| --------------------- | ---------------------------- | ------------------- |
| Funções de Dados      | Entidades do domínio         | Classes de modelo   |
| Processos Elementares | Operações de leitura/escrita | Endpoints e métodos |

### Pipeline de processamento

```
Código fonte (local)
       ↓
[tree-sitter] → extrai nomes de classes e métodos
       ↓
Arquivo JSON com lista de elementos
       ↓
[LLM Azure OpenAI] → sanitiza, classifica e conta
       ↓
Contagem SFP final
```

> O código fonte **nunca circula pela LLM** — apenas nomes de
> arquivos e métodos, garantindo segurança e baixo custo.

---

## Status do Desenvolvimento

### ✅ Etapa 1 — Repositórios públicos (Concluída)

- Definida estratégia de uso de repositórios públicos **RealWorld**
  como base de validação — mesma aplicação implementada em múltiplas
  linguagens, permitindo comparação direta entre tecnologias
- Criada estrutura de pastas do projeto
- Repositório público criado no GitHub

### ✅ Etapa 2 — Extrator tree-sitter (Concluída)

- Implementado `extractor.py` com suporte a 5 linguagens
- Resolvidos conflitos de compatibilidade entre versões do tree-sitter:
  versão `0.25.x` quebrou a API — fixado em `0.22.3` (estável)
- Adicionado filtro de arquivos de teste e configuração para
  reduzir ruído na extração (~30% de redução em Java)
- Implementado `validacao.py` para inspeção e classificação
  preliminar dos resultados antes do envio à LLM
- Resultados salvos em JSON por repositório e consolidado

### 🔄 Etapa 3 — Integração com LLM (Próxima)

- Conectar à Azure OpenAI
- Enviar listas de classes e métodos para sanitização
- Gerar contagem SFP final por repositório

### ⏳ Etapas Futuras

- Suporte a repositórios internos via Azure DevOps
- Análise histórica por commits (evolução ao longo do tempo)
- Dashboard executivo de métricas

---

## Linguagens Suportadas

| Linguagem  | Framework típico | Parser                 | Versão |
| ---------- | ---------------- | ---------------------- | ------ |
| Python     | Django, FastAPI  | tree-sitter-python     | 0.21.0 |
| Java       | Spring Boot      | tree-sitter-java       | 0.21.0 |
| JavaScript | React, Node.js   | tree-sitter-javascript | 0.21.4 |
| TypeScript | Node.js, Angular | tree-sitter-typescript | 0.21.2 |
| C#         | ASP.NET Core     | tree-sitter-c-sharp    | 0.21.3 |

---

## Linguagens Fora do Escopo da PoC

### ❌ Sem relevância para contagem SFP

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

| Linguagem | Motivo técnico                                                                                 |
| --------- | ---------------------------------------------------------------------------------------------- |
| Kotlin    | Pacote `tree-sitter-kotlin` requer tree-sitter >= 0.23 — incompatível com versão estável atual |
| Swift     | Pacote `tree-sitter-swift 0.0.1` em estágio inicial — instável para uso em produção            |
| Dart      | Sem pacote disponível no PyPI                                                                  |

> Kotlin, Swift e Dart serão reavaliados quando a versão
> do tree-sitter for atualizada em etapas futuras do projeto.

### 🔶 Baixa prioridade para a PoC

| Linguagem         | Motivo                                                           |
| ----------------- | ---------------------------------------------------------------- |
| C / C++           | Raramente usados em aplicações web/mobile corporativas           |
| Java Server Pages | Tecnologia legada — baixa representatividade nos projetos atuais |
| VBScript          | Tecnologia legada                                                |
| Prolog            | Nicho — sem representatividade nos projetos da empresa           |

---

## Resultados da Extração (com filtro de testes aplicado)

| Repositório              | Linguagem  | Arquivos | Funções de Dados | Processos Elementares |
| ------------------------ | ---------- | -------- | ---------------- | --------------------- |
| realworld-java-spring    | Java       | 93       | 79               | 217                   |
| realworld-csharp-dotnet  | C#         | 64       | 124              | 85                    |
| realworld-python-django  | Python     | 44       | 49               | 66                    |
| realworld-react-js       | JavaScript | 38       | 13               | 97                    |
| realworld-nodejs-express | TypeScript | 31       | 11               | 22                    |

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
git clone https://github.com/gothinkster/django-realworld-example-app repos/realworld-python-django
git clone https://github.com/gothinkster/node-express-realworld-example-app repos/realworld-nodejs-express
git clone https://github.com/gothinkster/react-redux-realworld-example-app repos/realworld-react-js
git clone https://github.com/gothinkster/spring-boot-realworld-example-app repos/realworld-java-spring
git clone https://github.com/gothinkster/aspnetcore-realworld-example-app repos/realworld-csharp-dotnet
```

---

## Como Executar

**Extração via tree-sitter**

```bash
python src/extractor/extractor.py
```

**Validação dos resultados**

```bash
python src/extractor/validacao.py
```

**Resultados gerados em:**

```
output/
├── realworld-python-django.json
├── realworld-nodejs-express.json
├── realworld-react-js.json
├── realworld-java-spring.json
├── realworld-csharp-dotnet.json
└── consolidated_report.json
```

---

## Estrutura do Projeto

```
sfp-poc/
├── README.md                  ← documentação completa
├── requirements.txt           ← dependências Python
├── repos/                     ← repositórios analisados
├── src/
│   └── extractor/
│       ├── extractor.py       ← pipeline tree-sitter
│       ├── validacao.py       ← validação dos resultados
│       └── diagnostico.py     ← ferramenta de diagnóstico AST
└── output/                    ← JSONs com resultados
```
