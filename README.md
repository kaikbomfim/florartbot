# FlorArtBot

Sistema especialista em flores e plantas ornamentais: indicação por ocasião e significado, cuidados de cultivo e conservação e diagnóstico de problemas comuns. Usa LLM (Gemini), cache semântico (ChromaDB), ferramentas MCP de consulta a uma base de espécies e avaliação por LLM-as-a-Judge.

## Instalação

```bash
# crie e ative o ambiente virtual
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS

# instale as dependências registradas no arquivo 'requirements.txt'
pip install -r requirements.txt

# crie um arquivo .env copiando o conteúdo do arquivo .env.example
# e informe um valor para GOOGLE_API_KEY (chave de acesso a modelos de IA da google)
# https://aistudio.google.com/api-keys
copy .env.example .env          # Windows
cp .env.example .env            # Linux/macOS
```

## Ferramentas MCP (terminal 1)

```bash
# inicia o serviço MCP em http://localhost:8000/mcp
python ferramentas.py

# inspeciona rapidamente o serviço MCP
fastmcp inspect ferramentas.py

# executa o inspetor visual (web) de ferramentas
# transporte: Streamable HTTP, URL: http://localhost:8000/mcp
npx @modelcontextprotocol/inspector
```

| Ferramenta | Exemplo de argumento | Retorno |
|---|---|---|
| `listar_especies` | — | espécies cadastradas |
| `consultar_toxicidade` | `{"especie": "lírio"}` | toxicidade para cães e gatos |
| `consultar_floracao` | `{"especie": "girassol"}` | época de floração |
| `consultar_luz_rega` | `{"especie": "orquidea"}` | necessidade de luz e rega |
| qualquer consulta | `{"especie": "baobá"}` | espécie não cadastrada |

A busca aceita nome popular, científico ou sinônimo, com ou sem acento (`conhecimento/especies.json`).

## Chat (terminal 2, com o MCP em execução)

```bash
python chat.py
```

Mensagens para testar:

```text
olá, tudo bem?                                   -> saudação, identifica-se como software
o que significa o girassol?                      -> resposta da base de conhecimento
qual o significado do girassol?                  -> mesma pergunta reformulada: [resposta do cache]
qual flor dar para pedir desculpas?              -> indicação por ocasião
por que as folhas da minha planta estão amarelando? -> diagnóstico
lírio é tóxico para gatos?                       -> executa consultar_toxicidade
quando floresce a azaleia?                       -> executa consultar_floracao
quanto sol e água precisa uma lavanda?           -> executa consultar_luz_rega
quais espécies você conhece?                     -> executa listar_especies
quem ganhou a copa de 2002?                      -> não posso responder esta pergunta
sair                                             -> encerra (ou /s)
```

Respostas que usaram ferramentas não vão para o cache, pois dependem da consulta à base.

## Julgador (LLM-as-a-Judge)

Roda separado do chat, sobre `conhecimento/flores_menor.json`, para não consumir tokens a cada mensagem. Cada caso envia ao juiz só a pergunta, a resposta e a referência daquele par.

```bash
# mostra quantas chamadas e tokens seriam usados, sem chamar a API
python julgamento.py --seco

# avalia apenas as 3 primeiras perguntas
python julgamento.py --limite 3

# avalia toda a base pequena (2 alucinações + 6 perguntas)
python julgamento.py

# julga tudo de novo, ignorando resultados salvos
python julgamento.py --refazer
```

| Opção | Padrão | Função |
|---|---|---|
| `--base` | `conhecimento/flores_menor.json` | base de perguntas e referências |
| `--limite` | todas | quantidade máxima de perguntas |
| `--pausa` | `4` | segundos entre chamadas (evita erro 429) |
| `--orcamento` | `50000` | para ao atingir esse total de tokens |
| `--refazer` | — | ignora os resultados salvos |
| `--seco` | — | apenas estima, sem usar a API |

Os resultados ficam em `resultados/julgamento.json`; uma nova execução reaproveita o que já foi julgado. Os modelos podem ser trocados no `.env` (`MODELO_ASSISTENTE`, `MODELO_JULGAMENTO`).
