"""The Wardrobe's own rules: a page is written by the first coat put on.

The same shape as :mod:`tests.test_armory`, and for the same reason: the book is
authored content -- names, a "what it is" line, a paragraph -- and the tests that
matter are that it covers the item table exactly, sorts by the name a player
would look under, reads its numbers off the coat in play, and is written by
*wearing* the coat rather than by walking past it.
"""

from __future__ import annotations

from neverdeads_revenge.game import wardrobe
from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.persistence import MetaProgress, TEST_GOLD, load_meta, save_meta
from neverdeads_revenge.world.items import ITEMS, make_item

COAT_KEYS = {key for key, one in ITEMS.items() if one.slot == "armour"}


# -- the book ---------------------------------------------------------------
def test_every_coat_in_the_game_has_exactly_one_page():
    keys = {page.key for page in wardrobe.ARMOURS}
    assert keys == COAT_KEYS, "a coat without a page, or a page without one"


def test_the_pages_sort_by_the_name_without_its_article():
    names = [page.name.removeprefix("the ") for page in wardrobe.ARMOURS]
    assert names == sorted(names)


def test_a_page_reads_its_numbers_off_the_coat_in_play():
    for page in wardrobe.ARMOURS:
        stats, where = wardrobe.stat_lines(page)
        assert stats, page.key
        template = ITEMS[page.key]
        if template.chest_only:
            assert "chest" in where, page.key
        else:
            assert f"{template.weight:g}" in where, page.key


def test_every_page_says_what_it_is_and_quotes_the_house():
    for page in wardrobe.ARMOURS:
        assert page.what and page.lore, page.key
        assert "*" not in page.what + page.lore, f"{page.key}: markdown in the book"


def test_every_coat_is_painted():
    from neverdeads_revenge.desktop.art import exists

    for page in wardrobe.ARMOURS:
        assert page.picture == f"sprites/items/{page.key}.png"
        assert exists(page.picture), page.picture


# -- the collection ---------------------------------------------------------
def _pick_up(state, key: str, at=(1, 1)):
    item = make_item(ITEMS[key])
    state.dungeon_map.add_item(at, item)
    state.player.position = at
    perform_action(state, Action.PICK_UP)
    return item


def test_putting_a_coat_on_is_what_writes_its_page():
    state = start_run(HEROES["noxx"], seed=3)
    _pick_up(state, "hide")

    assert state.found_armours == ["hide"]
    assert state.player.equipment["armour"].item_id == "hide"


def test_a_coat_walked_past_is_not_known():
    state = start_run(HEROES["noxx"], seed=3)
    state.dungeon_map.add_item((2, 2), make_item(ITEMS["hide"]))

    assert state.found_armours == []


def test_the_same_coat_is_written_once():
    state = start_run(HEROES["noxx"], seed=3)
    _pick_up(state, "hide")
    # Take it off by putting the old one back on: the page is already written.
    _pick_up(state, "shroud")

    assert "hide" in state.found_armours
    assert state.found_armours.count("hide") == 1


def test_the_book_keeps_one_page_a_coat():
    progress = MetaProgress()

    assert progress.record_armour("hide")
    assert not progress.record_armour("hide")

    progress.record_armour("warden")
    assert progress.wardrobe == ["hide", "warden"]


def test_the_wardrobe_outlives_the_run(tmp_path):
    path = tmp_path / "meta.json"
    progress = MetaProgress()
    progress.record_armour("hide")
    save_meta(progress, path)

    assert load_meta(path).wardrobe == ["hide"]

    from neverdeads_revenge.persistence import grant_test_save

    grant_test_save(path)
    loaded = load_meta(path)
    assert loaded.gold == TEST_GOLD
    assert loaded.wardrobe == sorted(COAT_KEYS), "the test save left the wardrobe shut"


def test_an_old_save_without_a_wardrobe_still_loads(tmp_path):
    """The page is new; a save from before it exists has no wardrobe key at all."""
    import json

    path = tmp_path / "meta.json"
    progress = MetaProgress(gold=40)
    save_meta(progress, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("wardrobe")
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_meta(path)
    assert loaded.gold == 40
    assert loaded.wardrobe == []
