from mcp.client.streamable_http import streamable_http_client
from contextlib import AsyncExitStack
from mcp import ClientSession
from cache import *
from llm import *
import asyncio
import json

NOME_ESPECIALISTA = "FlorArtBot"
BASE_CONHECIMENTO = "conhecimento/flores.json"

CACHE = "cache"
MODELO_CACHE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
NOME_CACHE = "florartbot_cache"

URL_FERRAMENTAS = "http://localhost:8000/mcp"

def iniciar_persona_assistente(conhecimento):
    persona = [
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": f"Você é um especialista, perito, em flores e plantas ornamentais, chamado {NOME_ESPECIALISTA}. Você indica flores por ocasião e explica seus significados, orienta sobre cultivo e conservação e ajuda a diagnosticar problemas comuns"}]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "Se o usuário fizer uma saudação, você deve falar na sua resposta que você é um software, não é um humano, mas que pode ajudar o usuário com flores e plantas ornamentais"}]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "Se o usuário te perguntar algo que não esteja relacionado com flores ou plantas ornamentais, você deve dizer 'não posso responder esta pergunta'"}]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "Sempre que o usuário perguntar se uma espécie é tóxica para animais de estimação, qual a época de floração de uma espécie ou quais as necessidades de luz e rega de uma espécie, você deve executar a ferramenta correspondente (consultar_toxicidade, consultar_floracao ou consultar_luz_rega) e responder com base no resultado dela"}]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "Se a ferramenta informar que a espécie não está cadastrada, diga isso ao usuário, execute a ferramenta listar_especies e apresente as espécies disponíveis"}]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "Se o usuário solicitar esclarecimentos sobre o que você pode fazer, você deve explicar seus assuntos e as ferramentas disponíveis"}]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "Responda sempre em português, de forma curta e objetiva"}]
        }
    ]

    for mensagem, resposta in conhecimento:
        persona.append({
            "type": "user_input",
            "content": [{ "type": "text", "text": f"Caso o usuário fale ou pergunte '{mensagem}' ou algo parecido, sua resposta deve ser '{resposta}'"}]
        })

    return persona

async def carregar_conhecimento(base_conhecimento = BASE_CONHECIMENTO):
    carregado, conhecimento = False, []

    try:
        with open(base_conhecimento, "r", encoding = "utf-8") as arquivo:
            conteudo = json.load(arquivo)

        for pergunta_resposta in conteudo:
            pergunta = pergunta_resposta["pergunta"]
            resposta = pergunta_resposta["resposta"]

            conhecimento.append((pergunta, resposta))

        carregado = True
    except Exception as e:
        print(f"erro carregando conhecimento: {e}")

    return carregado, conhecimento

async def conectar_ferramentas(contexto, url_ferramentas = URL_FERRAMENTAS):
    conexao_mcp, ferramentas = None, []

    try:
        stream_leitura, stream_escrita = await contexto.enter_async_context(streamable_http_client(url_ferramentas))

        conexao_mcp = await contexto.enter_async_context(ClientSession(stream_leitura, stream_escrita))

        await conexao_mcp.initialize()

        listagem_ferramentas = await conexao_mcp.list_tools()
        for f in listagem_ferramentas.tools:
            ferramentas.append({
                "type": "function",
                "name": f.name,
                "description": f.description,
                "parameters": f.input_schema
            })
    except Exception as e:
        print(f"erro conectando as ferramentas: {e}")

    return conexao_mcp, ferramentas

def extrair_texto_execucao(resultado):
    if resultado.structured_content:
        return json.dumps(resultado.structured_content, ensure_ascii = False)

    conteudo = []
    for c in resultado.content:
        if hasattr(c, "text"):
            conteudo.append(c.text)
        else:
            conteudo.append(str(c))

    return "\n".join(conteudo)

async def executar_ferramentas(conexao_mcp, resposta, mensagens):
    ferramentas_para_executar = [passo for passo in resposta.steps if passo.type == "function_call"]
    if ferramentas_para_executar:
        for ferramenta in ferramentas_para_executar:
            print(f"🔧 executando a ferramenta {ferramenta.name} com {ferramenta.arguments}")
            execucao = await conexao_mcp.call_tool(ferramenta.name, arguments = ferramenta.arguments)

            mensagens.append({
                "type": "function_result",
                "name": ferramenta.name,
                "call_id": ferramenta.id,
                "result": [
                    {
                        "type": "text",
                        "text": extrair_texto_execucao(execucao)
                    }
                ]
            })

    return len(ferramentas_para_executar) > 0

async def executar():
    contexto = AsyncExitStack()
    conexao_mcp, ferramentas = await conectar_ferramentas(contexto)
    if not ferramentas:
        print("não foram encontradas ferramentas")
    else:
        for ferramenta in ferramentas:
            print(f"ferramenta encontrada: {ferramenta['name']}, descrição: {ferramenta['description']}")

    iniciado, llm = await iniciar_llm()
    if not iniciado:
        await contexto.aclose()

        print("erro iniciando llm")
        return

    carregado, conhecimento = await carregar_conhecimento()
    if not carregado:
        await contexto.aclose()

        print("erro carregando conhecimento")
        return

    iniciado, modelo_cache, colecao_cache = iniciar_cache(MODELO_CACHE, CACHE, NOME_CACHE)
    if not iniciado:
        await contexto.aclose()

        print("erro iniciando cache")
        return

    persona = iniciar_persona_assistente(conhecimento)

    while True:
        mensagem = input("👤 ")
        if mensagem in ["sair", "/s"]:
            break

        inicio_mensagem = len(persona)
        persona.append({
            "type": "user_input",
            "content": [{ "type": "text", "text": mensagem }]
        })

        encontrada, resposta = buscar_cache(mensagem, modelo_cache, colecao_cache)
        if encontrada:
            persona.append({ "type": "model_output", "text": resposta})

            print(f"🤖 {resposta} [resposta do cache]")
        else:
            ferramentas_executadas = False

            while True:
                sucesso, resposta = await obter_resposta(llm, persona, ferramentas, modelo = MODELO)
                if not sucesso:
                    resposta = None

                    break

                persona.extend(resposta.steps)
                print(f"🤖 tokens consumidos: {get_consumo_tokens(resposta)}")

                if not await executar_ferramentas(conexao_mcp, resposta, persona):
                    resposta = resposta.output_text

                    break
                else:
                    ferramentas_executadas = True

            if resposta is None:
                # remove a mensagem sem resposta para não poluir o histórico
                del persona[inicio_mensagem:]

                print("🤖 não foi possível obter uma resposta, tente novamente")
                continue

            print(f"🤖 {resposta} [resposta do llm]")
            if not ferramentas_executadas:
                gravar_cache(mensagem, resposta, modelo_cache, colecao_cache)

    await contexto.aclose()

if __name__ == "__main__":
    asyncio.run(executar())
