"""Tests for the chronicle.

A collection is only as good as its bookkeeping: a page has to be findable once,
keepable forever, and placeable in the right slot no matter which run found it.
Most of this file is that, and one test is about the text itself -- that cutting
it into pages did not lose a word of it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import NOXX
from neverdeads_revenge.game.lore import PAGE_COUNT, PAGES, TITLE, numeral, page
from neverdeads_revenge.game.savegame import dump, load
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.persistence import MetaProgress, load_meta, save_meta
from neverdeads_revenge.world.items import make_page

ROOT = Path(__file__).resolve().parent.parent


# -- the text -----------------------------------------------------------------
def test_the_pages_are_the_source_text_and_no_words_were_lost():
    """The one that matters about the cutting.

    The generator wraps each page into several string literals for the sake of
    the diff, and adjacent literals concatenate with *nothing* between them --
    so a page written as separate pieces arrives as "Lord ofDarkness". It did,
    once. This is the check that says it does not.
    """
    source = (ROOT / "docs" / "lore.txt").read_text().strip().split("\n", 1)[1]
    normalise = lambda text: re.sub(r"\s+", " ", text).strip()  # noqa: E731

    assert normalise(" ".join(PAGES)) == normalise(source)


def test_every_page_says_something():
    for number in range(1, PAGE_COUNT + 1):
        text = page(number)
        assert text and text.strip(), number
        assert text[0].isupper(), number


def test_there_is_no_page_before_the_first_or_after_the_last():
    assert page(0) is None
    assert page(PAGE_COUNT + 1) is None


def test_the_book_has_a_name():
    assert TITLE and TITLE[0].isupper()


def test_page_numbers_are_written_the_way_a_chronicle_writes_them():
    assert numeral(1) == "I"
    assert numeral(4) == "IV"
    assert numeral(9) == "IX"
    assert numeral(14) == "XIV"
    assert numeral(37) == "XXXVII"
    assert numeral(40) == "XL"


# -- finding one --------------------------------------------------------------
def test_a_page_is_picked_up_and_comes_off_the_missing_list():
    state = start_run(NOXX, seed=3, pages=(12, 15, 30))
    state.dungeon_map.add_item(state.player.position, make_page(15))

    result = perform_action(state, Action.PICK_UP)

    assert not result.consumed_turn, "a page is not a turn's work"
    assert state.found_pages == [15]
    assert 15 not in state.missing_pages
    assert sorted(state.missing_pages) == [12, 30]
    assert state.dungeon_map.item_at(state.player.position) is None


def test_a_page_is_never_scattered_twice():
    """Drawn from what is *missing*, so finding one already on the shelf cannot
    happen -- which would be a find that gives nothing."""
    state = start_run(NOXX, seed=3, pages=(7,))
    found = []
    for depth in range(1, 6):
        state.build_floor(depth)
        # A copy: picking a page up removes it from the very mapping being
        # walked, which is a RuntimeError rather than a test failure.
        for pos, item in list(state.dungeon_map.items.items()):
            if item.kind != "page":
                continue
            found.append(item.page)
            state.player.position = pos
            perform_action(state, Action.PICK_UP)

    assert found == [7], f"the same page turned up {len(found)} times"
    assert state.missing_pages == set()


def test_a_run_with_nothing_left_to_find_scatters_nothing():
    state = start_run(NOXX, seed=3, pages=())
    state.build_floor(2)
    assert not [i for i in state.dungeon_map.items.values() if i.kind == "page"]


def test_a_new_run_starts_with_every_page_still_out_there():
    """Right for a new shelf, and for every test that is not about the shelf."""
    state = start_run(NOXX, seed=3)
    assert state.missing_pages == set(range(1, PAGE_COUNT + 1))


# -- the shelf ----------------------------------------------------------------
def test_a_page_is_filed_once_and_only_once():
    progress = MetaProgress()
    assert progress.record_page(15) is True
    assert progress.record_page(15) is False, "the same page was filed twice"
    assert progress.record_page(3) is True
    assert progress.pages == [3, 15], "the shelf is not in the order of the book"


def test_the_shelf_survives_a_save():
    progress = MetaProgress()
    for number in (15, 3, 22):
        progress.record_page(number)
    path = Path(pytest.importorskip("tempfile").mkdtemp()) / "meta.json"

    save_meta(progress, path)

    assert load_meta(path).pages == [3, 15, 22]


def test_an_old_save_has_no_pages_and_still_loads():
    path = Path(pytest.importorskip("tempfile").mkdtemp()) / "meta.json"
    path.write_text('{"version": 1, "gold": 10}')
    loaded = load_meta(path)
    assert loaded.pages == []
    assert loaded.gold == 10


def test_the_run_remembers_which_pages_it_found():
    state = start_run(NOXX, seed=3, pages=(1, 2, 3))
    state.found_pages.append(2)
    state.missing_pages.discard(2)
    back = load(dump(state))
    assert back.found_pages == [2]
    assert back.missing_pages == {1, 3}


# -- the screen ---------------------------------------------------------------














