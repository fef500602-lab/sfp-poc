# Projeto: PoC de SFP (Simple Function Points) para Extração a partir do Código-Fonte

## Introdução
O VNT tem diversas iniciativas em 2026 de coleta de dados associadas à padronização de práticas técnicas, processos e fluxos de decisão orientados a dados. Este projeto apoia essas iniciativas através do desenvolvimento de métricas extraídas diretamente do código-fonte, que é considerado o construto mais fiel e rico em dados e informações.

O objetivo principal é medir a evolução funcional das bases de código dos projetos ao longo do tempo. O valor gerado por este trabalho são métricas executivas para o acompanhamento da produtividade e a derivação de métricas para a estimativa de novos projetos.

## Metodologia
A metodologia de dimensionamento funcional proposta é o **SFP (Simple Function Points)**, um padrão ISO mantido pelo IFPUG. O SFP simplifica a contagem em dois itens principais:
1. **Funções de Dados (Data Functions):** As entidades de dados do sistema.
2. **Processos Elementares (Elementary Processes):** As operações de leitura e escrita envolvendo essas entidades.

### Abordagem no Código-Fonte
Para habilitar a contagem via código, a estratégia estabelecida é:
*   Identificar classes ou modelos de dados para a contagem de **Funções de Dados**.
*   Identificar métodos, endpoints ou funções correspondentes para a contagem de **Processos Elementares**.

O fluxo de processamento funciona da seguinte maneira:
1.  **Processamento Local (Pipeline):** Uma ferramenta de parsing rápido varre o código do repositório em segundos, identificando componentes estruturais (classes, interfaces, métodos, funções). Esta etapa gera uma lista inicial de possíveis funções de dados e processos elementares. **Ferramenta escolhida: Tree-sitter.**
2.  **Processamento por IA Generativa (LLM):** A lista final estruturada gerada localmente é enviada para uma API de LLM. O papel do LLM é higienizar (sanitizar), validar e sintetizar a contagem final baseada estritamente nesses nomes extraídos, sem que o código-fonte transite para a IA.

**Vantagens do modelo:**
*   Privacidade e Segurança: Não há necessidade de autorização rigorosa do parceiro/cliente, pois o código-fonte não é enviado. Apenas nomes (identificadores) circulam.
*   Custo-benefício: O gasto com o processamento de tokens por IA é dramaticamente reduzido.
*   Velocidade: O `tree-sitter` é reconhecido pela sua performance e precisão na geração da AST (Abstract Syntax Tree).

## Etapas de Desenvolvimento da PoC e Planejamento

A Prova de Conceito (PoC) possui o seguinte acompanhamento:

1.  [x] Estudo dos fundamentos metodológicos (IFPUG / SFP).
2.  [x] Estudo das ferramentas (Tree-sitter).
3.  [x] Familiarização com inferência usando LLM (Chatbot AI).
4.  [Em andamento] Implementar extração de dados local usando o `tree-sitter` para múltiplas linguagens.
    *   *Nota atual:* Já desenvolvido para Python, JavaScript, Java, TypeScript e TSX no arquivo `extractor.py`.
5.  [ ] Implementar a integração com a API do LLM para inferir e consolidar a contagem.
6.  [ ] Validação da PoC utilizando repositórios públicos e, posteriormente, repositórios internos da empresa.

---

## Análise de Viabilidade Técnica x Planejamento Atual

A estratégia utilizando o `tree-sitter` é totalmente viável para a primeira fase (Processamento Local), possuindo evidências técnicas claras para o sucesso.

### Como o `extractor.py` (Tree-sitter) suporta os requisitos
1.  **Agosticismo e Flexibilidade:** O script atual já suporta múltiplas linguagens vitais (Python, JS, Java, TS, TSX) instanciando os respectivos motores e queries específicas, atendendo ao requisito de suportar bases de projeto heterogêneas.
2.  **Mapeamento de Funções de Dados e Processos Elementares (SFP):** As `QUERIES` do tree-sitter definidas mapeiam perfeitamente:
    *   *Data Functions:* Classes e Interfaces (`class_definition`, `interface_declaration`).
    *   *Elementary Processes:* Procedimentos operacionais (`method_definition`, `function_declaration`, `arrow_function`).
3.  **Processamento em Massa Rápido:** O script inclui a função `analyze_repository`, capaz de varrer localmente um diretório via `os.walk`, ignorando pastas não pertinentes (ex: `node_modules`, `.venv`), analisar centenas de arquivos e compilar uma relação JSON (`consolidated_report.json`). 
4.  **Integração Futura Garantida:** A saída JSON lista `name`, `file` e `language`. Este é exatamente o formato conciso (payload limpo) necessário para ser repassado ao LLM via API para sanitização na próxima etapa (Etapa 5).
