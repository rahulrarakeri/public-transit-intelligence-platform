# Bain & Company / Consulting Interview Preparation Pack

This document prepares you for technical and behavioral interviews for the **Bain & Company BCN Intern Analyst** role. It bridges software engineering with management consulting: leading with business judgment, defending assumptions, quantifying trade-offs, and acknowledging data limitations.

---

## 1. The 2-Minute Project Pitch (Elevator Pitch)

> **Context & Problem:**  
> "Transit authorities in major metros like Chennai face severe network congestion and service dissatisfaction, yet decisions to allocate fleet and modify schedules are often made on legacy intuition rather than empirical data. I built the Public Transit Intelligence Platform to evaluate scheduled bus supply across 50 corridors and 150 stations using General Transit Feed Specification (GTFS) data in PostgreSQL and Python."
>
> **Methodology:**  
> "I approached this from a supply-side optimization lens: I developed 8 analytical SQL pipelines to evaluate headway compression, network transfer exposure, and day-of-week coverage. To prioritize corridors for timetable review, I designed a multi-criteria scoring model with Min-Max normalization and stress-tested its stability using a 500-iteration Monte Carlo sensitivity simulation."
>
> **Headline Findings:**  
> "Three major findings stood out:  
> First, **68.2% of all scheduled trips are compressed into 6 rush hours**, causing a **6.5× frequency drop off-peak** where 82% of routes face 4.5+ hour off-peak gaps.  
> Second, **network vulnerability is highly concentrated**: the top 10 interchange hubs carry **11.2% of all route transfer connections** across just **6.8% of stops**.  
> Third, **16.0% of corridors shut down completely on weekends**, stranding suburban commuters."
>
> **Recommendations & Impact:**  
> "Rather than requesting capital-intensive new bus purchases, I recommended a supply-neutral rescheduling strategy: shaving 10–15% of peak fleet padding to smooth midday headways below 45 minutes on trunk lines, and deploying skeleton weekend rosters on the 8 discontinued commuter lines."
>
> **Data Boundaries & Honesty:**  
> "Crucially, GTFS data represents planned supply, not realized passenger demand. Without automated fare collection (AFC) or GPS traces, I framed these not as definitive deficits, but as prioritized candidates for operational review."

---

## 2. Three Verified Resume Bullets (Numbers-Grounded)

Use these directly on your resume. Every metric is 100% computed from the GTFS dataset:

- **Option A (Analytics & SQL Heavy):**  
  > *Built an end-to-end transit analytics platform in Python & PostgreSQL analyzing 500 trips across 150 stops; uncovered that 68.2% of departures are compressed into 6 rush hours (6.5× off-peak drop) and 10 super-hubs concentrate 11.2% of all network transfers across 6.8% of stations.*

- **Option B (Modeling & Sensitivity Heavy):**  
  > *Designed a multi-criteria Route Prioritization Index (RSGPI) synthesizing transfer connectivity, off-peak headways, and weekend gaps; proved 99.4% Top-10 ranking stability across a 500-iteration Monte Carlo sensitivity analysis (Spearman $\rho = 0.994$).*

- **Option C (Operations & Strategic Consulting Heavy):**  
  > *Formulated supply-side optimization strategies for Chennai metropolitan bus network; identified 8 weekday-only corridors (16% of network) for weekend activation and modeled 3 scenario stress-tests projecting up to +1,000 supplemental holiday vehicle runs.*

---

## 3. Ten Tough Interviewer Pushback Questions & Model Answers

### Q1: "Why did you choose weights of 35% connectivity, 35% headway, 15% weekend gap, and 15% stop count?"
> **Answer:**  
> "In transit operations, network efficiency is driven primarily by two forces: passenger transfer liquidity (connectivity) and service availability (headway). I gave equal primary weight (35% each) to connectivity and off-peak headway because an unserved gap on an arterial corridor with 18 connections causes exponentially higher network friction than on an isolated feeder line.  
> However, because weights reflect business judgment, I did not rely on them blindly. I ran a **500-iteration Monte Carlo sensitivity test perturbing weights by $\pm 20\%$**. The ranking demonstrated a **mean Spearman rank correlation of 0.994** and **99.4% Top-10 set stability**, proving the priority list is robust to subjective weight shifts."

---

### Q2: "How can you claim an off-peak route is 'underserved' when you don't have passenger demand data?"
> **Answer:**  
> "That is a critical distinction, and I strictly enforce it in my project. GTFS is pure planned supply data. I never claim a route *needs* more buses.  
> What the data *does* prove empirically is supply-side temporal distortion: 82% of routes run headways exceeding 4.5 hours off-peak. Even if passenger demand is lower midday, a 5-hour wait time effectively eliminates transit as a viable option for non-office commuters, healthcare workers, and students. I frame these routes as **candidates for schedule review**, not confirmed demand shortages."

---

### Q3: "Where did your festival multipliers come from, and how would you validate them?"
> **Answer:**  
> "The multipliers (1.4× to 2.5× in Base) are explicit analytical assumptions grounded in observed regional holiday mobility in Tamil Nadu (e.g., massive interstate bus surges at CMBT during Pongal and Diwali). In my code and configs, they are explicitly tagged as `ASSUMPTION - not derived from ridership data`.  
> To empirically validate them, I would pull 12 months of **Electronic Ticketing Machine (ETM) transaction logs** or **Automated Fare Collection (AFC) smart-card taps** from the transit authority, compare holiday boarding volume against pre-festival 4-week moving averages for the same day-of-week, and derive empirically calibrated surge coefficients per corridor."

---

### Q4: "What happens to your analysis when buses get stuck in traffic and bunch together in real life?"
> **Answer:**  
> "Static GTFS assumes buses run precisely at timetable intervals. In real-world operations, traffic congestion causes bus bunching—where two buses arrive back-to-back followed by a 45-minute gap.  
> To capture this, the next phase of this project would integrate **GTFS-Realtime (GTFS-RT)** vehicle position telemetry. By calculating the coefficient of variation in real-time headway arrivals, we could identify corridors suffering from high schedule variance and recommend transit signal priority (TSP) or dedicated bus lanes."

---

### Q5: "Why did you use Min-Max normalization instead of Z-scores or Percentile Ranks?"
> **Answer:**  
> "Percentile rank was what the project initially used, but it is purely rank-based—it discards the relative scale of differences between values and treats ties artificially. Z-score standardizes variance, but can produce negative numbers that make composite linear weighting unintuitive for business stakeholders.  
> Min-Max normalization bounds each metric strictly between 0 and 1, preserving the relative proportional distance between values while maintaining an intuitive 0–100 score scale where 100 represents the most severe cumulative service review priority."

---

### Q6: "In your dataset, every route runs exactly 10 trips per day. Why is that, and what does it tell you?"
> **Answer:**  
> "That was one of the most interesting findings from my data audit! In the provided GTFS feed, all 50 routes are allocated exactly 10 scheduled daily trips (144.0 min baseline average headway).  
> In consulting, when you see flat allocation across heterogeneous assets, it signals **supply-side rigidity**: schedules were likely created with legacy flat quotas rather than dynamic demand- or connectivity-driven allocation. Even though trip counts are uniform, **temporal distribution varies from 40% to 100% peak concentration** and **transfer exposure varies from 7 to 18 lines**. My analysis focused on where the variance actually exists."

---

### Q7: "How stable is your Route Prioritization Index? If the client disagrees with your weights, does the answer change?"
> **Answer:**  
> "The answer is remarkably stable. When varying weights by $\pm 20\%$ over 500 randomized runs, the **Top-10 candidate pool overlap is 99.4%** (never dropping below 90%). Even in an extreme scenario where we assign **equal 25% weights to all 4 metrics**, the Spearman rank correlation against baseline is **0.953**, and the Top-10 overlap is 90%.  
> This means our top candidates—such as Route 32, Route 17A, and Route 15—are priority targets regardless of whether leadership prioritizes connectivity or headway."

---

### Q8: "How would you fund your recommendation to expand weekend services on the 8 discontinued routes?"
> **Answer:**  
> "A core tenet of operational consulting is seeking **supply-neutral or revenue-accretive solutions** before requesting capital expenditure.  
> On weekdays, the network operates 500 trips. On weekends, 8 routes shut down completely, leaving depot vehicles idle. Reallocating a fraction of weekend maintenance reserves to run 3–4 round-trip skeleton runs per day (45–60 min headways) on these 8 arterial lines requires **zero new vehicle purchases**. By capturing previously unserved weekend retail and leisure commuters, the additional farebox revenue covers marginal fuel and driver overtime costs."

---

### Q9: "If top hubs carry only 11.2% of connections, is that really a high concentration?"
> **Answer:**  
> "Yes, from a network topology perspective. 10 stops represent only **6.8% of all 147 active stations** in Chennai. For 6.8% of nodes to capture 11.2% of all multi-route intersections represents significant concentration.  
> More importantly, individual hubs like **Nungambakkam connect to 13 distinct routes** and **Washermanpet connects to 12 routes**. If an arterial intersection at Nungambakkam is gridlocked, delays immediately propagate into 26% of the city's bus routes."

---

### Q10: "If Bain staffed you on this transit optimization engagement for 3 months, what would be your Phase 2 roadmap?"
> **Answer:**  
> "I would execute a three-phase sprint:  
> 1. **Weeks 1–4 (Demand Grounding):** Ingest 6 months of ETM farebox transaction data to replace our supply assumptions with true passenger load factor profiles and revenue per seat-kilometer.  
> 2. **Weeks 5–8 (Realized Reliability):** Integrate GPS automatic vehicle location (AVL) data to measure actual on-time performance (OTP) and identify congestion hotspots.  
> 3. **Weeks 9–12 (Optimization & Pilot):** Formulate a route rationalization plan using linear programming to minimize passenger wait time subject to fleet size constraints, and run a 4-week schedule pilot on the top 3 review corridors."

---

## 4. Five-Slide Executive Summary Presentation Outline

```text
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 1: EXECUTIVE CONTEXT & CORE PROBLEM                             │
│ Headline: Chennai Transit Supply Suffers from Legacy Scheduling        │
│           Rigidity and Extreme Off-Peak Temporal Concentration         │
│ • Context: Metropolitan bus network (50 routes, 150 stops, 500 trips).│
│ • Problem: Flat allocation quotas (10 trips/line) create severe       │
│   midday gaps (82% of routes >4.5h off-peak) and 8 weekend blindspots. │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 2: METHODOLOGY & ANALYTICAL RIGOR                               │
│ Headline: Hypothesis-Driven Analytics Powered by Relational SQL and    │
│           Monte Carlo Sensitivity Stress-Testing                       │
│ • 8 SQL pipelines testing 5 business hypotheses on GTFS schedule data. │
│ • Multi-criteria RSGPI score combining connectivity, headways & equity.│
│ • 500-run Monte Carlo simulation proving 99.4% Top-10 ranking stability│
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 3: KEY FINDINGS & BOTTLENECK DIAGNOSTICS                         │
│ Headline: 68.2% of Departures Compressed into 6 Hours; 10 Hubs Carry   │
│           11.2% of All Corridor Transfers                              │
│ • Finding 1: 6.5× frequency collapse between peak and off-peak hours.  │
│ • Finding 2: Super-hub concentration (Nungambakkam intersects 13 lines)│
│ • Finding 3: 16% of network shut down on weekends (express commuters). │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 4: STRATEGIC RECOMMENDATIONS & BUSINESS CASE                    │
│ Headline: Three Supply-Neutral Interventions to Unlock Transit Utility │
│           Without Capital Fleet Expenditure                            │
│ • Rec 1: Schedule Smoothing — shave 10% peak padding to ensure <=45m   │
│   midday intervals on Top-10 review corridors.                         │
│ • Rec 2: Weekend Activation — skeleton rosters on 8 weekday lines.     │
│ • Rec 3: Contingency Staging — holiday rosters for +200 to +750 runs. │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 5: RISKS, DATA LIMITATIONS & IMPLEMENTATION ROADMAP             │
│ Headline: Grounding Planned Supply with Empirical Ridership Telemetry  │
│ • Limitation: GTFS captures planned supply; lacks boarding/delay data. │
│ • Mitigation: Validate with Electronic Ticketing Machine (ETM) logs.   │
│ • 12-Week Roadmap: ETM ingestion -> AVL tracking -> 3-route pilot.     │
└────────────────────────────────────────────────────────────────────────┘
```
