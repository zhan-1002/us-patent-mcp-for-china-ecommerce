# Case Study: Recovering a Generic Design Patent Through Citations

## Problem

The historical `religious_cross` sample contains five US design patents:

`D1066113`, `D1050666`, `D786128`, `D656429`, and `D638741`.

Product-language queries included `religious cross`, `wooden cross`, `heart cross`, `cross ornament`, and `cross`. Keyword and title search recovered four of the five patents, but missed `D1050666` because its title was too generic to rank reliably for the product phrases.

## Search path

1. Run bounded PPUBS title searches for the query set.
2. Merge and normalize all design-patent numbers.
3. Select the top three design candidates as citation seeds.
4. Expand both backward and forward PPUBS citations.
5. Re-run the historical recall evaluation over the complete merged set.

## Result

| Metric | Result |
|---|---:|
| Keyword/title recall | 4/5 |
| Final recall after citations | 5/5 |
| Recall rate | 100% |
| Network request budget used | 14 |
| Unique design candidates | 114 |

`D1050666` was recovered from the real citation network of `D656429`. The expected patent number was not injected into a search query or appended to the results.

## Why it matters

This case demonstrates why a small first-page result and keyword-only search are insufficient for design-patent screening. Citation expansion improved recall while preserving an auditable discovery path.

It does **not** prove that every one of the 114 candidates is relevant or that any product infringes a patent. Recall regression, relevance ranking, legal status, and visual comparison are separate evaluations.
