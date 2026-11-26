"""Future -> past tense for the Methods chapter (rule based, then checked by eye)."""
import re

IRREG_PL = {"data", "criteria", "films", "slices"}
SING_S = {"analysis", "basis", "axis", "thesis", "bias", "status", "process", "series", "lens"}


def is_plural(subj):
    s = re.sub(r"\(.*?\)", "", subj.strip().lower()).strip()
    if re.search(r"\band\b", s):
        return True
    words = re.findall(r"[a-z0-9²%]+", s)
    if not words:
        return False
    w = words[-1]
    if w in IRREG_PL:
        return True
    if w in SING_S or w.endswith(("ss", "us", "is")):
        return False
    return w.endswith("s")


VERB_PAST = {"follow": "followed", "use": "used", "receive": "received", "overlap": "overlapped",
             "include": "included", "exclude": "excluded", "cover": "covered", "consist": "consisted"}
PAT = re.compile(r"\bwill (?:(also|then|not) )?(be|follow|use|receive|overlap|include|exclude|cover|consist)\b")


def subject_head(pre):
    clause = re.split(r"[.;:]\s|,\s(?=(?:and|so|while|where|but)\b)|\bwhich\b|\bthat\b|\bif\b|\bwhen\b|"
                      r"\bbefore\b|\bafter\b|\buntil\b", pre)[-1]
    if "," in clause:
        parts = [c for c in clause.split(",") if c.strip()]
        clause = parts[0] if len(parts) > 1 and re.match(r"\s*(the|all|each|every|this|these)\b",
                                                         parts[0], re.I) else parts[-1]
    return re.split(r"\b(of|in|on|at|for|from|with|between|inside|under|along|to|by)\b", clause)[0]


def convert_pairs(text):
    pairs = []
    for m in PAT.finditer(text):
        adv, verb = m.group(1), m.group(2)
        pre = text[:m.start()]
        if re.search(r"\b(which|that)\s*$", pre):
            ante = re.sub(r",?\s*(which|that)\s*$", "", pre)
            pl = is_plural(re.split(r"\b(of|in|on|at|for)\b", ante.split(",")[-1])[0] or ante.split()[-1])
        else:
            pl = is_plural(subject_head(pre))
        if verb == "be":
            be = "were" if pl else "was"
            new = f"{be} {adv}" if adv else be
        else:
            new = (f"{adv} " if adv and adv != "not" else "") + VERB_PAST[verb]
            if adv == "not":
                new = "did not " + verb
        pairs.append((m.group(0), new))
    return pairs
