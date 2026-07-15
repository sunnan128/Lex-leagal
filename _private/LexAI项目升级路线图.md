# LexAI 项目升级路线图

> 当前版本 v1.0 已有不错的基础。以下是按"投入产出比"排序的升级方向，每个方向标注了面试价值和工作量。

---

## 升级总览

| 优先级 | 升级方向 | 面试价值 | 工作量 | 对准岗位 |
|---|---|---|---|---|
| **P0** | Rerank 重排序 | 极高（必问考点） | 1-2天 | RAG工程师 |
| **P0** | RAGAS 自动评估 | 极高（展示工程化思维） | 1-2天 | RAG工程师 |
| **P1** | 查询路由 + 意图识别 | 高（Agent面试加分） | 2-3天 | Agent工程师 |
| **P1** | 多轮对话 + 对话记忆 | 高（从RAG到Agent的桥梁） | 3-4天 | Agent工程师 |
| **P2** | LangGraph Agent编排 | 高（Agent岗位核心技能） | 3-5天 | Agent工程师 |
| **P2** | 知识图谱（Neo4j） | 中高（差异化亮点） | 5-7天 | RAG工程师 |
| **P3** | RAG可观测性（LangSmith） | 中（展示Harness Engineering） | 1天 | 全岗位 |
| **P3** | API限流 + 缓存层 | 中（展示后端工程能力） | 1-2天 | 全岗位 |

---

## P0：Rerank 重排序（1-2天）

### 做什么

在混合检索返回结果后，加一层重排序模型对结果精排。

### 为什么重要

面试RAG工程师**几乎必问**："你的检索结果怎么保证最相关的排在前面？" 当前你的系统是简单加权融合，没有精排。加上Rerank就是工业级RAG的标准流程。

### 怎么做

```
混合检索（语义+BM25）
    → 取 top-20 候选
    → bge-reranker-large 精排
    → 取 top-5 给 LLM
```

```python
from sentence_transformers import CrossEncoder
reranker = CrossEncoder('BAAI/bge-reranker-large')

# 候选文档 pairs: [(query, doc1), (query, doc2), ...]
scores = reranker.predict(pairs)
# 按分数重排，取 top-k
```

### 面试话术

> "混合检索的召回阶段我取了top-20候选，然后用bge-reranker-large做交叉编码精排。重排序模型能同时理解query和文档的语义关系，比简单的向量余弦相似度更准确。精排后取top-5给LLM，回答质量明显提升。"

---

## P0：RAGAS 自动评估（1-2天）

### 做什么

用RAGAS框架自动评估RAG系统的回答质量，替代人工评估。

### 为什么重要

面试官会问"你怎么评估你的RAG系统好不好？"。如果你说"人工看"，就完了。RAGAS是工业标准，用上它直接从"学生项目"变成"工程项目"。

### 关键指标

| 指标 | 衡量什么 |
|---|---|
| Answer Relevancy | 回答是否相关于问题 |
| Faithfulness | 回答是否忠于检索到的文档（幻觉检测） |
| Context Precision | 检索到的文档是否相关 |
| Context Recall | 检索到的文档是否覆盖了答案所需的信息 |

### 怎么做

```python
from ragas import evaluate
from ragas.metrics import answer_relevancy, faithfulness, context_precision, context_recall

result = evaluate(
    dataset=test_dataset,
    metrics=[answer_relevancy, faithfulness, context_precision, context_recall]
)
```

构建一个测试数据集（50-100条question-answer-reference对），跑完评估后在README里放一个评估结果表格。

### 面试话术

> "我用RAGAS框架构建了自动评估pipeline，包含4个核心指标。Faithfulness检测幻觉——如果回答中包含检索文档中没有的信息，分数会很低。我跑了100条测试数据，当前系统的Faithfulness是0.92，Context Precision是0.85。上线前我会在每次迭代后都跑一遍评估，确保改动不会退化。"

---

## P1：查询路由 + 意图识别（2-3天）

### 做什么

用户提问时，先用一个小模型判断问题类型，再路由到不同的检索策略。

### 为什么重要

这是从"简单RAG"到"Agent系统"的第一步。面试Agent工程师时非常加分。

### 架构

```
用户提问
    │
    ▼
意图分类器（轻量模型/b规则）
    │
    ├── 简单查询（"什么是不可抗力"）
    │   → 直接语义检索 → 回答
    │
    ├── 精确查询（"民法典第584条"）
    │   → BM25精确匹配 → 回答
    │
    └── 复杂查询（"这个合同有哪些风险点"）
        → 多文档检索 → 分段分析 → 结构化回答
```

### 面试话术

> "我加了一个查询路由层，先判断用户意图再决定检索策略。精确条款号走BM25，语义问题走向量检索，复杂分析类问题走多文档检索。这避免了所有查询都走同一条路径导致的检索效率问题。"

---

## P1：多轮对话 + 对话记忆（3-4天）

### 做什么

支持用户追问、澄清，系统记住上下文。

### 为什么重要

当前是单轮问答，面试Agent岗时面试官会说"那追问怎么办？"。多轮对话是Agent的基础能力。

### 架构

```
对话历史存储（Redis / 内存）
    │
    ▼
每轮提问时：
1. 把对话历史 + 当前问题 → 组合成完整query
2. 用完整query做检索
3. 生成回答时带上对话上下文
```

```python
# 简化实现：拼接历史
context = "\n".join([f"Q: {q}\nA: {a}" for q, a in conversation_history])
enhanced_query = f"{context}\n当前问题：{user_question}"
```

### 面试话术

> "我实现了多轮对话支持。核心是把对话历史拼接到query中，让检索和生成都有上下文。对话历史超过一定轮数后用摘要压缩，避免上下文窗口溢出。"

---

## P2：LangGraph Agent编排（3-5天）

### 做什么

把当前的直接编排改为LangGraph StateGraph，拆分成多个Agent节点。

### 为什么重要

面试Agent工程师时，**LangGraph是最核心的技术关键词**。你的课程阶段8会教这个，直接迁移到LexAI上。

### 架构

```
用户提问
    │
    ▼
┌──────────────┐
│  路由 Agent   │ ← 判断查询类型
└──────┬───────┘
       │
  ┌────┴────┐
  ▼         ▼
检索Agent  分析Agent
  │         │
  ▼         ▼
验证Agent  ← 检查引用是否准确
  │
  ▼
生成Agent  ← 整合所有信息，生成最终回答
  │
  ▼
输出（带引用溯源）
```

### 面试话术

> "我用LangGraph的StateGraph重构了整个编排逻辑。每个Agent负责一个独立任务：检索Agent负责混合检索，验证Agent检查引用准确性，生成Agent整合信息输出回答。StateGraph管理Agent之间的状态传递，如果某个Agent出错了可以重试或降级，比直接串联调用更健壮。"

---

## P2：知识图谱（Neo4j）（5-7天）

### 做什么

从法律文档中抽取实体和关系，构建知识图谱，支持图谱查询。

### 为什么重要

这是你的架构设计文档里"规划中"的部分。实现了它，你的项目就从"又一个RAG系统"变成了"RAG+知识图谱"双引擎，差异化极强。

### 架构

```
文档 → NER实体抽取 → 关系抽取 → Neo4j存储
                              │
用户提问 → 意图判断 → 普通查询走RAG
                   → 关系查询走Neo4j Cypher
                   → 混合查询 → RAG + 图谱结果融合
```

### 面试话术

> "我实现了RAG+知识图谱双引擎检索。对于'张三涉及哪些案件'这种关系型查询，纯向量检索很难处理，但Neo4j图谱查询直接返回关联实体。对于'不可抗力的法律后果'这种语义查询，走RAG。两路结果融合后精排，兼顾语义理解和关系推理。"

---

## P3：RAG可观测性 - LangSmith（1天）

### 做什么

接入LangSmith，追踪每次请求的完整链路：检索了什么文档、用了多少token、延迟多少。

### 为什么重要

这是Harness Engineering的核心实践。面试时说"我做了全链路可观测性"，工程素养直接拉满。

### 面试话术

> "我接入了LangSmith做全链路追踪。每次请求的检索耗时、LLM推理耗时、Token消耗、引用准确性都能在Dashboard上看到。上线后如果发现回答质量下降，可以追溯到具体是检索阶段还是生成阶段出了问题。"

---

## 推荐实施顺序

### 如果面试 RAG 工程师（按这个顺序做）

```
第1周：P0 Rerank + P0 RAGAS评估
第2周：P1 查询路由
第3周：P2 知识图谱（如果时间够）
最后：P3 LangSmith可观测性
```

### 如果面试 Agent 工程师（按这个顺序做）

```
第1周：P1 多轮对话
第2周：P1 查询路由
第3周：P2 LangGraph Agent编排
最后：P3 LangSmith可观测性
```

---

## 不建议做的事

| 方向 | 为什么不做 |
|---|---|
| 换Milvus | 当前数据量不需要，换的投入产出比极低 |
| 换前端框架（Vue/React） | Streamlit足够Demo用，换前端不增加AI技术含金量 |
| 做用户系统/登录注册 | 和AI技术无关，面试官不关心 |
| 微调模型 | 法律场景用RAG比微调更合理，做微调反而是技术路线错误 |
