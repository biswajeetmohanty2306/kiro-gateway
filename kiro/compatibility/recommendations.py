# -*- coding: utf-8 -*-
"""Improvement recommendations per type pairing (F5B).

Sourced from ImprovementLibrary.md. Each entry provides challenge description,
action plan, and weekly exercise for a specific dimension + type pairing.
"""

from __future__ import annotations

# Key: (dimension, frozenset({type_a, type_b}))
# Value: dict with challenge_description, action_plan, weekly_exercise

RECOMMENDATIONS: dict[tuple[str, frozenset], dict] = {
    # ─── Attachment Style ───
    ("attachment_style", frozenset({"anxious", "avoidant"})): {
        "pattern": "The Pursuit-Distance Cycle",
        "challenge_description": "One partner seeks closeness and reassurance while the other needs space and autonomy. The more one pursues, the more the other withdraws.",
        "action_plan": ["Name the cycle together — recognize it as a pattern, not a personal failing", "Create a departure/return protocol: the withdrawing partner communicates when they need space AND commits to a return time", "The pursuing partner practices one self-soothing activity before sending a follow-up", "Schedule one daily 10-minute connected check-in"],
        "weekly_exercise": "The Pause Protocol — When you feel the urge to pursue or withdraw, pause for 5 minutes. Write down what you actually need, share at your daily check-in.",
    },
    ("attachment_style", frozenset({"fearful_avoidant", "fearful_avoidant"})): {
        "pattern": "The Push-Pull Loop",
        "challenge_description": "Both partners oscillate between wanting closeness and needing distance, rarely synchronizing. Intense when aligned, disconnected when not.",
        "action_plan": ["Develop a shared signaling system for current state", "Accept that desynchronization is normal", "Build one predictable daily connection touchpoint", "When both are in closeness mode: savor it explicitly"],
        "weekly_exercise": "The State Check-In — Each morning, rate closeness desire 1–5. Share without judgment. If both 4–5, plan something together.",
    },
    ("attachment_style", frozenset({"avoidant", "avoidant"})): {
        "pattern": "Emotional Desert",
        "challenge_description": "Neither partner initiates emotional depth. The relationship feels peaceful but emotionally thin. Issues go unaddressed.",
        "action_plan": ["Accept that emotional initiation feels unnatural — commit to scheduling it", "Weekly 15-minute feelings check", "Use prompts to lower activation energy", "Celebrate any vulnerability as courage"],
        "weekly_exercise": "The One-Truth Ritual — Once per week, each share one emotional truth you haven't said yet. Listener responds only with 'Thank you for telling me.'",
    },
    ("attachment_style", frozenset({"anxious", "anxious"})): {
        "pattern": "The Reassurance Spiral",
        "challenge_description": "Both partners seek reassurance without a stable internal base to provide it consistently. Small triggers can escalate when both are activated.",
        "action_plan": ["Build individual self-regulation practices", "Agree on a reassurance ritual that doesn't require mind-reading", "When both activated: name it and take a parallel-regulation break", "Maintain one friendship each for external grounding"],
        "weekly_exercise": "The Self-Soothe First — When anxiety arises, take 10 minutes for your calming practice BEFORE bringing it to your partner. Track how many times you self-soothe first.",
    },
    # ─── Communication Style ───
    ("communication_style", frozenset({"analytical", "expressive"})): {
        "pattern": "Logic vs Emotion",
        "challenge_description": "One processes through logic; the other through emotion. Analytical responds to feelings with solutions; Expressive responds to logic with frustration.",
        "action_plan": ["Learn the Translation Protocol: ask 'solve or listen?'", "Analytical: lead with acknowledgment before analysis", "Expressive: lead with the ask (vent or input?)", "Weekly both-modes conversation: 10 min sharing + 10 min solving"],
        "weekly_exercise": "The Mode Signal — Agree on 'Listen mode' and 'Solve mode' as opening signals for every significant conversation this week.",
    },
    ("communication_style", frozenset({"direct", "expressive"})): {
        "pattern": "Efficiency vs Connection",
        "challenge_description": "Direct wants the bottom line; Expressive wants emotional engagement. Direct cuts short; Expressive feels dismissed.",
        "action_plan": ["Direct: stay 2 extra minutes beyond comfort", "Expressive: lead with main point in first 30 seconds", "Distinguish information-exchange from connection conversations", "Both validate the other's style explicitly"],
        "weekly_exercise": "The Extra Two Minutes — Direct stays 2 minutes longer than natural in one conversation per day. Expressive leads with one sentence summarizing their main point.",
    },
    ("communication_style", frozenset({"direct", "diplomatic"})): {
        "pattern": "Clarity vs Softness",
        "challenge_description": "Direct says things plainly; Diplomatic wraps in softness. Direct may feel the other is indirect; Diplomatic may feel the other is harsh.",
        "action_plan": ["Direct: one softening phrase before hard messages", "Diplomatic: state need in one clear sentence after context", "Acknowledge both styles explicitly", "For important conversations: state what you need from the other's style"],
        "weekly_exercise": "The Translation Round — Each partner restates what the other said in their OWN style. Check: did the translation feel accurate?",
    },
    # ─── Conflict Style ───
    ("conflict_style", frozenset({"avoiding", "competing"})): {
        "pattern": "The Escalation-Shutdown Cycle",
        "challenge_description": "Competing escalates intensity; Avoiding shuts down under pressure. Nothing resolves. Both feel profoundly unheard.",
        "action_plan": ["Establish rules of engagement before conflict", "Written agenda for recurring issues", "Time-box: no session exceeds 20 minutes", "Avoiding: practice ONE sentence of engagement before taking space"],
        "weekly_exercise": "The 5-5-5 — Practice with LOW-stakes disagreement. Each gets 5 min to state position, then 5 min collaborative solution. Competing: don't dominate. Avoiding: stay for full 15 min.",
    },
    ("conflict_style", frozenset({"avoiding", "avoiding"})): {
        "pattern": "The Silence Agreement",
        "challenge_description": "Both avoid conflict. Issues accumulate unspoken. Peaceful surface but resentments build underground.",
        "action_plan": ["Reframe raising issues as caring for the relationship", "Monthly written state-of-relationship notes", "Start with tiny issues (micro-concerns)", "Celebrate every instance of raising a concern"],
        "weekly_exercise": "The Micro-Raise — Each partner raises ONE tiny thing per week. Listener responds only with 'Thank you. I'll work on that.' No defending.",
    },
    ("conflict_style", frozenset({"competing", "competing"})): {
        "pattern": "The Battleground",
        "challenge_description": "Both fight to win. Conflicts are intense, long, and exhausting. Neither yields easily.",
        "action_plan": ["Introduce: winning the argument = losing the relationship", "Turn-taking: 3 min uninterrupted each, then discussion", "Acknowledge the other's strongest point before countering", "Practice deliberately losing on low-stakes issues"],
        "weekly_exercise": "The Graceful Concession — Once this week, one partner CHOOSES to concede. Say: 'You feel more strongly. Let's go with yours.' Alternate weekly.",
    },
    ("conflict_style", frozenset({"avoiding", "collaborative"})): {
        "pattern": "The Frustrated Engager",
        "challenge_description": "Collaborative wants to discuss and resolve; Avoiding retreats. The engager feels shut out; the avoider feels chased.",
        "action_plan": ["Validate both needs: engagement IS necessary; space IS necessary", "Return contract: avoiding partner names return time", "Collaborative: not every issue needs immediate resolution", "Use written communication for initial response"],
        "weekly_exercise": "The Text-First, Talk-Second — Collaborative raises concern via short text. Avoiding responds in writing within 24h. THEN discuss in person.",
    },
    # ─── Financial Personality ───
    ("financial_personality", frozenset({"saver", "spender"})): {
        "pattern": "The Restriction-Freedom Fight",
        "challenge_description": "Saver sees money as security; Spender sees it as life-quality. Every purchase is a potential argument.",
        "action_plan": ["Separate buckets: joint + personal fund each", "No-questions-asked spending threshold per person", "Monthly money meeting: celebrate both savings AND enjoyment wins", "Name the underlying values: security vs experience"],
        "weekly_exercise": "The Permission Slip — Each week, each partner gives the other permission for one financial act. Saver permits one guilt-free purchase; Spender permits one non-spend.",
    },
    ("financial_personality", frozenset({"investor", "spender"})): {
        "pattern": "Present vs Future",
        "challenge_description": "Investor wants every dollar working toward a goal; Spender wants to enjoy the present.",
        "action_plan": ["Agree on automated savings/investment floor", "Investor: frame present spending as relationship investment", "Spender: acknowledge Investor's planning serves both", "One shared experience per month that's both investment and experience"],
        "weekly_exercise": "The ROI Reframe — Investor identifies the relationship ROI of one thing Spender enjoyed. Spender acknowledges how one Investor win serves both.",
    },
    # ─── Lifestyle Type ───
    ("lifestyle_type", frozenset({"adventurous", "homebody"})): {
        "pattern": "The Go/Stay Divide",
        "challenge_description": "Every weekend is a negotiation. Adventurous feels trapped; Homebody feels exhausted by plans.",
        "action_plan": ["Accept the difference — goal is respect, not conversion", "Alternating weekends: one adventure, one home", "Independent adventure time without guilt", "Homebody makes home appealing for return"],
        "weekly_exercise": "The Willing Participant — Each partner fully participates in ONE activity that's the other's preference. Find something to enjoy. Reflect: what did I actually enjoy?",
    },
    ("lifestyle_type", frozenset({"homebody", "social"})): {
        "pattern": "Energy Mismatch",
        "challenge_description": "Social partner is energized by people; Homebody is drained. Weekends become zero-sum between social plans and quiet time.",
        "action_plan": ["Social maintains independent social life", "Agree on weekly social budget: X events together, Y solo", "Homebody attends one event per week at full presence", "Social protects one evening as sacred couple-only time"],
        "weekly_exercise": "The Social Budget — Each week, agree which events Homebody joins (1–2) and which Social does solo. Homebody: 'Have fun!' without guilt. Social: 'I'll miss you' without resentment.",
    },
    # ─── Relationship Archetype ───
    ("relationship_archetype", frozenset({"independent", "partner"})): {
        "pattern": "The We/I Tension",
        "challenge_description": "Partner wants shared identity and togetherness; Independent wants maintained autonomy. Neither is wrong, but defaults clash.",
        "action_plan": ["Map territory: what's 'ours' vs 'mine'", "Partner: name one personal interest that's just theirs", "Independent: initiate one 'us' activity per week unprompted", "Agree on togetherness floor AND independence floor"],
        "weekly_exercise": "The Both/And Calendar — Plan week together. Mark 'Together time' blocks (min 3 evenings) AND 'Independent time' blocks (min 2). Neither encroaches on the other.",
    },
    ("relationship_archetype", frozenset({"explorer", "partner"})): {
        "pattern": "Depth vs Breadth",
        "challenge_description": "Partner wants to go deeper into the relationship; Explorer wants to go wider. Partner may feel Explorer is never satisfied.",
        "action_plan": ["Reframe: Explorer's growth SERVES the relationship", "Explorer includes Partner in one growth activity per month", "Partner identifies one area of personal growth", "Daily ritual: 'What did you discover today?'"],
        "weekly_exercise": "The Shared Discovery — Explorer shares something discovered. Partner asks 3 genuine questions. Partner shares something meaningful about the relationship. Explorer responds with depth.",
    },
    ("relationship_archetype", frozenset({"independent", "nurturer"})): {
        "pattern": "Space vs Care",
        "challenge_description": "Nurturer wants to help and support; Independent doesn't want to be taken care of. Nurturer feels rejected; Independent feels smothered.",
        "action_plan": ["Create 'help-welcome zones' and 'I've-got-this zones'", "Nurturer: ask before jumping in", "Independent: receive help gracefully in at least one area", "Nurturer redirects some caregiving energy outward"],
        "weekly_exercise": "The One-Thing Receive — Independent picks ONE thing to gratefully accept help with. Nurturer provides care without expanding. Track: could Independent receive without discomfort?",
    },
}

# Generic fallback for pairings not explicitly listed
GENERIC_RECOMMENDATIONS: dict[str, dict] = {
    "low": {
        "challenge_description": "You have different approaches in this area, but the difference is manageable with awareness.",
        "action_plan": ["Acknowledge the difference openly", "Discuss how it shows up in daily life", "Agree on one small accommodation each", "Check in monthly on whether the accommodation feels fair"],
        "weekly_exercise": "The Weekly Check — Once this week, ask each other: 'Is there anything about how we handle [this dimension] that's been on your mind?'",
    },
    "medium": {
        "challenge_description": "This is a meaningful difference that requires intentional effort from both partners.",
        "action_plan": ["Name the specific friction points", "Each partner identifies what they need from the other", "Establish one new ritual or agreement", "Track progress weekly for 4 weeks"],
        "weekly_exercise": "The Experiment — Try one new approach to this dimension for one week. At the end, both rate 1–10: did it help? Adjust and try again.",
    },
    "high": {
        "challenge_description": "This is a fundamental difference that creates significant daily friction. Growth is possible but requires sustained commitment.",
        "action_plan": ["Accept that this difference won't disappear — the goal is management, not elimination", "Identify the three worst moments this causes each week", "Create a specific protocol for those moments", "Consider whether external support (book, course, counselor) would help"],
        "weekly_exercise": "The Protocol Practice — When the friction moment occurs this week, use your agreed protocol instead of the old pattern. Track: did you use it? Did it help even slightly?",
    },
}


def get_recommendation(dimension: str, type_a: str, type_b: str, severity: str) -> dict:
    """
    Get the matching recommendation for a type pairing.
    Falls back to generic severity-based recommendation if no specific pairing exists.
    """
    key = (dimension, frozenset({type_a, type_b}))
    specific = RECOMMENDATIONS.get(key)

    if specific:
        return specific

    # Fallback to generic based on severity
    return GENERIC_RECOMMENDATIONS.get(severity, GENERIC_RECOMMENDATIONS["medium"])
