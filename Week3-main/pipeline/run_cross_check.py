def run_cross_check(subscription, snapshot):

    total_flow = sum([s.数量 for s in subscription])

    snap_total = 0
    for s in snapshot:
        snap_total += float(s.get("总股本（万股）", 0))

    return {
        "flow": total_flow,
        "snapshot": snap_total,
        "diff": total_flow - snap_total,
        "status": "PASS" if abs(total_flow - snap_total) < 1e-6 else "FAIL"
    }