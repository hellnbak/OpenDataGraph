# Demo and Screenshot Guide

## Recommended flow

1. Start the application and open the dashboard at 1440px or wider.
2. Capture the top section showing the value statement, four KPIs, sensitivity distribution, and lifecycle intelligence.
3. Capture the inventory table with the restricted customer export and aging legal document visible.
4. Open `customer_export_2023.csv` to show explainable classification, data age, stale score, and the priority retention review.
5. In **Test an AI access decision**, select that asset and choose **External AI**. Capture the deny decision and required controls.
6. Evaluate a lower-risk asset against **Internal RAG** to show a conditional or allow response.
7. Open `/docs` and capture the API surface for a technical audience.
8. Show the tenant identifier, background-job count, evidence count, and search backend in the summary response.

## Suggested captions

- “A unified, AI-consumable view of enterprise data risk and lifecycle.”
- “Every classification and policy decision is explainable.”
- “Every runtime permit or deny produces a durable receipt, and external signing happens after the hot path.”
- “Expected model, vector-index, tool, and endpoint relationships make new runtime paths visible as drift.”
- “Sensitive stale data becomes an actionable lifecycle decision—not another inventory count.”
- “AI gateways query context before allowing enterprise data to leave a trust boundary.”

## Demo caveats

State clearly that Enterprise Demo Mode uses synthetic records within the authenticated tenant and that lifecycle actions are recommendations only. Live connector scans are separate from generated demo data. Do not imply that last-access evidence exists for every storage provider.
