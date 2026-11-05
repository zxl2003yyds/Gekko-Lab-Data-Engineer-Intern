# Independent reviewer instructions

This rubric contains no answers to the review cases. Give the reviewer this file and their own `reviewer_a_annotations.json` (or B) only. Do not include the casebook, translations, coordinator snapshot, previous labels, or automated predictions in phase one.

## Eligibility and scope

The reviewer must be a real person who can read Portuguese and English and did not implement the extractor or write the draft labels/translations. Fill in `attestation` truthfully. A reviewer ID may be a pseudonym; the project coordinator should know who it represents. Software checks declarations and file consistency, not a person's identity or independence.

Review every row marked `primary_30=true`; these 30 cases were selected before review. Reviewing all 60 is encouraged. Do not replace difficult cases with easier ones. Do not edit task IDs, source text, hashes, or selection flags. There is no required agreement rate and no penalty for disagreeing with the draft.

## Phase one: label the Portuguese source only

Use only what the source says. It is the buyer's report, not verified evidence of liability. Keep complaints separate from remedies, hypothetical events, and positive statements. Do not infer missing dates, product details, causes, or financial loss. Record unresolved ambiguity in `notes`; an uncertain case still requires your best evidence-supported labels.

One review may receive several categories, with at most one entry per category. Every issue needs `category`, `severity`, and an exact, nonempty Portuguese `evidence_quote` copied from the source. Choose a span long enough to preserve relevant negation and conditions; the whole review is allowed.

| Category | Definition |
| --- | --- |
| `delivery_late` | Explicitly late, missed delivery deadline, or a complaint that delivery is too slow. Nonreceipt alone does not prove lateness. Do not compare a historical expected date with today's date. |
| `wrong_product` | The received item, model, colour, material, or specification differs from what was ordered or advertised. Disappointment or inferior quality alone is not enough. |
| `quality_defect` | Reported damage, malfunction, poor construction/material, or low quality. A personal preference without a quality complaint is not a defect. |
| `missing_item` | All or part of the ordered goods have not been received, including missing accessories. In this project this category includes complete nonreceipt; it does not imply confirmed loss or lateness. A refund, invoice, or reply is not a physical ordered item. |
| `seller_communication` | Explicit unanswered contact, absent promised updates, or an actual communication failure. Merely requesting contact or awaiting an initial reply does not by itself establish failure. |
| `packaging` | A stated defect in wrapping, protection, or the package itself. Packaging mentioned only as evidence of a different complaint is not automatically a packaging defect. |
| `other` | A reported complaint outside these categories, including billing/receipt, refund, return, collection burden, misleading advertising without proven wrong goods, or nonspecific dissatisfaction. A neutral question or positive review alone is not a complaint. |

Severity is an operational label, not a financial-loss estimate. Use `high` for missing ordered goods or explicit inability to use the item; `medium` for other concrete product, fulfilment, service, or payment complaints; `low` for nonspecific dissatisfaction with no stated concrete harm. Damage without clear loss of use may be `medium`; explain borderline decisions in `notes`.

Set `sentiment_label` to `positive`, `negative`, `mixed` (both positive and negative), or `unknown` (neutral or insufficient evidence). Set `actionable_for_seller` to a boolean: `true` when a concrete issue or request allows the seller to investigate, answer, arrange return/exchange, or otherwise follow up; `false` for positive feedback or vague dissatisfaction with no concrete issue/request. This does not assign fault to the seller.

`issues=null` means **not reviewed**. After reviewing a case with no supported complaint, set `issues=[]` and still complete sentiment and actionability. Preserve your first-stage answers once phase two has been generated; discuss disagreements separately rather than retroactively aligning your labels with the draft.

## Phase two: inspect the full English translation

The coordinator seals your phase-one file and generates a translation packet for those cases. Inspect the complete Portuguese source and English translation. Additional product context, if present, is explicitly marked and is allowed only to clarify a word, not to invent a complaint.

For every row fill `verdict`:

- `faithful`: meaning, scope, and relevant details are preserved. Natural English and correction of an obvious source typo are allowed if no unsupported fact is added.
- `minor_error`: a local wording or grammar error that does not change the core claim, condition, requested remedy, entity, or decision.
- `major_error`: a meaning-changing error, including wrong negation, time relation, quantity, model, speaker, condition, or material omission/addition.

Fill `error_types` with zero or more of `negation`, `time`, `quantity`, `entity`, `subject`, `modality`, `omission`, `addition`, `word_choice`, `grammar`. For `faithful`, use `[]`. For either error verdict, provide at least one type and a complete replacement in `corrected_translation`. Do not overwrite `source_text` or `translation_en`. Use `notes` for uncertainty and your reasoning.

The report will show semantic disagreements and translation errors separately. Acceptance applies only to reviewed cases when no listed discrepancy remains. An optional second reviewer works independently under the same rubric; disagreements require human discussion and a recorded decision, not automatic majority voting. These previously inspected cases cannot measure performance on unseen texts.
