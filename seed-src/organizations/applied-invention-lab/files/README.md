# The Applied Invention Lab — Library Kit Tote Study

**SYNTHETIC practical problem and original dataset.** A fictional library-kit
service groups harmless paper, cloth, foam, and counting materials into
reusable totes. The working reference uses two integer capacity proxies:
volume units and weight units. They are not measured liters, kilograms,
physical dimensions, or safe handling limits.

## Run the offline computation

From `files/`, with Python 3.10 or newer:

```sh
python3 -I -B reference/test_tote_pack.py
python3 -I -B reference/tote_pack.py data --exact-small
python3 -I -B reference/run_experiment.py data
```

All code is original and standard-library-only. It reads the explicitly named
public source files, prints JSON, and performs no installation, network,
server, subprocess, persistence, identity, or external operation.

Eleven rows expand into 29 item instances across four scenarios. Three greedy
methods are compared. The dominant-load heuristic is **not always better**:
on `mixed-classroom`, it uses 7 bins versus input-order's 6 and volume-first's
8. The optional proof routine uses a lower bound when sufficient, or bounded
search for at most 12 items; it never calls an external solver.

The experiment runner uses a declared seed and 20 paired permutations per
scenario. It includes every trial, source hashes, and model limitations.
Repeatable synthetic computation is not real-world validation.

The five workspaces own framing, experiments, prototype instructions,
replication, and a cautious application hypothesis. A future physical-fit
study is a pending task; no mock tote has been packed by these files.
Commercial demand, novelty, patents, customer savings, physical fit, and
lifting safety are not established or claimed.
