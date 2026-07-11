def extract_with_rules(candidates):
    subscription = []
    transfer = []

    for c in candidates:
        if "增资" in c["raw"] or "认购" in c["raw"]:
            subscription.append({
                "公司": "unknown",
                "事件类型": "增资",
                "数量（万股）": float(c["value"]),
                "页码": c["page"]
            })

        if "转让" in c["raw"]:
            transfer.append({
                "公司": "unknown",
                "事件类型": "股权转让",
                "数量": c["value"],
                "页码": c["page"]
            })

    return subscription, transfer