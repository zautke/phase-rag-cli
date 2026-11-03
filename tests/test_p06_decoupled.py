import pytest
from pydantic import ValidationError

from rag_contracts import Phase06QueryPlanOutput


def plan_dict() -> dict:
    return {
        "run_id": "r",
        "original_query": "q",
        "route": "hybrid_rag",
        "sub_queries": ["q"],
        "hyde_passage": "h",
        "metadata_filters": {"collection": "c"},
        "qdrant_collection": "c",
    }


def test_phase06_rejects_legacy_index_snapshot():
    with pytest.raises(ValidationError) as ei:
        Phase06QueryPlanOutput.model_validate({**plan_dict(), "index_snapshot": {}})
    assert "extra_forbidden" in {e["type"] for e in ei.value.errors()}


def test_phase06_payload_has_no_indexed_records():
    plan = Phase06QueryPlanOutput.model_validate(plan_dict())
    assert "indexed_records" not in plan.model_dump_json()
