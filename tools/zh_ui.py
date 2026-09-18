# -*- coding: utf-8 -*-
from pathlib import Path

p = Path('frontend/src/App.vue')
t = p.read_text(encoding='utf-8')
pairs = [
    ("username or password is wrong", "\u7528\u6237\u540d\u6216\u5bc6\u7801\u9519\u8bef"),
    ("search failed", "\u68c0\u7d22\u5931\u8d25"),
    ("cannot create user", "\u65e0\u6cd5\u521b\u5efa\u7528\u6237"),
    ("choose a PDF first", "\u8bf7\u5148\u9009\u62e9 PDF"),
    ("upload failed", "\u4e0a\u4f20\u5931\u8d25"),
    ("'uploaded'", "'\u4e0a\u4f20\u6210\u529f'"),
    ("Lab internal login", "\u4ec5\u9650\u5b9e\u9a8c\u5ba4\u5185\u90e8\u4f7f\u7528"),
    (">Sign in<", ">\u767b\u5f55<"),
    (">Sign out<", ">\u9000\u51fa<"),
    (">Search<", ">\u6587\u732e\u68c0\u7d22<"),
    (">Upload<", ">\u4e0a\u4f20\u8bba\u6587<"),
    ("          Users", "          \u7528\u6237\u7ba1\u7406"),
    ("<h2>Users</h2>", "<h2>\u7528\u6237\u7ba1\u7406</h2>"),
    ('placeholder="keyword"', 'placeholder="\u9898\u540d / \u4f5c\u8005"'),
    ('placeholder="from"', 'placeholder="\u8d77\u59cb\u5e74"'),
    ('placeholder="to"', 'placeholder="\u7ed3\u675f\u5e74"'),
    (">All<", ">\u5168\u90e8<"),
    (">Has PDF<", ">\u6709 PDF<"),
    ("<th>Year</th>", "<th>\u5e74\u4efd</th>"),
    ("<th>Title</th>", "<th>\u9898\u540d</th>"),
    ("<th>Authors</th>", "<th>\u4f5c\u8005</th>"),
    ("<th>Source</th>", "<th>\u6765\u6e90</th>"),
    (">Preview<", ">\u9884\u89c8<"),
    ("No PDF", "\u65e0 PDF"),
    ("No results.", "\u6ca1\u6709\u547d\u4e2d"),
    ("Upload paper", "\u4e0a\u4f20\u8bba\u6587"),
    ("<label>Title", "<label>\u9898\u540d"),
    ("<label>Authors", "<label>\u4f5c\u8005"),
    ("<label>Year", "<label>\u5e74\u4efd"),
    ("<label>Abstract", "<label>\u6458\u8981"),
    ("<label>Username", "<label>\u7528\u6237\u540d"),
    ("<label>Password", "<label>\u5bc6\u7801"),
    ("Save to library", "\u4fdd\u5b58\u5165\u5e93"),
    ("<th>User</th>", "<th>\u7528\u6237</th>"),
    ("<th>Role</th>", "<th>\u89d2\u8272</th>"),
    ("<th>Status</th>", "<th>\u72b6\u6001</th>"),
    ("'active' : 'disabled'", "'\u542f\u7528' : '\u505c\u7528'"),
    ("'Disable' : 'Enable'", "'\u505c\u7528' : '\u542f\u7528'"),
    ("PDF preview", "PDF \u9884\u89c8"),
    (">Close<", ">\u5173\u95ed<"),
    (">Add<", ">\u65b0\u589e<"),
    ("{{ stats.total }} records", "\u9986\u85cf {{ stats.total }}"),
]
for old, new in pairs:
    t = t.replace(old, new)
# brand title appears twice
t = t.replace("PV Lab Papers", "\u5149\u4f0f\u5b9e\u9a8c\u5ba4\u8bba\u6587\u5e93", 2)
p.write_text(t, encoding='utf-8')
print('ok')
