| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Embed + store (s) | Search ms/query | Cost |
|---|---|---|---|---|---|---|---|
| A | dev | 7/19 | 14/19 | 460 | 6.23 + 0.07 | 2.68 | $0 |
| A | test | 0/6 | 2/6 | 460 | 6.23 + 0.07 | 2.6 | $0 |
| B | dev | 10/19 | 14/19 | 369 | 6.00 + 0.06 | 3.06 | $0 |
| B | test | 3/6 | 5/6 | 369 | 6.00 + 0.06 | 2.1 | $0 |
| C | dev | 10/19 | 14/19 | 369 | 0 (reuse B vectors) + 0.05 | 2.19 | $0 |
| C | test | 3/6 | 5/6 | 369 | 0 (reuse B vectors) + 0.05 | 1.56 | $0 |

| Strategy | Coherence mean /2 (n) | Metadata đủ & đúng (n/N, test top-3) | Filter tuân thủ dev | Filter tuân thủ test | Grounding 0/1/2 (test) | Grounding mean /2 |
|---|---|---|---|---|---|---|
| A | 0.9 (10) | 18/18 | 2/3 | 1/2 | 3/1/2 | 0.83 |
| B | 1.7 (10) | 18/18 | 1/3 | 1/2 | 1/0/5 | 1.67 |
| C | 1.7 (10) | 18/18 | 3/3 | 2/2 | 1/0/5 | 1.67 |
