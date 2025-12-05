# scripts/seed_precedents.py
"""
Seed Chroma local collection 'precedents' from data/precedents.json.

- Uses PersistentClient (new Chroma API).
- Tries SentenceTransformer embeddings first.
- Falls back to TF-IDF if transformers unavailable.
"""

import json
import os
import sys
import chromadb

CHROMA_DIR = os.path.join(os.getcwd(), "chroma_db")
DATA_PATH = os.path.join(os.getcwd(), "data", "precedents.json")
COLLECTION_NAME = "precedents"


def load_documents(path):
    with open(path, "r", encoding="utf-8") as f:
        docs = json.load(f)
    if not isinstance(docs, list) or not all(isinstance(d, str) for d in docs):
        raise ValueError("precedents.json must be a JSON array of strings.")
    return docs


def init_chroma_client():
    # new API — persistent client
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client


def try_sentence_transformer_embedder():
    try:
        from chromadb.utils import embedding_functions
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        return ef
    except Exception as e:
        print("SentenceTransformer embedder not available:", str(e))
        return None


def seed_with_sentence_transformer(client, docs, ef):
    try:
        col = client.get_or_create_collection(
            name=COLLECTION_NAME, embedding_function=ef
        )
        ids = [str(i) for i in range(len(docs))]
        col.add(documents=docs, ids=ids)
        print(
            f"Added {len(docs)} documents to collection '{COLLECTION_NAME}' with transformer embeddings."
        )
        return col
    except Exception as e:
        raise RuntimeError("Failed to seed with sentence-transformer embedder: " + str(e))


def seed_with_tfidf(client, docs):
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except Exception as e:
        raise RuntimeError(
            "scikit-learn is required for TF-IDF fallback. Install scikit-learn."
        ) from e

    vec = TfidfVectorizer(max_features=512)
    X = vec.fit_transform(docs)
    embeddings = X.toarray().tolist()

    col = client.get_or_create_collection(name=COLLECTION_NAME)
    ids = [str(i) for i in range(len(docs))]
    col.add(documents=docs, ids=ids, embeddings=embeddings)
    print(
        f"Added {len(docs)} documents to collection '{COLLECTION_NAME}' with TF-IDF embeddings."
    )
    return col, vec


def sample_query(col, query_text):
    res = col.query(query_texts=[query_text], n_results=3)
    print(f"Sample query results for '{query_text}':")
    for i, doc in enumerate(res.get("documents", [[]])[0]):
        print(f" {i+1}) {doc[:200].replace('\\n',' ')}")


def main():
    if not os.path.exists(DATA_PATH):
        print(f"Error: {DATA_PATH} not found. Create data/precedents.json first.")
        sys.exit(1)

    docs = load_documents(DATA_PATH)
    client = init_chroma_client()

    ef = try_sentence_transformer_embedder()
    if ef:
        try:
            col = seed_with_sentence_transformer(client, docs, ef)
            sample_query(col, "confidentiality obligations")
            return
        except Exception as e:
            print("Transformer seeding failed, fallback to TF-IDF. Error:", e)

    # fallback
    col, vec = seed_with_tfidf(client, docs)
    sample_query(col, "confidentiality obligations")


if __name__ == "__main__":
    main()
