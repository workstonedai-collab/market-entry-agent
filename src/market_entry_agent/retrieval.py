"""Bounded local lexical retrieval helpers; aliases never create public queries."""
import re
import unicodedata
from datetime import datetime, timezone

# Public names only. Matching is lexical, not a claim of semantic equivalence.
ALIASES = (
    ('eu', 'european union', '欧盟'),
    ('un', 'united nations', '联合国'),
    ('wto', 'world trade organization', '世界贸易组织', '世贸组织'),
    ('asean', 'association of southeast asian nations', '东盟'),
    ('cbam', 'carbon border adjustment mechanism', '碳边境调节机制', '碳边境调整机制'),
    ('wgi', 'worldwide governance indicators', '全球治理指标'),
    ('ofac', 'office of foreign assets control', '美国海外资产控制办公室'),
)


def normalized(value):
    return unicodedata.normalize('NFKC', value).casefold()


def tokens(value):
    parts = re.findall(r'[\u4e00-\u9fff]+|[a-z0-9]+(?:[-_][a-z0-9]+)*', normalized(value))
    return {token for part in parts for token in
            ([part[i:i+2] for i in range(len(part)-1)] if re.fullmatch(r'[\u4e00-\u9fff]{2,}',part) else [part])}


def alias_groups(value):
    value = normalized(value)
    return [group for group in ALIASES if any(
        re.search(r'(?<![a-z0-9])'+re.escape(alias)+r'(?![a-z0-9])',value)
        if re.search(r'[a-z]',alias) else alias in value for alias in group)]


def expanded_tokens(value):
    result=tokens(value)
    for group in alias_groups(value):
        for alias in group:result.update(tokens(alias))
    return result


def chunks(body, location, size=1600):
    """Keep exact slices and offsets; prefer paragraph/line ends and retain overlap."""
    start=0
    headings=list(re.finditer(r'^#{1,6}\s+([^\n]+)',body,re.M)) if location.get('format')=='md' else []
    while start<len(body):
        end=min(start+size,len(body))
        if end<len(body):
            # Do not split a paragraph early merely to produce very short fragments.
            lower=start+size//2
            split=body.rfind('\n\n',lower,end)
            if split<0:split=body.rfind('\n',lower,end)
            if split>=lower:end=split+1
        excerpt=body[start:end]
        if excerpt.strip():
            loc=dict(location,chunk_offset=start,chunk_end=end)
            preceding=[h for h in headings if h.start()<=start]
            if preceding:loc['section_heading']=preceding[-1].group(1)[:200]
            elif headings and headings[0].start()<end:loc['section_heading']=headings[0].group(1)[:200]
            yield excerpt,loc
        if end==len(body):break
        start=max(start+1,end-100)


def filters(value):
    if value is None:return {}
    if not isinstance(value,dict) or set(value)-{'countries','topics','published_after','published_before','include_undated'}:
        raise ValueError('Unknown knowledge search filter')
    result=dict(value)
    for field in ('countries','topics'):
        if field in value and (not isinstance(value[field],list) or len(value[field])>30 or any(not isinstance(x,str) or not x.strip() or len(x)>100 for x in value[field])):
            raise ValueError('Knowledge scope filter requires bounded text lists')
    if 'include_undated' in value and type(value['include_undated']) is not bool:raise ValueError('include_undated must be boolean')
    for field in ('published_after','published_before'):
        if field in value:result[field]=date_stamp(value[field])
    if result.get('published_after',float('-inf'))>result.get('published_before',float('inf')):raise ValueError('Publication range is reversed')
    return result


def date_stamp(value):
    if not isinstance(value,str) or len(value)>60:raise ValueError('Expected bounded ISO publication date')
    try:date=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise ValueError('Expected ISO publication date') from None
    return date.replace(tzinfo=timezone.utc).timestamp() if date.tzinfo is None else date.timestamp()


def matches(meta, selected):
    for field in ('countries','topics'):
        if selected.get(field) and not {normalized(x) for x in selected[field]}.intersection(normalized(x) for x in meta[field]):return False
    if 'published_after' in selected or 'published_before' in selected:
        if not meta.get('published_at'):return selected.get('include_undated',False)
        stamp=date_stamp(meta['published_at'])
        if stamp<selected.get('published_after',float('-inf')) or stamp>selected.get('published_before',float('inf')):return False
    return True


def excerpt(body, query, size=400):
    """Point to a matching literal or recognized name, preserving original characters."""
    needles=re.findall(r'[\u4e00-\u9fff]+|[a-z0-9_-]+',query.casefold())
    needles.extend(alias for group in alias_groups(query) for alias in group)
    # Keep offsets on the original body (NFKC can change its character count).
    haystack=body.lower()
    positions=[haystack.find(n) for n in needles if n and haystack.find(n)>=0]
    pos=min(positions) if positions else 0
    start=max(0,pos-80)
    return body[start:start+size],start
