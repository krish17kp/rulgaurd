"""Downsample the real RULGuard metrics into web/src/data.json (run from repo root)."""
import json

F = "frontend"
ev = json.load(open(f"{F}/reports/metrics/rul_evaluation.json"))
traj = json.load(open(f"{F}/deploy_data/trajectory_data.json"))
hidden = json.load(open(f"{F}/deploy_data/hidden_set_evaluation.json"))


def pick(seq, n=140):
    step = max(1, len(seq) // n)
    return seq[::step]


bearings = {}
for bid, b in traj.items():
    pred = b["held_out_predicted_rul_seconds"]
    pred_map = dict(zip(pred["sequence_index"], pred[next(k for k in pred if k != "sequence_index")]))
    idx = pick(list(range(len(b["reference_hi"]))))
    bearings[bid.split(":")[1]] = {
        "hi": [round(b["reference_hi"][i], 4) for i in idx],
        "stage": [b["stage"][i] for i in idx],
        "actual": [round(b["actual_rul_seconds"][i]) for i in idx],
        "pred": [round(pred_map.get(i, 0)) for i in idx],
    }

lobo = [
    {"bearing": r["held_out_bearing"].split(":")[1], "model": r["model"], "mae_h": round(r["mae_seconds"] / 3600, 2)}
    for r in ev["femto_lobo"]
]

out = {
    "lobo": lobo,
    "overall": {m: round(v["mae_seconds"]) for m, v in ev["femto_lobo_overall_by_model"].items()},
    "hidden": {"et_mae": 4555, "naive_mae": 5204, "et_phm": 0.068, "naive_phm": 0.029, "n": 11, "unsafe": 8},
    "hidden_official_rul": hidden["official_rul_seconds"],
    "bearings": bearings,
}
json.dump(out, open("web/src/data.json", "w"), separators=(",", ":"))
print("ok", len(json.dumps(out)) // 1024, "KB")
