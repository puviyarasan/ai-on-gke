# How to (horizontally) scale the workload. Allowed values are:
# - null (no scaling),
# - Workload resources:
#   - "cpu" (scale on cpu utilization).
# - Workload metrics (i.e. custom metrics):
#   - "jetstream_prefill_backlog_size"
#   - "jetstream_slots_used_percentage"
# - Other possibilities coming soon...
#
# See `autoscaling.md` for more details and recommendations.
custom_metrics_enabled = true

# For jetstream_prefill_backlog_size. (experiment with this to determine optimal values).
hpa_averagevalue_target = 10

# Adjust these if you want different min/max values
hpa_min_replicas = 1
hpa_max_replicas = 2
