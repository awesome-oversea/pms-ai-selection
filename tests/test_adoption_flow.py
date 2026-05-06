from __future__ import annotations

import pytest

from tests.test_erp_integration_service import (
    test_execute_selection_adoption_creates_real_purchase_suggestion as _execute_selection_adoption_creates_real_purchase_suggestion,
)
from tests.test_selection_service_feedback import (
    test_adopt_recommendation_persists_adoption_state as _adopt_recommendation_persists_adoption_state,
)
from tests.test_selection_service_feedback import (
    test_reject_recommendation_persists_rejection_state_and_model_feedback as _reject_recommendation_persists_rejection_state_and_model_feedback,
)


@pytest.mark.asyncio
async def test_adoption_flow_service_adopt() -> None:
    await _adopt_recommendation_persists_adoption_state()


@pytest.mark.asyncio
async def test_adoption_flow_service_reject() -> None:
    await _reject_recommendation_persists_rejection_state_and_model_feedback()


@pytest.mark.asyncio
async def test_adoption_flow_erp_submit() -> None:
    await _execute_selection_adoption_creates_real_purchase_suggestion()
