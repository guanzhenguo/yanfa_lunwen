# -*- coding: utf-8 -*-
from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'App.vue'
text = p.read_text(encoding='utf-8')
text = text.replace(
    '            用户管理??????????',
    '            \u542f\u7528\u540c\u6b65\uff08\u5f53\u524d\u4e0d\u4f1a\u771f\u6b63\u5199\u5165\uff09',
)
text = text.replace(
    '<p v-if="!topics.length" class="hint">????????????????????</p>',
    '<p v-if="!topics.length" class="hint">\u5c1a\u65e0\u5173\u952e\u8bcd\u3002\u4e0a\u4f20\u6216\u4e0b\u8f7d\u8bba\u6587\u540e\u4f1a\u81ea\u52a8\u51fa\u73b0\u3002</p>',
)
text = text.replace(
    "                    {{ user.active ? '\u542f\u7528' : '\u505c\u7528' }}",
    "                    {{ user.active ? '\u505c\u7528' : '\u542f\u7528' }}",
)
text = text.replace(
    '''            @click="reviewGraph('approved')"
            >
              \u7528\u6237\u7ba1\u7406
            </button>''',
    '''            @click="reviewGraph('approved')"
            >
              \u5ba1\u6838\u901a\u8fc7
            </button>''',
)
p.write_text(text, encoding='utf-8')
sample = p.read_text(encoding='utf-8')
print('sync_ok', '\u542f\u7528\u540c\u6b65' in sample)
print('approve_ok', '\u5ba1\u6838\u901a\u8fc7' in sample)
print('qmarks', sample.count('?'))
print('garbled_user', '用户管理??????????' in sample)
