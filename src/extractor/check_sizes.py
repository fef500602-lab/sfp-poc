import json
import os

output_dir = "output"

print(f"{'Repositório':<40} {'Total itens':>12}  {'Status'}")
print("-" * 60)

for filename in sorted(os.listdir(output_dir)):
    if not filename.endswith(".json"):
        continue
    if filename == "consolidated_report.json":
        continue

    filepath = os.path.join(output_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    total = len(data["data_functions"]) + len(data["elementary_processes"])
    alerta = "🔴 GRANDE" if total > 500 else "🟢 OK"

    print(f"  {data['repository']:<38} {total:>10}   {alerta}")