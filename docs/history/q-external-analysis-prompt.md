# AURA — Independent Repository Discovery & Usage Analysis

Repository target:

**https://github.com/masrizram/aura**

Lakukan analisis mendalam terhadap repository tersebut secara **evidence-based**. Jangan hanya mengandalkan README, deskripsi GitHub, nama file, atau asumsi. Periksa struktur repository, source code, konfigurasi, dokumentasi, tests, CLI/scripts, workflow, dan artefak lain yang tersedia.

## TUJUAN UTAMA

Saya ingin mengetahui secara objektif:

1. **Sebenarnya AURA itu apa?**
2. **Masalah apa yang ingin diselesaikan oleh AURA?**
3. **Bagaimana arsitektur dan cara kerja internalnya?**
4. **Bagaimana cara menggunakan AURA dari nol?**
5. **Apa kelebihan dan keunikan AURA dibanding pendekatan audit software biasa?**
6. **Apa keterbatasan, kelemahan, dan risiko desainnya?**
7. **Siapa target pengguna yang paling cocok?**
8. **Apa use case nyata yang dapat dilakukan dengan AURA?**
9. **Apakah implementasi aktual di source code sesuai dengan klaim dokumentasinya?**

---

# BAGIAN 1 — DEFINISI PRODUK

Jelaskan AURA dalam beberapa level:

### A. One-sentence definition

Definisikan AURA dalam satu kalimat yang paling akurat berdasarkan implementasi aktual.

### B. Simple explanation

Jelaskan AURA untuk orang non-teknis.

### C. Technical explanation

Jelaskan AURA menggunakan terminologi engineering/software architecture yang tepat.

### D. Problem statement

Identifikasi:

* Masalah utama yang diselesaikan AURA
* Pain point yang menjadi target
* Mengapa workflow audit software konvensional belum cukup
* Mengapa diperlukan autonomous audit-remediate-verify loop

Gunakan format:

| Komponen          | Penjelasan |
| ----------------- | ---------- |
| Problem           |            |
| Existing approach |            |
| Limitation        |            |
| AURA approach     |            |
| Expected benefit  |            |

---

# BAGIAN 2 — REVERSE ENGINEERING ARSITEKTUR

Telusuri seluruh repository dan identifikasi komponen aktual.

Buat peta:

```text
INPUT
  ↓
COMPONENTS
  ↓
AUDIT
  ↓
FINDINGS
  ↓
REMEDIATION
  ↓
VERIFICATION
  ↓
CONVERGENCE
  ↓
FINAL DECISION
```

Jelaskan fungsi setiap komponen.

Identifikasi secara spesifik:

* Core engine
* State machine
* Persistent state
* Database/storage
* Configuration
* Project analyzer
* Semantic analysis
* Domain auditor
* Execution context
* Finding classification/subclassification
* Adversarial validation
* Convergence logic
* Evidence handling
* Git safety/push guard
* CLI/scripts
* LLM/agent integration
* Error handling
* Recovery behavior

Untuk setiap komponen, jelaskan:

1. Tujuan
2. Input
3. Process
4. Output
5. Dependencies
6. Failure mode

---

# BAGIAN 3 — CARA KERJA AURA SECARA STEP-BY-STEP

Jelaskan lifecycle AURA dari awal sampai akhir.

Contoh struktur analisis:

### Step 1 — Target Project Discovery

Apa yang terjadi ketika target project diberikan?

### Step 2 — Context Analysis

Bagaimana AURA memahami project?

### Step 3 — Audit Cycle

Bagaimana audit dilakukan?

### Step 4 — Findings Generation

Bagaimana temuan direpresentasikan?

### Step 5 — Remediation

Bagaimana proses perbaikan dilakukan?

### Step 6 — Verification

Bagaimana AURA memastikan perbaikan benar?

### Step 7 — Adversarial Validation

Bagaimana AURA mencoba mendeteksi false confidence, regression, atau failure?

### Step 8 — Convergence

Apa syarat sistem dianggap converged?

### Step 9 — Final Decision

Apa kondisi untuk:

* READY
* CONDITIONALLY_READY
* NOT_READY
* HUMAN_BLOCKER
* FAILED CONVERGENCE

Gunakan diagram ASCII jika membantu.

---

# BAGIAN 4 — CARA MENGGUNAKAN AURA

Buat tutorial praktis dari nol.

Jelaskan:

## A. Prerequisites

Apa saja yang harus diinstall?

* Python version
* Dependencies
* Git
* Operating system requirements
* API keys jika diperlukan
* Environment variables

## B. Installation

Berikan langkah instalasi berdasarkan implementasi aktual repository.

Jangan mengarang command. Jika command tidak tersedia, katakan dengan jelas.

## C. Basic Usage

Berikan contoh:

```text
Target Project
     ↓
Run AURA
     ↓
Audit
     ↓
Review Findings
     ↓
Remediation
     ↓
Verification
     ↓
Final Report
```

Jelaskan setiap command yang benar-benar tersedia.

## D. Real Example

Buat contoh penggunaan terhadap sebuah repository target.

Jelaskan:

* Command yang dijalankan
* File/state yang dihasilkan
* Output yang diharapkan
* Cara membaca hasil
* Kapan harus melakukan intervensi manusia

---

# BAGIAN 5 — KELEBIHAN AURA

Identifikasi kelebihan berdasarkan source code aktual.

Jangan menggunakan marketing language berlebihan.

Analisis keunggulan AURA terhadap:

### 1. Manual Code Review

| Faktor               | Manual Review | AURA |
| -------------------- | ------------- | ---- |
| Repeatability        |               |      |
| Persistent state     |               |      |
| Evidence             |               |      |
| Regression detection |               |      |
| Verification         |               |      |
| Convergence          |               |      |

### 2. One-shot AI Code Audit

Bandingkan dengan workflow:

```text
Prompt AI
   ↓
AI audit
   ↓
AI memberikan hasil
```

Jelaskan apa perbedaan AURA.

### 3. CI/CD Testing

Apakah AURA menggantikan CI/CD?

Jika tidak, jelaskan posisinya.

### 4. Traditional Static Analysis

Bandingkan dengan:

* Linter
* Type checker
* Unit test
* Security scanner
* Static analyzer

Jelaskan layer masalah yang dapat dan tidak dapat ditangani AURA.

---

# BAGIAN 6 — FITUR PALING MENONJOL

Identifikasi fitur yang paling unik atau penting.

Berikan ranking:

| Rank | Feature | Importance | Uniqueness | Evidence |
| ---- | ------- | ---------: | ---------: | -------- |
| 1    |         |            |            |          |
| 2    |         |            |            |          |
| 3    |         |            |            |          |
| 4    |         |            |            |          |
| 5    |         |            |            |          |

Gunakan scoring:

* Importance: 1–10
* Uniqueness: 1–10

Berikan alasan matematis/teknis untuk ranking.

---

# BAGIAN 7 — KELEMAHAN DAN LIMITASI

Lakukan audit kritis terhadap AURA sendiri.

Cari:

* Architecture gaps
* Missing features
* False convergence risk
* State corruption risk
* LLM dependency risk
* Prompt injection risk
* Sandbox limitations
* Performance/scalability limitations
* Large repository limitations
* Failure recovery limitations
* Concurrency issues
* Database risks
* Security risks
* Git risks
* Evidence integrity risks
* Test coverage gaps
* Observability gaps

Buat:

| Finding | Severity | Probability | Impact | Risk Score | Recommendation |
| ------- | -------: | ----------: | -----: | ---------: | -------------- |

Gunakan:

```text
Risk Score = Probability × Impact
```

Dengan skala 1–10.

---

# BAGIAN 8 — USE CASE NYATA

Identifikasi penggunaan AURA untuk:

1. Legacy project
2. Project yang penuh bug
3. Project sebelum production release
4. AI-generated codebase
5. Large repository
6. Security audit
7. Regression detection
8. Continuous engineering audit
9. Open-source project
10. Internal enterprise repository

Untuk setiap use case:

* Cocok atau tidak?
* Confidence level
* Risiko
* Keterbatasan

Gunakan format:

| Use Case | Suitability | Risk | Confidence | Reason |
| -------- | ----------: | ---: | ---------: | ------ |

---

# BAGIAN 9 — ANALISIS POSISI PRODUK

Tentukan AURA sebenarnya berada dalam kategori apa.

Pilih dan analisis kemungkinan:

* AI Coding Agent
* Autonomous Software Auditor
* Engineering Quality Engine
* Audit Orchestrator
* Autonomous Remediation Framework
* Verification Engine
* Developer Tool
* CI/CD Tool
* Agentic Engineering System

Berikan:

```text
Primary Category
Secondary Category
Adjacent Categories
```

Kemudian jelaskan positioning yang paling akurat.

---

# BAGIAN 10 — VALIDASI KLAIM VS IMPLEMENTASI

Buat tabel:

| Claimed Capability  | README/Docs Claim | Actual Implementation | Test Evidence | Status |
| ------------------- | ----------------- | --------------------- | ------------- | ------ |
| Audit               |                   |                       |               |        |
| Remediation         |                   |                       |               |        |
| Verification        |                   |                       |               |        |
| Convergence         |                   |                       |               |        |
| Adversarial testing |                   |                       |               |        |
| Autonomous loop     |                   |                       |               |        |

Gunakan status:

* IMPLEMENTED
* PARTIALLY_IMPLEMENTED
* DOCUMENTED_ONLY
* MISSING
* UNVERIFIED

Jangan memberikan status IMPLEMENTED tanpa bukti dari repository.

---

# BAGIAN 11 — SCORING

Berikan penilaian objektif:

```text
Architecture Quality       /100
Code Quality               /100
Test Quality               /100
Reliability                /100
Security                   /100
Scalability                /100
Maintainability            /100
Real-world Effectiveness   /100
Production Readiness       /100
```

Kemudian:

```text
Overall Score = weighted average
```

Jelaskan bobot yang digunakan.

---

# BAGIAN 12 — FINAL VERDICT

Berikan kesimpulan:

## A. AURA sebenarnya adalah:

Satu definisi final.

## B. Cara terbaik menggunakan AURA:

Jelaskan workflow optimal.

## C. Kelebihan terbesar:

3–5 poin paling kuat.

## D. Kelemahan terbesar:

3–5 risiko paling penting.

## E. Siapa yang sebaiknya menggunakan AURA:

Target user ideal.

## F. Siapa yang sebaiknya tidak menggunakan AURA:

Jelaskan keterbatasannya.

## G. Final Production Verdict

Pilih salah satu:

* EXPERIMENTAL
* EARLY_PROTOTYPE
* LIMITED_REAL_WORLD
* CONDITIONALLY_READY
* PRODUCTION_READY
* ENTERPRISE_READY

Berikan alasan berdasarkan evidence.

---

# ATURAN PENTING

1. **Jangan hanya membaca README.**
2. **Audit source code aktual.**
3. **Periksa test suite.**
4. **Periksa konfigurasi dan scripts.**
5. **Bedakan fakta, inferensi, dan opini.**
6. **Jangan mengarang fitur yang tidak ada.**
7. **Jika sesuatu tidak dapat diverifikasi, tulis UNVERIFIED.**
8. **Jika dokumentasi bertentangan dengan source code, prioritaskan source code.**
9. **Berikan file path atau evidence untuk klaim teknis penting.**
10. **Jangan mencoba memperbaiki repository. Fokus hanya pada analisis dan pemahaman.**

# FORMAT FINAL

Gunakan urutan:

1. Executive Summary
2. What Is AURA?
3. Problem It Solves
4. Architecture
5. How It Works
6. How To Use It
7. Strengths
8. Weaknesses
9. Real-World Use Cases
10. Product Positioning
11. Claim vs Reality
12. Scoring
13. Ranking
14. Final Verdict
15. Confidence Level

Akhiri dengan:

```text
FINAL ANSWER:

What is AURA?
...

How should I use it?
...

Biggest advantage:
...

Biggest limitation:
...

Recommended for:
...

Not recommended for:
...

Overall Score: X/100

Confidence Level: X%
```

# BAGIAN 13 — MARKET VALIDATION: APAKAH AURA BENAR-BENAR DIBUTUHKAN?

Lakukan analisis objektif untuk menentukan apakah AURA menyelesaikan masalah nyata atau hanya merupakan solusi teknis untuk masalah yang sebenarnya tidak memiliki demand pasar.

## PERTANYAAN UTAMA

Jawab secara eksplisit:

> Apakah AURA adalah sesuatu yang benar-benar dibutuhkan oleh developer, engineering team, startup, enterprise, atau AI coding users?

Jangan memberikan jawaban positif hanya karena teknologi AURA terlihat menarik.

Analisis berdasarkan:

* Pain point nyata di software engineering
* Pertumbuhan AI-generated code
* Kebutuhan code review
* Kebutuhan software audit
* Kebutuhan automated remediation
* Kebutuhan verification
* Risiko false confidence dari AI coding agents
* Kebutuhan continuous quality assurance
* Keterbatasan manual engineering review
* Keterbatasan existing AI code review tools

---

## A. IDENTIFIKASI MASALAH NYATA

Jawab:

### Problem 1

Apakah developer sering mengalami kondisi:

```text
AI generates code
      ↓
Code looks correct
      ↓
Tests partially pass
      ↓
Hidden bugs remain
      ↓
Developer asks AI to check again
      ↓
Same AI says "looks good"
      ↓
False confidence
```

Apakah masalah tersebut benar-benar signifikan?

Siapa yang mengalami masalah ini?

* Solo developer
* Startup
* Vibe coder
* AI-heavy engineering team
* Enterprise
* Open-source maintainer
* Security team

Berikan:

| Problem | Severity | Frequency | Current Solution | Solution Gap |
| ------- | -------: | --------: | ---------------- | -----------: |

---

# BAGIAN 14 — CUSTOMER PROBLEM / SOLUTION FIT

Tentukan apakah AURA memiliki **Problem-Solution Fit**.

Gunakan formula:

```text
Problem-Solution Fit Score =
Problem Severity
× Frequency
× Cost of Failure
× Current Solution Gap
```

Skala:

* 1–10

Analisis customer persona.

## Persona 1 — Solo AI Developer

Masalah:

* Banyak menggunakan AI coding agent
* Tidak memiliki senior engineer untuk review
* Risiko false confidence tinggi

Apakah AURA berguna?

Score:

```text
Need Score: X/10
Willingness to Use: X/10
Willingness to Pay: X/10
```

---

## Persona 2 — Startup Engineering Team

Analisis:

* Speed
* Technical debt
* AI-generated code
* Limited engineering review capacity

Score:

```text
Need Score
Budget Potential
Integration Difficulty
ROI
```

---

## Persona 3 — Enterprise

Analisis:

* Governance
* Compliance
* Security
* Audit trail
* Evidence
* Human approval

Apakah AURA sudah cukup matang?

---

## Persona 4 — Open Source Maintainer

Analisis:

* Free/open-source ecosystem
* Limited reviewer capacity
* Large PR volume
* Contributor quality

---

# BAGIAN 15 — APakah ORANG BENAR-BENAR MAU MENGGUNAKAN AURA?

Jangan hanya menjawab "ya".

Berikan analisis:

## Scenario A — Strong Demand

Apa kondisi yang membuat AURA sangat dibutuhkan?

## Scenario B — Medium Demand

Kapan AURA hanya menjadi optional?

## Scenario C — Weak Demand

Kapan orang tidak membutuhkan AURA?

---

Gunakan probabilitas:

| Scenario             | Probability | Reason |
| -------------------- | ----------: | ------ |
| Strong Market Demand |          X% |        |
| Moderate Demand      |          X% |        |
| Weak Demand          |          X% |        |
| No Meaningful Demand |          X% |        |

Total harus:

```text
100%
```

---

# BAGIAN 16 — COMPETITIVE LANDSCAPE

Identifikasi tools yang benar-benar relevan sebagai pembanding.

Kelompokkan:

## Category A — AI Code Review

Contoh:

* CodeRabbit
* GitHub Copilot Code Review
* Qodo
* Greptile
* Cursor BugBot

## Category B — Static Analysis

Contoh:

* SonarQube
* Semgrep
* Codacy
* DeepSource

## Category C — Security Analysis

Contoh:

* Snyk Code
* Checkmarx
* Veracode

## Category D — AI Coding Agents

Contoh:

* Claude Code
* OpenAI Codex
* Cursor
* Windsurf

## Category E — Autonomous Remediation / Convergence

Cari tools yang memiliki:

```text
Analyze
   ↓
Find
   ↓
Fix
   ↓
Test
   ↓
Verify
   ↓
Repeat
```

Jangan mengasumsikan AURA tidak memiliki kompetitor.

Cari kompetitor langsung maupun tidak langsung.

---

# BAGIAN 17 — COMPETITOR COMPARISON

Bandingkan AURA dengan tools paling relevan.

Gunakan tabel:

| Capability               | AURA | Tool A | Tool B | Tool C | Tool D |
| ------------------------ | ---- | ------ | ------ | ------ | ------ |
| Full project audit       |      |        |        |        |        |
| PR review                |      |        |        |        |        |
| Persistent state         |      |        |        |        |        |
| Audit history            |      |        |        |        |        |
| Autonomous remediation   |      |        |        |        |        |
| Independent verification |      |        |        |        |        |
| Adversarial validation   |      |        |        |        |        |
| Convergence detection    |      |        |        |        |        |
| Evidence persistence     |      |        |        |        |        |
| Human blocker detection  |      |        |        |        |        |
| Rollback/recovery        |      |        |        |        |        |
| Git safety controls      |      |        |        |        |        |
| Multi-cycle execution    |      |        |        |        |        |
| Open source              |      |        |        |        |        |

Untuk setiap nilai, gunakan:

* YES
* PARTIAL
* NO
* UNKNOWN

Jangan mengarang.

---

# BAGIAN 18 — APA YANG MEMBUAT AURA UNIK?

Identifikasi apakah AURA benar-benar memiliki **Unique Value Proposition**.

Gunakan formula:

```text
Uniqueness Score =
Feature Novelty
× Practical Utility
× Competitor Gap
× Difficulty to Replicate
```

Skala:

* 1–10

Kemudian ranking:

| Rank | Potential Differentiator | Uniqueness | Market Value | Defensibility | Total |
| ---- | ------------------------ | ---------: | -----------: | ------------: | ----: |
| 1    |                          |            |              |               |       |
| 2    |                          |            |              |               |       |
| 3    |                          |            |              |               |       |

---

# BAGIAN 19 — AURA VS TOOLS SEJENIS

Jawab pertanyaan:

## Apakah AURA lebih baik?

Jawaban tidak boleh absolut.

Gunakan:

```text
AURA is better when:
```

Jelaskan kondisi.

Kemudian:

```text
Competitor is better when:
```

Jelaskan kondisi.

Contoh:

### AURA lebih unggul jika:

* Target adalah existing project
* Project memerlukan audit multi-cycle
* Developer menggunakan AI coding agent
* Dibutuhkan persistent audit state
* Dibutuhkan convergence tracking
* Dibutuhkan verification setelah remediation

### Competitor lebih unggul jika:

* Hanya membutuhkan PR review
* Membutuhkan enterprise SAST
* Membutuhkan security scanning khusus
* Membutuhkan IDE integration
* Membutuhkan massive-scale enterprise CI/CD
* Membutuhkan proven deterministic rule engine

Verifikasi apakah contoh tersebut benar berdasarkan implementasi dan kompetitor aktual.

---

# BAGIAN 20 — SWOT ANALYSIS

## Strengths

Identifikasi kekuatan teknis AURA.

## Weaknesses

Identifikasi kelemahan.

## Opportunities

Identifikasi peluang pasar.

Pertimbangkan:

* AI-generated software explosion
* Vibe coding
* Autonomous agents
* Software quality assurance
* Agent verification
* AI governance

## Threats

Pertimbangkan:

* GitHub Copilot
* OpenAI Codex
* Anthropic Claude Code
* SonarQube
* Existing AI code review platforms
* Competitor feature replication
* Open-source competition

Buat:

| Category | Item | Impact | Probability |
| -------- | ---- | -----: | ----------: |

---

# BAGIAN 21 — MARKET POSITIONING

Tentukan positioning terbaik untuk AURA.

Jangan menggunakan positioning yang terlalu umum.

Bandingkan:

### Option A

```text
AI Code Auditor
```

### Option B

```text
Autonomous Software Auditor
```

### Option C

```text
Autonomous Audit-Remediate-Verify Engine
```

### Option D

```text
Software Engineering Convergence Engine
```

### Option E

```text
AI-Generated Code Verification Engine
```

### Option F

```text
Autonomous Engineering Quality Engine
```

Berikan scoring:

| Positioning | Clarity | Differentiation | Market Appeal | Accuracy | Total |
| ----------- | ------: | --------------: | ------------: | -------: | ----: |

Pilih positioning terbaik.

---

# BAGIAN 22 — IS THIS A PRODUCT OR JUST A FEATURE?

Jawab pertanyaan penting:

> Apakah AURA cukup bernilai untuk menjadi standalone product?

Atau:

> Apakah AURA sebenarnya lebih cocok menjadi feature dalam AI coding platform, CI/CD platform, atau code review tool?

Bandingkan:

```text
Standalone Product
vs
GitHub Action
vs
CLI
vs
AI Agent Plugin
vs
CI/CD Integration
vs
IDE Integration
vs
Open-source Framework
```

Berikan ranking:

| Product Form | Market Fit | Development Complexity | Adoption Potential | Monetization | Score |
| ------------ | ---------: | ---------------------: | -----------------: | -----------: | ----: |

---

# BAGIAN 23 — MONETIZATION POTENTIAL

Analisis apakah AURA memiliki potensi bisnis.

Kemungkinan model:

* Open source + hosted cloud
* SaaS subscription
* Pay per audit
* Pay per repository
* Enterprise license
* GitHub App
* CI/CD platform
* API
* Managed engineering audit

Untuk setiap model:

| Model | Customer Fit | Scalability | Competition | Revenue Potential | Score |
| ----- | -----------: | ----------: | ----------: | ----------------: | ----: |

Jangan mengasumsikan orang akan membayar.

Analisis:

```text
Why would a customer pay?
```

Dan:

```text
Why would a customer refuse to pay?
```

---

# BAGIAN 24 — KILL TEST

Lakukan analisis kritis:

> Apa alasan terbesar mengapa AURA bisa gagal?

Identifikasi minimal 10 kemungkinan.

Contoh:

* Competitor adds same feature
* Too complex
* Too expensive
* Slow execution
* False positives
* False convergence
* Difficult setup
* LLM dependency
* Poor trust
* No measurable ROI

Untuk setiap risiko:

| Failure Risk | Probability | Impact | Detectability | Risk Score |
| ------------ | ----------: | -----: | ------------: | ---------: |

Gunakan:

```text
Risk Score =
Probability × Impact
```

---

# BAGIAN 25 — WHAT MUST BE TRUE FOR AURA TO WIN?

Identifikasi critical success factors.

Contoh:

```text
AURA must prove:
```

1. It finds more meaningful issues than one-shot AI review
2. It reduces human engineering time
3. It prevents regressions
4. Its convergence mechanism is reliable
5. It produces measurable evidence
6. Its cost is lower than human review cost

Jangan menggunakan contoh ini secara otomatis.

Verifikasi dan buat daftar berdasarkan analisis aktual.

---

# BAGIAN 26 — FINAL INVESTMENT-STYLE VERDICT

Bertindak sebagai:

```text
Technical Founder
+
Developer Tools Investor
+
Engineering Leader
+
Software Architect
```

Berikan keputusan:

## A. Is AURA a good idea?

Pilih:

* EXCELLENT IDEA
* GOOD IDEA
* PROMISING BUT UNPROVEN
* WEAK PRODUCT IDEA
* TECHNICALLY INTERESTING BUT LOW MARKET VALUE
* SHOULD NOT BE PURSUED

## B. Is there real market demand?

```text
YES / PARTIAL / NO
```

Dengan probabilitas.

## C. Is AURA differentiated?

```text
HIGH / MEDIUM / LOW
```

## D. Is the differentiation defensible?

```text
HIGH / MEDIUM / LOW
```

## E. Would you recommend continuing development?

```text
STRONGLY YES
YES
YES, BUT PIVOT
UNCERTAIN
NO
```

---

# BAGIAN 27 — FINAL RANKING

Berikan skor:

```text
Technical Quality           X/100
Problem Severity            X/100
Market Demand               X/100
Product-Market Fit          X/100
Differentiation             X/100
Competitive Advantage       X/100
Ease of Adoption            X/100
Monetization Potential      X/100
Long-Term Potential         X/100
```

Kemudian:

```text
OVERALL PRODUCT SCORE = X/100
```

Gunakan bobot yang dijelaskan secara eksplisit.

---

# BAGIAN 28 — FINAL ANSWER

Akhiri dengan jawaban yang sangat langsung:

```text
1. Apakah AURA bagus?

YES / NO / PROMISING

Alasan:
...

2. Apakah orang membutuhkan AURA?

YES / PARTIAL / NO

Target utama:
...

3. Masalah apa yang paling kuat diselesaikan AURA?

...

4. Apa kelebihan terbesar dibanding tools sejenis?

...

5. Apa kelemahan terbesar dibanding kompetitor?

...

6. Siapa kompetitor paling berbahaya?

...

7. Apa keunikan AURA yang benar-benar sulit ditiru?

...

8. Apakah AURA sebaiknya menjadi bisnis?

YES / NO / PIVOT

9. Apa yang harus dibangun agar AURA lebih unggul?

Rank #1:
Rank #2:
Rank #3:

10. FINAL VERDICT:

[VERDICT]

Overall Product Score: X/100

Market Confidence: X%

Technical Confidence: X%

Investment Confidence: X%
```

---

# ATURAN EVIDENCE

1. Gunakan kompetitor nyata yang masih aktif atau relevan.
2. Jangan menganggap AURA unik sebelum melakukan competitive research.
3. Jangan menganggap market demand hanya karena banyak AI coding tools.
4. Pisahkan:

   * Feature
   * Product
   * Business
5. Bedakan:

   * Technical novelty
   * Product differentiation
   * Market demand
6. Jika data market tidak cukup, katakan:

   ```text
   UNPROVEN
   ```
7. Jangan menggunakan hype atau marketing language.
8. Prioritaskan analisis objektif, bahkan jika kesimpulannya negatif.
