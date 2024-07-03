"""
This is a bare bones version of the OZglobals.py file from the main repo.
Ideally, we should find a way to share this file between the two repos.
This is tracked by https://github.com/OneZoom/tree-build/issues/6
"""

try:
    from gluon import current
except ImportError:
    # This is not being used in web2py, but instead in an independent python app.
    # Simply define cache.ram to be a function that returns the result of calling
    # the 2nd arg. This is a complex HACK!!!
    cache = type("", (), dict(ram=lambda self, name, func, **kw: func()))()
    current = type(
        "", (), {}
    )()  # allow us to set e.g. current.OZglobals, so we don't bomb out later

# bitwise flags for existence of different language wikipedia articles
# this variable is also used in construct_wiki_info in CSV_base_table_creator.py
wikiflags = cache.ram(
    "wikiflags",
    lambda: {
        lang: bit
        for (bit, lang) in enumerate(
            [
                "en",
                "de",
                "es",
                "fr",
                "ja",
                "ru",
                "it",
                "zh",
                "pt",
                "ar",
                "pl",
                "nl",
                "fa",
                "tr",
                "sv",
                "he",
                "uk",
                "id",
                "vi",
                "ko",
            ]
        )
    },
    time_expire=None,
)

src_flags = cache.ram(
    "src_flags",
    lambda: {
        "bespoke": 1,
        "onezoom_bespoke": 2,
        "onezoom_via_eol": 3,
        "iucn": 4,
        "arkive": 5,
        "wiki": 20,
        "eol": 30,
        "short_imprecise_name": 50,
        "eol_old": 99,
    },
    time_expire=None,
)
