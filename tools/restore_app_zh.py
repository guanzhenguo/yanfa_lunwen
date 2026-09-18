# -*- coding: utf-8 -*-
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'App.vue'

FIXES = [
    ("pending_review: '???'", "pending_review: '\u5f85\u5ba1\u6838'"),
    ("approved: '???'", "approved: '\u5df2\u901a\u8fc7'"),
    ("rejected: '???'", "rejected: '\u5df2\u9a73\u56de'"),
    ("error: '????'", "error: '\u62bd\u53d6\u5931\u8d25'"),
    ("}[status] || '???'", "}[status] || '\u672a\u62bd\u53d6'"),
    ("metadata_parse: '???????'", "metadata_parse: '\u4e0a\u4f20\u5143\u6570\u636e\u89e3\u6790'"),
    ("knowledge_extract: '??????'", "knowledge_extract: '\u77e5\u8bc6\u56fe\u8c31\u62bd\u53d6',\n      knowledge_qa: '\u6587\u732e\u95ee\u7b54'"),
    ("loginError.value = '????????'", "loginError.value = '\u7528\u6237\u540d\u6216\u5bc6\u7801\u9519\u8bef'"),
    ("throw new Error('????')", "throw new Error('\u68c0\u7d22\u5931\u8d25')"),
    ("error.value = err.message || '????'", "error.value = err.message || '\u68c0\u7d22\u5931\u8d25'"),
    ("body.detail || '???? AI ??'", "body.detail || '\u65e0\u6cd5\u4fdd\u5b58 AI \u914d\u7f6e'"),
    ("settingsMsg.value = 'AI ????? config.toml'", "settingsMsg.value = 'AI \u914d\u7f6e\u5df2\u5199\u5165 config.toml'"),
    ("body.detail || '???? Neo4j ??'", "body.detail || '\u65e0\u6cd5\u4fdd\u5b58 Neo4j \u914d\u7f6e'"),
    ("settingsMsg.value = 'Neo4j ????? config.toml???????'", "settingsMsg.value = 'Neo4j \u914d\u7f6e\u5df2\u5199\u5165 config.toml\uff0c\u540c\u6b65\u5c1a\u672a\u542f\u7528'"),
    ("settingsMsg.value = body.detail || '???????'\n    return\n  }\n  settingsMsg.value = `???????${promptLabel", "settingsMsg.value = body.detail || '\u65e0\u6cd5\u4fdd\u5b58\u63d0\u793a\u8bcd'\n    return\n  }\n  settingsMsg.value = `\u5df2\u4fdd\u5b58\u63d0\u793a\u8bcd\uff1a${promptLabel"),
    ("settingsMsg.value = body.detail || '???????'\n    return\n  }\n  settingsMsg.value = `???????${item.name}`", "settingsMsg.value = body.detail || '\u65e0\u6cd5\u4fdd\u5b58\u5173\u952e\u8bcd'\n    return\n  }\n  settingsMsg.value = `\u5df2\u4fdd\u5b58\u5173\u952e\u8bcd\uff1a${item.name}`"),
    ("userMsg.value = body.detail || '??????'", "userMsg.value = body.detail || '\u65e0\u6cd5\u521b\u5efa\u7528\u6237'"),
    ("uploadMsg.value = '???? PDF??????????'", "uploadMsg.value = '\u8bf7\u5148\u9009\u62e9 PDF\uff0c\u6216\u586b\u5199\u9898\u540d\u540e\u518d\u89e3\u6790'"),
    ("uploadMsg.value = body.detail || '????'\n      return\n    }\n    upload.value.title", "uploadMsg.value = body.detail || '\u89e3\u6790\u5931\u8d25'\n      return\n    }\n    upload.value.title"),
    ("uploadMsg.value = '?? AI ?????????'", "uploadMsg.value = '\u5df2\u7528 AI \u586b\u5165\uff0c\u8bf7\u6838\u5bf9\u540e\u4fdd\u5b58'"),
    ("uploadMsg.value = `AI ????????????${body.ai_error}`", "uploadMsg.value = `AI \u4e0d\u53ef\u7528\uff0c\u5df2\u6309\u6587\u4ef6\u540d\u586b\u5165\u3002${body.ai_error}`"),
    ("uploadMsg.value = '????? AI????????????????????'", "uploadMsg.value = '\u5f53\u524d\u672a\u914d\u7f6e AI\uff0c\u5df2\u6309\u6587\u4ef6\u540d\u586b\u5165\u9898\u540d\uff0c\u5176\u4f59\u5b57\u6bb5\u8bf7\u624b\u5de5\u8865\u5145'"),
    ("uploadMsg.value = '???? PDF'", "uploadMsg.value = '\u8bf7\u5148\u9009\u62e9 PDF'"),
    ("uploadMsg.value = body.detail || '????'\n    return\n  }\n  upload.value = emptyUpload()", "uploadMsg.value = body.detail || '\u4e0a\u4f20\u5931\u8d25'\n    return\n  }\n  upload.value = emptyUpload()"),
    ("uploadMsg.value = '????'\n  await loadStats()", "uploadMsg.value = '\u4e0a\u4f20\u6210\u529f'\n  await loadStats()"),
    ("error.value = body.detail || '?????????'", "error.value = body.detail || '\u65e0\u6cd5\u66f4\u65b0\u8bba\u6587\u5173\u952e\u8bcd'"),
    ("graphMsg.value = body.detail || '????'\n      return\n    }\n    graphData.value = body", "graphMsg.value = body.detail || '\u62bd\u53d6\u5931\u8d25'\n      return\n    }\n    graphData.value = body"),
    ("graphMsg.value = `AI ????????????????????????${body.run.error}`", "graphMsg.value = `AI \u8c03\u7528\u5931\u8d25\uff0c\u5df2\u5199\u5165\u7cfb\u7edf\u5c5e\u6027\u4e0e\u542f\u53d1\u5f0f\u5173\u952e\u8bcd\uff0c\u8bf7\u5ba1\u6838\u3002${body.run.error}`"),
    ("graphMsg.value = '?????????????????'", "graphMsg.value = '\u62bd\u53d6\u5b8c\u6210\uff0c\u8bf7\u5ba1\u6838\u8282\u70b9\u4e0e\u5173\u7cfb\u540e\u518d\u901a\u8fc7'"),
    ("graphMsg.value = body.detail || '????'\n    return\n  }\n  graphData.value = body", "graphMsg.value = body.detail || '\u5ba1\u6838\u5931\u8d25'\n    return\n  }\n  graphData.value = body"),
    ("graphMsg.value = status === 'approved' ? '?????????? Neo4j' : '???'", "graphMsg.value = status === 'approved' ? '\u5df2\u901a\u8fc7\uff0c\u53ef\u5f85\u540e\u7eed\u540c\u6b65 Neo4j' : '\u5df2\u9a73\u56de'"),
    ("<h1>????????</h1>", "<h1>\u5149\u4f0f\u5b9e\u9a8c\u5ba4\u8bba\u6587\u5e93</h1>"),
    ("<p>?????????</p>", "<p>\u4ec5\u9650\u5b9e\u9a8c\u5ba4\u5185\u90e8\u4f7f\u7528</p>"),
    ("<label>???<input v-model=\"loginUser\"", "<label>\u7528\u6237\u540d<input v-model=\"loginUser\""),
    ("<label>??<input v-model=\"loginPass\"", "<label>\u5bc6\u7801<input v-model=\"loginPass\""),
    (">??</button>\n      <p v-if=\"loginError\"", ">\u767b\u5f55</button>\n      <p v-if=\"loginError\""),
    ("<p>?? {{ stats.total }} / {{ stats.with_pdf }} PDFs</p>", "<p>\u9986\u85cf {{ stats.total }} / {{ stats.with_pdf }} PDFs</p>"),
    ("@click=\"doLogout\">??</button>", "@click=\"doLogout\">\u9000\u51fa</button>"),
    ("page = 'papers'\">????</button>", "page = 'papers'\">\u6587\u732e\u68c0\u7d22</button>"),
    ("page = 'chat'\">????</button>", "page = 'chat'\">\u6587\u732e\u95ee\u7b54</button>"),
    ("page = 'upload'\">????</button>", "page = 'upload'\">\u4e0a\u4f20\u8bba\u6587</button>"),
    ("page = 'settings'\">?????</button>", "page = 'settings'\">\u6a21\u578b\u4e0e\u56fe\u8c31</button>"),
    ("          ????", "          \u7528\u6237\u7ba1\u7406"),
    ('placeholder="?? / ??"', 'placeholder="\u9898\u540d / \u4f5c\u8005"'),
    ('placeholder="???" />\n          <input v-model="yearTo"', 'placeholder="\u8d77\u59cb\u5e74" />\n          <input v-model="yearTo"'),
    ('placeholder="???" />\n          <button class="chip"', 'placeholder="\u7ed3\u675f\u5e74" />\n          <button class="chip"'),
    ("topicId = null\">??</button>", "topicId = null\">\u5168\u90e8</button>"),
    (">? PDF</button>", ">\u6709 PDF</button>"),
    ('<span class="muted">??????</span>', '<span class="muted">\u6309\u5173\u952e\u8bcd\u5206\u7c7b</span>'),
    ('<span v-if="!topics.length" class="hint">????????????????????</span>', '<span v-if="!topics.length" class="hint">\u5c1a\u65e0\u5173\u952e\u8bcd\u3002\u4e0a\u4f20\u6216\u4e0b\u8f7d\u8bba\u6587\u540e\u4f1a\u81ea\u52a8\u51fa\u73b0\u3002</span>'),
    ("                <th>??</th>\n                <th>??</th>\n                <th>??</th>\n                <th>???</th>\n                <th>??</th>", "                <th>\u5e74\u4efd</th>\n                <th>\u9898\u540d</th>\n                <th>\u4f5c\u8005</th>\n                <th>\u5173\u952e\u8bcd</th>\n                <th>\u6765\u6e90</th>"),
    ('openPreview(item.id)">??</button>', 'openPreview(item.id)">\u9884\u89c8</button>'),
    ('class="muted">? PDF</span>', 'class="muted">\u65e0 PDF</span>'),
    ('openGraph(item)">??</button>', 'openGraph(item)">\u56fe\u8c31</button>'),
    ('openEditKeywords(item)">????</button>', 'openEditKeywords(item)">\u6539\u5173\u952e\u8bcd</button>'),
    ('class="hint">????</p>', 'class="hint">\u6ca1\u6709\u547d\u4e2d</p>'),
    ("          <h2>????</h2>\n          <p class=\"hint\">??????????????DOI??????????????????? AI ????????????</p>", "          <h2>\u4e0a\u4f20\u8bba\u6587</h2>\n          <p class=\"hint\">\u9ed8\u8ba4\u7528\u6587\u4ef6\u540d\u4f5c\u4e3a\u9898\u540d\u3002\u4f5c\u8005\u3001DOI\u3001\u5e74\u4efd\u3001\u6458\u8981\u3001\u5173\u952e\u8bcd\u5747\u53ef\u9009\u586b\uff1b\u4e5f\u53ef\u5148\u70b9 AI \u89e3\u6790\uff0c\u4ece\u6458\u8981\u62bd\u53d6\u5173\u952e\u8bcd\u3002</p>"),
    ("???? {{ settings.ai.model || '???' }} / {{ settings.ai.ready ? '?????' : '???? API Key' }}", "\u5f53\u524d\u6a21\u578b {{ settings.ai.model || '\u672a\u586b\u5199' }} / {{ settings.ai.ready ? '\u5df2\u914d\u7f6e\u5bc6\u94a5' : '\u5c1a\u672a\u586b\u5199 API Key' }}"),
    ('<label>??<input v-model="upload.title" placeholder="????????????"', '<label>\u9898\u540d<input v-model="upload.title" placeholder="\u9009\u62e9\u6587\u4ef6\u540e\u81ea\u52a8\u586b\u5165\u6587\u4ef6\u540d"'),
    ('<label>??????<input v-model="upload.authors"', '<label>\u4f5c\u8005\uff08\u9009\u586b\uff09<input v-model="upload.authors"'),
    ('<label>DOI????<input v-model="upload.doi"', '<label>DOI\uff08\u9009\u586b\uff09<input v-model="upload.doi"'),
    ('<label>??????<input v-model="upload.year"', '<label>\u5e74\u4efd\uff08\u9009\u586b\uff09<input v-model="upload.year"'),
    ('<label>??????<textarea v-model="upload.description"', '<label>\u6458\u8981\uff08\u9009\u586b\uff09<textarea v-model="upload.description"'),
    ('<label>????????????<input v-model="upload.keywords"', '<label>\u5173\u952e\u8bcd\uff08\u9009\u586b\uff0c\u9017\u53f7\u5206\u9694\uff09<input v-model="upload.keywords"'),
    ("parsing ? '???...' : 'AI ?????'", "parsing ? '\u89e3\u6790\u4e2d...' : 'AI \u89e3\u6790\u5e76\u586b\u5165'"),
    ('type="submit">????</button>', 'type="submit">\u4fdd\u5b58\u5165\u5e93</button>'),
    ("          <h2>?????</h2>\n          <p class=\"hint\">??????????????? config.toml????????Neo4j ????????????????</p>", "          <h2>\u6a21\u578b\u4e0e\u56fe\u8c31</h2>\n          <p class=\"hint\">\u5730\u5740\u3001\u6a21\u578b\u540d\u548c\u5bc6\u94a5\u5148\u5199\u5728\u9875\u9762\u4e0e config.toml\uff0c\u540e\u7eed\u81ea\u884c\u586b\u5199\u3002Neo4j \u4ec5\u9884\u7559\uff0c\u5ba1\u6838\u901a\u8fc7\u540e\u624d\u4f1a\u51c6\u5907\u540c\u6b65\u3002</p>"),
    ('<label>API ??<input v-model="settings.ai.base_url"', '<label>API \u5730\u5740<input v-model="settings.ai.base_url"'),
    ('<label>????<input v-model="settings.ai.model"', '<label>\u6a21\u578b\u540d\u79f0<input v-model="settings.ai.model"'),
    ('<label>?????<input v-model.number="settings.ai.timeout_seconds"', '<label>\u8d85\u65f6\uff08\u79d2\uff09<input v-model.number="settings.ai.timeout_seconds"'),
    ('@click="saveAi">?? AI ??</button>', '@click="saveAi">\u4fdd\u5b58 AI \u914d\u7f6e</button>'),
    ('<h3>Neo4j??????</h3>', '<h3>Neo4j\uff08\u540e\u671f\u540c\u6b65\uff09</h3>'),
    ("            ??????????????", "            \u542f\u7528\u540c\u6b65\uff08\u5f53\u524d\u4e0d\u4f1a\u771f\u6b63\u5199\u5165\uff09"),
    ('<label>??<input v-model="settings.neo4j.user"', '<label>\u7528\u6237<input v-model="settings.neo4j.user"'),
    ('<label>??<input v-model="settings.neo4j.password"', '<label>\u5bc6\u7801<input v-model="settings.neo4j.password"'),
    ('<label>???<input v-model="settings.neo4j.database"', '<label>\u6570\u636e\u5e93<input v-model="settings.neo4j.database"'),
    ('@click="saveNeo4j">?? Neo4j ??</button>', '@click="saveNeo4j">\u4fdd\u5b58 Neo4j \u914d\u7f6e</button>'),
    ("          <h3>?????</h3>\n          <p class=\"hint\">?????????????????????</p>", "          <h3>\u62bd\u53d6\u63d0\u793a\u8bcd</h3>\n          <p class=\"hint\">\u4ec5\u7ba1\u7406\u5458\u53ef\u4fee\u6539\u3002\u666e\u901a\u7528\u6237\u53ef\u67e5\u770b\u5f53\u524d\u63d0\u793a\u8bcd\u3002</p>"),
    ('@click="savePrompt(item)">??????</button>', '@click="savePrompt(item)">\u4fdd\u5b58\u8be5\u63d0\u793a\u8bcd</button>'),
    ("          <h3>????????</h3>\n          <p class=\"hint\">???????????????????????????????????????????????????</p>", "          <h3>\u5173\u952e\u8bcd\u62bd\u53d6\u63d0\u793a\u8bcd</h3>\n          <p class=\"hint\">\u76f8\u540c\u5173\u952e\u8bcd\u7684\u8bba\u6587\u5171\u7528\u4e00\u6761\u62bd\u53d6\u63d0\u793a\u8bcd\u3002\u7559\u7a7a\u5219\u4f7f\u7528\u9ed8\u8ba4\u63d0\u793a\u8bcd\u3002\u63d0\u793a\u8bcd\u4ec5\u7ba1\u7406\u5458\u53ef\u6539\uff1b\u5173\u952e\u8bcd\u540d\u79f0\u6240\u6709\u7528\u6237\u53ef\u6539\u3002</p>"),
    ('placeholder="??????????????"', 'placeholder="\u7559\u7a7a\u5219\u4f7f\u7528\u9ed8\u8ba4\u77e5\u8bc6\u56fe\u8c31\u63d0\u793a\u8bcd"'),
    ('@click="saveKeywordPrompt(item)">?????</button>', '@click="saveKeywordPrompt(item)">\u4fdd\u5b58\u5173\u952e\u8bcd</button>'),
    ("          <h2>????</h2>\n          <div class=\"row\">", "          <h2>\u7528\u6237\u7ba1\u7406</h2>\n          <div class=\"row\">"),
    ('type="submit">??</button>', 'type="submit">\u65b0\u589e</button>'),
    ("                <th>??</th>\n                <th>??</th>\n                <th>??</th>\n                <th></th>", "                <th>\u7528\u6237</th>\n                <th>\u89d2\u8272</th>\n                <th>\u72b6\u6001</th>\n                <th></th>"),
    ("                <td>{{ user.active ? '??' : '??' }}</td>", "                <td>{{ user.active ? '\u542f\u7528' : '\u505c\u7528' }}</td>"),
    ("                    {{ user.active ? '??' : '??' }}", "                    {{ user.active ? '\u505c\u7528' : '\u542f\u7528' }}"),
    ("<span>PDF ??</span>", "<span>PDF \u9884\u89c8</span>"),
    ('title="PDF ??"', 'title="PDF \u9884\u89c8"'),
    ("<span>????? / {{ editKw.title }}</span>", "<span>\u4fee\u6539\u5173\u952e\u8bcd / {{ editKw.title }}</span>"),
    ('<p class="hint">??????????????????????????</p>', '<p class="hint">\u591a\u4e2a\u5173\u952e\u8bcd\u7528\u9017\u53f7\u5206\u9694\u3002\u76f8\u540c\u540d\u79f0\u4f1a\u5408\u5e76\u4e3a\u540c\u4e00\u4e2a\u5173\u952e\u8bcd\u3002</p>'),
    ('<label>???<input v-model="editKw.text"', '<label>\u5173\u952e\u8bcd<input v-model="editKw.text"'),
    ('type="submit">?????</button>', 'type="submit">\u4fdd\u5b58\u5173\u952e\u8bcd</button>'),
    ("<span>???? / {{ graphPaper.title }}</span>", "<span>\u77e5\u8bc6\u56fe\u8c31 / {{ graphPaper.title }}</span>"),
    ("              ???{{ statusLabel(graphData.run?.status) }}", "              \u72b6\u6001\uff1a{{ statusLabel(graphData.run?.status) }}"),
    ("> / ?? {{ graphData.run.model }}</span>", "> / \u6a21\u578b {{ graphData.run.model }}</span>"),
    ("extracting ? '???...' : 'AI ????'", "extracting ? '\u62bd\u53d6\u4e2d...' : 'AI \u4e00\u952e\u62bd\u53d6'"),
    ("              ????", "              \u5ba1\u6838\u901a\u8fc7"),
    ("              ??\n            </button>", "              \u9a73\u56de\n            </button>"),
    ('placeholder="????????"', 'placeholder="\u5ba1\u6838\u610f\u89c1\uff08\u9009\u586b\uff09"'),
    ('<p v-else class="hint">????????AI ???????????????????????????????????????????</p>', '<p v-else class="hint">\u5c1a\u672a\u62bd\u53d6\u3002\u70b9\u51fb\u300cAI \u4e00\u952e\u62bd\u53d6\u300d\u540e\u5c06\u5199\u5165\u7cfb\u7edf\u5c5e\u6027\uff08\u65f6\u95f4\u3001\u673a\u6784\u3001\u4f5c\u8005\u3001\u6587\u4ef6\u540d\u3001\u6458\u8981\uff09\u53ca\u5173\u952e\u8bcd\u5173\u7cfb\uff0c\u5e76\u5728\u6b64\u9884\u89c8\u3002</p>'),
    (">??</button>", ">\u5173\u95ed</button>"),
]


def main() -> None:
    text = APP.read_text(encoding='utf-8')
    missing = []
    for old, new in FIXES:
        if old not in text:
            missing.append(old[:80])
            continue
        text = text.replace(old, new)

    chat_section = (
        "      <section v-else-if=\"page === 'chat'\" class=\"stage chat-stage\">\n"
        "        <ChatPage @preview=\"openPreview\" @graph=\"openGraph\" />\n"
        "      </section>\n"
    )
    if "page === 'chat'" in text and 'chat-stage' not in text:
        needle = "      <section v-else-if=\"page === 'upload'\" class=\"stage form-stage\">"
        if needle not in text:
            missing.append('chat section anchor')
        else:
            text = text.replace(needle, chat_section + needle, 1)

    APP.write_text(text, encoding='utf-8')
    leftover_q = text.count('?')
    print('missing', len(missing))
    for item in missing:
        print(' -', repr(item))
    print('qmarks', leftover_q)
    print('title_ok', '\u5149\u4f0f\u5b9e\u9a8c\u5ba4\u8bba\u6587\u5e93' in text)
    print('chat_nav', '\u6587\u732e\u95ee\u7b54' in text)
    print('chat_page', 'chat-stage' in text)
    print('import_ok', "import ChatPage from './ChatPage.vue'" in text)


if __name__ == '__main__':
    main()
