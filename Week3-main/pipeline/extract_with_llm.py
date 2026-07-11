import json

def build_prompt(system_prompt, user_template, page_text):
    """
    拼接system + user prompt
    """
    return {
        "system": system_prompt,
        "user": user_template.replace("{page_text}", page_text)
    }


def call_llm(prompt, model="gpt"):
    """
    模拟LLM调用接口（实际可接OpenAI API）
    """
    # 这里在真实系统中替换为API调用
    # response = openai.chat.completions.create(...)
    
    return {
        "output": "LLM_RESULT_PLACEHOLDER"
    }


def extract_with_llm(pages, system_prompt, user_template, variant="strict"):
    """
    用LLM逐页抽取IPO股权数据
    """

    results = []

    for page in pages:
        prompt = build_prompt(system_prompt, user_template, page["text"])

        llm_result = call_llm(prompt)

        # 模拟解析（真实环境是JSONL解析）
        results.append({
            "page": page["page"],
            "variant": variant,
            "raw_output": llm_result["output"]
        })

    return results


def save_jsonl(data, path):
    with open(path, "w", encoding="utf-8") as f:
        for d in data:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    # 示例运行
    pages = [
        {"page": 1, "text": "示例文本：某公司增资1000万元"}
    ]

    with open("system_prompt.md", "r", encoding="utf-8") as f:
        system_prompt = f.read()

    with open("user_prompt_template.md", "r", encoding="utf-8") as f:
        user_template = f.read()

    result = extract_with_llm(
        pages,
        system_prompt,
        user_template,
        variant="strict"
    )

    save_jsonl(result, "llm_output.jsonl")

    print("LLM extraction done.")