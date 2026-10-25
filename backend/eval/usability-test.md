# Usability test kit

The proposal's usability target (section 7, NFR-4): **at least 80% of 10 to 15 classmates save a
document and get a cited answer within two minutes, unaided.**

## Before each session

1. Start Recall with an **empty library** (a fresh database, or delete every item).
2. Put `sample.pdf` on the desktop: any short, text-based PDF the participant hasn't read, such
   as a lecture handout. Note one fact in it to ask about.
3. Open http://localhost:3000 in a browser and hand over the laptop. Start a timer when they
   first touch it.

Say only this: *"This app keeps your reading material. Please do the tasks on the card. I can't
help, but tell me what you're thinking as you go."*

## Task card (give to the participant)

1. Save the PDF on the desktop into Recall.
2. Save this article as well: `https://en.wikipedia.org/wiki/Bloom_filter`
3. Ask Recall: *"Who invented the Bloom filter?"* and open the passage the answer came from.
4. Ask Recall a question about the PDF.
5. Show only the items tagged with one of the tags Recall added.

## What to record

| Participant | Task 1 time | Tasks 1–3 within 2 min? | Tasks completed unaided (of 5) | Where they hesitated | SUS score |
| --- | --- | --- | --- | --- | --- |
| P1 | | | | | |
| P2 | | | | | |

"Unaided" means no hint from you. Note every hesitation longer than about five seconds and what
they were looking for; those notes are the most useful part.

## Questionnaire (System Usability Scale)

Ask after the tasks. Each item is rated 1 (strongly disagree) to 5 (strongly agree).

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

**Scoring:** for odd items subtract 1 from the rating; for even items subtract the rating from 5.
Add the ten results and multiply by 2.5, giving 0 to 100. Around 68 is average; above 80 is good.

Then ask two open questions: *"What was confusing?"* and *"Would you use this for your own notes?
Why or why not?"*

## Reporting

Report the share of participants who finished tasks 1–3 unaided within two minutes (the target
is 80%), the mean SUS score, and the three most common problems with what you changed because of
them. Report a missed target as missed.
