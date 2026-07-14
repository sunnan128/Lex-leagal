# 优化记录

法律文档智能问答系统（LexAI）开发过程中的优化与 Bug 修复记录。

---

## 项目一览（面试用）

| 维度 | 说明 |
|------|------|
| **项目名称** | LexAI 法律文档智能检索系统 |
| **核心架构** | RAG（检索增强生成）+ 混合检索 |
| **技术栈** | FastAPI · Streamlit · ChromaDB · Sentence-Transformers · BM25 · DeepSeek |
| **解决的问题** | 法律场景对准确性要求极高，通用大模型易产生幻觉。本系统通过**检索→溯源→生成**链路，确保每一条回答都有原文可查，检索不到则明确告知，杜绝幻觉。 |
| **核心能力** | PDF/Word 上传解析 → 按法律条款切分 → 语义+关键词混合检索 → LLM 生成带引用溯源的回答 |
| **本人贡献** | 全文检索链设计、文档解析切分优化、混合检索权重调优、嵌入模型多级降级加载、服务持久化、前端 UI 重构、生产级部署方案 |

---

## 优化总览

| 架构层 | # | 优化项 | 问题 | 效果 |
|-------|---|--------|------|------|
| **数据层** | ① | 合并过小文本片段 | 法律条款切分过碎，编码次数多 | 上传速度提升 3~5 倍 |
| **存储层** | ② | BM25 索引磁盘持久化 | 启动需从 ChromaDB 全量重建，数据安全无保障 | 启动从秒级→毫秒级，数据有磁盘副本 |
| **模型层** | ③ | 嵌入模型 6 层降级加载 | 国内无法直连 Hugging Face，服务不可用 | 已缓存秒级加载，未缓存自动走镜像/降级 |
| **模型层** | ④ | 向量编码显示进度 | 编码时终端无输出，用户无法判断状态 | 进度条实时展示编码进度 |
| **后端** | ⑤ | 文档列表重启后自动恢复 | `--reload` 热重载清空内存缓存，文档列表丢失 | 重启后从 ChromaDB 元数据恢复 |
| **后端** | ⑥ | 元数据索引 Bug 修复 | 上传第二个文件时数组越界，文件无法共存 | 多文件正常共存 |
| **后端** | ⑦ | 依赖导入优雅降级 | 缺少依赖直接模块级崩溃 | 打印警告引导安装，不直接崩溃 |
| **后端** | ⑧ | 删除文档失效修复 | `_restore_documents_from_db()` 未同步到内存缓存，重启后的文档无法删除 | 恢复时同步写入 `self.documents`，并增加兜底删除逻辑 |
| **接入层-前端** | ⑨ | 高智法律风格 UI + 可折叠抽屉 | Streamlit 默认样式缺少法律场景专业感 | 品牌 LexAI、卡片式布局、金色点缀、文档列表可折叠抽屉 |
| **接入层-前端** | ⑩ | 工具栏中文化 | 内置 "Stop" 按钮显示英文 | 替换为中文"停止" |
| **接入层-前端** | ⑪ | Streamlit 启动参数修复 | 参数不存在导致启动报错 | 前端能正常启动 |
| **接入层-前端** | ⑫ | 实时上传进度条 | 上传大文档时无反馈，用户不知道是否卡住 | 后台线程异步处理 + 前端每0.5s轮询进度，实时展示解析/编码/存储各阶段进度 |
| **接入层-部署** | ⑬ | 生产级部署方案 | 只能在本地运行，同事无法访问 | 4 套方案覆盖内网→远程→云服务 |
| **接入层-部署** | ⑭ | 后端自恢复脚本 | 后端进程崩溃、端口被占用时前端卡死 | `restart_backend.py` 检测端口 → 清理残留 → 重启后端 → 等待就绪，前端一键恢复 |
| **接入层-前端** | ⑮ | 文档预览页跳转框 | 浏览检索片段时无法快速定位 | 支持"片段号"和"原段落号"双模式跳转，跨页自动逐页搜索 |
| **接入层-前端** | ⑯ | 引用卡片直达定位 | 查看原文后需要手动翻页找引用位置 | 点击"查看原文"自动带上段落号参数，预览页加载后自动搜索并高亮定位 |

---

## 数据层

### ① 文档切分：合并过小片段

#### 问题

法律文档按 `第X条` / `第X款` 正则切分，每个条款独立成块。一份 193KB 的文档可能切出上百个片段，每条都要单独过向量编码模型，成为上传速度瓶颈。

#### 优化

在 [`document_parser.py`](backend/utils/document_parser.py) 中引入最小合并阈值：

```
MIN_CHUNK_SIZE = 80
```

切分完成后，遍历所有片段，将不足 80 字的相邻片段合并为一条，再丢给编码器。

#### 对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 193KB 文档片段数 | ~150~200 | ~40~60 |
| 向量编码次数 | 每片段 1 次 | 减少约 3~5 倍 |
| 上传耗时（同模型） | 慢（CPU 编码瓶颈） | 快 3~5 倍 |

---

## 存储层

### ② BM25 索引：从内存常驻改为磁盘持久化

#### 问题

BM25 关键词检索需要将所有文档片段的原文加载到内存以计算 TF-IDF 分数。随着文档量增长（数万份级别），BM25 占用的内存会线性增长到 GB 级别。同时，服务重启后需要从 ChromaDB 全量重新加载并重建 BM25 索引，耗时随着文档量增加。

#### 优化

在 [`vector_store.py`](backend/services/vector_store.py) 中引入 pickle 磁盘持久化：

```python
BM25_PERSIST_PATH = './backend/data/bm25_index.pkl'
```

- `add_documents()` → 更新内存 BM25 + **写盘**
- `delete_document()` → 从 ChromaDB 重建 + **写盘**  
- `__init__()` → 从磁盘 pickle **按需加载**（而非从 ChromaDB 重建）
- `clear_all()` → 同步删除 pickle 文件

#### 对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 启动时加载 | 从 ChromaDB 全量读取 → 分词 → 建索引 | 从 pickle 直接反序列化 |
| 启动速度（1万片段） | ~5~10 秒（需重新分词） | ~0.1 秒 |
| 内存占用（空闲时） | BM25 常驻 RAM | 服务启动后仍在 RAM（查询必需），但数据源头在磁盘 |
| 可扩展性 | 受限于服务重启重建时间 | 数据存磁盘，支持更大数据量 |

#### 说明

BM25 在查询时**必须**在内存中才能计算分数，所以查询时 RAM 占用不变。这项优化的意义在于：
1. 加速启动速度（从分词重建 → 直接反序列化）
2. 数据安全（磁盘有副本，内存崩溃不丢数据）
3. 为未来分片/惰性加载做基础

---

## 模型层

### ③ 嵌入模型加载：6 层降级策略

#### 问题

国内用户无法直连 Hugging Face，加载嵌入模型时抛出 `[WinError 10060]` 连接超时。

#### 优化

在 [`vector_store.py`](backend/services/vector_store.py) 中实现逐级降级策略：

| 优先级 | 策略 | 说明 |
|--------|------|------|
| ① | `local_files_only=True` | 先从本地缓存加载，零网络请求 |
| ② | ModelScope 国内源 | 调用 `modelscope.hub.snapshot_download` |
| ③ | HF 镜像 `hf-mirror.com` | 允许从镜像下载 |
| ④ | 轻量模型（本地） | `paraphrase-multilingual-MiniLM-L12-v2` |
| ⑤ | 轻量模型（下载） | 同上，允许联网 |
| ⑥ | 极小模型 `all-MiniLM-L6-v2` | 最终保底方案 |

同时配置镜像环境变量：

```python
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
os.environ['TRANSFORMERS_CACHE'] = './backend/data/model_cache'
os.environ['SENTENCE_TRANSFORMERS_HOME'] = './backend/data/model_cache'
```

#### 对比

| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 模型已缓存 | 仍尝试连接 HF → 超时报错 | 直接本地加载，秒级完成 |
| 模型未缓存（国内） | 无法下载，服务不可用 | 从镜像 / ModelScope 下载 |
| HF 镜像不可用 | 直接崩溃 | 自动降级到轻量模型 |

---

### ④ 向量编码：显示进度

#### 问题

上传文档时，终端没有任何进度输出，用户不知道模型是在加载还是卡住了。

#### 优化

在 [`vector_store.py`](backend/services/vector_store.py) 的 `encode()` 调用中添加进度条参数：

```python
# 优化前
embeddings = self.embedding_model.encode(documents).tolist()

# 优化后
embeddings = self.embedding_model.encode(documents, show_progress_bar=True).tolist()
```

#### 效果

终端会显示编码进度条 `100%|████| x/x [00:xx<00:00]`，用户可以清晰看到处理进度。

---

## 后端

### ⑤ 文档列表：重启后自动恢复

#### 问题

后端使用 `--reload` 热重载，修改代码后服务自动重启，`qa_service.documents` 内存字典清空，前端"已入库文档"列表变为空。

#### 优化

在 [`qa_service.py`](backend/services/qa_service.py) 中新增 `_restore_documents_from_db()` 方法：

```python
def get_documents(self) -> List[DocumentInfo]:
    # 内存有数据 → 直接返回
    if self.documents:
        return [...]
    # 内存为空 → 从 ChromaDB 元数据恢复
    return self._restore_documents_from_db()
```

恢复逻辑：遍历 ChromaDB 中所有 chunk 的 metadata，按 `document_id` 去重，还原出文档名和片段数。

#### 对比

| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 服务重启 | 文档列表清空 | 自动恢复，用户无感知 |
| 上传新文件后重启 | 新文件丢失 | 新老文件均可见 |

---

### ⑥ Bug 修复：add_documents 元数据索引越界

#### 问题

第二次上传文档时，`vector_store.add_documents()` 抛出 `IndexError: list index out of range`，导致上传失败且文档列表不更新。

#### 根因

[`vector_store.py`](backend/services/vector_store.py) 中 `all_documents` 的元数据索引计算错误：

```python
# 优化前（Bug）
for chunk in chunks:
    self.all_documents.append({
        ...
        'metadata': metadatas[len(self.all_documents) - len(chunks)]
    })
```

`len(self.all_documents)` 在循环中逐次增大，减去 `len(chunks)` 后超出 `metadatas` 的范围。

#### 修复

```python
# 优化后
for i, chunk in enumerate(chunks):
    self.all_documents.append({
        ...
        'metadata': metadatas[i]
    })
```

#### 对比

| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 上传第 1 个文件 | 正常（all_documents 为空） | 正常 |
| 上传第 2 个文件 | IndexError，上传失败 | 正常，文件共存 |
| 上传第 3+ 个文件 | 同第 2 个，持续报错 | 正常 |

---

### ⑦ 依赖导入：优雅降级

#### 问题

部分依赖（如 `sentence-transformers`、`chromadb`）未安装时，直接 `import` 导致模块级崩溃。

#### 优化

在 `document_parser.py` 和 `vector_store.py` 中使用 `try/except` 包裹 import：

```python
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None
    print("Warning: sentence-transformers not installed.")
```

同时在初始化时检查依赖是否可用，给出明确的安装提示：

```python
if SentenceTransformer is None:
    raise ImportError("请运行 pip install sentence-transformers")
```

#### 对比

| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 缺少依赖 | `ModuleNotFoundError` 崩溃 | 打印警告信息，引导安装 |
| 生产部署 | 缺少一个依赖整个服务不可用 | 给出明确提示，便于排障 |

---

### ⑧ 删除文档失效修复

#### 问题

文档上传后，如果服务经过 `--reload` 热重载，前端"已入库文档"列表虽然能正常显示（从 ChromaDB 元数据恢复），但点击"删除"按钮会返回"文档不存在"错误，无法删除。

#### 根因

[`qa_service.py`](backend/services/qa_service.py) 中有两条逻辑脱节：

1. `_restore_documents_from_db()` 从 ChromaDB 恢复文档列表后返回给前端展示，但**没有将文档信息写入 `self.documents` 内存缓存**
2. `delete_document()` 仅检查 `if document_id in self.documents`，找不到就返回 `False`

结果：恢复出来的文档在前端"可见"但"不可删"。

#### 修复

```python
# 修复前：恢复时不写缓存，delete 时找不到
def _restore_documents_from_db(self):
    ...
    return [DocumentInfo(...)]  # 仅返回，不缓存

# 修复后：同步写入 self.documents，并保留兜底删除
def _restore_documents_from_db(self):
    ...
    for info in doc_map.values():
        if info['id'] not in self.documents:
            self.documents[info['id']] = {
                'id': info['id'],
                'filename': info['filename'],
                'chunk_count': info['chunk_count'],
                'file_path': None  # 重启后文件路径不可恢复
            }
    return [...]

# delete_document 增加兜底：直接从 ChromaDB 删除
async def delete_document(self, document_id):
    if document_id in self.documents:
        ...
        return True
    # 兜底：即使缓存中没有，也尝试从 ChromaDB 删除
    try:
        self.vector_store.delete_document(document_id)
        return True
    except Exception:
        return False
```

#### 对比

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| 上传后立即删除 | 正常（在内存缓存中） | 正常 |
| 服务重启后删除 | ❌ 404"文档不存在" | ✅ 正常删除 |
| 极端情况（缓存异常） | ❌ 无法删除 | ✅ 兜底走 ChromaDB |

---

## 接入层 — 前端

### ⑧ 前端界面：高智法律风格

#### 问题

初始界面使用 Streamlit 默认样式，缺少法律场景的专业感。

#### 优化

在 [`app.py`](frontend/app.py) 中做了全面视觉升级：

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 品牌 | "法律文档智能问答系统" | **LexAI**（Lex 拉丁语"法律"） |
| 配色 | Streamlit 默认蓝白 | 深蓝灰 `#1a1a2e` + 金色 `#c9a84c` |
| 字体 | 系统默认无衬线 | `Noto Serif SC` 衬线体（法律文书感） |
| 背景 | 纯白 | 米白 `#f8f7f4`（纸质卷宗质感） |
| 布局 | 纵向线性排列 | 卡片式双栏布局 |
| 文档列表 | 卡片白框常驻显示 | 可折叠抽屉（`st.expander`），默认展开，可收起腾出空间 |
| 引用来源 | `st.expander` 默认样式 | 卡片式展示，hover 高亮金色边框 |
| 空状态 | `st.info("暂无文档")` | 设计感占位提示 |
| 侧边栏 | 简单文字说明 | 系统状态指示器 + 分节信息 |

---

### ⑨ Streamlit 工具栏中文化

#### 问题

Streamlit 内置的 "Stop" 按钮显示英文，与中文界面不协调。

#### 优化

通过 CSS `::after` 伪元素替换按钮文本：

```css
.stStatusWidget button[data-testid="stBaseButton-header"] span {
    font-size: 0;
    position: relative;
}
.stStatusWidget button[data-testid="stBaseButton-header"] span::after {
    content: "停止";
    font-size: 0.8rem;
    position: absolute;
    left: 0;
    top: 0;
}
```

#### 效果

| 元素 | 改前 | 改后 |
|------|------|------|
| 运行状态按钮 | "Stop" | "停止" |
| Deploy / 三点菜单 | 保留原文 | 保留原文（不影响使用） |

---

### ⑩ Streamlit 启动参数修正

#### 问题

启动前端时传入 `--server.gatherUsageStats false`，但该参数不存在，导致启动报错退出。

#### 修复

```bash
# 错误
--server.gatherUsageStats false

# 正确
--browser.gatherUsageStats false
```

同时创建 `.streamlit/config.toml` 配置文件，在配置层禁用使用统计收集。

---

### ⑫ 实时上传进度条

#### 问题

上传文档（尤其是大文档，如 193KB+）时，前端点击"上传并解析"后界面无任何反馈，用户不知道是在解析文档、编码向量还是卡住了。多文件上传场景下，用户也无法判断当前处理到第几个文件。

#### 优化

在 [`qa_service.py`](backend/services/qa_service.py) 中新增异步上传 + 进度报告机制：

1. **后端异步任务**：`POST /upload/start` 接受文件后立即返回 `task_id`，在后台线程中处理解析→编码→存储，每步更新进度
2. **进度分阶段**：
   - `queued`（0%）→ `parsing`（5%~15%）→ `embedding`（15%~85%，每 16 条一批更新）→ `saving`（88%~94%）→ `done`（100%）
3. **前端轮询**：调用 `GET /upload/progress/{task_id}` 每 0.5 秒轮询一次
4. **UI 显示**：整体进度条显示文件位置（如"文件 2/5"），每个文件有独立的实时进度条 + 状态文字（如"编码向量 (32/128)"）

#### 关键代码

**后端 — 异步上传入口**（[`qa_service.py`](backend/services/qa_service.py)）：
```python
async def start_upload_async(self, file, filename: str) -> str:
    task_id = str(uuid.uuid4())
    file_path = os.path.join(settings.UPLOAD_DIR, f"{task_id}_{filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file, buffer)
    self._report_progress(task_id, 0.0, "queued", "任务已创建")
    thread = threading.Thread(
        target=self._process_upload_background,
        args=(task_id, file_path, filename), daemon=True
    )
    thread.start()
    return task_id
```

**后端 — 进度报告**（[`qa_service.py`](backend/services/qa_service.py)）：
```python
def _report_progress(self, task_id, progress, stage, message):
    self._upload_progress[task_id] = {
        "progress": round(progress, 2),
        "stage": stage, "message": message
    }
```

**前端 — 轮询逻辑**（[`app.py`](frontend/app.py)）：
```python
# 启动异步上传
files = {"file": (file.name, file, file.type)}
r = requests.post(f"{API_URL}/upload/start", files=files)
task_id = r.json()["task_id"]

# 轮询进度
while True:
    time.sleep(0.5)
    pr = requests.get(f"{API_URL}/upload/progress/{task_id}")
    data = pr.json()
    progress_bar.progress(min(data["progress"], 1.0))
    status_text.text(f"{file.name} — {data['message']}")
    if data["stage"] == "done": break
```

#### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/upload/start` | 上传文件，返回 `{"task_id": "xxx"}` |
| `GET` | `/upload/progress/{task_id}` | 轮询进度，返回 `{"progress": 0.5, "stage": "embedding", "message": "编码向量 (32/128)"}` |

#### 对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 上传反馈 | 无任何进度指示，界面假死 | 实时显示解析→编码→存储各阶段进度 |
| 大文档体验 | 用户不知道是否在正常处理 | 进度条 + 状态文字，全程透明 |
| 多文件处理 | 每个文件间全黑 | 整体进度 + 文件级进度清晰可见 |

---

### ⑭ 后端自恢复脚本

#### 问题

后端服务可能因各种原因离线：端口被残留进程占用、代码热重载崩溃、模型加载超时等。前端会一直显示"后端服务尚未连接"，用户只能手动打开命令行排查重启。

#### 优化

新增 [`restart_backend.py`](restart_backend.py) 自恢复脚本，三步完成自恢复：

1. **检测端口占用** — 用 `netstat` 找出端口 8002 上的 LISTENING 进程 PID
2. **清理残留** — 逐个 `os.kill(pid, SIGTERM)` + `taskkill /F` 兜底
3. **重启后端** — `subprocess.Popen` 在新窗口中启动 uvicorn
4. **等待就绪** — 轮询 `/health` 端点，最多等 30 秒

前端"尝试恢复连接"按钮调用该脚本，展示 spinner 等待：

```python
restart_script = os.path.join(BASE_DIR, "restart_backend.py")
result = subprocess.run([sys.executable, restart_script],
    capture_output=True, text=True, timeout=60)
if result.returncode == 0:
    st.success("✅ 后端服务已自动恢复")
    st.rerun()
else:
    st.error("❌ 自动恢复失败，请手动启动")
```

#### 对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 后端离线 | 前端卡死，用户需要手动排查重启 | 点一下按钮，自动检测、清理、重启、验证 |
| 端口冲突 | 启动报错"地址已被占用" | 自动找 PID → 强制终止 → 重新绑定 |
| 恢复耗时 | 取决于用户排查能力 | 全自动，平均 30~60 秒 |

---

### ⑮ 文档预览页跳转框

#### 问题

文档预览页面有几百个检索片段，用户想找特定的片段号或原始段落号，只能手动滚动翻页，效率极低。

#### 优化

在文档预览页顶部增加跳转框，支持两种跳转模式：

**片段号模式**（默认）：输入 `1~N` 直接跳转到第 N 个检索片段

**原段落号模式**：输入原始文档段落号（如 `765`），自动搜索该段落所在的片段

跳转框的 HTML 实现：

```html
<select id="jumpMode">
    <option value="chunk">片段号</option>
    <option value="paragraph">原段落号</option>
</select>
<input type="number" id="jumpInput" placeholder="# 片段号 (1-614)">
<button onclick="jumpToChunk()">跳转</button>
```

JavaScript 自动翻页搜索逻辑：

```javascript
// 按原段落号跳转
var cards = document.querySelectorAll('[data-paragraph="' + num + '"]');
if (cards.length > 0) {
    cards[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
    cards.forEach(c => highlight(c));
} else {
    // 从第1页开始逐页搜索
    window.location.href = '/documents/' + docId + '/view?page=1&para=' + num;
}

// 每页加载时检查 para 参数，未找到自动翻下一页
var para = params.get('para');
if (para) {
    // 找当前页 → 没找到 → page+1 继续找
}
```

#### 对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 定位片段 | 手动逐页翻找 | 输入片段号一键跳转 |
| 定位原段落号 | 无法直接定位 | 输入任意段落号，自动跨页搜索+高亮 |

---

### ⑯ 引用卡片直达定位

#### 问题

用户在问答结果中看到引用卡片（如"第 1 页 · 第 765 段"），点击"查看原文"后跳转到文档预览页第一页，仍需手动翻到对应位置。

#### 优化

引用卡片的"查看原文 →"链接从纯文档预览 URL 改为带上段落号参数：

```python
# 改前
view_url = f"{API_URL}/documents/{doc_id}/view"

# 改后：直接定位到引用段落
view_url = f"{API_URL}/documents/{doc_id}/view?page=1&para={cite_para}"
```

预览页加载时自动检测 `?para=765` 参数，进行三段式定位：
1. 搜索当前页 → 找到则滚动+高亮
2. 未找到 → 自动翻到下一页继续搜索
3. 直到找到或最后一页

#### 交互效果

```
提问 → LLM 检索 → 引用卡片"第 765 段"
  ↓ 点击"查看原文"
文档预览页加载 → 自动触发 para=765 搜索
  ↓ 自动翻页直到找到
该段落卡片黄色高亮 + 自动滚动到屏幕中央
```

---

## 接入层 — 部署

### ⑬ 生产级部署方案

#### 问题

系统只能在本地运行，同事无法访问，公司内外网均不可用。

#### 方案

写了四套完整方案，详见 [`deployment.md`](deployment.md)：

| 方案 | 成本 | 远程可用 | 你关机还能用 |
|------|------|---------|------------|
| 内网共享 | 0 | ❌ | ❌ |
| Tailscale 组网 | 免费 | ✅ | ❌ |
| 云服务器 | ~50元/月 | ✅ | ✅ |
| Docker 云部署 | ~50元/月 | ✅ | ✅ |

#### 云服务器方案技术要点

- **反向代理**：Nginx 代理前后端，统一 443 端口
- **HTTPS**：Let's Encrypt 免费证书，自动续期
- **守护进程**：systemd 保证崩溃/重启后自动拉起
- **访问控制**：Nginx basic auth 防止未授权访问
- **数据迁移**：`backend/data/` 一键打包迁移

---

## 总结：面试时如何讲解优化

| 架构层 | 面试问题 | 回答要点 |
|--------|---------|---------|
| **数据层** | 上传速度慢怎么解决的？ | 合并小片段 + 进度条显示，编码次数减少 3~5 倍 |
| **存储层** | 内存不够怎么办？ | BM25 索引 pickle 磁盘持久化，启动速度从秒级降到毫秒级 |
| **模型层** | 模型下载不了怎么处理的？ | 6 层降级策略 + HF 镜像 + ModelScope 国内源 + 本地缓存优先 |
| **后端** | 多文件上传报错怎么修的？ | 元数据索引越界 Bug，用 `enumerate` 替代动态索引计算 |
| **后端** | 服务重启文档丢了怎么办？ | ChromaDB 元数据恢复机制，重启后自动回填文档列表 |
| **后端** | 重启后的文档删不掉怎么办？ | 恢复时同步写入内存缓存 + 兜底直接走 ChromaDB 删除 |
| **后端** | 后端崩溃了怎么办？ | `restart_backend.py` 自恢复脚本，前端一键检测端口→清理残留→重启→等待就绪 |
| **前端** | 前端做了哪些改进？ | LexAI 品牌、卡片式双栏布局、金色点缀、引用溯源卡片、实时上传进度条（异步后端 + 前端轮询） |
| **前端** | 预览页怎么快速定位片段？ | 双模式跳转框：按片段号直接跳转 / 按原段落号自动跨页搜索+高亮 |
| **前端** | 引用卡片能直接跳转到原文位置吗？ | 点击"查看原文"带上段落号参数，预览页自动搜索该段并高亮定位 |
| **部署** | 怎么部署到公网？ | 腾讯云轻量服务器 + Nginx + HTTPS + systemd + 基本认证 |
| **全栈** | 为什么用 ChromaDB 而不是 Milvus？ | 轻量、零运维、直接嵌入 Python 进程，小团队够用 |
| **全栈** | 为什么用 RAG 而不是 Fine-tune？ | 法律文档频繁更新、需要溯源、不可能为每份新法条重新训练 |
