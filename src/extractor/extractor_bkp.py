import os
import json
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_java as tsjava
import tree_sitter_c_sharp as tscsharp
import tree_sitter_typescript as tstypescript

# =============================================================================
# SFP Extractor — Simple Function Points via tree-sitter
#
# Varre repositórios de código fonte e extrai dois elementos da metodologia SFP:
#   - Funções de Dados:       classes e modelos de dados (as entidades)
#   - Processos Elementares:  métodos e endpoints (operações de leitura/escrita)
#
# O resultado é salvo em JSON para posterior análise pela LLM.
# O código fonte nunca circula pela LLM — apenas nomes de classes e métodos.
#
# Compatibilidade: tree-sitter==0.22.3
# Linguagens:      Python, Java, JavaScript, TypeScript, TSX, C#
# =============================================================================


# ─────────────────────────────────────────
# 1. Configuração dos parsers por linguagem
#
# Cada linguagem precisa de um parser específico (grammar).
# As versões 0.21.x dos pacotes de linguagem são compatíveis
# com tree-sitter 0.22.3 — não atualizar sem validar compatibilidade.
# ─────────────────────────────────────────
LANGUAGES = {
    "csharp":     {"language": Language(tscsharp.language()),                  "extensions": [".cs"]},
    "python":     {"language": Language(tspython.language()),                  "extensions": [".py"]},
    "javascript": {"language": Language(tsjavascript.language()),              "extensions": [".js", ".jsx"]},
    "java":       {"language": Language(tsjava.language()),                    "extensions": [".java"]},
    "typescript": {"language": Language(tstypescript.language_typescript()),   "extensions": [".ts"]},
    "tsx":        {"language": Language(tstypescript.language_tsx()),          "extensions": [".tsx"]},
}


# ─────────────────────────────────────────
# 2. Queries SFP por linguagem
#
# Queries escritas na linguagem de consulta do tree-sitter (S-expressions).
# Cada linguagem tem padrões próprios para identificar:
#   - data_functions:       classes, interfaces, modelos de dados
#   - elementary_processes: métodos, funções, endpoints
#
# Referência: https://tree-sitter.github.io/tree-sitter/using-parsers/queries
# ─────────────────────────────────────────
QUERIES = {

    # C# — captura classes, interfaces e records como Funções de Dados.
    # Métodos e construtores como Processos Elementares.
    "csharp": {
        "data_functions": """
            [
              (class_declaration name: (identifier) @class_name)
              (interface_declaration name: (identifier) @class_name)
              (record_declaration name: (identifier) @class_name)
            ]
        """,
        "elementary_processes": """
            [
              (method_declaration name: (identifier) @method_name)
              (constructor_declaration name: (identifier) @method_name)
            ]
        """,
    },

    # Python — classes cobrem tanto models (Django) quanto ViewSets e Serializers.
    # Funções de nível de módulo e métodos são capturados como Processos Elementares.
    "python": {
        "data_functions":       "(class_definition name: (identifier) @class_name)",
        "elementary_processes": "(function_definition name: (identifier) @func_name)",
    },

    # JavaScript — usado principalmente para React (class components).
    # Arrow functions exportadas são capturadas como Processos Elementares
    # pois representam handlers e funções de serviço no padrão Redux/React.
    "javascript": {
        "data_functions": """
            [
              (class_declaration name: (identifier) @class_name)
            ]
        """,
        "elementary_processes": """
            [
              (method_definition name: (property_identifier) @func_name)
              (function_declaration name: (identifier) @func_name)
              (lexical_declaration
                (variable_declarator
                  name: (identifier) @func_name
                  value: (arrow_function)
                )
              )
            ]
        """,
    },

    # Java — classes como Funções de Dados.
    # Apenas method_declaration captura métodos públicos de negócio,
    # excluindo construtores e blocos estáticos que não representam operações SFP.
    "java": {
        "data_functions":       "(class_declaration name: (identifier) @class_name)",
        "elementary_processes": "(method_declaration name: (identifier) @method_name)",
    },

    # TypeScript — usa type_identifier em vez de identifier para classes e interfaces.
    # Funções exportadas como arrow functions representam serviços e controllers
    # no padrão Node.js/Express usado nos projetos da empresa.
    "typescript": {
        "data_functions": """
            [
              (interface_declaration name: (type_identifier) @class_name)
              (type_alias_declaration name: (type_identifier) @class_name)
              (class_declaration name: (type_identifier) @class_name)
            ]
        """,
        "elementary_processes": """
            [
              (export_statement
                declaration: (lexical_declaration
                  (variable_declarator
                    name: (identifier) @func_name
                    value: (arrow_function)
                  )
                )
              )
              (function_declaration name: (identifier) @func_name)
              (method_definition name: (property_identifier) @func_name)
            ]
        """,
    },

    # TSX — mesmo padrão do TypeScript, aplicado a arquivos React com JSX.
    "tsx": {
        "data_functions": """
            [
              (interface_declaration name: (type_identifier) @class_name)
              (type_alias_declaration name: (type_identifier) @class_name)
              (class_declaration name: (type_identifier) @class_name)
            ]
        """,
        "elementary_processes": """
            [
              (export_statement
                declaration: (lexical_declaration
                  (variable_declarator
                    name: (identifier) @func_name
                    value: (arrow_function)
                  )
                )
              )
              (function_declaration name: (identifier) @func_name)
              (method_definition name: (property_identifier) @func_name)
            ]
        """,
    },
}


# ─────────────────────────────────────────
# 3. Detecção de linguagem por extensão de arquivo
# ─────────────────────────────────────────
def detect_language(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    for lang, config in LANGUAGES.items():
        if ext in config["extensions"]:
            return lang
    return None


# ─────────────────────────────────────────
# 4. Execução de query tree-sitter
#
# Usa a API captures() da versão 0.22.x que retorna
# uma lista de tuplas (node, capture_name).
# Versões mais novas (0.25+) mudaram esta API — não atualizar
# o tree-sitter sem revisar esta função.
# ─────────────────────────────────────────
def run_query(language, query_string, root_node):
    names = []
    try:
        q        = language.query(query_string)
        captures = q.captures(root_node)
        for node, capture_name in captures:
            text = node.text.decode("utf-8") if node.text else ""
            if text.strip():
                names.append(text.strip())
    except Exception as e:
        print(f"      ⚠️  Erro na query: {e}")
    return names


# ─────────────────────────────────────────
# 5. Análise de um único arquivo
# ─────────────────────────────────────────
def analyze_file(filepath, lang_name):
    config   = LANGUAGES[lang_name]
    language = config["language"]
    parser   = Parser()
    parser.language = language

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        source_code = f.read()

    if not source_code.strip():
        return {"data_functions": [], "elementary_processes": []}

    tree = parser.parse(bytes(source_code, "utf-8"))
    root = tree.root_node

    return {
        "data_functions":       run_query(language, QUERIES[lang_name]["data_functions"],       root),
        "elementary_processes": run_query(language, QUERIES[lang_name]["elementary_processes"], root),
    }


# ─────────────────────────────────────────
# 6. Filtros de arquivos irrelevantes para SFP
#
# IGNORE_DIRS:         pastas que não contêm código de negócio
# IGNORE_FILE_PATTERNS: padrões de nome que indicam arquivos de teste,
#                       mock ou infraestrutura — não contam no SFP
# ─────────────────────────────────────────
IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__",
    ".venv", "dist", "build", "target"
}

# Arquivos de teste e infraestrutura serão classificados pela LLM
# com base na metodologia SFP, garantindo maior fidelidade na contagem.
IGNORE_FILE_PATTERNS = []

def should_ignore_file(filename):
    return False


# ─────────────────────────────────────────
# 7. Varredura completa de um repositório
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
            lang_name = detect_language(filepath)

            if not lang_name:
                continue
            if should_ignore_file(filename):
                continue

            try:
                result = analyze_file(filepath, lang_name)
                report["files_analyzed"] += 1
                relative_path = filepath.replace(repo_path, "")

                for name in result["data_functions"]:
                    report["data_functions"].append({
                        "name":     name,
                        "file":     relative_path,
                        "language": lang_name,
                    })

                for name in result["elementary_processes"]:
                    report["elementary_processes"].append({
                        "name":     name,
                        "file":     relative_path,
                        "language": lang_name,
                    })

            except Exception as e:
                print(f"   ⚠️  Erro em {filename}: {e}")

    print(f"   ✅ Arquivos analisados    : {report['files_analyzed']}")
    print(f"   📦 Funções de Dados       : {len(report['data_functions'])}")
    print(f"   ⚙️  Processos Elementares  : {len(report['elementary_processes'])}")

    return report


# ─────────────────────────────────────────
# 8. Ponto de entrada — processa todos os repositórios
#    e salva um JSON por repositório + um consolidado
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

    # Relatório consolidado — base para envio à LLM na próxima etapa
    consolidated_file = os.path.join(output_dir, "consolidated_report.json")
    with open(consolidated_file, "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 50)
    print("✅ Análise concluída!")
    print(f"📁 Resultados em: output/")
    print("=" * 50)