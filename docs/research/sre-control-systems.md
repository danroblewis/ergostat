# The control systems SREs already run: research for an ergostat library

Research for `docs/proposals/external-systems.md` (observed controllers and a library of known
laws). Written 2026-11-16. No code was changed. Every law below is cited to a primary source
(official docs, the controller's source at a named file, a KEP or RFC, a paper); where the
source is code, it was read on the default branch on this date and line numbers will drift.
Tags: **[derived]** our inference from cited material; **[unverified]** could not be confirmed;
**[secondary]** vendor marketing or a third party; **[M]** a standard result or recollection not
re-checked this session; **[V]** checked this session; **[correction]** where the source
contradicts a common assumption.

Contents: 0 summary · 1 the frame · 2 Kubernetes (HPA, VPA, cluster autoscaler, rollout, PDB,
kubelet eviction, ScaleOps) · 3 Google Cloud (Pub/Sub, Cloud Run/Knative, MIG) · 4 S3 · 5 Kafka +
KEDA · 6 PostgreSQL · 7 MySQL/InnoDB · 8–9 database pathologies and models · 10 cross-cutting
loops (retries, budgets and breakers, token buckets, GC pacers, TCP, outlier ejection, alerting and
paging, queueing) · 11 published models · 12 modelling tools and XMILE · 13 proposed library
layout · 14 build order and the pathology each example demonstrates.

## 0. Summary of the top findings

1. **Every system on the list is a sampled controller with a dead band, a rate limit and a
   filter, and the parameters are public.** The HPA is `ceil(ready × metric/target)` with a 0.1
   dead band, a 300 s rolling-max filter on scale-down, rate limits of 100% or 4 pods per 15 s, and
   a 15 s sampling period (`replica_calculator.go`, `horizontal.go`). Postgres autovacuum is a
   threshold `50 + 0.2 × reltuples` checked every minute with an actuator rate-limited to 200
   cost credits per 2 ms, shared across three workers (`autovacuum.c`, `vacuum.c`). InnoDB's page
   cleaner is a nonlinear proportional controller on checkpoint age (`f^1.5 / 7.5`) averaged with
   feed-forward terms (`buf0flu.cc`). The Postgres checkpointer is a bang-bang tracker of a time
   ramp and a WAL ramp (`IsCheckpointOnSchedule`). Each fits ergostat's block vocabulary with a
   few additions (section 13.3).
2. **Several controllers people think of as simple are adaptive or gain-scheduled.** The Pub/Sub
   client sets its lease to the p99 of observed processing time; Knative switches between a 60 s
   and a 6 s window at 200% load; the VPA's bounds widen with little history (`(1 + 1/days)`) and
   narrow with more; G1 uses a pause-cost predictor; Go's pacer predicts when to start marking from
   a max of the last five cons/mark ratios. Their "law" includes a state (a histogram, a window,
   a mode) that is itself a stock.
3. **The sensors are often not what people assume, and that is where the surprising dynamics
   live.** HPA CPU utilisation is usage divided by *requests*, so a right-sizer (VPA, ScaleOps) that
   lowers requests raises utilisation and makes the HPA scale out: a documented conflict (VPA known
   limitations) and an undocumented reinforcing loop. The cluster autoscaler reads requests, not
   usage. MySQL's `Seconds_Behind_Source` reads 0 while the receiver is behind;
   postgres_exporter's `pg_replication_lag_seconds` overstates lag on an idle primary. Pub/Sub
   metrics are visible only 2–4 minutes late, which is dead time in any loop built on them.
4. **The reinforcing loops behind the worst incidents are named and measured in the literature.**
   Retries are "by far the most common sustaining effect" of metastable failures (Huang et al.,
   OSDI'22: over half of 22 incidents); 3 retries over 5 layers is 243× load (AWS Builders'
   Library); the fixes are balancing loops that are themselves stocks (gRPC retry throttling, the
   AWS SDK retry quota, Finagle/Linkerd/Envoy retry budgets, the SRE book's client-side throttling
   with K = 2). Outlier ejection (`max_ejection_percent` 10, panic at 50%), Postgres's full-page-write
   checkpoint loop and Kafka rebalance-on-scale are the same shape.
5. **Published control models of these exact controllers are few, which is the opportunity.**
   Found: an IEEE Access 2025 stability analysis of the HPA loop (Serracanta et al.), the DB2
   utility-throttling controller (Parekh et al., ACC 2004: the closest analogue to a controlled
   vacuum), Autopilot (the VPA's ancestor), M/M/c models of pods (AHPA), the TCP/AQM fluid model
   (Misra–Gong–Towsley; Hollot et al.), and Hellerstein et al. (2004) for method (first-order ARX
   identification, PI design). Not found: any control or SD model of the VPA recommender, the
   cluster autoscaler, autovacuum, InnoDB adaptive flushing, Pub/Sub lease management, or Knative
   panic mode. A library that writes these down as checked fragments would be new.
6. **ScaleOps's law is not public** (docs are behind sign-in). It must ship as a VPA-shaped
   fragment with `law: identified`: its structure and observable writes are known, its
   parameters are found from the record.
7. **XMILE is a practical export format and a weak import format.** It is an OASIS standard
   (2015), Stella's native file format, read by PySD, readsdr and others, and has the builtins
   ergostat needs for processes (SMTH1, DELAY3, DELAYN, conveyors, queues as an option). Vensim does
   not write it natively (Vensim users export through Stella or other tools) and it has no notion of
   a controller, a sensor binding or a goal, so a round trip loses ergostat's control layer. Export
   the SD perspective to XMILE; keep ergostat YAML as the source. Component libraries worth copying:
   Modelica's (`Blocks.Continuous.LimPID`, `Nonlinear.Limiter`, `Logical.Hysteresis`, typed
   connectors, parameters with defaults and documentation), Hines' SD "molecules" (named reusable
   structures), and MATLAB's `procest` (process models `P1D`: gain, time constant, delay) as the
   identification target for each fragment.
8. **Build order:** the HPA on a queue first (the kube-sim demo exists, every reader knows it, it
   shows saturation, lag and over-provisioning), then retries with a budget (the metastable failure,
   the most convincing "this is a control system" story), then HPA × VPA/ScaleOps on CPU (an
   interference loop only a model shows), then Pub/Sub backlog autoscaling with ack-deadline
   redelivery, then Postgres autovacuum with a long transaction, then alert rules and escalation
   (section 14).

## 1. The frame: what a fragment must capture

Each system below is read in ergostat's two perspectives (docs/SPEC.md §1a):

- **System dynamics:** the stocks (what accumulates: replicas, pods starting, backlog, dead
  tuples, WAL, history list, tokens, heap, open incidents), the flows that fill and drain them, the
  signed influences, and the loops (R or B).
- **Control:** for each controller, its process variable (what it reads, through which sensor),
  setpoint, law, manipulated variable (what it sets: a flow, or another controller's setpoint),
  sampling period, dead band, rate limits, filters and their windows, saturation bounds, and the
  delays between its output and the process's response.

For an *observed* controller ergostat runs nothing: it reads the controller's input and output
from the systems that hold them, declares the law where it is public, and tests the declaration
against what the controller did (external-systems.md). So for each controller the research
records three things: the **law with exact parameter names and defaults**, the **metric that
measures each input and output read-only**, and the **pathologies** the law makes possible, each
with the signature it leaves in those metrics.

Three things recur and decide the library's block vocabulary:

1. **Hysteresis in time, not only in level.** HPA stabilisation windows (rolling max/min), Prometheus
   `for:` / `keep_firing_for:`, kubelet `eviction-pressure-transition-period`, MIG's 10-minute
   scale-in peak, Knative's sticky panic, circuit breakers' open wait. ergostat has `onoff` with
   `until`, `min-on`/`min-off`, `timer` and `delay`; it lacks a **windowed max/min/mean/percentile**.
2. **Estimators with memory** (histograms, EWMAs, rolling windows) sit between the sensor and the
   law: the VPA's decaying histograms, Pub/Sub's p99 lease, Postgres's bgwriter and checkpoint
   distance estimates (fast up, slow down), InnoDB's averaged rates, Go's max-of-five cons/mark.
   They are stocks of information; SD calls them perceived values (MODELLING.md §4), and SMTH1 is
   their XMILE builtin.
3. **Quantisation and integer arithmetic matter.** `ceil` in the HPA, KEDA and Knative; truncation
   on HPA percent scale-down; integer division in InnoDB's `io_capacity_max / io_capacity`; percent
   rounding in rollouts (`maxSurge` up, `maxUnavailable` down). They create dead bands and limit
   cycles at small replica counts.

## 2. Kubernetes

Sampling, laws and defaults below are read from source on `master` (2026-11-16) unless a doc is
cited. Tags: **[derived]** is our inference from the cited material; **[unverified]** could not be
confirmed; **[secondary]** is vendor marketing or a third party.

### 2.1 Horizontal pod autoscaler (autoscaling/v2)

**Stocks.** `replicas` (the Deployment's `spec.replicas`, set through the scale subresource); the
pods in each readiness state (pending, starting, ready) as a material delay between "desired" and
"serving"; the stabilisation buffer of past recommendations (a stock of information, not material:
the controller's memory).

**Flows.** Pods created (scale-up), pods deleted (scale-down), pods becoming ready (the start-up
delay), load arriving (exogenous request rate, a disturbance), work served (`ready × per-pod rate`).

**Controller law.** `pkg/controller/podautoscaler/replica_calculator.go`,
`horizontal.go` (https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/podautoscaler/replica_calculator.go,
https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/podautoscaler/horizontal.go),
docs https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/:

```
ratio      = metric / target                       # utilisation = Σusage / Σrequests (of REQUESTS)
if (1 - tol_down) <= ratio <= (1 + tol_up): desired = current      # dead band, tolerance 0.1
else desired = ceil(ratio × readyPodsWithMetrics)                # code multiplies ready pods, not spec.replicas
# AverageValue targets (external/object): desired = ceil(total / targetPerPod); at 0 replicas ceil(ratio)
multiple metrics: desired = max over metrics                     # if some fail and valid ones say down: no change
stabilise:  upRec   = min(recommendations in scaleUp window)     # 0 s by default
            downRec = max(recommendations in scaleDown window)   # 300 s by default
            desired = clamp(desired, upRec, downRec)             # rolling max/min: hysteresis in time
rate limit: per policy over periodSeconds (start = current − added + removed in the period)
            up   Pods: start + v       Percent: ceil(start × (1 + v/100))
            down Pods: start − v       Percent: int(start × (1 − v/100))
            selectPolicy Max (default: largest change) | Min | Disabled
bounds:     clamp(desired, minReplicas (default 1), maxReplicas)
```

Defaults (`pkg/apis/autoscaling/v2/defaults.go`, https://github.com/kubernetes/kubernetes/blob/master/pkg/apis/autoscaling/v2/defaults.go):

```yaml
scaleUp:   {stabilizationWindowSeconds: 0,   selectPolicy: Max,
            policies: [{type: Percent, value: 100, periodSeconds: 15}, {type: Pods, value: 4, periodSeconds: 15}]}
scaleDown: {stabilizationWindowSeconds: 300, selectPolicy: Max,
            policies: [{type: Percent, value: 100, periodSeconds: 15}]}
```

(KEP-853's README says "per minute"; the code says 15 s: trust the code,
https://github.com/kubernetes/enhancements/blob/master/keps/sig-autoscaling/853-configurable-hpa-scale-velocity/README.md.)
Legacy path without `behavior`: scale-up capped at `max(2 × current, 4)` per sync
(`scaleUpLimitFactor`, `scaleUpLimitMinimum`). [unverified] which path a v2 object without
`behavior` takes after defaulting.

kube-controller-manager flags (cluster-wide;
https://github.com/kubernetes/kubernetes/blob/master/cmd/kube-controller-manager/app/options/hpacontroller.go,
defaults https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/podautoscaler/config/v1alpha1/defaults.go):

| Flag | Default | Role in the loop |
|---|---|---|
| `--horizontal-pod-autoscaler-sync-period` | 15s | sampling period |
| `--horizontal-pod-autoscaler-tolerance` | 0.1 | dead band |
| `--horizontal-pod-autoscaler-downscale-stabilization` | 5m | default scale-down window |
| `--horizontal-pod-autoscaler-cpu-initialization-period` | 5m | CPU samples of young pods distrusted |
| `--horizontal-pod-autoscaler-initial-readiness-delay` | 30s | readiness flaps ignored after start |
| `--concurrent-horizontal-pod-autoscaler-syncs` | 5 | |

Sensor handling. Missing samples: on scale-down a pod without a sample is assumed at
`max(100%, target)` (resource) or the target; on scale-up at 0. Unready pods count as 0 usage
when scaling up, else dropped; if that reverses the direction or lands in the band, no change.
Per-HPA asymmetric tolerance `behavior.scaleUp.tolerance` / `scaleDown.tolerance` (KEP-4951,
gate `HPAConfigurableTolerance`, stable v1.37,
https://github.com/kubernetes/enhancements/blob/master/keps/sig-autoscaling/4951-configurable-hpa-tolerance/kep.yaml).
Scale to zero (`HPAScaleToZero`, KEP-2021, beta on by default v1.37,
https://github.com/kubernetes/enhancements/blob/master/keps/sig-autoscaling/2021-scale-from-zero/kep.yaml):
`minReplicas: 0` only with an Object or External metric; condition `ScaledToZero`.

**Status as controller output.** `status.desiredReplicas`, `currentReplicas`, `currentMetrics`,
`lastScaleTime`; conditions `AbleToScale` (…`ScaleUpStabilized`, `ScaleDownStabilized`),
`ScalingActive` (`ValidMetricFound` / `FailedGet*Metric`, `ScalingDisabled`), `ScalingLimited`
(`TooFewReplicas`, **`TooManyReplicas` = saturation**, `ScaleUpLimit`, `ScaleDownLimit`).

**Delays in series** [derived]: metrics-server `--metric-resolution` 60s (FAQ advises ≥15s, the
kubelet's resolution; https://github.com/kubernetes-sigs/metrics-server/blob/master/FAQ.md) + sync
≤15s + rate limit (≤ ×2 or +4 per 15s) + scheduling + image pull + start + readiness + the 5m CPU
initialisation exclusion. If pods do not fit, the cluster autoscaler adds its own delay (2.3).

**Metrics** (kube-state-metrics,
https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/workload/horizontalpodautoscaler-metrics.md):
`kube_horizontalpodautoscaler_status_desired_replicas` (controller output),
`_status_current_replicas`, `_spec_min_replicas`, `_spec_max_replicas` (bounds),
`_status_target_metric{metric_name,metric_target_type}` (the measured process variable),
`_spec_target_metric` (setpoint, EXPERIMENTAL), `_status_condition{condition,status}`,
`_spec_behavior_scale_{up,down}_tolerance` (EXPERIMENTAL). Process: `container_cpu_usage_seconds_total`,
`kube_pod_container_resource_requests{resource="cpu"}` (the divisor of utilisation),
`kube_deployment_status_replicas_ready`. All read-only via Prometheus or `get/watch` on the HPA.
Not exported: per-metric proposals, the stabilisation buffer (reconstructable from the record of
desired replicas).

### 2.2 Vertical pod autoscaler

Three controllers: **recommender** (estimator), **updater** (actuator by eviction or in-place
resize), **admission controller** (actuator at pod creation). Source tree
https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler.

**Stocks.** Per-container decaying histograms of CPU usage samples and of memory peaks (memory
of the estimator: checkpointed as `VerticalPodAutoscalerCheckpoint` objects); the recommendation
(`status.recommendation.containerRecommendations[].{target,lowerBound,upperBound,uncappedTarget}`);
the pods' current requests; pods waiting to be updated.

**Recommender law** (`pkg/recommender/logic/recommender.go`,
https://github.com/kubernetes/autoscaler/blob/master/vertical-pod-autoscaler/pkg/recommender/logic/recommender.go;
flags in `pkg/recommender/config/config.go`):

```
cpu_target    = P(target-cpu-percentile=0.9) of decaying CPU histogram × (1 + recommendation-margin-fraction=0.15)
mem_target    = P(0.9) of 24h peaks over memory-aggregation-interval-count=8 intervals × 1.15
lower/upper   = P(0.5) / P(0.95) × 1.15 × (1 + m/historyDays)^exp      # upper m=1, exp=+1 (1 day ⇒ ×2, 7 days ⇒ ×1.14)
                                                                        # lower m=0.001, exp=−2
floors        = pod-recommendation-min-cpu-millicores=25, pod-recommendation-min-memory-mb=250 (split across containers)
decay         = sample weight × 2^(t / half-life), cpu/memory-histogram-decay-half-life = 24h
buckets       = exponential, +5% per bucket; cpu 0.01–1000 cores, memory 1e7–1e12 bytes
OOM           = memoryNeeded = max(max(request, peak) + oom-min-bump-up-bytes=100MiB, × oom-bump-up-ratio=1.2), added as a sample
period        = recommender-interval = 1m
```

Updater (`pkg/updater/config/config.go`, `pkg/updater/priority/update_priority_calculator.go`):
`updater-interval` 1m, `min-replicas` 2, `eviction-tolerance` 0.5, `eviction-rate-limit` −1 (off),
`eviction-rate-burst` 1, `pod-update-threshold` 0.1,
`in-recommendation-bounds-eviction-lifetime-threshold` 12h, `evict-after-oom-threshold` 10m. A pod
is updated when its requests are **outside [lowerBound, upperBound]** (a dead band, which with the
bounds' confidence multiplier is wide early and narrows with history), or after a quick OOM, or
when it has lived ≥12h and differs by ≥10%. Modes (`updateMode`): `Off`, `Initial`, `Recreate`
(default), `Auto` (deprecated = Recreate), `InPlaceOrRecreate` (GA in VPA 1.6.0), `InPlace` (alpha
1.7.0); Kubernetes in-place resize KEP-1287 stable v1.35
(https://github.com/kubernetes/autoscaler/blob/master/vertical-pod-autoscaler/docs/features.md).
Known limitations: not with an HPA on the same CPU or memory metric
(https://github.com/kubernetes/autoscaler/blob/master/vertical-pod-autoscaler/docs/known-limitations.md).

**Metrics.** Inputs `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`,
`container_oom_events_total` (cAdvisor, https://github.com/google/cadvisor/blob/master/docs/storage/prometheus.md).
Outputs: `kube_verticalpodautoscaler_*` were removed from kube-state-metrics in v2.9.0
(https://github.com/kubernetes/kube-state-metrics/releases/tag/v2.9.0); rebuild with Custom
Resource State config (`kube_customresource_verticalpodautoscaler_*`, names set by the config,
https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/extend/customresourcestate-metrics.md)
or read the VPA object's status. The actuation is visible as steps in
`kube_pod_container_resource_requests`.

### 2.3 Cluster autoscaler (and Karpenter)

**Stocks.** Nodes per node group (and their provisioning states: requested, booting, ready,
unneeded, draining); unschedulable pods (the error signal); requested resources vs allocatable.

**Law** (FAQ, https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/FAQ.md). Every
`scan-interval` (10s): if pods are unschedulable, simulate scheduling on each node group's template
node; the `expander` (default `least-waste`; also `random`, `most-pods`, `least-nodes`, `price`,
`priority`, `grpc`, chainable) picks a group; request the nodes. Scale-down: node utilisation =
max(Σ CPU requests / allocatable, Σ memory requests / allocatable); a node below
`scale-down-utilization-threshold` (0.5) whose pods fit elsewhere for `scale-down-unneeded-time`
(10m) is drained (PDBs respected through the eviction API, `max-pod-eviction-time` 2m) and deleted.
Note the sensor is **requests**, not usage: CA and HPA read different quantities.

| Flag | Default |
|---|---|
| `scan-interval` | 10s |
| `scale-down-utilization-threshold` | 0.5 |
| `scale-down-unneeded-time` | 10m |
| `scale-down-unready-time` | 20m |
| `scale-down-delay-after-add` | 10m |
| `scale-down-delay-after-delete` | 0s (FAQ table; [unverified] elsewhere described as the scan interval) |
| `scale-down-delay-after-failure` | 3m |
| `max-node-provision-time` | 15m |
| `max-scale-down-parallelism` | 10 |
| `max-drain-parallelism` | 1 |
| `max-graceful-termination-sec` | 600 |
| `new-pod-scale-up-delay` | 0s |
| `max-total-unready-percentage` / `ok-total-unready-count` | 45 / 3 (cluster "safe to autoscale") |

SLO (unschedulable → cloud request): ≤30s (avg ~5s) under 100 nodes, ≤60s (avg ~15s) up to 1000;
node boot is extra. Headroom by low-priority pause pods (overprovisioning).

**Metrics** (`cluster_autoscaler_` prefix,
https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/proposals/metrics.md):
`unschedulable_pods_count`, `nodes_count{state}`, `unneeded_nodes_count`,
`unremovable_nodes_count{reason}`, `scale_down_in_cooldown`, `cluster_safe_to_autoscale`,
`scaled_up_nodes_total`, `scaled_down_nodes_total{reason}`, `failed_scale_ups_total{reason}`,
`evicted_pods_total`, `node_group_target_count` (needs `--emit-per-nodegroup-metrics`), and the
`cluster-autoscaler-status` ConfigMap. Requires scraping CA's own `/metrics`.

**Karpenter** (https://karpenter.sh/docs/concepts/disruption/): consolidation
(`consolidationPolicy: WhenEmptyOrUnderutilized` default, `consolidateAfter` default 0s, timer reset
on pod churn), disruption budgets (default `nodes: 10%`, by `reasons`, `schedule` + `duration`),
`expireAfter` 720h (not budget-limited), `terminationGracePeriod`, `karpenter.sh/do-not-disrupt`.

### 2.4 Deployment rollout

A **controlled transfer** between two stocks, old ReplicaSet → new ReplicaSet
(https://kubernetes.io/docs/concepts/workloads/controllers/deployment/), under two constraints:
`old + new ≤ replicas + maxSurge` (25%, rounded up) and `available ≥ replicas − maxUnavailable`
(25%, rounded down). A new pod counts as available after Ready + `minReadySeconds` (0): that is
the transfer delay. `progressDeadlineSeconds` (600) is a watchdog timer
(`Progressing=False, ProgressDeadlineExceeded`); `revisionHistoryLimit` 10. Proportional scaling
splits an HPA's change mid-rollout across both ReplicaSets (the HPA and the rollout share the
actuator). Metrics: `kube_deployment_spec_replicas`, `kube_deployment_status_replicas{,_updated,_ready,_available,_unavailable}`,
`kube_deployment_status_terminating_replicas`, `kube_deployment_status_condition`,
`kube_deployment_spec_strategy_rollingupdate_max_{surge,unavailable}`,
`kube_deployment_metadata_generation` vs `_status_observed_generation`, and
`kube_replicaset_status_replicas` per ReplicaSet
(https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/workload/deployment-metrics.md).

### 2.5 PodDisruptionBudget

A **constraint on a flow** (voluntary evictions), not a controller with a goal of its own.
`minAvailable` xor `maxUnavailable`; status `currentHealthy`, `desiredHealthy`,
`disruptionsAllowed = max(0, currentHealthy − desiredHealthy)` [derived], `expectedPods`;
`unhealthyPodEvictionPolicy: IfHealthyBudget` (default) | `AlwaysAllow`
(https://kubernetes.io/docs/tasks/run-application/configure-pdb/). The eviction API returns 429
when blocked (https://kubernetes.io/docs/concepts/scheduling-eviction/api-eviction/).
**Rollouts are not limited by PDBs** (https://kubernetes.io/docs/concepts/workloads/pods/disruptions/):
PDBs limit drains (CA, Karpenter, `kubectl drain`, the VPA updater). Metrics
`kube_poddisruptionbudget_status_{current_healthy,desired_healthy,pod_disruptions_allowed,expected_pods}`
(https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/policy/poddisruptionbudget-metrics.md).

### 2.6 Kubelet node-pressure eviction

A threshold controller with hysteresis
(https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/; defaults
https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/eviction/defaults_linux.go).
Signals: `memory.available = capacity − workingSet` (inactive_file excluded), `nodefs.available`,
`nodefs.inodesFree`, `imagefs.available`, `imagefs.inodesFree`, `pid.available`. Default
`--eviction-hard`: `memory.available<100Mi`, `nodefs.available<10%`, `nodefs.inodesFree<5%`,
`imagefs.available<15%`, `imagefs.inodesFree<5%`. `--eviction-soft` with
`--eviction-soft-grace-period` (a `for:`-like timer), `--eviction-max-pod-grace-period`;
`--eviction-minimum-reclaim` (default 0: reclaim to threshold + this, the release point);
`--eviction-pressure-transition-period` 5m (minimum time a condition stays on: `min-on`);
sampled every `housekeeping-interval` 10s (or memcg notification). Ignores PDBs. Order: pods over
requests first, by priority then by excess. Conditions `MemoryPressure`, `DiskPressure`,
`PIDPressure` (taints stop new pods: a second actuator). Metrics `kubelet_evictions{eviction_signal}`
(ALPHA, https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/metrics/metrics.go),
`kube_node_status_condition{condition="MemoryPressure"}`, `container_memory_working_set_bytes`,
`node_memory_MemAvailable_bytes` (node_exporter). Below it, the kernel OOM killer is a faster
uncoordinated controller (`oom_score_adj`: Guaranteed −997, BestEffort 1000).

### 2.7 ScaleOps (commercial right-sizer)

Public parameter-level docs are behind sign-in (`docs.scaleops.com` redirects to
`api.scaleops.com/documentation`). From its product pages [secondary]
(https://scaleops.com/product/automated-pod-rightsizing/,
https://scaleops.com/blog/why-pod-rightsizing-fails-in-production-a-deep-dive-into-vpa-and-what-actually-works/):
continuous rightsizing of CPU and memory requests (limits, ephemeral storage; DaemonSets per node
size), applied at pod creation or by native in-place resize; per-workload policies (percentile
targets, observation windows, limit strategy, headroom per namespace); automatic workload-type
detection; burst reaction (moves to higher percentiles on a sustained rise); immediate memory bump
after OOM; CPU boost at start; "runs alongside HPA/KEDA" with policies "that avoid conflicts"
(mechanism not given); replica optimisation that "manages min and max replica counts and
triggers" with predictive scaling; node bin-packing guiding Karpenter; a read-only mode.

**Unknown, so it must be modelled as an observed controller whose law is identified, not
declared:** the recommendation law (percentiles, windows, decay), the update cadence and threshold,
whether "downscale-only" is a mode or a policy, how it coordinates with HPA (changes the HPA
target or minReplicas, or only counts it in; a third party, CloudBolt, says it alters HPA
targets: unconfirmed), the prediction model, the in-place → eviction fallback, its own metrics.
Its writes are observable read-only: steps in `kube_pod_container_resource_requests`/`_limits`,
changes to `kube_horizontalpodautoscaler_spec_*`, pod restarts. The ergostat fragment should
therefore be the VPA's structure with `law: identified`, and the identification target is
"requests as a function of the usage percentile over a window, with a dead band and a lag".

### 2.8 Pathologies, as dynamics

| Pathology | Dynamics | Evidence in metrics | Source |
|---|---|---|---|
| HPA flapping | dead time + noisy load ⇒ limit cycle; damped by the 300 s rolling max and the 0.1 band; `ceil` adds quantisation | `desired_replicas` alternating with period ≈ 2× loop delay | HPA docs (thrashing), KEP-853 |
| HPA lag | the delay chain in 2.1; scale-up ≤ ×2 per 15 s | error integral after a step in load | parameters above |
| Saturation | pinned at `maxReplicas`, loop open | `desired == spec_max`, condition `ScalingLimited/TooManyReplicas`, load still rising | horizontal.go |
| Frozen scale-down | a failing metric blocks scale-down | `ScalingActive=False` + replicas stuck high | HPA docs |
| HPA × VPA on CPU | utilisation is usage/**request**: VPA lowers requests ⇒ utilisation rises ⇒ HPA adds pods ⇒ per-pod usage falls ⇒ VPA lowers requests again: a reinforcing ratchet (more pods, smaller requests) | requests stepping down while replicas step up | VPA known limitations; [derived] |
| Request-relative CPU as sensor | relative and absolute utilisation diverge | | Casalicchio 2019, *Cluster Computing* 22, https://link.springer.com/article/10.1007/s10586-018-02890-1 |
| HPA + CA cascade | pods unschedulable ⇒ CA scan + SLO + node boot (up to 15 m) in series after HPA's delay: a second-order lag the HPA keeps "correcting" (it only counts ready pods) | `unschedulable_pods_count` > 0 while HPA desired > ready | CA FAQ |
| CA vs HPA scale-down | HPA scale-down empties nodes after a 5 m window; CA removes them after 10 m; a load return then waits for nodes | node count lags replica count | [derived] |
| Eviction cascade | evicted pods land on other nodes and push them under pressure; hard eviction has grace 0; damped by `minimum-reclaim` and the 5 m transition period | `kubelet_evictions` on several nodes in sequence | eviction docs |
| Drain blocked | `disruptionsAllowed = 0` (minAvailable = replicas, unhealthy pods) ⇒ CA/Karpenter cannot remove the node: over-provisioning | `pod_disruptions_allowed == 0`, `unremovable_nodes_count{reason}` | PDB docs, CA FAQ |
| Stuck rollout | not PDBs: pods never Ready, or `maxUnavailable: 0` with no capacity ⇒ `ProgressDeadlineExceeded` | `status_replicas_updated < spec_replicas` for > 600 s | Deployment docs |

### 2.9 Published models

- Serracanta, Lukács, Rodriguez-Natal, Cabellos, Rétvári, "On the Stability of the Kubernetes
  Horizontal Autoscaler Control Loop", *IEEE Access* 2025, https://doi.org/10.1109/ACCESS.2025.3526751:
  a control-theoretic model of the HPA, stability analysis, testbed, extended to service graphs
  (coupled HPAs). The closest published match to this library. [equations not read]
- Nguyen et al., "Horizontal Pod Autoscaling in Kubernetes for Elastic Container Orchestration",
  *Sensors* 20(16):4621, 2020, https://pmc.ncbi.nlm.nih.gov/articles/PMC7471989/: experiments on
  sync period, readiness, cooldown, metrics-server vs Prometheus metrics.
- Baresi, Guinea, Leva, Quattrocchi, "A Discrete-Time Feedback Controller for Containerized Cloud
  Applications", FSE 2016, https://doi.org/10.1145/2950290.2950328.
- Baresi, Hu, Quattrocchi, Terracciano, "KOSMOS: Vertical and Horizontal Resource Autoscaling for
  Kubernetes", ICSOC 2021 (https://github.com/deib-polimi/kosmos): control-theoretic vertical
  scaling with a horizontal heuristic.
- Gias, Casale, Woodside, "ATOM: Model-Driven Autoscaling for Microservices", ICDCS 2019: layered
  queueing network solved at run time.
- Rzadca et al., "Autopilot: Workload Autoscaling at Google", EuroSys 2020,
  https://research.google/pubs/autopilot-workload-autoscaling-at-google-scale/: the VPA's design
  ancestor (decaying histograms, moving windows).
- Zhou et al., "AHPA", arXiv:2303.03640, https://arxiv.org/abs/2303.03640: pods as M/M/c (Erlang C
  + Little's law) with forecasting.
- No peer-reviewed control model of the VPA recommender or the cluster autoscaler was found.
## 3. Google Cloud: Pub/Sub, Cloud Run, managed instance groups

Checked 2026-11-16. **[correction]** marks where a common assumption (including ours in the
brief) differs from the source.

### 3.1 Pub/Sub

**Stocks** (Cloud Monitoring metric types, prefix `pubsub.googleapis.com/`,
https://docs.cloud.google.com/monitoring/api/metrics_gcp_p_z):

| Stock | Metric type |
|---|---|
| undelivered backlog | `subscription/num_undelivered_messages` (Google advises `subscription/num_unacked_messages_by_region`) |
| backlog bytes | `subscription/backlog_bytes` |
| age of the oldest unacked (a stock's age, the queue's "delay") | `subscription/oldest_unacked_message_age` (`_by_region`) |
| outstanding push messages (push window in use) | `subscription/num_outstanding_messages` |
| retained acked | `subscription/num_retained_acked_messages` |
| leased in the subscriber client (in flight) | none in Cloud Monitoring: client-side, bounded by flow control |

**Flows:** publish `topic/send_request_count` (and the count of `topic/message_sizes`); delivered
`subscription/sent_message_count` (pull `pull_request_count`, streaming `streaming_pull_response_count`,
push `push_request_count{response_code}`); acked `subscription/ack_message_count`; nacked
`subscription/nack_requests` (a GAUGE); lease extensions `mod_ack_deadline_message_count`;
**deadline expired ⇒ redelivered** `subscription/expired_ack_deadlines_count`; dead-lettered
`subscription/dead_letter_message_count`; retention expiry: no counter (inferred when the oldest
age passes retention). Latencies `ack_latencies`, `push_request_latencies`; health
`subscription/delivery_latency_health_score` (10-minute rolling window).

**Sampling and reporting delay** (part of every loop built on these): sampled every 60 s, visible
after 120 s (gauges), 181 s (`ack_message_count`, `sent_message_count`), 240 s
(`expired_ack_deadlines_count`, `dead_letter_message_count`, `num_outstanding_messages`), 360 s
(`nack_requests`, health score). Any autoscaler on backlog therefore has 2–4 minutes of dead time
before its own sync period.

**Subscription parameters** (https://docs.cloud.google.com/pubsub/docs/subscription-properties):
ack deadline 10 s (10–600 s); retention 7 d (10 min–31 d); expiration 31 d; dead-letter
`maxDeliveryAttempts` 5 (5–100, approximate,
https://docs.cloud.google.com/pubsub/docs/handling-failures). **Retry policy [correction]:** by
default none: redelivery is immediate; exponential backoff is opt-in with `minimumBackoff` /
`maximumBackoff` (console defaults 10 s / 600 s, range 0–600 s), per message, best effort
(https://docs.cloud.google.com/pubsub/docs/subscription-retry-policy). Exactly-once: pull only,
per region, higher latency (https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery).

**Controller 1: client lease management** (https://docs.cloud.google.com/pubsub/docs/lease-management).
The deadline it asks for tracks the **99th percentile of observed processing time**: an adaptive
setpoint from a histogram.

- Go (`pubsub/iterator.go`, https://github.com/googleapis/google-cloud-go/blob/main/pubsub/iterator.go):
  samples clamped to 10 s–10 min; `dl = bounded(P99(ackTimeDist), MinExtensionPeriod or 10 s
  (60 s with exactly-once), MaxExtensionPeriod)`; keep-alive tick `dl − gracePeriod (5 s)`; first
  tick at 5 s. `DefaultReceiveSettings`: `MaxExtension` 60 min, `MaxOutstandingMessages` 1000,
  `MaxOutstandingBytes` 1e9, `NumGoroutines` 10 (v2: 1)
  (https://github.com/googleapis/google-cloud-go/blob/main/pubsub/subscription.go).
- Java (`Subscriber.java`): `DEFAULT_MAX_ACK_EXTENSION_PERIOD` 60 min, stream deadline 10–600 s,
  flow control `MaxOutstandingElementCount` 1000, `MaxOutstandingRequestBytes` **100 MiB**
  [correction: not 1e9], `LimitExceededBehavior.Block`
  (https://github.com/googleapis/java-pubsub/blob/main/google-cloud-pubsub/src/main/java/com/google/cloud/pubsub/v1/Subscriber.java).
- Python (`types.py` FlowControl: `max_messages` 1000, `max_bytes` 100 MiB, `max_lease_duration`
  3600 s; https://github.com/googleapis/python-pubsub/blob/main/google/cloud/pubsub_v1/types.py).

**Controller 2: subscriber flow control, an on/off controller with hysteresis** (Python
`streaming_pull_manager.py`,
https://github.com/googleapis/python-pubsub/blob/main/google/cloud/pubsub_v1/subscriber/_protocol/streaming_pull_manager.py):
`load = max(leased_msgs / max_messages, leased_bytes / max_bytes)`; pause the stream at
`load ≥ 1.0` (`_MAX_LOAD`), resume below `0.8` (`_RESUME_THRESHOLD`). Messages older than
`max_lease_duration` are dropped from the lease and so redelivered (`leaser.py`).

**Controller 3: push delivery window, a server-side slow-start (AIMD-like)**
(https://docs.cloud.google.com/pubsub/docs/push): starts at a single-digit window, grows
exponentially on success, linearly above 3,000 outstanding per region; if average latency > 1 s or
acks < 99%, drops to a lower limit of 3,000. Push backoff: a subscription-wide pause of 100 ms–60 s
on nack or expiry, not configurable; with a retry policy the larger delay wins. Throughput ≈
outstanding ÷ latency (Little's law).

**Publisher batching** (Go `topic.go`: `DelayThreshold` 10 ms, `CountThreshold` 100,
`ByteThreshold` 1e6, flow control off by default; Java retry initial 100 ms × 4 to 60 s, total
600 s; https://github.com/googleapis/google-cloud-go/blob/main/pubsub/topic.go,
https://docs.cloud.google.com/pubsub/docs/flow-control-messages).

**Controller 4: autoscaling subscribers on backlog.**
- GKE HPA on the external metric `pubsub.googleapis.com|subscription|num_undelivered_messages`,
  `type: AverageValue` (tutorial uses 2 per pod), through the Custom Metrics Stackdriver Adapter
  (https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/autoscaling-metrics). Law:
  `ceil(backlog / perPodTarget)`, then the HPA's stabilisation (section 2.1).
- KEDA `gcp-pubsub` (https://keda.sh/docs/2.18/scalers/gcp-pub-sub/,
  https://github.com/kedacore/keda/blob/main/pkg/scalers/gcp_pubsub_scaler.go): `subscriptionName`,
  `mode` (default `SubscriptionSize`; any metric in PascalCase, e.g. `OldestUnackedMessageAge`),
  `value` 10, `activationValue` 0, `aggregation`, `timeHorizon`. **[correction]** deprecated
  (it relies on MQL); KEDA recommends its Prometheus scaler on Google's PromQL endpoint
  (https://keda.sh/blog/2025-09-15-gcp-deprecations).
- MIG autoscaler on a per-group metric with `singleInstanceAssignment` (3.3).
- Dataflow horizontal autoscaling on backlog and CPU, bounded by `maxNumWorkers`; internals not
  published (https://docs.cloud.google.com/dataflow/docs/horizontal-autoscaling).

### 3.2 Cloud Run (and Knative's KPA)

**[correction]** Cloud Run (fully managed) "does not use Knative but offers portability with the
Knative API" (https://cloud.google.com/blog/products/serverless/knative-based-cloud-run-services-are-ga):
the KPA is a documented relative, not its source.

Cloud Run law (https://docs.cloud.google.com/run/docs/about-instance-autoscaling):

```
instances_cpu  = ceil( (avg CPU-seconds/s over 1 min ÷ CPUs per instance) ÷ 0.6 )
instances_conc = ceil( max(1-min avg, 10-min avg concurrent requests) ÷ max concurrency ÷ 0.6 )
dead band ±10% of target (54–66%)
scale-down: idle instances kept up to 15 min (GPU 10 min); deprioritised in two groups
at max instances: requests wait up to max(3.5 × avg startup, 10 s), then 429; overshoot normally < 2×
inner loop (adaptive concurrency): CPU > 90% for 1 s ⇒ instance limit −1; at limit and CPU < 70% for 1 s ⇒ +1
```

Concurrency default 80 (console) or 80 × vCPU (CLI), max 1000
(https://docs.cloud.google.com/run/docs/about-concurrency). Default max instances [unverified].
Metrics (`run.googleapis.com/`, 60 s sampling, 120 s delay): `container/instance_count{state}`,
`container/max_request_concurrencies`, `container/startup_latencies`, `request_count`,
`request_latencies`, `container/cpu/utilizations`, `container/billable_instance_time`,
`pending_queue/pending_requests` (ALPHA).

Knative KPA (`config-autoscaler`,
https://github.com/knative/serving/blob/main/config/core/configmaps/autoscaler.yaml;
law `pkg/autoscaler/scaling/autoscaler.go`,
https://github.com/knative/serving/blob/main/pkg/autoscaler/scaling/autoscaler.go): scrape every
1 s, decide every 2 s.

```
targets: container-concurrency-target-default 100 × container-concurrency-target-percentage 70%
         (or requests-per-second-target-default 200)
windows: stable-window 60s; panic window = panic-window-percentage 10% of it (6 s)
desired_stable = ceil(stableConc / target), desired_panic = ceil(panicConc / target)
rate limits: ≤ ceil(max-scale-up-rate 1000 × ready), ≥ floor(ready / max-scale-down-rate 2)
panic on:  desired_panic / ready ≥ panic-threshold-percentage 200%
panic off: below threshold for a whole stable window; in panic it never scales down
scale-down-delay (0s): sliding max of desired; scale-to-zero-grace-period 30s
excess burst capacity = floor(ready × total − target-burst-capacity 211 − panicConc); < 0 ⇒ activator in path
```

This is a **gain-scheduled** controller: two windows, two gains, a mode switch with hysteresis in
time. Ranges: stable window 6 s–1 h, panic threshold 110–1000%
(https://knative.dev/docs/serving/autoscaling/kpa-specific/).

### 3.3 Compute Engine managed instance group autoscaler

(https://docs.cloud.google.com/compute/docs/autoscaler,
https://docs.cloud.google.com/compute/docs/reference/rest/v1/autoscalers.) Parameters:
`minNumReplicas`, `maxNumReplicas`, `coolDownPeriodSec` (now called the initialization period:
VMs younger than this are ignored; default 60 s), `cpuUtilization.utilizationTarget` (default 0.6),
`loadBalancingUtilization.utilizationTarget` (0.8), `customMetricUtilizations[]` with
`utilizationTargetType` `GAUGE` / `DELTA_PER_SECOND` / `DELTA_PER_MINUTE`, `singleInstanceAssignment`
(per-group metric: VMs = metric ÷ assignment; can reach 0), `scaleInControl.maxScaledInReplicas`
and `timeWindowSec`, `mode` `ON` / `ONLY_SCALE_OUT` / `OFF` (`recommendedSize` is computed even
when not ON: a free "advise mode" record), `predictiveMethod` (`OPTIMIZE_AVAILABILITY`: CPU only,
needs 3 days of history, uses up to 3 weeks, leads by the initialization period), schedules
(`minRequiredReplicas`, cron, `durationSec` ≥ 300). Law: recommended = **max over signals**;
scale-in uses the **peak over a 10-minute stabilisation period**
(https://docs.cloud.google.com/compute/docs/autoscaler/understanding-autoscaler-decisions).
Evaluation interval: "continuously" [unverified]. Metric: `compute.googleapis.com/instance_group/size`
(60 s, 240 s delay); **[correction]** no `autoscaler.googleapis.com` metrics exist: read
`recommendedSize` and `status` from the Autoscaler REST resource.

### 3.4 Pathologies

| Pathology | Loop | Signature | Source |
|---|---|---|---|
| ack deadline < processing time | **R**: expiry ⇒ redelivery ⇒ duplicate work ⇒ more load ⇒ slower ⇒ more expiry; the p99 lease extender is the balancing loop, slow because its histogram is long | `expired_ack_deadlines_count` rising with `ack_message_count` flat; 0.1–1% "might be healthy" | https://docs.cloud.google.com/pubsub/docs/monitoring |
| flow-control saturation | client holds 1000 msgs; paused at 1.0, resumes at 0.8; server backlog grows while CPU idles | backlog up, subscriber CPU low | §3.1 |
| push window collapse | latency > 1 s ⇒ window to 3,000 ⇒ throughput = window/latency falls | `num_outstanding_messages` plateau, latency up | push docs |
| poison message | immediate retry loops forever; with DLQ it leaves after ~5 attempts | small steady backlog, rising oldest age; `dead_letter_message_count` | handling-failures |
| cold-start lag | decision on max(1-min,10-min) concurrency + start-up delay; queued up to 3.5× startup then 429 | `pending_requests`, 429s after a step | Cloud Run docs |
| KPA panic oscillation | panic at 200% over 6 s, sticky ≥ 60 s, then ≤ 2× drop per tick: burst, overshoot, drop | pods saw-tooth after bursts | autoscaler.go; https://github.com/knative/serving/issues/15121 |
| MIG flapping / wrong scale-in | per-group backlog metric that excludes in-flight work reaches 0 ⇒ busy VMs removed | size drops while work in progress | https://docs.cloud.google.com/compute/docs/autoscaler/scaling-cloud-monitoring-metrics |

### 3.5 Published models

- Shahrad et al., "Serverless in the Wild", USENIX ATC 2020 (keep-alive policy as a control
  problem, hybrid histogram), https://www.usenix.org/conference/atc20/presentation/shahrad.
- Schuler, Jamil, Kühl, "AI-based resource allocation: RL for adaptive auto-scaling in serverless
  environments" (Knative concurrency), arXiv:2005.14410, https://arxiv.org/abs/2005.14410.
- Li et al., "Understanding Open Source Serverless Platforms", WoSC 2019, arXiv:1911.07449.
- None found for Pub/Sub lease management, the push slow-start or KPA panic mode as control
  systems: these would be original fragments.

## 4. Amazon S3

**Stocks.** Bytes and objects per storage class (`BucketSizeBytes{StorageType}`,
`NumberOfObjects`, daily, free); objects pending replication (`OperationsPendingReplication`,
`BytesPendingReplication`); objects queued for a lifecycle action (not exposed); the **prefix's
request capacity** (hidden: a stock S3 grows by partitioning, revealed only by 503s).

**Controller 1: per-prefix capacity scaling (S3's own, hidden).** At least 3,500
PUT/COPY/POST/DELETE and 5,500 GET/HEAD per second per partitioned prefix; scaling "happens
gradually", with 503 Slow Down meanwhile; advice: ramp gradually, retry small requests after 2 s
then 4 s more (https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html,
https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html).
Time constants not published: identify them.

**Controller 2: the SDK's retry and client-side rate limit**
(https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html). Modes `standard`
(default), `adaptive`, `legacy`; `max_attempts` 3.

- Standard, botocore before 2026 (`botocore/retries/standard.py` at 1.35.0,
  https://github.com/boto/botocore/blob/1.35.0/botocore/retries/standard.py): delay =
  `rand(0,1) × min(2^(attempt−1) s, 20 s)`; **retry quota** (a token bucket): 500 tokens, a retry
  costs 5 (10 for a timeout), a success refunds 1. When the quota is empty, retries stop: a
  balancing loop against retry storms.
- 2026 behaviour (opt-in `AWS_NEW_RETRIES_2026=true`; botocore `develop`): `rand × min(20 s,
  base × 2^retry)`, base 50 ms (transient) or 1 s (throttling, incl. `SlowDown`); retry cost 14
  (transient) or 5 (throttling); refund of the retry's cost on success after a retry, 1 on a
  first-try success; `x-amz-retry-after` honoured within [backoff, backoff + 5 s]. How the flag
  selects in source [unverified].
- Adaptive (`throttling.py`, `adaptive.py`, `bucket.py`,
  https://github.com/boto/botocore/blob/develop/botocore/retries/throttling.py): **CUBIC on the send
  rate**: on a throttle `W_max = rate`, `rate ×= β (0.7)`, `K = cbrt(W_max (1 − β) / C)` with
  `C = 0.4`; on success `rate = C (t − t_fail − K)^3 + W_max`; capped at `2 × measured rate`
  (0.5 s buckets, EWMA 0.8); floor 0.5 tokens/s; engages only after the first throttle; **one
  limiter per client instance** (so N processes are N uncoordinated controllers).

**Controller 3: lifecycle rules, a scheduled transfer between stocks**
(https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-transition-general-considerations.html,
https://docs.aws.amazon.com/AmazonS3/latest/userguide/how-to-set-lifecycle-configuration-intro.html).
Flows Standard → Standard-IA / Intelligent-Tiering / One Zone-IA / Glacier IR → Glacier FR → Deep
Archive, and expiration; at most one action per object per day; queued asynchronously ("days or
even weeks later"); billing changes at eligibility, not at the move; objects < 128 KB not
transitioned by default; minimum durations 30 d (IA), 90 d (Glacier IR/FR), 180 d (Deep Archive).
In SD terms a pipeline (conveyor) delay of N days between stocks.

**Metrics** (`AWS/S3`, https://docs.aws.amazon.com/AmazonS3/latest/userguide/metrics-dimensions.html):
daily `BucketSizeBytes{StorageType}`, `NumberOfObjects`; opt-in 1-minute request metrics per
`FilterId` (prefix, tag, access point): `AllRequests`, `GetRequests`, `PutRequests`, ...,
`4xxErrors`, `5xxErrors` (Average = error rate), `FirstByteLatency`, `TotalRequestLatency`; replication
`ReplicationLatency`, `OperationsPendingReplication`. Read-only through `GetMetricData`. 503s per
prefix are best seen in the request metrics filtered by prefix, or in client-side SDK metrics.

**Pathology: hot prefix + retry amplification.** Rate above the prefix limit ⇒ 503 ⇒ up to 2 more
attempts per request (load × 3) ⇒ more 503: **R**; balanced by the retry quota and adaptive mode,
and slowly by S3's partitioning. Retries were the most common sustaining effect in metastable
failures (Huang et al., OSDI '22, https://www.usenix.org/conference/osdi22/presentation/huang-lexiang).

## 5. Kafka consumer lag with KEDA

**Stocks.** Lag per partition = log-end offset − committed offset; retained log (segments).
**Flows.** Produce = rate of the log-end offset; consume = rate of the committed offset;
retention deletion = steps of the oldest offset (`log.retention.hours` 168, checked every
`log.retention.check.interval.ms` 300000, by `log.segment.bytes` 1 GiB segments;
https://kafka.apache.org/41/generated/kafka_config.html). Metrics (kafka_exporter,
https://github.com/danielqsj/kafka_exporter): `kafka_consumergroup_lag{consumergroup,topic,partition}`,
`kafka_consumergroup_lag_sum`, `kafka_consumergroup_current_offset`,
`kafka_topic_partition_current_offset`, `kafka_topic_partition_oldest_offset`,
`kafka_topic_partitions`, `kafka_consumergroup_members`. Burrow's status rules (OK / WARNING /
STALLED / STOPPED over a 10-commit window) are a ready-made classifier
(https://github.com/linkedin/Burrow/wiki/Consumer-Lag-Evaluation-Rules).

**Controller: KEDA Kafka scaler feeding an HPA**
(https://keda.sh/docs/2.18/scalers/apache-kafka/,
https://github.com/kedacore/keda/blob/main/pkg/scalers/kafka_scaler.go,
https://keda.sh/docs/2.18/reference/scaledobject-spec/):

```
lag_p = latest − committed     (no commit: latest policy ⇒ 1, or 0 with scaleToZeroOnInvalidOffset; earliest ⇒ latest − earliest)
excludePersistentLag: a partition whose offset did not move since the last poll counts 0 for scaling
cap (unless allowIdleConsumers): totalLag ≤ partitions (or partitions with lag) × lagThreshold  ⇒ replicas ≤ partitions
activation (KEDA, 0↔1): totalLag > activationLagThreshold (0)
scaling (HPA, 1↔N): AverageValue target = lagThreshold (10) ⇒ desired = ceil(totalLag / lagThreshold), then HPA behaviour
pollingInterval 30s; cooldownPeriod 300s (only for scaling to 0); minReplicaCount 0; maxReplicaCount 100;
fallback {failureThreshold, replicas}; advanced.horizontalPodAutoscalerConfig.behavior passed to the HPA
```

KEDA metrics (https://keda.sh/docs/2.18/integrations/prometheus/): `keda_scaler_metrics_value`,
`keda_scaler_active`, `keda_scaler_metrics_latency_seconds`, `keda_scaler_detail_errors_total`.

**Disturbance: the consumer-group rebalance.** Each scale event changes membership ⇒ rebalance ⇒
consumption pauses (eager: all partitions; cooperative KIP-429: only moved ones,
https://cwiki.apache.org/confluence/display/KAFKA/KIP-429%3A+Kafka+Consumer+Incremental+Rebalance+Protocol;
static membership KIP-345 avoids rebalances on restart within `session.timeout.ms` 45000,
https://cwiki.apache.org/confluence/display/KAFKA/KIP-345%3A+Introduce+static+membership+protocol+to+reduce+consumer+rebalances).
Consumer defaults `max.poll.interval.ms` 300000, `max.poll.records` 500,
`heartbeat.interval.ms` 3000 (https://kafka.apache.org/41/generated/consumer_config.html).

**Pathology: scaling-induced lag (R).** Lag up ⇒ scale out ⇒ rebalance pause ⇒ lag up more ⇒
scale out more, until the partition cap (saturation: adding consumers beyond partitions does
nothing). Bounded by the HPA's 300 s scale-down window. Published: Landau, Saurabh, Andrade,
Barbosa, "Multi-Objective Optimization of Consumer Group Autoscaling in Message Broker Systems",
arXiv:2402.06085 (https://arxiv.org/abs/2402.06085), bin packing with rebalance cost; Wu, Shang,
Wolter, "Performance Prediction for the Apache Kafka Messaging System", 2019 (queueing model,
https://ieeexplore.ieee.org/document/8855525).
## 6. PostgreSQL (defaults PG18)

Laws read from source on `REL_18_STABLE`
(https://github.com/postgres/postgres/tree/REL_18_STABLE, "PG" below); defaults from
`src/backend/utils/misc/postgresql.conf.sample`. Line numbers drift.

### 6.1 Autovacuum

**Stocks** (per table): dead tuples `pg_stat_user_tables.n_dead_tup`; inserts since vacuum
`n_ins_since_vacuum`; changes since analyze `n_mod_since_analyze`; XID age
`age(pg_class.relfrozenxid)` (and `age(pg_database.datfrozenxid)`, `mxid_age(relminmxid)`); bloat
(no counter: estimate from `relpages` vs `reltuples`, or `pgstattuple`); frozen fraction
`relallfrozen / relpages` (PG18). **Flows:** `n_tup_upd` + `n_tup_del` fill dead tuples (HOT
pruning drains some without vacuum); vacuum drains them (`autovacuum_count`,
`total_autovacuum_time`, https://www.postgresql.org/docs/18/monitoring-stats.html).

**Trigger law** (`PG src/backend/postmaster/autovacuum.c`, `relation_needs_vacanalyze()`):

```
vacthresh    = autovacuum_vacuum_threshold (50) + autovacuum_vacuum_scale_factor (0.2) × reltuples
               capped at autovacuum_vacuum_max_threshold (100,000,000; PG18; −1 off)
vacinsthresh = autovacuum_vacuum_insert_threshold (1000)
               + autovacuum_vacuum_insert_scale_factor (0.2) × reltuples × (1 − relallfrozen/relpages)   # PG18 form
anlthresh    = autovacuum_analyze_threshold (50) + autovacuum_analyze_scale_factor (0.1) × reltuples
vacuum  if dead > vacthresh or ins_since_vacuum > vacinsthresh or relfrozenxid older than autovacuum_freeze_max_age (200M)
analyze if mod_since_analyze > anlthresh
```

Per-table reloptions override each. **Scheduling:** `autovacuum_naptime` 1min (the launcher
spreads databases over it: one worker start per `naptime / ndatabases`, floor 100 ms),
`autovacuum_max_workers` 3 (`autovacuum_worker_slots` 16 in PG18). Three workers are a hard cap:
tables queue behind large ones.

**Cost throttle: the actuator's rate limit** (`PG src/backend/commands/vacuum.c`,
`vacuum_delay_point()`): each page access adds `vacuum_cost_page_hit` 1 / `_miss` 2 / `_dirty` 20;
when the balance ≥ `vacuum_cost_limit` (200; `autovacuum_vacuum_cost_limit` −1 = use it), sleep
`autovacuum_vacuum_cost_delay` (2ms) × balance / limit (capped at 4× delay). Ceiling ≈ 100,000
credits/s: ~100k hit pages/s, ~5k dirtied pages/s (~39 MB/s at 8 KB pages). **Balancing:** PG16+
divides the limit across running workers (`cost_limit = base / nworkers_for_balance`): adding workers
adds no I/O; PG ≤15 `autov_balance_cost()` equalised limit/delay ratios
(https://github.com/postgres/postgres/blob/REL_15_STABLE/src/backend/postmaster/autovacuum.c).

**Freeze ladder:** `vacuum_freeze_min_age` 50M, `vacuum_freeze_table_age` 150M (aggressive scans),
`autovacuum_freeze_max_age` 200M (forced), `vacuum_failsafe_age` 1.6B (throttle off, index
vacuuming skipped); in `varsup.c SetTransactionIdLimit()`: warnings at wrap − 40M, new XIDs refused
at wrap − 3M (wrap ≈ 2^31). A **cascade of thresholds on one stock**, each with a different
actuator.

**Blocker:** dead tuples newer than the xmin horizon cannot be removed: min of
`pg_stat_activity.backend_xmin`/`backend_xid`, `pg_replication_slots.xmin`/`catalog_xmin`,
`pg_prepared_xacts`, standby queries through `hot_standby_feedback` (off). Signature:
`autovacuum_count` rising while `n_dead_tup` stays flat or rises. Bounded only by timeouts that
default to 0: `idle_in_transaction_session_timeout`, `transaction_timeout` (PG17+),
`idle_replication_slot_timeout` (PG18).

### 6.2 Checkpoints, WAL and the background writer

Settings: `checkpoint_timeout` 5min, `max_wal_size` 1GB, `min_wal_size` 80MB,
`checkpoint_completion_target` 0.9, `checkpoint_warning` 30s, `full_page_writes` on,
`wal_compression` off (https://www.postgresql.org/docs/18/wal-configuration.html).

**Two triggers** (`PG src/backend/access/transam/xlog.c`): by time (`checkpoint_timeout`) or by
WAL volume, `CheckPointSegments = floor(max_wal_size_segments / (1 + checkpoint_completion_target))`
(1 GB ⇒ 33 segments ≈ 528 MB).

**Pacing law** (`PG src/backend/postmaster/checkpointer.c`, `IsCheckpointOnSchedule()`): a
bang-bang tracker of a ramp.

```
progress = fraction of dirty buffers written × checkpoint_completion_target
on_schedule = progress >= max(elapsed WAL / CheckPointSegments, elapsed time / checkpoint_timeout)
on schedule: sleep 100 ms between writes; behind: write without sleeping
```

**WAL kept** (`UpdateCheckPointDistanceEstimate()`): `est = nbytes` if larger, else
`0.9 est + 0.1 nbytes` (fast up, slow down); segments recycled up to `(1 + target) × est`, within
[min_wal_size, max_wal_size]. Also retained by `wal_keep_size` (0), slots
(`max_slot_wal_keep_size` −1 = unlimited) and a failing `archive_command`.

**Background writer** (`PG src/backend/storage/buffer/bufmgr.c`, `BgBufferSync()`), every
`bgwriter_delay` 200ms: a feed-forward estimator of buffer demand.

```
smoothed_alloc = recent_alloc if higher, else += (recent − smoothed)/16     # fast up, slow down
upcoming       = max(smoothed_alloc × bgwriter_lru_multiplier (2.0), NBuffers/(120 s / delay) + reusable)
write dirty LRU buffers until reusable >= upcoming or bgwriter_lru_maxpages (100) written (⇒ maxwritten_clean++)
```

Ceiling 100 pages / 200 ms ≈ 4 MB/s; beyond it client backends write (in `pg_stat_io`).

**Full-page-write loop.** The first change to a page after a checkpoint logs the whole page
(`pg_stat_wal.wal_fpi`): WAL spikes after each checkpoint. With `max_wal_size` small for the WAL
rate, more WAL ⇒ more checkpoints by size (`num_requested ≫ num_timed`) ⇒ more full-page images ⇒
more WAL: **R**.

### 6.3 Connections and PgBouncer

Postgres: `max_connections` 100, `superuser_reserved_connections` 3, `reserved_connections` 0;
`pg_stat_activity` by `state`, `wait_event_type`. PgBouncer (https://www.pgbouncer.org/config.html)
is a **queue with a server pool**: arrivals = client queries; waiting room `cl_waiting` (bounded by
`max_client_conn` 100); servers `sv_active + sv_idle + sv_used + sv_tested + sv_login` ≤
`default_pool_size` 20 per (user, db) + `reserve_pool_size` 0 (unlocked after a client waits
`reserve_pool_timeout` 5 s); service time `avg_xact_time` (transaction mode) or session length
(`pool_mode` session, the default); reneging after `query_wait_timeout` 120 s; server outflows
`server_idle_timeout` 600 s, `server_lifetime` 3600 s; `min_pool_size` 0. SHOW POOLS / SHOW STATS
columns (https://www.pgbouncer.org/usage.html) map to pgbouncer_exporter
(https://github.com/prometheus-community/pgbouncer_exporter/blob/master/collector.go):
`pgbouncer_pools_client_waiting_connections`, `_client_active_connections`,
`_server_active_connections`, `_server_idle_connections`, `_client_maxwait_seconds` (whole
seconds), `pgbouncer_stats_queries_pooled_total`, `_queries_duration_seconds_total`,
`_client_wait_seconds_total`, `_sql_transactions_pooled_total`, `pgbouncer_databases_pool_size`,
`_reserve_pool`, `_current_connections`.

### 6.4 Replication lag

A **pipeline of stocks** (bytes): WAL inserted → sent → written → flushed → replayed:
`pg_stat_replication.{sent_lsn, write_lsn, flush_lsn, replay_lsn}` and `write_lag`, `flush_lag`,
`replay_lag` (NULL when idle and caught up); each gap `pg_wal_lsn_diff(pg_current_wal_lsn(),
replay_lsn)`. `synchronous_commit` (on) chooses which gap sits on the commit path. Feedback every
`wal_receiver_status_interval` 10s; `wal_sender_timeout` 60s. **Conflict controller:** replay
waits up to `max_standby_streaming_delay` 30s for a conflicting standby query, then cancels it
(`pg_stat_database_conflicts.confl_*`): a trade between lag and cancellations; −1 makes the lag
unbounded; `hot_standby_feedback = on` moves the cost to bloat on the primary (the standby's xmin
joins the horizon of 6.1: two loops coupled through one stock). Slots: `pg_replication_slots.wal_status`,
`safe_wal_size`, `restart_lsn`, `inactive_since` (an inactive slot is a WAL stock with no outflow).

### 6.5 Metric names

Views (PG17 split): `pg_stat_checkpointer` (`num_timed`, `num_requested`, `num_done` PG18,
`write_time`, `sync_time`, `buffers_written`), `pg_stat_bgwriter` (`buffers_clean`,
`maxwritten_clean`, `buffers_alloc`), `pg_stat_wal` (`wal_records`, `wal_fpi`, `wal_bytes`,
`wal_buffers_full`), `pg_stat_io`, `pg_stat_database` (`numbackends`, `xact_commit`, `deadlocks`,
`temp_bytes`, `conflicts`), `pg_stat_progress_vacuum` (`phase`, `heap_blks_*`, `delay_time` PG18).

postgres_exporter (https://github.com/prometheus-community/postgres_exporter/tree/master/collector):
`pg_up`; `pg_stat_user_tables_n_dead_tup`, `_n_live_tup`, `_n_mod_since_analyze`,
`_n_tup_{ins,upd,del,hot_upd}`, `_last_autovacuum`, `_autovacuum_count`, `_table_size_bytes` (no
`n_ins_since_vacuum`); `pg_stat_bgwriter_checkpoints_timed_total`, `_checkpoints_req_total`,
`_buffers_backend_total` (pre-17); `pg_stat_checkpointer_num_timed_total`,
`_num_requested_total`, `_write_time_total`, `_sync_time_total`, `_buffers_written_total`;
`pg_replication_lag_seconds` (= now − last replayed commit: **overstates lag on an idle primary**),
`pg_stat_replication_pg_wal_lsn_diff` (bytes, the honest stock), `pg_replication_slots_pg_wal_lsn_diff`,
`_safe_wal_size_bytes`; `pg_stat_activity_count{state,wait_event_type}`,
`pg_stat_activity_max_tx_duration`, `pg_long_running_transactions_oldest_timestamp_seconds`
(the horizon's holder); `pg_database_wraparound_age_datfrozenxid`; `pg_database_size_bytes`;
`pg_wal_size_bytes`; `pg_settings_<name>` (the parameters, so the declared law can be checked
against the live configuration). Read-only with the `pg_monitor` role
(https://www.postgresql.org/docs/18/predefined-roles.html). Which collectors are on by default:
[unverified].

## 7. MySQL / InnoDB (8.4; 8.0 differences noted)

Source `mysql-server` branch 8.4 (https://github.com/mysql/mysql-server/tree/8.4).

### 7.1 Buffer pool

`innodb_buffer_pool_size` 128MB; midpoint LRU `innodb_old_blocks_pct` 37, `innodb_old_blocks_time`
1000 ms; dirty pages `innodb_max_dirty_pages_pct` 90, `_lwm` 10; `innodb_lru_scan_depth` 1024;
`innodb_page_cleaners` = buffer pool instances. **Changed in 8.4**
(https://dev.mysql.com/doc/refman/8.4/en/mysql-nutshell.html): `innodb_io_capacity` 200 → 10000,
`innodb_io_capacity_max` 2× io_capacity, `innodb_purge_threads` 4 → 1 if ≤16 CPUs,
`innodb_log_buffer_size` 16 → 64MB, `innodb_change_buffering` none, `innodb_adaptive_hash_index`
OFF. Stalls: `Innodb_buffer_pool_wait_free`.

### 7.2 Adaptive flushing (page cleaner, about once a second)

Redo capacity `innodb_redo_log_capacity` 100MB (8.0.30+). Thresholds on **checkpoint age**
(current LSN − checkpoint LSN), `log0files_capacity.cc`
(https://github.com/mysql/mysql-server/blob/8.4/storage/innobase/log/log0files_capacity.cc):
soft ≈ 0.95 × usable; adaptive-flush min age ("async") = 7/8 soft; max age ("sync") = 15/16 soft;
aggressive checkpoint = 31/32 soft; beyond `log_free_check_capacity` user threads block.

Law (`buf0flu.cc`, namespace `Adaptive_flush`,
https://github.com/mysql/mysql-server/blob/8.4/storage/innobase/buf/buf0flu.cc):

```
averages, every innodb_flushing_avg_loops (30) s: page_avg_rate, lsn_avg_rate = (new + old)/2
pct_for_dirty = d × 100 / (max_dirty_pages_pct + 1) if d >= lwm else 0        # d = dirty %
pct_for_lsn   = 0 if age < innodb_adaptive_flushing_lwm (10%) of capacity
              else (io_capacity_max / io_capacity) × f^1.5 / 7.5,  f = age × 100 / async limit   # superlinear
target_lsn    = oldest_modification + 3 × lsn_avg_rate
n_pages       = min( (io_capacity × max(pct_dirty, pct_lsn)/100 + page_avg_rate + pages_for_lsn) / 3 , io_capacity_max )
sync flush (age > 15/16 soft): n_pages = max(pages_for_lsn, io_capacity), uncapped
```

This is a nonlinear proportional controller on checkpoint age, averaged with feed-forward terms
(the recent page rate and the LSN rate). Readable without writes: status
`Innodb_redo_log_current_lsn`, `_checkpoint_lsn` (age = difference), `Innodb_log_waits`,
`Innodb_buffer_pool_pages_dirty`, `_pages_flushed`. The INNODB_METRICS counters
`buffer_flush_pct_for_lsn`, `log_lsn_checkpoint_age` are off by default and enabling them is a write.

### 7.3 Purge

Stock: **history list length** (`trx_rseg_history_len`, INNODB_METRICS, on by default; "History
list length" in `SHOW ENGINE INNODB STATUS`; there is no `Innodb_history_list_length` status
variable in MySQL). Inflow: undo from committed UPDATE/DELETE; outflow: purge threads
(`innodb_purge_threads`, `innodb_purge_batch_size` 300). **Back-pressure on the inflow**
(`trx0purge.cc trx_purge_dml_delay()`,
https://github.com/mysql/mysql-server/blob/8.4/storage/innobase/trx/trx0purge.cc):

```
if innodb_max_purge_lag > 0 and hist_len > purge_threads × batch_size:
    ratio = hist_len / innodb_max_purge_lag
    delay_us = (ratio − 0.9995) × 10000 if ratio > 1 else 0, capped at innodb_max_purge_lag_delay
```

Off by default twice (both 0). Blocker: the oldest read view (long or REPEATABLE READ
transactions: `information_schema.innodb_trx.trx_started`) pins the history list.

### 7.4 Replication lag

`Seconds_Behind_Source` (https://dev.mysql.com/doc/refman/8.4/en/show-replica-status.html) is
replica now − source timestamp of the event being applied; 0 when the applier idles even if the
receiver is behind, NULL when stopped, a low-water mark with parallel workers: **a poor sensor**.
Stocks: relay log (`Relay_Log_Space`), `Retrieved_Gtid_Set` − `Executed_Gtid_Set`. Apply:
`replica_parallel_workers` 4, `replica_preserve_commit_order` ON (8.0.27+). Better sensor:
`performance_schema.replication_applier_status_by_worker` timestamps (end apply − original commit),
or a heartbeat table. **Semi-sync mode switch:** after `rpl_semi_sync_source_timeout` 10000 ms
without ACKs, the source falls back to async (`Rpl_semi_sync_source_status`): bounded commit latency
traded for durability.

### 7.5 mysqld_exporter names

(https://github.com/prometheus/mysqld_exporter/tree/main/collector) `mysql_global_status_threads_connected`,
`_threads_running`, `mysql_global_status_buffer_pool_pages{state}`,
`mysql_global_status_buffer_pool_dirty_pages`,
`mysql_global_status_buffer_pool_page_changes_total{operation="flushed"}`,
`mysql_global_status_innodb_redo_log_current_lsn`, `_innodb_redo_log_checkpoint_lsn`,
`_innodb_log_waits`, `mysql_global_variables_max_connections`, `mysql_global_variables_innodb_io_capacity`;
replication `mysql_slave_status_seconds_behind_source` (the prefix stays `slave_status` on 8.4);
opt-in `collect.info_schema.innodb_metrics`:
`mysql_info_schema_innodb_metrics_transaction_trx_rseg_history_len`.

## 8. Database pathologies, as dynamics

| Pathology | Loop | Signature | Source |
|---|---|---|---|
| autovacuum falls behind | **R**: bigger table ⇒ larger threshold and longer pass under a fixed cost budget ⇒ more dead tuples ⇒ more bloat ⇒ longer pass | `n_dead_tup` saw-tooth whose peaks grow; `autovacuum_vacuum_max_threshold` exists for this | https://www.postgresql.org/docs/18/runtime-config-autovacuum.html |
| vacuum cannot remove | outflow gated by the xmin horizon | vacuum count up, dead tuples flat; long transaction or slot | §6.1 |
| wraparound | threshold cascade; at failsafe the throttle lifts; at stop limit writes stop | `pg_database_wraparound_age_datfrozenxid` climbing to 200M+ | https://www.postgresql.org/docs/18/routine-vacuuming.html |
| checkpoint spikes / FPW storm | **R** of 6.2 | `num_requested ≫ num_timed`, `wal_fpi` saw-tooth, `sync_time` bursts | wal-configuration |
| bgwriter saturation | 4 MB/s ceiling < eviction demand ⇒ backends write | `maxwritten_clean` rising | bufmgr.c |
| connection storm | **R**: slow queries hold connections ⇒ queue ⇒ client retries and more connections ⇒ contention ⇒ slower | `cl_waiting`, `maxwait`, `wait_event` lock waits | §6.3 |
| pooler saturation | `sv_active == pool_size`, `cl_waiting > 0`: Little's law L = λ × `avg_xact_time` exceeds the pool | | PgBouncer docs |
| replica lag growth | lag stock grows while apply < generation (PG replay is single-threaded) | `pg_stat_replication_pg_wal_lsn_diff` ramp | §6.4 |
| standby lag via conflicts | replay waits 30 s per conflict | `confl_*` counters, lag steps | §6.4 |
| InnoDB sync flush | redo rate > flush capacity ⇒ age past 7/8 then 15/16 ⇒ throughput collapse, saw-tooth | checkpoint age near capacity, `Innodb_log_waits` | §7.2 |
| purge lag | long read view pins the history list ⇒ longer undo chains ⇒ slower reads | `trx_rseg_history_len` rising | §7.3 |

## 9. Database published models

- Parekh, Rose, Diao, Chang, Hellerstein, Lightstone, Huras, "Throttling Utilities in the IBM DB2
  Universal Database Server", ACC 2004, https://skoge.folk.ntnu.no/prost/proceedings/acc04/Papers/0354_ThA01.3.pdf:
  utilities (backup, reorg: the analogue of vacuum) throttled by a feedback controller on the
  estimated impact against `UTIL_IMPACT_LIM`; actuator "sleep fraction". **The closest published
  analogue to a controlled autovacuum.** Also Parekh et al., "Managing the Performance Impact of
  Administrative Utilities", DSOM 2003, https://link.springer.com/chapter/10.1007/978-3-540-39671-0_12.
- Storm, Garcia-Arellano, Lightstone, Diao, Surendra, "Adaptive Self-Tuning Memory in DB2", VLDB
  2006, https://www.vldb.org/conf/2006/p1081-storm.pdf: moving memory between heaps by marginal
  benefit with a control-theoretic step and oscillation damping.
- Van Aken, Pavlo, Gordon, Zhang, "Automatic Database Management System Tuning Through Large-scale
  Machine Learning" (OtterTune), SIGMOD 2017.
- No academic SD, queueing or control model of autovacuum or of InnoDB adaptive flushing was found;
  Azure's rule-based adaptive autovacuum
  (https://learn.microsoft.com/en-sg/azure/postgresql/monitor/concepts-adaptive-autovacuum) is the
  nearest product. These would be original contributions.
## 10. Cross-cutting control loops

Tags: **[V]** checked in the primary source this session; **[M]** standard result or memory, check
before encoding. Corrections found: gRPC A6 jitter is ±20% around the delay (not `U(0, d)`); G1's
default `GCTimeRatio` is 24 on current JDK master (not 12); current Go smooths cons/mark with a max
over recent cycles rather than the design doc's PI controller; PagerDuty's acknowledgement timeout
and auto-resolve are **off** by default; the G1 flag is `G1ReservePercent`.

### 10.1 Retries with backoff, and retry storms

**Laws.** Brooker, "Exponential Backoff and Jitter" (AWS Architecture Blog, 2015,
https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/) [V findings; formulas M
since they are images]: exponential `min(cap, base·2^n)`; full jitter `U(0, min(cap, base·2^n))`;
equal jitter `t/2 + U(0, t/2)`; decorrelated `min(cap, U(base, 3·prev))`; no-jitter is "the clear
loser". gRPC A6 (https://github.com/grpc/proposal/blob/master/A6-client-retries.md) [V]:
`retryPolicy {maxAttempts (≤5), initialBackoff, maxBackoff, backoffMultiplier, retryableStatusCodes}`,
retry n waits `min(initialBackoff·multiplier^(n−1), maxBackoff)·U(0.8, 1.2)`; **retry throttling
is a stock**: `retryThrottling {maxTokens ≤ 1000, tokenRatio}`, starts full, −1 per failure,
+tokenRatio per success, retries blocked while tokens ≤ maxTokens/2; server pushback
`grpc-retry-pushback-ms`. gRPC connection backoff
(https://github.com/grpc/grpc/blob/master/doc/connection-backoff.md) [V]: 1 s initial, ×1.6, jitter
0.2, max 120 s, `MIN_CONNECT_TIMEOUT` 20 s. AWS SDK retry quota and adaptive mode: section 4.

**Amplification.** Builders' Library, "Timeouts, retries, and backoff with jitter"
(https://builder.aws.com/content/3EumjoZascWd1oZiEgL8ORlv3qE/timeouts-retries-and-backoff-with-jitter)
[V]: 5 layers × 3 attempts ⇒ 3^5 = 243× load; retry at one layer; local retry token bucket in the
SDKs since 2016; timeouts at the acceptable false-timeout percentile (p99.9). SRE book ch. 22,
"Addressing Cascading Failures" (https://sre.google/sre-book/addressing-cascading-failures/) [V]: "a
failure that grows over time as a result of positive feedback"; 4^3 = 64 attempts; a server-wide
retry budget (e.g. 60 retries per minute per process).

**Client-side adaptive throttling** (SRE book ch. 21, "Handling Overload",
https://sre.google/sre-book/handling-overload/) [V for K and windows; formula M]:
`P_reject = max(0, (requests − K·accepts) / (requests + 1))`, K = 2, over the last two minutes;
**retry budget**: ≤ 3 attempts per request and retries only while retries/requests < 10% (worst
case ~1.1× instead of ~3×). This is a controller with a stock of evidence (two counters over a
window) and a gain K.

**Metastability** (the reinforcing loop made precise). Bronson, Aghayev, Charapko, Zhu, "Metastable
Failures in Distributed Systems", HotOS'21
(https://sigops.org/s/conferences/hotos/2021/papers/hotos21-s11-bronson.pdf) [V]: states stable →
vulnerable → metastable; worked example: DB serves < 300 QPS, clients retry once after 1 s; at
280 QPS a 10 s outage tips it, retries hold load at 560 QPS, goodput 0; recovery needs load < 150
QPS; a 90% cache hit rate is 10× amplification on cache loss; "weaken the strongest" loop. Huang et
al., "Metastable Failures in the Wild", OSDI'22
(https://www.usenix.org/conference/osdi22/presentation/huang-lexiang) [V]: 22 incidents, 11
organisations; retries "by far the most common sustaining effect" (> 50%); framework of load
L_sys(t), capacity C_sys(t), triggers (load spike, capacity drop), amplification α_L (workload) and
α_C (capacity, e.g. GC): **already a stock-and-flow model** waiting to be written as one.

### 10.2 Retry budgets and circuit breakers

- Envoy `CircuitBreakers.Thresholds`
  (https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto) [V]:
  per priority `max_connections` 1024, `max_pending_requests` 1024, `max_requests` 1024,
  `max_retries` 3 (concurrency limits, not rates); `retry_budget {budget_percent 20% of active +
  pending, min_retry_concurrency 3}` overrides `max_retries`. Stats
  (https://www.envoyproxy.io/docs/envoy/latest/configuration/upstream/cluster_manager/cluster_stats):
  `upstream_rq_retry`, `upstream_rq_retry_overflow`, `upstream_rq_pending_overflow`,
  `upstream_rq_pending_active`, `circuit_breakers.<priority>.{cx,rq_pending,rq,rq_retry}_open`;
  in Prometheus `envoy_cluster_upstream_rq_retry{envoy_cluster_name}` [M mapping].
- Finagle `RetryBudget`
  (https://github.com/twitter/finagle/blob/develop/finagle-core/src/main/scala/com/twitter/finagle/service/RetryBudget.scala)
  [V]: ttl 10 s, `minRetriesPerSec` 10, `percentCanRetry` 0.2; a leaky token bucket where each
  request deposits 1000 and each retry withdraws 1000/0.2, deposits expire after ttl.
- Linkerd `retryBudget {retryRatio, minRetriesPerSecond, ttl}`
  (https://linkerd.io/2.11/reference/service-profiles/) [V fields; defaults 0.2 / 10 / 10 s M].
- Hystrix (https://github.com/Netflix/Hystrix/wiki/Configuration) [V]:
  `circuitBreaker.requestVolumeThreshold` 20, `errorThresholdPercentage` 50,
  `sleepWindowInMilliseconds` 5000, `metrics.rollingStats.timeInMilliseconds` 10000 (10 buckets),
  health snapshot every 500 ms; in maintenance since 2018.
- resilience4j (https://resilience4j.readme.io/docs/circuitbreaker) [V]: `failureRateThreshold` 50,
  `slowCallRateThreshold` 100, `slowCallDurationThreshold` 60 s, `slidingWindowType` COUNT_BASED,
  `slidingWindowSize` 100, `minimumNumberOfCalls` 100, `waitDurationInOpenState` 60 s,
  `permittedNumberOfCallsInHalfOpenState` 10; metrics (https://resilience4j.readme.io/docs/micrometer)
  `resilience4j_circuitbreaker_state{state}`, `_failure_rate`, `_slow_call_rate`,
  `_calls_seconds{kind}`, `_calls_total{kind="not_permitted"}`.

**As control:** a breaker is a three-state relay with hysteresis on a filtered error rate (window
filter + minimum-volume gate; trip at θ; re-arm after a dead time, judged on a small trial sample).
Open = the flow is zero: it cuts the retry loop, and limit-cycles when the dependency hovers near θ.
A retry budget is a token stock: inflow = ratio × request rate (+ a floor), outflow = retries,
leakage = ttl.

### 10.3 Token-bucket rate limiters

Law: `tokens ← min(b, tokens + r·Δt)`; admit cost n if `tokens ≥ n`, then subtract. **The bucket is
a stock** (inflow r capped at b, outflow the admitted rate); rejected requests are a flow out of the
system, delayed requests a second stock (a queue).

- Envoy local rate limit (https://www.envoyproxy.io/docs/envoy/latest/api-v3/type/v3/token_bucket.proto,
  https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/local_ratelimit/v3/local_rate_limit.proto)
  [V]: `token_bucket {max_tokens, tokens_per_fill (1), fill_interval}` (discrete refill),
  `filter_enabled`, `filter_enforced` (default 0%), status 429; stats
  `<prefix>.http_local_rate_limit.{enabled,ok,rate_limited,enforced}`.
- `golang.org/x/time/rate` (https://pkg.go.dev/golang.org/x/time/rate) [V]: `NewLimiter(r, b)`,
  starts full, continuous refill.
- Guava `SmoothRateLimiter`
  (https://github.com/google/guava/blob/master/guava/src/com/google/common/util/concurrent/SmoothRateLimiter.java)
  [V]: SmoothBursty `maxPermits = 1.0 s × rate`; SmoothWarmingUp (`coldFactor` 3.0): stored permits
  are expensive when cold, the reverse of a token bucket (a warm-up ramp).
- NGINX `limit_req` (https://nginx.org/en/docs/http/ngx_http_limit_req_module.html) [V]: leaky
  bucket `rate=Nr/s`, `burst` (0), `nodelay` / `delay=N`, `limit_req_status` default **503**,
  `$limit_req_status` PASSED | DELAYED | REJECTED; seen in access logs only.

### 10.4 GC pacers

**Go** (GC guide https://tip.golang.org/doc/gc-guide [V]; `runtime/mgcpacer.go`
https://github.com/golang/go/blob/master/src/runtime/mgcpacer.go [V]; design
https://github.com/golang/proposal/blob/master/design/44167-gc-pacer-redesign.md [V]):

```
goal    = heapMarked + (heapMarked + lastStackScan + globalsScan) × GOGC/100   (GOGC 100; min heap 4 MiB × GOGC/100)
          or the GOMEMLIMIT goal if lower (3% headroom)
consMark = max(current, last 4 cycles)       # "bias a noisy cons/mark measurement toward fewer assists"
runway   = consMark × (1−u)/u × (heapScan + stackScan + globalsScan),  u = 0.25 (gcBackgroundUtilization)
trigger  = clamp(goal − runway, heapMarked + 0.70·(goal − heapMarked), heapMarked + 0.95·(goal − heapMarked))
actuators: when to start (trigger), mark workers (25% CPU), mark assists (slow allocating goroutines in proportion)
limiter (mgclimit.go): leaky bucket of GC CPU vs mutator CPU, capacity 1 CPU-s per P ⇒ GC CPU ≤ ~50%: the death-spiral guard
```

The heap is a stock (allocations in, sweeping out at each cycle); the pacer is a predictive
controller on when to start marking so that marking ends at the goal. Metrics: runtime/metrics
`/gc/heap/goal:bytes`, `/gc/heap/live:bytes`, `/gc/cycles/total:gc-cycles`, `/gc/gogc:percent`,
`/gc/gomemlimit:bytes`, `/cpu/classes/gc/mark/assist:cpu-seconds`,
`/gc/limiter/last-enabled:gc-cycle`; client_golang `go_memstats_heap_alloc_bytes`,
`go_memstats_next_gc_bytes` (= the goal), `go_gc_duration_seconds`, `go_gc_gogc_percent`,
`go_gc_gomemlimit_bytes` (https://github.com/prometheus/client_golang).

**JVM** (`gc_globals.hpp` https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/gc_globals.hpp,
`g1_globals.hpp`, `g1Arguments.cpp` [V]): `GCTimeRatio` 99 (goal: GC ≤ 1/(1+N) = 1% for Parallel;
G1 sets 24 ≈ 4%), `MaxGCPauseMillis` unset for Parallel, **200 for G1**;
`AdaptiveSizeDecrementScaleFactor` 4, `YoungGenerationSizeIncrement` 20 (Parallel's adaptive size
policy: priorities pause > throughput > footprint, grow 20%, shrink 5%) [M behaviour];
`MinHeapFreeRatio` 40 / `MaxHeapFreeRatio` 70; `GCTimeLimit` 98 / `GCHeapFreeLimit` 2 (the "GC
overhead limit exceeded" OOME). G1: `InitiatingHeapOccupancyPercent` 45 (initial only),
`G1UseAdaptiveIHOP` true, `G1ReservePercent` 10, `G1ConfidencePercent` 50 (safety margin on the pause
predictor), `G1NewSizePercent` 5 / `G1MaxNewSizePercent` 60, `G1MixedGCCountTarget` 8; G1 sizes the
young generation and collection set from a decaying-average pause-cost model to meet the pause goal
(https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html).
Micrometer names: `jvm_gc_pause_seconds_{count,sum,max}`, `jvm_gc_memory_allocated_bytes_total`,
`jvm_gc_memory_promoted_bytes_total`, `jvm_gc_live_data_size_bytes`, `jvm_memory_used_bytes{area,id}`.

GC as α_C in Huang et al.: memory pressure ⇒ more GC CPU ⇒ less capacity ⇒ queues grow ⇒ more live
heap ⇒ more GC: **R**, which the Go limiter and the JVM overhead limit exist to break.

### 10.5 TCP congestion control and queues

- Reno/AIMD, RFC 5681 (https://www.rfc-editor.org/rfc/rfc5681.html) [V]: slow start
  `cwnd += min(N, SMSS)` per ACK; congestion avoidance ≤ SMSS per RTT; on loss
  `ssthresh = max(FlightSize/2, 2·SMSS)`; on RTO `cwnd = 1 SMSS`; fast retransmit after 3 dup ACKs.
- CUBIC, RFC 9438 (https://www.rfc-editor.org/rfc/rfc9438.html) [V C, β]: `W(t) = C(t−K)^3 + W_max`,
  `K = ∛(W_max(1−β)/C)`, C = 0.4, β = 0.7 (the same law botocore's adaptive mode uses on request
  rate).
- BBR, draft-ietf-ccwg-bbr (https://datatracker.ietf.org/doc/draft-ietf-ccwg-bbr/) [V]: a
  model-based controller: `max_bw` windowed max over 2 ProbeBW cycles, `min_rtt` windowed min over
  10 s, `bdp = bw·min_rtt`, pacing gains Startup 2.77, Drain 0.5, ProbeBW DOWN 0.9 / CRUISE 1.0 /
  UP 1.25, ProbeRTT ≥ 200 ms at cwnd gain 0.5.
- Fluid model (Misra, Gong, Towsley, SIGCOMM 2000) [M transcription]:
  `dW/dt = 1/R(t) − W(t)·W(t−R)/(2R(t−R))·p(t−R)`, `dq/dt = N·W/R − C` (q ≥ 0), `R = q/C + T_p`:
  **the canonical SD model of a queue under a delayed controller** — the queue is the stock, the
  window is a second stock, the delay R depends on the queue. Hollot, Misra, Towsley, Gong,
  INFOCOM 2001 (control analysis of RED; PI AQM) [M]. Low, Paganini, Doyle, "Internet congestion
  control", IEEE Control Systems Magazine 22(1):28–43, 2002, https://resolver.caltech.edu/CaltechAUTHORS:LOWieeecsm02
  [V]: stability limits at large delay × capacity. Chiu & Jain 1989, AIMD convergence to fairness
  [M] (https://www.cse.wustl.edu/~jain/papers/ftp/cong_av.pdf).
- CoDel, RFC 8289 (https://www.rfc-editor.org/rfc/rfc8289.html) [V]: `TARGET` 5 ms sojourn,
  `INTERVAL` 100 ms; drop next at `t + INTERVAL/√count`: a controller on a stock's **age**, not its
  level (the same choice as alerting on `oldest_unacked_message_age`).
- Metrics: `node_netstat_Tcp_RetransSegs` / `node_netstat_Tcp_OutSegs` [M]; per-flow cwnd only via
  `ss -ti`.

### 10.6 Load balancer outlier ejection

Envoy `OutlierDetection`
(https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/outlier_detection.proto,
https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/outlier) [V]:
`consecutive_5xx` 5, `interval` 10 s (sampling), `base_ejection_time` 30 s, `max_ejection_percent`
10, `max_ejection_time` 300 s; ejection time = base × times ejected (decremented each interval while
healthy); success-rate detection `success_rate_minimum_hosts` 5, `success_rate_request_volume` 100,
threshold mean − stdev × `success_rate_stdev_factor` (1900)/1000; `failure_percentage_threshold` 85;
`enforcing_consecutive_5xx` 100, `enforcing_success_rate` 100, `enforcing_consecutive_gateway_failure`
0, `enforcing_failure_percentage` 0. Panic: `healthy_panic_threshold` 50% — below it Envoy ignores
health and spreads over all hosts
(https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/load_balancing/panic_threshold).
Stats `outlier_detection.ejections_active`, `ejections_enforced_total`, `ejections_overflow`,
`membership_healthy`, `membership_total`, `lb_healthy_panic`. nginx `max_fails` 1 / `fail_timeout`
10 s (https://nginx.org/en/docs/http/ngx_http_upstream_module.html); AWS ALB 30 s / 5 s / 5 healthy /
2 unhealthy, fails open when all unhealthy
(https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html);
GCP 5 s / 5 s / 2 / 2 (https://docs.cloud.google.com/load-balancing/docs/health-check-concepts).

**Pathology:** per-host load = λ / healthy; ejecting raises the others' load ⇒ more errors ⇒ more
ejection: **R**. `max_ejection_percent`, panic mode and fail-open are the balancing guards: a
saturation built in on purpose.

### 10.7 Alert rules and paging escalation

Prometheus (https://prometheus.io/docs/prometheus/latest/configuration/configuration/,
https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/) [V]: `scrape_interval`
1m, `evaluation_interval` 1m (defaults in config; most deployments set 15–30 s); `for:` (pending
state: an on-delay timer); `keep_firing_for:` (v2.42.0: an off-delay, i.e. hysteresis in time);
`ALERTS{alertname, alertstate}`, `ALERTS_FOR_STATE` (restores `for` across restarts [M]); flags
`--rules.alert.for-outage-tolerance` 1h, `--rules.alert.for-grace-period` 10m,
`--rules.alert.resend-delay` 1m. Alertmanager
(https://prometheus.io/docs/alerting/latest/configuration/) [V]: `group_wait` 30s, `group_interval`
5m, `repeat_interval` 4h, `inhibit_rules`. Metrics `alertmanager_notifications_total{integration}`,
`alertmanager_alerts{state}`, `prometheus_rule_evaluation_duration_seconds`,
`prometheus_rule_group_iterations_missed_total` [M].

As a control element: sampled sensor (scrape) → window filter (`rate[5m]`) → comparator →
on-delay (`for`) → off-delay (`keep_firing_for`) → grouping delay (`group_wait`) → actuator (a
page). Worst-case detection dead time ≈ scrape + eval + window/2 + for + group_wait. Hysteresis by
separate fire/clear thresholds or `keep_firing_for`.

PagerDuty (https://docs.pagerduty.com/incident-management/schedules/escalation-policies,
https://docs.pagerduty.com/incident-management/services/configurable-service-settings) [V]:
escalation timeout default 30 min (min 1 min single target, 3 min several), up to 9 repeats
(`escalation_delay_in_minutes`, `num_loops` [M names]); acknowledgement timeout **off** by default
(re-triggers acknowledged incidents when on; `acknowledgement_timeout`); auto-resolve **off** by
default; urgency high / low (low does not escalate) / dynamic. Opsgenie: end of sale 2025, support
ends April 2027, moving to Jira Service Management [M]. Stocks: triggered → acknowledged →
resolved; flows: ack, resolve, escalation (timer: a flow from "triggered at level k" to level
k+1), ack timeout (acknowledged → triggered).

SLO burn-rate alerts (https://sre.google/workbook/alerting-on-slos/) [V]: page at 14.4× over 1h and
5m (2% of a 30-day budget), page at 6× over 6h and 30m (5%), ticket at 1× over 3d and 6h (10%);
short window = long/12; both must exceed `burn × (1 − SLO)`. The error budget is a stock (filled by
time, drained by errors); burn rate is its outflow relative to the budgeted rate.

**Reinforcing loops in people** [M, conceptual]: alert volume ⇒ slower acks and lower trust ⇒
misses ⇒ more rules and looser thresholds ⇒ more volume (alert fatigue). Published SD analogues:
Repenning & Sterman, "Nobody Ever Gets Credit for Fixing Problems that Never Happened", California
Management Review 43(4), 2001,
https://cmr.berkeley.edu/2001/08/43-4-nobody-ever-gets-credit-for-fixing-problems-that-never-happened-creating-and-sustaining-process-improvement
[V] (the capability trap: firefighting crowds out improvement, i.e. toil); Rudolph & Repenning,
"Disaster Dynamics", ASQ 47(1), 2002 [M] (interruptions as a stock with a tipping point).

### 10.8 Queueing basics the library needs [M, standard]

- Little's law L = λW (Little 1961): ties every queue stock to its flows and its age.
- M/M/1: W = S / (1 − ρ): the utilisation–latency knee (why a 0.6 target exists).
- M/M/c, Erlang C: `P_wait = [(cρ)^c / c! · 1/(1−ρ)] / [Σ_{k<c} (cρ)^k / k! + (cρ)^c / c! · 1/(1−ρ)]`,
  `W_q = P_wait / (cμ − λ)`: replicas as servers (AHPA uses exactly this).
- Universal Scalability Law (Gunther, https://arxiv.org/abs/0808.1431):
  `X(N) = λN / (1 + α(N−1) + βN(N−1))`: why adding replicas (or Postgres connections) past a point
  lowers throughput — the structural cause of the connection-storm loop.

## 11. Published models of computing systems as control systems

- Hellerstein, Diao, Parekh, Tilbury, *Feedback Control of Computing Systems*, Wiley-IEEE 2004,
  ISBN 978-0-471-26637-2
  (https://www.wiley-vch.de/en/areas-interest/engineering/feedback-control-of-computing-systems-978-0-471-26637-2)
  [V TOC]: running examples Lotus Domino (MaxUsers → RPCs in system, sensor delay, moving-average
  sensor), Apache (MaxClients and KeepAlive → CPU and memory, MIMO), queueing systems, RED, load
  balancing, caching; methods: first-principles vs black-box models, **ARX identification by least
  squares**, z-transforms, transfer functions, P/PI/PID, state space, gain scheduling,
  self-tuning regulators, fluid flow analysis. The DB2 utility throttling work is the separate ACC
  2004 paper (section 9). **This is the method ergostat's identification step should follow:**
  first-order ARX `y(k+1) = a·y(k) + b·u(k)` fitted per controller and process, gain and time
  constant read from a and b.
- Janert, *Feedback Control for Computer Systems*, O'Reilly 2013
  (https://janert.me/books/feedback-control-for-computer-systems): cache hit rate, ad delivery,
  server scaling, with simulation code.
- Filieri, Maggio et al., "Software Engineering Meets Control Theory", SEAMS 2015,
  https://doi.org/10.1109/SEAMS.2015.12 (https://research.vu.nl/en/publications/software-engineering-meets-control-theory/).
- Abdelzaher, Diao, Hellerstein, Lu, Zhu, "Introduction to Control Theory and Its Application to
  Computing Systems", in *Performance Modeling and Engineering*, Springer 2008 [M].
- Abdel-Hamid & Madnick, *Software Project Dynamics: An Integrated Approach*, Prentice Hall 1991
  [M]: sectors human resources, software production (allocation, development, QA and rework,
  testing), controlling, planning; reproduces Brooks' law; written in DYNAMO; a Vensim port is
  described in a 1995 NPS thesis (https://apps.dtic.mil/sti/pdfs/ADA305650.pdf, not read). Madachy,
  *Software Process Dynamics*, Wiley-IEEE 2008, ships executable models (Appendix C), download URL not
  found. Relevant to `examples/software-factory`, not to the SRE library.
- Sterman, *Business Dynamics*, 2000: already ergostat's SD reference (docs/MODELLING.md).
- Huang et al. 2022 and Bronson et al. 2021 (10.1): the load/capacity framework for retry storms.
## 12. Modelling tools, component libraries and XMILE

### 12.1 What each tool offers for this

| Tool | What it brings | What a library there looks like | Use for ergostat |
|---|---|---|---|
| **Stella / iThink** (isee) | SD stocks, flows, converters, conveyors (pipeline delays), queues, ovens; modules (nestable submodels); XMILE is its native format (`.stmx`, `.itmx`) (https://www.iseesystems.com/resources/help/v3/Content/08-Reference/FileFormats.htm); opens XMILE and most Vensim `.mdl` (https://www.iseesystems.com/resources/help/v3/Content/03-BuildingModels/Opening_Closing_Saving/OpeningOtherModels.htm) | modules with input/output ports; Hines' "molecules" as reusable structures (https://iseesystems.com/resources/webinars/webinar.aspx/molecules) | the reference reader for exported XMILE |
| **Vensim** (Ventana) | SD with subscripts, macros, calibration and optimisation (Powell), Monte Carlo; `.mdl` text format; Save As offers `.mdl`, `.vmf`, v1.62 text, not XMILE (https://vensim.com/documentation/23785.html); third-party readers assume XMILE is produced elsewhere (readsdr, https://github.com/jandraor/readsdr) | macros; the original "molecules" were a Vensim add-on (Hines & Eberlein 1996; https://wikis.mit.edu/confluence/download/attachments/70203398/molecules.pdf?api=v2) | `.mdl` import is via PySD if wanted |
| **AnyLogic** | multi-method: SD (stock, flow, dynamic variable, delay/delay1/delay3), discrete event (Process Modeling Library: Source, Queue, Delay, Service, Sink; https://anylogic.help/library-reference-guides/process-modeling-library/pml-blocks.html), agents, linked both ways (an SD variable sets a Source's rate; a Sink increments a stock); imports Vensim ≤7 (https://anylogic.help/anylogic/system-dynamics/vensim-import.html), no XMILE import found | custom libraries of agent types and blocks built from core primitives | the model for mixing items (ergostat's §5a) with stocks |
| **Simulink / Simscape / SimEvents** (MathWorks) | Simulink: signal-flow blocks (PID Controller with clamping or back-calculation anti-windup and output saturation, https://www.mathworks.com/help/simulink/slref/pidcontroller.html; Discrete PID, Rate Limiter, Dead Zone, Relay, Transport Delay, Zero-Order Hold, Quantizer). Simscape: physical (acausal) networks. SimEvents: discrete-event Entity Generator → Entity Queue → Entity Server → Terminator, M/D/1 examples (https://www.mathworks.com/help/simevents/ug/model-basic-queuing-systems.html) | block libraries with masked parameters (each block a dialog of named parameters with defaults) | the control view's vocabulary: every SRE controller above is a composition of Relay, Dead Zone, Rate Limiter, Saturation, Quantizer, Transport Delay, a moving-window filter and a gain |
| **Modelica** (Modelica Association; OpenModelica, Dymola, Wolfram System Modeler) | equation-based, acausal, object-oriented; Modelica Standard Library `Blocks.Continuous` (`PID`, `LimPID` with anti-windup, setpoint weighting, feed-forward, https://doc.modelica.org/Modelica%204.0.0/Resources/helpOM/Modelica.Blocks.Continuous.PID.html), `Blocks.Nonlinear` (Limiter, DeadZone, FixedDelay, SlewRateLimiter), `Blocks.Logical` (Hysteresis, Timer), `Blocks.Discrete` (Sampler, ZeroOrderHold), `Clocked` (synchronous sampled systems), `StateGraph` (state machines); a **SystemDynamics** library (Fabricius; Cellier, "World3 in Modelica", Modelica 2008, https://modelica.org/events/conference2008/sessions/session4a2.pdf; https://reference.wolfram.com/system-modeler/libraries/SystemDynamics/SystemDynamics.html); DESLib for discrete events (https://build.openmodelica.org/Documentation/DESLib.html) | **the best model for ergostat's library**: packages of classes, each with typed connectors (inputs/outputs), parameters with units, defaults and documentation strings, `extends` for variants (Buildings' `LimPID` is MSL's with reverse action), and example models per package | copy the structure: one fragment per class, parameters documented with units and defaults, an example per fragment, variants by extension |
| **MATLAB System Identification Toolbox** | `procest` process models (`P1D`: K·e^(−sTd)/(1 + sTp1); `P1DI` with an integrator), `tfest`, `arx` with `[na nb nk]`, `delayest` for dead time, `arxstruc`/`selstruc` for order, residual analysis (https://www.mathworks.com/help/ident/ug/comparison-of-various-model-identification-methods.html, https://www.mathworks.com/help/ident/ug/preliminary-step-estimating-model-orders-and-input-delays.html) | model structures, not components | the identification target per fragment: each controller or process declares the low-order form it should fit (a gain, a time constant, a delay, a dead band) so a declared law can be tested and an unknown one (ScaleOps) found |
| **PySD** (open source) | translates Vensim `.mdl` and XMILE (`.xmile`, `.xml`, `.stmx`) to Python and runs them; XMILE macros not supported (https://pysd.readthedocs.io/en/latest/structure/xmile_translation.html) | | the cheapest way to check that an exported XMILE file simulates the same as ergostat |

Hellerstein et al. (2004) and Janert (2013) are the bridge: they use exactly the identification
(ARX by least squares) and design (P, PI, gain scheduling) methods of the toolbox above on servers.

### 12.2 Is XMILE a practical interchange format?

**For export, yes.** XMILE 1.0 is an OASIS Standard (December 2015,
https://docs.oasis-open.org/xmile/xmile/v1.0/xmile-v1.0.html). Its required core (§3.1–3.5) is
stocks (with `inflow`/`outflow` lists and `non_negative`), flows, auxiliaries, graphical functions
(lookups), sim specs (Euler default, RK4), units, and builtins that cover the processes here:
`DELAY`, `DELAY1`, `DELAY3`, `DELAYN` (pod start-up, lifecycle transitions), `SMTH1`, `SMTH3`
(perceived values, EWMAs), `TREND`, `FORCST`, `PULSE`, `STEP`, `RAMP`, `MIN`, `MAX`, `INT`,
`IF THEN ELSE`, `PREVIOUS`, `INIT`. Optional (§3.7): arrays, conveyors and queues (lifecycle rules,
pipelines), submodels/modules (one per fragment), macros. A model "without diagrams" must still
simulate (§2.2.1), so ergostat need not export layout. Stella reads it natively; PySD and readsdr read
it; the SDXorg test-models repository gives canonical outputs to test against
(https://github.com/SDXorg/test-models).

**What does not survive a round trip:** goals and setpoints, sensors and their bindings to
PromQL or cloud metrics, block roles (controller, actuator), external/observed status, items, and the
record. XMILE has no `ceil`; `INT` truncates, so `ceil(x)` must be written `-INT(-x)`. Windowed max
or percentile (HPA stabilisation, VPA histograms) has no builtin and becomes a macro or an
approximation. **Recommendation:** ergostat YAML stays the source of truth; `ergostat export
--xmile` writes the SD perspective (stocks, flows, auxiliaries, block laws as auxiliary equations,
one module per system), with ergostat-only data in XMILE's vendor-extension namespace so a reader
ignores it; import of XMILE is a one-way "start from this SD model" convenience (stocks, flows,
auxiliaries, causes with their signs), never a sync. Vensim users reach XMILE through Stella or
PySD's parser.

## 13. Proposed library layout

### 13.1 Files

```
library/                                  # ships with ergostat; included with `include:` or `use:`
  README.md                               # index: one line per fragment, its law in one formula, its source
  kubernetes/
    hpa.yaml                              # controller: law, parameters, defaults, bindings
    vpa-recommender.yaml                  # estimator (histograms) + law
    vpa-updater.yaml                      # actuator (eviction / in-place) with its dead band
    cluster-autoscaler.yaml
    karpenter-consolidation.yaml
    rollout.yaml                          # process: old RS → new RS under surge/unavailable constraints
    pdb.yaml                              # constraint on the eviction flow
    kubelet-eviction.yaml
    pods.yaml                             # process: desired → pending → starting → ready (a material delay chain)
    scaleops-rightsizer.yaml              # law: identified; structure of the VPA
  gcp/
    pubsub-subscription.yaml              # process: backlog, leased, acked, expired/redelivered, dead-lettered
    pubsub-client-lease.yaml              # controller: p99 lease, flow control with hysteresis
    pubsub-push-window.yaml
    cloud-run-autoscaler.yaml
    knative-kpa.yaml
    mig-autoscaler.yaml
  aws/
    s3-prefix.yaml                        # process: request capacity (hidden stock) and 503s
    sdk-retry-standard.yaml               # retry quota (token stock) + backoff
    sdk-retry-adaptive.yaml               # CUBIC rate limiter
    s3-lifecycle.yaml                     # conveyor between storage-class stocks
  kafka/
    consumer-group.yaml                   # process: lag per partition, rebalance pause
    keda-kafka.yaml                       # controller feeding an HPA
  postgres/
    autovacuum.yaml                       # trigger law + throttled actuator + xmin horizon gate
    checkpointer.yaml
    bgwriter.yaml
    connections.yaml                      # max_connections + pgbouncer queue
    replication.yaml
  mysql/
    buffer-pool.yaml
    adaptive-flushing.yaml
    purge.yaml
    replication.yaml
  resilience/
    retry-backoff.yaml                    # client retries: amplification as a flow
    retry-budget.yaml                     # Finagle/Linkerd/Envoy/gRPC throttling as a token stock
    circuit-breaker.yaml                  # three-state relay
    token-bucket.yaml
    adaptive-throttling.yaml              # SRE book client-side throttling, K = 2
    outlier-ejection.yaml
  runtime/
    go-gc-pacer.yaml
    jvm-g1.yaml
  network/
    tcp-aimd.yaml  tcp-cubic.yaml  codel.yaml
  alerting/
    prometheus-rule.yaml                  # sensor → window → comparator → for → keep_firing_for
    alertmanager-route.yaml
    pagerduty-escalation.yaml
    slo-burn-rate.yaml                    # error budget as a stock
  queueing/
    mm1.yaml  mmc.yaml  usl.yaml          # process laws for service capacity (Little, Erlang C, USL)
  examples/                               # one runnable model per pathology (section 14), simulated
```

### 13.2 One fragment: what it holds

Each fragment is ordinary ergostat YAML plus a header that makes it a reusable class (the Modelica
pattern: parameters with units, defaults and documentation; inputs and outputs as ports; variants by
`extends`). A proposed shape, for the HPA:

```yaml
fragment: kubernetes-hpa
version: "autoscaling/v2, Kubernetes 1.37"
source:
  - https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/podautoscaler/replica_calculator.go
  - https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/podautoscaler/horizontal.go
role: controller                      # observed: type external, law declared
parameters:                           # exact upstream names; units; defaults from source
  target-utilisation: {unit: share, upstream: spec.metrics[].resource.target.averageUtilization}
  min-replicas:      {default: 1, upstream: spec.minReplicas}
  max-replicas:      {upstream: spec.maxReplicas}
  tolerance:         {default: 0.1, upstream: --horizontal-pod-autoscaler-tolerance}
  sync-period:       {default: 15s, upstream: --horizontal-pod-autoscaler-sync-period}
  stabilize-up:      {default: 0s,   upstream: behavior.scaleUp.stabilizationWindowSeconds}
  stabilize-down:    {default: 300s, upstream: behavior.scaleDown.stabilizationWindowSeconds}
  up-percent:        {default: 100, per: 15s, upstream: behavior.scaleUp.policies[Percent]}
  up-pods:           {default: 4,   per: 15s, upstream: behavior.scaleUp.policies[Pods]}
  down-percent:      {default: 100, per: 15s, upstream: behavior.scaleDown.policies[Percent]}
ports:
  in:  {utilisation: auxiliary, ready: stock}     # usage / requests; ready pods with metrics
  out: {desired: stock}                           # writes spec.replicas
law: |
  ratio   = utilisation / target-utilisation
  raw     = ready                        if 1 - tolerance <= ratio <= 1 + tolerance
            ceil(ratio * ready)          otherwise
  desired = clamp(raw,
                  window-min(raw, stabilize-up),  window-max(raw, stabilize-down))
  desired = clamp(desired, current - floor-rate(down-percent), current + max(ceil-rate(up-percent), up-pods))
  desired = clamp(desired, min-replicas, max-replicas)
every: sync-period
bind:                                  # read-only metrics per port, as PromQL templates
  utilisation: 'kube_horizontalpodautoscaler_status_target_metric{horizontalpodautoscaler="{{name}}",metric_name="cpu",metric_target_type="utilization"} / 100'
  ready:       'kube_deployment_status_replicas_ready{deployment="{{deployment}}"}'
  desired:     'kube_horizontalpodautoscaler_status_desired_replicas{horizontalpodautoscaler="{{name}}"}'
  bounds:      'kube_horizontalpodautoscaler_spec_max_replicas{horizontalpodautoscaler="{{name}}"}'
  saturated:   'kube_horizontalpodautoscaler_status_condition{horizontalpodautoscaler="{{name}}",condition="ScalingLimited",status="true"}'
identify: {form: P1D-with-deadband, expect: {deadband: tolerance, delay: "sync-period + metric age"}}
checks:                                # the pathologies this fragment can report, with their signatures
  saturation:      desired == max-replicas while utilisation > target-utilisation * (1 + tolerance)
  oscillation:     sign changes of d(desired)/dt with period < 4 * stabilize-down
  over-provision:  utilisation < target-utilisation * 0.5 for > 1h with desired > min-replicas
  interference:    a right-sizer writes requests of the same pods (see vpa-recommender, scaleops-rightsizer)
example: library/examples/hpa-queue
```

Using it in a project (the shape external-systems.md proposes):

```yaml
use:
  hpa-checkout:
    fragment: kubernetes-hpa
    with: {name: checkout, deployment: checkout, target-utilisation: 0.6, max-replicas: 40}
    in:  {utilisation: auxiliary.checkout-cpu, ready: stock.checkout-ready}
    out: {desired: stock.checkout-replicas}
```

Process fragments (pods, a Pub/Sub subscription, a table's dead tuples) carry stocks, flows and
their equations the same way, with the metric per stock and flow; e.g. `postgres-autovacuum`:

```yaml
fragment: postgres-autovacuum
version: "PostgreSQL 18"
source: [https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/postmaster/autovacuum.c,
         https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/commands/vacuum.c]
parameters:
  threshold:     {default: 50,          upstream: autovacuum_vacuum_threshold}
  scale-factor:  {default: 0.2,         upstream: autovacuum_vacuum_scale_factor}
  max-threshold: {default: 100000000,   upstream: autovacuum_vacuum_max_threshold}
  naptime:       {default: 1m,          upstream: autovacuum_naptime}
  workers:       {default: 3,           upstream: autovacuum_max_workers}
  cost-limit:    {default: 200,         upstream: vacuum_cost_limit}
  cost-delay:    {default: 2ms,         upstream: autovacuum_vacuum_cost_delay}
stocks:
  dead-tuples: {unit: tuples, bind: 'pg_stat_user_tables_n_dead_tup{relname="{{table}}"}'}
  live-tuples: {unit: tuples, bind: 'pg_stat_user_tables_n_live_tup{relname="{{table}}"}'}
flows:
  tuples-obsoleted: {to: dead-tuples, bind: 'rate(pg_stat_user_tables_n_tup_upd{relname="{{table}}"}[5m]) + rate(pg_stat_user_tables_n_tup_del{relname="{{table}}"}[5m])'}
  tuples-vacuumed:  {from: dead-tuples, driven-by: [+stock.dead-tuples, -auxiliary.xmin-age]}
auxiliaries:
  xmin-age: {unit: s, bind: 'pg_stat_activity_max_tx_duration', description: "the horizon's holder: dead tuples newer than it cannot be removed"}
blocks:
  trigger:  {law: "dead-tuples > min(threshold + scale-factor * live-tuples, max-threshold)", every: naptime, out: block.vacuum}
  vacuum:   {role: actuator, out: flow.tuples-vacuumed, max: "cost-limit / cost-delay / 20 pages per s per worker (dirty)", shared-by: workers}
checks:
  falling-behind: peaks of dead-tuples grow from one vacuum to the next
  blocked:        autovacuum_count rises while dead-tuples does not fall, and xmin-age is large
```

### 13.3 What the block vocabulary needs (beyond SPEC §9.2)

Every law above decomposes into a short list. ergostat has `onoff`, `compare`, `proportional`,
`limit` (with `rate`), `delay`, `lookup`, `select`, `expr`, `timer`, `counter`, `alarm`. Missing:

| Block | Needed by |
|---|---|
| `window` (max, min, mean, sum, percentile over a duration; optionally decaying) | HPA stabilisation, MIG scale-in peak, Knative stable/panic, Cloud Run 1-min/10-min, VPA histograms, Pub/Sub p99 lease, Prometheus `rate[5m]`, breaker windows |
| `smooth` (first-order, optionally asymmetric: fast up, slow down) | Postgres bgwriter and checkpoint distance, InnoDB averages, perceived values (SMTH1) |
| `deadband` (output unchanged inside a band) | HPA tolerance, Cloud Run ±10%, VPA updater bounds |
| `quantise` / `ceil`, `floor` in `expr` | HPA, KEDA, Knative replica counts |
| `relay` / `state` (named states, transitions on conditions and timers) | circuit breakers, Knative panic, kubelet pressure conditions, PagerDuty escalation, semi-sync fallback |
| `token-bucket` (a stock with capacity, refill rate and per-event cost) — or the pattern written as stock + flows | rate limiters, retry budgets, retry quota, gRPC throttling, Go GC CPU limiter |
| `sample` (sample-and-hold at an interval with an offset) | every controller's sync period; metric reporting delays |

`delay` should allow a distribution (DELAY3 or a pipeline) for pod start-up and lifecycle
transitions. Each is a standard block in Simulink (Relay, Dead Zone, Quantizer, Rate Limiter,
Zero-Order Hold) and in Modelica (`Logical.Hysteresis`, `Nonlinear.DeadZone`, `SlewRateLimiter`,
`Discrete.Sampler`), so the names can follow theirs.

## 14. Build order (most convincing first), and what each example demonstrates

Each example is a simulated, runnable model (like `examples/the-job`) plus, where available, a
binding to real metrics. Order is by how quickly it convinces an SRE that "this is a control system
and the model shows something the dashboards don't".

| # | Example | Fragments | Pathology it demonstrates | Why here |
|---|---|---|---|---|
| 1 | **HPA on a queue** (`~/orchestra-kube-sim` already exports the series) | pods, hpa, queueing/mmc | **saturation** (pinned at max, `ScalingLimited/TooManyReplicas`, backlog growing), **lag** (the delay chain: metric age + sync + start-up), **over-provisioning** (the 300 s window holding replicas after a spike); a proposed change (target, window) with its simulated effect | everyone knows the HPA; the law is public; the demo exists (external-systems.md) |
| 2 | **Retry storm and its cure** | retry-backoff, retry-budget, adaptive-throttling, queueing/mm1 | **metastable failure**: a 10 s outage at 280 QPS tips a 300 QPS service into 560 QPS of retries that persist after the trigger (Bronson et al.'s numbers); the same run with a 10% retry budget recovers | the most convincing "a reinforcing loop, not a bad day" story; matches the literature exactly |
| 3 | **HPA × right-sizer on CPU** | hpa, vpa-recommender, vpa-updater, scaleops-rightsizer | **interference**: requests ratchet down while replicas ratchet up (utilisation = usage / requests); shown as an R loop through `kube_pod_container_resource_requests` | only a model of both loops shows it; directly relevant to the owner's ScaleOps; tests `law: identified` |
| 4 | **HPA + cluster autoscaler** | hpa, cluster-autoscaler, pods | **cascaded lag** (CA scan + node boot in series after the HPA's delay) and **mismatched sensors** (HPA reads usage, CA reads requests: nodes held after replicas fall) | the second most common capacity question |
| 5 | **Pub/Sub subscriber on backlog** | pubsub-subscription, pubsub-client-lease, hpa or keda (gcp-pubsub), mig-autoscaler | **dead time** (metrics visible 2–4 min late), **R loop of redelivery** when processing exceeds the ack deadline (`expired_ack_deadlines_count`), **flow-control saturation** (backlog grows while CPU idles), poison messages and the dead-letter outflow | the owner's GCP; a queue whose controller people misjudge |
| 6 | **Kafka lag with KEDA** | consumer-group, keda-kafka, hpa | **scaling-induced lag** (each scale-out rebalances and pauses consumption) and the **partition cap** (saturation by structure) | same shape as 5, different disturbance |
| 7 | **Postgres autovacuum and a long transaction** | postgres/autovacuum, connections | **falling behind** (growing peaks), **blocked outflow** (xmin horizon), the wraparound threshold ladder | shows stocks most SREs have never seen as stocks; no published model: new |
| 8 | **Alert rule → escalation** | prometheus-rule, alertmanager-route, pagerduty-escalation, slo-burn-rate | **detection dead time** (scrape + eval + for + group_wait), **flapping** without `keep_firing_for`, **alert fatigue** as an R loop through acknowledgement time; burn-rate alerts as a controller on the error-budget stock | ties ergostat to on-call, where the owner's examples (the-job) already live |
| 9 | **Postgres checkpoints / InnoDB flushing** | checkpointer, bgwriter, adaptive-flushing | **FPW R loop** (`num_requested ≫ num_timed`) and the InnoDB **sync-flush saw-tooth** at 15/16 of redo capacity | deep but specialised |
| 10 | **Outlier ejection cascade** | outlier-ejection, mmc | **R loop of ejection** (load concentrates on survivors) and why `max_ejection_percent`/panic exist | short, vivid |
| 11 | **S3 hot prefix** | s3-prefix, sdk-retry-standard, sdk-retry-adaptive | **retry amplification against a hidden capacity stock**; adaptive mode's CUBIC limiter as the balancing loop (one per client: N uncoordinated controllers) | good second retry example; capacity constants must be identified |
| 12 | **Cloud Run / Knative burst** | cloud-run-autoscaler, knative-kpa | **cold-start lag**, **panic-mode overshoot** | gain scheduling, clearly drawn |
| 13 | **Go GC under memory pressure** | go-gc-pacer, queueing/mm1 | **capacity degradation α_C** (GC CPU ⇒ less capacity ⇒ longer queues ⇒ more live heap) and the 50% limiter | shows runtime controllers inside the service |

The first three cover the three things the owner wants shown — a vendor controller judged
(saturation, lag, over-provisioning), a reinforcing loop that monitoring cannot explain, and two
controllers fighting over one process — and each needs only Prometheus with kube-state-metrics and
cAdvisor, which the kube-sim demo already serves.
