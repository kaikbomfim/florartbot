from chat import *
from llm import *
import argparse
import asyncio
import json
import os

# o julgamento roda separado do chat: nenhuma mensagem do usuário passa pelo juiz,
# assim o consumo de tokens fica restrito às execuções deste script

MODELO_ASSISTENTE = os.environ.get("MODELO_ASSISTENTE", "gemini-3.5-flash-lite")
MODELO_JULGAMENTO = os.environ.get("MODELO_JULGAMENTO", "gemini-3.1-flash-lite")

BASE_JULGAMENTO = "conhecimento/flores_menor.json"
RESULTADOS = "resultados/julgamento.json"

PAUSA_PADRAO = 4
ORCAMENTO_PADRAO = 50000

ALUCINACOES = [
    {
        "pergunta": "O que significa a rosa vermelha?",
        "resposta": "É um modelo de carro esportivo lançado na década de 1990."
    },
    {
        "pergunta": "Com que frequência devo regar uma orquídea?",
        "resposta": "Orquídeas devem ficar submersas em água o tempo todo, como plantas de aquário."
    }
]

async def iniciar_persona_julgamento():
    # a persona do juiz não carrega a base inteira: a referência vai somente no caso julgado
    persona = [
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "Você é um especialista, perito, em flores e plantas ornamentais" }]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "Sua função é avaliar se uma determinada resposta responde adequadamente uma pergunta sobre flores e plantas ornamentais, usando a resposta de referência, quando houver, como base de comparação. A resposta não precisa ser idêntica à referência, mas deve ser correta e compatível com ela" }]
        },
        {
            "type": "user_input",
            "content": [{ "type": "text", "text": "A sua resposta deve conter APENAS uma string que informe, 'ATENDE', se a resposta responde a pergunta e 'NÃO ATENDE' se a resposta não responde a pergunta. Não é necessário explicar o seu julgamento." }]
        }
    ]

    return persona

def montar_caso(pergunta, resposta, referencia = None):
    texto = f"pergunta: '{pergunta}', resposta: '{resposta}'"
    if referencia:
        texto += f", resposta de referência: '{referencia}'"

    return {
        "type": "user_input",
        "content": [{ "type": "text", "text": texto }]
    }

def estimar_tokens(mensagens):
    # estimativa grosseira (~4 caracteres por token), usada apenas no modo seco
    return sum(len(c["text"]) for m in mensagens for c in m["content"]) // 4

def carregar_resultados(refazer):
    if refazer or not os.path.exists(RESULTADOS):
        return {}

    with open(RESULTADOS, "r", encoding = "utf-8") as arquivo:
        return json.load(arquivo)

def salvar_resultados(resultados):
    os.makedirs(os.path.dirname(RESULTADOS), exist_ok = True)

    with open(RESULTADOS, "w", encoding = "utf-8") as arquivo:
        json.dump(resultados, arquivo, ensure_ascii = False, indent = 2)

class Controle:
    def __init__(self, pausa, orcamento):
        self.pausa = pausa
        self.orcamento = orcamento
        self.tokens = 0
        self.chamadas = 0

    def esgotado(self):
        return self.tokens >= self.orcamento

    async def chamar(self, llm, mensagens, modelo):
        if self.chamadas > 0:
            await asyncio.sleep(self.pausa)

        sucesso, resposta = await obter_resposta(llm, mensagens, None, modelo = modelo)
        self.chamadas += 1

        if sucesso:
            consumo = get_consumo_tokens(resposta)
            self.tokens += consumo["total"]

            print(f"   tokens: {consumo['total']} (acumulado: {self.tokens}/{self.orcamento})")

        return sucesso, resposta

async def testar_alucinacoes(llm, julgador, controle, resultados):
    detectadas = 0

    for alucinacao in ALUCINACOES:
        pergunta = alucinacao["pergunta"]
        resposta = alucinacao["resposta"]
        chave = f"alucinacao::{pergunta}"

        if chave in resultados:
            julgamento = resultados[chave]["julgamento"]
            print(f"♻️  julgamento reaproveitado para a alucinação '{resposta}'")
        else:
            if controle.esgotado():
                print("⛔ orçamento de tokens atingido, interrompendo")
                break

            print(f"julgando a alucinação '{resposta}' para a pergunta '{pergunta}'")
            sucesso, julgamento = await controle.chamar(llm, julgador + [montar_caso(pergunta, resposta)], MODELO_JULGAMENTO)
            if not sucesso:
                print("⛔ não foi possível julgar, interrompendo (os resultados até aqui foram salvos)")
                break

            julgamento = julgamento.output_text.strip()
            resultados[chave] = {"pergunta": pergunta, "resposta": resposta, "julgamento": julgamento}
            salvar_resultados(resultados)

        if "NÃO ATENDE" in julgamento:
            detectadas += 1
            print("👍👍 a resposta foi julgada INADEQUADA para a pergunta 👍👍")
        else:
            print("👎👎 o juiz NÃO detectou a alucinação 👎👎")

    return detectadas

async def testar_assistente(llm, conhecimento, assistente, julgador, controle, resultados):
    adequadas = 0

    for pergunta, referencia in conhecimento:
        chave = f"assistente::{pergunta}"

        if chave in resultados:
            resposta = resultados[chave]["resposta"]
            julgamento = resultados[chave]["julgamento"]
            print(f"♻️  julgamento reaproveitado para a pergunta '{pergunta}'")
        else:
            if controle.esgotado():
                print("⛔ orçamento de tokens atingido, interrompendo")
                break

            print(f"perguntando ao assistente: '{pergunta}'")
            sucesso, resposta = await controle.chamar(llm, assistente + [
                {
                    "type": "user_input",
                    "content": [{ "type": "text", "text": pergunta }]
                }
            ], MODELO_ASSISTENTE)
            if not sucesso:
                print("⛔ não foi possível obter a resposta, interrompendo (os resultados até aqui foram salvos)")
                break

            resposta = resposta.output_text.strip()

            print(f"julgando a resposta '{resposta}'")
            sucesso, julgamento = await controle.chamar(llm, julgador + [montar_caso(pergunta, resposta, referencia)], MODELO_JULGAMENTO)
            if not sucesso:
                print("⛔ não foi possível julgar, interrompendo (os resultados até aqui foram salvos)")
                break

            julgamento = julgamento.output_text.strip()
            resultados[chave] = {"pergunta": pergunta, "resposta": resposta, "referencia": referencia, "julgamento": julgamento}
            salvar_resultados(resultados)

        if "NÃO ATENDE" not in julgamento:
            adequadas += 1
            print("👍👍 a resposta foi julgada ADEQUADA para a pergunta 👍👍")
        else:
            print("👎👎 a resposta foi julgada INADEQUADA para a pergunta 👎👎")

    return adequadas

def simular(conhecimento, assistente, julgador, resultados):
    chamadas, tokens = 0, 0

    for alucinacao in ALUCINACOES:
        if f"alucinacao::{alucinacao['pergunta']}" not in resultados:
            chamadas += 1
            tokens += estimar_tokens(julgador + [montar_caso(alucinacao["pergunta"], alucinacao["resposta"])])

    for pergunta, referencia in conhecimento:
        if f"assistente::{pergunta}" not in resultados:
            chamadas += 2
            tokens += estimar_tokens(assistente) + estimar_tokens(julgador + [montar_caso(pergunta, referencia, referencia)])

    print(f"modo seco: {chamadas} chamadas à API, ~{tokens} tokens de entrada estimados (sem contar saída e raciocínio)")
    print(f"modelos: assistente '{MODELO_ASSISTENTE}', juiz '{MODELO_JULGAMENTO}'")

def ler_argumentos():
    parser = argparse.ArgumentParser(description = "avaliação do FlorArtBot com LLM-as-a-Judge")
    parser.add_argument("--base", default = BASE_JULGAMENTO, help = "base de perguntas e respostas de referência")
    parser.add_argument("--limite", type = int, default = None, help = "quantidade máxima de perguntas avaliadas")
    parser.add_argument("--pausa", type = float, default = PAUSA_PADRAO, help = "segundos de espera entre chamadas à API")
    parser.add_argument("--orcamento", type = int, default = ORCAMENTO_PADRAO, help = "máximo de tokens consumidos nesta execução")
    parser.add_argument("--refazer", action = "store_true", help = "ignora resultados salvos e julga tudo de novo")
    parser.add_argument("--seco", action = "store_true", help = "apenas estima as chamadas, sem usar a API")

    return parser.parse_args()

async def executar():
    argumentos = ler_argumentos()

    carregado, conhecimento = await carregar_conhecimento(base_conhecimento = argumentos.base)
    assert(carregado == True and len(conhecimento) > 0)

    if argumentos.limite:
        conhecimento = conhecimento[:argumentos.limite]

    resultados = carregar_resultados(argumentos.refazer)
    julgador = await iniciar_persona_julgamento()
    assistente = iniciar_persona_assistente(conhecimento)

    if argumentos.seco:
        simular(conhecimento, assistente, julgador, resultados)
        return

    iniciado, llm = await iniciar_llm()
    assert(iniciado == True)

    controle = Controle(argumentos.pausa, argumentos.orcamento)

    detectadas = await testar_alucinacoes(llm, julgador, controle, resultados)
    adequadas = await testar_assistente(llm, conhecimento, assistente, julgador, controle, resultados)

    print("\n📋 resumo do julgamento")
    print(f"   alucinações detectadas: {detectadas} de {len(ALUCINACOES)}")
    print(f"   respostas adequadas: {adequadas} de {len(conhecimento)}")
    print(f"   chamadas à API: {controle.chamadas}, tokens consumidos: {controle.tokens}")
    print(f"   resultados salvos em {RESULTADOS}")

if __name__ == "__main__":
    asyncio.run(executar())
