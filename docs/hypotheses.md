# Business Hypotheses & Empirical Validation

This document structures the transit analytics project around 5 explicit, hypothesis-driven problem statements. Each hypothesis tests a specific operational question on the scheduled bus supply in Chennai, defines the empirical methodology, and reports the quantitative verdict based on GTFS data.

---

## Hypothesis Framework Overview

| ID | Business Hypothesis | Target Area | Analytical Method | Empirical Verdict |
| :--- | :--- | :--- | :--- | :---: |
| **H1** | Super-Hub Transfer Concentration | Spatial Network Design | Degree centrality & Pareto connection share (Query 2) | **SUPPORTED** |
| **H2** | Rush-Hour Compression & Off-Peak Starvation | Temporal Service Allocation | Hourly departure binning & headway ratios (Query 3) | **SUPPORTED** |
| **H3** | Weekend Commuter Accessibility Deserts | Service Span & Equity | Calendar schedule analysis & `BOOL_OR` aggregation (Query 6) | **SUPPORTED** |
| **H4** | Rigid Inelasticity in Corridor Allocation | Fleet Allocation Efficiency | Trip distribution vs. transfer exposure (Queries 1, 4, 7) | **SUPPORTED** |
| **H5** | Festival Surge Capacity Exceedance | Contingency Operations | Multiplier-based surge projections (Query 5 & Scenarios) | **SUPPORTED** *(Assumption-Conditional)* |

---

## Detailed Hypothesis Analysis

### Hypothesis 1: Super-Hub Transfer Concentration
> **Hypothesis Statement:**  
> A small minority of transit stations acts as super-interchanges carrying an outsized share of multi-route transfers, creating single points of failure for delay propagation and station overcrowding.

- **Analytical Test:**  
  Evaluated unique intersecting bus routes and daily trips handled across all 150 stops in the network ([`sql/analysis.sql` Query 2](file:///Users/rahularakeri/Public%20Transit%20Intelligence%20Platform/sql/analysis.sql#L37-L77)).
- **Empirical Findings:**
  - Network contains **1,000 total route-stop intersection instances** across 147 active stops.
  - The **Top 10 transfer hubs carry 112 route connections (11.2% of network total)**, despite representing only **6.8% of active stops** (10 of 147).
  - Top 3 hubs: **Nungambakkam (13 intersecting lines)**, **Washermanpet (12 lines)**, and **ECR (12 lines)**.
- **Verdict:** **SUPPORTED**
- **Strategic Implication:**  
  These 10 hubs represent systemic operational bottlenecks. Platform infrastructure investments, dedicated bus priority bays, and real-time dispatch monitoring should be targeted at these 10 interchanges.

---

### Hypothesis 2: Rush-Hour Compression & Off-Peak Starvation
> **Hypothesis Statement:**  
> Scheduled vehicle journeys are disproportionately concentrated during morning and evening rush hours, leaving midday and late-evening travelers with severe headway penalties.

- **Analytical Test:**  
  Classified all 500 daily departures by initial trip departure hour into Morning Peak (07:00–10:00), Evening Peak (17:00–20:00), and Off-Peak intervals ([`sql/analysis.sql` Query 3](file:///Users/rahularakeri/Public%20Transit%20Intelligence%20Platform/sql/analysis.sql#L81-L125)).
- **Empirical Findings:**
  - **68.2% of scheduled daily trips (341 of 500)** operate within just 6 peak hours (Morning: 168 trips [33.6%], Evening: 173 trips [34.6%]).
  - Network peak departure rate is **56.8 trips/hour**, collapsing to **8.8 trips/hour off-peak**—a **6.5× frequency drop**.
  - **82.0% of corridors (41 routes)** experience average off-peak headways of **$\ge 270$ minutes ($4.5$ hours)**.
- **Verdict:** **SUPPORTED**
- **Strategic Implication:**  
  Commuter peak demand is prioritized at the expense of base service reliability. Midday supply starvation suppresses non-work trips (healthcare, education, retail), making transit unviable for non-peak riders.

---

### Hypothesis 3: Weekend Commuter Accessibility Deserts
> **Hypothesis Statement:**  
> A material share of the route network operates strictly on weekdays, cutting off peripheral and express suburban transit access on Saturdays and Sundays.

- **Analytical Test:**  
  Aggregated day-of-week service profiles across the calendar table using `BOOL_OR(saturday)` and `BOOL_OR(sunday)` ([`sql/analysis.sql` Query 6](file:///Users/rahularakeri/Public%20Transit%20Intelligence%20Platform/sql/analysis.sql#L198-L232)).
- **Empirical Findings:**
  - Exactly **16.0% of routes (8 of 50 corridors)** shut down completely on weekends (`c_weekday` service profile).
  - Affected lines include express corridors: **500A, E1, E2, E3, E4, E5, M70, and M79**.
- **Verdict:** **SUPPORTED**
- **Strategic Implication:**  
  Suburban shift workers and weekend travelers along these 8 corridors have zero direct transit service, forcing modal shift to private two-wheelers or informal autos.

---

### Hypothesis 4: Rigid Inelasticity in Corridor Allocation
> **Hypothesis Statement:**  
> Vehicle service allocation is uniformly distributed across routes without adjusting for corridor length, network connectivity, or transfer importance.

- **Analytical Test:**  
  Cross-referenced route transfer connectivity against scheduled daily trip volume ([`src/scoring.py`](file:///Users/rahularakeri/Public%20Transit%20Intelligence%20Platform/src/scoring.py#L42-L115)).
- **Empirical Findings:**
  - Network connectivity varies by **2.6×**: the most integrated routes connect to **18 distinct corridors** (Routes 2A, 58, E5), while isolated routes connect to only **7 corridors**.
  - Despite this 2.6× differential, **every single route in the dataset is allocated exactly 10 daily trips** (144.0 min baseline average headway).
- **Verdict:** **SUPPORTED**
- **Strategic Implication:**  
  The current schedule reflects flat, legacy supply allocation rather than network-optimized scheduling. High-transfer trunk lines are under-supplied relative to their network connectivity value.

---

### Hypothesis 5: Festival Surge Capacity Exceedance
> **Hypothesis Statement:**  
> Cultural and regional festival travel surges generate supplemental vehicle requirements that substantially exceed standard depot maintenance spare vehicle reserves.

- **Analytical Test:**  
  Evaluated supplemental fleet requirements across 15 major Indian festivals across Low, Base, and High demand scenarios ([`src/ingestion/load_festivals.py`](file:///Users/rahularakeri/Public%20Transit%20Intelligence%20Platform/src/ingestion/load_festivals.py#L107-L157)).
- **Empirical Findings:**
  - Across 15 festive events, supplemental trip requirements range from:
    - **Low Scenario (+20% to +80%):** +100 to +400 extra trips (mean: +240 trips)
    - **Base Scenario (+40% to +150%):** +200 to +750 extra trips (mean: +460 trips)
    - **High Scenario (+60% to +200%):** +300 to +1,000 extra trips (mean: +620 trips)
  - For top events like **Diwali (2.5× multiplier in Base)**, the required **+750 extra vehicle runs** represent a 150% expansion of normal daily service.
- **Verdict:** **SUPPORTED (Conditional on demand surge assumptions)**
- **Strategic Implication:**  
  Standard 10–15% maintenance float is inadequate for major holiday surges. Transit authorities must implement dedicated contingency rosters: temporary maintenance deferrals, depot reserve mobilization, and inter-depot fleet staging at Koyambedu (CMBT) and Tambaram.
