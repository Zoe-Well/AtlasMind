"""Approved evaluation dataset registry with hidden split protection."""

from atlasmind.domain.common import ResourceNotAvailable
from atlasmind.evaluation.models import DatasetStatus, EvaluationDataset


class EvaluationDatasetRegistry:
    def __init__(self) -> None:
        self._datasets: dict[tuple[str, str], EvaluationDataset] = {}

    def register(self, dataset: EvaluationDataset) -> None:
        key = (str(dataset.id), dataset.version)
        if key in self._datasets:
            raise ValueError("evaluation dataset version already registered")
        self._datasets[key] = dataset

    def get_for_run(self, dataset_id: str, version: str) -> EvaluationDataset:
        dataset = self._datasets.get((dataset_id, version))
        if dataset is None or dataset.status is not DatasetStatus.APPROVED:
            raise ResourceNotAvailable()
        return dataset

    def describe(self, dataset_id: str, version: str, *, reveal_hidden: bool) -> dict[str, str]:
        dataset = self.get_for_run(dataset_id, version)
        result = {"id": str(dataset.id), "version": dataset.version}
        if dataset.split != "HIDDEN_REGRESSION" or reveal_hidden:
            result["split"] = dataset.split
        return result
