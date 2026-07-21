# 法律文档智能问答系统（LexAI）

基于 RAG（检索增强生成）的专业法律文档问答系统，支持溯源回答出处，杜绝幻觉。

## 项目背景

### 痛点

法律行业对信息准确性要求极高，但通用大模型存在三个核心问题：

1. **幻觉不可接受** — ChatGPT / DeepSeek 可能编造看起来合理的法条，在法律场景中这是致命风险
2. **回答无法溯源** — 即使回答正确，也无法定位到原文第几条第几款，无法作为决策依据
3. **知识更新滞后** — 法律每年修订、新增、废止，Fine-tune 一次成本高、周期长

### 解决方案

LexAI 用 **RAG（检索增强生成）** 架构，将 LLM 从"编造者"变成"引用者"：

| # | 问题 | 方案 |
|---|------|------|
| ① | 杜绝幻觉 | 只基于检索到的文档回答，检索不到明确告知"未找到" |
| ② | 回答要有出处 | 引用溯源卡片：文档名 + 页码 + 段落号 + 内容快照 |
| ③ | 条款号精确检索 | 混合检索：语义检索 + BM25 关键词（如"第584条"精确命中） |
| ④ | 法律文档适配 | 按"第X条/款/章/节"切分，保留法律文书结构 |
| ⑤ | 知识及时更新 | 上传新文档即扩充知识库，无需重新训练 |

一句话：**让 AI 只引用原文，不编造内容，每条回答都可追溯。**

## 功能特点

- 📄 **文档上传**: 支持 PDF 和 Word 格式法律文档上传，可**同时选择最多 5 份**
- ⏳ **实时进度条**: 异步上传 + 前端轮询，实时展示解析→编码→存储各阶段进度
- 🔍 **混合检索**: 智能语义检索 + 关键词检索，精准匹配
- 📑 **溯源回答**: 回答附带引用来源，精确到页码和段落
- 🚫 **杜绝幻觉**: 检索不到时明确回复"知识库中未找到相关信息"
- 🎯 **法律场景优化**: 针对法律条款、判例等内容优化切分和检索
- 🔗 **层级关联检索**: "法律名称+条款序号"类查询自动拆解为主体+子关键词，通过元数据补充检索 + 三级梯次评分确保精准命中 | 目录切片 |

## 技术架构

```
接入层: FastAPI + Streamlit
数据层: 文档解析 (PyMuPDF, python-docx)
检索层: 向量检索 (ChromaDB) + 关键词检索 (BM25)
生成层: OpenAI API (支持本地 Ollama 部署)
存储层: ChromaDB (向量存储)
```

## 快速开始

### 环境要求

- Python 3.9+
- pip

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，并根据需要修改配置：

```bash
cp .env.example .env
```

主要配置项：
- `OPENAI_API_KEY`: OpenAI API 密钥
- `OPENAI_BASE_URL`: API 基础地址（可配置为兼容 OpenAI 的代理地址）
- `LLM_MODEL`: 使用的模型名称

### 3. 启动服务

#### 推荐方式（跨平台）

使用 Python 启动脚本（最稳定，无编码问题）：

```bash
python run.py
```

#### Windows

直接运行启动脚本：

```bash
start.bat
```

#### Linux/Mac

```bash
chmod +x start.sh
./start.sh
```

#### 手动启动

启动后端服务：

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload
```

启动前端服务（新终端）：

```bash
python -m streamlit run frontend/app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

### 4. 访问系统

- 前端界面: http://localhost:8501
- 后端 API: http://localhost:8002
- API 文档: http://localhost:8002/docs

## Docker 部署

使用 Docker Compose 一键部署：

```bash
docker-compose up -d
```

## 使用说明

### 1. 上传文档

在"文档管理"标签页上传法律文档（PDF 或 Word），系统会自动：
- 解析文档内容
- 按法律条款智能切分
- 向量化存储
- 实时进度条展示解析→编码→存储各阶段状态（后端异步处理，前端每 0.5s 轮询进度）

### 2. 智能问答

在"智能问答"标签页：
1. 输入法律问题
2. 调整检索参数（可选）
3. 点击"提问"获取回答
4. 查看回答及引用来源

### 3. 引用溯源

每个回答会显示：
- 来源文档名称
- 页码和段落号
- 相关度分数
- 内容片段

## 项目结构

```
legal-qa-system/
├── backend/
│   ├── config.py              # 配置文件
│   ├── main.py                # FastAPI 入口
│   ├── models/
│   │   └── schemas.py         # 数据模型
│   ├── services/
│   │   ├── qa_service.py      # 主服务
│   │   ├── vector_store.py    # 向量存储服务
│   │   └── llm_service.py     # LLM 服务
│   └── utils/
│       └── document_parser.py # 文档解析
├── frontend/
│   └── app.py                 # Streamlit 前端
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── run.py                   # Python 启动脚本（跨平台，推荐）
├── start.bat
├── start.sh
└── README.md
```

## API 接口

### 健康检查

```
GET /health
```

### 文档管理

```
GET    /documents              # 获取文档列表
POST   /upload                 # 上传文档（同步，保持向后兼容）
POST   /upload/start           # 异步上传文档，返回 task_id
GET    /upload/progress/{id}   # 轮询上传进度（progress: 0~1.0, stage, message）
DELETE /documents/{id}         # 删除文档
```

### 智能问答

```
POST /query
{
  "question": "法律问题",
  "top_k": 5,
  "use_rerank": true,
  "use_keyword_search": true
}
```

## 核心特性说明

### 混合检索 + 层级关联评分

系统采用"粗排→精排→层级评分"三段式检索策略：
1. 语义向量检索：使用 BGE 模型，处理语义匹配
2. 关键词检索：使用 BM25，处理精确条款号匹配
3. 混合融合：语义相似度（ChromDB L2 距离经 `1/(1+d)` 转相似度）+ 关键词分数（BM25 归一化到 [0,1]），按权重 0.7 : 0.3 合并，取 top-20 候选
4. **重排序精排**：bge-reranker-large CrossEncoder 对 top-20 候选逐对打分，精排取 top-5 给 LLM
5. **层级关联评分**：当检测到"法律名称+条款序号"类查询时（如"民法典第35条"），自动解析为主体关键词"民法典"和子关键词"第35条"，通过元数据（文件名）补充检索该法律的所有文档块，应用三级梯次评分（TIER-1 主体+子关键词 > TIER-2 仅主体 > TIER-3 仅子关键词），确保精准命中目标条款
6. **安全兜底**：当 CrossEncoder 最高分低于置信度阈值（0.1）时，自动回退到混合检索排序，避免不可靠的 rerank 分数覆盖有用结果

### 文档切分

针对法律文档特点，采用特殊切分策略：
- 按"第X条"、"第X款"等标识切分
- 保留文档结构信息
- 记录页码和段落号用于溯源

### 幻觉抑制

通过以下方式杜绝幻觉：
- 严格基于检索结果回答
- 检索不到时明确声明
- 所有回答附带引用来源
- 低温度参数设置（0.3）

## 评估结果

基于 **30 条 QA 对、10 个法律领域**的评估数据集，对比 Baseline（无 Rerank）和 Rerank（bge-reranker-large 精排）两种模式的量化效果。

> ⚠️ 当前未安装 RAGAS（`pip install ragas`），指标为 LLM-as-a-Judge 降级方案。安装后可输出 faithfulness / answer_relevancy / context_precision / context_recall 四大标准指标。

### 整体指标对比

| 指标 | Baseline | Rerank | 变化 |
|------|----------|--------|:----:|
| 知识库覆盖率 | 86.67% (26/30) | **93.10%** (27/29) | ▲ **7.42%** |
| 平均处理时间 | 2078 ms | 2137 ms | ▲ 2.83% |

> Rerank 模式增加了一次 CrossEncoder 逐对打分，处理时间上升约 59ms，但知识库覆盖率提升 7.42 个百分点，整体精度-速度权衡合理。

### 按法律类别分析

| 类别 | Baseline 覆盖率 | Rerank 覆盖率 | 变化 |
|------|:--------------:|:-------------:|:----:|
| 侵权责任 | 100% (3/3) | 100% (3/3) | — |
| 公司法 | 66.67% (2/3) | 66.67% (2/3) | — |
| 劳动法 | 100% (3/3) | 100% (3/3) | — |
| 合同法 | 100% (3/3) | 100% (3/3) | — |
| 婚姻家庭 | 100% (3/3) | 100% (3/3) | — |
| **民事诉讼法** | **33.33%** (1/3) | **66.67%** (2/3) | ▲ **100%** |
| 民法典-总则 | 100% (3/3) | 100% (2/2) | — |
| 民法典-物权 | 100% (3/3) | 100% (3/3) | — |
| **知识产权** | **66.67%** (2/3) | **100%** (3/3) | ▲ **50%** |
| 继承法 | 100% (3/3) | 100% (3/3) | — |

> Rerank 精排对**民事诉讼法**和**知识产权**类别提升最明显，说明 CrossEncoder 对语义模糊的检索场景有显著改善。

### 总结

> "Rerank 让知识库覆盖率从 **86.67% 提升到 93.10%**，民事诉讼法从 33% 提升到 67%，知识产权从 67% 提升到 100%。处理时间仅增加 59ms，在可接受范围内。"

## 常见问题

### 如何使用本地模型？

修改 `.env` 文件，配置为 Ollama 地址：

```
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=deepseek-chat
```

### 如何切换向量模型？

修改 `.env` 中的 `EMBEDDING_MODEL` 配置，支持所有 Sentence-Transformers 模型。

