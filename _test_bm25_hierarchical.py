# -*- coding: utf-8 -*-
"""模拟完整层级关联检索（含 RRF 融合 + 元数据补充 + 层级评分）
验证：搜索「民法典第35条」时，民事条款排位高于其他法律的相同条款"""

import pickle, re, sys, json

path = r'd:\trae_project02_law\backend\data\bm25_index.pkl'
with open(path, 'rb') as f:
    data = pickle.load(f)
docs = data['documents']
print(f'Total documents: {len(docs)}')

# ── 辅助函数 (同 vector_store.py) ──
_CHINESE_NUM_SIMPLE = ['零','一','二','三','四','五','六','七','八','九']
def _number_to_chinese(num_str):
    if not num_str: return ''
    n = int(num_str)
    if n == 0: return '零'
    units = ['','十','百','千']; result = ''
    digits = [int(d) for d in str(n)]; length = len(digits)
    for i, d in enumerate(digits):
        pos = length - 1 - i
        if d == 0:
            if result and not result.endswith('零'): result += '零'
        else:
            result += _CHINESE_NUM_SIMPLE[d]
            if pos > 0: result += units[pos]
    result = result.rstrip('零')
    if result.startswith('一十'): result = result[1:]
    return result

def _chinese_to_number(chinese):
    if not chinese: return None
    _cn_map = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    _unit_map = {'十':10,'百':100,'千':1000}
    try:
        total = 0; current = 0
        for ch in chinese:
            if ch in _cn_map: current = _cn_map[ch]
            elif ch in _unit_map:
                if current == 0: current = 1
                total += current * _unit_map[ch]; current = 0
            else: return None
        total += current; return str(total)
    except: return None

def _normalize_article_variant(article_str):
    m = re.match(r'^(第)(\d+)([条款章节])$', article_str)
    if m: return f'{m.group(1)}{_number_to_chinese(m.group(2))}{m.group(3)}'
    m = re.match(r'^(第)([零一二三四五六七八九十百千]+)([条款章节])$', article_str)
    if m:
        arabic = _chinese_to_number(m.group(2))
        if arabic: return f'{m.group(1)}{arabic}{m.group(3)}'
    return None

def parse_hierarchical_query(query):
    m = re.search(r'(第[零一二三四五六七八九十百千\d]+[条款章节])', query)
    if not m: return (None, None)
    sub_key = m.group(1); before = query[:m.start()].strip()
    return (before, sub_key) if before else (None, sub_key)

def apply_hierarchical_scoring(items, subject_key, sub_key):
    if subject_key is None or sub_key is None: return
    sub_variants = [sub_key]
    alt = _normalize_article_variant(sub_key)
    if alt and alt != sub_key: sub_variants.append(alt)
    for item in items:
        c = item['content']; meta = item.get('metadata', {})
        fn = meta.get('filename','') if isinstance(meta,dict) else ''
        hs = (subject_key in c) or (subject_key in fn)
        hsub = any(v in c for v in sub_variants)
        if hs and hsub: item['score'] += 0.03; item['_tag'] = 'TIER-1'
        elif hs: item['score'] += 0.01; item['_tag'] = 'TIER-2'
        elif hsub: item['_tag'] = 'TIER-3'
        else: item['_tag'] = 'NONE'

def search_by_subject_metadata(subject_key):
    results = []
    for d in docs:
        meta = d.get('metadata', {})
        fn = meta.get('filename','') if isinstance(meta,dict) else ''
        if subject_key in fn:
            results.append({
                'id': d['id'], 'content': d['content'],
                'metadata': d['metadata'], 'score': 0.0
            })
    return results

import jieba
from rank_bm25 import BM25Okapi
tokenized_docs = [jieba.lcut(d['content']) for d in docs]
bm25 = BM25Okapi(tokenized_docs)

def keyword_search(query, top_k=20):
    tq = jieba.lcut(query)
    scores = bm25.get_scores(tq)
    indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [{
        'id': docs[i]['id'], 'content': docs[i]['content'],
        'metadata': docs[i]['metadata'], 'score': float(scores[i])
    } for i in indices if scores[i] > 0]

# ═══════════════════════════════════
# 模拟 hybrid_search 完整流程
# ═══════════════════════════════════
query = "民法典第35条"
print(f'\nQuery: {query}')
subject_key, sub_key = parse_hierarchical_query(query)
alt = _normalize_article_variant(sub_key)
print(f'Parsed: subject={subject_key}, sub_key={sub_key}')
print(f'Sub variants: [{sub_key}, {alt}]')
print()

# 步骤1: 关键词检索 (internal_k=20)
keyword_results = keyword_search(query, top_k=20)
print(f'Keyword results: {len(keyword_results)}')

# 步骤2: 模拟 RRF (仅一路关键词，另一路语义假设为空)
# 实际系统中语义搜索也可贡献结果，这里模拟最坏情况
RRF_K = 20
scored = []
for i, r in enumerate(keyword_results):
    rank_kw = i + 1
    rrf_score = 1.0 / (RRF_K + rank_kw)
    scored.append({
        'id': r['id'], 'content': r['content'],
        'metadata': r['metadata'], 'score': rrf_score
    })

# 步骤3: 元数据补充检索
subject_docs = search_by_subject_metadata(subject_key)
existing_ids = {item['id'] for item in scored}
new_from_meta = 0
for sd in subject_docs:
    if sd['id'] not in existing_ids:
        sd['score'] = 0.02
        scored.append(sd)
        new_from_meta += 1
print(f'Subject metadata: {len(subject_docs)} found, {new_from_meta} new in pool')

# 步骤4: 层级评分
apply_hierarchical_scoring(scored, subject_key, sub_key)
scored.sort(key=lambda x: x['score'], reverse=True)

print(f'\nTop-10 results (RRF + metadata supplement + hierarchical scoring):')
print(f'{"Rank":<6} {"Tag":<10} {"Score":<10} Filename / Content')
print('-' * 100)

for i, r in enumerate(scored[:10], 1):
    tag = r.get('_tag', 'NONE')
    meta = r.get('metadata', {})
    fname = (meta.get('filename','?') or '?') if isinstance(meta,dict) else '?'
    preview = r['content'][:60].replace('\n', ' ')
    print(f'{i:<6} {tag:<10} {r["score"]:<10.6f} {fname[:40]}')
    print(f'       {preview}')
    print()

# ── 查找 TIER-1 位置 ──
tier1_ranks = [i for i,r in enumerate(scored) if r.get('_tag') == 'TIER-1']
tier3_ranks = [i for i,r in enumerate(scored[:20]) if r.get('_tag') == 'TIER-3']

print(f'\nTIER-1 count in full pool: {len(tier1_ranks)}')
print(f'TIER-1 best rank: #{tier1_ranks[0]+1 if tier1_ranks else "N/A"}')
print(f'TIER-3 count in top-20: {len(tier3_ranks)}')

# ── 验证 ──
print('\n' + '=' * 60)
print('VERIFICATION:')

top5_tier1 = sum(1 for r in scored[:5] if r.get('_tag') == 'TIER-1')
print(f'  Top-5 TIER-1: {top5_tier1} (need >= 1) -> {"PASS" if top5_tier1 >= 1 else "FAIL"}')

top3_tier3 = sum(1 for r in scored[:3] if r.get('_tag') == 'TIER-3')
print(f'  Top-3 TIER-3: {top3_tier3} (need == 0) -> {"PASS" if top3_tier3 == 0 else "FAIL"}')

# TIER-2 是否在 TIER-3 之前
tier2_before_tier3 = True
if tier1_ranks and tier3_ranks:
    tier2_earliest = None
    tier3_earliest = None
    for i, r in enumerate(scored):
        if r.get('_tag') == 'TIER-2' and tier2_earliest is None:
            tier2_earliest = i
        if r.get('_tag') == 'TIER-3' and tier3_earliest is None:
            tier3_earliest = i
        if tier2_earliest is not None and tier3_earliest is not None:
            break
    if tier2_earliest is not None and tier3_earliest is not None:
        tier2_before_tier3 = tier2_earliest < tier3_earliest
        print(f'  TIER-2 before TIER-3: rank #{tier2_earliest+1} vs #{tier3_earliest+1} -> {"PASS" if tier2_before_tier3 else "FAIL"}')

all_pass = top5_tier1 >= 1 and top3_tier3 == 0 and tier2_before_tier3
print(f'\n  OVERALL: {"PASS" if all_pass else "FAIL"}')
