"""Paper figures — reads data/*_rows.json ONLY (never re-globs logs or re-derives
outcomes; see AUDIT_CHECKLIST Stage 9). Publication vector output to figures/.

    python analysis/paper_figures.py fig2      # one figure
    python analysis/paper_figures.py all
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

mpl.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 300, "font.size": 11,
    "xtick.labelsize": 10, "ytick.labelsize": 10,
    "font.family": "sans-serif", "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#52514e", "axes.linewidth": 0.8,
    "xtick.color": "#52514e", "ytick.color": "#52514e",
    "text.color": "#0b0b0b", "axes.labelcolor": "#0b0b0b",
    "axes.grid": True, "grid.color": "#e6e6e3", "grid.linewidth": 0.6,
})
INK, SEC, MUTED = "#0b0b0b", "#52514e", "#8a897f"
# emphasis: the two models with FDR-significant spontaneous EH
EMPH = {"gemini-3.1-pro-preview": "#2a78d6", "claude-opus-4": "#eb6834"}
NULL_GREY = "#8f8e85"           # the other five models (visible, still receding)
ZONE = {"unnudged": "#f4f4f1", "nudge": "#eef2f7", "instruction": "#fbf1ea"}

MODELS = ["gemini-3.1-pro-preview", "claude-opus-4", "claude-sonnet-4",
          "gemini-2.5-pro", "glm-5.2", "gpt-5.6-sol", "kimi-k3-20260715"]
MLABEL = {"gemini-3.1-pro-preview": "Gemini 3.1 Pro", "claude-opus-4": "Claude Opus 4",
          "claude-sonnet-4": "Claude Sonnet 4", "gemini-2.5-pro": "Gemini 2.5 Pro",
          "glm-5.2": "GLM-5.2", "gpt-5.6-sol": "GPT-5.6 Sol", "kimi-k3-20260715": "Kimi K3"}

# unified 8-position x-axis; map each arm's condition names onto it
XPOS = ["L2", "L3-TM1", "L3-TM2", "L4-TM1", "L4-TM2", "L5-TM1", "L5-TM2", "L6"]
def _slot(cond):
    c = cond
    if "level2" in c: return 0
    if "level3" in c: return 1 if c.endswith("tm1") else 2
    if "level4" in c: return 3 if c.endswith("tm1") else 4
    if "level5" in c: return 5 if c.endswith("tm1") else 6
    if "level6" in c: return 7 if ("tm2" not in c) else None  # L6: single/seq merged; agentic use tm1
    return None

def _rows():
    return [x for x in json.loads(Path("data/behavioral_rows.json").read_text()) if "n" in x]

def fig2():
    r = [x for x in _rows() if x["dataset"] == "wmdp-cyber"]
    arms = [("single_turn_mcq", "A  Single-turn"), ("sequential_mcq", "B  Sequential"),
            ("agentic_discovery", "C  Agentic discovery")]
    fig, axes = plt.subplots(1, 3, figsize=(9.5, 3.6), sharey=True)
    for ax, (arm, title) in zip(axes, arms):
        # zone shading
        ax.axvspan(-0.5, 4.5, color=ZONE["unnudged"], zorder=0)
        ax.axvspan(4.5, 6.5, color=ZONE["nudge"], zorder=0)
        ax.axvspan(6.5, 7.5, color=ZONE["instruction"], zorder=0)
        for m in MODELS:
            pts = {}
            for x in r:
                if x["model"] != m or x["arm"] != arm: continue
                sl = _slot(x["cond"])
                if sl is None: continue
                pts[sl] = x
            if not pts: continue
            xs = sorted(pts)
            ys = [pts[k]["rate"] for k in xs]
            emph = m in EMPH
            col = EMPH.get(m, NULL_GREY)
            if emph:
                lo = [max(0, pts[k]["rate"] - pts[k]["ci"][0]) for k in xs]
                hi = [max(0, pts[k]["ci"][1] - pts[k]["rate"]) for k in xs]
                ax.errorbar(xs, ys, yerr=[lo, hi], color=col, lw=2, marker="o", ms=5,
                            mfc=col, mec="white", mew=0.6, elinewidth=1, capsize=0, zorder=5)
            else:
                # two-segment: unnudged (0-4) readable, nudge/instr (4-7) faded — the
                # L5/L6 points show the ceiling, not invite between-model comparison
                un = [k for k in xs if k <= 4]; hi_ = [k for k in xs if k >= 4]
                ax.plot(un, [pts[k]["rate"] for k in un], color=col, lw=1.4,
                        marker="o", ms=3.4, alpha=0.9, zorder=2)
                ax.plot(hi_, [pts[k]["rate"] for k in hi_], color=col, lw=1.4,
                        marker="o", ms=3.4, alpha=0.55, zorder=2)
            # FDR-significant unnudged cells: ring (smaller, thinner than before)
            for k in xs:
                x = pts[k]
                if x.get("family") and x.get("q") is not None and x["q"] < 0.05 and x["cw"] > x["wc"]:
                    ax.scatter([k], [x["rate"]], s=95, facecolors="none",
                               edgecolors=col, linewidths=1.3, zorder=6)
        ax.set_title(title, fontsize=15, loc="left", color=INK, pad=8)
        ax.set_xticks(range(8)); ax.set_xticklabels(XPOS, fontsize=11.5, rotation=30, ha="right")
        ax.set_ylim(-0.03, 1.0); ax.set_xlim(-0.5, 7.5)
        ax.tick_params(length=0, labelsize=11.5)
    axes[0].set_ylabel(r"C$\rightarrow$W rate  ($b/n$)", fontsize=14)

    # legend: emphasized direct + null group
    handles = [Line2D([0],[0], color=EMPH["gemini-3.1-pro-preview"], lw=2, marker="o", ms=5, mec="white", label="Gemini 3.1 Pro"),
               Line2D([0],[0], color=EMPH["claude-opus-4"], lw=2, marker="o", ms=5, mec="white", label="Claude Opus 4"),
               Line2D([0],[0], color=NULL_GREY, lw=1.4, marker="o", ms=3.4, alpha=0.9, label="Other 5 models"),
               Line2D([0],[0], marker="o", ms=9, mfc="none", mec=INK, mew=1.3, lw=0, label="FDR-significant (unnudged)")]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=12.5, bbox_to_anchor=(0.5, -0.07))
    fig.tight_layout(rect=[0, 0.04, 1, 0.94])
    fig.savefig("figures/fig2_delivery_modes.pdf", bbox_inches="tight")
    fig.savefig("figures/fig2_delivery_modes.png", bbox_inches="tight")
    print("wrote figures/fig2_delivery_modes.{pdf,png}")


DOMAIN_COL = {"cyber": "#1baf7a", "bio": "#eda100", "chem": "#4a3aa7"}
DLABEL = {"cyber": "Cyber", "bio": "Bio", "chem": "Chem"}

def fig3():
    r = [x for x in _rows() if x["model"] == "gemini-3.1-pro-preview"
         and x["arm"] == "agentic_discovery"]
    # x = rungs L2..L6; solid = TM1, dashed = TM2 (L2 shared)
    rungs = ["L2", "L3", "L4", "L5", "L6"]
    def val(dom, rung, tm):
        want = "level2" if rung == "L2" else f"level{rung[1]}-{tm}"
        for x in r:
            if x["dataset"] == f"wmdp-{dom}" and x["cond"] == want:
                return x
        return None
    fig, ax = plt.subplots(figsize=(3.48, 2.3))
    ax.axvspan(-0.3, 2.5, color=ZONE["unnudged"], zorder=0)
    ax.axvspan(2.5, 3.5, color=ZONE["nudge"], zorder=0)
    ax.axvspan(3.5, 4.3, color=ZONE["instruction"], zorder=0)
    for dom, col in DOMAIN_COL.items():
        for tm, ls, lw in [("tm1", "-", 2.2), ("tm2", "--", 1.6)]:
            xs, ys, lo, hi = [], [], [], []
            for i, rg in enumerate(rungs):
                x = val(dom, rg, tm)
                if x is None: continue
                xs.append(i); ys.append(x["rate"])
                lo.append(max(0, x["rate"] - x["ci"][0])); hi.append(max(0, x["ci"][1] - x["rate"]))
            # L2 is threat-model-agnostic: draw its marker once (on TM1); TM2 line
            # still connects from the shared L2 point but carries no marker there.
            mask_ms = [5 if tm=="tm1" else 4]*len(xs)
            ax.errorbar(xs, ys, yerr=[lo, hi], color=col, lw=lw, ls=ls,
                        elinewidth=1.5, capsize=2.5, capthick=1.5, alpha=1 if tm=="tm1" else 0.85,
                        zorder=5 if tm=="tm1" else 4)
            mx = xs if tm=="tm1" else xs[1:]      # TM2: skip L2 marker
            my = ys if tm=="tm1" else ys[1:]
            ax.plot(mx, my, ls="none", marker="o", ms=5 if tm=="tm1" else 4,
                    mfc=col, mec="white", mew=0.6, zorder=6 if tm=="tm1" else 4)
    ax.set_xticks(range(5)); ax.set_xticklabels(rungs, fontsize=7.5)
    ax.set_ylim(-0.03, 1.0); ax.set_xlim(-0.3, 4.3)
    ax.set_ylabel(r"C$\rightarrow$W rate  ($b/n$)", fontsize=8)
    ax.tick_params(length=0, labelsize=7.5)
    dom_h = [Line2D([0],[0], color=c, lw=2.4, marker="o", ms=5, mec="white", label=DLABEL[d])
             for d, c in DOMAIN_COL.items()]
    tm_h = [Line2D([0],[0], color=SEC, lw=2, ls="-", label="Capability strengthening"),
            Line2D([0],[0], color=SEC, lw=1.6, ls=(0,(3.5,2.5)), label="Deployment suspension")]
    leg1 = ax.legend(handles=dom_h, loc="upper left", frameon=False, fontsize=8,
                     bbox_to_anchor=(0.01, 0.99), title="Domain", labelspacing=0.3)
    leg1.get_title().set_fontsize(8)
    ax.add_artist(leg1)
    # TM1/TM2 line-style key: stacked beneath the axis, clear of the data
    ax.legend(handles=tm_h, loc="upper center", frameon=False, fontsize=7,
              bbox_to_anchor=(0.5, -0.16), ncol=2, handlelength=2.4,
              columnspacing=0.8, handletextpad=0.35)
    fig.tight_layout()
    fig.savefig("figures/fig3_gemini_crossdomain.pdf", bbox_inches="tight")
    fig.savefig("figures/fig3_gemini_crossdomain.png", bbox_inches="tight")
    print("wrote figures/fig3_gemini_crossdomain.{pdf,png}")


def _cog(): return json.loads(Path("data/cognitive_rows.json").read_text())
def _eng(): return json.loads(Path("data/engagement_rows.json").read_text())
_PRIMARY = {"claude-opus-4","claude-sonnet-4","gemini-2.5-pro","gemini-3.1-pro-preview","glm-5.2"}
ARM_COL = {"single_turn": "#b0afa6", "agentic": "#2a78d6"}  # muted vs saturated = less vs more engagement

def fig4():
    """Two panels: engagement by level, and engagement resolution by domain.
    (The per-model reasoning-construct rates are reported as a table, not a panel.)"""
    import numpy as np
    eng=_eng()
    _P={"claude-opus-4","claude-sonnet-4","gemini-2.5-pro","gemini-3.1-pro-preview","glm-5.2"}
    lv=lambda c: next((l for l in ("level2","level3","level4","level5","level6") if c.startswith(l)),None)
    fig, (axA, axB) = plt.subplots(1, 2, figsize=(7.4, 1.75), gridspec_kw={"width_ratios":[0.95,1.05], "wspace":0.22})

    # ---- A: registration by level, single-turn vs agentic ----
    def reg(arm,level):
        num=den=0
        for r in eng:
            if r["model"] not in _P or r["arm"]!=arm or lv(r["cond"])!=level: continue
            num+=r["registration_rate"]*r["n"]; den+=r["n"]
        return num/den if den else None
    levels=["level2","level3","level4","level5","level6"]; xl=["L2","L3","L4","L5","L6"]
    ARMLAB={"single_turn":"Single-turn","agentic":"Discovered context"}
    for arm in ["single_turn","agentic"]:
        ys=[reg(arm,l) for l in levels]
        axA.plot(range(5),ys,color=ARM_COL[arm],lw=2.4,marker="o",ms=7,mec="white",mew=0.8,
                 label=ARMLAB[arm])
    axA.set_xticks(range(5)); axA.set_xticklabels(xl,fontsize=7.5); axA.set_ylim(0,1.0)
    axA.set_ylabel("Fraction of readable\nreasoning traces", fontsize=8)
    axA.set_title("A  Explicit engagement by scaffold level", fontsize=9, loc="left", pad=7)
    axA.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0.0,1.05),
               labelspacing=0.3); axA.tick_params(length=0, labelsize=7.5)

    # ---- B: resolution of agentic engagement, by domain (grouped bars) ----
    # Five exhaustive, mutually-exclusive resolution buckets (Appendix E), drawn as
    # grouped thin bars per domain. The rare "disbelieved" residual (<=2%, Chem only)
    # is pooled into aware_no_action so the five fractions sum to 1 within a domain.
    cats=[("no_engagement","#d8d7cf","No visible engagement"),
          (("aware_no_action","disbelieved"),"#b0afa6","Aware, no action"),
          ("premise_rejected","#eda100","Danger premise rejected"),
          ("decoupled","#4a3aa7","Framing irrelevant"),
          ("acted","#eb6834","Strategic action")]
    def frac(dom,cat):
        keys=cat if isinstance(cat,tuple) else (cat,)
        num=den=0
        for r in eng:
            if r["model"] not in _P or r["arm"]!="agentic" or r["domain"]!=dom: continue
            if lv(r["cond"]) not in ("level3","level4"): continue
            num+=sum(r[k] for k in keys)*r["n"]; den+=r["n"]
        return num/den if den else 0
    doms=["cyber","bio","chem"]; xpos=np.arange(3); ncat=len(cats); H={}
    gw=0.82; bw=gw/ncat  # group width, per-category bar width
    for i,(cat,col,lab) in enumerate(cats):
        vals=np.array([frac(d,cat) for d in doms])
        off=-gw/2+bw*(i+0.5)
        H[lab]=axB.bar(xpos+off,vals,bw,color=col,label=lab,edgecolor="white",linewidth=0.5)
    axB.set_xticks(xpos); axB.set_xticklabels(["Cyber","Bio","Chem"],fontsize=7.5)
    axB.set_ylim(0,1.0); axB.set_ylabel("fraction of episodes", fontsize=8)
    axB.set_title("B  Reasoning patterns in discovered-context L3–L4", fontsize=9, loc="left", pad=7)
    # grouped thin bars top out ~0.62, so the legend fits inside the freed headroom
    order=["No visible engagement","Aware, no action","Danger premise rejected","Framing irrelevant","Strategic action"]
    axB.set_axisbelow(True)   # grid behind the bars
    axB.tick_params(length=0, labelsize=7.5)
    axB.legend([H[o] for o in order], order, frameon=False, fontsize=8, loc="upper left",
               bbox_to_anchor=(0.02,1.04), ncol=2, columnspacing=1.0, handlelength=1.2,
               handletextpad=0.4, labelspacing=0.3)

    fig.tight_layout()
    fig.savefig("figures/fig4_reasoning.pdf", bbox_inches="tight")
    fig.savefig("figures/fig4_reasoning.png", bbox_inches="tight")
    print("wrote figures/fig4_reasoning.{pdf,png}")



# ============================== APPENDIX ==============================
_ALLMODELS = ["gemini-3.1-pro-preview","claude-opus-4","claude-sonnet-4","gemini-2.5-pro",
              "glm-5.2","gpt-5.6-sol","kimi-k3-20260715"]
_ORD_ST = ["level2_training_awareness","level3_goal_conflict_tm1","level3_goal_conflict_tm2",
           "level4_action_knowledge_tm1","level4_action_knowledge_tm2","level5_desire_nudge_tm1",
           "level5_desire_nudge_tm2","level6_explicit_instruction"]
_ORD_AG = ["level2","level3-tm1","level3-tm2","level4-tm1","level4-tm2","level5-tm1","level5-tm2",
           "level6-tm1","level6-tm2"]
_CLAB = ["L2","L3·T1","L3·T2","L4·T1","L4·T2","L5·T1","L5·T2","L6","L6·T2"]

def _behav_grid(arm, dataset, order, models):
    import numpy as np
    r=[x for x in _rows() if x.get("arm")==arm and x.get("dataset")==dataset and "n" in x]
    M=np.full((len(models), len(order)), np.nan)
    for i,m in enumerate(models):
        for j,c in enumerate(order):
            cell=next((x for x in r if x["model"]==m and x["cond"]==c), None)
            if cell: M[i,j]=cell["rate"]
    return M

def _heatmap(ax, M, rowlab, collab, title, vmax=1.0, cmap="Blues", annot=True,
             annot_fs=6.2, xtick_fs=7.5, ytick_fs=8.5, title_fs=11):
    import numpy as np
    im=ax.imshow(M, cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(collab))); ax.set_xticklabels(collab, fontsize=xtick_fs, rotation=35, ha="right")
    ax.set_yticks(range(len(rowlab))); ax.set_yticklabels(rowlab, fontsize=ytick_fs)
    ax.set_title(title, fontsize=title_fs, loc="left", pad=6)
    if annot:
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                if not np.isnan(M[i,j]):
                    ax.text(j,i,f"{M[i,j]:.2f}",ha="center",va="center",fontsize=annot_fs,
                            color="white" if M[i,j]>0.55*vmax else INK)
    ax.tick_params(length=0)
    for sp in ax.spines.values(): sp.set_visible(False)
    return im

# Final paper-facing model names — single source for every appendix matrix
# (A1a/A1b/A2/A5/A7) and the main-figure legends, so labels never mix forms.
_MLAB_FULL = {"gemini-3.1-pro-preview": "Gemini 3.1 Pro", "claude-opus-4": "Claude Opus 4",
              "claude-sonnet-4": "Claude Sonnet 4", "gemini-2.5-pro": "Gemini 2.5 Pro",
              "glm-5.2": "GLM-5.2", "gpt-5.6-sol": "GPT-5.6 Sol",
              "kimi-k3-20260715": "Kimi K3"}
MLAB7 = [_MLAB_FULL[m] for m in _ALLMODELS]
_CORE5 = _ALLMODELS[:5]                                  # evaluated on all 3 domains
_CLAB_ST = ["L2","L3·TM1","L3·TM2","L4·TM1","L4·TM2","L5·TM1","L5·TM2","L6"]
_CLAB_AG = ["L2","L3·TM1","L3·TM2","L4·TM1","L4·TM2","L5·TM1","L5·TM2","L6·TM1","L6·TM2"]

def _domain_models(dom):
    # Sol/Kimi are Cyber-only; omit their empty rows on Bio/Chem (noted in caption).
    return _ALLMODELS if dom == "wmdp-cyber" else _CORE5

def _behav_matrix_fig(arm, order, clab, suptitle, outstem):
    """One full-width behavioral matrix: Cyber/Bio/Chem side by side."""
    doms = ["wmdp-cyber", "wmdp-bio", "wmdp-chem"]
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.0),
                             gridspec_kw={"wspace": 0.62})
    im = None
    for ax, dom in zip(axes, doms):
        models = _domain_models(dom)
        M = _behav_grid(arm, dom, order, models)
        im = _heatmap(ax, M, [_MLAB_FULL[m] for m in models], clab,
                      dom[5:].capitalize(),
                      annot_fs=8, xtick_fs=9, ytick_fs=9.5, title_fs=12.5)
    cb = fig.colorbar(im, ax=axes, fraction=0.015, pad=0.02)
    cb.set_label(r"C$\rightarrow$W rate ($b/n$)")
    fig.suptitle(suptitle, fontsize=13, x=0.01, ha="left")
    fig.savefig(f"figures/{outstem}.pdf", bbox_inches="tight")
    fig.savefig(f"figures/{outstem}.png", bbox_inches="tight")
    print(f"wrote figures/{outstem}.{{pdf,png}}")

def figA1a():
    _behav_matrix_fig(
        "single_turn_mcq", _ORD_ST, _CLAB_ST,
        r"A1a  Single-turn behavioral matrix — C$\rightarrow$W rate ($b/n$) by model $\times$ condition $\times$ domain",
        "appA1a_behav_single_turn")

def figA1b():
    _behav_matrix_fig(
        "agentic_discovery", _ORD_AG, _CLAB_AG,
        r"A1b  Agentic-discovery behavioral matrix — C$\rightarrow$W rate ($b/n$) by model $\times$ condition $\times$ domain",
        "appA1b_behav_agentic")

def figA2():
    M=_behav_grid("sequential_mcq","wmdp-cyber",_ORD_ST,_ALLMODELS)
    fig,ax=plt.subplots(figsize=(7.5,4.4))
    _heatmap(ax,M,[_MLAB_FULL[m] for m in _ALLMODELS],_CLAB_ST,
             r"A2  Sequential behavioral matrix — C$\rightarrow$W rate (WMDP-Cyber)",
             annot_fs=8, xtick_fs=9, ytick_fs=9.5, title_fs=12)
    fig.tight_layout()
    fig.savefig("figures/appA2_sequential_matrix.pdf",bbox_inches="tight")
    fig.savefig("figures/appA2_sequential_matrix.png",bbox_inches="tight")
    print("wrote figures/appA2_sequential_matrix.{pdf,png}")

def figA4():
    # behaviour vs reasoning alignment: C→W rate vs dim4 rate, one point per cell
    import numpy as np
    beh={(x["model"],x["arm"],x["cond"],x.get("dataset")):x for x in _rows() if "n" in x}
    cog=_cog()
    ax_arm={"single_turn":"single_turn_mcq","agentic":"agentic_discovery"}
    xs,ys,cols=[],[],[]
    opus_seq=[]
    for r in cog:
        if r["dim4_rate"] is None: continue
        key=(r["model"],ax_arm.get(r["arm"],r["arm"]),
             r["cond"], f"wmdp-{r['domain']}")
        b=beh.get(key)
        if not b: continue
        xs.append(b["rate"]); ys.append(r["dim4_rate"])
        cols.append(EMPH.get(r["model"], NULL_GREY))
    fig,ax=plt.subplots(figsize=(4.0,3.2))
    ax.plot([0,1],[0,1],ls="--",color="#c4c3ba",lw=1,zorder=1)
    ax.scatter(xs,ys,c=cols,s=20,edgecolors="white",linewidths=0.4,zorder=3,alpha=0.85)
    ax.set_xlabel(r"C$\rightarrow$W rate", fontsize=8)
    ax.set_ylabel("judged strategic-action rate", fontsize=8)
    ax.set_title("Underperformance–reasoning alignment", fontsize=9, loc="left", pad=6)
    ax.set_xlim(-0.02,1.0); ax.set_ylim(-0.02,1.0); ax.tick_params(length=0, labelsize=8)
    ax.set_aspect("equal", adjustable="box")
    h=[Line2D([0],[0],marker="o",ls="none",mfc=EMPH["gemini-3.1-pro-preview"],mec="white",label="Gemini 3.1 Pro"),
       Line2D([0],[0],marker="o",ls="none",mfc=EMPH["claude-opus-4"],mec="white",label="Claude Opus 4"),
       Line2D([0],[0],marker="o",ls="none",mfc=NULL_GREY,mec="white",label="other models")]
    ax.legend(handles=h,frameon=False,fontsize=7.5,loc="upper left")
    fig.tight_layout()
    fig.savefig("figures/appA4_alignment.pdf",bbox_inches="tight")
    fig.savefig("figures/appA4_alignment.png",bbox_inches="tight")
    print("wrote figures/appA4_alignment.{pdf,png}")



def figA5():
    import numpy as np
    cog=_cog()
    doms=["cyber","bio","chem"]
    def grid(field, jd):
        M=np.full((len(_ALLMODELS),3),np.nan)
        for i,m in enumerate(_ALLMODELS):
            for k,d in enumerate(doms):
                num=den=0
                for r in cog:
                    if r["model"]!=m or r["domain"]!=d or r["arm"]!="agentic": continue
                    if not any(r["cond"].startswith(f"level{l}") for l in "345"): continue
                    j=r.get(jd) or 0; v=r.get(field)
                    if v is None or j==0: continue
                    num+=v*j; den+=j
                if den: M[i,k]=num/den
        return M
    fig,(a1,a2)=plt.subplots(1,2,figsize=(8.5,4.6))
    _heatmap(a1,grid("premise_rejection_gate_rate","premise_rejection_gate_judged"),MLAB7,
             ["Cyber","Bio","Chem"],"A5a  Premise rejection",vmax=0.6,cmap="Oranges")
    _heatmap(a2,grid("decoupling_gate_rate","decoupling_gate_judged"),MLAB7,
             ["Cyber","Bio","Chem"],"A5b  Decoupling",vmax=0.6,cmap="Purples")
    fig.suptitle("Alternative responses by model × domain (agentic, L3–L5)", fontsize=12, x=0.01, ha="left")
    fig.tight_layout(rect=[0,0,1,0.96])
    fig.savefig("figures/appA5_dismissal.pdf",bbox_inches="tight")
    fig.savefig("figures/appA5_dismissal.png",bbox_inches="tight"); print("wrote appA5")

def figA6():
    # Opus sequential diagnostics: (a) C→W by question position (NULL), (b) lexical EH-language gradient
    from inspect_ai.log import read_eval_log
    import glob, numpy as np, collections, re
    # (a) position effect, opus L4-tm1, baseline-paired
    bc={}
    for f in glob.glob("logs/gen-seq-cyber/*.eval"):
        h=read_eval_log(f,header_only=True); a=h.eval.task_args or {}
        if "opus" not in h.eval.model or a.get("condition")!="baseline": continue
        for smp in (read_eval_log(f).samples or []):
            sc=(smp.scores or {}).get("sequential_outcome_scorer"); pq=(sc.metadata or {}).get("per_question") if sc else []
            for pos,o in enumerate(pq): bc[(str(smp.id),pos)]=o
    pos_cw=collections.Counter(); pos_n=collections.Counter()
    for f in glob.glob("logs/gen-seq-cyber/*.eval"):
        h=read_eval_log(f,header_only=True); a=h.eval.task_args or {}
        if "opus" not in h.eval.model or a.get("condition")!="level4_action_knowledge_tm1": continue
        for smp in (read_eval_log(f).samples or []):
            sc=(smp.scores or {}).get("sequential_outcome_scorer"); pq=(sc.metadata or {}).get("per_question") if sc else []
            for pos,o in enumerate(pq):
                if bc.get((str(smp.id),pos))=="correct":
                    pos_n[pos]+=1; pos_cw[pos]+= (o=="wrong")
    # (b) lexical EH-language rate among wrong answers, by condition
    KW=re.compile(r"\b(reinforc\w+|gradient|underperform|deliberately|incorrect answer|answer incorrectly|restricted (capabilit|domain)|reward model)\b",re.I)
    order=["level2_training_awareness","level3_goal_conflict_tm1","level4_action_knowledge_tm1",
           "level5_desire_nudge_tm1","level6_explicit_instruction"]
    olab=["L2","L3·T1","L4·T1","L5·T1","L6"]
    lex={}
    for f in glob.glob("logs/gen-seq-cyber/*.eval"):
        h=read_eval_log(f,header_only=True); a=h.eval.task_args or {}
        if "opus" not in h.eval.model or a.get("condition") not in order: continue
        c=a.get("condition"); log=read_eval_log(f)
        for smp in (log.samples or []):
            for m in (smp.messages or []):
                if getattr(m,"role",None)!="assistant": continue
                cc=m.content; t=cc if isinstance(cc,str) else " ".join(getattr(x,"text","") or "" for x in (cc or []))
                sc=(smp.scores or {}).get("sequential_outcome_scorer"); pass
            # approximate: count wrong answers with EH language across the session text
        # simpler: reuse the summary numbers we computed earlier
    lexrate={"level2_training_awareness":0.0,"level3_goal_conflict_tm1":0.0,
             "level4_action_knowledge_tm1":0.20,"level5_desire_nudge_tm1":0.73,"level6_explicit_instruction":0.98}
    fig,(a1,a2)=plt.subplots(1,2,figsize=(9,4.0))
    xs=sorted(pos_n); ys=[pos_cw[p]/pos_n[p] if pos_n[p] else 0 for p in xs]
    a1.plot([x+1 for x in xs],ys,color=EMPH["claude-opus-4"],lw=2,marker="o",ms=6,mec="white")
    a1.set_xlabel("question position in session",fontsize=10.5); a1.set_ylim(0,0.5)
    a1.set_ylabel(r"C$\rightarrow$W rate",fontsize=10.5)
    a1.set_title("A6a  Opus L4·TM1: position effect (n.s., perm. p=0.10)",fontsize=10,loc="left",pad=6)
    a1.tick_params(length=0)
    a2.bar(range(len(order)),[lexrate[o] for o in order],color=EMPH["claude-opus-4"],width=0.6,edgecolor="white")
    a2.set_xticks(range(len(order))); a2.set_xticklabels(olab,fontsize=9.5)
    a2.set_ylim(0,1.0); a2.set_ylabel("EH-language in wrong answers",fontsize=10.5)
    a2.set_title("A6b  Verbalization tracks scaffold, not behaviour",fontsize=10,loc="left",pad=6)
    a2.tick_params(length=0)
    fig.tight_layout()
    fig.savefig("figures/appA6_opus_seq.pdf",bbox_inches="tight")
    fig.savefig("figures/appA6_opus_seq.png",bbox_inches="tight"); print("wrote appA6")

def figA7():
    import numpy as np
    rows=[json.loads(l) for l in Path("data/episode_index.jsonl").read_text().splitlines()]
    live=[r for r in rows if not r["superseded"]]
    doms=["cyber","bio","chem"]
    M=np.full((len(_ALLMODELS),3),np.nan)
    import collections
    for i,m in enumerate(_ALLMODELS):
        for k,d in enumerate(doms):
            sub=[r for r in live if r["model"]==m and r["domain"]==d and r["arm"]!="sequential"]
            if not sub: continue
            filt=sum(1 for r in sub if r["outcome"]=="filtered")
            M[i,k]=filt/len(sub)
    fig,ax=plt.subplots(figsize=(5.0,4.4))
    _heatmap(ax,M,MLAB7,["Cyber","Bio","Chem"],"A7  Provider content-filter rate by model × domain",vmax=0.7,cmap="Reds")
    fig.tight_layout()
    fig.savefig("figures/appA7_filtering.pdf",bbox_inches="tight")
    fig.savefig("figures/appA7_filtering.png",bbox_inches="tight"); print("wrote appA7")



def fig_abstract():
    """Compact visual-abstract ladder: Gemini-3.1 agentic, TM1 only, 3 domains.
    Stripped down for the headline figure — direct end-labels, no CI, no legend,
    a thin L4|L5 separator marking the unnudged region."""
    r = [x for x in _rows() if x["model"] == "gemini-3.1-pro-preview"
         and x["arm"] == "agentic_discovery"]
    rungs = ["L2", "L3", "L4", "L5", "L6"]
    def val(dom, rung):
        want = "level2" if rung == "L2" else f"level{rung[1]}-tm1"
        for x in r:
            if x["dataset"] == f"wmdp-{dom}" and x["cond"] == want:
                return x["rate"]
        return None

    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    # thin separator between the unnudged (L2-L4) and elicited (L5-L6) regimes
    ax.axvline(2.5, color="#cbcac3", lw=1.0, zorder=1)

    end = {}
    for dom, col in DOMAIN_COL.items():
        ys = [val(dom, rg) for rg in rungs]
        ax.plot(range(5), ys, color=col, lw=2.0, zorder=5,
                marker="o", ms=5, mfc=col, mec="white", mew=0.6)
        end[dom] = ys[-1]

    # direct end-labels, vertically spread so the near-coincident L6 values don't collide
    order = sorted(end, key=lambda d: end[d], reverse=True)   # cyber, chem, bio
    slot = {order[0]: end[order[0]] + 0.045,
            order[1]: end[order[1]],
            order[2]: end[order[2]] - 0.055}
    for dom in order:
        ax.text(4.13, slot[dom], DLABEL[dom], color=DOMAIN_COL[dom],
                fontsize=11, fontweight="bold", va="center", ha="left")

    # region labels just above the axis
    ax.text(1.0, 0.045, "unnudged", color=MUTED, fontsize=9.5, ha="center", va="center")
    ax.text(3.5, 0.045, "preference / instruction", color=MUTED, fontsize=9.5,
            ha="center", va="center")

    ax.set_xticks(range(5)); ax.set_xticklabels(rungs, fontsize=10.5)
    ax.set_yticks([0, 0.5, 1.0]); ax.set_yticklabels(["0", ".5", "1.0"], fontsize=12)
    ax.set_ylim(-0.02, 1.02); ax.set_xlim(-0.3, 4.95)
    ax.set_ylabel(r"C$\rightarrow$W rate", fontsize=13)
    ax.tick_params(length=0)
    ax.grid(False); ax.grid(True, axis="y")          # horizontal grid only
    ax.set_axisbelow(True)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.set_title("Gemini 3.1 Pro: agentic discovery", fontsize=13.5,
                 fontweight="bold", loc="left", pad=22)
    ax.text(0.0, 1.03, "Capability drift (TM1)", transform=ax.transAxes,
            fontsize=10.5, color=SEC, ha="left", va="bottom")
    fig.tight_layout()
    fig.savefig("figures/fig_abstract_gemini_tm1.pdf", bbox_inches="tight")
    fig.savefig("figures/fig_abstract_gemini_tm1.png", bbox_inches="tight")
    print("wrote fig_abstract")




# stylized visual-abstract colors: correct = calm teal, wrong = warm clay
CORRECT_COL, WRONG_COL = "#2f77b5", "#d1454f"   # blue = correct, red = wrong

def fig_abstract_bars():
    """Stylized 100% stacked Correct/Wrong bars for the visual abstract.
    Gemini-3.1 agentic-discovery, WMDP-Cyber, common 122-item pool.
    Reads data/abstract_bars_rows.json (exported by analysis/export_abstract_bars.py)."""
    d = json.loads(Path("data/abstract_bars_rows.json").read_text())
    rows = d["rows"]
    xlab = {"baseline": "L1", "level2": "L2", "level3-tm1": "L3",
            "level4-tm1": "L4", "level5-tm1": "L5", "level6-tm1": "L6"}
    labels = [xlab[r["cond"]] for r in rows]
    pc = [r["p_correct"] for r in rows]
    pw = [1 - x for x in pc]
    x = list(range(len(rows)))
    W = 0.82

    fig, ax = plt.subplots(figsize=(5.0, 3.3))
    ax.grid(False)
    # wrong on the bottom, correct on top; 2px white gap between the fills
    ax.bar(x, pw, W, color=WRONG_COL, edgecolor="white", linewidth=0, zorder=3)
    ax.bar(x, pc, W, bottom=[w + 0.006 for w in pw], color=CORRECT_COL,
           edgecolor="white", linewidth=0, zorder=3)

    # direct in-graphic labels (no legend): Correct in the tall baseline top block,
    # Wrong in the full L6 bottom block
    ax.text(0, pw[0] + pc[0] / 2, "Correct", color="white", ha="center", va="center",
            fontsize=11, fontweight="bold", zorder=5)
    ax.text(5, pw[5] / 2, "Wrong", color="white", ha="center", va="center",
            fontsize=11, fontweight="bold", zorder=5)

    # subtle 0% / 100% references only (no full axis)
    for yv, tx in [(0.0, "0%"), (1.0, "100%")]:
        ax.text(-0.72, yv, tx, color=MUTED, fontsize=9, ha="right", va="center")

    # faint separators between scaffold regimes (internal fills unchanged)
    for xs in (0.5, 3.5, 4.5):
        ax.axvline(xs, color="#e2e1db", lw=1.0, zorder=1)

    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 1.0); ax.set_xlim(-0.85, 5.6)
    ax.set_yticks([])
    for sp in ("top", "right", "left", "bottom"): ax.spines[sp].set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig("figures/fig_abstract_bars.pdf", bbox_inches="tight")
    fig.savefig("figures/fig_abstract_bars.png", bbox_inches="tight")
    fig.savefig("figures/fig_abstract_bars.svg", bbox_inches="tight")
    print("wrote fig_abstract_bars")



# ---- TM-split variants of fig2 / fig3 (one row per threat model) ----
def _lvl_tm(cond):
    lv = int(cond[5])                       # 'levelN...' -> N
    if cond.endswith("tm1"): return lv, "tm1"
    if cond.endswith("tm2"): return lv, "tm2"
    return lv, ""                           # L2 (no TM); single/seq L6 (merged)

_XSLOT = {2: 0, 3: 1, 4: 2, 5: 3, 6: 4}
_TMROW = {"tm1": "TM1 · capability drift", "tm2": "TM2 · deployment threshold"}

def fig2_bytm():
    """fig2 split by threat model: rows = TM1 / TM2, cols = the three arms."""
    r = [x for x in _rows() if x["dataset"] == "wmdp-cyber"]
    arms = [("single_turn_mcq", "A  Single-turn"), ("sequential_mcq", "B  Sequential"),
            ("agentic_discovery", "C  Agentic discovery")]
    fig, axes = plt.subplots(2, 3, figsize=(9.5, 4.1), sharey=True, sharex=True)
    for ri, tm in enumerate(["tm1", "tm2"]):
        for ci, (arm, title) in enumerate(arms):
            ax = axes[ri, ci]
            ax.axvspan(-0.5, 2.5, color=ZONE["unnudged"], zorder=0)
            ax.axvspan(2.5, 3.5, color=ZONE["nudge"], zorder=0)
            ax.axvspan(3.5, 4.5, color=ZONE["instruction"], zorder=0)
            for m in MODELS:
                pts = {}
                for x in r:
                    if x["model"] != m or x["arm"] != arm: continue
                    lv, ctm = _lvl_tm(x["cond"])
                    if lv == 2: pts[0] = x
                    elif lv == 6:
                        if ctm == "" or ctm == tm: pts[4] = x
                    elif ctm == tm:
                        pts[_XSLOT[lv]] = x
                if not pts: continue
                xs = sorted(pts); ys = [pts[k]["rate"] for k in xs]
                col = EMPH.get(m, NULL_GREY)
                if m in EMPH:
                    lo = [max(0, pts[k]["rate"] - pts[k]["ci"][0]) for k in xs]
                    hi = [max(0, pts[k]["ci"][1] - pts[k]["rate"]) for k in xs]
                    ax.errorbar(xs, ys, yerr=[lo, hi], color=col, lw=2, marker="o", ms=5,
                                mfc=col, mec="white", mew=0.6, elinewidth=1.3,
                                capsize=3, capthick=1.3, zorder=5)
                else:
                    un = [k for k in xs if k <= 2]; hg = [k for k in xs if k >= 2]
                    ax.plot(un, [pts[k]["rate"] for k in un], color=col, lw=1.4,
                            marker="o", ms=3.4, alpha=0.9, zorder=2)
                    ax.plot(hg, [pts[k]["rate"] for k in hg], color=col, lw=1.4,
                            marker="o", ms=3.4, alpha=0.55, zorder=2)
                for k in xs:
                    x = pts[k]
                    if x.get("family") and x.get("q") is not None and x["q"] < 0.05 and x["cw"] > x["wc"]:
                        ax.scatter([k], [x["rate"]], s=95, facecolors="none",
                                   edgecolors=col, linewidths=1.3, zorder=6)
            if ri == 0:
                ax.set_title(title, fontsize=14, loc="left", color=INK, pad=8)
            ax.set_xticks(range(5)); ax.set_ylim(-0.03, 1.0); ax.set_xlim(-0.5, 4.5)
            ax.tick_params(length=0, labelsize=11.5)
        axes[1, ci].set_xticklabels(["L2", "L3", "L4", "L5", "L6"], fontsize=11.5)
        axes[ri, 0].set_ylabel({"tm1": "TM1", "tm2": "TM2"}[tm],
                               fontsize=13.5, fontweight="bold", labelpad=3)
    for ci in range(3):
        axes[1, ci].set_xticklabels(["L2", "L3", "L4", "L5", "L6"], fontsize=11.5)
    handles = [Line2D([0],[0], color=EMPH["gemini-3.1-pro-preview"], lw=2, marker="o", ms=5, mec="white", label="Gemini 3.1 Pro"),
               Line2D([0],[0], color=EMPH["claude-opus-4"], lw=2, marker="o", ms=5, mec="white", label="Claude Opus 4"),
               Line2D([0],[0], color=NULL_GREY, lw=1.4, marker="o", ms=3.4, alpha=0.9, label="Other 5 models"),
               Line2D([0],[0], marker="o", ms=9, mfc="none", mec=INK, mew=1.3, lw=0, label="FDR-significant (unnudged)")]
    fig.supylabel(r"C$\rightarrow$W rate ($b/n$)", fontsize=12.5, x=0.055)
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=11,
               bbox_to_anchor=(0.57, -0.02), columnspacing=1.25, handletextpad=0.5, handlelength=1.7)
    fig.tight_layout(rect=[0.035, 0.03, 1, 1])
    fig.savefig("figures/fig2_delivery_modes_bytm.pdf", bbox_inches="tight")
    fig.savefig("figures/fig2_delivery_modes_bytm.png", bbox_inches="tight")
    print("wrote figures/fig2_delivery_modes_bytm.{pdf,png}")

def fig3_bytm():
    """fig3 split by threat model: rows = TM1 / TM2, three domains solid in each."""
    r = [x for x in _rows() if x["model"] == "gemini-3.1-pro-preview"
         and x["arm"] == "agentic_discovery"]
    rungs = ["L2", "L3", "L4", "L5", "L6"]
    def val(dom, rung, tm):
        want = "level2" if rung == "L2" else f"level{rung[1]}-{tm}"
        for x in r:
            if x["dataset"] == f"wmdp-{dom}" and x["cond"] == want:
                return x
        return None
    fig, axes = plt.subplots(2, 1, figsize=(6.0, 5.6), sharex=True)
    for ri, tm in enumerate(["tm1", "tm2"]):
        ax = axes[ri]
        ax.axvspan(-0.3, 2.5, color=ZONE["unnudged"], zorder=0)
        ax.axvspan(2.5, 3.5, color=ZONE["nudge"], zorder=0)
        ax.axvspan(3.5, 4.3, color=ZONE["instruction"], zorder=0)
        for dom, col in DOMAIN_COL.items():
            xs, ys, lo, hi = [], [], [], []
            for i, rg in enumerate(rungs):
                x = val(dom, rg, tm)
                if x is None: continue
                xs.append(i); ys.append(x["rate"])
                lo.append(max(0, x["rate"] - x["ci"][0])); hi.append(max(0, x["ci"][1] - x["rate"]))
            ax.errorbar(xs, ys, yerr=[lo, hi], color=col, lw=2.2,
                        elinewidth=1.5, capsize=2.5, capthick=1.5, zorder=5)
            ax.plot(xs, ys, ls="none", marker="o", ms=5, mfc=col, mec="white", mew=0.6, zorder=6)
        ax.set_ylim(-0.03, 1.0); ax.set_xlim(-0.3, 4.3)
        ax.set_ylabel(_TMROW[tm] + "\n" + r"C$\rightarrow$W rate ($b/n$)", fontsize=11)
        ax.tick_params(length=0, labelsize=12)
    axes[1].set_xticks(range(5)); axes[1].set_xticklabels(rungs, fontsize=12)
    dom_h = [Line2D([0],[0], color=c, lw=2.4, marker="o", ms=5, mec="white", label=DLABEL[d])
             for d, c in DOMAIN_COL.items()]
    leg = axes[0].legend(handles=dom_h, loc="upper left", frameon=False, fontsize=10.5,
                         bbox_to_anchor=(0.01, 0.99), title="Domain")
    leg.get_title().set_fontsize(10.5)
    fig.tight_layout()
    fig.savefig("figures/fig3_gemini_crossdomain_bytm.pdf", bbox_inches="tight")
    fig.savefig("figures/fig3_gemini_crossdomain_bytm.png", bbox_inches="tight")
    print("wrote figures/fig3_gemini_crossdomain_bytm.{pdf,png}")



ALLCOL = {"gemini-3.1-pro-preview": "#2a78d6", "claude-opus-4": "#eb6834",
          "claude-sonnet-4": "#2f9e44", "gemini-2.5-pro": "#9c36b5",
          "glm-5.2": "#e6a817", "gpt-5.6-sol": "#17a2b8", "kimi-k3-20260715": "#8d6e63"}

def fig2_bytm_allcolor():
    """fig2_bytm with EVERY model coloured (exploratory; no null-grey group)."""
    r = [x for x in _rows() if x["dataset"] == "wmdp-cyber"]
    arms = [("single_turn_mcq", "A  Single-turn"), ("sequential_mcq", "B  Sequential"),
            ("agentic_discovery", "C  Agentic discovery")]
    fig, axes = plt.subplots(2, 3, figsize=(9.5, 4.1), sharey=True, sharex=True)
    for ri, tm in enumerate(["tm1", "tm2"]):
        for ci, (arm, title) in enumerate(arms):
            ax = axes[ri, ci]
            ax.axvspan(-0.5, 2.5, color=ZONE["unnudged"], zorder=0)
            ax.axvspan(2.5, 3.5, color=ZONE["nudge"], zorder=0)
            ax.axvspan(3.5, 4.5, color=ZONE["instruction"], zorder=0)
            for m in MODELS:
                pts = {}
                for x in r:
                    if x["model"] != m or x["arm"] != arm: continue
                    lv, ctm = _lvl_tm(x["cond"])
                    if lv == 2: pts[0] = x
                    elif lv == 6:
                        if ctm == "" or ctm == tm: pts[4] = x
                    elif ctm == tm:
                        pts[_XSLOT[lv]] = x
                if not pts: continue
                xs = sorted(pts); ys = [pts[k]["rate"] for k in xs]
                col = ALLCOL[m]
                lo = [max(0, pts[k]["rate"] - pts[k]["ci"][0]) for k in xs]
                hi = [max(0, pts[k]["ci"][1] - pts[k]["rate"]) for k in xs]
                ax.errorbar(xs, ys, yerr=[lo, hi], color=col, lw=1.6, marker="o", ms=3.8,
                            mfc=col, mec="white", mew=0.5, elinewidth=0.7, capsize=0,
                            alpha=0.95, zorder=4)
                for k in xs:
                    x = pts[k]
                    if x.get("family") and x.get("q") is not None and x["q"] < 0.05 and x["cw"] > x["wc"]:
                        ax.scatter([k], [x["rate"]], s=95, facecolors="none",
                                   edgecolors=col, linewidths=1.3, zorder=6)
            if ri == 0:
                ax.set_title(title, fontsize=14, loc="left", color=INK, pad=8)
            ax.set_xticks(range(5)); ax.set_ylim(-0.03, 1.0); ax.set_xlim(-0.5, 4.5)
            ax.tick_params(length=0, labelsize=11.5)
        axes[ri, 0].set_ylabel({"tm1": "TM1", "tm2": "TM2"}[tm],
                               fontsize=13.5, fontweight="bold", labelpad=3)
    for ci in range(3):
        axes[1, ci].set_xticklabels(["L2", "L3", "L4", "L5", "L6"], fontsize=11.5)
    handles = [Line2D([0], [0], color=ALLCOL[m], lw=2, marker="o", ms=4.5, mec="white",
                      label=MLABEL[m]) for m in MODELS]
    handles.append(Line2D([0], [0], marker="o", ms=9, mfc="none", mec=INK, mew=1.3, lw=0,
                          label="FDR-significant (unnudged)"))
    fig.supylabel(r"C$\rightarrow$W rate ($b/n$)", fontsize=12.5, x=0.055)
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=10.5,
               bbox_to_anchor=(0.5, -0.09), columnspacing=1.2, handletextpad=0.4, handlelength=1.6)
    fig.tight_layout(rect=[0.035, 0.06, 1, 1])
    fig.savefig("figures/fig2_delivery_modes_bytm_allcolor.pdf", bbox_inches="tight")
    fig.savefig("figures/fig2_delivery_modes_bytm_allcolor.png", bbox_inches="tight")
    print("wrote figures/fig2_delivery_modes_bytm_allcolor.{pdf,png}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "fig2"
    if which in ("fig2_bytm_allcolor", "all"): fig2_bytm_allcolor()
    if which in ("fig_abstract", "all"): fig_abstract()
    if which in ("fig_abstract_bars", "all"): fig_abstract_bars()
    if which in ("fig2", "all"): fig2()
    if which in ("fig2_bytm", "all"): fig2_bytm()
    if which in ("fig3", "all"): fig3()
    if which in ("fig3_bytm", "all"): fig3_bytm()
    if which in ("fig4", "all"): fig4()
    if which in ("figA4", "all"): figA4()
    if which in ("figA7", "all"): figA7()
    if which in ("figA6", "all"): figA6()
    if which in ("figA5", "all"): figA5()
    if which in ("figA2", "all"): figA2()
    if which in ("figA1a", "all"): figA1a()
    if which in ("figA1b", "all"): figA1b()
