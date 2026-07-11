import json

def compare(auto, gold_path):
    gold = [json.loads(l) for l in open(gold_path, encoding="utf-8")]

    results = []

    for a in auto:
        g = next((x for x in gold if x.get("公司")==a.get("公司")), None)

        if not g:
            continue

        results.append({
            "公司": a["公司"],
            "auto_flow": a["flow"],
            "gold_snapshot": g.get("snapshot值（期末总股本）"),
            "match": abs(float(a["flow"]) - float(g.get("snapshot值（期末总股本）",0))) < 1e-6
        })

    return results