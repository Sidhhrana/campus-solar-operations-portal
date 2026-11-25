"""
run_pipeline.py
End-to-End Execution Pipeline:
- Loads campus solar telemetry
- Computes expected generation (Physics & ML)
- Runs root cause diagnosis
- Evaluates diagnostic precision/recall against ground truth
- Runs economic maintenance optimizer
- Exports ranked action plan and KPI metrics
"""

import os
import json
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, r2_score, mean_absolute_error

from expected_generation_model import PhotovoltaicPhysicsModel, MLGenerationModel
from diagnostic_engine import RooftopDiagnosticEngine
from maintenance_optimizer import EconomicMaintenanceOptimizer

def main():
    print("=" * 70)
    print("  CAMPUS SMART SOLAR ANALYTICS & ROOT-CAUSE DIAGNOSIS PIPELINE")
    print("=" * 70)
    
    data_dir = "data"
    output_dir = "outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Load Data
    print("\n[Step 1/5] Loading Telemetry and Metadata...")
    df_meta = pd.read_csv(os.path.join(data_dir, "campus_rooftop_metadata.csv"))
    df_weather = pd.read_csv(os.path.join(data_dir, "campus_weather.csv"))
    df_gen = pd.read_csv(os.path.join(data_dir, "rooftop_generation_telemetry.csv"))
    
    print(f" Loaded {len(df_meta)} rooftops, {len(df_weather)} weather intervals, and {len(df_gen)} telemetry records.")
    
    # Merge telemetry with weather
    df_merged = pd.merge(df_gen, df_weather, on="timestamp", how="left")
    
    # 2. Physics & ML Expected Generation Model
    print("\n[Step 2/5] Initializing Expected Generation Models...")
    physics_model = PhotovoltaicPhysicsModel()
    
    # Train ML baseline on Healthy rooftops
    healthy_ids = df_meta[df_meta["true_condition"] == "HEALTHY"]["system_id"].tolist()
    df_healthy = df_merged[df_merged["system_id"].isin(healthy_ids)].copy()
    df_healthy["dt"] = pd.to_datetime(df_healthy["timestamp"])
    df_healthy["hour"] = df_healthy["dt"].dt.hour + df_healthy["dt"].dt.minute / 60.0
    
    # Map capacity
    cap_map = dict(zip(df_meta["system_id"], df_meta["capacity_kw"]))
    df_healthy["capacity_kw"] = df_healthy["system_id"].map(cap_map)
    
    ml_model = MLGenerationModel()
    daylight_healthy = df_healthy[df_healthy["g_poa"] >= 50].copy()
    
    # Train-test split (first 20 days train, last 10 days test)
    train_mask = daylight_healthy["dt"].dt.day <= 20
    train_df = daylight_healthy[train_mask]
    test_df = daylight_healthy[~train_mask]
    
    ml_model.train(train_df)
    y_pred_ml = ml_model.predict(test_df)
    r2_ml = r2_score(test_df["p_ac"], y_pred_ml)
    mae_ml = mean_absolute_error(test_df["p_ac"], y_pred_ml)
    print(f" ML Expected Generation Model Trained: Test R^2 = {r2_ml:.4f}, MAE = {mae_ml:.2f} kW")
    
    # 3. Diagnosis Engine
    print("\n[Step 3/5] Running Root-Cause Diagnostic Engine on all 50 Rooftops...")
    diag_engine = RooftopDiagnosticEngine(physics_model)
    
    diagnoses = []
    for _, sys_row in df_meta.iterrows():
        s_id = sys_row["system_id"]
        df_sys = df_merged[df_merged["system_id"] == s_id].copy()
        res = diag_engine.analyze_rooftop(df_sys, sys_row)
        res["true_condition"] = sys_row["true_condition"]
        diagnoses.append(res)
        
    df_diag = pd.DataFrame([{k: v for k, v in d.items() if k != "daily_history"} for d in diagnoses])
    df_diag.to_csv(os.path.join(output_dir, "rooftop_diagnoses.csv"), index=False)
    print(f" Completed automated diagnosis for {len(df_diag)} systems.")
    
    # Map ground truth to top-level category for accuracy evaluation
    def map_true_cat(cond):
        if cond == "HEALTHY":
            return "Healthy"
        elif cond == "SOILING":
            return "Dust / Soiling"
        elif "SHADING" in cond:
            return "Partial Shading"
        else:
            return "Inverter / Hardware Fault"
            
    df_diag["true_category"] = df_diag["true_condition"].apply(map_true_cat)
    accuracy = (df_diag["diagnosed_category"] == df_diag["true_category"]).mean() * 100.0
    print(f" Diagnostic Engine Accuracy vs Ground Truth: {accuracy:.1f}%")
    
    # 4. Economic Maintenance Optimizer
    print("\n[Step 4/5] Executing Economic Maintenance Optimizer & Self-Paying Logic...")
    optimizer = EconomicMaintenanceOptimizer(electricity_tariff_inr=8.50)
    df_ranked_plan = optimizer.generate_ranked_plan(diagnoses)
    df_ranked_plan.to_csv(os.path.join(output_dir, "ranked_maintenance_plan.csv"), index=False)
    print(f" Generated prioritized maintenance plan for 50 systems.")
    
    # 5. Campus Executive Summary & KPIs
    print("\n[Step 5/5] Compiling Executive KPIs...")
    total_cap_kw = df_meta["capacity_kw"].sum()
    total_gen_kwh = df_diag["total_actual_kwh"].sum()
    total_exp_kwh = df_diag["total_expected_kwh"].sum()
    total_gap_kwh = df_diag["gap_kwh_30d"].sum()
    campus_pr = (total_gen_kwh / total_exp_kwh) * 82.0  # Normalized campus PR
    
    total_daily_loss = df_ranked_plan["daily_loss_inr"].sum()
    total_monthly_loss = df_ranked_plan["monthly_loss_inr"].sum()
    
    # Self-paying recoverable revenue
    actionable_plans = df_ranked_plan[df_ranked_plan["dispatch_decision"].isin(["DISPATCH NOW", "SCHEDULE SERVICE"])]
    actionable_cost = actionable_plans["action_cost_inr"].sum()
    actionable_net_gain_30d = actionable_plans["net_30d_gain_inr"].sum()
    
    kpis = {
        "total_systems": 50,
        "total_campus_capacity_kw": float(total_cap_kw),
        "total_30d_generation_kwh": float(round(total_gen_kwh, 1)),
        "total_30d_expected_kwh": float(round(total_exp_kwh, 1)),
        "total_30d_lost_energy_kwh": float(round(total_gap_kwh, 1)),
        "overall_energy_loss_pct": float(round((total_gap_kwh / total_exp_kwh) * 100.0, 1)),
        "daily_financial_loss_inr": float(round(total_daily_loss, 2)),
        "monthly_financial_loss_inr": float(round(total_monthly_loss, 2)),
        "annualized_financial_loss_inr": float(round(total_monthly_loss * 12, 2)),
        "actionable_maintenance_cost_inr": float(round(actionable_cost, 2)),
        "net_30d_profit_from_actions_inr": float(round(actionable_net_gain_30d, 2)),
        "ml_model_r2_score": float(round(r2_ml, 4)),
        "diagnostic_accuracy_pct": float(round(accuracy, 1)),
        "category_distribution": df_diag["diagnosed_category"].value_counts().to_dict()
    }
    
    with open(os.path.join(output_dir, "executive_kpis.json"), "w") as f:
        json.dump(kpis, f, indent=2)
        
    print("\n" + "=" * 70)
    print(" EXECUTIVE RESULTS SUMMARY")
    print("=" * 70)
    print(f"Total Campus Solar Capacity   : {total_cap_kw:,.0f} kWp (~{total_cap_kw/1000:.2f} MWp)")
    print(f"Systems Operating Healthy      : {kpis['category_distribution'].get('Healthy', 0)} / 50")
    print(f"Systems with Dust / Soiling    : {kpis['category_distribution'].get('Dust / Soiling', 0)} / 50")
    print(f"Systems with Partial Shading   : {kpis['category_distribution'].get('Partial Shading', 0)} / 50")
    print(f"Systems with Inverter Faults   : {kpis['category_distribution'].get('Inverter / Hardware Fault', 0)} / 50")
    print(f"Daily Campus Revenue Loss      : ₹{total_daily_loss:,.2f} / day")
    print(f"Monthly Campus Revenue Loss    : ₹{total_monthly_loss:,.2f} / month (₹{total_monthly_loss*12/100000:,.1f} Lakhs/yr)")
    print(f"Immediate Maintenance Budget   : ₹{actionable_cost:,.2f}")
    print(f"Net 30-Day Profit from Actions : ₹{actionable_net_gain_30d:,.2f}")
    print("=" * 70)
    print("\n Top 5 Urgent Maintenance Actions (Self-Paying Schedule):")
    print(df_ranked_plan[["rank", "system_id", "building_name", "diagnosed_category", "gap_pct", "daily_loss_inr", "action_cost_inr", "payback_period_days", "recommended_action"]].head(5).to_string(index=False))

if __name__ == "__main__":
    main()
