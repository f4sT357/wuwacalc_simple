import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from wuwacalc17 import ScoreCalculator


def test_parse_numeric():
    sc = ScoreCalculator()
    assert sc._parse_numeric('10') == 10.0
    assert sc._parse_numeric('18,6%') == 18.6
    assert sc._parse_numeric('％12') == 12.0
    assert sc._parse_numeric('') is None
    assert sc._parse_numeric(None) is None


def test_calculate_single_score():
    sc = ScoreCalculator()
    res = sc.calculate_single_score({'a': '10', 'b': '5.5'}, {'a': 1, 'b': 2})
    assert abs(res - (10*1 + 5.5*2)) < 1e-6


def test_calculate_batch_scores():
    sc = ScoreCalculator()
    tabs = {
        't1': {
            'substats': {'a': 1, 'b': 2},
            'weights': {'a': 1, 'b': 1},
        },
        't2': {
            'substats': {'a': 3},
            'weights': {'a': 2},
        },
    }
    res = sc.calculate_batch_scores(tabs)
    assert res['t1'] == 3
    assert res['t2'] == 6
