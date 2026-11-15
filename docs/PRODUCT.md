# Filing Lens — Product Specification

What the product is, who it is for, and what it does and does not do. The technical
design is in [SPEC.md](../SPEC.md); current progress is in [STATUS.md](STATUS.md).

## 1. One-paragraph summary

Filing Lens tells you what changed in a public company's annual report (SEC Form 10-K)
since last year, and answers questions about filings across years with a link to the
exact paragraph. One engine aligns consecutive filings paragraph by paragraph; that
alignment drives the change alerts, a time-aware retrieval index, and a research
signal that can be tested against stock returns.

## 2. Who it is for

- **Primary user:** the author, as an individual investor who wants to know what is new
  in the filings of companies on a watchlist without reading 100+ pages each.
- **Secondary audience:** recruiters and interviewers for software-engineering and
  AI-engineering internships (and, as a bonus, bank technology and quant roles). The
  project replaces course projects on the author's resume, so every claim must be
  measured and defensible in an interview.

The author currently has no real holdings. `holdings.sample.toml` is a sample watchlist
used for development and demos.

## 3. The problem

A 10-K is long and mostly identical to the previous year's. The informative part is
what changed: a new risk factor, a removed one, a reworded disclosure, a number that
moved. Published research ("Lazy Prices", Cohen, Malloy and Nguyen, 2020) argues that
investors under-react to these changes. Reading for changes by hand is slow, and a
plain text diff shows every edit, including boilerplate and routine number updates.

## 4. What the user can do

| # | Capability | Slice | Example |
|---|---|---|---|
| F1 | **Change alerts.** Add tickers; for each new 10-K, get a short ranked list of substantive changes, each with old text, new text, a word-level diff and a link to the filing. | 1 | "Item 1A: new risk factor on export controls." |
| F2 | **Numeric change flags.** Material moves in numbers inside narrative text. | 1 | "One customer: 10% of revenue → 35%." |
| F3 | **Backfill.** Run the same analysis over past years for any ticker, so the tool is useful outside filing season. | 1 | `fl backfill --ticker JPM --years 5` |
| F4 | **Cited question answering.** Ask about a company's filings; every claim links to a paragraph or a reported figure; unsupported claims are dropped or flagged. | 2 | "What did Boeing say about supplier quality in fiscal 2023?" |
| F5 | **Questions across time.** The answer walks a paragraph's history year by year instead of hoping search finds the right years. | 2 | "How has JPMorgan's commercial real estate exposure changed since 2021?" |
| F6 | **Exact figures.** Numeric questions are answered from the SEC's structured XBRL data and computed in code, not by the language model. | 2 | "What was Costco's operating margin in fiscal 2022?" |
| F7 | **Paragraph history view.** See one paragraph across all the years it existed. | 2 | — |
| F8 | **Research results.** Whether large filing changes predict lower returns, tested point-in-time. | 3 | See §7 for what can be claimed. |

Interfaces: a command-line tool (`fl`) in slice 1; a web app and a thin MCP server in
slice 2.

## 5. What makes it different

- **Versus "chat with a 10-K" tools:** those index each filing as a separate pile of
  text. Over several years the same paragraph is indexed several times, retrieval
  returns near-duplicates, and the model mixes up years. Filing Lens aligns filings
  first, stores each paragraph once with the years it was valid, and retrieves by time.
- **Versus a text diff:** a diff shows every edit. Filing Lens filters out formatting,
  boilerplate adopted by many companies that year, and routine number roll-forwards,
  then ranks what is left.
- **Versus commercial platforms** (for example AlphaSense offers filing comparison):
  the idea of comparing filings is not new. What is new here is an open implementation
  whose every stage is measured against hand-labelled data, with the results —
  including what did not help — published.
- **One signal, three uses:** the same alignment drives the alerts, the retrieval index
  and the research signal.

## 6. How we know it works

Every headline number comes from a recorded, reproducible run (details in SPEC §6.5,
§7.7, §9, §11).

| Claim | Measured by |
|---|---|
| The aligner matches paragraphs correctly | Precision and recall on changed paragraphs against 30 hand-aligned filing pairs, versus a standard diff |
| Alerts are worth reading | Precision of shown alerts on companies the classifier never trained on |
| The versioned index helps | A step-by-step ablation on FinanceBench (150 questions) and a custom 60-question set |
| Answers are grounded | Share of claims that pass verification against their cited source |
| The automated judge is trustworthy | Agreement with the author's own labels |
| The backtest engine is correct | Recovers a planted effect in synthetic data; fails loudly on look-ahead |

A component that does not improve its measured result is removed and the removal is
reported.

## 7. Restrictions and limitations (current)

**Scope**

- Annual reports (10-K, 10-K405) only. Quarterly reports (10-Q), 8-Ks, earnings
  releases and Canadian 40-F filers are not supported yet.
- US filers on SEC EDGAR only.
- Section-level analysis needs the section to exist and parse in both years. Risk
  Factors (Item 1A) only exists for fiscal years ending on or after December 1, 2005.
- Filings that fail to parse are excluded and counted, never guessed at.
- Hand-aligned evaluation covers Items 1A and 7 only.
- The alert classifier is trained by a single annotator on a few hundred labels.

**Cost**

- $0 running cost. Language models are free-tier or local, which limits answer quality
  and imposes rate limits. The public demo will have daily query caps.
- The hosted database is a free plan (1 GB storage shown at signup), so only the
  40–60 company question-answering universe is hosted. Everything heavy runs offline
  on the author's laptop.

**Data and licensing**

- CRSP price data (through WRDS) is **not available yet**. The author's undergraduate
  account includes CRSP, but access is not approved and accounts are blocked between
  terms.
- Until CRSP data is in hand, the research claim is limited to: *the change signal and
  a point-in-time backtest framework were built and validated; the return effect was
  not tested.* Returns computed on free price data are never reported, because free
  data omits delisted companies, which biases exactly the effect being tested.
- CRSP data and the company-to-security link table may never be committed, deployed,
  displayed, or shown to any language model or AI coding session.
- FinanceBench is non-commercial; it is downloaded by script, not committed.
- The project is academic and non-commercial. If that changes, the CRSP component is
  removed.

**Privacy**

- Free model providers may train on prompts. Only public filing text goes to them.
  Requests that reveal the watchlist go only to a provider that does not train on API
  data, or to a local model.
- Secrets live in `.env`, which is never committed and never read aloud by an agent.

**Not a financial product**

- No buy or sell recommendations, no trading, no personalised advice. Backtest output
  is research.

## 8. Explicit non-goals

Agent frameworks (LangGraph and similar), a knowledge graph built by a language model,
fine-tuning, multi-agent report writing, price prediction, and a provider-routing layer
as a feature. These were considered and rejected for cost, scope, or because they add
keywords without depth (SPEC §16).

## 9. Delivery order

Each slice stands alone on a resume.

| Slice | Delivers | Estimate |
|---|---|---|
| 0 | Project skeleton, local database, CI | ~2 days |
| 1 | Ingestion, parsing, alignment engine, alignment evaluation, change alerts (F1–F3) | ~3–4 weeks |
| 2 | Versioned index, question answering, ablation study, web app, MCP server (F4–F7) | ~4 weeks |
| 3 | Change signal at scale, backtest engine, write-up (F8); CRSP when available | ~2–3 weeks |

Internship applications for summer 2027 are open now, so slice 1 is the priority: it is
the first point at which the project can go on the resume.
