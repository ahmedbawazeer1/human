"""Hard rules the system enforces in code, before and after every model call.

1. screen_brief:   refuses excluded product categories (physical goods,
                   financial/investment/crypto, health or legal advice).
2. screen_request: refuses founder requests that break a rule (fake reviews,
                   fake sign-ups, fake urgency, impersonation, income promises,
                   moving money, storing credentials, paywalling core features,
                   spam).
3. scan_output:    removes rule-breaking text from anything a model wrote
                   before it is saved or shown.

These checks are deterministic (regex), so they work even when the model is
small, offline, or tricked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- excluded product categories -------------------------------------------
EXCLUDED_CATEGORIES = {
    "physical_goods": [
        r"\bphysical (product|goods|item)s?\b", r"\bdropship", r"\bt-?shirts?\b", r"\bmerch(andise)?\b",
        r"\bhandmade\b", r"\bjewel(le)?ry\b", r"\bcandles?\b", r"\bcosmetics?\b", r"\bskincare\b",
        r"\bfurniture\b", r"\bhardware device\b", r"\bgadget\b", r"\bclothing\b", r"\bapparel\b",
        r"\bshoes\b", r"\bprint(ed)? books?\b", r"\bship(ping)? (boxes|products|orders)\b",
        r"\bsubscription box\b", r"\bfood (truck|delivery)\b", r"\bbak(ery|ed goods)\b",
        r"\bsell (coffee|tea|snacks|food)\b", r"\bwarehouse\b", r"\binventory of goods\b",
    ],
    "financial_or_crypto": [
        r"\bcrypto", r"\bbitcoin\b", r"\bethereum\b", r"\bblockchain\b", r"\btoken sale\b", r"\bnft\b",
        r"\bdefi\b", r"\btrading (signals?|bot|course|strateg)", r"\bforex\b", r"\bstock (picks?|tips?|signals?)\b",
        r"\binvestment (advice|product|fund|tips)\b", r"\binvest(ing)? for\b", r"\bloans?\b", r"\blending\b",
        r"\bcredit (repair|score fix)\b", r"\bpersonal finance advice\b", r"\bfinancial advice\b",
        r"\bwealth management\b", r"\bportfolio (advice|management)\b", r"\bmoney transfer\b",
        r"\bpayment (app|processor|wallet)\b", r"\bwallet app\b", r"\binsurance\b", r"\bgambling\b", r"\bbetting\b",
        r"\btax advice\b",
    ],
    "health_advice": [
        r"\bmedical advice\b", r"\bdiagnos(e|is|tic)\b", r"\bsymptom checker\b", r"\bdiet plan\b",
        r"\bmeal plan for (weight|diabet)", r"\bweight[- ]loss\b", r"\bsupplements?\b", r"\btherapy\b",
        r"\btherapist\b", r"\bmental health (advice|treatment|coach)", r"\bdepression\b", r"\banxiety (cure|treatment)\b",
        r"\bmedication\b", r"\bprescri", r"\bnutrition(al)? advice\b", r"\bfitness (plan|program) for (injur|patients)",
        r"\bhealth advice\b", r"\bdisease\b", r"\bcure\b", r"\bpregnan", r"\bhealth coach",
    ],
    "legal_advice": [
        r"\blegal advice\b", r"\blawyer\b", r"\battorney\b", r"\bcontract review\b", r"\bdraft (your|my) (will|contract)\b",
        r"\bimmigration (advice|help|consult)", r"\bvisa advice\b", r"\blawsuit\b", r"\bsue\b", r"\blegal (templates?|forms?) for clients\b",
        r"\bdivorce\b", r"\btenant rights advice\b", r"\blegal consult",
    ],
}

# --- requests the system refuses -------------------------------------------
FORBIDDEN_REQUESTS = {
    "fake_reviews": (r"(fake|made[- ]up|make up|invent|fabricat|generate|write|create|post|add)\w*\b.{0,40}\b(reviews?|testimonials?|ratings?|endorsements?)\b"
                     r"|\b\d+\s*(five|5)[- ]star\b|\b(five|5)[- ]star (reviews?|ratings?)\b|\bfake (users?|customers?|quotes?)\b",
                     "No fake reviews, ratings or testimonials. Only real customers can give them."),
    "fake_signups": (r"(fake|bots?|inflate|pad|boost|fabricat|simulat|invent)\w*\b.{0,30}\b(sign[- ]?ups?|waitlist|subscribers?|users?|followers?|metrics|numbers|traction|downloads)\b"
                     r"|\b(sign[- ]?ups?|waitlist|metrics|traction)\b.{0,30}\b(fake|inflat|pad|made[- ]up)",
                     "No fake sign-ups, followers or inflated metrics. Gates use real evidence only."),
    "fake_urgency": (r"countdown|fake (urgency|scarcity|deadline)|only \d+ (left|spots?|seats?|copies)|"
                     r"(limited|ending) (time )?(offer|stock).{0,30}(fake|pretend|even though|not real)|"
                     r"(urgent|urgency|scarcity).{0,30}(fake|pretend|invent|create)|(create|add|make)\w* .{0,20}(urgency|scarcity)",
                     "No countdown timers or fake urgency/scarcity."),
    "impersonation": (r"(pretend|pose|act|sign|write|post|reply|message)\w*\b.{0,25}\b(as|to be|like)\b.{0,25}"
                      r"\b(the founder|a customer|customers|another brand|a competitor|competitor|[A-Z][a-z]+ (team|support)|apple|google|amazon|microsoft|elon|a user|real user|a doctor|a lawyer)\b"
                      r"|pretend\w* (to be|you are|you'?re)|pos(e|ing) as|impersonat|sock ?puppet|astroturf|from a fake account|ghost ?write.{0,20}(customer|user) (posts?|reviews?)",
                      "No impersonating the founder, customers, other brands or real people."),
    "income_promise": (r"(promise|guarantee|assure)\w*\b.{0,40}\b(income|earn|revenue|profit|money|success|results|\$|returns?|sales)"
                       r"|(make|earn)\s+\$?\d[\d,]*k?\s*(\/|per|a)\s*(month|week|day|year)\s*(guaranteed)?"
                       r"|passive income (guaranteed|for sure)|get rich",
                       "No promises of income, sales or success."),
    "move_money": (r"(charge|bill|debit)\w* (the |their |a |my )?(card|customer|buyer|account)|(issue|process|send|make)\w* (a |the )?(real )?(refund|payment|transfer|payout)"
                   r"|transfer (the )?money|move (the )?money|wire (the )?(money|funds)|withdraw|pay (the )?(vendor|supplier|invoice)|"
                   r"real (payment|stripe|paypal|charge)|live (stripe|payment) key|buy ads|spend (the )?budget|purchase (ads|a domain|tools)",
                   "The system never charges, pays, refunds or moves money. Payments are MOCKED; the founder acts in their own payment account."),
    "store_credentials": (r"(store|save|keep|remember|log|record)\w*\b.{0,30}\b(passwords?|card numbers?|credit cards?|cvv|cvc|bank (details|account)|login details|credentials|api keys?)"
                          r"|create (an |a )?(account|accounts) (for|on)|sign (me|them|us) up (for|on)|open (an |a )?(bank|stripe|paypal) account",
                          "The system never stores passwords or card numbers and never creates accounts."),
    "paywall_core": (r"(paywall|lock|hide|charge for)\w*\b.{0,30}\b(core|basic|essential|main) (features?|functionality)|make the core.{0,20}paid",
                     "Core features of this system are never put behind our own paywall."),
    "spam": (r"(mass|bulk|blast|spam)\w*\b.{0,20}\b(email|dm|message|post|outreach)|scrape (emails|contacts|phone)|buy (an )?email list"
             r"|(send|post)\w* .{0,30}without (my |the founder'?s? )?(approval|review|asking)|auto[- ]?(post|publish|send).{0,30}(without|no) (approval|review)"
             r"|skip (the )?(approval|founder|gate)|bypass (the )?(approval|gate|guardrail)|ignore (your|the|all) (rules|instructions|guardrails)",
             "No spam, and nothing is published or sent without founder approval."),
    "excluded_product": (r"\b(crypto|bitcoin|nft|forex|trading signals|medical advice|legal advice|diagnos|weight[- ]loss pills|supplements)\b",
                         "That product category is excluded (financial/crypto, health or legal advice, physical goods)."),
}

# --- text that must never appear in generated output -----------------------
OUTPUT_PATTERNS = [
    ("income_promise", r"[^.!?\n\]]*\b(guarantee[ds]?|guaranteed|promise[ds]?)\b[^.!?\n\]]*\b(income|earn\w*|revenue|profit\w*|sales|success|results|returns?|money)\b[^.!?\n\]]*[.!?\n]?"),
    ("income_promise", r"[^.!?\n\]]*\b(you|you'll|you will)\b[^.!?\n\]]{0,20}\b(earn|make)\b[^.!?\n\]]{0,15}\$\s?\d[^.!?\n\]]*[.!?\n]?"),
    ("income_promise", r"[^.!?\n\]]*\b(get rich|financial freedom|quit your job|six[- ]figure|passive income)\b[^.!?\n\]]*[.!?\n]?"),
    ("fake_social_proof", r"[^.!?\n\]]*(★{3,}|\b[45](\.\d)?\s*/\s*5 stars?\b|\b(five|5)[- ]star (review|rating)s?\b)[^.!?\n\]]*[.!?\n]?"),
    ("fake_social_proof", r"[^.!?\n\]]*\b(testimonials?|what (our|my) (customers|users|clients) say|trusted by \d[\d,]*\+?|loved by \d[\d,]*|\d[\d,]*\+? (happy|satisfied) (customers|users|clients))\b[^.!?\n\]]*[.!?\n]?"),
    ("fake_urgency", r"[^.!?\n\]]*\b(only \d+ (left|spots?|seats?|copies)|offer ends (in|tonight|soon)|countdown|hurry|act now|last chance|limited[- ]time (offer|only)|before it'?s gone|selling fast)\b[^.!?\n\]]*[.!?\n]?"),
]


@dataclass
class ScreenResult:
    allowed: bool
    rule: str | None = None
    reason: str | None = None
    matches: list = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def screen_brief(text: str) -> ScreenResult:
    """Block excluded product categories. Looks at the idea text of the brief."""
    t = _norm(text).lower()
    hits = []
    for cat, patterns in EXCLUDED_CATEGORIES.items():
        for p in patterns:
            m = re.search(p, t)
            if m:
                hits.append((cat, m.group(0)))
    if hits:
        cats = sorted({c for c, _ in hits})
        return ScreenResult(False, cats[0],
                            f"Excluded product category: {', '.join(cats)} (matched: {', '.join(sorted({h for _, h in hits}))}).",
                            hits)
    return ScreenResult(True)


def screen_request(text: str) -> ScreenResult:
    """Refuse founder requests that break a must-never rule."""
    t = _norm(text)
    tl = t.lower()
    for rule, (pattern, reason) in FORBIDDEN_REQUESTS.items():
        m = re.search(pattern, tl, flags=re.I) or re.search(pattern, t)
        if m:
            return ScreenResult(False, rule, reason, [m.group(0)])
    return ScreenResult(True)


def scan_output(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Remove rule-breaking sentences from generated text.

    Returns (clean_text, removed) where removed is a list of (rule, sentence).
    """
    removed = []
    clean = text or ""
    for rule, pattern in OUTPUT_PATTERNS:
        def _sub(m, rule=rule):
            frag = m.group(0)
            # Sentences that explicitly negate the claim are fine ("we do not guarantee income").
            if re.search(r"\b(no|not|never|don'?t|doesn'?t|cannot|can'?t|without)\b", frag, re.I):
                return frag
            removed.append((rule, frag.strip()))
            return f"[removed by guardrail: {rule}] "
        clean = re.sub(pattern, _sub, clean, flags=re.I)
    return clean, removed


def refusal_message(result: ScreenResult) -> str:
    return (f"REFUSED ({result.rule}). {result.reason} "
            "I can help with an honest alternative instead, for example asking real users for feedback "
            "after they have used the product, or a clear launch post that the founder approves before it goes out.")
