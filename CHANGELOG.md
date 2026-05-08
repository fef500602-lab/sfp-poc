# Changelog — SFP PoC

Histórico de mudanças técnicas entre versões do extrator e do analisador SFP.
Versões seguem o esquema `vX.Y` referente à iteração do pipeline, não do projeto geral.

---

## [v4.1] — Etapa 3.2: Redução de ruído e revalidação completa

### Java Spring — ruído nos EPs auto-classificados

O projeto implementa REST e GraphQL DGS. Field resolvers `@DgsData` são internos
ao GraphQL (não são operações de fronteira) — apenas `@DgsQuery` e `@DgsMutation` o são.

- `@DgsData` movido de `ELEMENTARY_PROCESS_DECORATORS` para `IGNORE_DECORATORS`
- `@ExceptionHandler` adicionado a `IGNORE_DECORATORS`
- `IGNORE_METHOD_NAME_SUFFIXES` criado para filtrar response builders por sufixo de nome
  (`articleResponse`, `userResponse`, etc.)
- Controller methods Java sem decorator HTTP redirecionados para `llm`

### C# .NET — dupla contagem em Vertical Slice Architecture

Em VSA, cada feature contém um controller method (ex: `ArticlesController.Get`) e um
handler CQRS (ex: `Details.Handle`) representando a *mesma* operação. Ambos eram
auto-classificados como EP.

- Métodos em `feature/` sem decorator HTTP explícito passam para `llm`
- Instrução específica de VSA adicionada ao system prompt do `sfp_analyzer`
- LLM deduplica os pares, mantendo ~17 EPs (equivalente às 17 rotas REST)

### Python Django — classes abstratas e utilitárias como FD

- `TimestampedModel`, `AbstractModel`, `BaseModel` adicionados ao `IGNORE_CLASS_NAME_SUFFIXES["python"]`
- `mixin` e `baseusermanager` adicionados ao `IGNORE_BASE_CLASSES["python"]`
- Métodos DRF (`to_internal_value`, `to_representation`, `get_queryset`) e signals
  (`receiver`) adicionados ao filtro de métodos padrão

### TypeScript / Node.js Express — modelos invisíveis e métodos de framework

O projeto usa TypeScript `interface` (não classes) para definir entidades em arquivos
`*.model.ts` dentro de `routes/`. Essa pasta recebia `file_role: "controller"`,
tornando as interfaces invisíveis ao extrator.

- Padrão `.model` adicionado ao `HIGH_PRIORITY_ROLES` com prioridade sobre `routes/`
- DTOs filtrados por sufixo: `input`, `registered`, `response`, `request`
- `error` adicionado ao `IGNORE_BASE_CLASSES` (TypeScript/JS) para classes de exceção
- Métodos de interface de framework NestJS (`canActivate`, `intercept`, `catch`,
  `bootstrap`) adicionados ao filtro

### Impacto da revalidação

| Repositório              | SFP v3.1 | SFP v4.0 | SFP v4.1 | Variação |
| ------------------------ | -------- | -------- | -------- | -------- |
| realworld-java-spring    | 96       | 67       | 34       | -65%     |
| realworld-csharp-dotnet  | 45       | 45       | 24       | -47%     |
| realworld-python-django  | 29       | 28       | 22       | -24%     |
| realworld-nodejs-express | 21       | 21       | 26       | +24% *   |

> \* Node.js aumentou porque passamos a detectar as interfaces TypeScript `*.model.ts`,
> anteriormente invisíveis. A contagem ficou mais completa, não inflada.

---

## [v4.0] — Etapa 3.1: Correção metodológica — fronteira do sistema

### Defeito identificado

O extrator contava métodos em **todas as camadas arquiteturais** como EPs. A metodologia
SFP define EP exclusivamente na **fronteira do sistema** com o usuário. Em Spring Boot MVC,
`ArticleController.getArticle()` e `ArticleService.getArticle()` representam a mesma
operação de negócio — ambos eram contados, gerando dupla contagem sistemática.

### Correções implementadas

- `classify_hint` separado para `controller` e `service`: métodos de controller continuam
  como `elementary_process`; métodos de service passam para `llm` para a LLM decidir
  se são fronteira real ou implementação interna
- Sufixos `repository`, `service` e `controller` adicionados a
  `IGNORE_CLASS_NAME_SUFFIXES` (Java e C#)
- System prompt do `sfp_analyzer` atualizado com regra de fronteira explícita e
  instrução de deduplicação controller vs. service

---

## [v3.1] — Etapa 2.5: Enriquecimento do extrator

### Contexto estrutural adicionado a cada elemento

- `base_classes` — classes pai / interfaces implementadas
- `decorators` — annotations e decorators aplicados
- `file_role` — papel inferido do arquivo pelo caminho
- `sfp_hint` — pré-classificação determinística

### Correções por linguagem

**Java Spring**
- Adicionados decorators GraphQL DGS: `@DgsQuery`, `@DgsMutation`, `@DgsData`, `@DgsSubscription`
- Filtro de `@Override` — implementações de interface não são EPs independentes
- Sufixos de DTOs e infraestrutura ignorados: `Param`, `Response`, `Serializer`,
  `Cursor`, `Validator`, `Dto`, `Resource`, `Envelope`, etc.
- Inferência de `file_role: model` para pacotes `core/` (padrão Spring JDBC sem `@Entity`)
- Filtro de construtores Java (detectados como `method_declaration` sem tipo de retorno)

**TypeScript / NestJS**
- Corrigido bug crítico em `extract_decorators_ts`: parava ao encontrar `export` antes
  do decorator pai em `export_statement → [decorator, "export", class]`. Solução:
  subir ao `grandparent` quando o `parent` é `export_statement`
- Lifecycle methods React (`render`, `componentDidMount`, etc.) adicionados ao filtro

**React / Frontend**
- Adicionado `file_role: ui` para pastas `components/`, `pages/`, `screens/`
- Resultado correto: 0 FD / 0 EP para repositórios frontend

**Express / Node.js**
- Detecção de rotas via `call_expression` (`router.get(path, handler)`) — padrão não
  capturado pelo extrator de declarações de método
- Nome do EP derivado do método HTTP + path: `GET /articles/:slug` → `getArticlesSlug`

**C# .NET**
- Filtro de construtores C# (`constructor_declaration`)
- Artefato `Task<T>` corrigido: parser C# lia o tipo de retorno genérico como nome de método
- `ServicesExtensions.cs` corretamente classificados como `file_role: config`; corrigida
  prioridade onde `"service"` (substring de `ServicesExtensions`) prevalecia sobre `"config"`
- Sufixos CQRS/MediatR ignorados: `Command`, `Query`, `Handler`, `Validator`,
  `Behaviour`, `Envelope`, `Dto`, `Vm`, etc.
- Suporte a Vertical Slice Architecture: arquivos em `Features/` têm `file_role: feature`

**Infraestrutura geral**
- `infer_file_role` refatorado com lista `HIGH_PRIORITY_ROLES` verificada antes do loop
  geral; garante que `test`, `migration`, `config`, `infrastructure`, `ui` e `feature`
  têm precedência sobre `model`, `service` e `controller`

---

## [v2.5] — Etapa 2: Extrator tree-sitter inicial

- Implementado `extractor.py` com suporte a Python, Java, JavaScript, TypeScript/TSX e C#
- tree-sitter fixado em `0.22.3` (versão `0.25.x` quebrou a API)
- Adicionado filtro de pastas de teste, configuração e gerados (`IGNORE_DIRS`)
  — redução de ~30% de ruído em Java
- Implementados `validacao.py` e `diagnostico_repos.py` para inspeção dos resultados
