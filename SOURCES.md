# Sources ledger - Germany (DE)

See `eu-legal-mcp/PLAYBOOK.md` section 8 and `eu-legal-mcp/template/SOURCES.template.md` for the
process this file supports.

| LDH id | LDH name | Our status | Our tool(s) | Notes / rejection reason |
|---|---|---|---|---|
| DE/NeuRIS | Federal legislation (beta) | shipped | `de_search`, `de_get_act`, `de_get_text`, `de_list_publishers`, `de_recent_changes` | original build. KNOWN LIMITATION: `testphase.rechtsinformationen.bund.de` is officially beta/incomplete - live total only ~2 417 acts. Not a bug, a documented gap in the upstream source itself. |
| DE/BVerfG | Federal Constitutional Court | shipped | `de_rii_case_search`, `de_rii_get_case_text` | 2026-07-07, commit ce5b823. Via `rechtsprechung-im-internet.de` (RII) master TOC, ~5 718 decisions live, native ECLI where the court publishes one |
| DE/BGH | Federal Court of Justice | shipped | same RII tools, `Gericht=BGH` filter | 2026-07-07, ~34 787 decisions |
| DE/BAG | Federal Labor Court | shipped | same RII tools, `Gericht=BAG` | 2026-07-07, ~7 233 decisions |
| DE/BFH | Federal Finance Court | shipped | same RII tools, `Gericht=BFH` | 2026-07-07, ~11 613 decisions |
| DE/BVerwG | Federal Administrative Court | shipped | same RII tools, `Gericht=BVerwG` | 2026-07-07, ~10 287 decisions |
| DE/BSG | Federal Social Court | shipped | same RII tools, `Gericht=BSG` | 2026-07-07, ~6 380 decisions |
| DE/BPatG (bonus, not originally requested) | Federal Patent Court | shipped | same RII tools, `Gericht=BPatG` | 2026-07-07, ~7 293 decisions - RII's TOC covers it too, shipped for free alongside the other 6 |
| DE Landesrecht (16 states) | various | todo | - | not yet evaluated, most flagged `duplicate_of_existing_source`/`javascript_spa` by LDH itself - low expected ROI |
| DE/BaFin | Financial Supervisory Authority | todo | - | LDH flags `infrastructure_blocked` for its own crawler; unverified by us |

Last updated: 2026-07-07 (widen round, see `eu-legal-mcp/AUDIT-LOG.md`). Total RII coverage across
the 7 courts above: ~83 300 decisions from one shared client/master-TOC (do not split into 7
separate clients - the upstream already unifies them).
