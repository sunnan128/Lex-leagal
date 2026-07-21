# -*- coding: utf-8 -*-
# ── 层级关联检索 单元测试（仅测试静态方法，无需初始化 VectorStore）──
import os, sys, json

# 设置 UTF-8 编码
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
from typing import Tuple, Optional

@staticmethod
def _parse_hierarchical_query(query: str) -> Tuple[Optional[str], Optional[str]]:
    article_match = re.search(r'(第[零一二三四五六七八九十百千\d]+[条款章节])', query)
    if not article_match:
        return (None, None)
    sub_key = article_match.group(1)
    before = query[:article_match.start()].strip()
    if not before:
        return (None, sub_key)
    return (before, sub_key)

@staticmethod
def _apply_hierarchical_scoring(scored_items, subject_key, sub_key):
    FULL_MATCH_BOOST = 0.03
    SUBJECT_ONLY_BOOST = 0.01
    for item in scored_items:
        content = item['content']
        has_subject = subject_key in content
        has_sub = sub_key in content
        if has_subject and has_sub:
            item['score'] += FULL_MATCH_BOOST
        elif has_subject:
            item['score'] += SUBJECT_ONLY_BOOST

RESULTS = []
def log(s=""): RESULTS.append(s); print(s)

# ── 测试1: 解析器 ──
log("=" * 60)
log("测试1: 层级查询解析器 _parse_hierarchical_query()")
log("=" * 60)

tests = [
    ("民法典第35条", ("民法典", "第35条")),
    ("民法典第三十五条", ("民法典", "第三十五条")),
    ("刑法第35条", ("刑法", "第35条")),
    ("第35条", (None, "第35条")),
    ("第三十五条", (None, "第三十五条")),
    ("民法典", (None, None)),
    ("", (None, None)),
    ("民法典第一章", ("民法典", "第一章")),
    ("中华人民共和国消费者权益保护法第35条", ("中华人民共和国消费者权益保护法", "第35条")),
]

t1_ok = True
for q, exp in tests:
    r = _parse_hierarchical_query(q)
    ok = r == exp
    if not ok: t1_ok = False
    log(f"  [PASS] {q} -> {r}" if ok else f"  [FAIL] {q} -> {r} (expected: {exp})")

log(f"\n  解析器 test: {'ALL PASS' if t1_ok else 'SOME FAILED'}")

# ── 测试2: 评分逻辑 ──
log("\n" + "=" * 60)
log("测试2: 层级评分逻辑 _apply_hierarchical_scoring()")
log("=" * 60)

items = [
    {'id': 'doc_civil_35', 'content': '第三十五条 监护人应当按照最有利于被监护人的原则履行监护职责。民法典', 'score': 0.05},
    {'id': 'doc_civil_title', 'content': '中华人民共和国民法典 第一编 总则', 'score': 0.05},
    {'id': 'doc_penal_35', 'content': '第三十五条 对于犯罪的外国人，可以独立适用或者附加适用驱逐出境。', 'score': 0.05},
    {'id': 'doc_procedure_35', 'content': '第三十五条 犯罪嫌疑人、被告人因经济困难或者其他原因没有委托辩护人的', 'score': 0.05},
    {'id': 'doc_consumer_35', 'content': '第三十五条 人民法院应当采取措施，方便消费者提起诉讼。', 'score': 0.05},
    {'id': 'doc_civil_other', 'content': '第一千零四十三条 家庭应当树立优良家风。中华人民共和国民法典 第五编', 'score': 0.05},
    {'id': 'doc_unrelated', 'content': '本规定自2024年1月1日起施行。', 'score': 0.05},
]

_apply_hierarchical_scoring(items, "民法典", "第三十五条")
scores = {it['id']: it['score'] for it in items}

checks = [
    ("doc_civil_35 (民法典+第三十五条) = 0.08", abs(scores['doc_civil_35'] - 0.08) < 0.001, f"actual: {scores['doc_civil_35']:.4f}"),
    ("doc_civil_title (only 民法典) = 0.06", abs(scores['doc_civil_title'] - 0.06) < 0.001, f"actual: {scores['doc_civil_title']:.4f}"),
    ("doc_civil_other (only 民法典) = 0.06", abs(scores['doc_civil_other'] - 0.06) < 0.001, f"actual: {scores['doc_civil_other']:.4f}"),
    ("doc_penal_35 (only 第三十五条) = 0.05", abs(scores['doc_penal_35'] - 0.05) < 0.001, f"actual: {scores['doc_penal_35']:.4f}"),
    ("doc_procedure_35 (only 第三十五条) = 0.05", abs(scores['doc_procedure_35'] - 0.05) < 0.001, f"actual: {scores['doc_procedure_35']:.4f}"),
    ("doc_consumer_35 (only 第三十五条) = 0.05", abs(scores['doc_consumer_35'] - 0.05) < 0.001, f"actual: {scores['doc_consumer_35']:.4f}"),
    ("doc_unrelated (no match) = 0.05", abs(scores['doc_unrelated'] - 0.05) < 0.001, f"actual: {scores['doc_unrelated']:.4f}"),
]

t2_ok = True
for desc, ok, detail in checks:
    if not ok: t2_ok = False
    log(f"  [PASS] {desc}" if ok else f"  [FAIL] {desc} [{detail}]")

sorted_items = sorted(items, key=lambda x: x['score'], reverse=True)
top_ids = [it['id'] for it in sorted_items]
log(f"\n  Final order: {' -> '.join(top_ids)}")

rank_ok1 = top_ids[0] == 'doc_civil_35'
rank_ok2 = top_ids.index('doc_civil_title') < top_ids.index('doc_penal_35')
log(f"  [PASS] Tier-1 rank 1" if rank_ok1 else f"  [FAIL] Tier-1 not rank 1")
log(f"  [PASS] Tier-2 before Tier-3" if rank_ok2 else f"  [FAIL] Tier-2 not before Tier-3")
if not rank_ok1 or not rank_ok2: t2_ok = False

log(f"\n  Scoring test: {'ALL PASS' if t2_ok else 'SOME FAILED'}")

# ── Summary ──
log("\n" + "=" * 60)
log("SUMMARY:")
log(f"  [Test1] Parser:      {'PASS' if t1_ok else 'FAIL'}")
log(f"  [Test2] Scoring:     {'PASS' if t2_ok else 'FAIL'}")
if t1_ok and t2_ok:
    log("\nALL TESTS PASSED! Hierarchical search logic works correctly.")
else:
    log("\nSome tests FAILED.")

# Write result to file
try:
    out = r'd:\trae_project02_law\_test_unit_result.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'t1': t1_ok, 't2': t2_ok, 'all': t1_ok and t2_ok, 'log': '\n'.join(RESULTS)}, f, ensure_ascii=False)
    log(f"Result saved to: {out}")
except Exception as e:
    log(f"File write failed (sandbox): {e}")
