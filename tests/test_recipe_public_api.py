from __future__ import annotations

import pyjev.recipes as recipes


def test_secondary_recipes_are_exported_from_the_recipe_package():
    expected = {
        "build_classify",
        "classify",
        "aclassify",
        "build_match",
        "match",
        "amatch",
        "build_route",
        "route",
        "aroute",
        "build_rerank",
        "rerank",
        "arerank",
        "build_screen",
        "screen",
        "ascreen",
        "ScreenPolicy",
        "RouteHandler",
        "RouteArgument",
        "RerankCandidate",
    }
    assert expected <= set(recipes.__all__)
    assert all(getattr(recipes, name) is not None for name in expected)
