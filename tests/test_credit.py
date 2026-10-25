"""The house's credit: three pieces, shown by name, with one paid reroll."""

from __future__ import annotations

import json

from neverdeads_revenge.desktop.screens.credit import CreditScreen
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.savegame import dump, load
from neverdeads_revenge.game.state import CREDIT_GOLD, CREDIT_REROLL, start_run


def _begin(seed: int = 3):
    return start_run(
        HEROES["noxx"],
        seed,
        tenth_door=True,
        start_depth=10,
    )


def test_the_loan_is_three_named_pieces_and_a_purse():
    state = _begin()

    assert len(state.credit_gear) == 3
    assert all(item.name for item in state.credit_gear)
    assert state.gold == CREDIT_GOLD
    assert state.credit_rerolled is False


def test_one_reroll_costs_fifty_and_takes_the_old_pieces_back():
    state = _begin()
    before = list(state.credit_gear)

    message = state.reroll_credit()

    assert message.startswith("The house rolls again")
    assert state.gold == CREDIT_GOLD - CREDIT_REROLL
    assert state.credit_rerolled is True
    assert state.credit_roll == 1
    assert len(state.credit_gear) == 3
    for old in before:
        assert old not in state.inventory
        assert all(
            state.player.equipment.get(slot) is not old
            for slot in ("weapon", "armour", "amulet")
        )


def test_the_house_only_rolls_once_and_only_with_coin():
    state = _begin()
    state.reroll_credit()

    assert state.reroll_credit() == "The house has already rolled again."

    poor = _begin()
    poor.gold = 0
    assert poor.reroll_credit() == "The house wants 50 coin."
    assert poor.credit_rerolled is False


def test_the_card_shows_the_names_and_rerolls_in_place():
    class FakeApp:
        def __init__(self):
            self.played = []
            self.popped = False
            self.redraws = 0

        def play(self, name):
            self.played.append(name)

        def pop(self):
            self.popped = True

        def redraw(self):
            self.redraws += 1

    state = _begin()
    screen = CreditScreen(state)
    text = "\n".join(screen._item_lines(60))

    assert all(item.name in text for item in state.credit_gear)

    app = FakeApp()
    screen._reroll(app)
    assert state.credit_rerolled is True
    assert state.gold == 0
    assert "coin" in app.played
    assert app.redraws == 1

    screen._begin(app)
    assert app.popped is True


def test_the_credit_and_its_reroll_survive_a_save():
    state = _begin()
    state.reroll_credit()

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.credit_rerolled is True
    assert reloaded.credit_roll == 1
    assert reloaded.gold == 0
    assert [item.name for item in reloaded.credit_gear] == [
        item.name for item in state.credit_gear
    ]
