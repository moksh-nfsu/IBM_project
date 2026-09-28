# Problem Statement

## Context

Coordinated disinformation campaigns on social media have preceded real-world communal violence in several Indian districts. In 2020 and 2022, hashtag campaigns that appeared to describe ongoing violence spread rapidly — but police and district administrations had no systematic way to:

1. Distinguish organic outrage from orchestrated amplification
2. Identify *when* a campaign was transitioning from passive spread to active mobilisation
3. Correlate online activity with offline incidents in near-real-time
4. Know *where* and *when* a planned offline event was advertised

By the time official fact-checks or counter-messaging were deployed, the campaigns had already reached mobilisation stage.

## The gap

Existing social-media monitoring tools provide keyword alerts or engagement metrics, but they do not:

- Model *coordination* (who is acting together, how many accounts, how fresh)
- Track narrative *evolution* (CLAIM → AMPLIFICATION → INFLAMMATORY → MOBILIZATION)
- Provide an *explainable* escalation state with auditable trigger conditions
- Correlate online content with offline police-log incidents
- Generate a structured, legally-referenced analyst brief for a district SP or magistrate

## Constraints

- Police analysts are not data scientists. The interface must be simple and the findings must be explainable in plain language.
- Legal suggestions must reference the actual sections of the Bharatiya Nyaya Sanhita (BNS) with disclaimers.
- False positives are dangerous. The system must not over-flag organic discourse. A built-in benign decoy validates this.
- No database, no cloud deployment required for field use. Must run on a laptop with no internet.
- Privacy: PII must be masked in all displays; no profiling by religion, caste, or identity.

## Scope (hackathon)

We model one 24-hour window of mock data from a fictional set of five districts in India. The same pipeline generalises to any region or language provided posts are in the schema.
