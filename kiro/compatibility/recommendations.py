# -*- coding: utf-8 -*-
"""Improvement recommendations per type pairing (F5B, rewritten F8B).

Sourced from ImprovementLibrary.md. Each entry provides challenge description,
action plan, and weekly exercise for a specific dimension + type pairing.

F8B rewrite: all content now uses concrete, actionable language.
No clinical/therapy jargon. Plain English only.
"""

from __future__ import annotations

# Key: (dimension, frozenset({type_a, type_b}))
# Value: dict with challenge_description, action_plan, weekly_exercise

RECOMMENDATIONS: dict[tuple[str, frozenset], dict] = {
    # ─── Attachment Style ───
    ("attachment_style", frozenset({"anxious", "avoidant"})): {
        "pattern": "The Pursuit-Distance Cycle",
        "challenge_description": "One partner reaches out for connection more often, while the other needs more personal space. The more one reaches out, the more the other pulls back — and both end up feeling frustrated.",
        "action_plan": [
            "Sit together for 10 minutes and name the pattern: 'When I reach out more, you need more space. When you take space, I reach out more.' Agree it's a pattern, not anyone's fault.",
            "Create a simple signal: the partner who needs space says 'I need 30 minutes to myself — I'll be back at [specific time]' and then actually returns at that time.",
            "The partner who reaches out more picks one calming activity (walk, music, journaling) to do for 10 minutes before sending a follow-up message.",
            "Schedule one 10-minute evening check-in at the same time daily — no phones, just talking. This gives both partners something predictable to rely on.",
        ],
        "weekly_exercise": "The Evening Check-In — Every evening at your agreed time, sit together for 10 minutes. Each share one thing from your day and one thing you appreciate about the other. No problem-solving, just listening. Track: did you do the check-in at least 5 out of 7 days this week?",
    },
    ("attachment_style", frozenset({"fearful_avoidant", "fearful_avoidant"})): {
        "pattern": "The Push-Pull Loop",
        "challenge_description": "Both partners sometimes want closeness and sometimes want space, but rarely at the same time. When one reaches out, the other might be pulling away — and the roles keep switching.",
        "action_plan": [
            "Each morning, tell each other: 'Today I'm feeling like a 3 out of 5 for closeness' (1 = need lots of space, 5 = want lots of connection). No judgment about the number.",
            "When both of you feel like connecting at the same time, say it out loud: 'This feels good right now.' Noticing it helps it happen more.",
            "Pick one 5-minute daily ritual that happens no matter what (morning coffee together, goodnight kiss, a short walk). Keep it short enough that neither person feels overwhelmed.",
            "When one of you switches from wanting closeness to needing space, say: 'I'm shifting — I need a bit of quiet. It's not about you.' Keep it to one sentence.",
        ],
        "weekly_exercise": "The Morning Number — Each morning, rate your closeness desire from 1 to 5 and share it with your partner. Don't explain or justify — just share the number. At the end of the week, look at both sets of numbers together. Notice any patterns without trying to fix them. Time: 2 minutes daily.",
    },
    ("attachment_style", frozenset({"avoidant", "avoidant"})): {
        "pattern": "Comfortable Distance",
        "challenge_description": "Both partners value independence, which keeps things peaceful — but important feelings can go unspoken. Over time, the relationship may feel more like roommates than partners.",
        "action_plan": [
            "Set a weekly 15-minute 'feelings check' at a specific time (e.g., Sunday at 7pm). Use this prompt: 'One thing I appreciated this week was...' and 'One thing on my mind is...'",
            "When your partner shares something personal, respond with 'Thank you for telling me' before saying anything else. This makes sharing feel safer.",
            "Once a week, initiate one small gesture of connection that's slightly outside your comfort zone — a longer hug, a compliment, asking how their day really went.",
            "Text each other one appreciation during the workday, even if it's short: 'I was thinking about you' or 'Thanks for making coffee this morning.'",
        ],
        "weekly_exercise": "The One Truth — Once this week, sit together for 10 minutes. Each share one emotional truth you haven't said yet. It can be positive ('I felt really happy when you...') or honest ('I've been feeling a bit distant this week'). The listener only says: 'Thank you for telling me.' No fixing, no defending. Track: did you both share one truth this week? Time: 10 minutes.",
    },
    ("attachment_style", frozenset({"anxious", "anxious"})): {
        "pattern": "The Reassurance Loop",
        "challenge_description": "Both partners want lots of reassurance, but neither has a fully steady base to always provide it. Small worries can grow quickly when both are feeling unsure at the same time.",
        "action_plan": [
            "Each partner picks one personal calming activity they can do alone (a walk, 5 deep breaths, a favorite song). Practice it at least once a day, even when not stressed.",
            "Create a simple reassurance phrase that works for both of you — something like 'We're okay' or 'I'm here and I love you.' Use it when either person seems worried.",
            "When both of you feel worried at the same time, name it together: 'We're both feeling unsure right now. Let's each take 10 minutes for our calming thing, then come back and hug.'",
            "Each maintain at least one friendship or activity that's just yours — this gives you another source of stability besides each other.",
        ],
        "weekly_exercise": "The Calm-First Practice — When you notice relationship worry rising, use your calming activity for 10 minutes BEFORE bringing it to your partner. Then say: 'I felt worried about X, I calmed myself first, and now I'd like to check in about it.' Track: how many times did you calm first before seeking reassurance? Aim for 3+ times this week. Time: 10 minutes per instance.",
    },
    # ─── Communication Style ───
    ("communication_style", frozenset({"analytical", "expressive"})): {
        "pattern": "Head vs Heart",
        "challenge_description": "One partner thinks through problems with logic, while the other processes through sharing feelings. The logical one offers solutions when the other just wants to be heard. The feeling one gets frustrated when the other seems detached.",
        "action_plan": [
            "Before starting any important conversation, the speaker says either 'I need you to listen' or 'I need your input.' This one sentence prevents 90% of the frustration.",
            "The logical partner practices saying 'That sounds really hard' or 'I can see why that bothered you' BEFORE offering any analysis or solutions.",
            "The expressive partner practices leading with a one-sentence summary of the main point, then expanding with details. This helps the logical partner stay engaged.",
            "Schedule one 20-minute weekly conversation divided into two halves: 10 minutes of pure listening (no fixing), then 10 minutes of problem-solving together.",
        ],
        "weekly_exercise": "The Listen-or-Solve Signal — For every important conversation this week, start with either 'Listen mode' (I need to be heard) or 'Solve mode' (I want your help fixing this). The other person follows that mode for the whole conversation. At the end of the week, count how many times you used the signal. Did it reduce frustration? Time: 1 minute setup per conversation.",
    },
    ("communication_style", frozenset({"direct", "expressive"})): {
        "pattern": "Short vs Long",
        "challenge_description": "One partner likes to get to the point quickly, while the other wants to share the full story with all the feelings. The brief one feels trapped in long conversations; the storyteller feels cut off.",
        "action_plan": [
            "The direct partner commits to staying in conversations 2 extra minutes beyond when they'd normally wrap up. Set a mental timer — those extra minutes often contain the most important part.",
            "The expressive partner practices starting with the main point in one sentence, then adding context: 'The short version is X. Here's what happened...'",
            "Together, label conversations: 'quick update' (1 minute max) vs 'real talk' (15+ minutes with full attention). Both types are valid.",
            "Each day, tell your partner one thing you genuinely appreciate about their communication style: 'I love how efficient you are' or 'I love how you make stories come alive.'",
        ],
        "weekly_exercise": "The Two Extra Minutes — Once a day, the direct partner deliberately stays 2 minutes longer in a conversation than feels natural. Notice: did something meaningful come up in those extra minutes? The expressive partner leads one conversation with a single opening sentence before expanding. Notice: did the direct partner engage more? Time: 5 minutes total. Track: how many days did you practice?",
    },
    ("communication_style", frozenset({"direct", "diplomatic"})): {
        "pattern": "Blunt vs Gentle",
        "challenge_description": "One partner says exactly what they mean; the other softens everything. The blunt one can seem harsh; the gentle one can seem unclear. Each wishes the other would just communicate 'normally.'",
        "action_plan": [
            "The direct partner adds one softening phrase before delivering tough messages: 'I'm sharing this because I care about us...' then says what they need to say.",
            "The diplomatic partner practices ending with one clear, direct sentence after any context-setting: 'What I'm actually asking for is...'",
            "When either partner feels hurt or confused, they say: 'Can you say that again in my language?' — giving each other permission to translate.",
            "For important topics, both state upfront what they need from the other: 'I need you to be gentle with this' or 'I need you to be direct — no hints.'",
        ],
        "weekly_exercise": "The Translation Check — Pick one conversation from this week. Each partner restates what the other said in their OWN style. The direct partner translates: 'So what you're really saying is...' The diplomatic partner translates: 'I think what you meant was...' Check with each other: was the translation accurate? Time: 10 minutes. Do this once this week.",
    },
    # ─── Conflict Style ───
    ("conflict_style", frozenset({"avoiding", "competing"})): {
        "pattern": "Loud vs Silent",
        "challenge_description": "One partner gets more intense during disagreements, while the other shuts down. The louder one feels ignored; the quieter one feels overwhelmed. Nothing gets resolved because they can't stay in the conversation together.",
        "action_plan": [
            "Agree on ground rules BEFORE your next disagreement: no raised voices, no walking away without saying when you'll return. Write these down and put them on the fridge.",
            "The quieter partner practices saying ONE sentence before taking space: 'I hear you. I need 20 minutes and I'll be back at [time].' Then follow through.",
            "The more intense partner practices lowering their voice by half when they feel themselves heating up. Quieter = more likely to be heard.",
            "Time-limit all disagreements to 20 minutes. If unresolved, schedule Part 2 within 48 hours. This prevents marathon arguments and indefinite avoidance.",
        ],
        "weekly_exercise": "The 5-5-5 Practice — Pick one LOW-stakes disagreement this week (what to eat, what to watch). Each partner gets 5 minutes to share their position without interruption. Then 5 minutes of finding a solution together. Total: 15 minutes max. The intense partner practices not dominating. The quiet partner practices staying present for the full 15 minutes. Track: could you both stay the whole time?",
    },
    ("conflict_style", frozenset({"avoiding", "avoiding"})): {
        "pattern": "The Silence",
        "challenge_description": "Both partners avoid bringing up issues. Everything seems fine on the surface, but small frustrations quietly build up underneath. Eventually they either drift apart or one person explodes unexpectedly.",
        "action_plan": [
            "Reframe: raising an issue is an act of CARING about the relationship, not attacking it. Say to each other: 'If something bothers me, I'll tell you — because I want us to be good.'",
            "Start tiny: practice raising micro-concerns (intensity 2/10) before they become big ones. Example: 'Hey, small thing — when you leave dishes overnight, I notice it bugs me.'",
            "The listener responds to any raised concern with ONLY: 'Thank you for telling me. I'll think about that.' No defending, no counter-complaints. Make it safe to speak up.",
            "Schedule a monthly 15-minute 'state of us' check: each partner shares one appreciation and one thing they'd like to improve. Use a timer so neither avoids their turn.",
        ],
        "weekly_exercise": "The Micro-Raise — Each partner raises ONE tiny thing this week that's been on their mind (maximum 2/10 intensity). Share it calmly: 'Small thing — I noticed [X] and it [bothered/confused/worried] me a little.' The listener says: 'Thank you for telling me.' Nothing more. Track: did each of you raise one thing? Time: 2 minutes each.",
    },
    ("conflict_style", frozenset({"competing", "competing"})): {
        "pattern": "The Battle",
        "challenge_description": "Both partners fight hard to be right. Disagreements become long, intense, and exhausting. Neither wants to back down, and small issues can turn into major arguments.",
        "action_plan": [
            "Before responding to your partner's point, first say what's VALID about it: 'You're right that...' THEN share your view. This one change shortens arguments dramatically.",
            "Take turns: one person speaks for 3 minutes without interruption, then the other for 3 minutes. Only AFTER both have spoken do you discuss solutions.",
            "Ask yourselves: 'Do I want to be right, or do I want to be happy together?' Write this question somewhere you'll both see it daily.",
            "Once a week, one partner deliberately chooses to say: 'You feel more strongly about this — let's go with your preference.' Alternate who does this each week.",
        ],
        "weekly_exercise": "The Graceful Yield — This week, one partner CHOOSES to let go of one small disagreement. Say: 'This matters more to you than to me. Let's do it your way.' Notice how it feels — dangerous, or actually fine? Next week, the other partner does it. Track: did yielding actually cost you anything? Time: 1 moment of choice.",
    },
    ("conflict_style", frozenset({"avoiding", "collaborative"})): {
        "pattern": "Talk vs Space",
        "challenge_description": "One partner wants to discuss issues right now and work through them together. The other needs to step away and think first. The talker feels shut out; the quiet one feels pressured.",
        "action_plan": [
            "Agree: the partner who needs space ALWAYS names a return time: 'I need until tonight at 8pm to think about this. I promise I'll come back to discuss it then.'",
            "The partner who wants to talk NOW practices patience: not every issue needs immediate resolution. Ask yourself: 'Will this be just as important in 3 hours?'",
            "Try 'text first, talk second' for sensitive topics: the talker sends a short message about what they want to discuss. The quiet partner responds in writing when ready. THEN talk in person.",
            "The quiet partner initiates ONE conversation per month about something that matters to them. This is powerful because it shows they're engaged, not just avoiding.",
        ],
        "weekly_exercise": "The Written Warm-Up — For one concern this week, the talking partner writes it in a short text or note (3 sentences max). The quiet partner reads it and responds in writing within 24 hours. THEN sit together and talk, having already processed the initial surprise. Track: was the in-person conversation calmer than usual? Time: 5 minutes writing + 15 minutes talking.",
    },
    # ─── Love Language ───
    ("love_language", frozenset({"words", "time"})): {
        "pattern": "Words vs Presence",
        "challenge_description": "One partner feels most loved hearing words of appreciation, while the other feels most loved through undivided attention and shared time. Each is giving love — but in a language the other doesn't naturally speak.",
        "action_plan": [
            "The words partner writes one specific, genuine compliment for the time partner each day — a text, a note, or said out loud. Be specific: 'I loved how you handled that call today' instead of 'you're great.'",
            "The time partner puts their phone completely away for 15 minutes each evening and gives undivided attention — no screens, no multitasking, just presence.",
            "Together, create a '5-minute ritual' that combines both languages: sit together (time) and each share one thing you appreciated about the other today (words).",
            "Once a week, each partner does something deliberately in the OTHER's language: the words partner plans 30 minutes of focused together-time; the time partner writes a heartfelt note or message.",
        ],
        "weekly_exercise": "The Daily Deposit — Each day, make one intentional 'deposit' in your partner's language. Words partner: 15 minutes of phone-free focused presence. Time partner: one specific, heartfelt verbal appreciation. At the end of the week, each name the 3 deposits that meant the most. Track: did you make at least 5 deposits each this week? Time: 5 minutes per deposit.",
    },
    ("love_language", frozenset({"words", "touch"})): {
        "pattern": "Words vs Touch",
        "challenge_description": "One partner feels loved through hearing words of appreciation and encouragement, while the other feels loved through physical closeness and affection. Both are expressing care — just through different senses.",
        "action_plan": [
            "The words partner initiates physical affection once per day without being asked — a long hug, holding hands, a touch on the shoulder. It doesn't need to be grand; consistency matters more.",
            "The touch partner says one specific appreciation out loud each day: what their partner did, how it made them feel, why it mattered. Specifics land harder than generics.",
            "Create a transition ritual that combines both: when reuniting after work, a 10-second hug (touch) followed by 'the best part of my day was...' (words).",
            "Before bed, spend 2 minutes connecting: the touch partner holds their partner's hand while the words partner shares one thing they're grateful for about the relationship.",
        ],
        "weekly_exercise": "The Reunion Ritual — Every time you reunite after being apart (coming home, waking up), combine both languages: a 10-second hug (touch) + one sentence of appreciation (words). Track: how many days did you do the reunion ritual? Aim for 5 out of 7 days. Time: 30 seconds per reunion.",
    },
    ("love_language", frozenset({"acts", "gifts"})): {
        "pattern": "Actions vs Tokens",
        "challenge_description": "One partner feels loved when the other does helpful things without being asked, while the other feels loved through thoughtful gifts and surprises. Both show care through action — one practical, one symbolic.",
        "action_plan": [
            "The acts partner brings home one small, thoughtful token per week — it doesn't need to be expensive. A favorite snack, a flower, a book they'd enjoy. The thought matters more than the price.",
            "The gifts partner handles one task per week without being asked — something they know their partner usually does (dishes, errands, planning). Do it completely, not halfway.",
            "Together, identify 3 things each partner regularly does that goes unnoticed. Acknowledge them this week: 'I noticed you did X and it means a lot.'",
            "Once a month, surprise each other: the acts partner picks a meaningful gift; the gifts partner does something unexpectedly helpful. Keep it simple but intentional.",
        ],
        "weekly_exercise": "The Thoughtful Swap — This week, each partner does ONE thing in the other's language. Acts partner: bring home a small, thoughtful gift (under $10). Gifts partner: handle one household task completely without being asked. Afterward, tell each other: 'That made me feel loved because...' Track: did you both complete the swap? Time: varies.",
    },
    # ─── Financial Personality ───
    ("financial_personality", frozenset({"saver", "spender"})): {
        "pattern": "Save vs Spend",
        "challenge_description": "One partner feels safer with money in the bank; the other feels happier when money is used to enjoy life. Every purchase can become a source of tension when these values clash.",
        "action_plan": [
            "Create three accounts: (1) joint bills/savings, (2) your personal fund, (3) their personal fund. Agree on amounts. What's in your personal fund is spent WITHOUT the other person's approval or comment.",
            "Set a 'no-questions-asked' threshold — an amount either partner can spend freely without checking in (e.g., $50). This gives the spender freedom and the saver peace.",
            "Hold a 30-minute monthly money meeting: review joint spending, celebrate one saving win AND one enjoyment win. End with: 'Are we both feeling okay about money right now?'",
            "Name the underlying needs out loud: 'I need to know we're secure' and 'I need to enjoy what we earn.' Both are valid. Say it to each other now.",
        ],
        "weekly_exercise": "The Permission Exchange — Each week, each partner gives the other one financial 'permission': The saving partner says 'Buy yourself [something specific] this week — guilt-free.' The spending partner says 'Let's skip [one expense] this week — and I won't feel deprived.' Track: did giving permission feel freeing or scary? Time: 5 minutes to agree, then live it all week.",
    },
    ("financial_personality", frozenset({"investor", "spender"})): {
        "pattern": "Future vs Now",
        "challenge_description": "One partner wants every dollar working toward future goals; the other wants to enjoy life today. The planner feels the other is careless; the spender feels they're being denied a life worth living.",
        "action_plan": [
            "Agree on a monthly savings/investment amount that's automated and non-negotiable. Everything beyond that is genuinely available for spending. This satisfies both needs.",
            "The future-focused partner practices seeing shared experiences (a nice dinner, a weekend trip) as 'investing in the relationship' — because connection IS a return.",
            "The present-focused partner tells the future-planner once a month: 'I appreciate that you plan for us. Our future is better because of you.' Acknowledgment reduces lectures.",
            "Plan one shared experience per month that's BOTH an investment and enjoyment — a meaningful trip, a class together, something you'll both remember.",
        ],
        "weekly_exercise": "The Value Swap — The future-focused partner names one thing the spender enjoyed this week and identifies the relationship value: 'That dinner made us feel connected.' The present-focused partner names one financial win and says how it serves both of them: 'That extra savings means we can relax about next month.' Track: did you both complete the swap? Time: 5 minutes. Do this Sunday evening.",
    },
    # ─── Lifestyle Type ───
    ("lifestyle_type", frozenset({"adventurous", "homebody"})): {
        "pattern": "Go vs Stay",
        "challenge_description": "One partner gets energy from being out and doing things; the other recharges at home in quiet. Every weekend feels like a negotiation between adventure and rest.",
        "action_plan": [
            "Accept this difference — it won't change. The goal is respect and structure, not converting each other. Say to each other: 'I respect that you recharge differently than me.'",
            "Alternate weekends: one planned outing (adventure partner picks), one home day (homebody partner picks). Both participate fully in the other's choice — no complaining, genuine effort.",
            "The adventure partner maintains friends or activities they do independently — without guilt and without the homebody needing to come every time.",
            "The homebody makes home a place the adventure partner genuinely enjoys returning to — comfort, good food, a welcoming atmosphere.",
        ],
        "weekly_exercise": "The Full Participation Day — This week, each partner fully participates in ONE activity the other prefers. The adventure partner spends one full evening at home and finds something to enjoy about it. The homebody goes on one outing and finds something to enjoy. Afterward, share: 'What I actually enjoyed about that was...' Time: one evening/outing each. Track: did you find genuine enjoyment?",
    },
    ("lifestyle_type", frozenset({"homebody", "social"})): {
        "pattern": "Quiet vs People",
        "challenge_description": "One partner is energized by social gatherings; the other is drained by them. Weekends become a tug-of-war between 'let's have people over' and 'can we just stay in.'",
        "action_plan": [
            "The social partner maintains their own social life — friends they see without the quiet partner needing to attend every time. This is healthy, not a rejection.",
            "Agree on a weekly 'social budget': X events the quiet partner joins (with full presence), Y events the social partner does solo. Be specific about numbers.",
            "The quiet partner commits to attending one social event per week at full energy — not grudgingly, but genuinely present. In exchange, one evening is sacred couple-only time.",
            "The social partner protects at least one evening per week as quiet, just-the-two-of-us time. No guests, no plans. This is their gift to the relationship.",
        ],
        "weekly_exercise": "The Social Budget — Sunday evening, plan the upcoming week together. Mark which social events the quiet partner will join (pick 1–2) and which the social partner does alone. The quiet partner says 'Have fun!' without guilt. The social partner says 'I'll miss you' without resentment. Track: did the plan reduce weekly tension? Time: 10 minutes to plan on Sunday.",
    },
    # ─── Relationship Archetype ───
    ("relationship_archetype", frozenset({"independent", "partner"})): {
        "pattern": "We vs Me",
        "challenge_description": "One partner wants a strong shared identity and lots of togetherness; the other wants to maintain their individual life and autonomy. The togetherness partner feels rejected; the independent one feels trapped.",
        "action_plan": [
            "Together, draw a simple map: what's 'ours' (shared time, shared goals, shared spaces) vs what's 'mine/yours' (hobbies, friendships, alone time). Make both lists visible.",
            "The togetherness partner names one personal interest or activity that's just theirs — not shared with the partner. Having your own thing makes the relationship healthier.",
            "The independent partner initiates one 'us' activity per week without being asked — a date, cooking together, a walk. Initiating shows choice, not obligation.",
            "Agree on minimums: at least 3 evenings together per week AND at least 2 evenings of independent time. Neither encroaches on the other's allocation.",
        ],
        "weekly_exercise": "The Both/And Calendar — On Sunday, plan your week together. Mark at least 3 'Together evenings' and at least 2 'Independent evenings' for each partner. During together time, be fully present. During independent time, no guilt. Track at week's end: did both of you feel your needs were met? Rate satisfaction 1–10 each. Time: 10 minutes to plan.",
    },
    ("relationship_archetype", frozenset({"explorer", "partner"})): {
        "pattern": "Depth vs Breadth",
        "challenge_description": "One partner wants to go deeper into the relationship; the other wants to go wider — exploring new interests, ideas, and growth. The deep partner may feel the explorer is never satisfied; the explorer may feel held back.",
        "action_plan": [
            "Reframe: the explorer's personal growth actually SERVES the relationship. A growing person brings more back to share. Say it together: 'Your growth makes us better.'",
            "The explorer includes the depth partner in one discovery per month — share a book, try an activity together, teach something new you learned.",
            "The depth partner identifies one area of personal growth they want to explore — even small. This prevents the explorer from being the only one 'changing.'",
            "Create a daily ritual: 'What did you discover or learn today?' Both answer. This connects exploration to intimacy.",
        ],
        "weekly_exercise": "The Shared Discovery — Once this week, sit for 15 minutes. The explorer shares something they discovered or are excited about. The depth partner asks 3 genuine, curious questions (not skeptical ones). Then the depth partner shares one meaningful thing about the relationship. The explorer responds with full attention. Track: did you complete the full exchange? Did both feel heard? Time: 15 minutes.",
    },
    ("relationship_archetype", frozenset({"independent", "nurturer"})): {
        "pattern": "Space vs Care",
        "challenge_description": "One partner shows love by helping and caring for the other; the other doesn't want to be taken care of and values doing things themselves. The caring partner feels rejected; the independent one feels smothered.",
        "action_plan": [
            "Together, identify 'help-welcome zones' (areas where care is appreciated: packed lunch, running errands) and 'I've-got-this zones' (areas where independence is needed).",
            "The caring partner practices asking before jumping in: 'Would it help if I did X, or would you rather handle it?' One question prevents most friction.",
            "The independent partner practices receiving help gracefully in at least one area per week: 'Thank you — that actually means a lot to me.' Receiving is not weakness.",
            "The caring partner directs some nurturing energy outward — volunteering, helping friends, a pet. This satisfies the caregiving need without overwhelming the partner.",
        ],
        "weekly_exercise": "The One-Thing Receive — This week, the independent partner picks ONE thing to gratefully accept help with (making dinner, organizing something, handling a task). Receive it with a genuine 'Thank you.' The caring partner provides care in ONLY that area without expanding to others. Track: could the independent partner receive without discomfort? Time: varies by the chosen thing.",
    },
}

# Generic fallback for pairings not explicitly listed
GENERIC_RECOMMENDATIONS: dict[str, dict] = {
    "low": {
        "challenge_description": "You have different approaches in this area, and while it's manageable, a little awareness and effort will make things smoother between you.",
        "action_plan": [
            "Sit together for 10 minutes and each describe how you handle this area differently. Listen without judgment — just understand each other's perspective.",
            "Each partner names one specific thing they'd appreciate the other doing differently (small and concrete, not 'be better at this').",
            "Try the suggested change for one full week. At the end of the week, both rate 1–10: 'Did this feel better?'",
            "If it helped, keep it. If not, adjust together and try something else next week.",
        ],
        "weekly_exercise": "The Weekly Check — At the end of the week, ask each other: 'Is there anything about how we handle this area that's been on your mind?' Listen. Say 'Thank you for telling me.' Discuss one small adjustment for next week. Time: 10 minutes.",
    },
    "medium": {
        "challenge_description": "This is a real difference between you that creates friction regularly. It's not anyone's fault — you simply approach this area differently. With focused effort, this can improve significantly.",
        "action_plan": [
            "Together, name the specific moments when this difference causes frustration. Write down the 2–3 situations that come up most often.",
            "For each situation, each partner writes down what they need from the other. Share these needs out loud: 'When X happens, I need you to...'",
            "Pick the ONE most common situation and create a specific plan: 'When X happens, I will do Y and you will do Z.'",
            "Practice your plan for 2 weeks. Then sit together and assess: is it working? What needs adjusting?",
        ],
        "weekly_exercise": "The Friction Log — Each time this difference causes tension this week, briefly note: what happened, how each person felt, and what you wish had gone differently. On Sunday, review the log together for 15 minutes. Pick one pattern to address with a specific agreement. Time: 2 minutes per entry + 15 minutes review.",
    },
    "high": {
        "challenge_description": "This is a significant difference that creates daily friction between you. Neither of you is wrong — you're simply wired differently in this area. Real improvement is possible, but it requires consistent effort from both partners over several weeks.",
        "action_plan": [
            "Accept together: this difference won't disappear. The goal is managing it well, not eliminating it. Say to each other: 'I accept that we're different here, and I'm committed to making it work.'",
            "Identify the 3 worst moments this causes each week. Be specific: 'Tuesday morning when... Thursday evening when...'",
            "For each of those moments, create a clear protocol: 'When this happens, I will [specific action] instead of my usual response. You will [specific action].'",
            "Practice the protocol for 3 weeks. Keep a simple tally: used it / didn't use it. Aim for improvement, not perfection. After 3 weeks, assess together whether you need additional support.",
        ],
        "weekly_exercise": "The Protocol Practice — When one of your identified friction moments occurs this week, use your agreed protocol instead of reacting automatically. Afterward, briefly acknowledge each other: 'We just did the thing differently. Good.' Track: how many times did you use the protocol vs. fall into the old pattern? Aim for more protocol use each week. Time: varies by situation.",
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
