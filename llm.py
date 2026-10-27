from dotenv import load_dotenv
from google import genai
import asyncio
import os

load_dotenv()

MODELO = os.environ.get("MODELO_ASSISTENTE", "gemini-3.5-flash-lite")

TENTATIVAS = 3
ESPERA_INICIAL = 10

async def iniciar_llm():
    iniciado, llm = False, None

    try:
        llm = genai.Client(api_key = os.environ["GOOGLE_API_KEY"])

        iniciado = True
    except Exception as e:
        print(f"erro iniciando conexão com IA: {e}")

    return iniciado, llm

def limite_excedido(erro):
    # erro 429 (RESOURCE_EXHAUSTED): limite de requisições ou de tokens por minuto
    return getattr(erro, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(erro)

async def obter_resposta(llm, mensagens, ferramentas, modelo = MODELO):
    sucesso, resposta = False, None

    espera = ESPERA_INICIAL
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            if not ferramentas:
                resposta =  await llm.aio.interactions.create(
                    input = mensagens,
                    model = modelo
                )
            else:
                resposta =  await llm.aio.interactions.create(
                    input = mensagens,
                    tools = ferramentas,
                    model = modelo
                )

            sucesso = True
            break
        except Exception as e:
            if limite_excedido(e) and tentativa < TENTATIVAS:
                print(f"limite da API atingido, nova tentativa em {espera}s ({tentativa}/{TENTATIVAS})")
                await asyncio.sleep(espera)

                espera *= 2
            else:
                print(f"ocorreu um erro ao obter resposta: {e}")
                break

    return sucesso, resposta

def get_consumo_tokens(resposta):
    uso = resposta.usage

    return {
        "entrada": uso.total_input_tokens or 0,
        "saida": uso.total_output_tokens or 0,
        "raciocinio": uso.total_thought_tokens or 0,
        "ferramentas": uso.total_tool_use_tokens or 0,
        "total": uso.total_tokens or 0
    }

async def executar():
    iniciado, llm = await iniciar_llm()
    if not iniciado:
        return
    print("llm iniciado")

    mensagens = [
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "Elabore uma resposta curta para uma saudação. Na sua resposta, você deve se identificar como um sistema especialista em flores e plantas ornamentais"}]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "O seu nome é FlorArtBot. Sempre se identifique com esse nome durante saudações"}]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "olá, tudo bem?"}]
        }
    ]

    sucesso, resposta = await obter_resposta(llm, mensagens, None)
    if sucesso:
        print(f"resposta do llm: {resposta.output_text}")
    else:
        print("não foi possível obter uma resposta do llm")

if __name__ == "__main__":
    asyncio.run(executar())
