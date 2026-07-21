# -*- coding: utf-8 -*-
import pickle, os, sys, json

path = r'd:\trae_project02_law\backend\data\bm25_index.pkl'
with open(path, 'rb') as f:
    data = pickle.load(f)
docs = data['documents']

print(f'Total documents: {len(docs)}')

civil_total = sum(1 for d in docs if '民法典' in d['content'])
art35_total = sum(1 for d in docs if '第三十五条' in d['content'] or '第35条' in d['content'])
civil_art35 = sum(1 for d in docs if ('民法典' in d['content']) and ('第三十五条' in d['content'] or '第35条' in d['content']))
non_civil_art35 = sum(1 for d in docs if ('民法典' not in d['content']) and ('第三十五条' in d['content'] or '第35条' in d['content']))

print(f'civil: {civil_total}')
print(f'art35: {art35_total}')
print(f'  civil+art35: {civil_art35}')
print(f'  non-civil art35: {non_civil_art35}')

count = 0
for d in docs:
    if '民法典' in d['content'] and ('第三十五条' in d['content'] or '第35条' in d['content']):
        if count < 2:
            print(f'  Civil+35: {d["content"][:120]}')
            count += 1

count = 0
for d in docs:
    if '民法典' not in d['content'] and ('第三十五条' in d['content'] or '第35条' in d['content']):
        if count < 3:
            meta = d.get('metadata', {})
            fname = meta.get('filename', '?') if isinstance(meta, dict) else '?'
            print(f'  Non-civil35: {fname} | {d["content"][:120]}')
            count += 1

print('Done.')
