import json
import os

OUTPUT_DIR = "output"

# ─────────────────────────────────────────
# Critérios de validação SFP
# ─────────────────────────────────────────

# Palavras que indicam Funções de Dados REAIS (modelos/entidades)
KEYWORDS_DATA = [
    "model", "entity", "schema", "dto", "domain",
    "record", "document", "data", "request", "response",
    "user", "article", "profile", "comment", "tag",
    "product", "order", "customer", "account"
]

# Palavras que indicam Processos Elementares REAIS (endpoints/operações)
KEYWORDS_PROCESS = [
    "get", "post", "put", "delete", "patch",
    "create", "update", "find", "list", "save",
    "fetch", "load", "read", "write", "handle",
    "register", "login", "logout", "submit"
]

# Palavras que indicam RUÍDO (testes, configs, utilitários)
KEYWORDS_NOISE = [
    "test", "spec", "mock", "stub", "fake",
    "setup", "teardown", "config", "util", "helper",
    "abstract", "base", "mixin", "exception", "error"
]

def classify(name):
    name_lower = name.lower()
    if any(k in name_lower for k in KEYWORDS_NOISE):
        return "🔴 ruído"
    if any(k in name_lower for k in KEYWORDS_DATA):
        return "✅ dados"
    if any(k in name_lower for k in KEYWORDS_PROCESS):
        return "✅ processo"
    return "⚠️  indefinido"

def validate_repository(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    repo = data["repository"]
    print(f"\n{'='*60}")
    print(f"📁 Repositório: {repo}")
    print(f"{'='*60}")

    # ── Funções de Dados ──
    print(f"\n📦 FUNÇÕES DE DADOS ({len(data['data_functions'])} encontradas)")
    print(f"{'─'*60}")

    contagem_dados = {"✅ dados": 0, "🔴 ruído": 0, "⚠️  indefinido": 0}
    for item in data["data_functions"]:
        classificacao = classify(item["name"])
        contagem_dados[classificacao] = contagem_dados.get(classificacao, 0) + 1
        print(f"  {classificacao}  {item['name']:40s} ({item['file'].split(chr(92))[-1]})")

    print(f"\n  Resumo:")
    for k, v in contagem_dados.items():
        pct = (v / len(data["data_functions"]) * 100) if data["data_functions"] else 0
        print(f"    {k}: {v} ({pct:.0f}%)")

    # ── Processos Elementares ──
    print(f"\n⚙️  PROCESSOS ELEMENTARES ({len(data['elementary_processes'])} encontrados)")
    print(f"{'─'*60}")

    contagem_proc = {"✅ processo": 0, "🔴 ruído": 0, "⚠️  indefinido": 0}
    for item in data["elementary_processes"][:30]:  # mostra primeiros 30
        classificacao = classify(item["name"])
        contagem_proc[classificacao] = contagem_proc.get(classificacao, 0) + 1
        print(f"  {classificacao}  {item['name']:40s} ({item['file'].split(chr(92))[-1]})")

    if len(data["elementary_processes"]) > 30:
        print(f"  ... e mais {len(data['elementary_processes']) - 30} itens")

    print(f"\n  Resumo (primeiros 30):")
    for k, v in contagem_proc.items():
        pct = (v / min(30, len(data["elementary_processes"])) * 100) if data["elementary_processes"] else 0
        print(f"    {k}: {v} ({pct:.0f}%)")

    return {
        "repo": repo,
        "data_functions": len(data["data_functions"]),
        "elementary_processes": len(data["elementary_processes"]),
        "dados_validos": contagem_dados.get("✅ dados", 0),
        "processos_validos": contagem_proc.get("✅ processo", 0),
        "ruido_dados": contagem_dados.get("🔴 ruído", 0),
        "ruido_proc": contagem_proc.get("🔴 ruído", 0),
    }

if __name__ == "__main__":
    print("🔍 VALIDAÇÃO DOS RESULTADOS SFP")
    print("=" * 60)

    resultados = []
    for filename in sorted(os.listdir(OUTPUT_DIR)):
        if filename == "consolidated_report.json":
            continue
        if filename.endswith(".json"):
            path = os.path.join(OUTPUT_DIR, filename)
            r = validate_repository(path)
            resultados.append(r)

    # ── Tabela resumo final ──
    print(f"\n\n{'='*60}")
    print("📊 RESUMO GERAL DA VALIDAÇÃO")
    print(f"{'='*60}")
    print(f"{'Repositório':<30} {'F.Dados':>8} {'P.Elem':>8} {'Ruído%':>8}")
    print(f"{'─'*60}")
    for r in resultados:
        total = r["data_functions"] + r["elementary_processes"]
        ruido = r["ruido_dados"] + r["ruido_proc"]
        pct_ruido = (ruido / total * 100) if total > 0 else 0
        print(f"  {r['repo']:<28} {r['data_functions']:>8} {r['elementary_processes']:>8} {pct_ruido:>7.0f}%")