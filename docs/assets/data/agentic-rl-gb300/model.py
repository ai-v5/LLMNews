#!/usr/bin/env python3
"""Agentic RL sizing, planning scenarios, not measured. Python 3 standard library."""
from dataclasses import dataclass, replace
import csv
import sys

@dataclass(frozen=True)
class Model:
    name: str
    rollout_gpu: int
    train_gpu: int
    cpu_cores: int
    out_tps_gpu: float             # mixed-workload ceiling; all assigned rollout GPUs
    train_pflops_gpu: float        # effective counted FLOP during active trainer steps
    train_gflops_tok: float        # includes attention and non-loss packed tokens
    cycle_s: float
    cpu_s: float = 96              # aggregate physical-core-seconds per launched trajectory
    output_tok: float = 12000      # includes launched attempts incl. filtered/truncated work
    train_tok_kept: float = 18000  # conditional mean per admitted trajectory in complete groups
    keep: float = .72              # final usable sibling slots / launched trajectories; not reward-pass
    train_available: float = .95   # outside-step publication/coordination budget
    step: int = 256                # admitted trajectories per optimizer step (batch size, not rate)
    group: int = 8
    session_gib: float = .5

DS = Model("DS-V4.1-Flash", 360, 72, 3072, 820, .600, 125, 480)
KIMI = Model("Kimi-K3.1-Pro", 864, 288, 2304, 250, .703, 810, 660)

VARS = {
    "baseline": {},
    "rollout_minus_40pct": {"out_tps_gpu": .6},
    "cpu_seconds_x3": {"cpu_s": 3},
    "kept_sequence_x2": {"train_tok_kept": 2},
    "output_tokens_x2": {"output_tok": 2},
    "keep_50pct": {"keep": .5/.72},
    "train_compute_minus_25pct": {"train_pflops_gpu": .75},
    "keep_85pct": {"keep": .85/.72},
}

def size(m):
    raw_rollout_cap = m.rollout_gpu * m.out_tps_gpu / m.output_tok
    raw_cpu_cap = m.cpu_cores / m.cpu_s
    train_tok_per_gpu = m.train_pflops_gpu * 1e6 / m.train_gflops_tok * m.train_available
    raw_train_cap = m.train_gpu * train_tok_per_gpu / (m.keep * m.train_tok_kept)
    r = min(.8*raw_rollout_cap, .65*raw_cpu_cap, .8*raw_train_cap)
    ranks = {"rollout": .8*raw_rollout_cap, "sandbox": .65*raw_cpu_cap, "learner": .8*raw_train_cap}
    return {
        "raw_traj_per_s": r,
        "valid_groups_per_h": r*m.keep*3600/m.group,
        "raw_rollout_cap_s": raw_rollout_cap,
        "raw_cpu_cap_s": raw_cpu_cap,
        "raw_train_cap_s": raw_train_cap,
        "rollout_load_pct": 100*r/raw_rollout_cap,
        "cpu_load_pct": 100*r/raw_cpu_cap,
        "train_load_pct": 100*r/raw_train_cap,
        "train_tok_s_gpu_calendar": train_tok_per_gpu,
        "trained_sequence_tok_s": r*m.keep*m.train_tok_kept,
        "session_slots_avg": r*m.cycle_s,
        "session_ram_gib_avg": r*m.cycle_s*m.session_gib,
        "optimizer_step_s_avg": m.step/(r*m.keep),
        "limiting_budget": min(ranks,key=ranks.get),
    }

def rack_rows():
    for m in (DS,KIMI):
        total=(m.rollout_gpu+m.train_gpu)//72
        min_learner=m.train_gpu//72
        for tr in range(min_learner,total):
            v=replace(m, rollout_gpu=72*(total-tr), train_gpu=72*tr)
            result=size(v)
            yield {"model":m.name, "rollout_racks":total-tr, "learner_racks":tr,
                   "raw_traj_per_s":round(result["raw_traj_per_s"],6),
                   "valid_groups_per_h":round(result["valid_groups_per_h"],3),
                   "limiting_budget":result["limiting_budget"]}

def rows():
    for m in (DS,KIMI):
        for k,v in VARS.items():
            a=replace(m, **{a:getattr(m,a)*b for a,b in v.items()})
            yield {"model":m.name,"scenario":k,
                   "rollout_gpu":a.rollout_gpu,"train_gpu":a.train_gpu,"cpu_cores":a.cpu_cores,
                   **{k:(round(v,6) if isinstance(v,float) else v) for k,v in size(a).items()}}

if __name__ == "__main__":
    assert abs(size(DS)["raw_traj_per_s"]-19.68)<1e-6
    assert abs(size(KIMI)["raw_traj_per_s"]-14.4)<1e-6
    rows=list(rack_rows() if "--racks" in sys.argv else rows())
    out=csv.DictWriter(sys.stdout, fieldnames=tuple(rows[0]), lineterminator="\n")
    out.writeheader(); out.writerows(rows)
