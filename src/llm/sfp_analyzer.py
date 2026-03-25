import os
import json
from openai import AzureOpenAI
from dotenv import load_dotenv
import httpx
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =============================================================================
# SFP Analyzer — Integração com Azure OpenAI
#
# Recebe o JSON gerado pelo extractor.py e envia para a LLM classificar
# os elementos segundo a metodologia SFP (Simple Function Points - IFPUG).
#
# O código fonte nunca é enviado — apenas nomes de classes e métodos.
# =============================================================================

load_dotenv()

# ─────────────────────────────────────────
# 1. Configuração do cliente Azure OpenAI
# ─────────────────────────────────────────
# Desabilita verificação SSL para contornar proxy corporativo
# com certificado auto-assinado. Rever quando fora da rede corporativa.
http_client = httpx.Client(verify=False)

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    http_client=http_client,
)

DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")


# ─────────────────────────────────────────
# 2. System prompt — instrui a LLM sobre a metodologia SFP
#
# Definido uma vez e reutilizado em todas as chamadas.
# Quanto mais preciso o contexto, melhor a classificação.
# ─────────────────────────────────────────
SYSTEM_PROMPT = """
Você é um especialista em mensuração de software pela metodologia 
SFP (Simple Function Points) do IFPUG (ISO 20926).

A metodologia SFP conta dois elementos:

1. FUNÇÕES DE DADOS — representam entidades do domínio do negócio.
   Exemplos: classes de modelo, entidades de banco, DTOs, schemas, 
   interfaces de domínio.
   NÃO são Funções de Dados: classes de teste, configuração, 
   infraestrutura, migrations, exceptions, utilitários.

2. PROCESSOS ELEMENTARES — representam operações de leitura ou escrita 
   sobre as entidades.
   Exemplos: endpoints REST, métodos de serviço (create, update, delete, 
   get, list), handlers de requisição.
   NÃO são Processos Elementares: métodos internos, utilitários, 
   construtores, métodos de configuração, métodos de teste.

Responda SEMPRE em formato JSON válido, sem texto adicional.
"""


# ─────────────────────────────────────────
# 3. Monta o prompt com os dados extraídos pelo tree-sitter
# ─────────────────────────────────────────
def build_prompt(repo_name, data_functions, elementary_processes):
    # Formata listas para o prompt — envia nome e arquivo para dar contexto
    classes_list = "\n".join(
        f"- {item['name']} ({item['file'].split(chr(92))[-1]})"
        for item in data_functions
    )
    methods_list = "\n".join(
        f"- {item['name']} ({item['file'].split(chr(92))[-1]})"
        for item in elementary_processes
    )

    return f"""
Analise os elementos extraídos do repositório "{repo_name}" e classifique 
cada item segundo a metodologia SFP.

CLASSES/INTERFACES ENCONTRADAS:
{classes_list}

MÉTODOS/FUNÇÕES ENCONTRADOS:
{methods_list}

Retorne um JSON com exatamente esta estrutura:
{{
  "repository": "{repo_name}",
  "data_functions": ["nome1", "nome2"],
  "elementary_processes": ["nome1", "nome2"],
  "ignored": ["nome1", "nome2"],
  "sfp_count": {{
    "data_functions": 0,
    "elementary_processes": 0,
    "total": 0
  }},
  "notes": "observações relevantes sobre a contagem"
}}
"""


# ─────────────────────────────────────────
# 4. Chama a LLM e retorna a contagem SFP
# ─────────────────────────────────────────
def analyze_with_llm(repo_name, data_functions, elementary_processes):
    print(f"\n🤖 Enviando para LLM: {repo_name}")
    print(f"   Classes enviadas  : {len(data_functions)}")
    print(f"   Métodos enviados  : {len(elementary_processes)}")

    prompt = build_prompt(repo_name, data_functions, elementary_processes)

    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            max_completion_tokens=4096,
            temperature=0,  # determinístico — importante para contagem
        )

        raw = response.choices[0].message.content.strip()

        # Remove possíveis marcadores de markdown que a LLM pode incluir
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]

        result = json.loads(raw)

        print(f"   ✅ Funções de Dados       : {result['sfp_count']['data_functions']}")
        print(f"   ⚙️  Processos Elementares  : {result['sfp_count']['elementary_processes']}")
        print(f"   📊 Total SFP              : {result['sfp_count']['total']}")

        return result

    except json.JSONDecodeError as e:
        print(f"   ❌ Erro ao parsear JSON da LLM: {e}")
        print(f"   Resposta bruta: {raw}")
        return None
    except Exception as e:
        print(f"   ❌ Erro na chamada à LLM: {e}")
        return None


# ─────────────────────────────────────────
# 6. Análise em lotes para repositórios grandes
# ─────────────────────────────────────────
BATCH_SIZE = 100

def analyze_in_batches(repo_name, data_functions, elementary_processes):
    total_df = len(data_functions)
    total_ep = len(elementary_processes)
    total    = total_df + total_ep

    if total <= BATCH_SIZE * 2:
        return analyze_with_llm(repo_name, data_functions, elementary_processes)

    print(f"\n   ⚠️  Repositório grande ({total} itens) — processando em lotes de {BATCH_SIZE}")

    all_data_functions       = []
    all_elementary_processes = []
    all_ignored              = []
    batch_num                = 0

    for i in range(0, total_df, BATCH_SIZE):
        batch_num += 1
        batch_df = data_functions[i:i + BATCH_SIZE]
        print(f"\n   📦 Lote {batch_num} — Funções de Dados [{i}:{i+len(batch_df)}]")
        result = analyze_with_llm(f"{repo_name} (lote {batch_num})", batch_df, [])
        if result:
            all_data_functions += result.get("data_functions", [])
            all_ignored        += result.get("ignored", [])

    for i in range(0, total_ep, BATCH_SIZE):
        batch_num += 1
        batch_ep = elementary_processes[i:i + BATCH_SIZE]
        print(f"\n   ⚙️  Lote {batch_num} — Processos Elementares [{i}:{i+len(batch_ep)}]")
        result = analyze_with_llm(f"{repo_name} (lote {batch_num})", [], batch_ep)
        if result:
            all_elementary_processes += result.get("elementary_processes", [])
            all_ignored              += result.get("ignored", [])

    final = {
        "repository":           repo_name,
        "data_functions":       list(set(all_data_functions)),
        "elementary_processes": list(set(all_elementary_processes)),
        "ignored":              list(set(all_ignored)),
        "sfp_count": {
            "data_functions":       len(set(all_data_functions)),
            "elementary_processes": len(set(all_elementary_processes)),
            "total":                len(set(all_data_functions)) + len(set(all_elementary_processes)),
        },
        "notes": f"Processado em {batch_num} lotes de até {BATCH_SIZE} itens."
    }

    print(f"\n   ✅ Funções de Dados       : {final['sfp_count']['data_functions']}")
    print(f"   ⚙️  Processos Elementares  : {final['sfp_count']['elementary_processes']}")
    print(f"   📊 Total SFP              : {final['sfp_count']['total']}")

    return final


# ─────────────────────────────────────────
# 5. Processa todos os repositórios
# ─────────────────────────────────────────
if __name__ == "__main__":
    base_dir   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    output_dir = os.path.join(base_dir, "output")
    sfp_dir    = os.path.join(base_dir, "output", "sfp")

    os.makedirs(sfp_dir, exist_ok=True)

    # ─────────────────────────────────────────
    # Controle de quais repositórios processar
    #
    # REPOS_PERMITIDOS: lista os JSONs que serão enviados à LLM.
    # Deixe vazio [] para processar todos — mas cuidado com custos!
    #
    # MAX_ITENS_POR_REPO: repositórios com mais itens que este limite
    # serão ignorados para evitar custo alto de API.
    # ─────────────────────────────────────────
    REPOS_PERMITIDOS = [
        "realworld-csharp-dotnet.json",
        "realworld-java-spring.json",
        "realworld-nodejs-express.json",
        "realworld-python-django.json",
        "realworld-react-js.json",
        "csharp-clean-arch.json",
        "java-clean-arch.json",
        "fastapi-fullstack.json",
    ]

    MAX_ITENS_POR_REPO = 500  # ignora repositórios maiores que isto

    all_results = []

    for filename in sorted(os.listdir(output_dir)):
        if filename == "consolidated_report.json" or not filename.endswith(".json"):
            continue

        # Pula repositórios não listados
        if REPOS_PERMITIDOS and filename not in REPOS_PERMITIDOS:
            print(f"\n⏭️  Pulando: {filename} (não está na lista)")
            continue

        filepath = os.path.join(output_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            repo_data = json.load(f)

        total_itens = len(repo_data["data_functions"]) + len(repo_data["elementary_processes"])

        # Pula repositórios muito grandes
        if total_itens > MAX_ITENS_POR_REPO:
            print(f"\n⏭️  Pulando: {repo_data['repository']} ({total_itens} itens — acima do limite de {MAX_ITENS_POR_REPO})")
            continue

        print(f"\n📋 {repo_data['repository']} — {total_itens} itens")

        result = analyze_in_batches(
            repo_name            = repo_data["repository"],
            data_functions       = repo_data["data_functions"],
            elementary_processes = repo_data["elementary_processes"],
        )

        if result:
            all_results.append(result)
            sfp_file = os.path.join(sfp_dir, filename)
            with open(sfp_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"   💾 Salvo em: output/sfp/{filename}")

    consolidated = os.path.join(sfp_dir, "sfp_consolidated.json")
    with open(consolidated, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 50)
    print("📊 RESUMO FINAL SFP")
    print("=" * 50)
    print(f"{'Repositório':<35} {'F.Dados':>8} {'P.Elem':>8} {'Total':>8}")
    print("-" * 50)
    for r in all_results:
        c = r.get("sfp_count", {})
        print(f"  {r['repository']:<33} {c.get('data_functions',0):>8} "
              f"{c.get('elementary_processes',0):>8} {c.get('total',0):>8}")
    print("=" * 50)
    print("✅ Análise SFP concluída!")
    print(f"📁 Resultados em: output/sfp/")