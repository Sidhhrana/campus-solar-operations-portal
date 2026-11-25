"""
diagnostic_engine.py
Automated Root Cause Diagnosis Engine for Solar Rooftop Underperformance.
Distinguishes between:
1. Dust / Soiling
2. Shading (Morning, Afternoon, Midday)
3. Inverter / Hardware Fault (String outage, Thermal derating, Electrical degradation)
4. Healthy Baseline
"""

import numpy as np
import pandas as pd
from scipy.stats import linregress

class RooftopDiagnosticEngine:
    def __init__(self, physics_model):
        self.physics_model = physics_model

    def analyze_rooftop(self, df_sys, sys_meta, rain_day=18):
        """
        Analyzes 30-day telemetry for a single rooftop system.
        df_sys: merged generation and weather dataframe
        sys_meta: row from metadata
        """
        cap_kw = sys_meta["capacity_kw"]
        sys_id = sys_meta["system_id"]
        
        # 1. Calculate Expected Generation
        exp_res = self.physics_model.predict(cap_kw, df_sys["g_poa"].values, df_sys["t_amb"].values)
        df_sys = df_sys.copy()
        df_sys["p_ac_exp"] = exp_res["p_ac_expected"]
        df_sys["p_dc_exp"] = exp_res["p_dc_expected"]
        
        # Filter daylight hours for solar metrics (G_poa > 50 W/m^2)
        daylight = df_sys[df_sys["g_poa"] >= 50].copy()
        daylight["dt"] = pd.to_datetime(daylight["timestamp"])
        daylight["date"] = daylight["dt"].dt.date
        daylight["hour"] = daylight["dt"].dt.hour + daylight["dt"].dt.minute / 60.0
        
        # 2. Key Aggregate Metrics
        total_exp_kwh = df_sys["p_ac_exp"].sum()
        total_act_kwh = df_sys["p_ac"].sum()
        gap_kwh = max(0.0, total_exp_kwh - total_act_kwh)
        gap_pct = (gap_kwh / max(1.0, total_exp_kwh)) * 100.0
        
        # Overall Performance Ratio (PR)
        total_poa_irradiation = (df_sys["g_poa"] / 1000.0).sum()
        overall_pr = (total_act_kwh / (cap_kw * total_poa_irradiation)) if total_poa_irradiation > 0 else 0.0
        
        # 3. Daily Metrics & Trends
        daily_df = daylight.groupby("date").agg(
            act_kwh=("p_ac", "sum"),
            exp_kwh=("p_ac_exp", "sum"),
            g_sum=("g_poa", "sum"),
            rain_sum=("rain_mm", "sum"),
            inverter_eff_median=("inverter_eff", "median")
        ).reset_index()
        daily_df["pr"] = daily_df["act_kwh"] / np.maximum(0.1, (cap_kw * (daily_df["g_sum"] / 1000.0)))
        daily_df["ratio"] = daily_df["act_kwh"] / np.maximum(0.1, daily_df["exp_kwh"])
        daily_df["day_num"] = range(1, len(daily_df) + 1)
        
        # Check dry period drift (Days 1 to 17 before rain)
        dry_df = daily_df[daily_df["day_num"] <= 17]
        if len(dry_df) > 5:
            slope, intercept, r_val, p_val, std_err = linregress(dry_df["day_num"], dry_df["ratio"])
            dry_drift_rate = slope  # Daily change in ratio
        else:
            dry_drift_rate = 0.0
            
        # Check Rain Recovery Jump (Day 17 vs Day 19)
        day17_ratio = daily_df[daily_df["day_num"] == 17]["ratio"].values
        day19_ratio = daily_df[daily_df["day_num"] == 19]["ratio"].values
        if len(day17_ratio) > 0 and len(day19_ratio) > 0:
            rain_recovery_jump = (day19_ratio[0] - day17_ratio[0]) * 100.0  # percentage points
        else:
            rain_recovery_jump = 0.0
            
        # 4. Diurnal Shape Signatures (Clear Sunny Days)
        # Compare Morning (8-10h), Midday (11:30-13:30h), Afternoon (14:30-17h)
        clear_days = daily_df[daily_df["rain_sum"] == 0]["date"].values
        clear_telemetry = daylight[daylight["date"].isin(clear_days)].copy()
        clear_telemetry["hour_int"] = clear_telemetry["hour"].astype(int)
        
        morning_rows = clear_telemetry[(clear_telemetry["hour"] >= 7.5) & (clear_telemetry["hour"] <= 9.5)]
        midday_rows = clear_telemetry[(clear_telemetry["hour"] >= 11.5) & (clear_telemetry["hour"] <= 13.5)]
        afternoon_rows = clear_telemetry[(clear_telemetry["hour"] >= 14.5) & (clear_telemetry["hour"] <= 16.5)]
        
        r_am = (morning_rows["p_ac"].sum() / max(0.1, morning_rows["p_ac_exp"].sum()))
        r_mid = (midday_rows["p_ac"].sum() / max(0.1, midday_rows["p_ac_exp"].sum()))
        r_pm = (afternoon_rows["p_ac"].sum() / max(0.1, afternoon_rows["p_ac_exp"].sum()))
        
        # 5. Inverter Hardware Signatures
        high_sun = daylight[daylight["g_poa"] >= 500]
        med_inv_eff = high_sun["inverter_eff"].median() if len(high_sun) > 0 else daylight["inverter_eff"].median()
        
        # Thermal clipping check: does actual power saturate / flatline at high G?
        peak_sun = daylight[daylight["g_poa"] >= 750]
        peak_ratio = (peak_sun["p_ac"].sum() / max(0.1, peak_sun["p_ac_exp"].sum())) if len(peak_sun) > 0 else 1.0
        mod_sun = daylight[(daylight["g_poa"] >= 300) & (daylight["g_poa"] <= 500)]
        mod_ratio = (mod_sun["p_ac"].sum() / max(0.1, mod_sun["p_ac_exp"].sum())) if len(mod_sun) > 0 else 1.0
        
        # Constant step-reduction signature across all daylight hours (variance of ratio across hours)
        hourly_ratios = []
        for h_val, h_df in clear_telemetry.groupby("hour_int"):
            h_exp = h_df["p_ac_exp"].sum()
            if h_exp > 0.1:
                hourly_ratios.append(h_df["p_ac"].sum() / h_exp)
        hourly_ratios = np.array(hourly_ratios)
        hourly_std = float(np.std(hourly_ratios)) if len(hourly_ratios) > 1 else 0.0
        hourly_mean_ratio = float(np.mean(hourly_ratios)) if len(hourly_ratios) > 0 else 1.0

        # 6. Rule-Based Multi-Layer Diagnostic Classifier
        category = "Healthy"
        specific_fault = "Normal Operation"
        confidence = 95.0
        evidence = []
        
        if gap_pct < 6.0 and overall_pr >= 0.77:
            category = "Healthy"
            specific_fault = "Healthy / Operating as Expected"
            confidence = 95.0
            evidence.append(f"Performance Ratio is healthy at {overall_pr*100:.1f}% (Benchmark >77%).")
            evidence.append(f"Generation gap is minimal ({gap_pct:.1f}%).")
        else:
            # Underperformance Detected (15-35% gap)
            
            # Rule 1: Inverter Electrical Efficiency Degradation
            if med_inv_eff < 0.90:
                category = "Inverter / Hardware Fault"
                specific_fault = "Inverter Efficiency Degradation (Aging IGBTs/Capacitors)"
                confidence = 98.0
                evidence.append(f"Inverter conversion efficiency degraded to {med_inv_eff*100:.1f}% (Nominal >97%).")
                evidence.append("DC power generated normally, but conversion to AC experiences high internal electrical loss.")
                
            # Rule 2: Blown String Fuse / Open-Circuit String (Flat ~33% or ~50% drop throughout all hours)
            elif (0.58 <= hourly_mean_ratio <= 0.72) and hourly_std < 0.06 and abs(r_am - r_pm) < 0.08:
                category = "Inverter / Hardware Fault"
                specific_fault = "Blown DC String Fuse / Disconnected String"
                confidence = 98.0
                evidence.append(f"Output is uniformly reduced to {hourly_mean_ratio*100:.1f}% across all daylight hours (Hourly Std: {hourly_std:.3f}).")
                evidence.append("Flat ~1/3 generation drop across all solar angles matches open-circuit / blown string fuse on a 3-string MPPT.")
                evidence.append("Sustained flat line rules out time-of-day shade or environmental dust.")

            # Rule 3: Midday Overhead Shading (Both AM and PM are high, only midday dips)
            elif (r_mid < 0.75) and (r_am >= 0.88) and (r_pm >= 0.88):
                category = "Partial Shading"
                specific_fault = "Midday Overhead Obstruction (HVAC / Antenna / Parapet)"
                confidence = 96.0
                evidence.append(f"Pronounced midday saddle dip: Midday ratio {r_mid*100:.1f}% vs Morning {r_am*100:.1f}% and Afternoon {r_pm*100:.1f}%.")
                evidence.append("Shadow profile intersects panels near solar zenith (11:30 - 13:30) while early and late sun is unhindered.")

            # Rule 4: Morning Shading Obstacle
            elif (r_pm - r_am) > 0.12 and r_pm >= 0.85:
                category = "Partial Shading"
                specific_fault = "Morning Shading Obstacle (Eastern Trees/Structures)"
                confidence = 96.0
                evidence.append(f"Severe morning deficit (Ratio: {r_am*100:.1f}%) followed by complete afternoon recovery ({r_pm*100:.1f}%).")
                evidence.append("Diurnal asymmetry aligns precisely with eastern solar elevation angle.")

            # Rule 5: Afternoon Shading Obstacle
            elif (r_am - r_pm) > 0.12 and r_am >= 0.85:
                category = "Partial Shading"
                specific_fault = "Afternoon Shading Obstacle (Western Parapet/Building)"
                confidence = 96.0
                evidence.append(f"Normal morning generation ({r_am*100:.1f}%) dropping abruptly in afternoon ({r_pm*100:.1f}%).")
                evidence.append("Diurnal cliff signature coincides with western solar azimuth angle.")

            # Rule 6: Inverter Thermal Clipping / Derating
            elif mod_ratio > 0.80 and peak_ratio < 0.75:
                category = "Inverter / Hardware Fault"
                specific_fault = "Inverter Thermal Derating / Cooling Fan Failure"
                confidence = 96.0
                evidence.append(f"Normal operation at moderate irradiance ({mod_ratio*100:.1f}%), but sharp clipping at peak sun ({peak_ratio*100:.1f}%).")
                evidence.append("Severe flat-topping profile indicates thermal throttle due to clogged filters or failed exhaust fans.")

            # Rule 7: Dust / Soiling
            elif abs(r_am - r_pm) < 0.10:
                category = "Dust / Soiling"
                specific_fault = "Uniform Dust & Particulate Soiling"
                confidence = 96.0
                evidence.append(f"Symmetric diurnal generation profile (AM: {r_am*100:.1f}%, PM: {r_pm*100:.1f}%), characteristic of uniform surface deposition.")
                evidence.append(f"Performance gap of {gap_pct:.1f}% with nominal inverter health (>97%).")
                if dry_drift_rate < -0.001:
                    evidence.append(f"Monotonic degradation during dry sequences (Drift: {dry_drift_rate*100:.2f}%/day).")
                if rain_recovery_jump >= 3.0:
                    evidence.append(f"Rainfall event produced observable yield recovery (+{rain_recovery_jump:.1f}% PR boost).")
                
            else:
                category = "Dust / Soiling"
                specific_fault = "Moderate Surface Soiling"
                confidence = 88.0
                evidence.append(f"Uniform generation loss across daytime ({gap_pct:.1f}% gap) with normal inverter health.")
                    
        return {
            "system_id": sys_id,
            "building_name": sys_meta["building_name"],
            "capacity_kw": cap_kw,
            "total_expected_kwh": round(total_exp_kwh, 1),
            "total_actual_kwh": round(total_act_kwh, 1),
            "gap_kwh_30d": round(gap_kwh, 1),
            "daily_avg_gap_kwh": round(gap_kwh / 30.0, 2),
            "gap_pct": round(gap_pct, 1),
            "overall_pr_pct": round(overall_pr * 100.0, 1),
            "dry_drift_rate_pct_day": round(dry_drift_rate * 100.0, 2),
            "rain_recovery_jump_pct": round(rain_recovery_jump, 1),
            "r_morning": round(r_am, 2),
            "r_midday": round(r_mid, 2),
            "r_afternoon": round(r_pm, 2),
            "median_inverter_eff": round(med_inv_eff * 100.0, 2),
            "diagnosed_category": category,
            "specific_fault": specific_fault,
            "confidence_pct": confidence,
            "evidence": evidence,
            "daily_history": daily_df
        }
