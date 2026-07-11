import re

SECTION_KEYWORDS = {
    "equity": ["股本", "股份", "出资", "注册资本"],
    "subscription": ["增资", "认购", "发行", "定向发行"],
    "transfer": ["转让", "股权转让", "受让", "出让"]
}

def locate_sections(pages):
    sections = {"equity": [], "subscription": [], "transfer": []}

    for p in pages:
        for sec, keys in SECTION_KEYWORDS.items():
            if any(k in p["text"] for k in keys):
                sections[sec].append(p)

    return sections