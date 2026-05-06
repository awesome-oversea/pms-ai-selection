# Screenshot Guide

## Purpose

Screenshots should prove business value quickly. Do not spend time screenshotting monitoring dashboards unless a viewer specifically asks about engineering operations.

Recommended output folder:

`docs/github/screenshots`

## Required Screenshots

| File | Page | What To Show |
| --- | --- | --- |
| `01-home-blueprint.png` | `/` | Unified workbench entry and product positioning |
| `02-selection-workbench.png` | `/workbench/selection` | Task metrics, real-time signal area and create task form |
| `03-ai-decision.png` | `/workbench/selection` | GO / NO-GO result, recommendation, risk and ROI |
| `04-approval-chain.png` | `/approval` or `/manager` | Operator, procurement and manager approval stages |
| `05-procurement-execution.png` | `/procurement` | Supplier, purchase order, WMS reservation and OMS listing draft |
| `06-profit-feedback.png` | `/finance` or `/dashboard` | Profit, margin, sales feedback and rescore |
| `07-report-center.png` | `/reports` | Report generation, archive and sharing view |
| `08-public-signal-gdelt.png` | `/trends` or evidence view | Public event/news signal and business interpretation |
| `09-acceptance-evidence.png` | Markdown preview | Acceptance evidence summary |

## Optional GIF

Create one short GIF:

- Filename: `demo-business-loop.gif`.
- Length: 20-35 seconds.
- Flow: home -> selection workbench -> approval -> procurement -> finance -> report.
- Goal: show the closed loop, not every field.

## Visual Quality Notes

- Use one polished theme for the first public release.
- Multi-color theme screenshots are optional and should not replace business-flow screenshots.
- Crop browser chrome if it distracts, but keep enough context to show the page route or product name.
- Avoid screenshots containing `.env`, tokens, local secrets, private supplier terms or raw logs.

## Caption Template

Use concise captions in the GitHub README:

- `Unified workbench entry for operator, manager, procurement, finance and analyst roles.`
- `AI selection task with GO / NO-GO decision, trend signal and risk summary.`
- `Human approval chain keeps business control over AI recommendations.`
- `Adopted recommendation triggers local SCM / WMS / OMS execution.`
- `Sales, review, profit and inventory feedback rescore the recommendation.`

## Business Storyboard

The screenshots should answer five questions:

1. What business problem does this solve?
2. Who uses it?
3. What does AI decide?
4. How do humans approve and execute it?
5. How does the system know whether the decision made money?
