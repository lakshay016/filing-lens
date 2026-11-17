# Fixture filings

Public SEC 10-K primary documents (Apple, CIK 320193; Exxon Mobil, CIK 34088), stored
zstd-compressed at level 19. Load with `load_fixture("aapl-fy2023")` from `load.py`.

Produced by `scripts/make_fixtures.py` (run once on 2026-11-17; downloads through
`EdgarClient`, locates each filing with `fetch_filing_list`). Tests never import that
script and never touch the network.

| File | Accession | Primary document | Period | Uncompressed | Compressed | SHA-256 of the uncompressed document |
|---|---|---|---|---|---|---|
| `aapl-fy2022.htm.zst` | 0000320193-22-000108 | `aapl-20220924.htm` | 2022-09-24 | 2,049,969 B | 119,582 B | `5f8c5086f8618b29aa35c04acb5e712aa4872c8e0e51502cac94e8d6e779f287` |
| `aapl-fy2023.htm.zst` | 0000320193-23-000106 | `aapl-20230930.htm` | 2023-09-30 | 1,559,036 B | 75,992 B | `e3c661822fef81d6098cc0befd78df2a81a250a7afd9f76bfffed6a3b1cd3190` |
| `xom-fy2022.htm.zst` | 0000034088-23-000020 | `xom-20221231.htm` | 2022-12-31 | 6,699,312 B | 262,217 B | `e77e31e9e87420396a5e0e18343458447b470fbeff29e613ede262818fc5ff7d` |
| `xom-fy2023.htm.zst` | 0000034088-24-000018 | `xom-20231231.htm` | 2023-12-31 | 5,654,100 B | 179,101 B | `65ebfcd3f6b49bc7cf6867d5913c27efeb15be2ae4c94ff63497b57d05e26604` |

Note: neither Exxon filing has a combined "Items 1 and 2" heading (SPEC §16 expected
one for energy filers); Items 1 and 2 are separate headings in both.
