# ── 向量检索服务 ──
# 决策记录：
# - 6 层降级策略加载嵌入模型：本地缓存 → HF 镜像 → 轻量模型
# - BM25 关键词索引持久化到磁盘 pickle，不在 RAM 中常驻
# - 混合检索权重：语义 0.7 + 关键词 0.3
# - Bug 修复: add_documents 中 metadatas 索引原为 len(all_docs)-len(chunks)，
#   上传第二个文件时越界。已改为 enumerate(chunks) 正确索引。

import os
import pickle
import uuid
from typing import List, Dict, Any, Optional, Tuple
from backend.config import settings
from backend.utils.document_parser import DocumentChunk

# Hugging Face 镜像配置（国内用户无法直连 HF）
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
os.environ['TRANSFORMERS_CACHE'] = './backend/data/model_cache'
os.environ['SENTENCE_TRANSFORMERS_HOME'] = './backend/data/model_cache'

MODEL_CACHE_DIR = './backend/data/model_cache'
# BM25 索引持久化路径（存在磁盘，按需加载到内存）
BM25_PERSIST_PATH = './backend/data/bm25_index.pkl'

# Import optional dependencies with error handling
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None
    print("Warning: sentence-transformers not installed. Embedding features will not work.")

try:
    import chromadb
except ImportError:
    chromadb = None
    print("Warning: chromadb not installed. Vector storage will not work.")

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    BM25Okapi = None
    print("Warning: rank-bm25 not installed. Keyword search will not work.")

try:
    import jieba
except ImportError:
    jieba = None
    print("Warning: jieba not installed. Chinese text segmentation will not work.")

try:
    import numpy as np
except ImportError:
    np = None
    print("Warning: numpy not installed.")

def _download_model_from_modelscope(model_name: str, cache_dir: str) -> str:
    """Download model from ModelScope to local cache directory"""
    try:
        from modelscope.hub.snapshot_download import snapshot_download
        os.makedirs(cache_dir, exist_ok=True)
        model_dir = snapshot_download(model_name, cache_dir=cache_dir)
        return model_dir
    except Exception as e:
        print(f"Warning: Could not download from ModelScope: {e}")
        return None

def _download_default_embedding_model():
    """Download the default embedding model from available sources"""
    model_name = "shibing624/text2vec-base-chinese"
    cache_path = os.path.join(MODEL_CACHE_DIR, model_name.replace("/", "_"))
    
    if os.path.exists(cache_path) and any(os.listdir(cache_path)):
        print(f"Model found in local cache: {cache_path}")
        return cache_path
    
    # Try ModelScope first (better for Chinese users)
    print(f"Trying to download model from ModelScope: {model_name}...")
    ms_model_name = "iic/nlp_corom_sentence-embedding_chinese-base"
    model_dir = _download_model_from_modelscope(ms_model_name, MODEL_CACHE_DIR)
    if model_dir:
        return model_dir
    
    return None

class VectorStoreService:
    def __init__(self):
        # Check required dependencies
        if chromadb is None:
            raise ImportError("chromadb is not installed. Please install it with 'pip install chromadb'.")
        if SentenceTransformer is None:
            raise ImportError("sentence-transformers is not installed. Please install it with 'pip install sentence-transformers'.")
        if jieba is None:
            raise ImportError("jieba is not installed. Please install it with 'pip install jieba'.")
        if BM25Okapi is None:
            raise ImportError("rank-bm25 is not installed. Please install it with 'pip install rank-bm25'.")
        
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self.collection = self.client.get_or_create_collection(
            name="legal_documents",
            metadata={"description": "法律文档知识库"}
        )
        
        # Load embedding model
        self.embedding_model = self._load_embedding_model()
        
        self.bm25_index = None
        self.all_documents = []
        self._load_bm25_from_disk()
    
    def _load_embedding_model(self):
        """Load embedding model with multiple fallback strategies"""
        # Strategy 1: Try to load from local cache path from ModelScope
        local_model_path = _download_default_embedding_model()
        if local_model_path:
            try:
                print(f"Loading model from local path: {local_model_path}...")
                model = SentenceTransformer(local_model_path, local_files_only=True)
                print("Model loaded successfully from local cache!")
                return model
            except Exception as e:
                print(f"Could not load model from local path: {e}")
        
        # Strategy 2: Try specified model from config (local cache)
        print(f"Trying to load model: {settings.EMBEDDING_MODEL} from local cache...")
        try:
            model = SentenceTransformer(settings.EMBEDDING_MODEL, local_files_only=True)
            print("Model loaded successfully from local cache!")
            return model
        except Exception as e:
            print(f"Model not in local cache: {e}")
        
        # Strategy 3: Try specified model with HF mirror (allow download)
        print(f"Trying to download model: {settings.EMBEDDING_MODEL} via HF mirror...")
        try:
            model = SentenceTransformer(settings.EMBEDDING_MODEL)
            print("Model loaded successfully!")
            return model
        except Exception as e:
            print(f"Error loading model from HF mirror: {e}")
        
        # Strategy 4: Fallback to a lightweight model (local only)
        print("Trying lightweight fallback model from local cache...")
        try:
            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", local_files_only=True)
            print("Lightweight model loaded!")
            return model
        except Exception as e2:
            print(f"Lightweight model not in cache: {e2}")
        
        # Strategy 5: Try to download lightweight model
        print("Trying to download lightweight model...")
        try:
            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            print("Lightweight model downloaded and loaded!")
            return model
        except Exception as e3:
            print(f"All model loading strategies failed: {e3}")
            
        # Strategy 6: Absolute last resort - try minimal model
        print("Trying minimal model...")
        try:
            model = SentenceTransformer("all-MiniLM-L6-v2")
            print("Minimal model loaded!")
            return model
        except Exception as e4:
            print(f"All model loading strategies failed: {e4}")
            raise RuntimeError("No embedding model could be loaded. Please run 'python download_model.py' first.")
    
    def _load_bm25_from_disk(self):
        """从磁盘 pickle 加载 BM25 索引（不在 RAM 中常驻重建）"""
        if os.path.exists(BM25_PERSIST_PATH):
            try:
                with open(BM25_PERSIST_PATH, 'rb') as f:
                    data = pickle.load(f)
                self.all_documents = data['documents']
                if self.all_documents:
                    tokenized_docs = [jieba.lcut(doc['content']) for doc in self.all_documents]
                    self.bm25_index = BM25Okapi(tokenized_docs)
                print(f"BM25 索引已从磁盘加载，共 {len(self.all_documents)} 个片段")
            except Exception as e:
                print(f"BM25 磁盘加载失败，将从 ChromaDB 重建: {e}")
                self._rebuild_bm25_from_db()
        else:
            print("未找到 BM25 持久化文件，将从 ChromaDB 重建")
            self._rebuild_bm25_from_db()
    
    def _rebuild_bm25_from_db(self):
        """从 ChromaDB 重建 BM25 索引（兜底方案）"""
        results = self.collection.get()
        self.all_documents = []
        
        if results and results['documents']:
            for i, doc in enumerate(results['documents']):
                self.all_documents.append({
                    'id': results['ids'][i],
                    'content': doc,
                    'metadata': results['metadatas'][i] if results['metadatas'] else {}
                })
            
            if self.all_documents:
                tokenized_docs = [jieba.lcut(doc['content']) for doc in self.all_documents]
                self.bm25_index = BM25Okapi(tokenized_docs)
        
        self._save_bm25_to_disk()
    
    def _save_bm25_to_disk(self):
        """将 BM25 文档数据持久化到磁盘 pickle"""
        try:
            os.makedirs(os.path.dirname(BM25_PERSIST_PATH), exist_ok=True)
            with open(BM25_PERSIST_PATH, 'wb') as f:
                pickle.dump({'documents': self.all_documents}, f)
        except Exception as e:
            print(f"BM25 持久化失败（不影响运行）: {e}")
    
    def add_documents(self, chunks: List[DocumentChunk], document_id: str, filename: str) -> int:
        if not chunks:
            return 0
        
        ids = [chunk.id for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = []
        
        for chunk in chunks:
            meta = {
                "document_id": document_id,
                "filename": filename,
                "page_number": chunk.page_number or 0,
                "paragraph_number": chunk.paragraph_number or 0
            }
            meta.update(chunk.metadata)
            metadatas.append(meta)
        
        embeddings = self.embedding_model.encode(documents, show_progress_bar=True).tolist()
        
        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )
        
        for i, chunk in enumerate(chunks):
            self.all_documents.append({
                'id': chunk.id,
                'content': chunk.content,
                'metadata': metadatas[i]
            })
        
        if self.all_documents:
            tokenized_docs = [jieba.lcut(doc['content']) for doc in self.all_documents]
            self.bm25_index = BM25Okapi(tokenized_docs)
        
        self._save_bm25_to_disk()
        
        return len(chunks)
    
    def semantic_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        query_embedding = self.embedding_model.encode([query]).tolist()
        
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k
        )
        
        formatted_results = []
        if results and results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                formatted_results.append({
                    'id': results['ids'][0][i],
                    'content': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'score': results['distances'][0][i] if results['distances'] else 0.0
                })
        
        return formatted_results
    
    def keyword_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self.bm25_index or not self.all_documents:
            return []
        
        tokenized_query = jieba.lcut(query)
        scores = self.bm25_index.get_scores(tokenized_query)
        
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                doc = self.all_documents[idx]
                results.append({
                    'id': doc['id'],
                    'content': doc['content'],
                    'metadata': doc['metadata'],
                    'score': float(scores[idx])
                })
        
        return results
    
    def hybrid_search(self, query: str, top_k: int = 5, 
                     semantic_weight: float = 0.7, 
                     keyword_weight: float = 0.3,
                     rerank_candidates: int = 0) -> List[Dict[str, Any]]:
        # 当启用 rerank 时，对内部语义/关键词检索取更多候选
        internal_k = max(top_k * 2, rerank_candidates) if rerank_candidates > 0 else top_k * 2
        semantic_results = self.semantic_search(query, internal_k)
        keyword_results = self.keyword_search(query, internal_k)
        
        combined = {}  # doc_id -> { id, content, metadata, total_score }
        
        for result in semantic_results:
            doc_id = result['id']
            combined[doc_id] = {
                'id': doc_id,
                'content': result['content'],
                'metadata': result['metadata'],
                'total_score': result['score'] * semantic_weight
            }
        
        for result in keyword_results:
            doc_id = result['id']
            if doc_id in combined:
                combined[doc_id]['total_score'] += result['score'] * keyword_weight
            else:
                combined[doc_id] = {
                    'id': doc_id,
                    'content': result['content'],
                    'metadata': result['metadata'],
                    'total_score': result['score'] * keyword_weight
                }
        
        # 最终取 top N（rerank 时取更多候选供精排，否则取 top_k）
        final_k = rerank_candidates if rerank_candidates > 0 else top_k
        sorted_results = sorted(
            combined.values(),
            key=lambda x: x['total_score'],
            reverse=True
        )[:final_k]
        
        return [
            {
                'id': r['id'],
                'content': r['content'],
                'metadata': r['metadata'],
                'score': r['total_score']
            }
            for r in sorted_results
        ]
    
    def delete_document(self, document_id: str) -> int:
        results = self.collection.get(
            where={"document_id": document_id}
        )
        
        if results and results['ids']:
            self.collection.delete(ids=results['ids'])
            self._rebuild_bm25_from_db()
            return len(results['ids'])
        
        return 0
    
    def get_document_chunks(self, document_id: str, page: int = 1, page_size: int = 50) -> Dict:
        """获取文档的所有检索片段（分页），用于文档预览"""
        results = self.collection.get(
            where={"document_id": document_id}
        )
        if not results or not results['ids']:
            return {"total": 0, "chunks": []}
        
        # 按页码和段落号排序
        chunks = []
        for i in range(len(results['ids'])):
            meta = results['metadatas'][i] if results['metadatas'] else {}
            chunks.append({
                "id": results['ids'][i],
                "content": results['documents'][i] if results['documents'] else "",
                "page_number": meta.get('page_number', 0),
                "paragraph_number": meta.get('paragraph_number', 0),
            })
        
        chunks.sort(key=lambda c: (c['page_number'], c['paragraph_number']))
        
        total = len(chunks)
        start = (page - 1) * page_size
        end = start + page_size
        page_chunks = chunks[start:end]
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            "chunks": page_chunks
        }
    
    def get_document_count(self) -> int:
        return self.collection.count()
    
    def clear_all(self):
        self.client.delete_collection("legal_documents")
        self.collection = self.client.get_or_create_collection(
            name="legal_documents",
            metadata={"description": "法律文档知识库"}
        )
        self.all_documents = []
        self.bm25_index = None
        if os.path.exists(BM25_PERSIST_PATH):
            os.remove(BM25_PERSIST_PATH)
