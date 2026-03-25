import json
from collections import Counter

# ─────────────────────────────────────────
# Diagnóstico 1 — edge-only-markdown
# ─────────────────────────────────────────
print("\n" + "="*60)
print("DIAGNÓSTICO 1 — edge-only-markdown")
print("="*60)

with open("output/edge-only-markdown.json", "r") as f:
    data = json.load(f)

files = set()
for i in data["data_functions"] + data["elementary_processes"]:
    files.add(i["file"])

print("\nArquivos capturados:")
for f in sorted(files):
    print(f"  {f}")

print("\nFunções de Dados:")
for i in data["data_functions"]:
    print(f"  {i['name']} — {i['file']}")

print("\nProcessos Elementares (primeiros 15):")
for i in data["elementary_processes"][:15]:
    print(f"  {i['name']} — {i['file']}")


# ─────────────────────────────────────────
# Diagnóstico 2 — nestjs-framework
# ─────────────────────────────────────────
print("\n" + "="*60)
print("DIAGNÓSTICO 2 — nestjs-framework")
print("="*60)

with open("output/nestjs-framework.json", "r") as f:
    data = json.load(f)

pastas = Counter()
for item in data["data_functions"] + data["elementary_processes"]:
    partes = item["file"].replace("\\", "/").strip("/").split("/")
    pasta = partes[0] if partes else "raiz"
    pastas[pasta] += 1

print("\nTop 15 pastas com mais capturas:")
for pasta, total in pastas.most_common(15):
    print(f"  {total:5d}  {pasta}")


# ─────────────────────────────────────────
# Diagnóstico 3 — saleor-ecommerce
# ─────────────────────────────────────────
print("\n" + "="*60)
print("DIAGNÓSTICO 3 — saleor-ecommerce")
print("="*60)

with open("output/saleor-ecommerce.json", "r") as f:
    data = json.load(f)

extensoes = Counter()
pastas = Counter()

for item in data["elementary_processes"]:
    ext = item["file"].split(".")[-1]
    extensoes[ext] += 1
    partes = item["file"].replace("\\", "/").strip("/").split("/")
    pasta = partes[0] if partes else "raiz"
    pastas[pasta] += 1

total_proc = len(data["elementary_processes"])
total_dados = len(data["data_functions"])

print(f"\nTotal Processos Elementares : {total_proc}")
print(f"Total Funcoes de Dados      : {total_dados}")

print("\nPor extensão:")
for ext, total in extensoes.most_common(10):
    print(f"  {total:6d}  .{ext}")

print("\nTop 10 pastas:")
for pasta, total in pastas.most_common(10):
    print(f"  {total:6d}  {pasta}")