"""The Almanac's own rules: a page is written by the first kill, and not before.

Two halves are worth holding apart here. The *book* is authored content -- names,
lore, a rule and an answer per monster -- and the test that matters is that it
covers the dungeon exactly and stays in alphabetical order. The *collection* is
progress: one page a monster, written at the death that first taught it, and
kept across runs.
"""

from __future__ import annotations

from neverdeads_revenge.game import bestiary
from neverdeads_revenge.game.actions import _on_death
from neverdeads_revenge.game.actors import ENEMIES, HEROES, make_enemy
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.persistence import MetaProgress, load_meta, save_meta


def _kill(state, key: str, at=(1, 1)):
    enemy = make_enemy(ENEMIES[key], at)
    state.enemies.append(enemy)
    state.turn_queue.add(enemy)
    _on_death(state, enemy)
    return enemy


# -- the book ---------------------------------------------------------------
def test_every_monster_in_the_dungeon_has_exactly_one_page():
    keys = {page.key for page in bestiary.ENTRIES}
    assert keys == set(ENEMIES), "a monster without a page, or a page without one"
    assert len(bestiary.ENTRIES) == len(ENEMIES), "a monster was filed twice"


def test_the_pages_are_alphabetical_by_the_name_on_the_page():
    """An almanac is for looking something up, and nobody looks a monster up by
    the floor it first stood on."""
    names = [page.name for page in bestiary.ENTRIES]
    assert names == sorted(names)


def test_a_page_reads_its_numbers_off_the_monster_that_is_in_play():
    for page in bestiary.ENTRIES:
        if page.key == "notary":
            continue
        stats = ENEMIES[page.key].stats
        first, second, third = bestiary.stat_lines(page)
        assert f"HP {stats.max_hp}" in first, page.key
        assert f"{stats.damage[0]}-{stats.damage[1]}" in first, page.key
        assert f"armour {stats.armor}" in second, page.key
        assert f"gold {ENEMIES[page.key].gold[0]}" in third, page.key


def test_the_notarys_page_says_it_bills_the_floor():
    """Its health is a formula, so a page that printed the template's sixteen
    would be the one page in the book that lied."""
    from neverdeads_revenge.game.actors import NOTARY_BILL, NOTARY_MINIMUM

    first, _second, _third = bestiary.stat_lines(bestiary.entry("notary"))
    assert f"max({NOTARY_MINIMUM}, {NOTARY_BILL}" in first


def test_every_page_has_a_rule_and_a_way_to_answer_it():
    for page in bestiary.ENTRIES:
        assert page.rule and page.answer and page.lore, page.key
        assert "*" not in page.lore, f"{page.key}: markdown leaked into the book"


def test_the_echo_wears_the_shadow_because_it_has_no_face_of_its_own():
    echo = bestiary.entry("echo")
    assert echo.picture == "sprites/atritas.png"
    assert bestiary.entry("ghoul").picture == "sprites/ghoul.png"
    assert bestiary.entry("kindly").picture == "sprites/kindly_one.png"


# -- the collection ---------------------------------------------------------
def test_a_first_kill_is_written_and_a_second_is_not():
    state = start_run(HEROES["noxx"], seed=3)
    _kill(state, "ghoul", (1, 1))
    _kill(state, "ghoul", (2, 2))

    assert state.defeated == ["ghoul"], "the run filed the same monster twice"


def test_the_book_keeps_one_page_a_monster_and_sorts_what_it_keeps():
    progress = MetaProgress()

    assert progress.record_bestiary("hush")
    assert not progress.record_bestiary("hush"), "a known monster was written again"

    progress.record_bestiary("ghoul")
    assert progress.bestiary == ["ghoul", "hush"]


def test_the_book_outlives_the_run(tmp_path):
    path = tmp_path / "meta.json"
    progress = MetaProgress()
    progress.record_bestiary("ghoul")
    save_meta(progress, path)

    assert load_meta(path).bestiary == ["ghoul"]


def test_the_notary_page_quotes_the_formula_the_floor_uses():
    from neverdeads_revenge.game.actors import NOTARY_BILL, NOTARY_MINIMUM
    from neverdeads_revenge.game.bestiary import entry, stat_lines

    page = entry("notary")
    assert f"max({NOTARY_MINIMUM}, {NOTARY_BILL}" in page.rule
    assert f"HP max({NOTARY_MINIMUM}, {NOTARY_BILL}" in stat_lines(page)[0]
