import os
import re
import csv
import json

BASE_DIR = r"C:\Users\lenovo\Desktop\project"

MARKDOWN_FOLDER = os.path.join(BASE_DIR, "markdown_files")
LOG_FILE = os.path.join(BASE_DIR, "logs", "locate_log.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "outputs", "relevant_sections.json")

# 关键词分组，支持模糊匹配
KEYWORDS = {
    "financing": ["融资历史", "融资轮次", "增资", "募资", "融资记录", "投资历史"],
    "equity": ["股权结构", "股东", "持股比例", "股权变动", "股权分配"],
    "transfer": ["股权转让", "股权交易", "股东变更"]
}

def read_markdown(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()

def extract_sections(lines):
    """按 Markdown 标题分段，同时保留层级"""
    sections = []
    hierarchy = []
    current_section = {"title_hierarchy": [], "content": []}
    
    for line in lines:
        header_match = re.match(r"^(#+)\s*(.+)", line)
        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            
            # 更新层级
            if len(hierarchy) >= level:
                hierarchy = hierarchy[:level-1]
            hierarchy.append(title)
            
            # 保存当前段落
            if current_section["content"]:
                sections.append(current_section)
            current_section = {"title_hierarchy": hierarchy.copy(), "content": []}
        else:
            if line.strip():
                current_section["content"].append(line.strip())
    
    if current_section["content"]:
        sections.append(current_section)
    return sections

def match_keywords(text):
    """模糊匹配关键词"""
    text = re.sub(r"\s+", "", text)  # 去掉空格
    for words in KEYWORDS.values():
        for word in words:
            word_norm = re.sub(r"\s+", "", word)
            if re.search(word_norm, text, re.IGNORECASE):
                return True, word
    return False, None

def locate_relevant_sections(folder):
    results = []
    log_rows = []

    for filename in os.listdir(folder):
        if not filename.endswith(".md"):
            continue
        file_path = os.path.join(folder, filename)
        try:
            lines = read_markdown(file_path)
            sections = extract_sections(lines)
            relevant_sections = []
            matched_keywords = set()

            for sec in sections:
                text = " ".join(sec["content"])
                title_text = " ".join(sec["title_hierarchy"])
                matched, keyword = match_keywords(title_text)
                if not matched:
                    matched, keyword = match_keywords(text)
                if matched:
                    relevant_sections.append({
                        "title_hierarchy": sec["title_hierarchy"],
                        "content": sec["content"],
                        "matched_keyword": keyword
                    })
                    matched_keywords.add(keyword)

            success = len(relevant_sections) > 0
            results.append({
                "file_path": file_path,
                "relevant_sections": relevant_sections
            })

            log_rows.append({
                "file_name": filename,
                "sections_found": len(relevant_sections),
                "success": success,
                "matched_keywords": ";".join(matched_keywords),
                "error": ""
            })
        except Exception as e:
            log_rows.append({
                "file_name": filename,
                "sections_found": 0,
                "success": False,
                "matched_keywords": "",
                "error": str(e)
            })

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["file_name", "sections_found", "success", "matched_keywords", "error"])
        writer.writeheader()
        writer.writerows(log_rows)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"完成定位，结果保存到 {OUTPUT_FILE}，日志保存到 {LOG_FILE}")

if __name__ == "__main__":
    locate_relevant_sections(MARKDOWN_FOLDER)