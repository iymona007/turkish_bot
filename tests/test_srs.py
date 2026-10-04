from datetime import date

from bot import srs

TODAY = date(2026, 10, 4)


def test_first_review_is_tomorrow():
    assert srs.first_review(TODAY) == date(2026, 10, 5)


def test_correct_moves_to_next_box_with_longer_interval():
    review = srs.after_answer(0, True, TODAY)
    assert (review.status, review.box, review.next_review) == ("learning", 1, "2026-10-07")


def test_wrong_resets_to_box_zero_and_tomorrow():
    review = srs.after_answer(4, False, TODAY)
    assert (review.status, review.box, review.next_review) == ("learning", 0, "2026-10-05")


def test_last_box_correct_marks_known():
    review = srs.after_answer(len(srs.INTERVALS) - 1, True, TODAY)
    assert review.status == "known"
    assert review.next_review is None


def test_full_ladder_reaches_known():
    box, status = 0, "learning"
    steps = 0
    while status != "known":
        review = srs.after_answer(box, True, TODAY)
        box, status = review.box, review.status
        steps += 1
    assert steps == len(srs.INTERVALS)
