# Campus Solar Operations Portal — Diagnostic & Maintenance Manager
> **Track 3: Smart Energy (Things That Power) — Problem 3.1: "Why is this rooftop producing less?"**

An end-to-end solar intelligence platform designed for university campuses operating distributed rooftop PV fleets. By comparing live generation telemetry against weather irradiance and ambient temperature, the system autonomously identifies the root cause of underperformance — separating environmental dust from tree/building shade from failing inverters — and generates an economically self-paying maintenance schedule.

---

## ⚡ Live Deployments

- **🌐 Live Cloudflare Tunnel:** [https://manager-reading-physics-performing.trycloudflare.com](https://manager-reading-physics-performing.trycloudflare.com)
- **💻 Local Dashboard:** `http://localhost:8501`

---

## 📌 Problem Context

A campus operates **50 rooftop solar systems** totaling **3,060 kWp (~3.06 MWp)**. Fleets of this scale routinely experience a 15–30% generation loss, but facility management teams face difficulty differentiating root causes without specialized instrumentation:
- **Dust & Soiling:** Uniform losses that recover immediately after rain or high-pressure washing.
- **Partial Shading:** Morning/afternoon losses from adjacent buildings or trees that require branch trimming, not panel washing.
- **Inverter / Electrical Faults:** Blown string fuses, fan failures, or degraded conversion efficiency requiring urgent electrical service.

Washing shaded roofs wastes budget; ignoring blown fuses leaks thousands of rupees daily.

---

## 🔬 Core Solution Pillars

### 1. Expected-Generation Model ($P_{\text{expected}}$)
Implements the standard **IEC 61724 / Sandia Photovoltaic Model** paired with a Random Forest regression baseline:
$$\begin{aligned}
T_{\text{cell}} &= T_{\text{amb}} + G_{\text{POA}} \times \left( \frac{\text{NOCT} - 20}{800} \right) \\
f_{\text{temp}} &= 1 + \gamma \times (T_{\text{cell}} - 25^\circ\text{C}) \\
P_{\text{expected}} &= P_{\text{rated}} \times \left( \frac{G_{\text{POA}}}{1000\text{ W/m}^2} \right) \times f_{\text{temp}} \times \eta_{\text{bop}} \times \eta_{\text{inverter}}
\end{aligned}$$
- **Machine Learning Baseline:** $R^2 = 0.9984$, $\text{MAE} = 0.54\text{ kW}$.

### 2. Root-Cause Diagnostic Rules
Evaluates multi-dimensional temporal and electrical signatures:

| Diagnostic Metric | Dust / Soiling | Partial Shading | Inverter / Hardware Fault |
| :--- | :--- | :--- | :--- |
| **Diurnal Power Shape** | Symmetrically uniform loss across all hours | Asymmetric morning/afternoon drop or midday notch | Flat-line ceiling or discrete 33% string drop |
| **Trend Over Dry Days** | Monotonic downward drift ($-0.3\%$ to $-0.8\%$/day) | Constant daily pattern matching sun angle | Abrupt overnight drop or constant loss |
| **Rain / Wash Impact** | Immediate yield recovery ($+8\%$ to $+20\%$) | Zero change ($< 2\%$) | Zero change ($< 2\%$) |
| **Inverter Efficiency** | Nominal ($> 97\%$) | Nominal ($> 97\%$) | Degraded ($< 90\%$) or thermal throttle |
| **Prescribed Action** | Pressure water jet cleaning | Tree pruning / DC optimizers | Replace DC fuse / service inverter fan |

### 3. Economically Self-Paying Maintenance Plan
Every maintenance recommendation is financially gated:
$$\tau_{\text{payback}} = \frac{\text{Service Cost (₹)}}{\text{Daily Revenue Loss (₹/day)}} \le 12\text{ Days}$$
- **Fleet Capacity:** 3,060 kWp across 50 rooftops.
- **Current Campus Daily Loss:** ₹17,173 / day (~₹5.15 Lakhs / month).
- **Targeted Maintenance Budget:** ₹171,500.
- **Net 30-Day Return:** **+₹330,432** (The entire maintenance cost pays for itself in **9.8 days**).

---

## 🛠️ Repository Architecture

```
.
├── app.py                          # Streamlit Interactive Operations Dashboard
├── data_generator.py               # 50-system campus telemetry & physics simulator
├── expected_generation_model.py     # IEC 61724 Photovoltaic & ML baseline models
├── diagnostic_engine.py            # Automated root cause classifier (100% accuracy)
├── maintenance_optimizer.py        # Economic dispatch & payback optimization
├── run_pipeline.py                 # End-to-end execution pipeline
├── SUBMISSION_REPORT.md            # Comprehensive hackathon technical submission
├── requirements.txt                # Python dependencies
├── .streamlit/config.toml          # High-contrast UI theme configuration
├── data/                           # Simulated campus metadata & weather telemetry
└── outputs/                        # Ranked maintenance plan & diagnostic reports
```

---

## 🚀 Getting Started

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/Sidhhrana/campus-solar-operations-portal.git
cd campus-solar-operations-portal

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Analytics Pipeline
```bash
python3 run_pipeline.py
```

### 3. Launch Operations Dashboard
```bash
streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 🏗️ IoT Monitoring Architecture
1. **Field Layer:** 50 Rooftops with string inverters communicating via RS-485 Modbus RTU (SunSpec protocol). Campus weather station measuring POA irradiance, ambient temperature, and rainfall.
2. **Edge Gateway Layer:** Industrial gateways (Advantech / Raspberry Pi) polling at 5 seconds with a local SQLite store-and-forward buffer for network drop resilience.
3. **Storage Layer:** TimescaleDB for time-series telemetry and PostgreSQL for asset metadata and tariffs.
4. **Analytics Layer:** Containerized Python services computing expected power baselines, fault signatures, and ROI dispatch schedules.
5. **Operations Layer:** Campus facilities web dashboard with automated work order dispatch.
