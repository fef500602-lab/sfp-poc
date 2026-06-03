import json
import os
from collections import Counter

OUTPUT_DIR = "output"

def diagnostico(filename, label, max_items=10):
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        print(f"\n⚠️  Arquivo não encontrado: {filepath}")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n{'='*60}")
    print(f"DIAGNÓSTICO — {label}")
    print(f"{'='*60}")
    print(f"Arquivos analisados : {data.get('files_analyzed', '?')}")
    print(f"Funções de Dados    : {len(data['data_functions'])}")
    print(f"Processos Elementar : {len(data['elementary_processes'])}")

    # Breakdown por sfp_hint
    hints_df = Counter(i.get("sfp_hint", "?") for i in data["data_functions"])
    hints_ep = Counter(i.get("sfp_hint", "?") for i in data["elementary_processes"])
    print(f"Hints F.Dados       : {dict(hints_df)}")
    print(f"Hints P.Elem        : {dict(hints_ep)}")

    print(f"\n--- Funções de Dados (primeiros {max_items}) ---")
    for item in data["data_functions"][:max_items]:
        print(f"  [{item.get('sfp_hint','?'):20s}] {item['name']:35s}"
              f" | role: {item.get('file_role','?'):12s}"
              f" | bases: {item.get('base_classes',[])}"
              f" | decs: {item.get('decorators',[])}")

    print(f"\n--- Processos Elementares (primeiros {max_items}) ---")
    for item in data["elementary_processes"][:max_items]:
        print(f"  [{item.get('sfp_hint','?'):20s}] {item['name']:35s}"
              f" | role: {item.get('file_role','?'):12s}"
              f" | decs: {item.get('decorators',[])}")


# ── Conjunto principal de validação (repositórios RealWorld) ──
# Critério: aplicações de negócio completas, mesma especificação,
# múltiplas linguagens — permite comparação direta entre tecnologias.
repos_validacao = [
    ("realworld-python-django.json",  "Python Django"),
    ("realworld-java-spring.json",    "Java Spring"),
    ("realworld-nodejs-express.json", "Node.js Express"),
    ("realworld-csharp-dotnet.json",  "C# .NET"),
    ("csharp-clean-arch.json",        "C# Clean Arch"),
    ("nestjs-framework.json",         "NestJS Framework"),
]

# ── Casos de borda (excluídos da validação principal) ──
# Documentados como limitações conhecidas da ferramenta.
repos_edge = [
    # React JS: frontend puro — componentes UI não mapeiam para SFP.
    # A ferramenta filtra corretamente (0 FD / 0 EP), mas o repositório
    # não representa uma aplicação backend mensurável por SFP.
    ("realworld-react-js.json",  "Edge — React JS (frontend)"),

    # Express Lib: repositório do próprio framework Express.js, não uma
    # aplicação. Contém código interno do framework + demos de exemplo.
    # A ferramenta extrai rotas corretamente, mas os números não têm
    # significado de negócio — não é código de aplicação.
    # Limitação conhecida: a ferramenta não distingue framework de aplicação.
    ("edge-express-lib.json",    "Edge — Express Lib (framework, não app)"),

    # Markdown apenas: repositório sem código-fonte — resultado 0 esperado.
    # Valida que o extractor não quebra com repositórios não-suportados.
    ("edge-only-markdown.json",  "Edge — Markdown (sem código)"),
]

print("=" * 60)
print("CONJUNTO PRINCIPAL DE VALIDAÇÃO")
print("=" * 60)
for filename, label in repos_validacao:
    diagnostico(filename, label)

print()
print("=" * 60)
print("CASOS DE BORDA (fora do conjunto de validação)")
print("=" * 60)
for filename, label in repos_edge:
    diagnostico(filename, label)