# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'frontend' / 'src' / 'App.placeholders.vue'
APP = ROOT / 'frontend' / 'src' / 'App.vue'

PAIRS = [
    ('__ST_PENDING__', '\u5f85\u5ba1\u6838'),
    ('__ST_APPROVED__', '\u5df2\u901a\u8fc7'),
    ('__ST_REJECTED__', '\u5df2\u9a73\u56de'),
    ('__ST_ERROR__', '\u62bd\u53d6\u5931\u8d25'),
    ('__ST_NONE__', '\u672a\u62bd\u53d6'),
    ('__PR_META__', '\u4e0a\u4f20\u5143\u6570\u636e\u89e3\u6790'),
    ('__PR_KG__', '\u77e5\u8bc6\u56fe\u8c31\u62bd\u53d6'),
    ('__MSG_LOGIN_FAIL__', '\u7528\u6237\u540d\u6216\u5bc6\u7801\u9519\u8bef'),
    ('__MSG_SEARCH_FAIL__', '\u68c0\u7d22\u5931\u8d25'),
    ('__MSG_AI_SAVE_FAIL__', '\u65e0\u6cd5\u4fdd\u5b58 AI \u914d\u7f6e'),
    ('__MSG_AI_SAVED__', 'AI \u914d\u7f6e\u5df2\u5199\u5165 config.toml'),
    ('__MSG_NEO_SAVE_FAIL__', '\u65e0\u6cd5\u4fdd\u5b58 Neo4j \u914d\u7f6e'),
    ('__MSG_NEO_SAVED__', 'Neo4j \u914d\u7f6e\u5df2\u5199\u5165 config.toml\uff0c\u540c\u6b65\u5c1a\u672a\u542f\u7528'),
    ('__MSG_PROMPT_SAVE_FAIL__', '\u65e0\u6cd5\u4fdd\u5b58\u63d0\u793a\u8bcd'),
    ('__MSG_PROMPT_SAVED__', '\u5df2\u4fdd\u5b58\u63d0\u793a\u8bcd\uff1a'),
    ('__MSG_USER_CREATE_FAIL__', '\u65e0\u6cd5\u521b\u5efa\u7528\u6237'),
    ('__MSG_PARSE_NEED_FILE__', '\u8bf7\u5148\u9009\u62e9 PDF\uff0c\u6216\u586b\u5199\u9898\u540d\u540e\u518d\u89e3\u6790'),
    ('__MSG_PARSE_FAIL__', '\u89e3\u6790\u5931\u8d25'),
    ('__MSG_PARSE_AI_OK__', '\u5df2\u7528 AI \u586b\u5165\uff0c\u8bf7\u6838\u5bf9\u540e\u4fdd\u5b58'),
    ('__MSG_PARSE_AI_ERR__', 'AI \u4e0d\u53ef\u7528\uff0c\u5df2\u6309\u6587\u4ef6\u540d\u586b\u5165\u3002'),
    ('__MSG_PARSE_NO_AI__', '\u5f53\u524d\u672a\u914d\u7f6e AI\uff0c\u5df2\u6309\u6587\u4ef6\u540d\u586b\u5165\u9898\u540d\uff0c\u5176\u4f59\u5b57\u6bb5\u8bf7\u624b\u5de5\u8865\u5145'),
    ('__MSG_NEED_PDF__', '\u8bf7\u5148\u9009\u62e9 PDF'),
    ('__MSG_UPLOAD_FAIL__', '\u4e0a\u4f20\u5931\u8d25'),
    ('__MSG_UPLOAD_OK__', '\u4e0a\u4f20\u6210\u529f'),
    ('__MSG_EXTRACT_FAIL__', '\u62bd\u53d6\u5931\u8d25'),
    ('__MSG_EXTRACT_AI_ERR__', 'AI \u8c03\u7528\u5931\u8d25\uff0c\u5df2\u5199\u5165\u7cfb\u7edf\u5c5e\u6027\u4e0e\u542f\u53d1\u5f0f\u5173\u952e\u8bcd\uff0c\u8bf7\u5ba1\u6838\u3002'),
    ('__MSG_EXTRACT_OK__', '\u62bd\u53d6\u5b8c\u6210\uff0c\u8bf7\u5ba1\u6838\u8282\u70b9\u4e0e\u5173\u7cfb\u540e\u518d\u901a\u8fc7'),
    ('__MSG_REVIEW_FAIL__', '\u5ba1\u6838\u5931\u8d25'),
    ('__MSG_REVIEW_OK__', '\u5df2\u901a\u8fc7\uff0c\u53ef\u5f85\u540e\u7eed\u540c\u6b65 Neo4j'),
    ('__MSG_REVIEW_NO__', '\u5df2\u9a73\u56de'),
    ('__APP_TITLE__', '\u5149\u4f0f\u5b9e\u9a8c\u5ba4\u8bba\u6587\u5e93'),
    ('__LOGIN_SUB__', '\u4ec5\u9650\u5b9e\u9a8c\u5ba4\u5185\u90e8\u4f7f\u7528'),
    ('__LBL_USERNAME__', '\u7528\u6237\u540d'),
    ('__LBL_PASSWORD__', '\u5bc6\u7801'),
    ('__BTN_LOGIN__', '\u767b\u5f55'),
    ('__STATS_PREFIX__', '\u9986\u85cf'),
    ('__BTN_LOGOUT__', '\u9000\u51fa'),
    ('__NAV_SEARCH__', '\u6587\u732e\u68c0\u7d22'),
    ('__NAV_UPLOAD__', '\u4e0a\u4f20\u8bba\u6587'),
    ('__NAV_SETTINGS__', '\u6a21\u578b\u4e0e\u56fe\u8c31'),
    ('__NAV_USERS__', '\u7528\u6237\u7ba1\u7406'),
    ('__PH_KEYWORD__', '\u9898\u540d / \u4f5c\u8005'),
    ('__PH_YEAR_FROM__', '\u8d77\u59cb\u5e74'),
    ('__PH_YEAR_TO__', '\u7ed3\u675f\u5e74'),
    ('__CHIP_ALL__', '\u5168\u90e8'),
    ('__CHIP_PDF__', '\u6709 PDF'),
    ('__TH_YEAR__', '\u5e74\u4efd'),
    ('__TH_TITLE__', '\u9898\u540d'),
    ('__TH_AUTHORS__', '\u4f5c\u8005'),
    ('__TH_KEYWORDS__', '\u5173\u952e\u8bcd'),
    ('__TH_SOURCE__', '\u6765\u6e90'),
    ('__BTN_PREVIEW__', '\u9884\u89c8'),
    ('__NO_PDF__', '\u65e0 PDF'),
    ('__BTN_GRAPH__', '\u56fe\u8c31'),
    ('__BTN_EDIT_KW__', '\u6539\u5173\u952e\u8bcd'),
    ('__NO_HITS__', '\u6ca1\u6709\u547d\u4e2d'),
    ('__KW_FILTER__', '\u6309\u5173\u952e\u8bcd\u5206\u7c7b'),
    ('__KW_EMPTY__', '\u5c1a\u65e0\u5173\u952e\u8bcd\u3002\u4e0a\u4f20\u6216\u4e0b\u8f7d\u8bba\u6587\u540e\u4f1a\u81ea\u52a8\u51fa\u73b0\u3002'),
    ('__LBL_KEYWORDS__', '\u5173\u952e\u8bcd\uff08\u9009\u586b\uff0c\u9017\u53f7\u5206\u9694\uff09'),
    ('__PH_KEYWORDS__', 'TOPCon, perovskite'),
    ('__KW_PROMPT_TITLE__', '\u5173\u952e\u8bcd\u62bd\u53d6\u63d0\u793a\u8bcd'),
    ('__KW_PROMPT_HINT__', '\u76f8\u540c\u5173\u952e\u8bcd\u7684\u8bba\u6587\u5171\u7528\u4e00\u6761\u62bd\u53d6\u63d0\u793a\u8bcd\u3002\u7559\u7a7a\u5219\u4f7f\u7528\u9ed8\u8ba4\u63d0\u793a\u8bcd\u3002\u63d0\u793a\u8bcd\u4ec5\u7ba1\u7406\u5458\u53ef\u6539\uff1b\u5173\u952e\u8bcd\u540d\u79f0\u6240\u6709\u7528\u6237\u53ef\u6539\u3002'),
    ('__PH_KW_PROMPT__', '\u7559\u7a7a\u5219\u4f7f\u7528\u9ed8\u8ba4\u77e5\u8bc6\u56fe\u8c31\u63d0\u793a\u8bcd'),
    ('__BTN_SAVE_KW__', '\u4fdd\u5b58\u5173\u952e\u8bcd'),
    ('__MSG_KW_PROMPT_FAIL__', '\u65e0\u6cd5\u4fdd\u5b58\u5173\u952e\u8bcd'),
    ('__MSG_KW_PROMPT_OK__', '\u5df2\u4fdd\u5b58\u5173\u952e\u8bcd\uff1a'),
    ('__MSG_KW_SAVE_FAIL__', '\u65e0\u6cd5\u66f4\u65b0\u8bba\u6587\u5173\u952e\u8bcd'),
    ('__EDIT_KW_TITLE__', '\u4fee\u6539\u5173\u952e\u8bcd'),
    ('__EDIT_KW_HINT__', '\u591a\u4e2a\u5173\u952e\u8bcd\u7528\u9017\u53f7\u5206\u9694\u3002\u76f8\u540c\u540d\u79f0\u4f1a\u5408\u5e76\u4e3a\u540c\u4e00\u4e2a\u5173\u952e\u8bcd\u3002'),
    ('__BTN_ADD__', '\u65b0\u589e'),
    ('__UPLOAD_HINT__', '\u9ed8\u8ba4\u7528\u6587\u4ef6\u540d\u4f5c\u4e3a\u9898\u540d\u3002\u4f5c\u8005\u3001DOI\u3001\u5e74\u4efd\u3001\u6458\u8981\u3001\u5173\u952e\u8bcd\u5747\u53ef\u9009\u586b\uff1b\u4e5f\u53ef\u5148\u70b9 AI \u89e3\u6790\uff0c\u4ece\u6458\u8981\u62bd\u53d6\u5173\u952e\u8bcd\u3002'),
    ('__MODEL_PREFIX__', '\u5f53\u524d\u6a21\u578b'),
    ('__UNSET__', '\u672a\u586b\u5199'),
    ('__KEY_OK__', '\u5df2\u914d\u7f6e\u5bc6\u94a5'),
    ('__KEY_MISSING__', '\u5c1a\u672a\u586b\u5199 API Key'),
    ('__LBL_TITLE__', '\u9898\u540d'),
    ('__PH_TITLE__', '\u9009\u62e9\u6587\u4ef6\u540e\u81ea\u52a8\u586b\u5165\u6587\u4ef6\u540d'),
    ('__LBL_AUTHORS__', '\u4f5c\u8005\uff08\u9009\u586b\uff09'),
    ('__LBL_DOI__', 'DOI\uff08\u9009\u586b\uff09'),
    ('__LBL_YEAR__', '\u5e74\u4efd\uff08\u9009\u586b\uff09'),
    ('__LBL_ABSTRACT__', '\u6458\u8981\uff08\u9009\u586b\uff09'),
    ('__BTN_PARSING__', '\u89e3\u6790\u4e2d...'),
    ('__BTN_PARSE__', 'AI \u89e3\u6790\u5e76\u586b\u5165'),
    ('__BTN_SAVE__', '\u4fdd\u5b58\u5165\u5e93'),
    ('__SETTINGS_HINT__', '\u5730\u5740\u3001\u6a21\u578b\u540d\u548c\u5bc6\u94a5\u5148\u5199\u5728\u9875\u9762\u4e0e config.toml\uff0c\u540e\u7eed\u81ea\u884c\u586b\u5199\u3002Neo4j \u4ec5\u9884\u7559\uff0c\u5ba1\u6838\u901a\u8fc7\u540e\u624d\u4f1a\u51c6\u5907\u540c\u6b65\u3002'),
    ('__LBL_API_URL__', 'API \u5730\u5740'),
    ('__LBL_MODEL__', '\u6a21\u578b\u540d\u79f0'),
    ('__LBL_TIMEOUT__', '\u8d85\u65f6\uff08\u79d2\uff09'),
    ('__BTN_SAVE_AI__', '\u4fdd\u5b58 AI \u914d\u7f6e'),
    ('__NEO_TITLE__', 'Neo4j\uff08\u540e\u671f\u540c\u6b65\uff09'),
    ('__NEO_ENABLE__', '\u542f\u7528\u540c\u6b65\uff08\u5f53\u524d\u4e0d\u4f1a\u771f\u6b63\u5199\u5165\uff09'),
    ('__LBL_NEO_USER__', '\u7528\u6237'),
    ('__LBL_NEO_PASS__', '\u5bc6\u7801'),
    ('__LBL_NEO_DB__', '\u6570\u636e\u5e93'),
    ('__BTN_SAVE_NEO__', '\u4fdd\u5b58 Neo4j \u914d\u7f6e'),
    ('__PROMPT_TITLE__', '\u62bd\u53d6\u63d0\u793a\u8bcd'),
    ('__PROMPT_HINT__', '\u4ec5\u7ba1\u7406\u5458\u53ef\u4fee\u6539\u3002\u666e\u901a\u7528\u6237\u53ef\u67e5\u770b\u5f53\u524d\u63d0\u793a\u8bcd\u3002'),
    ('__BTN_SAVE_PROMPT__', '\u4fdd\u5b58\u8be5\u63d0\u793a\u8bcd'),
    ('__BTN_ADD__', '\u65b0\u589e'),
    ('__TH_USER__', '\u7528\u6237'),
    ('__TH_ROLE__', '\u89d2\u8272'),
    ('__TH_STATUS__', '\u72b6\u6001'),
    ('__ON__', '\u542f\u7528'),
    ('__OFF__', '\u505c\u7528'),
    ('__PDF_PREVIEW__', 'PDF \u9884\u89c8'),
    ('__BTN_CLOSE__', '\u5173\u95ed'),
    ('__GRAPH_TITLE__', '\u77e5\u8bc6\u56fe\u8c31'),
    ('__STATUS_PREFIX__', '\u72b6\u6001\uff1a'),
    ('__MODEL_WORD__', '\u6a21\u578b'),
    ('__BTN_EXTRACTING__', '\u62bd\u53d6\u4e2d...'),
    ('__BTN_EXTRACT__', 'AI \u4e00\u952e\u62bd\u53d6'),
    ('__BTN_APPROVE__', '\u5ba1\u6838\u901a\u8fc7'),
    ('__BTN_REJECT__', '\u9a73\u56de'),
    ('__PH_REVIEW__', '\u5ba1\u6838\u610f\u89c1\uff08\u9009\u586b\uff09'),
    ('__GRAPH_EMPTY__', '\u5c1a\u672a\u62bd\u53d6\u3002\u70b9\u51fb\u300cAI \u4e00\u952e\u62bd\u53d6\u300d\u540e\u5c06\u5199\u5165\u7cfb\u7edf\u5c5e\u6027\uff08\u65f6\u95f4\u3001\u673a\u6784\u3001\u4f5c\u8005\u3001\u6587\u4ef6\u540d\u3001\u6458\u8981\uff09\u53ca\u5173\u952e\u8bcd\u5173\u7cfb\uff0c\u5e76\u5728\u6b64\u9884\u89c8\u3002'),
]


def main() -> None:
    text = SRC.read_text(encoding='utf-8')
    missing = [key for key, _ in PAIRS if key not in text]
    if missing:
        raise SystemExit('missing keys: ' + ', '.join(missing))
    for key, value in PAIRS:
        text = text.replace(key, value)
    leftover = [key for key, _ in PAIRS if key in text]
    if leftover:
        raise SystemExit('leftover keys: ' + ', '.join(leftover))
    APP.write_text(text, encoding='utf-8')
    leftover = [key for key, _ in PAIRS if key in APP.read_text(encoding='utf-8')]
    if leftover:
        raise SystemExit('leftover keys after write: ' + ', '.join(leftover))
    sample = APP.read_text(encoding='utf-8')
    if '\u5149\u4f0f\u5b9e\u9a8c\u5ba4\u8bba\u6587\u5e93' not in sample:
        raise SystemExit('chinese title missing after write')
    print('ok', APP)


if __name__ == '__main__':
    main()
