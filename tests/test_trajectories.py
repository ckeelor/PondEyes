# tests.test_trajectories
# =======================
#
# Unit tests for radar/trajectories.py. The properties we care about: the shapes are correct
# at known instants, and random_walk is deterministic for a fixed seed (so manual-clock tests
# that use it stay reproducible).

import math

from radar import trajectories


def test_static_is_constant():
    f = trajectories.static(x=100, y=2000)
    assert f(0.0) == [(100, 2000, 0)]
    assert f(99.0) == [(100, 2000, 0)]


def test_circle_hits_known_points():
    # r=1000, period=4s, centre (0, 2000). At t=0 -> rightmost; at t=1 (quarter) -> top.
    # Trajectories return a LIST of targets, so we unpack the single target with [0].
    f = trajectories.circle(r=1000, period=4.0, cx=0, cy=2000)
    x0, y0, _ = f(0.0)[0]
    assert (x0, y0) == (1000, 2000)
    x1, y1, _ = f(1.0)[0]
    assert abs(x1) <= 1 and y1 == 3000           # cos(pi/2)≈0 -> x≈0, sin=1 -> y=cy+r


def test_line_stays_within_bounds():
    f = trajectories.line(x0=-2000, x1=2000, y=1500, period=8.0)
    for t in [i * 0.5 for i in range(20)]:
        x, y, _ = f(t)[0]
        assert -2000 <= x <= 2000
        assert y == 1500


def test_random_walk_is_deterministic_for_seed():
    # Two independent generators with the same seed, called the same number of times, must
    # produce identical paths. This is what lets seeded sims be asserted exactly.
    a = trajectories.random_walk(seed=7)
    b = trajectories.random_walk(seed=7)
    pa = [a(t) for t in range(10)]
    pb = [b(t) for t in range(10)]
    assert pa == pb
    # A different seed should (almost surely) diverge.
    c = trajectories.random_walk(seed=8)
    pc = [c(t) for t in range(10)]
    assert pc != pa


def test_make_resolves_names_and_falls_back():
    assert trajectories.make("static")(0.0) == trajectories.static()(0.0)
    # Unknown name must not raise — it falls back to a circle.
    f = trajectories.make("does-not-exist")
    assert len(f(0.0)) == 1
