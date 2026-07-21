# -*- coding: utf-8 -*-
"""集成测试：搜索「民法典第35条」验证层级关联检索效果"""
import sys, os, json

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = []
def log(s=""): RESULTS.append(s); print(s)

try:
    from backend.services.vector_store import VectorStoreService
    service = VectorStoreService()
except Exception as e:
    log(f"[ERROR] Service init failed: {e}")
    sys.exit(1)

# ── 主测试 ──
query = "民法典第35条"
log(f"Query: {query}")
log(f"Candidate pool: 20 (config.RERANK_CANDIDATES)")
log("")

results = service.hybrid_search(query, top_k=10, rerank_candidates=20)
log(f"Returned {len(results)} results\n")

tier1_count = 0
non_civil_35_in_top3 = 0

for i, r in enumerate(results, 1):
    content = r['content']
    has_subject = "民法典" in content
    has_sub = ("第35条" in content or "第三十五条" in content)
    
    if has_subject and has_sub:
        tag = "TIER-1 (subject+sub)"
        tier1_count += 1
    elif has_subject:
        tag = "TIER-2 (subject only)"
    elif has_sub:
        tag = "TIER-3 (sub only)"
        if i <= 3:
            non_civil_35_in_top3 += 1
    else:
        tag = "NO MATCH"
    
    preview = content[:80].replace('\n', ' ')
    score = r['score']
    fname = r.get('metadata', {}).get('filename', '?')
    log(f"  [{i:2d}] {tag:25s} score={score:.4f} | {fname}")
    log(f"        {preview}")
    log("")

# 对照：无主体限定
log("-" * 50)
query2 = "第35条"
log(f"Control query: {query2}\n")

results2 = service.hybrid_search(query2, top_k=10, rerank_candidates=20)
if results2:
    for i, r in enumerate(results2[:5], 1):
        content = r['content']
        has_subject = "民法典" in content
        has_sub = ("第35条" in content or "第三十五条" in content)
        
        if has_subject and has_sub:
            tag = "CIVIL+35"
        elif has_subject:
            tag = "CIVIL"
        elif has_sub:
            tag = "ONLY-35"
        else:
            tag = "OTHER"
        
        log(f"  [{i}] {tag} score={r['score']:.4f} | {r['content'][:60].replace(chr(10),' ')}")
    
    civil_count = sum(1 for r in results2[:5] if "民法典" in r['content'])
    log(f"\n  Control check: Top-5 civil related = {civil_count}/5 (should be < 5)")

# ── 验证 ──
t1_ok = tier1_count >= 1
t3_ok = non_civil_35_in_top3 == 0
all_ok = t1_ok and t3_ok

log("=" * 50)
log("INTEGRATION TEST VERIFICATION:")
log(f"  TIER-1 hits in results: {tier1_count} (need >= 1) -> {'PASS' if t1_ok else 'FAIL'}")
log(f"  Non-civil art.35 in top-3: {non_civil_35_in_top3} (need == 0) -> {'PASS' if t3_ok else 'FAIL'}")
log(f"  OVERALL: {'PASS' if all_ok else 'FAIL'}")

# 写入结果文件
try:
    out = r'd:\trae_project02_law\_test_integration_result.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({
            'query': query,
            'tier1_count': tier1_count,
            'non_civil_35_in_top3': non_civil_35_in_top3,
            'passed': all_ok,
            'results_count': len(results),
            'log': '\n'.join(RESULTS)
        }, f, ensure_ascii=False, indent=2)
    log(f"\nResults saved to: {out}")
except Exception as e:
    log(f"\nFile write failed: {e}")
