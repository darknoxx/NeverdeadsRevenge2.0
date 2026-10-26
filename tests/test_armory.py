"""The Armory's own rules: a page is written by the first blade taken up.

The same shape as :mod:`tests.test_bestiary`, and for the same reason. The book
is authored content -- names, a "what it is" line, a paragraph -- and the test
that matters is that it covers the item table exactly, sorts by the name a
player would look under, and reads its numbers off the blade in play.
"""

from __future__ import annotations

from neverdeads_revenge.game import armory
from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.persistence import MetaProgress, load_meta, save_meta
from neverdeads_revenge.world.items import ITEMS, make_item

#: The Armory collects the vanilla blades only. A curated variant with its own
#: template key is still in the game, but it is not a page of its own.
WEAPON_KEYS = {
    key
    for key, one in ITEMS.items()
    if one.slot == "weapon" and key != "depthless_dark"
}


# -- the book ---------------------------------------------------------------
def test_every_blade_in_the_game_has_exactly_one_page():
    keys = {page.key for page in armory.WEAPONS}
    assert keys == WEAPON_KEYS, "a blade without a page, or a page without one"


def test_the_pages_sort_by_the_name_without_its_article():
    """Half the blades are "the something", and a catalogue filed under T is a
    catalogue nobody can use."""
    names = [page.name.removeprefix("the ") for page in armory.WEAPONS]
    assert names == sorted(names)


def test_a_page_reads_its_numbers_off_the_blade_that_is_in_play():
    for page in armory.WEAPONS:
        stats, where = armory.stat_lines(page)
        assert stats, page.key
        template = ITEMS[page.key]
        if template.chest_only:
            assert "chest" in where, page.key
        else:
            assert f"{template.weight:g}" in where, page.key


def test_every_page_says_what_it_is_and_quotes_the_house():
    for page in armory.WEAPONS:
        assert page.what and page.lore, page.key
        assert "*" not in page.what + page.lore, f"{page.key}: markdown in the book"


def test_every_blade_is_painted():
    from neverdeads_revenge.desktop.art import exists

    for page in armory.WEAPONS:
        assert exists(page.picture), page.picture


# -- the collection ---------------------------------------------------------
def _pick_up(state, key: str, at=(1, 1)):
    item = make_item(ITEMS[key])
    state.dungeon_map.add_item(at, item)
    state.player.position = at
    perform_action(state, Action.PICK_UP)
    return item


def test_taking_a_blade_up_is_what_writes_its_page():
    state = start_run(HEROES["noxx"], seed=3)
    _pick_up(state, "tooth")

    assert state.found_weapons == ["tooth"]


def test_a_blade_walked_past_is_not_known():
    state = start_run(HEROES["noxx"], seed=3)
    state.dungeon_map.add_item((2, 2), make_item(ITEMS["tooth"]))

    assert state.found_weapons == []


def test_the_same_blade_is_written_once():
    state = start_run(HEROES["noxx"], seed=3)
    _pick_up(state, "tooth")
    # Set it down and take it up again: the page is already in the book.
    state.dungeon_map.add_item(state.player.position, make_item(ITEMS["tooth"]))
    perform_action(state, Action.PICK_UP)

    assert state.found_weapons == ["tooth"]


def test_the_book_keeps_one_page_a_blade():
    progress = MetaProgress()

    assert progress.record_weapon("tooth")
    assert not progress.record_weapon("tooth")

    progress.record_weapon("grave")
    assert progress.armory == ["grave", "tooth"]


def test_the_armory_outlives_the_run(tmp_path):
    path = tmp_path / "meta.json"
    progress = MetaProgress()
    progress.record_weapon("tooth")
    save_meta(progress, path)

    assert load_meta(path).armory == ["tooth"]


# -- the dark's cuts --------------------------------------------------------
def test_a_weapon_aspect_is_remembered_on_its_base_blade():
    state = start_run(HEROES["noxx"], seed=3)
    blade = make_item(ITEMS["hummingbird"], affixes=("frostbound",))

    state.note_weapon_aspect(blade)

    assert state.weapon_aspects == [("hummingbird", "frostbound")]


def test_the_weapon_page_names_the_variants_that_were_met():
    from types import SimpleNamespace

    from neverdeads_revenge.desktop.screens.almanac import AlmanacScreen

    progress = MetaProgress()
    progress.record_weapon_aspect("hummingbird", "frostbound")
    progress.record_weapon_aspect("hummingbird", "darkness_touched")
    app = SimpleNamespace(progress=progress)

    text = " ".join(
        line
        for line, _style in AlmanacScreen().weapon_lines(
            armory.weapon("hummingbird"), 60, app
        )
    )

    assert "ASPECTS MET" in text
    assert "the frostbound hummingbird" in text
    assert "the darkness-touched hummingbird" in text


def test_a_weapon_aspect_outlives_the_run(tmp_path):
    path = tmp_path / "meta.json"
    progress = MetaProgress()
    progress.record_weapon_aspect("hummingbird", "fire_kissed")
    save_meta(progress, path)

    assert load_meta(path).weapon_aspects == {
        "hummingbird": ["fire_kissed"]
    }


def test_weapon_aspects_travel_with_the_run():
    import json

    from neverdeads_revenge.game.savegame import dump, load

    state = start_run(HEROES["noxx"], seed=3)
    state.note_weapon_aspect(
        make_item(ITEMS["hummingbird"], affixes=("frostbound",))
    )

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.weapon_aspects == [("hummingbird", "frostbound")]
