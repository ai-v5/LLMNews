#!/usr/bin/env python3
"""Deterministic topology and directional capacity checks, not packet simulation."""
import csv
import ipaddress
import math
import sys
from collections import Counter

RAILS, PLANES = 4, 2
TRAYS_PER_RACK, GPUS_PER_TRAY = 18, 4
LEAVES, AGGS, SLOTS = 32, 32, 64
PORTS, EDGE, FABRIC = 64, 400, 800  # directional Gb/s


def measure(target, cells, north=32, bundle=1):
    """One rail-plane template, then replicate 4*2. bundle is physical links per pair."""
    racks = math.ceil(target / (TRAYS_PER_RACK * GPUS_PER_TRAY))
    q, rem = divmod(racks, cells)
    racks_by_cell = [q + (p < rem) for p in range(cells)]
    assert 0 < north <= 32 and north % bundle == 0
    assert cells * bundle <= PORTS and SLOTS // 2 + AGGS == PORTS
    assert LEAVES + north <= PORTS and AGGS * FABRIC == SLOTS * EDGE
    trays = [x * TRAYS_PER_RACK for x in racks_by_cell]
    assert max(trays) <= LEAVES * SLOTS
    leaf_n = {(p, l): min(SLOTS, max(0, t - l * SLOTS))
              for p, t in enumerate(trays) for l in range(LEAVES)}
    assert sum(leaf_n.values()) == racks * TRAYS_PER_RACK
    # L[p,l] -> A[p,i]; A[p,i] -> C[i,j] (bundle parallel if used).
    ll, ad, au, cc = Counter(), Counter(), Counter(), Counter()
    leaf_choices, core_cells = {}, {}
    for p, l in leaf_n:
        leaf_choices[p, l] = set()
        for i in range(AGGS):
            leaf_choices[p, l].add(i)
            ll[p, l] += 1
            ad[p, i] += 1
    for p in range(cells):
        for i in range(AGGS):
            for j in range(north // bundle):
                au[p, i] += bundle
                cc[i, j] += bundle
                core_cells.setdefault((i, j), set()).add(p)
    assert all(math.ceil(leaf_n[x] / 2) + ll[x] <= PORTS for x in ll)
    assert all(ad[x] + au[x] <= PORTS for x in ad)
    assert all(n == cells * bundle for n in cc.values())
    assert len(cc) == AGGS * north // bundle
    assert len(ll) == cells * LEAVES and len(ad) == cells * AGGS
    # Every core group has all cells. Leaf->agg->core->same-index agg->leaf.
    for (i, j), visible_cells in core_cells.items():
        assert visible_cells == set(range(cells))
        assert all(i in indexes for indexes in (leaf_choices[p, 0] for p in visible_cells))
    for p in range(cells):
        for q in range(p + 1, cells):
            paths = {(i, j) for i in leaf_choices[p, 0] & leaf_choices[q, LEAVES - 1]
                     for j in range(north // bundle)
                     if {p, q} <= core_cells[i, j]}
            assert len(paths) * bundle == AGGS * north
            assert len(paths - {(0, 0)}) * bundle == AGGS * north - bundle
            assert sum(i != 0 for i, j in paths) * bundle == (AGGS - 1) * north
    copies = RAILS * PLANES
    assert len(list(ipaddress.ip_network("10.64.0.0/11").subnets(new_prefix=14))) == copies
    assert len(list(ipaddress.ip_network("10.64.0.0/14").subnets(new_prefix=20))) >= cells
    assert len(list(ipaddress.ip_network("10.64.0.0/20").subnets(new_prefix=25))) == LEAVES
    # Installed/used both ends of each physical inter-switch link.
    edge_links = sum(trays) * copies
    return dict(target=target, gpus=racks * 72, racks=racks, trays=sum(trays), cells=cells,
                min_trays_cell=min(trays), max_trays_cell=max(trays),
                leaf=copies * len(ll), agg=copies * len(ad), core=copies * len(cc),
                switches=copies * (len(ll)+len(ad)+len(cc)), endpoints_400g=edge_links,
                leaf_agg_800g=copies*sum(ll.values()), agg_core_800g=copies*sum(au.values()),
                core_ports=cells*bundle, max_cell_oversub=round(max(trays)*EDGE/(AGGS*north*FABRIC), 6),
                cell_north_tbps=AGGS*north*FABRIC*copies/1000,
                single_agg_capacity_loss_fraction=1/AGGS,
                single_core_switch_per_cell_plane_rail_capacity_loss_fraction=bundle/(AGGS*north),
                one_local_core_path_loss_fraction=bundle/north)


def shallow(target):
    """512 x 200G effective ports, 4 rails x 4 planes; same NVL72 racks."""
    racks = math.ceil(target/72)
    trays = racks*18
    leaves = math.ceil(trays/256)
    assert leaves <= 512
    copies = 16
    return dict(gpus=racks*72, trays=trays, leaf=copies*leaves, spine=copies*256,
                switches=copies*(leaves+256), endpoints_200g=copies*trays,
                leaf_spine_200g=copies*leaves*256, ports_per_spine=leaves)


if __name__ == "__main__":
    rows = [measure(100_000, 13, 32, 4), measure(200_000, 25, 32, 2),
            measure(400_000, 50, 32, 1), measure(400_000, 50, 16, 1),
            measure(400_000, 50, 8, 1)]
    assert rows[2]["switches"] == 33_792 and rows[2]["endpoints_400g"] == 800_064
    assert rows[2]["leaf_agg_800g"] == rows[2]["agg_core_800g"] == 409_600
    assert rows[3]["switches"] == 29_696 and rows[3]["agg_core_800g"] == 204_800
    assert rows[4]["switches"] == 27_648 and rows[4]["agg_core_800g"] == 102_400
    assert shallow(400_000)["switches"] == 10_352
    if "--shallow" in sys.argv:
        rows = [shallow(n) for n in (100_000, 200_000, 400_000)]
    w = csv.DictWriter(sys.stdout, fieldnames=rows[0].keys(), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
