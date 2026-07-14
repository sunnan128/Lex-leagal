# ── FastAPI 应用入口 ──
# 决策记录：
# - CORS 全放开（allow_origins=["*"]）：本地开发阶段简化调试，云部署时由 Nginx 控制
# - 同步 /upload 端点保留：保持向后兼容，供脚本调用
# - 异步 /upload/start + /upload/progress/{id} 端点新增：前端实时进度轮询方案
# - 异步上传设计：POST 接受文件后立即返回 task_id，后台线程处理解析→编码→存储
# - 健康检查 /health 返回 vector_db + llm 状态，前端据此决定是否启用检索功能

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from typing import List
import os
from backend.config import settings
from backend.models.schemas import (
    QueryRequest, QueryResponse, UploadResponse, 
    HealthResponse, DocumentInfo
)
from backend.services.qa_service import qa_service

app = FastAPI(
    title="法律文档智能问答系统",
    description="基于RAG和知识图谱的法律文档问答系统，支持溯源回答出处",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return await qa_service.get_health()

@app.get("/documents", response_model=List[DocumentInfo])
async def list_documents():
    return await qa_service.get_documents()

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    success = await qa_service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"message": "文档删除成功"}

@app.get("/documents/{document_id}/file")
async def download_document(document_id: str):
    """下载原始文档文件"""
    file_path = qa_service.get_document_file_path(document_id)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="原始文件不存在，文档可能已通过异步上传且服务已重启")
    
    filename = qa_service.documents.get(document_id, {}).get('filename', 'document')
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )

@app.get("/documents/{document_id}/view", response_class=HTMLResponse)
async def view_document(document_id: str, page: int = 1):
    """文档预览页面 — 在浏览器中展示文档的所有检索片段"""
    doc_info = qa_service.documents.get(document_id, {})
    filename = doc_info.get('filename', '未知文档')
    
    chunks_data = qa_service.get_document_chunks(document_id, page=page, page_size=50)
    if chunks_data['total'] == 0:
        return HTMLResponse("<h2>该文档没有检索片段</h2>")
    
    chunks_html = ""
    for i, chunk in enumerate(chunks_data['chunks']):
        page_str = f"第 {chunk['page_number']} 页" if chunk['page_number'] else ""
        para_str = f"原第 {chunk['paragraph_number']} 段" if chunk['paragraph_number'] else ""
        loc = f"{page_str} · {para_str}" if page_str and para_str else (page_str or para_str or "全文")
        global_idx = (page-1)*50 + i + 1
        
        chunks_html += f"""
        <div class="chunk-card" id="chunk-{global_idx}" data-paragraph="{chunk['paragraph_number']}">
            <div class="chunk-header">
                <span class="chunk-num">#片段 {global_idx}</span>
                <span class="chunk-loc">📖 {loc}</span>
            </div>
            <div class="chunk-content">{chunk['content']}</div>
        </div>
        """
    
    # 分页导航
    pages_html = ""
    if chunks_data['pages'] > 1:
        pages_html = '<div class="pagination">'
        for p in range(1, chunks_data['pages'] + 1):
            active = 'active' if p == page else ''
            pages_html += f'<a href="/documents/{document_id}/view?page={p}" class="page-link {active}">{p}</a>'
        pages_html += '</div>'
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{filename} — LexAI 文档预览</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f5f0; color: #1a1a2e; }}
        .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #f5f0e8; padding: 24px 40px; }}
        .header h1 {{ font-size: 1.3rem; font-weight: 500; }}
        .header .meta {{ font-size: 0.85rem; color: #c9a84c; margin-top: 6px; }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 24px 20px; }}
        .summary {{ background: #fff; border: 1px solid #e5e0d8; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; color: #4b5563; font-size: 0.9rem; }}
        .chunk-card {{ background: #fff; border: 1px solid #e5e0d8; border-radius: 8px; padding: 16px 20px; margin-bottom: 12px; }}
        .chunk-card:hover {{ border-color: #c9a84c; }}
        .chunk-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .chunk-num {{ font-size: 0.8rem; color: #c9a84c; font-weight: 600; }}
        .chunk-loc {{ font-size: 0.8rem; color: #6b7280; }}
        .chunk-content {{ font-size: 0.9rem; line-height: 1.8; color: #374151; white-space: pre-wrap; }}
        .pagination {{ display: flex; justify-content: center; gap: 8px; margin-top: 24px; flex-wrap: wrap; }}
        .page-link {{ display: inline-flex; align-items: center; justify-content: center; min-width: 36px; height: 36px; border-radius: 6px; border: 1px solid #e5e0d8; background: #fff; color: #374151; text-decoration: none; font-size: 0.85rem; }}
        .page-link:hover {{ border-color: #c9a84c; }}
        .page-link.active {{ background: #c9a84c; color: #fff; border-color: #c9a84c; }}
        .jump-box {{ display: flex; gap: 6px; align-items: center; }}
        .jump-box select {{ padding: 6px 6px; border: 1px solid #e5e0d8; border-radius: 6px; font-size: 0.85rem; outline: none; background: #fff; cursor: pointer; }}
        .jump-box select:focus {{ border-color: #c9a84c; }}
        .jump-box input {{ width: 110px; padding: 6px 10px; border: 1px solid #e5e0d8; border-radius: 6px; font-size: 0.85rem; outline: none; }}
        .jump-box input:focus {{ border-color: #c9a84c; }}
        .jump-box button {{ padding: 6px 14px; background: #c9a84c; color: #fff; border: none; border-radius: 6px; font-size: 0.85rem; cursor: pointer; }}
        .jump-box button:hover {{ background: #b8942e; }}
        .footer {{ text-align: center; padding: 24px; color: #9ca3af; font-size: 0.8rem; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📄 {filename}</h1>
        <div class="meta">共 {chunks_data['total']} 个检索片段 · 第 {chunks_data['page']}/{chunks_data['pages']} 页</div>
    </div>
    <div class="container">
        <div class="summary">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                <span>共检索到 <strong>{chunks_data['total']}</strong> 个片段，按页码排列</span>
                <div class="jump-box">
                    <select id="jumpMode" onchange="updateJumpPlaceholder()">
                        <option value="chunk">片段号</option>
                        <option value="paragraph">原段落号</option>
                    </select>
                    <input type="number" id="jumpInput" min="1" placeholder="# 片段号 (1-{chunks_data['total']})" onkeydown="if(event.key==='Enter') jumpToChunk()">
                    <button onclick="jumpToChunk()">跳转</button>
                </div>
            </div>
        </div>
        {chunks_html}
        {pages_html}
    </div>
    <div class="footer">LexAI 法律文档智能问答系统 · 文档预览</div>
    <script>
    var totalChunks = {chunks_data['total']};
    var docId = '{document_id}';

    // 页面加载后自动跳转到 URL 锚点
    window.onload = function() {{
        if (window.location.hash) {{
            var el = document.getElementById(window.location.hash.slice(1));
            if (el) {{
                setTimeout(function() {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    highlight(el);
                }}, 300);
            }}
        }}
    }};

    function highlight(el) {{
        el.style.transition = 'background 0.5s';
        el.style.background = '#fefce8';
        setTimeout(function() {{ el.style.background = '#fff'; }}, 2000);
    }}

    function updateJumpPlaceholder() {{
        var mode = document.getElementById('jumpMode').value;
        var input = document.getElementById('jumpInput');
        if (mode === 'chunk') {{
            input.placeholder = '# 片段号 (1-' + totalChunks + ')';
            input.max = totalChunks;
        }} else {{
            input.placeholder = '原段落号（如 765）';
            input.max = '';
        }}
        input.value = '';
    }}

    function jumpToChunk() {{
        var mode = document.getElementById('jumpMode').value;
        var num = parseInt(document.getElementById('jumpInput').value);
        if (!num || num < 1) {{
            alert('请输入有效的编号');
            return;
        }}

        if (mode === 'chunk') {{
            // 按片段号跳转
            if (num > totalChunks) {{
                alert('片段号范围 1~' + totalChunks);
                return;
            }}
            var el = document.getElementById('chunk-' + num);
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                highlight(el);
            }} else {{
                var targetPage = Math.ceil(num / 50);
                window.location.href = '/documents/' + docId + '/view?page=' + targetPage + '#chunk-' + num;
            }}
        }} else {{
             // 按原段落号跳转：查找所有 data-paragraph 匹配的卡片
             var cards = document.querySelectorAll('[data-paragraph="' + num + '"]');
             if (cards.length > 0) {{
                 cards[0].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                 cards.forEach(function(c) {{ highlight(c); }});
             }} else {{
                 // 不在当前页，从第1页开始逐页搜索
                 window.location.href = '/documents/' + docId + '/view?page=1&para=' + num;
             }}
         }}
     }}
 
     // 处理从其他页跳转过来的段落号定位
     (function() {{
         var params = new URLSearchParams(window.location.search);
         var para = params.get('para');
         if (para) {{
             setTimeout(function() {{
                 var cards = document.querySelectorAll('[data-paragraph="' + para + '"]');
                 if (cards.length > 0) {{
                     cards[0].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                     cards.forEach(function(c) {{ highlight(c); }});
                     document.getElementById('jumpMode').value = 'paragraph';
                     document.getElementById('jumpInput').placeholder = '原段落号（如 ' + para + '）';
                     document.getElementById('jumpInput').value = para;
                 }} else {{
                     // 当前页未找到，自动翻到下一页
                     var currentPage = parseInt(params.get('page')) || 1;
                     var nextPage = currentPage + 1;
                     if (nextPage <= {chunks_data['pages']}) {{
                         window.location.href = '/documents/' + docId + '/view?page=' + nextPage + '&para=' + para;
                     }}
                 }}
             }}, 300);
         }}
     }}());
    </script>
</body>
</html>"""
    return HTMLResponse(html)

@app.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    
    ext = file.filename.split('.')[-1].lower()
    if ext not in ['pdf', 'docx', 'doc']:
        raise HTTPException(status_code=400, detail="只支持 PDF 和 Word 文档")
    
    try:
        return await qa_service.upload_document(file.file, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload/start")
async def upload_start(file: UploadFile = File(...)):
    """启动异步上传，返回 task_id 供轮询进度"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    
    ext = file.filename.split('.')[-1].lower()
    if ext not in ['pdf', 'docx', 'doc']:
        raise HTTPException(status_code=400, detail="只支持 PDF 和 Word 文档")
    
    try:
        task_id = await qa_service.start_upload_async(file.file, file.filename)
        return {"task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/upload/progress/{task_id}")
async def upload_progress(task_id: str):
    """轮询异步上传任务的进度"""
    progress_data = qa_service.get_upload_progress(task_id)
    if not progress_data:
        raise HTTPException(status_code=404, detail="任务不存在")
    return progress_data

@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    
    try:
        return await qa_service.query(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True
    )
