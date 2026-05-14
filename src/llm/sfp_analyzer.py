import os
import json
from openai import AzureOpenAI
from dotenv import load_dotenv
import httpx
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =============================================================================
# SFP Analyzer v2.0 — Integração com Azure OpenAI
#
# Arquitetura de duas etapas:
#
#   1. Pré-classificação determinística (extractor.py)
#      Itens com sfp_hint "data_function" ou "elementary_process" são
#      contados automaticamente — zero tokens gastos.
#
#   2. Classificação LLM (este módulo)
#      Apenas itens com sfp_hint "llm" são enviados à LLM, com contexto
#      estrutural completo: decorators, herança, file_role e linguagem.
#      A LLM retorna classificação individual com justificativa.
#
# Esta separação reduz custo de API e aumenta consistência:
# casos determinísticos não dependem de variação do modelo.
#
# O código fonte nunca é enviado — apenas metadados estruturais.
#
# Compatibilidade: extractor.py v3.1+
# =============================================================================

load_dotenv()

# ─────────────────────────────────────────
# 1. Configuração do cliente Azure OpenAI
# ─────────────────────────────────────────
# Bypass de verificação SSL para proxy corporativo com certificado
# auto-assinado. Rever quando fora da rede corporativa.
http_client = httpx.Client(verify=False)

client = AzureOpenAI(
    api_key        = os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version    = os.getenv("AZURE_OPENAI_API_VERSION"),
    http_client    = http_client,
)

DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

# Máximo de itens por chamada à LLM.
# Cada item gera ~200 chars de JSON de resposta (name + file + classification + reason).
# Com 50 itens → ~10.000 chars → ~2.500 tokens de saída → margem segura para 8.192.
# Reduzido de 80 para 50 após truncamento observado no NestJS (lote de 80 → 16.683 chars).
BATCH_SIZE = 50


# ─────────────────────────────────────────
# 2. System prompt — especialista SFP
#
# Inclui regras precisas da metodologia para reduzir
# ambiguidade na classificação dos casos borderline.
# ─────────────────────────────────────────
SYSTEM_PROMPT = """
Você é um especialista certificado em mensuração de software pela metodologia
SFP (Simple Function Points) do IFPUG (ISO 20926).

A metodologia SFP conta dois elementos funcionais do sistema:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 FUNÇÕES DE DADOS (FD)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Grupos lógicos de dados do domínio do negócio que o sistema mantém ou
referencia. Representam ENTIDADES, não mecanismos técnicos.

✅ CONTAR como FD:
  - Entidades de domínio (User, Article, Order, Product, Invoice, etc.)
  - Value objects e agregados DDD com significado de negócio
  - Interfaces de domínio que representam contratos de dados de negócio

❌ NÃO CONTAR como FD:
  - Infraestrutura: DbContext, repositórios, DAOs, migrations
  - Transporte: DTOs, ViewModels, Request/Response bodies, Envelopes
  - Técnico: Exceptions, Middleware, Filters, Configurations, Modules
  - Bootstrap: Startup, DependencyInjection, Extensions
  - Testes e mocks

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PROCESSOS ELEMENTARES (EP)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Operações atômicas na FRONTEIRA DO SISTEMA com o usuário ou sistema externo.
Cada operação distinta conta UMA vez, no ponto de entrada no sistema.

REGRA DE FRONTEIRA (crítica):
  Em arquiteturas em camadas (MVC, layered), o EP é contado no Controller.
  O Service que implementa a mesma operação internamente NÃO é um EP adicional
  — é a implementação da mesma fronteira. Contar os dois seria dupla contagem.

✅ CONTAR como EP:
  - Endpoints HTTP no controller (GET, POST, PUT, DELETE, PATCH)
  - Handlers CQRS que são a única fronteira da operação (sem controller separado)
  - Application Service como fronteira exclusiva (sem controller correspondente)

❌ NÃO CONTAR como EP:
  - Métodos de Service quando já existe Controller para a mesma operação
    (ArticleService.createArticle não conta se ArticleController.create existe)
  - Helpers e utilitários internos sem contato com o usuário
  - Construtores e factory methods técnicos
  - Métodos de framework (canActivate, intercept, catch, handle genérico)
  - Configuração e bootstrap (ConfigureServices, OnModelCreating, etc.)
  - Getters/setters simples e propriedades computadas
  - Duplicatas: interface + implementação conta UMA vez

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 REGRAS DE CONTAGEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Quando interface e implementação aparecerem juntas: classifique a
  implementação concreta como EP/FD e a interface como "ignore"
- Quando receber métodos de Controller E Service da mesma operação:
  classifique o Controller como EP e o Service como "ignore"
- Em Vertical Slice Architecture (VSA), cada "feature" tem um controller
  method (Get, Create, Edit) E um handler method (Handle). São a MESMA
  operação de negócio. Classifique o controller method como EP e o Handle
  correspondente como "ignore". Se não houver controller, o Handle é EP.
- Métodos com nome genérico (Handle, Execute, Run) em arquivos de feature
  CQRS sem controller correspondente: contar como EP
- Em caso de dúvida genuína, prefira "ignore" a inflar a contagem

Responda SEMPRE em formato JSON válido, sem texto adicional, sem markdown.
"""


# ─────────────────────────────────────────
# 3. Separação por sfp_hint
#
# Itens pré-classificados com certeza pelo extractor são contados
# automaticamente. Apenas os ambíguos vão à LLM.
# ─────────────────────────────────────────
def split_by_hint(items):
    """
    Separa itens com classificação determinística dos ambíguos.

    Returns:
        confirmed : lista com sfp_hint definitivo (data_function / elementary_process)
        to_llm    : lista com sfp_hint "llm" — precisam de julgamento da LLM
    """
    confirmed, to_llm = [], []
    for item in items:
        if item.get("sfp_hint", "llm") == "llm":
            to_llm.append(item)
        else:
            confirmed.append(item)
    return confirmed, to_llm


# ─────────────────────────────────────────
# 4. Formatação do contexto estrutural
#
# Cada item enviado à LLM inclui todos os sinais disponíveis:
# papel do arquivo, herança, decorators e linguagem.
# ─────────────────────────────────────────
def format_item_for_prompt(item):
    """
    Formata um item com contexto estrutural completo para o prompt.

    Ex: "nome: UserProfile | arquivo: users/models.py | papel: unknown |
         herança: TimestampedModel | linguagem: python"
    """
    parts = [f"nome: {item['name']}"]
    parts.append(f"arquivo: {item.get('file', '')}")

    file_role = item.get("file_role", "unknown")
    if file_role and file_role != "unknown":
        parts.append(f"papel: {file_role}")

    bases = item.get("base_classes", [])
    if bases:
        parts.append(f"herança: {', '.join(bases)}")

    decs = item.get("decorators", [])
    if decs:
        parts.append(f"decorators: {', '.join(decs)}")

    lang = item.get("language", "")
    if lang:
        parts.append(f"linguagem: {lang}")

    return " | ".join(parts)


# ─────────────────────────────────────────
# 5. Construção do prompt para itens ambíguos
# ─────────────────────────────────────────
def build_llm_prompt(repo_name, llm_classes, llm_methods):
    """
    Monta prompt apenas com os itens ambíguos (sfp_hint: llm),
    com contexto estrutural completo para auxiliar a classificação.
    """
    classes_text = "\n".join(
        f"  {i+1}. {format_item_for_prompt(item)}"
        for i, item in enumerate(llm_classes)
    ) or "  (nenhum)"

    methods_text = "\n".join(
        f"  {i+1}. {format_item_for_prompt(item)}"
        for i, item in enumerate(llm_methods)
    ) or "  (nenhum)"

    total = len(llm_classes) + len(llm_methods)

    return f"""Repositório: "{repo_name}"

Estes {total} elementos foram extraídos pelo parser tree-sitter mas não
puderam ser classificados deterministicamente pela pipeline de pré-processamento.
Classifique cada um segundo a metodologia SFP usando o contexto fornecido.

CLASSES / INTERFACES AMBÍGUAS ({len(llm_classes)} itens):
{classes_text}

MÉTODOS / FUNÇÕES AMBÍGUOS ({len(llm_methods)} itens):
{methods_text}

Retorne um JSON com exatamente esta estrutura — classifique TODOS os {total} itens:
{{
  "classifications": [
    {{
      "name": "NomeExato",
      "file": "caminho/exato/do/arquivo",
      "classification": "data_function",
      "reason": "justificativa objetiva em português"
    }},
    {{
      "name": "OutroNome",
      "file": "caminho/exato/do/arquivo",
      "classification": "elementary_process",
      "reason": "justificativa objetiva em português"
    }},
    {{
      "name": "ItemIgnorado",
      "file": "caminho/exato/do/arquivo",
      "classification": "ignore",
      "reason": "justificativa objetiva em português"
    }}
  ]
}}

Valores válidos para "classification": "data_function", "elementary_process", "ignore".
"""


# ─────────────────────────────────────────
# 6. Chamada à LLM
# ─────────────────────────────────────────
def call_llm(repo_name, llm_classes, llm_methods):
    """
    Envia os itens ambíguos à LLM e retorna lista de classificações.

    Cada classificação é um dict com:
        name, file, classification, reason
    """
    prompt = build_llm_prompt(repo_name, llm_classes, llm_methods)

    try:
        response = client.chat.completions.create(
            model      = DEPLOYMENT,
            messages   = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            max_completion_tokens = 8192,   # aumentado de 4096: evita truncamento em lotes
            temperature           = 0,   # determinístico — essencial para contagem
        )

        raw = response.choices[0].message.content.strip()

        # Remove possíveis marcadores de markdown da LLM
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0].strip()

        result = json.loads(raw)
        return result.get("classifications", [])

    except json.JSONDecodeError as e:
        # Resposta truncada — divide o lote ao meio e tenta novamente
        total = len(llm_classes) + len(llm_methods)
        if total > 10:
            half = total // 2
            print(f"   ⚠️  JSON truncado ({e}) — re-tentando com lotes de {half} itens")
            mid_c = len(llm_classes) // 2 or len(llm_classes)
            mid_m = len(llm_methods) // 2 or len(llm_methods)
            part1 = call_llm(repo_name + " (A)", llm_classes[:mid_c], llm_methods[:mid_m])
            part2 = call_llm(repo_name + " (B)", llm_classes[mid_c:], llm_methods[mid_m:])
            return part1 + part2
        print(f"   ❌ JSON inválido mesmo com lote pequeno: {e}")
        return []
    except Exception as e:
        print(f"   ❌ Erro na chamada à LLM: {e}")
        return []


def _process_in_batches(repo_name, llm_fds, llm_eps):
    """
    Quando o total de itens ambíguos excede BATCH_SIZE,
    processa em lotes separados (FDs e EPs) e consolida.
    """
    all_classifications = []
    batch_num = 0

    for i in range(0, len(llm_fds), BATCH_SIZE):
        batch_num += 1
        batch = llm_fds[i:i + BATCH_SIZE]
        print(f"      📦 Lote {batch_num} — Classes [{i}:{i+len(batch)}]")
        all_classifications += call_llm(f"{repo_name} (lote {batch_num})", batch, [])

    for i in range(0, len(llm_eps), BATCH_SIZE):
        batch_num += 1
        batch = llm_eps[i:i + BATCH_SIZE]
        print(f"      ⚙️  Lote {batch_num} — Métodos [{i}:{i+len(batch)}]")
        all_classifications += call_llm(f"{repo_name} (lote {batch_num})", [], batch)

    return all_classifications


# ─────────────────────────────────────────
# 7. Análise completa de um repositório
# ─────────────────────────────────────────
def analyze_repository(repo_data):
    """
    Orquestra a análise SFP de um repositório em duas etapas:

      Etapa A — Contagem automática
        Itens com sfp_hint "data_function" ou "elementary_process"
        são contados diretamente, sem custo de API.

      Etapa B — Classificação LLM
        Itens com sfp_hint "llm" são enviados à LLM com contexto
        enriquecido. A LLM retorna classificação + justificativa.

      Resultado final = Etapa A + Etapa B
    """
    repo_name = repo_data["repository"]
    all_fds   = repo_data["data_functions"]
    all_eps   = repo_data["elementary_processes"]

    # ── Etapa A: separação por sfp_hint ──────────────────────────
    confirmed_fds, llm_fds = split_by_hint(all_fds)
    confirmed_eps, llm_eps = split_by_hint(all_eps)
    total_llm = len(llm_fds) + len(llm_eps)

    print(f"\n🔍 {repo_name}")
    print(f"   Pré-classificados → FD: {len(confirmed_fds)}, EP: {len(confirmed_eps)}")
    print(f"   Enviando à LLM   → FD: {len(llm_fds)}, EP: {len(llm_eps)}  ({total_llm} itens)")

    # Monta listas finais com os itens auto-confirmados.
    # hint_reason vem do extrator e registra qual regra determinística disparou.
    final_fds = [
        {
            "name":   i["name"],
            "file":   i["file"],
            "source": "pre_classifier",
            "reason": i.get("hint_reason", ""),
        }
        for i in confirmed_fds
    ]
    final_eps = [
        {
            "name":   i["name"],
            "file":   i["file"],
            "source": "pre_classifier",
            "reason": i.get("hint_reason", ""),
        }
        for i in confirmed_eps
    ]
    ignored_by_llm = []

    # ── Etapa B: LLM para os casos ambíguos ──────────────────────
    if total_llm > 0:
        if total_llm <= BATCH_SIZE:
            classifications = call_llm(repo_name, llm_fds, llm_eps)
        else:
            classifications = _process_in_batches(repo_name, llm_fds, llm_eps)

        llm_fd_count  = 0
        llm_ep_count  = 0
        llm_ign_count = 0

        for c in classifications:
            entry = {
                "name":   c.get("name", ""),
                "file":   c.get("file", ""),
                "source": "llm",
                "reason": c.get("reason", ""),
            }
            clf = c.get("classification", "ignore")
            if clf == "data_function":
                final_fds.append(entry)
                llm_fd_count += 1
            elif clf == "elementary_process":
                final_eps.append(entry)
                llm_ep_count += 1
            else:
                ignored_by_llm.append(entry)
                llm_ign_count += 1

        print(f"   LLM classificou  → FD: {llm_fd_count}, EP: {llm_ep_count}, "
              f"Ignorados: {llm_ign_count}")

    # ── Resultado final ───────────────────────────────────────────
    result = {
        "repository": repo_name,
        "pre_classification": {
            "data_functions":       len(confirmed_fds),
            "elementary_processes": len(confirmed_eps),
        },
        "llm_classification": {
            "sent":                 total_llm,
            "data_functions":       len(final_fds)  - len(confirmed_fds),
            "elementary_processes": len(final_eps)  - len(confirmed_eps),
            "ignored":              len(ignored_by_llm),
        },
        "sfp_count": {
            "data_functions":       len(final_fds),
            "elementary_processes": len(final_eps),
            "total":                len(final_fds) + len(final_eps),
        },
        "data_functions":       final_fds,
        "elementary_processes": final_eps,
        "ignored_by_llm":       ignored_by_llm,
    }

    print(f"   ✅ FD: {result['sfp_count']['data_functions']}  "
          f"EP: {result['sfp_count']['elementary_processes']}  "
          f"Total SFP: {result['sfp_count']['total']}")

    return result


# ─────────────────────────────────────────
# 8. Ponto de entrada — processa todos os repositórios
# ─────────────────────────────────────────
if __name__ == "__main__":
    base_dir   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    output_dir = os.path.join(base_dir, "output")
    sfp_dir    = os.path.join(output_dir, "sfp")
    os.makedirs(sfp_dir, exist_ok=True)

    # ─────────────────────────────────────────
    # Controle de repositórios a processar
    #
    # REPOS_PERMITIDOS — lista os JSONs do conjunto de validação.
    # Repositórios frontend (React) e casos de borda são excluídos:
    # não representam aplicações backend mensuráveis por SFP.
    #
    # Deixe REPOS_PERMITIDOS = [] para processar tudo (cuidado com custo).
    # ─────────────────────────────────────────
    REPOS_PERMITIDOS = [
        # Conjunto principal RealWorld — mesma aplicação em múltiplas linguagens
        "realworld-csharp-dotnet.json",
        "realworld-java-spring.json",
        "realworld-nodejs-express.json",
        "realworld-python-django.json",
        "realworld-kotlin-ktor.json",
        # Arquiteturas complementares
        "csharp-clean-arch.json",
        "nestjs-framework.json",
    ]

    all_results = []

    for filename in sorted(os.listdir(output_dir)):
        if not filename.endswith(".json") or filename == "consolidated_report.json":
            continue

        if REPOS_PERMITIDOS and filename not in REPOS_PERMITIDOS:
            print(f"⏭️  Pulando: {filename}")
            continue

        filepath = os.path.join(output_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            repo_data = json.load(f)

        total_itens = (len(repo_data["data_functions"])
                       + len(repo_data["elementary_processes"]))

        print(f"\n{'='*55}")
        print(f"📋 {repo_data['repository']} — {total_itens} elementos extraídos")

        result = analyze_repository(repo_data)

        if result:
            all_results.append(result)
            sfp_file = os.path.join(sfp_dir, filename)
            with open(sfp_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"   💾 Salvo em: output/sfp/{filename}")

    # Consolida todos os resultados em um único arquivo
    consolidated = os.path.join(sfp_dir, "sfp_consolidated.json")
    with open(consolidated, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    # ── Resumo final ─────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("📊 RESUMO FINAL SFP")
    print("=" * 65)
    print(f"  {'Repositório':<32} {'Auto':>6} {'LLM':>6} {'FD':>6} {'EP':>6} {'Total':>7}")
    print("  " + "-" * 63)
    total_fd = total_ep = 0
    for r in all_results:
        pre = r.get("pre_classification", {})
        llm = r.get("llm_classification", {})
        c   = r.get("sfp_count", {})
        auto = pre.get("data_functions", 0) + pre.get("elementary_processes", 0)
        fd   = c.get("data_functions", 0)
        ep   = c.get("elementary_processes", 0)
        tot  = c.get("total", 0)
        total_fd += fd
        total_ep += ep
        print(f"  {r['repository']:<32} {auto:>6} {llm.get('sent',0):>6} "
              f"{fd:>6} {ep:>6} {tot:>7}")
    print("  " + "-" * 63)
    print(f"  {'TOTAL':<32} {'':>6} {'':>6} {total_fd:>6} {total_ep:>6} {total_fd+total_ep:>7}")
    print("=" * 65)
    print("✅ Análise SFP concluída!")
    print(f"📁 Resultados em: output/sfp/")

    # ── Relatório Excel (SFP-02) ─────────────────────────────────
    try:
        import sys
        sys.path.insert(0, os.path.join(base_dir, "src"))
        from report.generate_report import generate as generate_excel
        excel_path = os.path.join(output_dir, "sfp_report.xlsx")
        generate_excel(sfp_dir, excel_path)
    except Exception as exc:
        print(f"   ⚠️  Relatório Excel não gerado: {exc}")