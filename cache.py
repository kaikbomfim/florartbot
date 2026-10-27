from sentence_transformers import SentenceTransformer
import chromadb

import hashlib
import os

LIMIAR_DISTANCIA_CACHE = 0.20

def iniciar_cache(modelo, caminho, nome):
    iniciado, modelo_cache, colecao_cache = False, None, None

    try:
        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("MPLCONFIGDIR", ".matplotlib")

        modelo_cache = SentenceTransformer(modelo)
        cliente_cache = chromadb.PersistentClient(path = str(caminho))
        colecao_cache = cliente_cache.get_or_create_collection(
            name = nome,
            metadata = {"hnsw:space": "cosine"}
        )

        iniciado = True
    except Exception as e:
        print(f"cache semântico indisponível: {str(e)}")

    return iniciado, modelo_cache, colecao_cache

def normalizar_pergunta(pergunta):
    return " ".join(pergunta.lower().strip().split())

def gerar_id_cache(pergunta):
    pergunta_normalizada = normalizar_pergunta(pergunta)
    return hashlib.sha256(pergunta_normalizada.encode("utf-8")).hexdigest()

def gerar_embedding(modelo_cache, texto):
    return modelo_cache.encode(texto, normalize_embeddings = True).tolist()

def buscar_cache(pergunta, modelo_cache, colecao_cache):
    encontrada, resposta = False, None

    try:
        if colecao_cache.count() == 0:
            return encontrada, resposta

        embedding = gerar_embedding(modelo_cache, pergunta)
        resultados = colecao_cache.query(
            query_embeddings = [embedding],
            n_results = 1,
            include = ["metadatas", "distances"]
        )

        distancias = resultados["distances"][0]
        metadados = resultados["metadatas"][0]

        distancia = distancias[0]
        resposta = metadados[0].get("resposta")

        encontrada = resposta is not None and distancia <= LIMIAR_DISTANCIA_CACHE
    except Exception as e:
        print(f"ocorreu um erro consultando o cache semântico: {str(e)}")

    return encontrada, resposta

def gravar_cache(pergunta, resposta, modelo_cache, colecao_cache):
    if modelo_cache is None or colecao_cache is None or not pergunta.strip() or not resposta:
        return

    try:
        embedding = gerar_embedding(modelo_cache, pergunta)
        colecao_cache.upsert(
            ids = [gerar_id_cache(pergunta)],
            embeddings = [embedding],
            documents = [pergunta],
            metadatas = [{"pergunta": pergunta, "resposta": resposta}]
        )
    except Exception as e:
        print(f"ocorreu um erro gravando no cache semântico: {str(e)}")
