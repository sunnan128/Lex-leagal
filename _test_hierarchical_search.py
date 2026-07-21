# -*- coding: utf-8 -*-
"""Final validation test for hierarchical search system.
Run: python _test_hierarchical_search.py
"""
import pickle, re, sys, json

# ── 辅助函数 (同 vector_store.py 一致) ──
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

def search_by_subject_metadata(subject_key, docs):
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

# ── 加载数据 ──
path = r'd:\trae_project02_law\backend\data\bm25_index.pkl'
with open(path, 'rb') as f:
    data = pickle.load(f)
docs = data['documents']

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

PASS = 0; FAIL = 0
def check(desc, ok, detail=''):
    global PASS, FAIL
    if ok: PASS += 1
    else: FAIL += 1
    print(f'  [{"PASS" if ok else "FAIL"}] {desc}' + (f' -> {detail}' if not ok else ''))

# ═══════════════════════════════════
print('=' * 60)
print('TEST 1: Query Parser (_parse_hierarchical_query)')
print('=' * 60)
check('empty string -> (None,None)', parse_hierarchical_query('') == (None,None))
check('free text -> (None,None)', parse_hierarchical_query('民法典') == (None,None))
check('art.35 only -> (None,第35条)', parse_hierarchical_query('第35条') == (None,'第35条'))
check('chinese art.35 only -> (None,第三十五条)', parse_hierarchical_query('第三十五条') == (None,'第三十五条'))
check('civil+art.35 -> (民法典,第35条)', parse_hierarchical_query('民法典第35条') == ('民法典','第35条'))
check('civil+chinese art.35 -> (民法典,第三十五条)', parse_hierarchical_query('民法典第三十五条') == ('民法典','第三十五条'))
check('chapter -> (民法典,第一章)', parse_hierarchical_query('民法典第一章') == ('民法典','第一章'))
check('long name -> (消费者权益保护法,第35条)', parse_hierarchical_query('消费者权益保护法第35条') == ('消费者权益保护法','第35条'))

# ═══════════════════════════════════
print('\n' + '=' * 60)
print('TEST 2: Article Number Normalization')
print('=' * 60)
check('35 -> 三十五', _normalize_article_variant('第35条') == '第三十五条')
check('1 -> 一', _normalize_article_variant('第1条') == '第一条')
check('10 -> 十', _normalize_article_variant('第10条') == '第十条')
check('100 -> 一百', _normalize_article_variant('第100条') == '第一百条')
check('35章 -> 第三十五章', _normalize_article_variant('第35章') == '第三十五章')
check('三十五 -> 35', _normalize_article_variant('第三十五条') == '第35条')
check('十 -> 10', _normalize_article_variant('第十条') == '第10条')

# ═══════════════════════════════════
print('\n' + '=' * 60)
print('TEST 3: Hierarchical Scoring Logic')
print('=' * 60)
items = [
    {'id':'a', 'content':'第三十五条 监护人 民法典', 'score':0.05},
    {'id':'b', 'content':'民法典 第一编 总则', 'score':0.05},
    {'id':'c', 'content':'第三十五条 对于犯罪的外国人', 'score':0.05},
    {'id':'d', 'content':'无关文档', 'score':0.05},
]
apply_hierarchical_scoring(items, '民法典', '第三十五条')
scores = {i['id']:i['score'] for i in items}
check('tier-1 (subject+sub) = 0.08', abs(scores['a']-0.08)<0.001, f'{scores["a"]:.4f}')
check('tier-2 (subject only) = 0.06', abs(scores['b']-0.06)<0.001, f'{scores["b"]:.4f}')
check('tier-3 (sub only) = 0.05', abs(scores['c']-0.05)<0.001, f'{scores["c"]:.4f}')
check('none = 0.05', abs(scores['d']-0.05)<0.001, f'{scores["d"]:.4f}')

# ═══════════════════════════════════
print('\n' + '=' * 60)
print('TEST 4: Integration - Search "民法典第35条"')
print('=' * 60)

# RRF simulation
RRF_K = 20
kw_results = keyword_search('民法典第35条', top_k=20)
scored = []
for i, r in enumerate(kw_results):
    rrf = 1.0 / (RRF_K + i + 1)
    scored.append({'id':r['id'], 'content':r['content'], 'metadata':r['metadata'], 'score':rrf})

# Subject metadata supplement
subject_key, sub_key = parse_hierarchical_query('民法典第35条')
sub_docs = search_by_subject_metadata(subject_key, docs)
existing = {s['id'] for s in scored}
for sd in sub_docs:
    if sd['id'] not in existing:
        sd['score'] = 0.02
        scored.append(sd)

# Apply scoring
apply_hierarchical_scoring(scored, subject_key, sub_key)
scored.sort(key=lambda x: x['score'], reverse=True)

tier1_top5 = sum(1 for r in scored[:5] if r.get('_tag') == 'TIER-1')
tier3_top3 = sum(1 for r in scored[:3] if r.get('_tag') == 'TIER-3')

check(f'TIER-1 in top-5 >= 1', tier1_top5 >= 1, f'actual: {tier1_top5}')
check(f'TIER-3 in top-3 == 0', tier3_top3 == 0, f'actual: {tier3_top3}')

# Print top 5
print('\n  Top-5 results:')
for i, r in enumerate(scored[:5], 1):
    tag = r.get('_tag', '?')
    meta = r.get('metadata', {})
    fn = (meta.get('filename','?') or '?') if isinstance(meta,dict) else '?'
    content = r['content'][:60].replace('\n',' ')
    print(f'    #{i} [{tag}] {r["score"]:.4f} | {fn[:35]}')
    print(f'       {content}')
    print()

# ═══════════════════════════════════
print('=' * 60)
print(f'SUMMARY: {PASS} passed, {FAIL} failed out of {PASS+FAIL}')
print('=' * 60)
if FAIL == 0:
    print('ALL TESTS PASSED - Hierarchical search system is working correctly!\n')
else:
    print(f'{FAIL} tests FAILED - needs review.\n')

# Save result
result = {
    'test_results': {'passed': PASS, 'failed': FAIL, 'total': PASS+FAIL},
    'top5': [{'rank':i+1, 'tag':r.get('_tag'), 'score':round(r['score'],4),
              'filename':((r.get('metadata',{}) or {}).get('filename','?') or '?')[:40],
              'content':r['content'][:80]} for i,r in enumerate(scored[:5])]
}
out = r'd:\trae_project02_law\_test_final_result.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f'Result saved to: {out}')
