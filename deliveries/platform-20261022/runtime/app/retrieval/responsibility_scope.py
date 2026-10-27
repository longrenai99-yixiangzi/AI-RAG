"""Literal responsibility lookup; an unrelated duty cannot answer who handles an action."""
import re


def responsibility_action(question):
    q = re.sub(r'\s+', '', question)
    match = re.search(r'(?:哪个|哪一|什么|哪家)(?:部门|单位|机构|人员|岗位)(?:具体)?负责([\u4e00-\u9fff]{2,12})[？?。]?$|谁(?:来|具体)?负责([\u4e00-\u9fff]{2,12})[？?。]?$', q)
    return next((v for v in match.groups() if v), None) if match else None


def responsibility_quotes(action, text):
    if not action:
        return []
    pattern = re.compile(r'(?<!不)(?<!不得)负责[^。；;！？!?]{0,12}'+re.escape(action))
    return [sentence.strip() for sentence in re.split(r'(?<=[。！？])', re.sub(r'\s+', '', text))
            if pattern.search(sentence)]


def responsibility_key(action, quote):
    # Only collapse unqualified statements with an identical literal actor; keep conditions distinct.
    actor = re.search(r'由([^。；;，,]{2,50}?)负责[^。；;，,]{0,12}'+re.escape(action), quote)
    if actor and not re.search(r'仅|只|若|当|不|阶段|适用|期间|条件|但|\d{4}年', quote):
        return actor[1], action
    return quote
