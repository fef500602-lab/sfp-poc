import os
import json
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_java as tsjava
import tree_sitter_typescript as tstypescript

# ─────────────────────────────────────────
# 1. Configura linguagens
# ─────────────────────────────────────────
PY_LANGUAGE   = Language(tspython.language())
JS_LANGUAGE   = Language(tsjavascript.language())
JAVA_LANGUAGE = Language(tsjava.language())

LANGUAGES = {
    "python":     {"language": PY_LANGUAGE,   "extensions": [".py"]},
    "javascript": {"language": JS_LANGUAGE,   "extensions": [".js", ".jsx"]},
    "java":       {"language": JAVA_LANGUAGE, "extensions": [".java"]},
    "typescript": {"language": Language(tstypescript.language_typescript()), "extensions": [".ts"]},
    "tsx":{"language": Language(tstypescript.language_tsx()), "extensions": [".tsx"]},
}

# ─────────────────────────────────────────
# 2. Queries SFP por linguagem
# ─────────────────────────────────────────
QUERIES = {
    "python": {
        "data_functions":       "(class_definition name: (identifier) @class_name)",
        "elementary_processes": "(function_definition name: (identifier) @func_name)",
    },
    "javascript": {
        "data_functions":       "(class_declaration name: (identifier) @class_name)",
        "elementary_processes": "(function_declaration name: (identifier) @func_name)",
    },
    "java": {
        "data_functions":       "(class_declaration name: (identifier) @class_name)",
        "elementary_processes": "(method_declaration name: (identifier) @method_name)",
    },
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
# 3. Detecta linguagem pela extensão
# ─────────────────────────────────────────
def detect_language(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    for lang, config in LANGUAGES.items():
        if ext in config["extensions"]:
            return lang
    return None

# ─────────────────────────────────────────
# 4. Executa query — API 0.21.x
#    captures() retorna lista de (node, capture_name)
# ─────────────────────────────────────────
def run_query(language, query_string, root_node):
    names = []
    try:
        q        = language.query(query_string)
        captures = q.captures(root_node)          # [(node, "capture_name"), ...]
        for node, capture_name in captures:
            text = node.text.decode("utf-8") if node.text else ""
            if text.strip():
                names.append(text.strip())
    except Exception as e:
        print(f"      ⚠️  Erro na query: {e}")
    return names

# ─────────────────────────────────────────
# 5. Analisa um único arquivo
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
# 6. Varre repositório inteiro
# ─────────────────────────────────────────
IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__",
    ".venv", "dist", "build", "target"
}

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
# 7. Main
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