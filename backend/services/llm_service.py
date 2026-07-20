# ── LLM 推理服务 ──
# 决策记录：
# - 选 DeepSeek API 而非本地 7B 模型：API 效果远超本地小模型，百万 token ~1 元
# - OpenAI 兼容接口：切换模型只需改 base_url（如 Ollama / Qwen / 本地 vLLM）
# - temperature=0.3：法律场景需确定性和严谨性，偏低温度减少随机性
# - 防幻觉设计：
#   ① System Prompt 要求"只基于提供的文档内容回答"
#   ② 无检索结果时直接返回"知识库中未找到相关信息"
#   ③ found_kb 字段从 answer 字符串匹配判断，前端据此展示不同样式
# - _build_context 组装引用来源时保留文件名+页码+段落号，供 Citation 溯源展示

import time
import os
from typing import List, Dict, Any, Tuple, Optional
from openai import OpenAI
from backend.config import settings
from backend.models.schemas import Citation

# ── LangSmith 全链路追踪（条件化集成） ──
if settings.LANGSMITH_TRACING:
    # 将配置注入环境变量，langsmith SDK 从 os.environ 读取
    os.environ.setdefault("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    from langsmith import traceable
    from langsmith.wrappers import wrap_openai
else:
    # 关闭时使用无操作装饰器与包装函数，零额外开销
    def traceable(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda x: x
    def wrap_openai(client):
        return client

# ── bge-reranker-large 重排序模型 ──
# 决策记录：
# - 使用 CrossEncoder 而非 BiEncoder：CrossEncoder 直接建模 query-doc 相关性，精度更高
# - 懒加载：首次调用 rerank 时初始化，不占用启动时间
# - 输入为混合检索 top-20 候选，输出精排后 top-5
# - 面试重点：Rerank 是工业级 RAG 标准流程中"检索→精排→生成"的关键中间环节
_RERANKER_INSTANCE = None  # 模块级单例

def _reranker_cache_dir() -> str:
    """返回重排序模型在本地缓存的目录路径"""
    # SENTENCE_TRANSFORMERS_HOME 已在 vector_store.py 中设为 ./backend/data/model_cache
    cache_home = os.environ.get('SENTENCE_TRANSFORMERS_HOME', './backend/data/model_cache')
    # HuggingFace hub 缓存格式: models--BAAI--bge-reranker-large
    model_slug = f"models--{settings.RERANK_MODEL.replace('/', '--')}"
    return os.path.join(cache_home, model_slug)

def _is_reranker_cached() -> bool:
    """检查重排序模型是否已下载到本地缓存"""
    cache_dir = _reranker_cache_dir()
    if not os.path.exists(cache_dir):
        return False
    snapshots_dir = os.path.join(cache_dir, 'snapshots')
    if not os.path.exists(snapshots_dir):
        return False
    snapshots = os.listdir(snapshots_dir)
    return len(snapshots) > 0

def _get_reranker() -> Optional[Any]:
    """懒加载 CrossEncoder 重排序模型（单例，避免重复加载到显存）
    
    首次加载需要从 HuggingFace 下载模型（仅一次）并缓存到本地磁盘。
    后续重启/热重载后直接从磁盘加载，无需再次下载。
    """
    global _RERANKER_INSTANCE
    if _RERANKER_INSTANCE is not None:
        return _RERANKER_INSTANCE
    try:
        from sentence_transformers import CrossEncoder
        is_cached = _is_reranker_cached()
        if not is_cached:
            print(f"⏳ 首次加载重排序模型: {settings.RERANK_MODEL}（下载后永久缓存）...")
        _RERANKER_INSTANCE = CrossEncoder(settings.RERANK_MODEL)
        if not is_cached:
            print(f"✅ 重排序模型加载完成！")
        return _RERANKER_INSTANCE
    except Exception as e:
        print(f"重排序模型加载失败，将跳过 rerank: {e}")
        return None

class LLMService:
    def __init__(self):
        self.client = wrap_openai(OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        ))
        self.model = settings.LLM_MODEL
    
    def _build_context(self, search_results: List[Dict[str, Any]]) -> Tuple[str, List[Citation]]:
        if not search_results:
            return "", []
        
        context_parts = []
        citations = []
        
        for i, result in enumerate(search_results, 1):
            metadata = result.get('metadata', {})
            filename = metadata.get('filename', '未知文档')
            page_num = metadata.get('page_number')
            para_num = metadata.get('paragraph_number')
            
            context_part = f"[文档{i}] {filename}"
            if page_num:
                context_part += f" (第{page_num}页"
                if para_num:
                    context_part += f"，第{para_num}段"
                context_part += ")"
            context_part += f":\n{result['content']}\n"
            
            context_parts.append(context_part)
            
            citations.append(Citation(
                document_id=metadata.get('document_id', ''),
                document_name=filename,
                page_number=page_num,
                paragraph_number=para_num,
                content=result['content'][:300] + "..." if len(result['content']) > 300 else result['content'],
                score=result.get('score', 0.0)
            ))
        
        return "\n".join(context_parts), citations
    
    def _build_prompt(self, question: str, context: str) -> str:
        prompt = f"""你是一个专业的法律问答助手。请根据以下检索到的法律文档内容回答用户的问题。

重要规则：
1. 只基于提供的文档内容回答，不要编造信息
2. 如果文档中没有相关信息，明确回答"知识库中未找到相关信息"
3. 回答要准确、专业、简洁
4. 引用相关文档时，说明文档来源

检索到的文档内容：
{context}

用户问题：
{question}

请给出你的回答："""
        
        return prompt
    
    @traceable(run_type="chain")
    def rerank_results(self, question: str, 
                      candidates: List[Dict[str, Any]], 
                      top_k: int = 5) -> List[Dict[str, Any]]:
        """使用 CrossEncoder 对候选结果重排序
        
        Args:
            question: 原始查询问题
            candidates: 混合检索返回的候选结果列表
            top_k: 精排后返回的 top-k 条结果
            
        Returns:
            精排后的结果列表（按相关性降序）
        """
        if not candidates:
            return []
        
        reranker = _get_reranker()
        if reranker is None:
            # 重排序模型加载失败，直接取前 top_k 条
            return candidates[:top_k]
        
        # 构建 query-doc 对，供 CrossEncoder 打分
        pairs = [[question, cand['content']] for cand in candidates]
        
        import numpy as np
        try:
            scores = reranker.predict(pairs)
        except Exception as e:
            print(f"Rerank 预测失败，回退到原始排序: {e}")
            return candidates[:top_k]
        
        # 将 CrossEncoder 分数附加到结果中
        for i, cand in enumerate(candidates):
            cand['rerank_score'] = float(scores[i])
        
        # 按 rerank 分数降序排列
        reranked = sorted(candidates, key=lambda x: x['rerank_score'], reverse=True)
        
        # ── 安全兜底：若 CrossEncoder 最高分低于阈值，说明模型对全部候选置信度不足 ──
        # 此时回退到原始混合检索排序，避免用不可靠的 rerank 分数覆盖有用结果
        RERANK_CONFIDENCE_THRESHOLD = 0.1
        if reranked and reranked[0]['rerank_score'] < RERANK_CONFIDENCE_THRESHOLD:
            print(f"Rerank 最高分 {reranked[0]['rerank_score']:.4f} 低于阈值 {RERANK_CONFIDENCE_THRESHOLD}，"
                  f"回退到混合检索排序")
            return candidates[:top_k]
        
        # 置信度达标，用 rerank 分数覆盖 score，确保 LLM 看到的是精排后的相关性
        for cand in reranked:
            cand['score'] = cand['rerank_score']
        
        return reranked[:top_k]
    
    @traceable(run_type="llm")
    def generate_answer(self, question: str, 
                       search_results: List[Dict[str, Any]],
                       use_rerank: bool = True) -> Tuple[str, List[Citation], bool, float]:
        start_time = time.time()
        
        if not search_results:
            processing_time = (time.time() - start_time) * 1000
            return "知识库中未找到相关信息", [], False, processing_time
        
        context, citations = self._build_context(search_results)
        prompt = self._build_prompt(question, context)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的法律问答助手，严谨、准确、只基于提供的文档内容回答。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            answer = response.choices[0].message.content.strip()
            
            found_kb = "知识库中未找到相关信息" not in answer
            
            processing_time = (time.time() - start_time) * 1000
            
            return answer, citations, found_kb, processing_time
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            return f"生成回答时出错: {str(e)}", citations, False, processing_time
