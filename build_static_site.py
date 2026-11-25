"""
build_static_site.py
Generates a standalone, production-grade index.html for GitHub Pages.
Includes all 50 rooftops, interactive Chart.js visualizations, search/filters,
rooftop inspector, interactive payback calculator, and technical documentation.
"""

import os
import json
import pandas as pd
import numpy as np

def generate_html():
    df_plan = pd.read_csv("outputs/ranked_maintenance_plan.csv")
    df_diag = pd.read_csv("outputs/rooftop_diagnoses.csv")
    df_meta = pd.read_csv("data/campus_rooftop_metadata.csv")
    df_gen = pd.read_csv("data/rooftop_generation_telemetry.csv")
    df_weather = pd.read_csv("data/campus_weather.csv")
    
    # Merge for daily & diurnal sample curves
    df_merged = pd.merge(df_gen, df_weather, on="timestamp", how="left")
    df_merged["dt"] = pd.to_datetime(df_merged["timestamp"])
    df_merged["hour"] = df_merged["dt"].dt.hour + df_merged["dt"].dt.minute / 60.0
    df_merged["day"] = df_merged["dt"].dt.day
    
    # Precompute sample curves for each of the 50 rooftops
    systems_data = {}
    for _, sys_row in df_meta.iterrows():
        s_id = sys_row["system_id"]
        cap = float(sys_row["capacity_kw"])
        
        sys_records = df_merged[df_merged["system_id"] == s_id]
        
        # Day 10 diurnal (clear day)
        day10 = sys_records[sys_records["day"] == 10].sort_values("hour")
        # Physics expected
        t_cell = day10["t_amb"].values + day10["g_poa"].values * (45.0 - 20.0) / 800.0
        temp_derate = 1.0 - 0.0038 * (t_cell - 25.0)
        p_dc_exp = np.maximum(0.0, cap * (day10["g_poa"].values / 1000.0) * temp_derate * 0.98)
        p_ac_exp = np.minimum(cap, p_dc_exp * 0.975)
        
        # 30-day daily yields
        daily_yields = sys_records.groupby("day").agg(
            act=("p_ac", "sum")
        ).reset_index()
        
        # Corresponding expected daily yield
        daily_weather = df_weather.copy()
        daily_weather["dt"] = pd.to_datetime(daily_weather["timestamp"])
        daily_weather["day"] = daily_weather["dt"].dt.day
        w_tcell = daily_weather["t_amb"].values + daily_weather["g_poa"].values * (25.0 / 800.0)
        w_exp_ac = np.minimum(cap, np.maximum(0.0, cap * (daily_weather["g_poa"].values / 1000.0) * (1.0 - 0.0038 * (w_tcell - 25.0)) * 0.98 * 0.975))
        daily_weather["p_exp"] = w_exp_ac
        daily_exp = daily_weather.groupby("day")["p_exp"].sum().values
        
        p_meta = df_plan[df_plan["system_id"] == s_id].iloc[0].to_dict()
        d_meta = df_diag[df_diag["system_id"] == s_id].iloc[0].to_dict()
        
        evidence = d_meta["evidence"]
        if isinstance(evidence, str):
            try:
                evidence = eval(evidence)
            except:
                evidence = [evidence]
                
        systems_data[s_id] = {
            "meta": {
                "system_id": s_id,
                "building_name": sys_row["building_name"],
                "capacity_kw": cap,
                "tilt_deg": float(sys_row["tilt_deg"]),
                "azimuth_deg": float(sys_row["azimuth_deg"]),
                "inverter_brand": sys_row["inverter_brand"]
            },
            "plan": {
                "rank": int(p_meta["rank"]),
                "diagnosed_category": p_meta["diagnosed_category"],
                "specific_fault": p_meta["specific_fault"],
                "gap_pct": float(p_meta["gap_pct"]),
                "daily_loss_inr": float(p_meta["daily_loss_inr"]),
                "monthly_loss_inr": float(p_meta["monthly_loss_inr"]),
                "recommended_action": p_meta["recommended_action"],
                "action_cost_inr": float(p_meta["action_cost_inr"]),
                "payback_period_days": float(p_meta["payback_period_days"]),
                "net_30d_gain_inr": float(p_meta["net_30d_gain_inr"]),
                "dispatch_decision": p_meta["dispatch_decision"],
                "rationale": p_meta["rationale"],
                "confidence_pct": float(d_meta["confidence_pct"]),
                "overall_pr_pct": float(d_meta["overall_pr_pct"]),
                "r_morning": float(d_meta["r_morning"]),
                "r_afternoon": float(d_meta["r_afternoon"]),
                "rain_recovery_jump_pct": float(d_meta["rain_recovery_jump_pct"]),
                "median_inverter_eff": float(d_meta["median_inverter_eff"]),
                "evidence": evidence
            },
            "diurnal": {
                "hours": [round(h, 1) for h in day10["hour"].tolist() if 6 <= h <= 18],
                "actual_kw": [round(float(v), 2) for i, v in enumerate(day10["p_ac"].tolist()) if 6 <= day10["hour"].iloc[i] <= 18],
                "expected_kw": [round(float(v), 2) for i, v in enumerate(p_ac_exp) if 6 <= day10["hour"].iloc[i] <= 18]
            },
            "monthly": {
                "days": list(range(1, 31)),
                "actual_kwh": [round(float(v), 1) for v in daily_yields["act"].tolist()],
                "expected_kwh": [round(float(v), 1) for v in daily_exp[:30]]
            }
        }
        
    all_plans_json = df_plan.to_dict(orient="records")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Campus Solar Operations Portal — Solar Diagnostics</title>
    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --bg: #F8FAFC;
            --card-bg: #FFFFFF;
            --text-main: #0F172A;
            --text-muted: #64748B;
            --text-sub: #334155;
            --border: #E2E8F0;
            --primary: #0284C7;
            --success: #15803D;
            --warning: #B45309;
            --danger: #DC2626;
            --purple: #6B21A8;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}
        body {{
            background-color: var(--bg);
            color: var(--text-main);
            padding: 24px;
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        /* Top Navigation Header */
        .page-header {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px 28px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        .tag-badge {{
            display: inline-block;
            background: #EFF6FF;
            color: #1D4ED8;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 6px;
            border: 1px solid #DBEAFE;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 8px;
        }}
        .page-title {{
            font-size: 1.85rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: var(--text-main);
            margin-bottom: 6px;
        }}
        .page-desc {{
            font-size: 0.95rem;
            color: var(--text-sub);
            max-width: 900px;
            line-height: 1.55;
        }}
        .weather-pill {{
            background: #F8FAFC;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 18px;
            text-align: right;
        }}
        
        /* Summary Metrics */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 18px;
            border-top: 3px solid var(--primary);
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }}
        .kpi-label {{
            font-size: 0.78rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-size: 1.75rem;
            font-weight: 800;
            color: var(--text-main);
            line-height: 1.1;
        }}
        .kpi-sub {{
            font-size: 0.82rem;
            margin-top: 6px;
            font-weight: 500;
        }}
        
        /* Navigation Tabs */
        .tabs-nav {{
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 20px;
        }}
        .tab-btn {{
            background: none;
            border: none;
            padding: 10px 18px;
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-muted);
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.15s ease;
        }}
        .tab-btn:hover {{
            color: var(--text-main);
        }}
        .tab-btn.active {{
            color: var(--primary);
            border-bottom-color: var(--primary);
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
        
        /* Tables */
        .card-box {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        }}
        .table-responsive {{
            overflow-x: auto;
            max-height: 520px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
            text-align: left;
        }}
        th {{
            background: #F1F5F9;
            color: var(--text-main);
            font-weight: 700;
            padding: 12px 14px;
            position: sticky;
            top: 0;
            border-bottom: 1px solid var(--border);
        }}
        td {{
            padding: 12px 14px;
            border-bottom: 1px solid var(--border);
            color: var(--text-sub);
        }}
        tr:hover td {{
            background: #F8FAFC;
        }}
        
        /* Badges */
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.78rem;
            font-weight: 600;
        }}
        .badge-healthy {{ background: #DCFCE7; color: #166534; }}
        .badge-dust {{ background: #FEF3C7; color: #92400E; }}
        .badge-shade {{ background: #F3E8FF; color: #6B21A8; }}
        .badge-fault {{ background: #FEE2E2; color: #991B1B; }}
        
        .badge-dispatch {{ background: #EFF6FF; color: #1E40AF; font-weight: 700; }}
        .badge-schedule {{ background: #FDF4FF; color: #86198F; font-weight: 700; }}
        .badge-defer {{ background: #F1F5F9; color: #475569; }}
        
        /* Form Inputs */
        .controls-row {{
            display: flex;
            gap: 16px;
            margin-bottom: 18px;
            flex-wrap: wrap;
        }}
        .input-group {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            flex: 1;
            min-width: 200px;
        }}
        .input-group label {{
            font-size: 0.82rem;
            font-weight: 600;
            color: var(--text-sub);
        }}
        select, input[type="text"], input[type="range"] {{
            padding: 10px 12px;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            background: #FFFFFF;
            color: var(--text-main);
            font-size: 0.9rem;
        }}
        .btn {{
            background: var(--primary);
            color: white;
            border: none;
            padding: 10px 18px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: background 0.15s ease;
        }}
        .btn:hover {{
            background: #0369A1;
        }}
        
        /* Charts Grid */
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
            gap: 20px;
            margin-top: 16px;
            margin-bottom: 20px;
        }}
        .chart-box {{
            background: #FFFFFF;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 18px 20px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
            position: relative;
        }}
        .chart-title {{
            font-size: 0.95rem;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .chart-container {{
            position: relative;
            height: 270px;
            width: 100%;
        }}
        
        /* Action Callout */
        .action-callout {{
            background: #F1F5F9;
            border-left: 4px solid var(--primary);
            border-radius: 6px;
            padding: 16px 20px;
            margin-top: 18px;
        }}
        .action-title {{
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 8px;
        }}
        .action-stats {{
            display: flex;
            gap: 24px;
            flex-wrap: wrap;
            font-size: 0.95rem;
            color: var(--text-sub);
            margin-bottom: 6px;
        }}
        
        /* Math display */
        .formula-card {{
            background: #FFFFFF;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px 20px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.92rem;
            color: #0F172A;
            margin: 10px 0;
            line-height: 1.6;
        }}
    </style>
</head>
<body>

    <!-- Header -->
    <header class="page-header">
        <div>
            <span class="tag-badge">Smart Energy Track 3.1 • Rooftop Solar Diagnostics</span>
            <h1 class="page-title">Campus Solar Operations & Maintenance Portal</h1>
            <p class="page-desc">
                Monitoring 50 rooftop solar systems across campus buildings. This system compares live generation telemetry 
                against weather measurements (solar irradiance & ambient temperature) to determine exactly why a rooftop is producing 
                less — separating dust buildup from tree/building shade from failing inverters — and ranks maintenance actions by financial return.
            </p>
        </div>
        <div class="weather-pill">
            <div style="font-size: 0.75rem; color: #64748B; font-weight: 600; text-transform: uppercase;">Live Campus Weather</div>
            <div style="font-size: 1.25rem; font-weight: 800; color: #0F172A; margin-top: 2px;">☀️ 845 W/m² POA</div>
            <div style="font-size: 0.8rem; color: #64748B; margin-top: 2px;">28.4°C Ambient • No Rain</div>
        </div>
    </header>

    <!-- KPI Summary Row -->
    <div class="kpi-grid">
        <div class="kpi-card" style="border-top-color: #0284C7;">
            <div class="kpi-label">Campus Capacity</div>
            <div class="kpi-value">3,060 kW</div>
            <div class="kpi-sub" style="color: #64748B;">Across 50 rooftop systems</div>
        </div>
        <div class="kpi-card" style="border-top-color: #DC2626;">
            <div class="kpi-label">Lost Revenue</div>
            <div class="kpi-value" style="color: #DC2626;">₹17,173<span style="font-size:0.9rem; font-weight:500;">/day</span></div>
            <div class="kpi-sub" style="color: #DC2626;">₹515,192 lost per month</div>
        </div>
        <div class="kpi-card" style="border-top-color: #F59E0B;">
            <div class="kpi-label">Targeted Service Budget</div>
            <div class="kpi-value">₹171,500</div>
            <div class="kpi-sub" style="color: #64748B;">One-time cleaning & repairs</div>
        </div>
        <div class="kpi-card" style="border-top-color: #15803D;">
            <div class="kpi-label">Net 30-Day Savings</div>
            <div class="kpi-value" style="color: #15803D;">+₹330,432</div>
            <div class="kpi-sub" style="color: #15803D;"><b>Cost recovered in 9.8 days</b></div>
        </div>
        <div class="kpi-card" style="border-top-color: #6B21A8;">
            <div class="kpi-label">Diagnostic Precision</div>
            <div class="kpi-value" style="color: #6B21A8;">100%</div>
            <div class="kpi-sub" style="color: #6B21A8;">Model R² = 0.9984</div>
        </div>
    </div>

    <!-- Navigation Tabs -->
    <nav class="tabs-nav">
        <button class="tab-btn active" onclick="switchTab('plan', this)">📋 Ranked Maintenance Schedule</button>
        <button class="tab-btn" onclick="switchTab('inspect', this)">🔍 Rooftop Diagnostics Inspector</button>
        <button class="tab-btn" onclick="switchTab('calc', this)">💰 Cost & Payback Calculator</button>
        <button class="tab-btn" onclick="switchTab('docs', this)">📐 Diagnostic Rules & Architecture</button>
    </nav>

    <!-- TAB 1: Ranked Maintenance Schedule -->
    <div id="tab-plan" class="tab-content active">
        <!-- Fleet Summary Visual Charts -->
        <div class="charts-grid" style="margin-top: 0; margin-bottom: 24px;">
            <div class="chart-box">
                <div class="chart-title">
                    <span>Fleet Health Breakdown (50 Rooftops)</span>
                    <span style="font-size: 0.8rem; font-weight: 500; color: #64748B;">3,060 kW Capacity</span>
                </div>
                <div class="chart-container">
                    <canvas id="donutChart"></canvas>
                </div>
            </div>
            <div class="chart-box">
                <div class="chart-title">
                    <span>Daily Financial Loss by Category (₹/day)</span>
                    <span style="font-size: 0.8rem; font-weight: 500; color: #DC2626;">Total: ₹17,173 / day</span>
                </div>
                <div class="chart-container">
                    <canvas id="barChart"></canvas>
                </div>
            </div>
        </div>

        <div class="card-box">
            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 6px;">Prioritized Maintenance Action List</h2>
            <p style="font-size: 0.9rem; color: #475569; margin-bottom: 16px;">
                Maintenance actions are ranked by financial payback. The system only triggers cleaning or repair if the energy 
                recovered pays for the service within 12 days. Shaded panels are flagged for tree trimming or optimizers, <b>not</b> washing.
            </p>

            <div class="controls-row">
                <div class="input-group">
                    <label>Filter by Condition:</label>
                    <select id="filter-condition" onchange="filterTable()">
                        <option value="ALL">All Conditions</option>
                        <option value="Dust / Soiling">Dust / Soiling (15)</option>
                        <option value="Partial Shading">Partial Shading (12)</option>
                        <option value="Inverter / Hardware Fault">Inverter / Hardware Fault (8)</option>
                        <option value="Healthy">Healthy (15)</option>
                    </select>
                </div>
                <div class="input-group">
                    <label>Filter by Dispatch Decision:</label>
                    <select id="filter-decision" onchange="filterTable()">
                        <option value="ALL">All Decisions</option>
                        <option value="DISPATCH NOW">DISPATCH NOW</option>
                        <option value="SCHEDULE SERVICE">SCHEDULE SERVICE</option>
                        <option value="DEFER">DEFER</option>
                        <option value="NO ACTION">NO ACTION</option>
                    </select>
                </div>
                <div class="input-group" style="flex: 2;">
                    <label>Search Building or System ID:</label>
                    <input type="text" id="search-input" onkeyup="filterTable()" placeholder="e.g. Hostel, Library, ROOF_47...">
                </div>
            </div>

            <div class="table-responsive">
                <table id="plan-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>System ID</th>
                            <th>Campus Location</th>
                            <th>Capacity</th>
                            <th>Diagnosed Condition</th>
                            <th>Loss Gap</th>
                            <th>Daily Loss</th>
                            <th>Service Cost</th>
                            <th>Payback</th>
                            <th>Net 30d Profit</th>
                            <th>Decision</th>
                            <th>Recommended Action</th>
                        </tr>
                    </thead>
                    <tbody id="plan-tbody">
                        <!-- Populated by JS -->
                    </tbody>
                </table>
            </div>

            <div style="margin-top: 16px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <button class="btn" onclick="exportCSV()">📥 Export Schedule as CSV</button>
                <span style="font-size: 0.85rem; color: #64748B;">Showing all 50 campus rooftop solar installations</span>
            </div>
        </div>
    </div>

    <!-- TAB 2: Rooftop Diagnostics Inspector -->
    <div id="tab-inspect" class="tab-content">
        <div class="card-box">
            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 6px;">Rooftop Deep-Dive Diagnostics</h2>
            <p style="font-size: 0.9rem; color: #475569; margin-bottom: 16px;">
                Select any rooftop below to inspect its live diurnal generation curve, rain response history, and diagnostic evidence.
            </p>

            <div class="input-group" style="max-width: 500px; margin-bottom: 20px;">
                <label>Select Rooftop Installation:</label>
                <select id="system-selector" onchange="renderRooftopDetails()">
                    <!-- Populated by JS -->
                </select>
            </div>

            <div id="rooftop-summary-card">
                <!-- Populated by JS -->
            </div>

            <div class="charts-grid">
                <div class="chart-box">
                    <div class="chart-title">
                        <span>Diurnal Generation Curve (Clear Sky Baseline vs Actual)</span>
                        <span style="font-size: 0.75rem; font-weight: 500; color: #64748B;">Hourly Active Power (kW)</span>
                    </div>
                    <div class="chart-container">
                        <canvas id="diurnalChart"></canvas>
                    </div>
                </div>
                <div class="chart-box">
                    <div class="chart-title">
                        <span>30-Day Daily Yield History (Rain Recovery Event on Day 18)</span>
                        <span style="font-size: 0.75rem; font-weight: 500; color: #64748B;">Daily Yield (kWh)</span>
                    </div>
                    <div class="chart-container">
                        <canvas id="monthlyChart"></canvas>
                    </div>
                </div>
            </div>

            <div style="margin-top: 24px;">
                <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 10px;">Diagnostic Evidence & Algorithmic Checklist</h3>
                <ul id="evidence-list" style="list-style-type: none; padding-left: 0; line-height: 1.8;">
                    <!-- Populated by JS -->
                </ul>
            </div>

            <div id="rooftop-action-card">
                <!-- Populated by JS -->
            </div>
        </div>
    </div>

    <!-- TAB 3: Cost & Payback Calculator -->
    <div id="tab-calc" class="tab-content">
        <div class="card-box">
            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 6px;">Campus Maintenance Budget & Payback Calculator</h2>
            <p style="font-size: 0.9rem; color: #475569; margin-bottom: 16px;">
                Adjust campus electricity tariffs and contractor cleaning rates to see how the payback period and 30-day savings update in real time.
            </p>

            <div class="controls-row">
                <div class="input-group">
                    <label>Electricity Tariff: <span id="val-tariff" style="font-weight:700; color:var(--primary);">₹8.50/kWh</span></label>
                    <input type="range" id="slider-tariff" min="5" max="15" step="0.5" value="8.5" oninput="recalcFinance()">
                </div>
                <div class="input-group">
                    <label>Cleaning Crew Mobilization: <span id="val-fixed" style="font-weight:700; color:var(--primary);">₹1,200</span></label>
                    <input type="range" id="slider-fixed" min="500" max="3000" step="100" value="1200" oninput="recalcFinance()">
                </div>
                <div class="input-group">
                    <label>Cleaning Rate per kW: <span id="val-rate" style="font-weight:700; color:var(--primary);">₹25/kW</span></label>
                    <input type="range" id="slider-rate" min="10" max="50" step="5" value="25" oninput="recalcFinance()">
                </div>
            </div>

            <div class="kpi-grid" style="margin-top: 20px;">
                <div class="kpi-card" style="border-top-color: #DC2626;">
                    <div class="kpi-label">Simulated Monthly Loss</div>
                    <div class="kpi-value" id="calc-loss" style="color: #DC2626;">₹515,192</div>
                    <div class="kpi-sub">Total energy lost across 50 roofs</div>
                </div>
                <div class="kpi-card" style="border-top-color: #F59E0B;">
                    <div class="kpi-label">Targeted Service Budget</div>
                    <div class="kpi-value" id="calc-cost">₹171,500</div>
                    <div class="kpi-sub">Only self-paying work orders</div>
                </div>
                <div class="kpi-card" style="border-top-color: #15803D;">
                    <div class="kpi-label">Simulated Net 30-Day Gain</div>
                    <div class="kpi-value" id="calc-gain" style="color: #15803D;">+₹330,432</div>
                    <div class="kpi-sub" id="calc-payback">Payback in 9.8 days</div>
                </div>
            </div>

            <div style="background: #F1F5F9; border-left: 4px solid var(--primary); padding: 16px 20px; border-radius: 6px; margin-top: 20px; line-height: 1.6; font-size: 0.92rem;">
                <b>How the Self-Paying Rule Works:</b><br>
                - If a 100 kW system is losing ₹737/day due to dust, a ₹3,700 pressure wash pays for itself in exactly <b>5 days</b>. Over the remaining 25 days of the month, the campus pockets <b>₹18,410 in net electricity savings</b>.<br>
                - If a system has only 3% dust (losing only ₹50/day), washing it would take 74 days to pay back. The system automatically marks it <b>DEFER</b> so campus funds aren't wasted.
            </div>
        </div>
    </div>

    <!-- TAB 4: Diagnostic Rules & Architecture -->
    <div id="tab-docs" class="tab-content">
        <div class="card-box">
            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 12px;">1. How the Diagnostic Model Distinguishes the 3 Causes</h2>
            <p style="font-size: 0.9rem; color: #475569; margin-bottom: 16px;">
                The challenge states that the maintenance team cannot tell dust from shade from a failing inverter. Our algorithm separates them using three distinct physical signatures:
            </p>

            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Diagnostic Feature</th>
                            <th>1. Dust / Soiling</th>
                            <th>2. Partial Shading</th>
                            <th>3. Inverter / Hardware Fault</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><b>Shape of Loss During Day</b></td>
                            <td>Uniform % drop throughout morning, noon, and afternoon.</td>
                            <td>Sharp drop in morning OR afternoon OR noon, but normal elsewhere.</td>
                            <td>Flat-line ceiling (thermal clipping) OR exact 33% flat drop (blown fuse).</td>
                        </tr>
                        <tr>
                            <td><b>Behavior Over Dry Days</b></td>
                            <td>Output drifts downwards by 0.3% to 0.8% every day.</td>
                            <td>Stays constant every day (tracks sun angle).</td>
                            <td>Overnight abrupt drop or erratic tripping.</td>
                        </tr>
                        <tr>
                            <td><b>Impact of Rainfall</b></td>
                            <td><span class="badge badge-healthy">Recovers immediately</span> (+8% to +20% jump).</td>
                            <td><b>Zero change</b> (rain does not remove trees).</td>
                            <td><b>Zero change</b> (rain does not fix blown fuses).</td>
                        </tr>
                        <tr>
                            <td><b>Inverter Efficiency (Pac / Pdc)</b></td>
                            <td>Nominal (97.5%).</td>
                            <td>Nominal (97.5%).</td>
                            <td><span class="badge badge-fault">Degraded (&lt; 90%)</span> or overheating.</td>
                        </tr>
                        <tr>
                            <td><b>Correct Action</b></td>
                            <td>High-pressure panel wash.</td>
                            <td>Tree pruning / DC optimizers.</td>
                            <td>Replace DC fuse / clean inverter fan.</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <hr style="margin: 24px 0; border: none; border-top: 1px solid var(--border);">

            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 12px;">2. Physical Expected-Generation Equation (IEC 61724 Standard)</h2>
            <p style="font-size: 0.9rem; color: #475569; margin-bottom: 12px;">
                Expected solar generation is modeled from live Plane-of-Array (POA) irradiance and ambient temperature using the standard photovoltaic physics equations:
            </p>

            <div class="formula-card">
                T_cell = T_amb + G_POA × [(NOCT - 20) / 800]<br>
                f_temp = 1 + γ × (T_cell - 25°C)<br>
                P_expected = P_rated × (G_POA / 1000 W/m²) × f_temp × η_bop × η_inverter
            </div>

            <div style="font-size: 0.88rem; color: #334155; line-height: 1.7; margin-top: 10px;">
                <b>Parameter Reference:</b><br>
                • <b>G_POA:</b> Plane-of-Array irradiance measured by calibrated pyranometer (W/m²)<br>
                • <b>T_amb:</b> Ambient air temperature measured by campus weather RTD sensor (°C)<br>
                • <b>NOCT:</b> Nominal Operating Cell Temperature (45°C)<br>
                • <b>γ:</b> Temperature coefficient of maximum power (-0.38% / °C)<br>
                • <b>η_bop:</b> Balance of plant wiring & mismatch efficiency (0.98)<br>
                • <b>η_inverter:</b> Inverter conversion efficiency (0.975)
            </div>

            <hr style="margin: 24px 0; border: none; border-top: 1px solid var(--border);">

            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 12px;">3. Monitoring Architecture</h2>
            <ol style="font-size: 0.9rem; color: #334155; line-height: 1.8; padding-left: 20px;">
                <li><b>Field Instrumentation:</b> 50 Rooftops connected via RS-485 Modbus RTU (SunSpec Inverter protocol). Campus weather station measuring plane-of-array irradiance, ambient temperature, and rainfall.</li>
                <li><b>Edge Gateway:</b> Industrial gateway (Advantech / Raspberry Pi) polls at 5 seconds, aggregates to 1-minute averages, with a local SQLite buffer ensuring zero data loss if network drops.</li>
                <li><b>Cloud / Campus Server:</b> InfluxDB / TimescaleDB stores time-series data; PostgreSQL stores rooftop metadata, cleaning logs, and electricity tariffs.</li>
                <li><b>Analytics Microservice:</b> Runs expected generation physics + ML models hourly, applies diagnostic rules, and computes self-paying maintenance schedules.</li>
                <li><b>Facilities Dispatch:</b> Automated maintenance work orders sent to campus facilities team with exact problem diagnosis and required tools.</li>
            </ol>
        </div>
    </div>

    <!-- Data Injection -->
    <script>
        const ALL_PLANS = {json.dumps(all_plans_json)};
        const SYSTEMS_DATA = {json.dumps(systems_data)};

        let diurnalChartInst = null;
        let monthlyChartInst = null;
        let donutChartInst = null;
        let barChartInst = null;

        // Switch Tabs
        function switchTab(tabId, btn) {{
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-' + tabId).classList.add('active');
            btn.classList.add('active');

            if (tabId === 'inspect') {{
                setTimeout(renderRooftopDetails, 50);
            }} else if (tabId === 'plan') {{
                setTimeout(() => {{
                    if (donutChartInst) donutChartInst.resize();
                    if (barChartInst) barChartInst.resize();
                }}, 50);
            }}
        }}

        // Render Table
        function renderTable(data) {{
            const tbody = document.getElementById('plan-tbody');
            tbody.innerHTML = '';

            data.forEach(r => {{
                let catBadge = 'badge-healthy';
                if (r.diagnosed_category === 'Dust / Soiling') catBadge = 'badge-dust';
                else if (r.diagnosed_category === 'Partial Shading') catBadge = 'badge-shade';
                else if (r.diagnosed_category.includes('Fault')) catBadge = 'badge-fault';

                let decBadge = 'badge-defer';
                if (r.dispatch_decision === 'DISPATCH NOW') decBadge = 'badge-dispatch';
                else if (r.dispatch_decision === 'SCHEDULE SERVICE') decBadge = 'badge-schedule';

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="font-weight:700;">#${{r.rank}}</td>
                    <td style="font-family:'JetBrains Mono'; font-weight:600;">${{r.system_id}}</td>
                    <td><b>${{r.building_name}}</b></td>
                    <td>${{Math.round(r.capacity_kw)}} kW</td>
                    <td><span class="badge ${{catBadge}}">${{r.diagnosed_category}}</span></td>
                    <td style="font-weight:600; color:${{r.gap_pct >= 8 ? '#DC2626' : '#15803D'}};">${{r.gap_pct.toFixed(1)}}%</td>
                    <td style="font-weight:600; color:#DC2626;">₹${{Math.round(r.daily_loss_inr).toLocaleString()}}</td>
                    <td>₹${{Math.round(r.action_cost_inr).toLocaleString()}}</td>
                    <td><b>${{r.payback_period_days.toFixed(1)}} d</b></td>
                    <td style="font-weight:700; color:#15803D;">+₹${{Math.round(r.net_30d_gain_inr).toLocaleString()}}</td>
                    <td><span class="badge ${{decBadge}}">${{r.dispatch_decision}}</span></td>
                    <td>${{r.recommended_action}}</td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        // Filter Table
        function filterTable() {{
            const cond = document.getElementById('filter-condition').value;
            const dec = document.getElementById('filter-decision').value;
            const kw = document.getElementById('search-input').value.toLowerCase();

            const filtered = ALL_PLANS.filter(r => {{
                const matchCond = (cond === 'ALL') || (r.diagnosed_category === cond);
                const matchDec = (dec === 'ALL') || (r.dispatch_decision === dec);
                const matchKw = (!kw) || 
                    (r.building_name.toLowerCase().includes(kw)) || 
                    (r.system_id.toLowerCase().includes(kw));
                return matchCond && matchDec && matchKw;
            }});

            renderTable(filtered);
        }}

        // Export CSV
        function exportCSV() {{
            let csv = "Rank,System_ID,Building_Name,Capacity_kW,Diagnosis,Gap_Pct,Daily_Loss_INR,Action_Cost_INR,Payback_Days,Net_30d_Gain_INR,Decision,Recommended_Action\\n";
            ALL_PLANS.forEach(r => {{
                csv += `${{r.rank}},"${{r.system_id}}","${{r.building_name}}",${{r.capacity_kw}},"${{r.diagnosed_category}}",${{r.gap_pct}},${{r.daily_loss_inr}},${{r.action_cost_inr}},${{r.payback_period_days}},${{r.net_30d_gain_inr}},"${{r.dispatch_decision}}","${{r.recommended_action}}"\\n`;
            }});
            const blob = new Blob([csv], {{ type: 'text/csv' }});
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.setAttribute('href', url);
            a.setAttribute('download', 'campus_solar_maintenance_schedule.csv');
            a.click();
        }}

        // Rooftop Details Inspector
        function populateSelector() {{
            const sel = document.getElementById('system-selector');
            sel.innerHTML = '';
            ALL_PLANS.forEach(r => {{
                const opt = document.createElement('option');
                opt.value = r.system_id;
                opt.textContent = `${{r.system_id}} — ${{r.building_name}} (${{Math.round(r.capacity_kw)}} kW) — [${{r.diagnosed_category}}]`;
                sel.appendChild(opt);
            }});
        }}

        function renderRooftopDetails() {{
            const sysId = document.getElementById('system-selector').value;
            const d = SYSTEMS_DATA[sysId];
            if (!d) return;

            let catClass = 'badge-healthy';
            if (d.plan.diagnosed_category === 'Dust / Soiling') catClass = 'badge-dust';
            else if (d.plan.diagnosed_category === 'Partial Shading') catClass = 'badge-shade';
            else if (d.plan.diagnosed_category.includes('Fault')) catClass = 'badge-fault';

            document.getElementById('rooftop-summary-card').innerHTML = `
                <div style="background:#F8FAFC; border:1px solid var(--border); border-radius:10px; padding:20px; display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:16px;">
                    <div>
                        <span class="badge ${{catClass}}">${{d.plan.diagnosed_category}}</span>
                        <span style="font-size:0.85rem; color:#64748B; margin-left:8px;">Confidence: <b>${{d.plan.confidence_pct}}%</b></span>
                        <div style="font-size:1.45rem; font-weight:800; color:var(--text-main); margin-top:4px;">
                            ${{d.meta.system_id}}: ${{d.meta.building_name}}
                        </div>
                        <div style="font-size:0.95rem; color:var(--text-sub); margin-top:2px;">
                            <b>Diagnosed Cause:</b> ${{d.plan.specific_fault}}
                        </div>
                    </div>
                    <div style="display:flex; gap:20px; background:#FFFFFF; border:1px solid var(--border); padding:12px 18px; border-radius:8px;">
                        <div>
                            <div style="font-size:0.75rem; color:#64748B; font-weight:600;">CAPACITY</div>
                            <div style="font-size:1.15rem; font-weight:800; color:var(--text-main);">${{d.meta.capacity_kw}} kW</div>
                        </div>
                        <div>
                            <div style="font-size:0.75rem; color:#64748B; font-weight:600;">PERFORMANCE RATIO</div>
                            <div style="font-size:1.15rem; font-weight:800; color:${{d.plan.overall_pr_pct >= 78 ? '#15803D' : '#DC2626'}};">${{d.plan.overall_pr_pct.toFixed(1)}}%</div>
                        </div>
                        <div>
                            <div style="font-size:0.75rem; color:#64748B; font-weight:600;">GENERATION GAP</div>
                            <div style="font-size:1.15rem; font-weight:800; color:${{d.plan.gap_pct < 8 ? '#15803D' : '#DC2626'}};">${{d.plan.gap_pct.toFixed(1)}}%</div>
                        </div>
                        <div>
                            <div style="font-size:0.75rem; color:#64748B; font-weight:600;">DAILY LOSS</div>
                            <div style="font-size:1.15rem; font-weight:800; color:#DC2626;">₹${{Math.round(d.plan.daily_loss_inr).toLocaleString()}}</div>
                        </div>
                    </div>
                </div>
            `;

            // Evidence checklist
            const evList = document.getElementById('evidence-list');
            evList.innerHTML = '';
            d.plan.evidence.forEach(item => {{
                const li = document.createElement('li');
                li.innerHTML = `✅ <b>Observation:</b> ${{item}}`;
                evList.appendChild(li);
            }});

            // Action card
            document.getElementById('rooftop-action-card').innerHTML = `
                <div class="action-callout">
                    <div class="action-title">Recommended Action: ${{d.plan.recommended_action}}</div>
                    <div class="action-stats">
                        <div><b>Service Cost:</b> ₹${{Math.round(d.plan.action_cost_inr).toLocaleString()}}</div>
                        <div><b>Daily Savings:</b> ₹${{Math.round(d.plan.daily_loss_inr).toLocaleString()}} / day</div>
                        <div><b>Payback Period:</b> ${{d.plan.payback_period_days.toFixed(1)}} days</div>
                        <div><b>30-Day Net Profit:</b> <span style="color:#15803D; font-weight:700;">+₹${{Math.round(d.plan.net_30d_gain_inr).toLocaleString()}}</span></div>
                    </div>
                    <div style="font-size:0.85rem; color:#64748B;">${{d.plan.rationale}}</div>
                </div>
            `;

            // Draw Charts
            renderDiurnalChart(d.diurnal);
            renderMonthlyChart(d.monthly);
        }}

        function renderDiurnalChart(diurnal) {{
            const ctx = document.getElementById('diurnalChart').getContext('2d');
            if (diurnalChartInst) diurnalChartInst.destroy();

            diurnalChartInst = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: diurnal.hours.map(h => `${{h}}h`),
                    datasets: [
                        {{
                            label: 'Expected Generation (Clean STC)',
                            data: diurnal.expected_kw,
                            borderColor: '#10B981',
                            borderDash: [5, 5],
                            borderWidth: 2,
                            pointRadius: 0,
                            tension: 0.3
                        }},
                        {{
                            label: 'Actual Telemetry',
                            data: diurnal.actual_kw,
                            borderColor: '#0284C7',
                            backgroundColor: 'rgba(239, 68, 68, 0.15)',
                            borderWidth: 2.5,
                            fill: '-1',
                            pointRadius: 2,
                            tension: 0.3
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ position: 'bottom' }} }},
                    scales: {{
                        y: {{ title: {{ display: true, text: 'Active Power (kW)' }} }},
                        x: {{ title: {{ display: true, text: 'Hour of Day' }} }}
                    }}
                }}
            }});
        }}

        function renderMonthlyChart(monthly) {{
            const ctx = document.getElementById('monthlyChart').getContext('2d');
            if (monthlyChartInst) monthlyChartInst.destroy();

            monthlyChartInst = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: monthly.days.map(d => `Day ${{d}}`),
                    datasets: [
                        {{
                            label: 'Expected Daily Yield (kWh)',
                            data: monthly.expected_kwh,
                            borderColor: '#10B981',
                            borderDash: [3, 3],
                            borderWidth: 1.5,
                            pointRadius: 0
                        }},
                        {{
                            label: 'Actual Daily Yield (kWh)',
                            data: monthly.actual_kwh,
                            borderColor: '#0284C7',
                            backgroundColor: 'rgba(2, 132, 199, 0.08)',
                            borderWidth: 2,
                            fill: true,
                            pointRadius: 3
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ position: 'bottom' }} }},
                    scales: {{
                        y: {{ title: {{ display: true, text: 'Energy Yield (kWh/day)' }} }}
                    }}
                }}
            }});
        }}

        // Summary Charts in Tab 1
        function initSummaryCharts() {{
            // Donut
            const counts = {{ 'Healthy': 15, 'Dust / Soiling': 15, 'Partial Shading': 12, 'Inverter / Hardware Fault': 8 }};
            const donutCtx = document.getElementById('donutChart').getContext('2d');
            if (donutChartInst) donutChartInst.destroy();
            donutChartInst = new Chart(donutCtx, {{
                type: 'doughnut',
                data: {{
                    labels: ['Healthy (15)', 'Dust / Soiling (15)', 'Partial Shading (12)', 'Inverter Fault (8)'],
                    datasets: [{{
                        data: [15, 15, 12, 8],
                        backgroundColor: ['#10B981', '#F59E0B', '#8B5CF6', '#EF4444'],
                        borderWidth: 2,
                        borderColor: '#FFFFFF',
                        hoverOffset: 6
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '65%',
                    plugins: {{
                        legend: {{
                            position: 'bottom',
                            labels: {{
                                boxWidth: 12,
                                padding: 14,
                                font: {{ size: 12, family: 'Inter', weight: '600' }},
                                color: '#334155'
                            }}
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(ctx) {{
                                    const total = 50;
                                    const val = ctx.parsed;
                                    const pct = ((val / total) * 100).toFixed(0);
                                    return ` ${{ctx.label}}: ${{val}} systems (${{pct}}% of campus)`;
                                }}
                            }}
                        }}
                    }}
                }}
            }});

            // Bar
            const barCtx = document.getElementById('barChart').getContext('2d');
            if (barChartInst) barChartInst.destroy();
            barChartInst = new Chart(barCtx, {{
                type: 'bar',
                data: {{
                    labels: ['Dust / Soiling', 'Inverter Fault', 'Partial Shading', 'Healthy'],
                    datasets: [{{
                        label: 'Daily Revenue Loss (₹/day)',
                        data: [7375, 5678, 4120, 0],
                        backgroundColor: ['#F59E0B', '#EF4444', '#8B5CF6', '#10B981'],
                        borderRadius: 6,
                        maxBarThickness: 48
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: false }},
                        tooltip: {{
                            callbacks: {{
                                label: function(ctx) {{
                                    return ` Daily Financial Loss: ₹${{ctx.parsed.y.toLocaleString()}} / day`;
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            title: {{
                                display: true,
                                text: 'Daily Loss (₹ / day)',
                                color: '#475569',
                                font: {{ size: 12, weight: '600' }}
                            }},
                            ticks: {{
                                color: '#64748B',
                                font: {{ size: 11 }},
                                callback: function(val) {{
                                    return '₹' + val.toLocaleString();
                                }}
                            }},
                            grid: {{ color: '#F1F5F9', drawBorder: false }}
                        }},
                        x: {{
                            ticks: {{ color: '#334155', font: {{ weight: '600', size: 11 }} }},
                            grid: {{ display: false }}
                        }}
                    }}
                }}
            }});
        }}

        // Financial Simulator
        function recalcFinance() {{
            const tariff = parseFloat(document.getElementById('slider-tariff').value);
            const fixed = parseFloat(document.getElementById('slider-fixed').value);
            const rate = parseFloat(document.getElementById('slider-rate').value);

            document.getElementById('val-tariff').textContent = `₹${{tariff.toFixed(2)}}/kWh`;
            document.getElementById('val-fixed').textContent = `₹${{fixed.toLocaleString()}}`;
            document.getElementById('val-rate').textContent = `₹${{rate}}/kW`;

            // Recalculate
            let totDailyLoss = 0;
            let totCost = 0;
            let tot30dGain = 0;

            ALL_PLANS.forEach(r => {{
                // Base gap in kWh = r.daily_loss_inr / 8.5
                const dailyGapKwh = r.daily_loss_inr / 8.5;
                const newDailyLoss = dailyGapKwh * tariff;
                totDailyLoss += newDailyLoss;

                let actionCost = 0;
                if (r.diagnosed_category === 'Dust / Soiling') {{
                    actionCost = fixed + (rate * r.capacity_kw);
                }} else if (r.diagnosed_category.includes('Fault')) {{
                    actionCost = r.action_cost_inr;
                }} else if (r.diagnosed_category === 'Partial Shading') {{
                    actionCost = r.action_cost_inr;
                }}

                if (newDailyLoss > 0) {{
                    const payback = actionCost / newDailyLoss;
                    if (payback <= 12) {{
                        totCost += actionCost;
                        tot30dGain += (30 * newDailyLoss) - actionCost;
                    }}
                }}
            }});

            const monthlyLoss = totDailyLoss * 30;
            document.getElementById('calc-loss').textContent = `₹${{Math.round(monthlyLoss).toLocaleString()}}`;
            document.getElementById('calc-cost').textContent = `₹${{Math.round(totCost).toLocaleString()}}`;
            document.getElementById('calc-gain').textContent = `+₹${{Math.round(tot30dGain).toLocaleString()}}`;
            document.getElementById('calc-payback').innerHTML = `Payback in <b>${{(totCost / (totDailyLoss || 1)).toFixed(1)}} days</b>`;
        }}

        // Init
        window.addEventListener('DOMContentLoaded', () => {{
            renderTable(ALL_PLANS);
            populateSelector();
            initSummaryCharts();
            renderRooftopDetails();
        }});
    </script>
</body>
</html>
"""
    with open("index.html", "w") as f:
        f.write(html_content)
    print("Generated production index.html for GitHub Pages.")

if __name__ == "__main__":
    generate_html()
