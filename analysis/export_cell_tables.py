"""Export cell-level behavioral tables (single-turn, agentic, sequential).

For every cell: model, domain, level, threat model, realized n, b (C->W),
c (W->C), b/n rate, Wilson 95% CI, raw exact-McNemar p, and BH-adjusted q where
the cell belongs to a pre-specified family. Reads data/behavioral_rows.json
(the canonical index/log-backed export). Writes .csv / .md / .tex per arm to
docs/tables/.

    python analysis/export_cell_tables.py
"""
import json, csv, re
from pathlib import Path

ARMS = {"single_turn_mcq": "single_turn", "agentic_discovery": "agentic",
        "sequential_mcq": "sequential"}
CORE = ["gemini-3.1-pro-preview", "claude-opus-4", "claude-sonnet-4",
        "gemini-2.5-pro", "glm-5.2"]
EXP = ["gpt-5.6-sol", "kimi-k3-20260715"]
MORDER = CORE + EXP
MLAB = {"gemini-3.1-pro-preview": "Gemini 3.1 Pro", "claude-opus-4": "Claude Opus 4",
        "claude-sonnet-4": "Claude Sonnet 4", "gemini-2.5-pro": "Gemini 2.5 Pro",
        "glm-5.2": "GLM-5.2", "gpt-5.6-sol": "GPT-5.6 Sol",
        "kimi-k3-20260715": "Kimi K3"}
DOM = {"wmdp-cyber": "Cyber", "wmdp-bio": "Bio", "wmdp-chem": "Chem"}
DORDER = ["wmdp-cyber", "wmdp-bio", "wmdp-chem"]
CONDRANK = {"level2": 0, "level3": 1, "level4": 2, "level5": 3, "level6": 4}


def parse_cond(c):
    lv = int(re.match(r"level(\d)", c).group(1))
    tm = "TM1" if c.endswith("tm1") else "TM2" if c.endswith("tm2") else "--"
    return lv, tm, f"L{lv}"


def family_label(r):
    fam = r.get("family")
    if fam in ("primary", "expansion", "sequential"):
        return fam
    if r.get("posthoc"):
        return "post-hoc"
    return "control"          # L5/L6 expected-positive controls (raw p only)


def qtext(r):
    fam = family_label(r)
    if fam == "post-hoc":
        return "-- (post-hoc, raw p)"
    if fam == "control":
        return "-- (control)"
    return f"{r['q']:.3f}" if r.get("q") is not None else "--"


def sortkey(r):
    lv, tm, _ = parse_cond(r["cond"])
    tmr = {"--": 0, "TM1": 1, "TM2": 2}[tm]
    return (DORDER.index(r["dataset"]), MORDER.index(r["model"]),
            CONDRANK[r["cond"][:6]], tmr)


def export(arm_key, rows):
    rows = sorted([r for r in rows if r["arm"] == arm_key], key=sortkey)
    stem = ARMS[arm_key]
    Path("docs/tables").mkdir(parents=True, exist_ok=True)

    def cond(r):
        """Return (a+b baseline-correct count, conditional C->W = b/(a+b),
        baseline accuracy in matched sample = (a+b)/n)."""
        a = r.get("cc", 0); ab = a + r["cw"]; n = r["n"]
        return ab, (r["cw"] / ab if ab else 0.0), (ab / n if n else 0.0)

    # ---- CSV (canonical) ----
    with open(f"docs/tables/{stem}_cells.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["model", "domain", "level", "threat_model", "n", "a_cc",
                     "b_cw", "c_wc", "d_ww", "cw_rate", "ci_low", "ci_high",
                     "n_baseline_correct", "cond_cw_rate", "baseline_acc",
                     "raw_p", "q", "family"])
        for r in rows:
            lv, tm, L = parse_cond(r["cond"])
            ab, ccw, bacc = cond(r)
            wr.writerow([MLAB[r["model"]], DOM[r["dataset"]], L, tm, r["n"],
                         r.get("cc", ""), r["cw"], r["wc"], r.get("ww", ""),
                         round(r["rate"], 4),
                         round(r["ci"][0], 4), round(r["ci"][1], 4),
                         ab, round(ccw, 4), round(bacc, 4),
                         round(r["p"], 5),
                         "" if r.get("q") is None else round(r["q"], 4),
                         family_label(r)])

    # ---- Markdown ----
    md = ["| model | domain | level | TM | n | b | c | b/n | b/(a+b) | base acc | 95% CI | raw p | q |",
          "|---|---|---|---|--:|--:|--:|--:|--:|--:|---|--:|---|"]
    for r in rows:
        lv, tm, L = parse_cond(r["cond"])
        ci = f"[{r['ci'][0]:.3f}, {r['ci'][1]:.3f}]"
        ab, ccw, bacc = cond(r)
        md.append(f"| {MLAB[r['model']]} | {DOM[r['dataset']]} | {L} | {tm} | "
                  f"{r['n']} | {r['cw']} | {r['wc']} | {r['rate']:.3f} | "
                  f"{ccw:.3f} | {bacc:.3f} | {ci} | "
                  f"{r['p']:.4f} | {qtext(r)} |")
    Path(f"docs/tables/{stem}_cells.md").write_text("\n".join(md) + "\n")

    # ---- LaTeX longtable ----
    tex = [r"\begin{longtable}{lll l rr l r r l}", r"\toprule",
           r"Model & Dom. & L·TM & $n$ & $b$ & $c$ & $b/n$ [95\% CI] & $\frac{b}{a+b}$ & $p$ & $q$ \\",
           r"\midrule", r"\endhead"]
    prev = None
    for r in rows:
        key = (r["dataset"], r["model"])
        if prev is not None and key != prev:
            tex.append(r"\midrule")
        prev = key
        lv, tm, L = parse_cond(r["cond"])
        ltm = L if tm == "--" else f"{L}·{tm}"
        ci = f"{r['rate']:.3f} [{r['ci'][0]:.3f}, {r['ci'][1]:.3f}]"
        _, ccw, _ = cond(r)
        q = qtext(r).replace("--", r"\,--\,")
        if r.get("family") in ("primary", "expansion", "sequential") and r.get("q") is not None and r["q"] < 0.05 and r["cw"] > r["wc"]:
            q = r"\textbf{" + f"{r['q']:.3f}" + "}"
        tex.append(f"{MLAB[r['model']]} & {DOM[r['dataset']]} & {ltm} & {r['n']} & "
                   f"{r['cw']} & {r['wc']} & {ci} & {ccw:.3f} & {r['p']:.4f} & {q} \\\\")
    tex += [r"\bottomrule", r"\end{longtable}"]
    Path(f"docs/tables/{stem}_cells.tex").write_text("\n".join(tex) + "\n")

    print(f"{stem}: {len(rows)} cells -> docs/tables/{stem}_cells.{{csv,md,tex}}")
    return rows


def main():
    rows = json.load(open("data/behavioral_rows.json"))
    for arm in ARMS:
        export(arm, rows)


if __name__ == "__main__":
    main()
