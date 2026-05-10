from services.contact_write_consistency import verify_contact_write_with_retry


class _FakeSheetsVerify:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    def verify_contact_subset(self, contact_id: str, expected_subset: dict[str, str]) -> bool:
        _ = contact_id
        _ = expected_subset
        if not self._outcomes:
            return False
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return bool(outcome)


def test_verify_contact_write_confirmed_first_attempt() -> None:
    sheets = _FakeSheetsVerify([True])
    result = verify_contact_write_with_retry(
        sheets=sheets,  # type: ignore[arg-type]
        contact_id="CID-1",
        expected_subset={"contact_id": "CID-1"},
        operation="update",
    )
    assert result.status == "confirmed"
    assert result.attempts == 1


def test_verify_contact_write_ambiguous_after_retries() -> None:
    sheets = _FakeSheetsVerify([False, False, False, False])
    result = verify_contact_write_with_retry(
        sheets=sheets,  # type: ignore[arg-type]
        contact_id="CID-1",
        expected_subset={"contact_id": "CID-1"},
        operation="update",
    )
    assert result.status == "ambiguous"
    assert result.attempts == 4
