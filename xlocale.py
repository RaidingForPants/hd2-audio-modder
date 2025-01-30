LANGUAGE_MAPPING = ({
    "English (US)" : 0x03f97b57,
    "English (UK)" : 0x6f4515cb,
    "Français" : 4271961631,
    "Português 1": 1861586415,
    "Português 2": 1244441033,
    "Polski": 260593578,
    "日本語": 2427891497,
    "繁體中文": 2663028010,
    "简体中文": 2189905090,
    "Nederlands": 291057413,
    "한국어": 3151476177,
    "Español (Castellano)": 830498882,
    "Español (LatinoAmérica)": 3854981686,
    "Deutsch": 3124347884,
    "Italiano": 3808107213,
    "Русский": 3317373165
})


def language_lookup(lang_string):
    try:
        return LANGUAGE_MAPPING[lang_string]
    except:
        return int(lang_string)


language = 0
