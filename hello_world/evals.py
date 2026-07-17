import typing as t

import numpy as np
from pydantic import BaseModel
# from ragas.experimental.project.backends import LocalCSVProjectBackend  # TODO: Not implemented yet
from ragas.metrics.result import MetricResult
from ragas.metrics.numeric import numeric_metric

# TODO: Project class not implemented yet  
# p = Project(
#     project_id="hello_world", 
#     project_backend=LocalCSVProjectBackend("."),
# )


@numeric_metric(name="accuracy_score", allowed_values=(0, 1))
def accuracy_score(response: str, expected: str):
    """
    Is the response a good response to the query?
    """
    result = 1 if expected.lower().strip() == response.lower().strip() else 0
    return MetricResult(
        result=result,
        reason=(
            f"Response contains {expected}"
            if result
            else f"Response does not contain {expected}"
        ),
    )


def mock_app_endpoint(**kwargs) -> str:
    """Mock AI endpoint for testing purposes."""
    mock_responses = [
        "Paris","4","Blue Whale","Einstein","Python","Mount Everest","Shakespeare",
        "Mars","Apple","Leonardo da Vinci",]
    return np.random.choice(mock_responses)


class TestDataRow(BaseModel):
    id: t.Optional[int]
    query: str
    expected_output: str


class ExperimentDataRow(TestDataRow):
    response: str
    accuracy: int
    accuracy_reason: t.Optional[str] = None


# @p.experiment(ExperimentDataRow)  # TODO: Project not implemented
async def run_experiment(row: TestDataRow):
    response = mock_app_endpoint(query=row.query)
    accuracy = accuracy_score.score(response=response, expected=row.expected_output)

    experiment_view = ExperimentDataRow(
        **row.model_dump(),
        response=response,
        accuracy=accuracy.result,
        accuracy_reason=accuracy.reason,
    )
    return experiment_view
