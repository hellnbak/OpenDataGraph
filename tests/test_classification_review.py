from app.classification import heuristic_classify


def test_low_confidence_metadata_is_queued_for_review():
    result = heuristic_classify("meeting-notes.txt", "shared/general/meeting-notes.txt", "text/plain")
    assert result.review_required
    assert result.confidence < 0.70
