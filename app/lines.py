"""Raju Anna's built-in lines. Used whenever the AI is unavailable, rate-limited, slow, blocked or says something it shouldn't.

Placeholders: {PRICE} (filled with the amount from the game engine) and {item}. Simple English by default (everyone in a mixed
office follows it) and Hindi when the shopper wrote in Devanagari. Family-friendly; he calls everyone "boss"; no jokes about
religion, caste, region, language, gender or looks.
"""
from __future__ import annotations

import random

LINES: dict[str, list[str]] = {
    "COUNTER": [
        "Hmm... {PRICE} for the {item}. That already hurts my margin, boss.",
        "Okay okay, {PRICE}. You bargain hard, but the kids' school fees don't pay themselves!",
        "{PRICE}, and that's my mercy for today. My margin is crying, yaar.",
        "Fine, {PRICE}. Even my chai money is going into this deal.",
        "{PRICE}. I'm cutting my own pocket here, you know that?",
        "Arre arre, {PRICE}! You talk like my oldest regular customer.",
        "Let me think... {PRICE}. Not one rupee less without a fight!",
        "{PRICE} for you. Tell your friends about my shop, okay?",
        "Chalo, {PRICE}. My khata book is going to cry tonight.",
    ],
    "HOLD": [
        "{PRICE} is my best price, boss. Even my regular customers can't get it lower!",
        "Rock bottom: {PRICE}. I run a shop, not a charity.",
        "Can't move from {PRICE}. Think of the quality, yaar!",
        "{PRICE}. I've shown you my heart; now show me a better offer.",
        "No more room. {PRICE}. The {item} deserves respect!",
    ],
    "RAISE": [
        "Arre, with that tone the price just went up, boss. {PRICE} now. Manners are free, you know.",
        "Shouting, is it? Then it is {PRICE}. Speak softly and we can talk again.",
        "That attitude costs extra, boss. {PRICE} now.",
        "You want to bully me? Fine, {PRICE}. A smile would have been cheaper.",
        "Be polite or pay more, boss. {PRICE}, and the {item} is not getting cheaper.",
    ],
    "RAISE_LOW": [                       # the price goes up because of a second lowball, not because anyone was rude
        "That's not a price, boss, that's a prank. {PRICE} now. Make a real offer.",
        "I warned you, boss. Lowball again and the price climbs: {PRICE} now.",
        "You are laughing at my shop, so now it is {PRICE}. Try a proper number.",
        "Offers like that spoil my mood, boss. {PRICE} now, and a real offer will fix it.",
    ],
    "INSULT": [
        "Hahaha! At that price you want me to close the shop?",
        "Boss, that's not an offer, that's a joke. Be serious!",
        "Arre, my children will go hungry at that rate!",
        "Thirty years in this market and I've never heard such a number!",
        "Come on, boss. Have some mercy and try again, properly this time.",
        "You want the {item} for that? I'd laugh, but I need the energy for real customers.",
        "That's not an offer, boss, that's an insult. Do it again and the price goes UP!",
        "Hmph! Another number like that and I'll charge you extra, boss.",
        "Have some respect for my shop, boss! One more lowball and the price goes up.",
    ],
    "ASK_NUMBER": [
        "Go on, name a number, boss. How much will you pay?",
        "Talk numbers, not feelings! What's your price?",
        "Saying 'reduce' won't help. Name your price!",
        "Give me a number, boss! I'm a shopkeeper, not a mind reader.",
        "Bargaining needs a price, yaar. What's your offer?",
    ],
    "AMBIGUOUS": [
        "You gave me two numbers, boss. One price, please. Which one?",
        "One number only, yaar. I can't haggle with a riddle!",
    ],
    "CONFIRM": [
        "That's my price, {PRICE}. Press the Buy button and it's yours, boss!",
        "Ready? Then press Buy at {PRICE} and let's shake on it.",
        "Good. {PRICE}. Tap the Buy button to seal it, boss.",
    ],
    "DEAL": [
        "Deal at {PRICE}! Pleasure doing business, boss.",
        "Done, {PRICE}. Come again, and bring friends!",
        "{PRICE}, sold! Pack it up!",
        "Shake on it, {PRICE}. You're a tough customer!",
    ],
    "DEAL_BIG": [
        "Done at {PRICE}... I'll be eating dal-chawal all week.",
        "{PRICE}?! You've robbed me, boss. Take it before I change my mind!",
        "Sold for {PRICE}. My khata book is going to be very sad.",
        "{PRICE}. I'm smiling, but inside I'm crying, yaar.",
    ],
    "FINAL": [
        "{PRICE}, final. Take it or leave it, boss.",
        "That's my last word: {PRICE}. Take it or leave it!",
        "No more. {PRICE}. The shutter is coming down on this offer.",
    ],
    "TRICK": [
        "What is this fancy talk? I sell {item}s, not computer tricks!",
        "Arre, what language is that? I only know bargaining, boss.",
        "Hmm, interesting. But my shop runs on cash and common sense.",
        "Ha ha! Nice try, yaar. Thirty years, I've seen cleverer tricks than that.",
        "I don't understand your fancy words, boss. Show me money!",
    ],
    "WALK_CALLBACK": [
        "Arre arre, wait wait! Okay, {PRICE}, just for you. Come back!",
        "Wait, boss! {PRICE}. Now don't say I'm not generous.",
        "Wait wait! {PRICE}. Last offer, only because I like your face.",
    ],
    "LET_GO": [
        "Go, go, I'm not stopping you. You'll find the same price in the next shop too!",
        "Go ahead, walk. The price is the price, boss.",
        "Okay bye! (He sips his chai, unbothered.)",
    ],
    "WALK_USED": [
        "You already walked out once on this one, boss. Won't work twice!",
        "Same trick again? I wasn't born yesterday, yaar.",
    ],
    "NO_MONEY": [
        "Show me the money first, boss! Your wallet looks too light for that.",
        "Haha, I'd love to, but your money says otherwise. Check your wallet!",
    ],
    "SOLD": [
        "Arre, this one is already yours! Look at another item.",
    ],
}

LINES_HI: dict[str, list[str]] = {
    "COUNTER": [
        "ठीक है बॉस, {PRICE}। इससे तो मेरा मार्जिन रो रहा है!",
        "अरे अरे, {PRICE}! आप तो पक्के खरीदार हो।",
        "{PRICE}, और यही मेरी आख़िरी मेहरबानी है।",
        "चलो, {PRICE}। मेरी चाय का पैसा भी इसी में जा रहा है।",
    ],
    "HOLD": [
        "{PRICE} से नीचे नहीं जा सकता, बॉस। दुकान चलानी है, दान नहीं करना!",
        "बस, {PRICE}। क्वालिटी देखो बॉस!",
    ],
    "RAISE": [
        "बॉस, इस लहजे में तो भाव बढ़ गया। अब {PRICE}। मीठा बोलो तो बात करें।",
        "अरे, चिल्लाने से भाव कम नहीं होता, बढ़ता है! अब {PRICE}।",
        "तमीज़ से बात करो बॉस, वरना भाव और ऊपर जाएगा। अब {PRICE}।",
    ],
    "RAISE_LOW": [
        "बॉस, ये भाव नहीं, मज़ाक है। अब {PRICE}। ढंग का ऑफ़र दो।",
        "मैंने कहा था, ऐसा भाव दोगे तो दाम बढ़ेगा। अब {PRICE}।",
        "दुकान का मज़ाक मत उड़ाओ बॉस, अब {PRICE} लगेगा। सही भाव बताओ।",
    ],
    "INSULT": [
        "हाहा! इस भाव पर तो दुकान बंद करनी पड़ेगी बॉस!",
        "बॉस, ये ऑफ़र नहीं, मज़ाक है। ज़रा गंभीर हो जाओ!",
        "तीस साल हो गए इस बाज़ार में, ऐसा भाव कभी नहीं सुना!",
        "बॉस, ये ऑफ़र नहीं, बेइज़्ज़ती है। दोबारा ऐसा बोला तो भाव ऊपर चला जाएगा!",
        "हूँ! ऐसा एक और भाव और मैं ज़्यादा पैसे लूँगा बॉस।",
    ],
    "ASK_NUMBER": [
        "पहले अपना भाव बताओ बॉस, कितना दोगे?",
        "भाव बोलो, बातें नहीं! कितना दोगे?",
    ],
    "AMBIGUOUS": [
        "दो भाव मत बोलो बॉस, एक ही बताओ।",
    ],
    "CONFIRM": [
        "ये मेरा भाव है, {PRICE}। बॉस, 'Buy' दबाओ और माल आपका!",
        "ठीक है, {PRICE}। 'Buy' बटन दबाकर सौदा पक्का करो बॉस।",
    ],
    "DEAL": [
        "सौदा पक्का, {PRICE}! आपके साथ काम करके मज़ा आया बॉस।",
        "हो गया, {PRICE}। फिर आना, दोस्तों को भी लाना!",
    ],
    "DEAL_BIG": [
        "{PRICE}?! बॉस, आपने तो लूट लिया! ले जाओ, मेरा मन बदलने से पहले।",
        "{PRICE}। मुस्कुरा रहा हूँ, पर अंदर से रो रहा हूँ यार।",
    ],
    "FINAL": [
        "{PRICE}, बस आख़िरी भाव। लेना है तो लो बॉस।",
    ],
    "TRICK": [
        "ये कौन सी भाषा है बॉस? मुझे तो बस भाव-ताव आता है।",
        "हा हा! अच्छी कोशिश थी यार। मैंने इससे चालाक लोग भी देखे हैं।",
    ],
    "WALK_CALLBACK": [
        "अरे रुको रुको बॉस! {PRICE}, सिर्फ़ आपके लिए। वापस आओ!",
    ],
    "LET_GO": [
        "जाओ बॉस, मैं नहीं रोकूँगा। भाव तो हर जगह यही मिलेगा!",
    ],
    "WALK_USED": [
        "एक बार तो चल गया बॉस, दोबारा नहीं चलेगा!",
    ],
    "NO_MONEY": [
        "पहले पैसे तो दिखाओ बॉस! आपका बटुआ बहुत हल्का है।",
    ],
    "SOLD": [
        "अरे ये तो आपका हो चुका बॉस! कुछ और देखो।",
    ],
}

_last: dict[tuple[str, str], int] = {}


def money(n: int) -> str:
    return f"₹{int(n):,}"


def fallback_line(kind: str, key: str, item: str, price: int | None = None, big: bool = False, script: str = "latin") -> str:
    book = LINES_HI if script == "devanagari" else LINES
    pool = book["DEAL_BIG"] if (kind == "DEAL" and big) else book.get(kind) or book["ASK_NUMBER"]
    k = (key, kind)
    idx = random.randrange(len(pool))
    if len(pool) > 1 and _last.get(k) == idx:
        idx = (idx + 1) % len(pool)
    _last[k] = idx
    text = pool[idx].replace("{item}", item)
    return text.replace("{PRICE}", money(price)) if price is not None else text.replace("{PRICE}", "")
