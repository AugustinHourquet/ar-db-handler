"""Public API of the ``metrics`` subpackage."""

from .init import init_metrics_db
from .writer import write_metric

__all__ = ["init_metrics_db", "write_metric"]
