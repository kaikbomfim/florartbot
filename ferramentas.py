from mcp.server.mcpserver import MCPServer
import unicodedata
import json
import os

BASE_ESPECIES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conhecimento", "especies.json")

NOME = "base_especies"
mcp = MCPServer(NOME, "uma base de consulta de especies de flores e plantas ornamentais")

def normalizar_nome(nome):
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.lower().replace("-", " ").strip().split())

def carregar_especies(base_especies = BASE_ESPECIES):
    with open(base_especies, "r", encoding = "utf-8") as arquivo:
        return json.load(arquivo)

ESPECIES = carregar_especies()

def buscar_especie(nome):
    procurado = normalizar_nome(nome)

    for especie in ESPECIES:
        nomes = [especie["nome"], especie["cientifico"]] + especie["sinonimos"]
        if procurado in [normalizar_nome(n) for n in nomes]:
            return especie

    return None

def especie_nao_encontrada(nome):
    return f"a espécie '{nome}' não está cadastrada na base; use a ferramenta listar_especies para ver as espécies disponíveis"

@mcp.tool(name = "listar_especies", title = "listagem das especies cadastradas", description = "lista as especies de flores e plantas ornamentais cadastradas na base, com nome popular e cientifico")
def listar_especies():
    return "\n".join(f"{e['nome']} ({e['cientifico']})" for e in ESPECIES)

@mcp.tool(name = "consultar_toxicidade", title = "consulta de toxicidade para animais de estimacao", description = "informa se uma especie de flor ou planta ornamental e toxica para caes e gatos")
def consultar_toxicidade(especie: str):
    encontrada = buscar_especie(especie)
    if not encontrada:
        return especie_nao_encontrada(especie)

    toxicidade = encontrada["toxicidade"]
    return (
        f"{encontrada['nome']} ({encontrada['cientifico']}): "
        f"cães: {toxicidade['caes']}; gatos: {toxicidade['gatos']}; observação: {toxicidade['observacao']}"
    )

@mcp.tool(name = "consultar_floracao", title = "consulta da epoca de floracao", description = "informa a epoca de floracao de uma especie de flor ou planta ornamental")
def consultar_floracao(especie: str):
    encontrada = buscar_especie(especie)
    if not encontrada:
        return especie_nao_encontrada(especie)

    return f"{encontrada['nome']} ({encontrada['cientifico']}): floração: {encontrada['floracao']}"

@mcp.tool(name = "consultar_luz_rega", title = "consulta das necessidades de luz e rega", description = "informa a necessidade de luz e a frequencia de rega de uma especie de flor ou planta ornamental")
def consultar_luz_rega(especie: str):
    encontrada = buscar_especie(especie)
    if not encontrada:
        return especie_nao_encontrada(especie)

    return f"{encontrada['nome']} ({encontrada['cientifico']}): luz: {encontrada['luz']}; rega: {encontrada['rega']}"

if __name__ == "__main__":
    mcp.run(transport = "streamable-http", host = "0.0.0.0", streamable_http_path = "/mcp")
