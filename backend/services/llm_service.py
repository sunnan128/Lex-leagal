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
from typing import List, Dict, Any, Tuple
from openai import OpenAI
from backend.config import settings
from backend.models.schemas import Citation

class LLMService:
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )
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
