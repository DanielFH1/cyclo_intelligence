# ViTacFormer policy backend

ViTacFormer is deployed as an independent Cyclo policy backend:

- backend/service namespace: `vitacformer`
- container: `vitacformer_server`
- image: `robotis/vitacformer-zenoh:1.0.0-<arch>`
- engine module: `vitacformer_engine`
- default model root: `/workspace/model/vitacformer`

Unlike the LeRobot development container, the dedicated image copies the
engine, common runtime, and SDK sources into the image. Runtime Compose mounts
only workspace data, caches, devices, and robot configuration.

The backend accepts the audited SH5 ViTacFormer artifact layout containing
`train_config.json`, `normalization_stats.pt`, and `checkpoints/best_model.pt`.
It is intentionally fail-closed for the `ffw_sh5_rev1` 54-joint contract.

Supported action horizons are the existing 100-step exports and the 200-step
`vitacformer_sh5_h200_v1` / `sh5_h200_original_tactile_r1` export. H200 uses
200 action queries and a 202-row latent position table, while future tactile
prediction remains 18 rows. Its learned tactile residuals apply to both hands;
the legacy loader's right-hand persistence fallback remains unchanged for
100-step exports. H200 also requires the original `inference_config.json` and
normalization hashes bound into its checkpoint. Do not edit artifact metadata
to bypass a contract mismatch.

The pour H100 export (`vitacformer_sh5_pour_h100_v2`, recipe
`task519_folder159_gt75_residual_unpenalized_r1`) is also supported. It stores
architecture metadata under `train_config.json`'s `model_config` and its
preprocessing contract in `inference_config.json`. The loader validates these
original files and the checkpoint's config/stats hashes, then adapts the
metadata in memory. Both hands retain their learned tactile residuals for this
export. Legacy H100 right-hand persistence and H200 behavior are preserved.
Selecting the run folder or its `checkpoints` folder loads `best_model.pt`;
an explicit `.pt` file or numeric checkpoint folder selects those weights.

For regression tests, run `pytest policy/vitacformer/tests` from `cyclo_brain`
in an environment with compatible PyTorch/torchvision. Set
`VITACFORMER_POUR_TEST_ROOT` to the complete original pour package to additionally
check strict checkpoint loading and output parity with its packaged reference
loader on CPU and CUDA (when available). These tests use synthetic observations
and do not connect to robot services.

The prediction horizon is separate from the runtime execution limit. The image
retains `POLICY_SOURCE_CHUNK_LIMIT=20`, 30 Hz source actions, and the existing
alignment/refill settings.

Temporal ensemble is enabled by `POLICY_TEMPORAL_ENSEMBLE_COEFF=0.01` in both
ViTacFormer images. The common Main runtime averages full, absolute, raw action
predictions before safety bridging, L2 alignment, execution slicing, and output
interpolation. Engine prediction and checkpoint decoding remain unchanged.
The coefficient follows the [reference inference.py](https://github.com/RoboVerseOrg/ViTacFormer/blob/main/inference.py):
newer overlapping predictions receive larger exponential weights. Actual
monotonic request-start times and the checkpoint's 30 Hz action grid replace
the reference's fixed inference interval; fractional offsets use interpolation.
Only unaveraged predictions enter history, and pause, stop, mode changes,
reconfiguration, model switch (which pauses), preflight, and safety rejection
clear history. Late results from an invalid generation cannot repopulate it.

`POLICY_TEMPORAL_ENSEMBLE_TAIL_FADE_S=0.2` fades older contributions before their
prediction horizon expires. This is a Cyclo adaptation: full-horizon asynchronous
output otherwise acquires discontinuities where the number of overlapping
plans changes. Setting it to `0` gives the reference's untapered weights.
Setting the coefficient to `none` disables ensemble; `0` means uniform averaging.
These are runtime settings, independent of the immutable export's historical
`runtime_proposal.temporal_ensembling_enabled=false` metadata. The export is not
rewritten because its hashes are verified against the checkpoint.

Raw model predictions now pass the existing raw-step and joint-limit checks
before entering real-run ensemble history. After averaging multiple plans,
the existing `REAL_SOURCE_STEP_MAX_DELTA_RAD` (0.03 rad) also limits the change
of each joint per source row, retaining the first row and 30 Hz time grid.
This bounds discontinuities caused by disagreement between expiring plans;
fixed tail fading alone cannot bound them for arbitrary predictions. The final
result still passes the usual safety checks, including publish-time tracking.
Unsafe raw model output remains a hard failure; it is not silently smoothed.
Ensemble logs report `limited_values`, and trace metadata records the unlimited
maximum step. On asynchronous chunk rejection, a separate last-rejection JSON
preserves the raw and processed chunks even if high-rate tracing hit 100 MB.

This enables reference-style ensemble, not exact replication of reference
deployment timing: 20-row execution, L2 alignment, 0.2-second boundary blend,
SH5 decoder arm ramp, and real-robot safety limits remain in use. The Main log
reports the effective ensemble settings and overlap counts; chunk traces include
`raw`, `ensembled`, `prepared`, `observed_at`, and `ensemble` metadata.

Updating host engine files requires rebuilding the
image and recreating the container; restarting an old container alone does not
install the updated loader. Loading and offline prediction do not verify robot
execution or timing.

Cycle Home waits for a request-specific completion from the SH5 bringup
returner before either Start path can activate inference. The returner checks
the measured arm and hand targets and reports failure on timeout; publishing
a home trigger alone is not completion. Stop after Home retains the pending
fresh-cycle requirement. The next successful Start recreates the ViTacFormer
policy object, sensor histories and tactile calibration, then uses a fresh
preflight instead of continuation. This cycle boundary reloads the checkpoint
and therefore takes longer than an ordinary Stop/Resume.

Build on Jetson:

```bash
docker compose -f docker/docker-compose.yml build vitacformer
```

Build and start through the repository helper:

```bash
docker/container.sh start-vitacformer --build
```
