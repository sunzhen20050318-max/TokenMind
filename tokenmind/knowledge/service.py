from __future__ import annotations

import json
import math
import re
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json_repair
from loguru import logger
from openai import OpenAI

from tokenmind.knowledge.chunking import semantic_chunks, simple_chunks
from tokenmind.knowledge.models import (
    KnowledgeBaseRecord,
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    SessionKnowledgeLinks,
    utc_now_iso,
)
from tokenmind.knowledge.wiki_graph import build_graph_data
# compile_with_llm is the legacy JSON-middleman path; we now drive the LLM
# directly via WikiCompileRunner (imported lazily in _wiki_process_document).
# The legacy function and its tests are kept until Phase C cleanup.
from tokenmind.utils.helpers import safe_filename

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
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
        vlm_model: str = "",
        vlm_api_key: str = "",
        vlm_api_base: str | None = None,
        vlm_timeout: int = 30,
        vlm_max_dim: int = 1280,
        vlm_max_workers: int = 8,
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
        self.vlm_model = vlm_model.strip()
        self.vlm_api_key = vlm_api_key.strip()
        self.vlm_api_base = vlm_api_base.strip() if vlm_api_base else None
        self.vlm_timeout = vlm_timeout
        self.vlm_max_dim = vlm_max_dim
        self.vlm_max_workers = vlm_max_workers
        self.collection_name = "knowledge_chunks"
        self._state_lock = threading.RLock()
        self._state = self._load()
        self._ensure_index()
        self._wiki_llm_provider = None
        self._wiki_llm_model: str | None = None

    def _cascade_cleanup_after_source_removal(
        self, kb_root: Path, deleted_source_page_id: str
    ) -> dict[str, int]:
        """Walk all entity/topic pages and either drop them entirely (if they
        only listed the deleted source) or strip the deleted source's
        contributions (frontmatter `sources:` entry, `## 来源` line, and any
        `## 新增信息(来自 [[deleted_id]] ...)` section).

        Idempotent: safe to call twice; second run is a no-op.
        """
        stats = {"deleted": 0, "updated": 0}
        for sub in ("entities", "topics"):
            d = kb_root / "wiki" / sub
            if not d.is_dir():
                continue
            for page in d.glob("*.md"):
                try:
                    body = page.read_text(encoding="utf-8")
                except OSError:
                    continue
                sources = _parse_frontmatter_sources(body)
                if deleted_source_page_id not in sources:
                    continue
                remaining = [s for s in sources if s != deleted_source_page_id]
                if not remaining:
                    page.unlink()
                    stats["deleted"] += 1
                    continue
                new_body = _strip_source_contributions(
                    body, deleted_source_page_id, remaining
                )
                page.write_text(new_body, encoding="utf-8")
                stats["updated"] += 1
        return stats

    def _wiki_cache_hit(self, kb_root: Path, document_id: str) -> str | None:
        """Return the source-page relative path if this document's SHA has a
        compiled cache entry whose page file still exists. None otherwise.

        Used by _wiki_process_document to skip the LLM compile for unchanged
        re-uploads. Matches by document_id → SHA → cache entry chain so the
        same content uploaded twice resolves to the same cached compile.
        """
        cache_path = kb_root / ".wiki-cache.json"
        if not cache_path.is_file():
            return None
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        for entry in cache.get("sources", {}).values():
            if entry.get("document_id") != document_id:
                continue
            if not entry.get("compiled_at"):
                return None
            page_id = entry.get("source_page_id")
            if not page_id:
                return None
            page_info = cache.get("pages", {}).get(page_id)
            if not page_info:
                return None
            page_rel = page_info.get("path")
            if not page_rel:
                return None
            page_abs = kb_root / page_rel
            if page_abs.is_file():
                return page_rel
            return None
        return None

    def refresh_knowledge_base_counts(self, knowledge_base_id: str) -> None:
        """Re-scan the on-disk wiki workspace and update cached counts on the
        KB record. Safe to call any time; used after operations that change
        page/edge totals without going through process_document."""
        with self._state_lock:
            self._reload()
            self._update_knowledge_base_counts(knowledge_base_id)
            self._save()

    def set_wiki_llm(self, provider, model: str) -> None:
        self._wiki_llm_provider = provider
        self._wiki_llm_model = model
        logger.info(
            "wiki LLM wired: provider={} model={}",
            getattr(provider, "provider_name", type(provider).__name__),
            model,
        )

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
        vlm_model: str | None = None,
        vlm_api_key: str | None = None,
        vlm_api_base: str | None = None,
        vlm_timeout: int | None = None,
        vlm_max_dim: int | None = None,
        vlm_max_workers: int | None = None,
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
        if vlm_model is not None:
            self.vlm_model = vlm_model.strip()
        if vlm_api_key is not None:
            self.vlm_api_key = vlm_api_key.strip()
        if vlm_api_base is not None:
            self.vlm_api_base = vlm_api_base.strip() or None
        if vlm_timeout is not None:
            self.vlm_timeout = vlm_timeout
        if vlm_max_dim is not None:
            self.vlm_max_dim = vlm_max_dim
        if vlm_max_workers is not None:
            self.vlm_max_workers = vlm_max_workers

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
        project_id: str | None = None,
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
                project_id=project_id,
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
        if session_manager is not None and hasattr(session_manager, "list_sessions"):
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
                    kb_root = Path(item.get("root_path") or "")
                    cache_path = kb_root / ".wiki-cache.json"
                    if cache_path.is_file():
                        try:
                            cache = json.loads(cache_path.read_text(encoding="utf-8"))
                            item["source_count"] = len(cache.get("sources", {}))
                        except Exception:
                            pass
                    if kb_root.is_dir():
                        entity_dir = kb_root / "wiki" / "entities"
                        topic_dir = kb_root / "wiki" / "topics"
                        source_dir = kb_root / "wiki" / "sources"
                        entity_count = sum(1 for _ in entity_dir.glob("*.md")) if entity_dir.is_dir() else 0
                        topic_count = sum(1 for _ in topic_dir.glob("*.md")) if topic_dir.is_dir() else 0
                        source_pages = sum(1 for _ in source_dir.glob("*.md")) if source_dir.is_dir() else 0
                        item["entity_count"] = entity_count
                        item["topic_count"] = topic_count
                        item["page_count"] = entity_count + topic_count + source_pages
                        graph_path = kb_root / "graph-data.json"
                        if graph_path.is_file():
                            try:
                                graph = json.loads(graph_path.read_text(encoding="utf-8"))
                                item["link_count"] = len(graph.get("edges", []))
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

    def _vlm_config(self) -> "VLMConfig | None":
        from tokenmind.knowledge.parsers import VLMConfig

        if not self.vlm_model or not self.vlm_api_key:
            return None
        return VLMConfig(
            model=self.vlm_model,
            api_key=self.vlm_api_key,
            api_base=self.vlm_api_base,
            timeout=self.vlm_timeout,
            max_dim=self.vlm_max_dim,
            max_workers=self.vlm_max_workers,
        )

    def _extract_text(self, path: Path) -> str:
        from tokenmind.knowledge.parsers import (
            LegacyOfficeConversionError,
            can_parse,
            extract_document_text,
        )

        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            return path.read_text(encoding="utf-8", errors="ignore")
        if can_parse(suffix):
            try:
                return extract_document_text(path, vlm=self._vlm_config())
            except LegacyOfficeConversionError:
                # Surface to the caller so the document gets marked failed
                # with a useful "install LibreOffice" message instead of
                # silently being indexed with garbage from the fallback.
                raise
            except Exception:
                logger.exception("Rich parser failed for {} — falling back to text", path)
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

    def register_url_source(
        self,
        knowledge_base_id: str,
        url: str,
    ) -> KnowledgeDocumentRecord:
        """Fetch a URL via the matching adapter (currently: WeChat) and
        register the resulting markdown as a wiki source. Only valid on
        wiki-type knowledge bases."""
        kb = self.get_knowledge_base(knowledge_base_id)
        if kb.type != "wiki":
            raise ValueError("URL sources are only supported for wiki knowledge bases")

        from tokenmind.knowledge.adapters import (
            WechatFetchError,
            fetch_wechat_article,
            is_wechat_url,
        )

        if not is_wechat_url(url):
            raise ValueError(
                "Currently only mp.weixin.qq.com URLs are supported as wiki sources"
            )

        try:
            article = fetch_wechat_article(url)
        except WechatFetchError as exc:
            raise ValueError(f"Failed to fetch WeChat article: {exc}") from exc

        from tokenmind.knowledge.wiki_paths import get_kb_root, safe_wiki_filename

        kb_root = Path(kb.root_path or get_kb_root(self.root.parent, kb.id))
        raw_dir = kb_root / "raw" / "wechat"
        raw_dir.mkdir(parents=True, exist_ok=True)
        date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = safe_wiki_filename(article.title or "wechat-article")[:60].strip("-") or "wechat-article"
        target = raw_dir / f"{date_prefix}-{slug}.md"
        if target.exists():
            target = raw_dir / f"{date_prefix}-{slug}-{uuid.uuid4().hex[:6]}.md"

        # Prepend a tiny header so the editor LLM can see provenance.
        header = (
            f"<!-- source: {url} -->\n"
            f"<!-- fetched_at: {utc_now_iso()} -->\n\n"
        )
        target.write_text(header + article.markdown, encoding="utf-8")

        import hashlib
        sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
        document = KnowledgeDocumentRecord(
            id=f"doc_{uuid.uuid4().hex[:10]}",
            knowledge_base_id=kb.id,
            name=article.title or target.stem,
            path=str(target),
            file_type="md",
            size=target.stat().st_size,
            status="processing",
            processing_stage="queued",
            processing_progress=5,
            chunk_count=0,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        with self._state_lock:
            self._reload()
            self._state["documents"].append(document.model_dump())
            self._update_wiki_cache(kb_root, sha256=sha256, document=document)
            self._update_knowledge_base_counts(kb.id)
            self._save()
        logger.info("registered WeChat article {} → {}", url, target.name)
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

        # Serialize the cache read-modify-write under _state_lock so it can't
        # interleave with the compile/delete paths (which write the same file)
        # and lose entries. RLock → safe even if a caller already holds it.
        cache_path = kb_root / ".wiki-cache.json"
        with self._state_lock:
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

    def process_document(
        self, document_id: str, *, force: bool = False
    ) -> KnowledgeDocumentRecord:
        """Run the ingest pipeline for one document.

        force=False (default): if the document's SHA already has a successful
        source page on disk, skip the LLM compile and reuse the existing
        artifacts. Cheap re-uploads of identical content stay free.
        force=True: always re-run the full pipeline (used by /recompile).
        """
        with self._state_lock:
            self._reload()
            existing = next((item for item in self._state["documents"] if item["id"] == document_id), None)
            if existing is None:
                raise KeyError(f"Knowledge document not found: {document_id}")
            kb_id = str(existing["knowledge_base_id"])
        kb = self.get_knowledge_base(kb_id)
        if kb.type == "wiki":
            return self._wiki_process_document(kb, document_id, force=force)
        return self._rag_process_document(document_id)

    def _wiki_process_document(
        self, kb: KnowledgeBaseRecord, document_id: str, *, force: bool = False
    ) -> KnowledgeDocumentRecord:
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

        # Cache gate: if this document's SHA matches a previously-compiled
        # source whose page still exists on disk, skip the whole pipeline.
        # force=True (e.g. from /recompile) bypasses this.
        if not force:
            cached = self._wiki_cache_hit(Path(kb.root_path), document_id)
            if cached is not None:
                logger.info(
                    "wiki compile cache hit for {}: reusing {}",
                    doc_name,
                    cached,
                )
                return save_state(
                    status="ready",
                    processing_stage="ready",
                    processing_progress=100,
                    error_message=None,
                )

        save_state(
            status="processing",
            processing_stage="extracting",
            processing_progress=25,
            error_message=None,
        )
        try:
            # Route through the shared structured parser so wiki ingestion
            # gets the same docx-table / pptx-slide / xlsx-sheet preservation
            # and optional VLM captioning that the RAG path uses.
            text = self._extract_text(path)
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
        # Cache read-modify-write held under _state_lock (see _update_wiki_cache)
        # so a concurrent registration/delete can't drop this source/page entry.
        # The expensive LLM compile below runs OUTSIDE the lock.
        with self._state_lock:
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

        # Track whether the LLM enrichment actually succeeded. A hard failure
        # must surface as status="failed" (not a silent "ready") AND must not
        # stamp compiled_at — otherwise the cache gate would treat the broken
        # doc as done and never retry it on re-upload/recompile.
        compile_error: str | None = None
        compile_incomplete = False
        if self._wiki_llm_provider is not None and self._wiki_llm_model:
            save_state(
                processing_stage="compiling_with_llm",
                processing_progress=80,
            )
            try:
                import asyncio
                from tokenmind.knowledge.wiki_compile import WikiCompileRunner

                logger.info("wiki LLM compile (runner): starting for {}", title)
                runner = WikiCompileRunner(
                    provider=self._wiki_llm_provider,
                    model=self._wiki_llm_model,
                    kb_root=kb_root,
                    language=getattr(kb, "language", "zh"),
                )
                coro = runner.run(
                    source_title=title,
                    source_text=text,
                    source_page_id=page_id,
                    source_page_path=page_path,
                )
                # Fresh loop: this sync method runs in a worker thread via
                # asyncio.to_thread, so asyncio.run would error.
                loop = asyncio.new_event_loop()
                try:
                    stats = loop.run_until_complete(coro)
                finally:
                    loop.close()
                logger.info(
                    "wiki compile done for {}: {} iterations, {} tool calls ({}), errors={}",
                    title,
                    stats.get("iterations"),
                    stats.get("tool_calls"),
                    stats.get("tool_breakdown"),
                    len(stats.get("errors", [])),
                )
                # Post-check: warn if the LLM left the source page sections empty.
                try:
                    body = page_path.read_text(encoding="utf-8")
                    summary_empty = bool(re.search(r"## 摘要\s*\n\s*##", body))
                    concepts_empty = bool(re.search(r"## 提到的概念\s*$", body))
                    if summary_empty or concepts_empty:
                        compile_incomplete = True
                        logger.warning(
                            "wiki compile finished but source page sections empty for {} "
                            "(summary_empty={}, concepts_empty={})",
                            title,
                            summary_empty,
                            concepts_empty,
                        )
                except OSError:
                    pass
            except Exception as exc:
                compile_error = str(exc)
                logger.warning(f"wiki LLM compile (runner) failed: {exc}")

        try:
            build_graph_data(kb_root, persist=True)
        except Exception as exc:
            logger.warning(f"wiki graph rebuild failed: {exc}")

        # Mark this SHA as compiled so a subsequent re-upload with identical
        # content can hit the cache gate — but ONLY when the compile actually
        # succeeded. Stamping a failed/incomplete compile would cache the broken
        # result and prevent any retry. RMW held under _state_lock (D2).
        if sha and compile_error is None and not compile_incomplete:
            with self._state_lock:
                try:
                    cache = json.loads(cache_path.read_text(encoding="utf-8"))
                    key = f"sha256:{sha}"
                    if key in cache.get("sources", {}):
                        cache["sources"][key]["compiled_at"] = utc_now_iso()
                        cache_path.write_text(
                            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                except Exception as exc:
                    logger.warning(f"failed to mark cache compiled_at: {exc}")

        if compile_error is not None:
            # Source page was written (raw text is on disk), but entity/topic
            # extraction failed — surface it so the user can recompile.
            return save_state(
                status="failed",
                processing_stage="failed",
                processing_progress=100,
                error_message=f"Wiki 编译失败：{compile_error}",
            )

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
        # Hold _state_lock across the whole cache read-modify-write (D2) so a
        # concurrent compile/registration can't lose entries. No long ops here.
        with self._state_lock:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))

            source_page_id = None
            cache_key_to_remove = None
            for key, entry in cache.get("sources", {}).items():
                if entry.get("document_id") == document_id:
                    source_page_id = entry.get("source_page_id")
                    cache_key_to_remove = key
                    break

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

        cascade_stats = {"deleted": 0, "updated": 0}
        if source_page_id:
            cascade_stats = self._cascade_cleanup_after_source_removal(
                kb_root, source_page_id
            )
            if cascade_stats["deleted"] or cascade_stats["updated"]:
                logger.info(
                    "wiki cascade cleanup for {}: deleted={} updated={}",
                    source_page_id,
                    cascade_stats["deleted"],
                    cascade_stats["updated"],
                )

        try:
            build_graph_data(kb_root, persist=True)
        except Exception as exc:
            logger.warning(f"graph rebuild after delete failed: {exc}")

        # Re-scan counts so the popover shows fresh numbers immediately.
        self.refresh_knowledge_base_counts(kb.id)

        return {
            "success": True,
            "document_id": document_id,
            "cascade": cascade_stats,
        }

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
        # Project-owned KBs are managed from their project page and are
        # intentionally excluded from the global knowledge-base list.
        return {
            "items": [
                item.model_dump()
                for item in self.list_knowledge_bases()
                if item.project_id is None
            ],
        }

    def get_knowledge_base_detail(self, knowledge_base_id: str) -> dict[str, dict | list[dict]]:
        knowledge_base = self.get_knowledge_base(knowledge_base_id)
        return {
            "knowledge_base": knowledge_base.model_dump(),
            "documents": [item.model_dump() for item in self.list_documents(knowledge_base_id)],
        }


# ---- module-level helpers for cascade cleanup --------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_SOURCES_BLOCK_RE = re.compile(
    r"^sources:\s*\n((?:[ \t]+- .+\n?)+)",
    re.MULTILINE,
)


def _parse_frontmatter_sources(body: str) -> list[str]:
    """Return the list of page ids listed under `sources:` in the frontmatter,
    or [] if no frontmatter or no sources block."""
    fm_match = _FRONTMATTER_RE.match(body)
    if not fm_match:
        return []
    src_match = _SOURCES_BLOCK_RE.search(fm_match.group(1))
    if not src_match:
        return []
    return [
        line.strip().lstrip("-").strip()
        for line in src_match.group(1).strip().splitlines()
        if line.strip().lstrip("-").strip()
    ]


def _strip_source_contributions(
    body: str, deleted_id: str, remaining_sources: list[str]
) -> str:
    """Surgically remove every trace of `deleted_id` from an entity/topic
    page that still has other sources. Returns the rewritten body.

    Touches:
      - frontmatter `sources:` block (rewritten with remaining ids)
      - `## 来源` list items matching `- [[deleted_id]]`
      - any `## 新增信息(来自 [[deleted_id]] ...)` body section, taken out
        whole (heading + content) until the next `## ` heading or EOF
    """
    new_block = "sources:\n" + "\n".join(f"  - {s}" for s in remaining_sources) + "\n"
    body = _SOURCES_BLOCK_RE.sub(lambda _: new_block, body, count=1)

    # Drop the source list item line in any `## 来源` (or similar) section.
    body = re.sub(
        rf"^- \[\[{re.escape(deleted_id)}\]\]\s*\n",
        "",
        body,
        flags=re.MULTILINE,
    )

    # Strip the `## 新增信息(来自 [[deleted_id]]...)` block, whole. Matches
    # both half-width () and full-width （）parentheses since the LLM is
    # inconsistent. Section ends at the next `## ` heading or end of file.
    section_re = re.compile(
        rf"\n## 新增信息[(（]\s*来自 \[\[{re.escape(deleted_id)}\]\][^\n]*\n"
        r"(?:(?!\n## )[\s\S])*",
        re.MULTILINE,
    )
    body = section_re.sub("", body)

    # Collapse any 3+ consecutive blank lines that the surgery may have left.
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body
