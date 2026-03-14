# Re-Assessment with Metric Overrides

## What Re-Assessment Does

When a user asks to re-score an applicant with changed values ("what if revenue was 500K?"),
the `re_assessment` intent routes through a short, targeted path that (1) extracts the
user-stated metric values, (2) loads the applicant's full feature set from the database, and
(3) merges the user values on top before running the credit-scoring pipeline.
This avoids repeating the planning and tool-execution phases that are only needed for
first-time assessments, and ensures user overrides are not silently discarded.

---

## How to Trigger It

Any of the following prompt patterns will classify as `re_assessment`:

```
Re-assess applicant #285000 with revenue=500K and margin=18%
What if applicant #270000 had annual income of 800K?
Recalculate the score assuming AMT_CREDIT=200000
Reassess this applicant with debt-to-equity=2.5
What would the score be if #300000 had 3 years employment instead of 1?
Scenario where profit margin is 22% — re-run the score
```

**Key signals the classifier looks for:**
- An applicant reference (ID number or sidebar selection)
- What-if / change language: `re-assess`, `reassess`, `what if`, `assuming`, `suppose`,
  `scenario where`, `recalculate`, `update the score`, `change X to Y`, `if X was`

If only an applicant ID is given with no changed values, the classifier uses `full_assessment`.

---

## Metric Name Mapping

The LLM maps plain-language terms to Home Credit column names automatically.
You can also use the column names directly.

| User language | Home Credit column | Notes |
|---|---|---|
| annual income, revenue, yearly income | `AMT_INCOME_TOTAL` | strip currency symbols |
| loan amount, credit amount | `AMT_CREDIT` | |
| monthly payment, annuity | `AMT_ANNUITY` | |
| age (years) | `DAYS_BIRTH` | converted: `years × −365.25` |
| years employed | `DAYS_EMPLOYED` | converted: `years × −365.25` |
| profit margin | `profit_margin` | snake_case, ignored by XGBoost |
| debt-to-equity | `debt_to_equity` | snake_case, ignored by XGBoost |

**Value conversion rules:**
- `500K` → `500000`, `1.2M` → `1200000`, `300M` → `300000000`
- `18%` → `0.18` (stored as decimal)
- Age and employment years are negated automatically

---

## How Overrides Work (Flow)

```
User message
    │
    ▼
classify  ──[re_assessment]──▶  metric_extraction
                                     │  LLM parses explicit values
                                     │  → user_metric_overrides = {"AMT_INCOME_TOTAL": 500000}
                                     ▼
                               data_completeness
                                     │  loads all features from DB for applicant #ID
                                     │  merges overrides:
                                     │    extracted_features["AMT_INCOME_TOTAL"] = 500000
                                     ▼
                         route_after_data_completeness_v2
                               intent == re_assessment
                                     │  skip planning & tools
                                     ▼
                               credit_scoring
                               explainability
                               fairness_check
                         counterfactual_generation  (if rejected)
                               analysis → response → END

SKIPPED: fetch_merchant_data, document_ingestion, planning,
         tool_selection, execute_tools
```

Backend log lines to confirm it worked:

```
🎯 Query classified as: re_assessment
📐 Extracting user metric overrides from message...
   Extracted 2 metric override(s): ['AMT_INCOME_TOTAL', 'profit_margin']
   Applying 2 user override(s):
      AMT_INCOME_TOTAL: 240000.0 → 500000
      profit_margin: <new> → 0.18
Re-assessment intent — routing directly to credit_scoring (skipping planning/tools)
```

---

## Edge Cases / Notes

| Scenario | Behaviour |
|---|---|
| No metrics extracted from message | `user_metric_overrides = {}` — dataset values used unchanged; valid no-op re-score |
| Unknown key (e.g. `profit_margin`) | Added to `extracted_fields`; silently ignored by XGBoost feature selection |
| Applicant ID not in database | `data_completeness_node` sets `route_to = incomplete` → routed to `need_more_data` |
| LLM structured-output call fails | `metric_extraction_node` fails open → `user_metric_overrides = {}` |
| Sidebar selection, no ID in message | `classify_node` prepends `[Applicant #ID selected]`; classifier still detects re_assessment |
| What-if question with no applicant ID | Classified as `re_assessment`; DB lookup fails → `need_more_data` asks for an ID |
| Percentage stated as decimal already | Both `0.18` and `18%` produce the same stored value `0.18` |