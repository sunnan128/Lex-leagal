# ── 文档解析与切分 ──
# 决策记录：
# - PDF 用 PyMuPDF(fitz) 解析，Word 用 python-docx
# - 按"第X条/款/章/节"正则切分，适合法律文书结构
# - MIN_CHUNK_SIZE=80：相邻小片段自动合并，减少向量编码次数，
#   首批上传时提速 3~5 倍（原策略每个条款独立成块，数量过多）

import os
import re
import uuid
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

# Import optional dependencies with error handling
try:
    import fitz
except ImportError:
    fitz = None
    print("Warning: PyMuPDF (fitz) not installed. PDF parsing will not work.")

try:
    from docx import Document
except ImportError:
    Document = None
    print("Warning: python-docx not installed. Word document parsing will not work.")

class DocumentChunk:
    def __init__(self, content: str, page_number: Optional[int] = None, 
                 paragraph_number: Optional[int] = None, metadata: Dict[str, Any] = None):
        self.id = str(uuid.uuid4())
        self.content = content
        self.page_number = page_number
        self.paragraph_number = paragraph_number
        self.metadata = metadata or {}

class DocumentParser:
    # 最小合并阈值：少于该字数的相邻片段自动合并
    MIN_CHUNK_SIZE = 80

    @staticmethod
    def parse_pdf(file_path: str) -> List[DocumentChunk]:
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) is not installed. Please install it with 'pip install pymupdf'.")
        
        chunks = []
        doc = fitz.open(file_path)
        filename = os.path.basename(file_path)
        
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                if not text.strip():
                    continue
                    
                page_chunks = DocumentParser._split_legal_text(
                    text, 
                    page_num + 1, 
                    filename
                )
                chunks.extend(page_chunks)
        finally:
            doc.close()
        
        return chunks
    
    @staticmethod
    def parse_word(file_path: str) -> List[DocumentChunk]:
        if Document is None:
            raise ImportError("python-docx is not installed. Please install it with 'pip install python-docx'.")
        
        chunks = []
        doc = Document(file_path)
        filename = os.path.basename(file_path)
        
        current_page = 1
        paragraph_num = 0
        current_text = ""
        
        for para in doc.paragraphs:
            paragraph_num += 1
            text = para.text.strip()
            
            if not text:
                continue
                
            if DocumentParser._is_legal_article_start(text) and current_text:
                chunks.append(DocumentChunk(
                    content=current_text.strip(),
                    page_number=current_page,
                    paragraph_number=paragraph_num - 1,
                    metadata={"filename": filename}
                ))
                current_text = text + "\n"
            else:
                current_text += text + "\n"
        
        if current_text.strip():
            chunks.append(DocumentChunk(
                content=current_text.strip(),
                page_number=current_page,
                paragraph_number=paragraph_num,
                metadata={"filename": filename}
            ))
        
        return chunks
    
    @staticmethod
    def _split_legal_text(text: str, page_num: int, filename: str) -> List[DocumentChunk]:
        chunks = []
        
        article_pattern = r'(?:第[零一二三四五六七八九十百千\d]+条|第[零一二三四五六七八九十百千\d]+款)'
        
        parts = re.split(f'({article_pattern})', text)
        
        if not parts:
            return [DocumentChunk(
                content=text.strip(),
                page_number=page_num,
                metadata={"filename": filename}
            )]
        
        current_content = ""
        para_num = 0
        
        for i in range(len(parts)):
            part = parts[i].strip()
            if not part:
                continue
                
            if re.match(article_pattern, part):
                if current_content:
                    chunks.append({
                        'content': current_content.strip(),
                        'para_num': para_num
                    })
                    para_num += 1
                current_content = part + " "
            else:
                current_content += part
        
        if current_content.strip():
            chunks.append({
                'content': current_content.strip(),
                'para_num': para_num
            })
        
        # Merge small consecutive chunks
        merged = []
        buffer = ""
        buffer_para = 0
        for ch in chunks:
            if len(buffer) < DocumentParser.MIN_CHUNK_SIZE:
                buffer += "\n" + ch['content'] if buffer else ch['content']
                if buffer_para == 0:
                    buffer_para = ch['para_num']
            else:
                merged.append({'content': buffer, 'para_num': buffer_para})
                buffer = ch['content']
                buffer_para = ch['para_num']
        if buffer:
            if merged and len(buffer) < DocumentParser.MIN_CHUNK_SIZE:
                merged[-1]['content'] += "\n" + buffer
            else:
                merged.append({'content': buffer, 'para_num': buffer_para})
        
        if not merged:
            return [DocumentChunk(
                content=text.strip(),
                page_number=page_num,
                metadata={"filename": filename}
            )]
        
        return [
            DocumentChunk(
                content=m['content'],
                page_number=page_num,
                paragraph_number=m['para_num'],
                metadata={"filename": filename}
            )
            for m in merged
        ]
    
    @staticmethod
    def _is_legal_article_start(text: str) -> bool:
        patterns = [
            r'^第[零一二三四五六七八九十百千\d]+条',
            r'^第[零一二三四五六七八九十百千\d]+款',
            r'^第[零一二三四五六七八九十百千\d]+章',
            r'^第[零一二三四五六七八九十百千\d]+节',
        ]
        return any(re.match(pattern, text) for pattern in patterns)
    
    @staticmethod
    def parse_file(file_path: str) -> List[DocumentChunk]:
        ext = Path(file_path).suffix.lower()
        
        if ext == '.pdf':
            return DocumentParser.parse_pdf(file_path)
        elif ext in ['.docx', '.doc']:
            return DocumentParser.parse_word(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
