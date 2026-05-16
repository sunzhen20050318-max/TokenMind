from __future__ import annotations

import json
import math
import re
import shutil
import sqlite3
import threading
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import json_repair
from loguru import logger
from openai import OpenAI
from pypdf import PdfReader

from tokenmind.knowledge.chunking import semantic_chunks, simple_chunks
from tokenmind.knowledge.models import (
    KnowledgeBaseRecord,
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    SessionKnowledgeLinks,
    utc_now_iso,
)
from tokenmind.knowledge.wiki_graph import build_graph_data
from tokenmind.knowledge.wiki_ingest import compile_with_llm
from tokenmind.utils.helpers import safe_filename

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".csv",
    ".tsv",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".html",
    ".css",
}

ASCII_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]{2,}")
CJK_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")


class KnowledgeService:
    def __init__(
        self,
        workspace: Path,
        *,
        vector_backend: str = "sqlite",
        chunk_size: int = 900,
        chunk_overlap: int = 120,
        top_k: int = 6,
        embedding_model: str = "",
        embedding_api_key: str = "",
        embedding_api_base: str | None = None,
        rerank_model: str = "",
        rerank_api_key: str = "",
        rerank_api_base: str | None = None,
        rerank_top_n: int = 12,
    ):
        self.workspace = workspace
        self.root = workspace / "knowledge"
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.root / "metadata.json"
        self.index_file = self.root / "vectors.sqlite3"
        self.vector_backend = vector_backend or "sqlite"
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        self.embedding_model = embedding_model.strip()
        self.embedding_api_key = embedding_api_key.strip()
        self.embedding_api_base = embedding_api_base.strip() if embedding_api_base else None
        self.rerank_model = rerank_model.strip()
        self.rerank_api_key = rerank_api_key.strip()
        self.rerank_api_base = rerank_api_base.strip() if rerank_api_base else None
        self.rerank_top_n = rerank_top_n
        self.collection_name = "knowledge_chunks"
        self._state_lock = threading.RLock()
        self._state = self._load()
        self._ensure_index()
        self._wiki_llm_provider = None
        self._wiki_llm_model: str | None = None

    def set_wiki_llm(self, provider, model: str) -> None:
        self._wiki_llm_provider = provider
        self._wiki_llm_model = model

    def configure(
        self,
        *,
        vector_backend: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        top_k: int | None = None,
        embedding_model: str | None = None,
        embedding_api_key: str | None = None,
        embedding_api_base: str | None = None,
        rerank_model: str | None = None,
        rerank_api_key: str | None = None,
        rerank_api_base: str | None = None,
        rerank_top_n: int | None = None,
    ) -> None:
        if vector_backend is not None:
            self.vector_backend = vector_backend or "sqlite"
        if chunk_size is not None:
            self.chunk_size = chunk_size
        if chunk_overlap is not None:
            self.chunk_overlap = chunk_overlap
        if top_k is not None:
            self.top_k = top_k
        if embedding_model is not None:
            self.embedding_model = embedding_model.strip()
        if embedding_api_key is not None:
            self.embedding_api_key = embedding_api_key.strip()
        if embedding_api_base is not None:
            self.embedding_api_base = embedding_api_base.strip() or None
        if rerank_model is not None:
            self.rerank_model = rerank_model.strip()
        if rerank_api_key is not None:
            self.rerank_api_key = rerank_api_key.strip()
        if rerank_api_base is not None:
            self.rerank_api_base = rerank_api_base.strip() or None
        if rerank_top_n is not None:
            self.rerank_top_n = rerank_top_n

    def _load(self) -> dict:
        if self.metadata_file.exists():
            return json.loads(self.metadata_file.read_text(encoding="utf-8"))
        return {
            "knowledge_bases": [],
            "documents": [],
            "session_links": {},
        }

    def _reload(self) -> None:
        self._state = self._load()

    def _save(self) -> None:
        tmp_file = self.metadata_file.with_suffix(".tmp")
        tmp_file.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_file.replace(self.metadata_file)

    def _ensure_index(self) -> None:
        with sqlite3.connect(self.index_file) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    knowledge_base_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    embedding_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_kb ON chunks(knowledge_base_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)"
            )
            conn.commit()

    def _knowledge_base_status(self, knowledge_base_id: str) -> str:
        documents = [
            item
            for item in self._state["documents"]
            if item["knowledge_base_id"] == knowledge_base_id
        ]
        if any(item.get("status") == "processing" for item in documents):
            return "processing"
        if any(item.get("status") == "failed" for item in documents):
            return "failed"
        return "ready"

    def _hydrate_knowledge_base(self, item: dict[str, Any]) -> KnowledgeBaseRecord:
        payload = dict(item)
        payload["status"] = self._knowledge_base_status(item["id"])
        return KnowledgeBaseRecord(**payload)

    def _update_document_record(self, document_id: str, **updates: Any) -> KnowledgeDocumentRecord:
        now = utc_now_iso()
        for item in self._state["documents"]:
            if item["id"] != document_id:
                continue
            item.update(updates)
            item["updated_at"] = now
            return KnowledgeDocumentRecord(**item)
        raise KeyError(f"Knowledge document not found: {document_id}")

    def create_knowledge_base(
        self,
        name: str,
        description: str,
        *,
        type: str = "rag",
        language: str = "zh",
    ) -> KnowledgeBaseRecord:
        from tokenmind.knowledge.wiki_paths import ensure_wiki_structure, get_kb_root

        if type not in ("rag", "wiki"):
            raise ValueError(f"invalid kb type: {type}")
        with self._state_lock:
            self._reload()
            now = utc_now_iso()
            kb_id = f"kb_{uuid.uuid4().hex[:10]}"
            root_path = ""
            if type == "wiki":
                kb_root = get_kb_root(self.root.parent, kb_id)
                ensure_wiki_structure(
                    kb_root, name=name, description=description, language=language
                )
                root_path = str(kb_root)
            record = KnowledgeBaseRecord(
                id=kb_id,
                name=name,
                description=description,
                type=type,
                language=language,
                root_path=root_path,
                created_at=now,
                updated_at=now,
            )
            self._state["knowledge_bases"].append(record.model_dump())
            self._save()
            return record

    def update_knowledge_base(
        self,
        knowledge_base_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> KnowledgeBaseRecord:
        with self._state_lock:
            self._reload()
            now = utc_now_iso()
            updated: KnowledgeBaseRecord | None = None
            for item in self._state["knowledge_bases"]:
                if item["id"] != knowledge_base_id:
                    continue
                if name is not None:
                    item["name"] = name
                if description is not None:
                    item["description"] = description
                if enabled is not None:
                    item["enabled"] = enabled
                item["updated_at"] = now
                updated = self._hydrate_knowledge_base(item)
                break
            if updated is None:
                raise KeyError(f"Knowledge base not found: {knowledge_base_id}")

            if enabled is False:
                for session_id, linked_ids in list(self._state["session_links"].items()):
                    filtered_ids = [linked_id for linked_id in linked_ids if linked_id != knowledge_base_id]
                    self._state["session_links"][session_id] = filtered_ids

            self._save()
            return updated

    def delete_knowledge_base(self, knowledge_base_id: str, *, session_manager=None) -> dict[str, Any]:
        documents = self.list_documents(knowledge_base_id)
        for document in documents:
            self.delete_document(knowledge_base_id, document.id)

        target_dir = self.root / knowledge_base_id
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        with self._state_lock:
            self._reload()
            before_count = len(self._state["knowledge_bases"])
            self._state["knowledge_bases"] = [
                item for item in self._state["knowledge_bases"] if item["id"] != knowledge_base_id
            ]
            if len(self._state["knowledge_bases"]) == before_count:
                raise KeyError(f"Knowledge base not found: {knowledge_base_id}")

            cleaned_session_links: dict[str, list[str]] = {}
            for session_id, linked_ids in self._state["session_links"].items():
                filtered = [linked_id for linked_id in linked_ids if linked_id != knowledge_base_id]
                if filtered:
                    cleaned_session_links[session_id] = filtered
            self._state["session_links"] = cleaned_session_links
            self._save()

        # Cascade: clear any session that had this KB as its active wiki KB.
        if session_manager is not None:
            for summary in session_manager.list_sessions():
                key = summary.get("key") if isinstance(summary, dict) else getattr(summary, "key", None)
                if not key:
                    continue
                session = session_manager.get_or_create(key)
                if session.active_wiki_kb_id == knowledge_base_id:
                    session.set_active_wiki_kb_id(None)
                    session_manager.save(session)

        return {
            "success": True,
            "knowledge_base_id": knowledge_base_id,
        }

    def list_knowledge_bases(self) -> list[KnowledgeBaseRecord]:
        with self._state_lock:
            self._reload()
            return [self._hydrate_knowledge_base(item) for item in self._state["knowledge_bases"]]

    def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseRecord:
        with self._state_lock:
            self._reload()
            for item in self._state["knowledge_bases"]:
                if item["id"] == knowledge_base_id:
                    return self._hydrate_knowledge_base(item)
            raise KeyError(f"Knowledge base not found: {knowledge_base_id}")

    def _update_knowledge_base_counts(self, knowledge_base_id: str) -> None:
        count = len(
            [item for item in self._state["documents"] if item["knowledge_base_id"] == knowledge_base_id]
        )
        now = utc_now_iso()
        for item in self._state["knowledge_bases"]:
            if item["id"] == knowledge_base_id:
                item["document_count"] = count
                item["updated_at"] = now
                if item.get("type") == "wiki":
                    cache_path = Path(item.get("root_path") or "") / ".wiki-cache.json"
                    if cache_path.is_file():
                        try:
                            cache = json.loads(cache_path.read_text(encoding="utf-8"))
                            item["source_count"] = len(cache.get("sources", {}))
                            item["page_count"] = len(cache.get("pages", {}))
                        except Exception:
                            pass
                break

    def set_session_links(self, session_id: str, knowledge_base_ids: list[str]) -> None:
        with self._state_lock:
            self._reload()
            enabled_ids = {
                item["id"]
                for item in self._state["knowledge_bases"]
                if item.get("enabled", True)
            }
            payload = SessionKnowledgeLinks(
                session_id=session_id,
                knowledge_base_ids=[knowledge_base_id for knowledge_base_id in knowledge_base_ids if knowledge_base_id in enabled_ids],
            )
            self._state["session_links"][session_id] = payload.knowledge_base_ids
            self._save()

    def get_session_links(self, session_id: str) -> list[str]:
        with self._state_lock:
            self._reload()
            enabled_ids = {
                item["id"]
                for item in self._state["knowledge_bases"]
                if item.get("enabled", True)
            }
            return [
                knowledge_base_id
                for knowledge_base_id in self._state["session_links"].get(session_id, [])
                if knowledge_base_id in enabled_ids
            ]

    @property
    def embeddings_enabled(self) -> bool:
        return bool(self.embedding_model)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        tokens = [token.lower() for token in ASCII_TOKEN_PATTERN.findall(text)]
        for block in CJK_TOKEN_PATTERN.findall(text):
            clean = block.strip()
            if not clean:
                continue
            if len(clean) <= 2:
                tokens.append(clean)
                continue
            tokens.extend(clean[index : index + 2] for index in range(len(clean) - 1))
        return tokens

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        numerator = sum(left * right for left, right in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(value * value for value in a))
        norm_b = math.sqrt(sum(value * value for value in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return numerator / (norm_a * norm_b)

    @classmethod
    def _lexical_score(cls, query: str, content: str) -> float:
        query_tokens = cls._tokenize(query)
        if not query_tokens:
            return 0.0
        content_tokens = cls._tokenize(content)
        if not content_tokens:
            return 0.0
        content_counts: dict[str, int] = {}
        for token in content_tokens:
            content_counts[token] = content_counts.get(token, 0) + 1
        overlap = sum(min(content_counts.get(token, 0), 2) for token in query_tokens)
        if overlap == 0:
            return 0.0
        coverage = overlap / max(1, len(set(query_tokens)))
        density = overlap / max(8, len(content_tokens))
        return coverage * 0.8 + density * 0.2

    def _embedding_client(self) -> OpenAI | None:
        if not self.embeddings_enabled:
            return None
        try:
            kwargs: dict[str, Any] = {
                "api_key": self.embedding_api_key or "tokenmind-local",
            }
            if self.embedding_api_base:
                kwargs["base_url"] = self.embedding_api_base
            return OpenAI(**kwargs)
        except Exception:
            logger.exception("Failed to initialize embedding client")
            return None

    @property
    def rerank_enabled(self) -> bool:
        return bool(self.rerank_model)

    def _rerank_client(self) -> OpenAI | None:
        if not self.rerank_enabled:
            return None
        try:
            kwargs: dict[str, Any] = {
                "api_key": self.rerank_api_key or self.embedding_api_key or "tokenmind-local",
            }
            if self.rerank_api_base:
                kwargs["base_url"] = self.rerank_api_base
            return OpenAI(**kwargs)
        except Exception:
            logger.exception("Failed to initialize rerank client")
            return None

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts or not self.embeddings_enabled:
            return [[] for _ in texts]
        client = self._embedding_client()
        if client is None:
            return [[] for _ in texts]
        try:
            response = client.embeddings.create(model=self.embedding_model, input=texts)
            return [list(item.embedding) for item in response.data]
        except Exception:
            logger.exception("Failed to generate embeddings for knowledge chunks")
            return [[] for _ in texts]

    def _qdrant_client(self):
        if self.vector_backend != "qdrant":
            return None
        try:
            from qdrant_client import QdrantClient

            storage_path = self.root / "qdrant"
            storage_path.mkdir(parents=True, exist_ok=True)
            return QdrantClient(path=str(storage_path))
        except Exception:
            logger.exception("Failed to initialize Qdrant local client; falling back to sqlite retrieval")
            return None

    def _ensure_qdrant_collection(self, vector_size: int) -> None:
        client = self._qdrant_client()
        if client is None or vector_size <= 0:
            return
        try:
            from qdrant_client.models import Distance, VectorParams

            collections = client.get_collections().collections
            if any(collection.name == self.collection_name for collection in collections):
                return
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        except Exception:
            logger.exception("Failed to ensure Qdrant collection")

    def _upsert_qdrant_records(self, records: list[KnowledgeChunkRecord]) -> None:
        if not records:
            return
        vectors = [record.embedding for record in records if record.embedding]
        if not vectors:
            return
        client = self._qdrant_client()
        if client is None:
            return
        self._ensure_qdrant_collection(len(vectors[0]))
        try:
            from qdrant_client.models import PointStruct

            points = [
                PointStruct(
                    id=record.id,
                    vector=record.embedding,
                    payload={
                        "document_id": record.document_id,
                        "knowledge_base_id": record.knowledge_base_id,
                        "ordinal": record.ordinal,
                        "content": record.content,
                        "token_count": record.token_count,
                    },
                )
                for record in records
                if record.embedding
            ]
            if points:
                client.upsert(collection_name=self.collection_name, points=points)
        except Exception:
            logger.exception("Failed to upsert knowledge vectors into Qdrant")

    def _delete_qdrant_points(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        client = self._qdrant_client()
        if client is None:
            return
        try:
            from qdrant_client.models import PointIdsList

            client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=chunk_ids),
            )
        except Exception:
            logger.exception("Failed to delete knowledge vectors from Qdrant")

    def _qdrant_hits(self, knowledge_base_ids: list[str], query_embedding: list[float], limit: int) -> list[dict[str, Any]]:
        if not knowledge_base_ids or not query_embedding:
            return []
        client = self._qdrant_client()
        if client is None:
            return []
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchAny

            points = client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="knowledge_base_id",
                            match=MatchAny(any=knowledge_base_ids),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
            )
        except Exception:
            logger.exception("Failed to retrieve knowledge vectors from Qdrant")
            return []

        results: list[dict[str, Any]] = []
        for point in points:
            payload = point.payload or {}
            results.append(
                {
                    "id": str(point.id),
                    "document_id": payload.get("document_id", ""),
                    "knowledge_base_id": payload.get("knowledge_base_id", ""),
                    "ordinal": payload.get("ordinal", 0),
                    "content": payload.get("content", ""),
                    "token_count": payload.get("token_count", 0),
                    "vector_score": float(point.score or 0.0),
                }
            )
        return results

    def _rerank_hits(self, query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.rerank_enabled or len(hits) < 2:
            return hits
        client = self._rerank_client()
        if client is None:
            return hits

        candidates = hits[: max(self.rerank_top_n, len(hits))]
        docs_text = "\n\n".join(
            f"[{index}] {item['knowledge_base_name']} / {item['document_name']}\n{item['content'][:700]}"
            for index, item in enumerate(candidates)
        )
        try:
            response = client.chat.completions.create(
                model=self.rerank_model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You rerank retrieved knowledge chunks for relevance. "
                            "Return strict JSON only: {\"ranking\":[{\"index\":0,\"score\":1.0}]}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Query: {query}\n\nCandidates:\n{docs_text}\n\n"
                            "Return the candidate indexes sorted by relevance. "
                            "Use score between 0 and 1."
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content or "{\"ranking\":[]}"
            payload = json_repair.loads(content)
            ranking = payload.get("ranking", [])
            rescored: list[dict[str, Any]] = []
            used_indexes: set[int] = set()
            for item in ranking:
                try:
                    index = int(item.get("index"))
                except Exception:
                    continue
                if index < 0 or index >= len(candidates) or index in used_indexes:
                    continue
                used_indexes.add(index)
                score = float(item.get("score", 0.0))
                rescored.append({**candidates[index], "score": score + candidates[index]["score"]})
            rescored.extend(candidates[index] for index in range(len(candidates)) if index not in used_indexes)
            return rescored + hits[len(candidates) :]
        except Exception:
            logger.exception("Failed to rerank knowledge hits")
            return hits

    @staticmethod
    def _normalize_positive_scores(values: list[float]) -> list[float]:
        positives = [value for value in values if value > 0]
        if not positives:
            return [0.0 for _ in values]
        ceiling = max(positives)
        if ceiling <= 0:
            return [0.0 for _ in values]
        return [max(0.0, value) / ceiling for value in values]

    def _fuse_retrieval_scores(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not hits:
            return []

        lexical_values = [float(hit.get("lexical_score", 0.0) or 0.0) for hit in hits]
        vector_values = [float(hit.get("vector_score", 0.0) or 0.0) for hit in hits]
        lexical_norm = self._normalize_positive_scores(lexical_values)
        vector_norm = self._normalize_positive_scores(vector_values)

        fused: list[dict[str, Any]] = []
        for hit, lexical_signal, vector_signal in zip(
            hits, lexical_norm, vector_norm, strict=False
        ):
            agreement = math.sqrt(lexical_signal * vector_signal) if lexical_signal and vector_signal else 0.0
            fused_score = (
                lexical_signal * 0.25
                + vector_signal * 0.35
                + agreement * 0.4
            )
            fused.append(
                {
                    **hit,
                    "score": round(fused_score, 6),
                    "lexical_score": round(float(hit.get("lexical_score", 0.0) or 0.0), 6),
                    "vector_score": round(float(hit.get("vector_score", 0.0) or 0.0), 6),
                }
            )

        fused.sort(
            key=lambda item: (
                item["score"],
                item.get("vector_score", 0.0),
                item.get("lexical_score", 0.0),
            ),
            reverse=True,
        )
        return fused

    def _store_chunks(
        self,
        knowledge_base_id: str,
        document_id: str,
        chunks: list[str],
        embeddings: list[list[float]] | None = None,
    ) -> int:
        embeddings = embeddings or [[] for _ in chunks]
        records = [
            KnowledgeChunkRecord(
                id=f"chunk_{uuid.uuid4().hex[:12]}",
                document_id=document_id,
                knowledge_base_id=knowledge_base_id,
                ordinal=index,
                content=chunk,
                token_count=max(1, len(chunk.split())),
                embedding=embeddings[index] if index < len(embeddings) else [],
            )
            for index, chunk in enumerate(chunks)
        ]
        with sqlite3.connect(self.index_file) as conn:
            conn.executemany(
                """
                INSERT INTO chunks (
                    id, document_id, knowledge_base_id, ordinal, content,
                    token_count, embedding_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.id,
                        record.document_id,
                        record.knowledge_base_id,
                        record.ordinal,
                        record.content,
                        record.token_count,
                        json.dumps(record.embedding),
                        record.created_at,
                    )
                    for record in records
                ],
            )
            conn.commit()
        if self.vector_backend == "qdrant":
            self._upsert_qdrant_records(records)
        return len(records)

    def _extract_pdf_text(self, path: Path) -> str:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text.strip())
        return "\n\n".join(parts)

    @staticmethod
    def _extract_zip_xml_text(path: Path, members: list[str]) -> str:
        chunks: list[str] = []
        with ZipFile(path) as archive:
            for member in members:
                if member not in archive.namelist():
                    continue
                with archive.open(member) as handle:
                    root = ET.fromstring(handle.read())
                texts = [text.strip() for text in root.itertext() if text and text.strip()]
                if texts:
                    chunks.append("\n".join(texts))
        return "\n\n".join(chunks)

    def _extract_docx_text(self, path: Path) -> str:
        return self._extract_zip_xml_text(path, ["word/document.xml"])

    def _extract_pptx_text(self, path: Path) -> str:
        with ZipFile(path) as archive:
            slide_members = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide"))
        return self._extract_zip_xml_text(path, slide_members)

    def _extract_xlsx_text(self, path: Path) -> str:
        with ZipFile(path) as archive:
            members = ["xl/sharedStrings.xml"] + sorted(
                name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")
            )
        return self._extract_zip_xml_text(path, members)

    def _extract_text(self, path: Path) -> str:
        suffix = path.suffix.lower()
        try:
            if suffix in TEXT_SUFFIXES:
                return path.read_text(encoding="utf-8", errors="ignore")
            if suffix == ".pdf":
                return self._extract_pdf_text(path)
            if suffix == ".docx":
                return self._extract_docx_text(path)
            if suffix in {".pptx", ".ppt"}:
                return self._extract_pptx_text(path)
            if suffix in {".xlsx", ".xls"}:
                return self._extract_xlsx_text(path)
        except Exception:
            # Fall back to a best-effort text decode so documents still register.
            pass

        return path.read_text(encoding="utf-8", errors="ignore")

    def _prepare_document_target(self, knowledge_base_id: str, original_name: str, source: Path) -> tuple[Path, str]:
        target_dir = self.root / knowledge_base_id / "documents"
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_name = safe_filename(original_name or source.name or "upload.bin")
        target = target_dir / safe_name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            target = target_dir / f"{stem}-{uuid.uuid4().hex[:6]}{suffix}"
        return target, safe_name

    def register_document_upload(
        self,
        knowledge_base_id: str,
        source: Path,
        original_name: str,
    ) -> KnowledgeDocumentRecord:
        kb = self.get_knowledge_base(knowledge_base_id)
        if kb.type == "wiki":
            return self._wiki_register_source(kb, source, original_name)
        return self._rag_register_document(knowledge_base_id, source, original_name)

    def _rag_register_document(
        self,
        knowledge_base_id: str,
        source: Path,
        original_name: str,
    ) -> KnowledgeDocumentRecord:
        with self._state_lock:
            self._reload()
            target, safe_name = self._prepare_document_target(knowledge_base_id, original_name, source)
            shutil.copy2(source, target)
            now = utc_now_iso()
            document = KnowledgeDocumentRecord(
                id=f"doc_{uuid.uuid4().hex[:10]}",
                knowledge_base_id=knowledge_base_id,
                name=original_name or safe_name,
                path=str(target),
                file_type=target.suffix.lower().lstrip("."),
                size=target.stat().st_size,
                status="processing",
                processing_stage="queued",
                processing_progress=5,
                chunk_count=0,
                created_at=now,
                updated_at=now,
            )
            self._state["documents"].append(document.model_dump())
            self._update_knowledge_base_counts(knowledge_base_id)
            self._save()
            return document

    def _wiki_register_source(
        self,
        kb: KnowledgeBaseRecord,
        source: Path,
        original_name: str,
    ) -> KnowledgeDocumentRecord:
        import hashlib

        from tokenmind.knowledge.wiki_paths import get_kb_root, safe_wiki_filename

        kb_root = Path(kb.root_path or get_kb_root(self.root.parent, kb.id))
        raw_dir = kb_root / "raw" / "files"
        raw_dir.mkdir(parents=True, exist_ok=True)
        sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        safe_name = safe_wiki_filename(Path(original_name).stem) + Path(original_name).suffix
        target = raw_dir / safe_name
        if target.exists():
            target = raw_dir / f"{Path(safe_name).stem}-{uuid.uuid4().hex[:6]}{Path(safe_name).suffix}"
        shutil.copy2(source, target)
        now = utc_now_iso()

        document = KnowledgeDocumentRecord(
            id=f"doc_{uuid.uuid4().hex[:10]}",
            knowledge_base_id=kb.id,
            name=original_name or safe_name,
            path=str(target),
            file_type=target.suffix.lower().lstrip("."),
            size=target.stat().st_size,
            status="processing",
            processing_stage="queued",
            processing_progress=5,
            chunk_count=0,
            created_at=now,
            updated_at=now,
        )
        with self._state_lock:
            self._reload()
            self._state["documents"].append(document.model_dump())
            self._update_wiki_cache(kb_root, sha256=sha256, document=document)
            self._update_knowledge_base_counts(kb.id)
            self._save()
        return document

    def _update_wiki_cache(
        self,
        kb_root: Path,
        *,
        sha256: str,
        document: KnowledgeDocumentRecord,
    ) -> None:
        import json

        cache_path = kb_root / ".wiki-cache.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache["sources"][f"sha256:{sha256}"] = {
            "document_id": document.id,
            "title": document.name,
            "raw_path": str(Path(document.path).relative_to(kb_root)),
            "status": "registered",
            "created_at": document.created_at,
        }
        cache["updated_at"] = utc_now_iso()
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def process_document(self, document_id: str) -> KnowledgeDocumentRecord:
        with self._state_lock:
            self._reload()
            existing = next((item for item in self._state["documents"] if item["id"] == document_id), None)
            if existing is None:
                raise KeyError(f"Knowledge document not found: {document_id}")
            kb_id = str(existing["knowledge_base_id"])
        kb = self.get_knowledge_base(kb_id)
        if kb.type == "wiki":
            return self._wiki_process_document(kb, document_id)
        return self._rag_process_document(document_id)

    def _wiki_process_document(
        self, kb: KnowledgeBaseRecord, document_id: str
    ) -> KnowledgeDocumentRecord:
        from tokenmind.knowledge.wiki_extractors import extract_text
        from tokenmind.knowledge.wiki_ingest import compile_source_page_template
        from tokenmind.knowledge.wiki_paths import safe_wiki_filename

        def save_state(**updates: Any) -> KnowledgeDocumentRecord:
            with self._state_lock:
                self._reload()
                updated = self._update_document_record(document_id, **updates)
                self._update_knowledge_base_counts(kb.id)
                self._save()
                return updated

        with self._state_lock:
            self._reload()
            doc = next(item for item in self._state["documents"] if item["id"] == document_id)
            path = Path(str(doc["path"]))
            doc_name = doc.get("name") or path.stem

        if not path.exists():
            return save_state(
                status="failed",
                processing_stage="failed",
                error_message="Source file is missing",
            )

        save_state(
            status="processing",
            processing_stage="extracting",
            processing_progress=25,
            error_message=None,
        )
        try:
            text = extract_text(path)
        except Exception as exc:
            logger.exception("Failed to extract wiki document {}", document_id)
            return save_state(
                status="failed",
                processing_stage="failed",
                error_message=str(exc),
            )

        save_state(processing_stage="compiling_source", processing_progress=70)
        kb_root = Path(kb.root_path)
        try:
            raw_rel = str(path.relative_to(kb_root))
        except ValueError:
            raw_rel = str(path)
        page_id = f"page_{uuid.uuid4().hex[:10]}"
        title = doc_name
        safe_name = safe_wiki_filename(Path(title).stem) + ".md"

        cache_path = kb_root / ".wiki-cache.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        sha = ""
        for key, entry in cache.get("sources", {}).items():
            if entry.get("document_id") == document_id:
                sha = key.split(":", 1)[1] if ":" in key else ""
                break

        page_md = compile_source_page_template(
            page_id=page_id,
            source_id=document_id,
            title=title,
            raw_path=raw_rel,
            sha256=sha,
            body_text=text,
        )
        page_path = kb_root / "wiki" / "sources" / safe_name
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(page_md, encoding="utf-8")

        sources_map = cache.setdefault("sources", {})
        sha_key = f"sha256:{sha}"
        sources_map.setdefault(sha_key, {})
        sources_map[sha_key]["status"] = "ready"
        sources_map[sha_key]["source_page_id"] = page_id
        cache.setdefault("pages", {})[page_id] = {
            "path": f"wiki/sources/{safe_name}",
            "type": "source",
            "title": title,
            "source_id": document_id,
        }
        cache["updated_at"] = utc_now_iso()
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if self._wiki_llm_provider is not None and self._wiki_llm_model:
            try:
                import asyncio
                coro = compile_with_llm(
                    provider=self._wiki_llm_provider,
                    model=self._wiki_llm_model,
                    kb_root=kb_root,
                    source_title=title,
                    source_text=text,
                    source_page_id=page_id,
                    language=getattr(kb, "language", "zh"),
                )
                # Create a fresh loop. If called from inside a running loop,
                # this still works because we're on a sync method invoked from
                # an executor / sync context. asyncio.run() would error inside
                # an already-running loop; new_event_loop + run_until_complete
                # avoids that.
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(coro)
                finally:
                    loop.close()
            except Exception as exc:
                logger.warning(f"wiki LLM compile failed: {exc}")

        try:
            build_graph_data(kb_root, persist=True)
        except Exception as exc:
            logger.warning(f"wiki graph rebuild failed: {exc}")

        return save_state(
            status="ready",
            processing_stage="ready",
            processing_progress=100,
            error_message=None,
        )

    def _rag_process_document(self, document_id: str) -> KnowledgeDocumentRecord:
        with self._state_lock:
            self._reload()
            existing = next((item for item in self._state["documents"] if item["id"] == document_id), None)
            if existing is None:
                raise KeyError(f"Knowledge document not found: {document_id}")
            knowledge_base_id = str(existing["knowledge_base_id"])
            path = Path(str(existing["path"]))

        def save_state(**updates: Any) -> KnowledgeDocumentRecord:
            with self._state_lock:
                self._reload()
                updated = self._update_document_record(document_id, **updates)
                self._update_knowledge_base_counts(knowledge_base_id)
                self._save()
                return updated

        if not path.exists():
            return save_state(
                status="failed",
                processing_stage="failed",
                error_message="Source file is missing",
            )

        try:
            save_state(
                status="processing",
                processing_stage="extracting",
                processing_progress=20,
                error_message=None,
            )
            text = self._extract_text(path)

            save_state(
                processing_stage="chunking",
                processing_progress=55,
            )
            if self.embeddings_enabled:
                chunks = semantic_chunks(
                    text,
                    self._embed_texts,
                    size=self.chunk_size,
                    overlap=self.chunk_overlap,
                )
            else:
                chunks = simple_chunks(text, size=self.chunk_size, overlap=self.chunk_overlap)

            embeddings: list[list[float]] = []
            if chunks and self.embeddings_enabled:
                save_state(
                    processing_stage="embedding",
                    processing_progress=78,
                )
                embeddings = self._embed_texts(chunks)

            save_state(
                processing_stage="indexing",
                processing_progress=92,
            )
            with sqlite3.connect(self.index_file) as conn:
                conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
                conn.commit()
            chunk_count = self._store_chunks(
                knowledge_base_id,
                document_id=document_id,
                chunks=chunks,
                embeddings=embeddings,
            )

            return save_state(
                status="ready",
                processing_stage="ready",
                processing_progress=100,
                error_message=None,
                chunk_count=chunk_count,
            )
        except Exception as exc:
            logger.exception("Failed to ingest knowledge document {}", document_id)
            return save_state(
                status="failed",
                processing_stage="failed",
                error_message=str(exc),
            )

    def add_document(self, knowledge_base_id: str, source: Path, original_name: str) -> KnowledgeDocumentRecord:
        document = self.register_document_upload(knowledge_base_id, source, original_name)
        return self.process_document(document.id)

    def list_documents(self, knowledge_base_id: str) -> list[KnowledgeDocumentRecord]:
        with self._state_lock:
            self._reload()
            return [
                KnowledgeDocumentRecord(**item)
                for item in self._state["documents"]
                if item["knowledge_base_id"] == knowledge_base_id
            ]

    def get_document(self, knowledge_base_id: str, document_id: str) -> KnowledgeDocumentRecord:
        with self._state_lock:
            self._reload()
            for item in self._state["documents"]:
                if item["knowledge_base_id"] == knowledge_base_id and item["id"] == document_id:
                    return KnowledgeDocumentRecord(**item)
            raise KeyError(f"Knowledge document not found: {document_id}")

    def delete_document(self, knowledge_base_id: str, document_id: str) -> Any:
        kb = self.get_knowledge_base(knowledge_base_id)
        if kb.type == "wiki":
            return self._wiki_delete_document(kb, document_id)
        return self._rag_delete_document(knowledge_base_id, document_id)

    def _rag_delete_document(self, knowledge_base_id: str, document_id: str) -> None:
        document = self.get_document(knowledge_base_id, document_id)
        path = Path(document.path)
        if path.exists():
            path.unlink()

        with sqlite3.connect(self.index_file) as conn:
            chunk_ids = [
                row[0]
                for row in conn.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,)).fetchall()
            ]

        with self._state_lock:
            self._reload()
            self._state["documents"] = [
                item
                for item in self._state["documents"]
                if not (item["knowledge_base_id"] == knowledge_base_id and item["id"] == document_id)
            ]
            with sqlite3.connect(self.index_file) as conn:
                conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
                conn.commit()
            self._delete_qdrant_points(chunk_ids)

            self._update_knowledge_base_counts(knowledge_base_id)
            self._save()

    def _wiki_delete_document(self, kb: KnowledgeBaseRecord, document_id: str) -> dict[str, Any]:
        kb_root = Path(kb.root_path)
        cache_path = kb_root / ".wiki-cache.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

        source_page_id = None
        cache_key_to_remove = None
        for key, entry in cache.get("sources", {}).items():
            if entry.get("document_id") == document_id:
                source_page_id = entry.get("source_page_id")
                cache_key_to_remove = key
                break

        with self._state_lock:
            self._reload()
            doc = next((d for d in self._state["documents"] if d["id"] == document_id), None)
            if doc is None:
                raise KeyError(f"document not found: {document_id}")
            raw_path = Path(doc["path"])
            if raw_path.exists():
                raw_path.unlink()
            self._state["documents"] = [d for d in self._state["documents"] if d["id"] != document_id]
            self._update_knowledge_base_counts(kb.id)
            self._save()

        if source_page_id and source_page_id in cache.get("pages", {}):
            page_rel = cache["pages"][source_page_id]["path"]
            page_path = kb_root / page_rel
            if page_path.exists():
                page_path.unlink()
            del cache["pages"][source_page_id]
        if cache_key_to_remove:
            del cache["sources"][cache_key_to_remove]
        cache["updated_at"] = utc_now_iso()
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

        try:
            build_graph_data(kb_root, persist=True)
        except Exception as exc:
            logger.warning(f"graph rebuild after delete failed: {exc}")

        return {"success": True, "document_id": document_id}

    def retrieve_for_session(
        self,
        session_id: str,
        query: str,
        *,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        all_linked_ids = self.get_session_links(session_id)
        # Wiki KBs are not auto-retrieved; they're accessed via tools (wiki_*) when active.
        with self._state_lock:
            self._reload()
            rag_kb_ids = {
                item["id"]
                for item in self._state["knowledge_bases"]
                if item["id"] in all_linked_ids and item.get("type", "rag") == "rag"
            }
        linked_ids = [k for k in all_linked_ids if k in rag_kb_ids]
        if not linked_ids or not query.strip():
            return []

        limit = top_k or self.top_k
        placeholders = ", ".join("?" for _ in linked_ids)
        with self._state_lock:
            self._reload()
            documents = {
                item["id"]: item
                for item in self._state["documents"]
                if item["knowledge_base_id"] in linked_ids and item.get("status") == "ready"
            }
            knowledge_bases = {
                item["id"]: item
                for item in self._state["knowledge_bases"]
                if item["id"] in linked_ids
            }
        if not documents:
            return []
        document_ids = list(documents.keys())
        document_placeholders = ", ".join("?" for _ in document_ids)

        with sqlite3.connect(self.index_file) as conn:
            rows = conn.execute(
                f"""
                SELECT id, document_id, knowledge_base_id, ordinal, content, token_count, embedding_json
                FROM chunks
                WHERE knowledge_base_id IN ({placeholders})
                  AND document_id IN ({document_placeholders})
                """,
                [*linked_ids, *document_ids],
            ).fetchall()

        query_embedding = self._embed_texts([query])[0] if self.embeddings_enabled else []
        vector_hits_by_id = {
            hit["id"]: hit
            for hit in self._qdrant_hits(linked_ids, query_embedding, max(limit * 3, self.rerank_top_n))
        }
        scored: list[dict[str, Any]] = []
        for chunk_id, document_id, knowledge_base_id, ordinal, content, token_count, embedding_json in rows:
            lexical = self._lexical_score(query, content)
            vector_hit = vector_hits_by_id.get(chunk_id)
            vector = float(vector_hit["vector_score"]) if vector_hit else 0.0
            if not vector and query_embedding and embedding_json:
                try:
                    vector = self._cosine_similarity(query_embedding, json.loads(embedding_json))
                except Exception:
                    vector = 0.0
            if lexical <= 0 and vector <= 0:
                continue
            document = documents.get(document_id, {})
            knowledge_base = knowledge_bases.get(knowledge_base_id, {})
            score = lexical * 0.7 + max(0.0, vector) * 0.3
            scored.append({
                "id": chunk_id,
                "document_id": document_id,
                "document_name": document.get("name", ""),
                "knowledge_base_id": knowledge_base_id,
                "knowledge_base_name": knowledge_base.get("name", ""),
                "ordinal": ordinal,
                "content": content,
                "token_count": token_count,
                "lexical_score": lexical,
                "vector_score": vector,
                "score": round(score, 6),
            })

        fused = self._fuse_retrieval_scores(scored)
        return self._rerank_hits(query, fused[: max(limit * 3, self.rerank_top_n)])[:limit]

    def get_knowledge_overview(self) -> dict[str, list[dict]]:
        return {
            "items": [item.model_dump() for item in self.list_knowledge_bases()],
        }

    def get_knowledge_base_detail(self, knowledge_base_id: str) -> dict[str, dict | list[dict]]:
        knowledge_base = self.get_knowledge_base(knowledge_base_id)
        return {
            "knowledge_base": knowledge_base.model_dump(),
            "documents": [item.model_dump() for item in self.list_documents(knowledge_base_id)],
        }
