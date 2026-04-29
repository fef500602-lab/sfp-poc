import os
import json
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_java as tsjava
import tree_sitter_c_sharp as tscsharp
import tree_sitter_typescript as tstypescript

# =============================================================================
# SFP Extractor v4.0 — Correção metodológica: fronteira do sistema
#
# Correção crítica em relação às versões anteriores:
#
#   Versões anteriores contavam métodos de TODAS as camadas arquiteturais
#   (controller + service + repository) como Processos Elementares,
#   inflando a contagem e quebrando a comparabilidade entre linguagens.
#
#   A metodologia SFP define EP como operação na FRONTEIRA DO SISTEMA —
#   não em cada camada interna de implementação.
#
#   Mudanças v4.0:
#   - Métodos em file_role "service" → sfp_hint "llm" (não mais auto-EP)
#   - Sufixos "repository" e "service" adicionados a IGNORE_CLASS_NAME_SUFFIXES
#     para Java e C# (repositórios e services não são Funções de Dados)
#   - system prompt do sfp_analyzer atualizado com regra de fronteira explícita
#
# Além de extrair nomes, captura:
#   - base_classes : herança da classe
#   - decorators   : anotações/decorators aplicados
#   - file_role    : papel inferido pelo caminho do arquivo
#   - sfp_hint     : pré-classificação determinística
#
# Compatibilidade: tree-sitter==0.22.3
# =============================================================================


# ─────────────────────────────────────────
# 1. Configuração dos parsers
# ─────────────────────────────────────────
LANGUAGES = {
    "csharp":     {"language": Language(tscsharp.language()),                "extensions": [".cs"]},
    "python":     {"language": Language(tspython.language()),                "extensions": [".py"]},
    "javascript": {"language": Language(tsjavascript.language()),            "extensions": [".js", ".jsx"]},
    "java":       {"language": Language(tsjava.language()),                  "extensions": [".java"]},
    "typescript": {"language": Language(tstypescript.language_typescript()), "extensions": [".ts"]},
    "tsx":        {"language": Language(tstypescript.language_tsx()),        "extensions": [".tsx"]},
}


# ─────────────────────────────────────────
# 2. Regras de pré-classificação SFP
#
# Baseadas em padrões estruturais determinísticos por linguagem.
# Estas regras eliminam a necessidade da LLM classificar
# elementos com papel arquitetural óbvio.
# ─────────────────────────────────────────

# ─────────────────────────────────────────
# Filtros por sufixo de nome de CLASSE
#
# Aplicados apenas a classes (is_method=False).
# Sufixos que indicam com certeza que a classe deve ser IGNORADA para SFP.
# ─────────────────────────────────────────
IGNORE_CLASS_NAME_SUFFIXES = {
    "java": [
        "serializer", "deserializer",   # Jackson / serialização
        "util", "utils", "helper", "helpers",  # utilitários
        "validator", "validation",      # validadores
        "cursor",                       # paginação
        "exception", "error",           # exceções
        "module", "modules",            # módulos Jackson/Spring
        "config", "configuration",      # configuração Spring
        "factory",                      # fábricas
        "converter",                    # conversores
        "interceptor",                  # interceptors
        "aspect",                       # AOP
        "listener",                     # event listeners
        "handler",                      # exception handlers genéricos
        "adapter",                      # adapters de infraestrutura
        # DTOs de transporte — não são entidades de domínio SFP
        "param", "params",
        "request", "requestbody",
        "response", "responsebody",
        "dto",
        "resource",                     # classes de resposta REST (ErrorResource, etc.)
        "envelope",                     # wrappers de resposta (ArticleEnvelope, etc.)
        # DTOs de leitura (read models / projections)
        "data", "datalist",
        "count",                        # contadores/agregados
        "withtoken",                    # wrappers de auth
        # Camadas arquiteturais — não são entidades de domínio SFP
        # (correção v4.0: evita que classes em pacote core/ sejam contadas como FD)
        "repository", "repositoryimpl", # Spring Data / JDBC repositories
        "service", "serviceimpl",       # camada de serviço não é FD
        "controller", "controllerimpl", # controllers são EPs, não FDs
    ],
    "python":     [],
    "csharp":     [
        "exception", "middleware", "extensions",
        "behaviour", "behavior",        # MediatR pipeline behaviors
        "handler",                      # CQRS handlers
        "profile",                      # AutoMapper profiles
        # DTOs e wrappers — não são entidades de domínio SFP
        "envelope",                     # wrappers de resposta (ArticleEnvelope, etc.)
        "dto",                          # Data Transfer Objects
        "vm",                           # ViewModels
        "validator", "validation",      # FluentValidation validators
        # CQRS — classes de request (não são domínio, são operações)
        "command",                      # MediatR commands
        "query",                        # MediatR queries
        # Infraestrutura de segurança/acesso
        "accessor",                     # CurrentUserAccessor, etc.
        "generator",                    # JwtTokenGenerator, etc.
        "hasher",                       # PasswordHasher, etc.
        "filter",                       # ActionFilter, ExceptionFilter, etc.
        "initialiser", "initializer",   # DbInitialiser, etc.
        "transformer",                  # OpenAPI transformers
        "constants",                    # classes de constantes
        # Camadas arquiteturais — não são entidades de domínio SFP
        "repository", "repositoryimpl", # repositórios não são FD
        "service", "serviceimpl",       # camada de serviço não é FD
        "controller", "controllerimpl", # controllers são EPs, não FDs
    ],
    "typescript": [],
    "javascript": [],
}

# Métodos padrão da linguagem que nunca são Processos Elementares SFP
IGNORE_METHOD_NAMES = {
    "java": {
        "tostring", "hashcode", "equals", "compareto", "clone",
        "main",           # entry point da JVM
        "getclass",       # reflexão
        "notify", "notifyall", "wait",  # sincronização Object
    },
    "python":     set(),
    "csharp":     {
        "tostring", "gethashcode", "equals", "gettype",
        "task",           # artefato: parser C# lê Task<T> como nome de método
        "onmodelcreating", "onconfiguring",  # EF Core overrides
        "configureservices", "configure",    # Startup overrides
    },
    # Lifecycle methods React/JS — não são lógica de negócio SFP
    "typescript": {
        "render", "constructor",
        "componentdidmount", "componentdidupdate",
        "componentwillmount", "componentwillunmount",
        "componentwillreceiveprops", "componentwillupdate",
        "shouldcomponentupdate", "getsnapshotbeforeupdate",
        "getderivedstatefromprops", "getderivedstatefromerror",
        "componentdidcatch",
    },
    "javascript": {
        "render", "constructor",
        "componentdidmount", "componentdidupdate",
        "componentwillmount", "componentwillunmount",
        "componentwillreceiveprops", "componentwillupdate",
        "shouldcomponentupdate", "getsnapshotbeforeupdate",
        "getderivedstatefromprops", "getderivedstatefromerror",
        "componentdidcatch",
    },
}

# Herança que indica Data Function com certeza
DATA_FUNCTION_BASE_CLASSES = {
    "python": [
        "model", "models.model", "abstractmodel",
        "models.abstractmodel", "timestampedmodel",
    ],
    "java": [],  # Java usa annotations — ver DATA_FUNCTION_DECORATORS
    "csharp": [
        "entity", "baseentity", "auditable",
    ],
    "typescript": [],
    "javascript": [],
}

# Decorators/annotations que indicam Data Function com certeza
DATA_FUNCTION_DECORATORS = {
    "python":     [],
    "java":       [
        # Marcadores JPA/MongoDB de entidade de domínio — certeza de Data Function
        "entity", "table", "document", "mappedsuperclass", "embeddable",
        # Nota: @Data, @Getter, @Setter, @Value, @Builder são Lombok —
        # indicam apenas geração de código, não que a classe é entidade de domínio.
        # Classes com apenas Lombok sem @Entity/@Table são DTOs ou helpers → LLM decide.
    ],
    "csharp":     [],
    "typescript": ["entity"],  # TypeORM
    "javascript": [],
}

# Decorators/annotations que indicam Elementary Process com certeza
ELEMENTARY_PROCESS_DECORATORS = {
    "python":     [
        "api_view", "action",
        "get", "post", "put", "delete", "patch",  # FastAPI/Flask
    ],
    "java":       [
        "getmapping", "postmapping", "putmapping",
        "deletemapping", "patchmapping", "requestmapping",
        "dgsquery", "dgsmutation", "dgssubscription",  # Netflix DGS (GraphQL)
        "dgsdata",                                      # Netflix DGS: data loaders / field resolvers
        "graphqlquery", "graphqlmutation",              # Spring GraphQL
        "queryhandler", "commandhandler",               # CQRS
    ],
    "csharp":     ["httpget", "httppost", "httpput", "httpdelete", "httppatch"],
    "typescript": ["get", "post", "put", "delete", "patch"],  # NestJS
    "javascript": [],
}

# Herança/padrões que indicam elementos a IGNORAR
IGNORE_BASE_CLASSES = {
    "python": [
        "serializer", "modelserializer", "hyperlinkedmodelserializer",
        "listserializer", "baseserializer",
        "migration",
        "appconfig",
        "testcase", "simpletest", "unittest",
        "exception", "error",
        "permission", "basepermission",
        "authentication", "baseauthentication",
        "filter", "basefilter",
        "pagination", "basepagination",
        "renderer", "baserenderer",
        "throttle", "basethrottle",
    ],
    "java": [
        "runtimeexception", "exception", "error",  # hierarquia de exceções
        "simplemodule", "module",                   # módulos Jackson
        "abstractvalidator", "constraintvalidator", # validadores
    ],
    "csharp": [
        "exception", "middleware",
        "profile",  # AutoMapper
    ],
    "typescript": [],
    "javascript": [],
}

# Decorators que indicam elementos a IGNORAR
IGNORE_DECORATORS = {
    "python":     [],
    "java":       [
        "repository", "mapper", "configuration",
        "component", "bean", "test", "service",
        "springbootapplication", "controller", "restcontroller",
        "controlleradvice", "restcontrolleradvice",
        "override",         # implementação de interface — não é EP independente
    ],
    "csharp":     [],
    "typescript": ["injectable", "module", "guard", "interceptor", "pipe"],
    "javascript": [],
}


# ─────────────────────────────────────────
# 3. Inferência do papel do arquivo pelo caminho
#
# Evita enviar migrations, serializers e testes à LLM.
# ─────────────────────────────────────────
FILE_ROLE_PATTERNS = {
    "model":      ["model", "models", "entity", "entities", "domain",
                   "core",          # Spring Boot: pacote core/ contém entidades de domínio
                   "aggregate",     # DDD: pacote de agregados
                   "valueobject",   # DDD: value objects
                   ],
    "controller": ["view", "views", "controller", "controllers",
                   "api", "endpoint", "endpoints", "route", "routes"],
    "service":    ["service", "services", "usecase", "usecases",
                   "command", "query", "handler"],
    "serializer": ["serial", "dto", "schema", "mapper", "mapping"],
    "repository": ["repositor", "repository", "repo", "dao"],
    "migration":  ["migration", "migrations"],
    "test":       ["test", "tests", "spec", "specs", "mock", "stub",
                   "fixture", "fake"],
    "config":     ["config", "settings", "setup", "bootstrap",
                   "startup", "middleware", "extensions"],  # ServicesExtensions, etc.
    # Frontend UI — componentes visuais não contam para SFP
    "ui":         ["component", "components", "page", "pages",
                   "screen", "screens", "layout", "layouts",
                   "widget", "widgets"],
    # Vertical Slice Architecture (C# / .NET):
    # classes container são ignoradas; métodos são EPs
    "feature":    ["feature", "features"],
    # Infraestrutura técnica — não conta para SFP
    "infrastructure": ["infrastructure"],
}

def infer_file_role(filepath):
    parts = filepath.lower().replace("\\", "/").split("/")
    filename = parts[-1].replace(".py", "").replace(".java", "") \
                        .replace(".cs", "").replace(".ts", "") \
                        .replace(".js", "")

    # Regras de alta prioridade verificadas antes do loop geral
    # (evitam false-matches por substrings, ex: "service" em "servicesextensions")
    HIGH_PRIORITY_ROLES = [
        ("test",           ["test", "tests", "spec", "specs", "mock", "stub", "fixture", "fake"]),
        ("migration",      ["migration", "migrations"]),
        ("config",         ["config", "settings", "setup", "bootstrap", "startup",
                            "middleware", "extensions"]),
        ("infrastructure", ["infrastructure"]),
        ("ui",             ["component", "components", "page", "pages",
                            "screen", "screens", "layout", "layouts", "widget", "widgets"]),
        ("feature",        ["feature", "features"]),
    ]
    for part in parts + [filename]:
        for role, patterns in HIGH_PRIORITY_ROLES:
            if any(p in part for p in patterns):
                return role

    # Verifica pastas e nome do arquivo — papéis de menor prioridade
    for part in parts + [filename]:
        for role, patterns in FILE_ROLE_PATTERNS.items():
            if role in dict(HIGH_PRIORITY_ROLES):
                continue  # já tratado acima
            if any(p in part for p in patterns):
                return role
    return "unknown"


# ─────────────────────────────────────────
# Detecção de rotas Express/Koa/Fastify
#
# Captura padrões do tipo:
#   router.get('/articles', middleware, handler)
#   app.post('/users', handler)
#
# O extractor padrão procura por declarações de método/função,
# mas rotas Express são call_expression — precisam de tratamento especial.
# ─────────────────────────────────────────

HTTP_ROUTE_METHODS = {"get", "post", "put", "delete", "patch"}


def _route_to_name(method: str, path: str) -> str:
    """
    Converte método HTTP + path em nome descritivo no estilo camelCase.
    Ex: ('get',  '/articles/:slug/comments') → 'getArticleSlugComments'
        ('post', '/articles')                → 'createArticles'
        ('delete', '/articles/:slug')        → 'deleteArticleSlug'
    """
    import re
    # Remove query string e barra inicial
    clean = re.sub(r"\?.*$", "", path).lstrip("/")
    # Normaliza parâmetros (:slug → slug)
    clean = re.sub(r":(\w+)", r"\1", clean)
    # Quebra em partes e filtra vazias
    parts = [p for p in clean.split("/") if p]

    prefix = {
        "get":    "get",
        "post":   "create",
        "put":    "update",
        "patch":  "update",
        "delete": "delete",
    }.get(method, method)

    if not parts:
        return prefix.upper()

    # camelCase: primeira parte minúscula, demais capitalizadas
    body = parts[0] + "".join(p.capitalize() for p in parts[1:])
    return f"{prefix}{body[0].upper()}{body[1:]}"


def extract_express_routes(root_node, relative_path, lang_name):
    """
    Percorre a AST de um arquivo JS/TS procurando call_expression
    no padrão router.METHOD(path, ...) ou app.METHOD(path, ...).

    Retorna lista de Elementary Processes prontos para o relatório.
    """
    routes = []
    file_role = infer_file_role(relative_path)

    # Não extrai de arquivos de teste ou configuração
    if file_role in ("migration", "test", "config"):
        return routes

    def walk(node):
        if node.type == "call_expression":
            # Callee deve ser member_expression (router.get, app.post, ...)
            callee = node.children[0] if node.children else None
            if callee and callee.type == "member_expression":
                prop_node = callee.children[-1] if callee.children else None
                if (prop_node
                        and prop_node.type == "property_identifier"
                        and prop_node.text.decode("utf-8", errors="ignore").lower()
                        in HTTP_ROUTE_METHODS):

                    method = prop_node.text.decode("utf-8", errors="ignore").lower()

                    # Primeiro argumento string = path da rota
                    path = ""
                    for child in node.children:
                        if child.type == "arguments":
                            for arg in child.children:
                                if arg.type in ("string", "template_string"):
                                    raw = arg.text.decode("utf-8", errors="ignore")
                                    path = raw.strip("'\"`")
                                    break
                            break

                    # Só registra se tiver path real (evita router.use() genérico)
                    if path and path.startswith("/"):
                        name = _route_to_name(method, path)
                        routes.append({
                            "name":         name,
                            "file":         relative_path,
                            "language":     lang_name,
                            "file_role":    file_role if file_role != "unknown"
                                            else "controller",
                            "base_classes": [],
                            "decorators":   [f"{method.upper()}:{path}"],
                            "sfp_hint":     "elementary_process",
                        })

        for child in node.children:
            walk(child)

    walk(root_node)
    return routes


# ─────────────────────────────────────────
# 4. Pré-classificação SFP (sfp_hint)
#
# Retorna uma das 3 categorias:
#   "data_function"       → certeza de que é SFP
#   "elementary_process"  → certeza de que é SFP
#   "ignore"              → certeza de que NÃO é SFP
#   "llm"                 → ambíguo, precisa da LLM
# ─────────────────────────────────────────
def classify_hint(name, base_classes, decorators, file_role, lang, is_method=False):
    name_lower       = name.lower()
    bases_lower      = [b.lower() for b in base_classes]
    decorators_lower = [d.lower() for d in decorators]

    # 1. Arquivo de migration, teste, config, UI ou infraestrutura → sempre ignorar
    if file_role in ("migration", "test", "config", "ui", "infrastructure"):
        return "ignore"

    # 2. Método padrão da linguagem → sempre ignorar (antes da regra feature,
    #    para filtrar artefatos do parser como "Task" mesmo em arquivos feature/)
    if is_method and name_lower in IGNORE_METHOD_NAMES.get(lang, set()):
        return "ignore"

    # 1b. Vertical Slice (feature/): classes são containers ignoráveis;
    #     métodos são as operações reais → elementary_process
    if file_role == "feature":
        return "elementary_process" if is_method else "ignore"

    # 3. Sufixo de nome de CLASSE indica ignorar (não se aplica a métodos)
    if not is_method:
        for suffix in IGNORE_CLASS_NAME_SUFFIXES.get(lang, []):
            if name_lower.endswith(suffix):
                return "ignore"

    # 4. Base class indica ignorar
    for base in bases_lower:
        for pattern in IGNORE_BASE_CLASSES.get(lang, []):
            if pattern in base:
                return "ignore"

    # 5. Decorator indica ignorar
    for dec in decorators_lower:
        for pattern in IGNORE_DECORATORS.get(lang, []):
            if pattern in dec:
                return "ignore"

    # 6. Base class indica Data Function com certeza
    for base in bases_lower:
        for pattern in DATA_FUNCTION_BASE_CLASSES.get(lang, []):
            if pattern in base:
                return "data_function"

    # 7. Decorator indica Data Function com certeza
    for dec in decorators_lower:
        for pattern in DATA_FUNCTION_DECORATORS.get(lang, []):
            if pattern in dec:
                return "data_function"

    # 8. Decorator indica Elementary Process com certeza
    for dec in decorators_lower:
        for pattern in ELEMENTARY_PROCESS_DECORATORS.get(lang, []):
            if pattern in dec:
                return "elementary_process"

    # 9. Arquivo é model → provável Data Function
    if file_role == "model":
        return "data_function"

    # 10. Arquivo é controller → EP na fronteira do sistema (apenas métodos)
    #     Correção v4.0: service separado de controller.
    #     Controller = fronteira com o usuário → métodos são EPs com certeza.
    #     Classes controller (ex: ArticlesController) não são FDs → ignore.
    if file_role == "controller":
        return "elementary_process" if is_method else "ignore"

    # 10b. Arquivo é service → AMBÍGUO para EP.
    #      Em arquiteturas em camadas (MVC), o service é implementação interna —
    #      o EP já foi contado no controller. Enviar à LLM para decidir se é
    #      fronteira real (ex: Application Service sem controller) ou redundante.
    #      Classes service não são FDs → ignore.
    if file_role == "service":
        return "llm" if is_method else "ignore"

    # 11. Arquivo é serializer/repository → ignorar
    if file_role in ("serializer", "repository"):
        return "ignore"

    # 12. Ambíguo → delega à LLM
    return "llm"


# ─────────────────────────────────────────
# 5. Extração de contexto estrutural por linguagem
#    usando travessia da AST (Opção B)
# ─────────────────────────────────────────

def extract_base_classes_python(class_node):
    """Extrai classes pai de uma class_definition Python."""
    bases = []
    for child in class_node.children:
        if child.type == "argument_list":
            for arg in child.children:
                if arg.type in ("identifier", "attribute"):
                    text = arg.text.decode("utf-8") if arg.text else ""
                    if text:
                        bases.append(text)
    return bases

def extract_decorators_python(node, source_bytes):
    """Extrai decorators aplicados a uma classe ou função Python."""
    decorators = []
    parent = node.parent
    if not parent:
        return decorators
    siblings = parent.children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), -1)
    for i in range(idx - 1, -1, -1):
        sib = siblings[i]
        if sib.type == "decorator":
            text = sib.text.decode("utf-8") if sib.text else ""
            # Extrai apenas o nome do decorator sem @ e argumentos
            name = text.strip("@").split("(")[0].split(".")[-1].strip()
            if name:
                decorators.append(name)
        elif sib.type not in ("comment", "newline"):
            break
    return decorators

def extract_base_classes_java(class_node):
    """Extrai superclass e interfaces de uma class_declaration Java."""
    bases = []
    for child in class_node.children:
        if child.type == "superclass":
            for c in child.children:
                if c.type == "type_identifier":
                    text = c.text.decode("utf-8") if c.text else ""
                    if text:
                        bases.append(text)
        if child.type == "super_interfaces":
            for c in child.named_children:
                if c.type == "type_identifier":
                    text = c.text.decode("utf-8") if c.text else ""
                    if text:
                        bases.append(text)
    return bases

def extract_decorators_java(node):
    """
    Extrai todas as annotations (decorators) de uma classe ou método Java.
    Retorna uma lista de nomes normalizados (minúsculo, sem '@').
    """
    decorators = []
    
    # Em Java, modifiers (incluindo annotations) são filhos do node de declaração
    for child in node.children:
        if child.type == "modifiers":
            for mod in child.children:
                if "annotation" in mod.type:
                    # Pode ser 'annotation' ou 'marker_annotation'
                    name = ""
                    for c in mod.children:
                        if c.type in ("identifier", "scoped_identifier"):
                            name = c.text.decode("utf-8") if c.text else ""
                            break
                    if not name:
                        # Alternativa, procurar nos fields nomeados se houver
                        for c in mod.named_children:
                            if "identifier" in c.type:
                                name = c.text.decode("utf-8") if c.text else ""
                                break
                    if name:
                        # Extrair o nome final caso seja FQN como javax.persistence.Entity
                        decorators.append(name.split('.')[-1].lower())
            break  # Encontrou o bloco modifiers, não precisa continuar

    return decorators


def extract_base_classes_csharp(class_node):
    """Extrai base types de uma class_declaration C#."""
    bases = []
    for child in class_node.children:
        if child.type == "base_list":
            for c in child.named_children:
                text = c.text.decode("utf-8") if c.text else ""
                if text and text not in (",", ":"):
                    bases.append(text)
    return bases

def extract_decorators_csharp(node):
    """Extrai attributes de uma classe ou método C#."""
    decorators = []
    parent = node.parent
    if not parent:
        return decorators
    siblings = parent.children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), -1)
    for i in range(idx - 1, -1, -1):
        sib = siblings[i]
        if sib.type == "attribute_list":
            text = sib.text.decode("utf-8") if sib.text else ""
            name = text.strip("[]").split("(")[0].strip()
            if name:
                decorators.append(name)
        elif sib.type not in ("comment",):
            break
    return decorators

def extract_base_classes_ts(class_node):
    """Extrai herança de uma class_declaration TypeScript."""
    bases = []
    for child in class_node.children:
        if child.type == "class_heritage":
            for c in child.named_children:
                if c.type in ("extends_clause", "implements_clause"):
                    for t in c.named_children:
                        text = t.text.decode("utf-8") if t.text else ""
                        if text:
                            bases.append(text)
    return bases

def extract_decorators_ts(node):
    """
    Extrai decorators de uma classe ou método TypeScript.

    Corrige o caso de classes exportadas:
        export_statement
          [0] decorator   ← @Module({...}) / @Injectable() / @Controller()
          [1] "export"    ← keyword — NÃO deve parar a busca
          [2] class_declaration  ← nó atual

    A versão anterior parava ao encontrar o sibling "export",
    nunca alcançando o decorator acima dele.
    """
    decorators = []
    parent = node.parent
    if not parent:
        return decorators

    # Se o parent for export_statement, subimos um nível:
    # o decorator está no parent do export_statement.
    if parent.type == "export_statement":
        grandparent = parent.parent
        if grandparent:
            gp_siblings = grandparent.children
            gp_idx = next(
                (i for i, c in enumerate(gp_siblings) if c.id == parent.id), -1
            )
            for i in range(gp_idx - 1, -1, -1):
                sib = gp_siblings[i]
                if sib.type == "decorator":
                    text = sib.text.decode("utf-8") if sib.text else ""
                    name = text.strip("@").split("(")[0].strip()
                    if name:
                        decorators.append(name)
                elif sib.type not in ("comment",):
                    break
        # Também busca decorators dentro do export_statement
        # (alguns transpiladores colocam o decorator como filho direto)
        ep_siblings = parent.children
        ep_idx = next(
            (i for i, c in enumerate(ep_siblings) if c.id == node.id), -1
        )
        for i in range(ep_idx - 1, -1, -1):
            sib = ep_siblings[i]
            if sib.type == "decorator":
                text = sib.text.decode("utf-8") if sib.text else ""
                name = text.strip("@").split("(")[0].strip()
                if name:
                    decorators.append(name)
            elif sib.type not in ("comment", "export"):
                break
        return decorators

    # Caso padrão: busca siblings anteriores no mesmo parent
    siblings = parent.children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), -1)
    for i in range(idx - 1, -1, -1):
        sib = siblings[i]
        if sib.type == "decorator":
            text = sib.text.decode("utf-8") if sib.text else ""
            name = text.strip("@").split("(")[0].strip()
            if name:
                decorators.append(name)
        elif sib.type not in ("comment", "export"):
            break
    return decorators


# ─────────────────────────────────────────
# 6. Análise de um arquivo — versão enriquecida
# ─────────────────────────────────────────
def analyze_file(filepath, lang_name, relative_path):
    config   = LANGUAGES[lang_name]
    language = config["language"]
    parser   = Parser()
    parser.language = language

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        source_code = f.read()

    if not source_code.strip():
        return {"data_functions": [], "elementary_processes": []}

    source_bytes = source_code.encode("utf-8")
    tree = parser.parse(source_bytes)
    root = tree.root_node
    file_role = infer_file_role(relative_path)

    data_functions       = []
    elementary_processes = []

    def walk(node):
        # ── Classes ──────────────────────────────────
        if node.type in ("class_definition",          # Python
                         "class_declaration",          # Java, C#, TS, JS
                         "interface_declaration",      # Java, C#, TS
                         "record_declaration",         # C#
                         "type_alias_declaration"):    # TS

            name = ""
            for child in node.children:
                if child.type in ("identifier", "type_identifier"):
                    name = child.text.decode("utf-8") if child.text else ""
                    break

            if not name:
                for child in node.named_children:
                    if child.type in ("identifier", "type_identifier"):
                        name = child.text.decode("utf-8") if child.text else ""
                        break

            if name:
                # Extrai contexto estrutural por linguagem
                if lang_name == "python":
                    bases = extract_base_classes_python(node)
                    decs  = extract_decorators_python(node, source_bytes)
                elif lang_name == "java":
                    bases = extract_base_classes_java(node)
                    decs  = extract_decorators_java(node)
                elif lang_name == "csharp":
                    bases = extract_base_classes_csharp(node)
                    decs  = extract_decorators_csharp(node)
                elif lang_name in ("typescript", "tsx", "javascript"):
                    bases = extract_base_classes_ts(node)
                    decs  = extract_decorators_ts(node)
                else:
                    bases, decs = [], []

                hint = classify_hint(name, bases, decs, file_role, lang_name, is_method=False)

                item = {
                    "name":         name,
                    "file":         relative_path,
                    "language":     lang_name,
                    "file_role":    file_role,
                    "base_classes": bases,
                    "decorators":   decs,
                    "sfp_hint":     hint,
                }

                if hint in ("data_function", "llm"):
                    data_functions.append(item)

        # ── Métodos e funções ──────────────────────────────────
        elif node.type in ("function_definition",     # Python
                           "method_declaration",       # Java, C#
                           "method_definition",        # JS, TS
                           "function_declaration",     # JS, TS
                           "constructor_declaration"): # C#

            name = ""
            for child in node.children:
                if child.type in ("identifier", "property_identifier"):
                    name = child.text.decode("utf-8") if child.text else ""
                    break

            if not name:
                for child in node.named_children:
                    if child.type in ("identifier", "property_identifier"):
                        name = child.text.decode("utf-8") if child.text else ""
                        break

            if name and not name.startswith("__"):  # ignora dunder Python
                if lang_name == "python":
                    decs = extract_decorators_python(node, source_bytes)
                elif lang_name == "java":
                    decs = extract_decorators_java(node)
                elif lang_name == "csharp":
                    decs = extract_decorators_csharp(node)
                elif lang_name in ("typescript", "tsx", "javascript"):
                    decs = extract_decorators_ts(node)
                else:
                    decs = []

                # Construtores C#: constructor_declaration → sempre ignorar
                if lang_name == "csharp" and node.type == "constructor_declaration":
                    for child in node.children:
                        walk(child)
                    return  # pula construtores C#

                # Construtores Java: method_declaration cujo nome começa com
                # maiúscula e não tem tipo de retorno → é construtor, ignora
                if lang_name == "java" and name[0].isupper():
                    # Verifica se o nó não possui tipo de retorno (construtor)
                    has_return_type = any(
                        c.type in ("void_type", "integral_type", "floating_point_type",
                                   "boolean_type", "type_identifier", "generic_type",
                                   "array_type")
                        for c in node.children
                    )
                    if not has_return_type:
                        for child in node.children:
                            walk(child)
                        return  # pula construtores Java

                hint = classify_hint(name, [], decs, file_role, lang_name, is_method=True)

                item = {
                    "name":         name,
                    "file":         relative_path,
                    "language":     lang_name,
                    "file_role":    file_role,
                    "base_classes": [],
                    "decorators":   decs,
                    "sfp_hint":     hint,
                }

                if hint in ("elementary_process", "llm"):
                    elementary_processes.append(item)

        for child in node.children:
            walk(child)

    walk(root)

    # Para JS/TS, detecta também rotas Express/Koa/Fastify
    # (padrão call_expression não capturado pelo walk padrão)
    if lang_name in ("javascript", "typescript", "tsx"):
        express_routes = extract_express_routes(root, relative_path, lang_name)
        elementary_processes.extend(express_routes)

    return {
        "data_functions":       data_functions,
        "elementary_processes": elementary_processes,
    }


# ─────────────────────────────────────────
# 7. Filtros de pastas e arquivos
# ─────────────────────────────────────────
IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__",
    ".venv", "dist", "build", "target",
    "tests", "test", "integration", "e2e",
    "__tests__", "spec", "fixtures",
    "scripts", "tools", "hooks",
    "migrations", "static", "media",
    "packages", "vendor", "third_party",
}


# ─────────────────────────────────────────
# 8. Varredura de repositório
# ─────────────────────────────────────────
def analyze_repository(repo_path, repo_name):
    print(f"\n🔍 Analisando repositório: {repo_name}")
    print(f"   Caminho: {repo_path}")
    print("-" * 50)

    report = {
        "repository":           repo_name,
        "files_analyzed":       0,
        "data_functions":       [],
        "elementary_processes": [],
    }

    for root_dir, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for filename in files:
            filepath  = os.path.join(root_dir, filename)
            ext = os.path.splitext(filename)[1].lower()
            lang_name = next(
                (l for l, c in LANGUAGES.items() if ext in c["extensions"]),
                None
            )

            if not lang_name:
                continue

            relative_path = filepath.replace(repo_path, "")

            try:
                result = analyze_file(filepath, lang_name, relative_path)
                report["files_analyzed"] += 1
                report["data_functions"]       += result["data_functions"]
                report["elementary_processes"] += result["elementary_processes"]
            except Exception as e:
                print(f"   ⚠️  Erro em {filename}: {e}")

    # Resumo por sfp_hint
    hints_df = {}
    for item in report["data_functions"]:
        h = item["sfp_hint"]
        hints_df[h] = hints_df.get(h, 0) + 1

    hints_ep = {}
    for item in report["elementary_processes"]:
        h = item["sfp_hint"]
        hints_ep[h] = hints_ep.get(h, 0) + 1

    print(f"   ✅ Arquivos analisados    : {report['files_analyzed']}")
    print(f"   📦 Funções de Dados       : {len(report['data_functions'])} "
          f"{hints_df}")
    print(f"   ⚙️  Processos Elementares  : {len(report['elementary_processes'])} "
          f"{hints_ep}")

    return report


# ─────────────────────────────────────────
# 9. Main
# ─────────────────────────────────────────
if __name__ == "__main__":
    base_dir   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    repos_dir  = os.path.join(base_dir, "repos")
    output_dir = os.path.join(base_dir, "output")

    os.makedirs(output_dir, exist_ok=True)

    all_reports = []

    for repo_name in sorted(os.listdir(repos_dir)):
        repo_path = os.path.join(repos_dir, repo_name)
        if not os.path.isdir(repo_path):
            continue

        report = analyze_repository(repo_path, repo_name)
        all_reports.append(report)

        output_file = os.path.join(output_dir, f"{repo_name}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"   💾 Salvo em: output/{repo_name}.json")

    consolidated_file = os.path.join(output_dir, "consolidated_report.json")
    with open(consolidated_file, "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 50)
    print("✅ Análise concluída!")
    print(f"📁 Resultados em: output/")
    print("=" * 50)