"""Word lists for display names, customer rudeness and moderation of the AI's output. Small on purpose (English, Hinglish and
Hindi); the real protection is that the AI never decides a price outright and every AI line passes through
app.voice.validate_reply. Azure's own content filter sits on top for the other Indian languages.

Everything is matched on whole words, never substrings: "Kshitij" must not trip "shit" and "Nazia" must not trip "nazi"."""
from __future__ import annotations

import re
import unicodedata

_PROFANE = (r"fuck\w*|shit(?:s|ty|head)?|bitch\w*|asshole\w*|dick(?:s|head)?|cunt\w*|slut\w*|whore\w*|porn(?:o|ography|hub|star|s)?|"
            r"rape[ds]?|raping|nazis?|nigg\w+|retard\w*|faggot\w*|madarchod|maderchod|bhenchod|behenchod|bhosdi\w*|bhosad\w*|"
            r"chutiya\w*|chutia|gandu|randi|lauda|lavda|bsdk|haramzada|harami")
_INSULT = (r"idiot\w*|stupid\w*|fool\w*|moron\w*|dumb\w*|shut up|useless|bastard\w*|crap\w*|damn\w*|pathetic|loser\w*|bewakoof|pagal|"
           r"gadha|nikamma|nalayak|ullu|kamina|kutta|kutti")
_IDENTITY = (r"hindus?|muslims?|sikhs?|christians?|jains?|buddhists?|islam\w*|allah|jesus|bhagwan|ganesh\w*|hanuman|shiva|krishna|"
             r"castes?|dalits?|brahmins?|bihari|madrasi|chinki|pakistan\w*|terror\w*|jihad\w*|religio\w+|church\w*|mosque\w*|"
             r"temples?|namaz|puja|gender|racist|sexist")
_TEASE = r"saala|saale|saali|gaand|chod"

# Devanagari (Hindi and Marathi). Marks are part of the word, so boundaries are "not next to another Devanagari character".
_DEV_PROFANE = (r"मादरचोद|भेनचोद|बहनचोद|चूतिया|चुतिया|गांडू|गाण्डू|गांड|रंडी|हरामी|हरामज़ादा|हरामजादा|भोसड़ी|भोसडी|लौड़ा|लवडा")
_DEV_INSULT = (r"कमीना|कमीने|कुत्ता|कुत्ती|कुत्ते|बेवकूफ|पागल|गधा|उल्लू|नालायक|निकम्मा|बदतमीज़|बदतमीज|घटिया|साला|साले|साली|मूर्ख|बेकार")
_DEV_IDENTITY = (r"हिंदू|हिन्दू|मुसलमान|मुस्लिम|सिख|ईसाई|जैन|बौद्ध|जाति|दलित|ब्राह्मण|मंदिर|मस्जिद|गिरजा|धर्म|भगवान|अल्लाह|ईश्वर|"
                 r"पाकिस्तान|आतंकी|जिहाद")


def _words(p: str) -> re.Pattern:
    return re.compile(r"\b(?:" + p + r")\b", re.I)


def _dev(p: str) -> re.Pattern:
    return re.compile(r"(?<![\u0900-\u097F])(?:" + p + r")(?![\u0900-\u097F])")


PROFANE = _words(_PROFANE)                                     # display names
RUDE = _words(_PROFANE + "|" + _INSULT)                        # customer messages (costs a little patience)
FORBIDDEN_OUTPUT = _words(_PROFANE + "|" + _INSULT + "|" + _IDENTITY + "|" + _TEASE)   # never shown from the AI
DEV_PROFANE = _dev(_DEV_PROFANE)
DEV_RUDE = _dev(_DEV_PROFANE + "|" + _DEV_INSULT)
DEV_FORBIDDEN = _dev(_DEV_PROFANE + "|" + _DEV_INSULT + "|" + _DEV_IDENTITY)

# What the AI may write: plain printable ASCII, a few typographic marks, and the Indian scripts (plus ZWJ/ZWNJ and the danda).
# No emoji, no control or bidirectional characters, no markup. Digits of any script are rejected separately.
SAFE_OUTPUT_CHARS = re.compile(r"^[\x20-\x7e₹—–‘’“”…·\u0900-\u0DFF\u200c\u200d]+$")

# Money spelled out in words (we never let the AI write prices, so any of these in a reply is a reason to discard it)
_NUM_EN = re.compile(r"\b(?:hundred|thousand|lakh|crore|sau|hazaar|hazar)\b", re.I)
_NUM_EN_CUR = re.compile(r"\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|"
                         r"fifty|sixty|seventy|eighty|ninety|ek|do|teen|char|paanch|das|bees|pachas)\s+"
                         r"(?:rupees?|rupaye|rs|bucks|paise|only|final|off)\b", re.I)
_NUM_EN_PAIR = re.compile(r"\b(?:one|two|three|four|five|six|seven|eight|nine)\s+(?:ten|twenty|thirty|forty|fifty|sixty|seventy|"
                          r"eighty|ninety)\b", re.I)
_NUM_INDIC = re.compile(
    r"(?<![\u0900-\u0DFF])(?:सौ|सो|शंभर|शे|हज़ार|हजार|लाख|करोड़|करोड|"
    r"(?:बीस|तीस|चालीस|पचास|साठ|सत्तर|अस्सी|नब्बे)(?![\u0900-\u0DFF]|\s*(?:साल|बरस|वर्ष|दिन|मिनट|घंटे|लोग|बच्चे|बार))|"
    r"শো|শত|হাজার|লাখ|কোটি|ਸੌ|ਹਜ਼ਾਰ|ਲੱਖ|સો|હજાર|લાખ|ଶହ|ହଜାର|"
    r"நூறு|நூற்று|ஆயிரம்|லட்சம்|இருபது|முப்பது|நாற்பது|ஐம்பது|அறுபது|எழுபது|எண்பது|தொண்ணூறு|"
    r"వంద|వెయ్యి|వేయి|లక్ష|ನೂರು|ಸಾವಿರ|ಲಕ್ಷ|നൂറ്|ആയിരം|ലക്ഷം)(?![\u0900-\u0DFF])")


def is_rude(text: str) -> bool:
    return bool(RUDE.search(text) or DEV_RUDE.search(text))


def is_profane_name(text: str) -> bool:
    return bool(PROFANE.search(text) or DEV_PROFANE.search(text))


def forbidden_in_output(text: str) -> bool:
    return bool(FORBIDDEN_OUTPUT.search(text) or DEV_FORBIDDEN.search(text))


def has_digits(text: str) -> bool:
    return any(unicodedata.category(c) == "Nd" for c in text)


def money_in_words(text: str) -> bool:
    return bool(_NUM_EN.search(text) or _NUM_EN_CUR.search(text) or _NUM_EN_PAIR.search(text) or _NUM_INDIC.search(text))
