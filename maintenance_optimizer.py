"""
maintenance_optimizer.py
Economic Maintenance Optimizer for 50 Campus Rooftop Solar Systems.
Calculates ROI, Payback Period, Net 30-Day Gain, and builds a prioritized,
ranked maintenance plan where every recommended action pays for itself.
"""

import pandas as pd
import numpy as np

class EconomicMaintenanceOptimizer:
    def __init__(self, electricity_tariff_inr=8.50, fixed_mobilize_cost=1200.0, per_kw_clean_cost=25.0):
        """
        electricity_tariff_inr: Cost of campus grid electricity in INR per kWh (default ₹8.50/kWh)
        fixed_mobilize_cost: Fixed crew dispatch cost per site (default ₹1,200)
        per_kw_clean_cost: Variable cleaning cost per kW capacity (default ₹25/kW)
        """
        self.tariff = electricity_tariff_inr
        self.fixed_clean = fixed_mobilize_cost
        self.per_kw_clean = per_kw_clean_cost

    def evaluate_rooftop(self, diag_result):
        """
        Evaluates financial losses and generates an action recommendation with payback period.
        """
        sys_id = diag_result["system_id"]
        building = diag_result["building_name"]
        cap_kw = diag_result["capacity_kw"]
        category = diag_result["diagnosed_category"]
        specific_fault = diag_result["specific_fault"]
        gap_pct = diag_result["gap_pct"]
        daily_avg_gap_kwh = diag_result["daily_avg_gap_kwh"]
        confidence = diag_result["confidence_pct"]
        
        # Financial loss per day
        daily_loss_inr = daily_avg_gap_kwh * self.tariff
        monthly_loss_inr = daily_loss_inr * 30.0
        
        action = "None (Monitor Only)"
        action_cost_inr = 0.0
        payback_days = 999.0
        net_30d_gain_inr = 0.0
        dispatch_decision = "HOLD"
        urgency = "LOW"
        notes = "System operating within healthy thresholds."
        
        if category == "Dust / Soiling":
            # Cleaning cost based on capacity
            clean_cost = self.fixed_clean + (self.per_kw_clean * cap_kw)
            action_cost_inr = clean_cost
            
            if daily_loss_inr > 0:
                payback_days = clean_cost / daily_loss_inr
            else:
                payback_days = 999.0
                
            net_30d_gain_inr = (30.0 * daily_loss_inr) - clean_cost
            
            # Self-paying rule: Payback must be within 12 days to justify immediate cleaning
            if payback_days <= 12.0 and gap_pct >= 14.0:
                action = "Schedule Robotic / High-Pressure Cleaning"
                dispatch_decision = "DISPATCH NOW"
                urgency = "HIGH" if payback_days <= 6.0 else "MEDIUM"
                notes = f"Self-paying cleaning! Recovers cost in {payback_days:.1f} days, netting ₹{net_30d_gain_inr:,.0f} profit over 30 days."
            else:
                action = "Defer Cleaning (Monitor Soiling Rate)"
                dispatch_decision = "DEFER"
                urgency = "LOW"
                notes = f"Loss is currently too low ({gap_pct:.1f}%) to justify mobilization cost (Payback: {payback_days:.1f} days)."
                
        elif category == "Inverter / Hardware Fault":
            if "String" in specific_fault:
                action = "Inspect DC Combiner & Replace Blown String Fuse / Connector"
                action_cost_inr = 3500.0
                urgency = "CRITICAL"
            elif "Thermal" in specific_fault:
                action = "Service Inverter Heat Sink & Replace Failed Exhaust Fans"
                action_cost_inr = 6500.0
                urgency = "HIGH"
            else: # Degradation
                action = "Inverter Diagnostic Bench Test / Power Board Replacement"
                action_cost_inr = 15000.0
                urgency = "HIGH"
                
            payback_days = action_cost_inr / max(1.0, daily_loss_inr)
            net_30d_gain_inr = (30.0 * daily_loss_inr) - action_cost_inr
            dispatch_decision = "DISPATCH NOW"
            notes = f"Permanent hardware loss! Repair pays for itself in {payback_days:.1f} days. Net 30-day gain: ₹{net_30d_gain_inr:,.0f}."
            
        elif category == "Partial Shading":
            if "Morning" in specific_fault or "Afternoon" in specific_fault:
                action = "Campus Landscaping: Tree Canopy Pruning / Branch Clearance"
                action_cost_inr = 2500.0
                urgency = "MEDIUM"
            else:
                action = "Install DC Module Power Optimizers on Shaded String"
                action_cost_inr = 7500.0
                urgency = "MEDIUM"
                
            payback_days = action_cost_inr / max(1.0, daily_loss_inr)
            net_30d_gain_inr = (30.0 * daily_loss_inr) - action_cost_inr
            dispatch_decision = "SCHEDULE SERVICE"
            notes = f"Physical obstacle. Do NOT clean panels. Mitigation pays for itself in {payback_days:.1f} days."
            
        else: # Healthy
            action = "Routine Predictive Monitoring"
            action_cost_inr = 0.0
            payback_days = 0.0
            net_30d_gain_inr = 0.0
            dispatch_decision = "NO ACTION"
            urgency = "NONE"
            notes = "Performance Ratio healthy (>78%). No maintenance required."

        # Composite Priority Score for Ranking:
        # High financial return + High severity + Urgency weight
        urgency_weights = {"CRITICAL": 40.0, "HIGH": 25.0, "MEDIUM": 15.0, "LOW": 5.0, "NONE": 0.0}
        score = (0.35 * gap_pct) + (0.35 * min(100.0, max(0.0, net_30d_gain_inr / 250.0))) + urgency_weights.get(urgency, 0.0)
        
        return {
            "system_id": sys_id,
            "building_name": building,
            "capacity_kw": cap_kw,
            "diagnosed_category": category,
            "specific_fault": specific_fault,
            "confidence_pct": confidence,
            "gap_pct": gap_pct,
            "daily_avg_gap_kwh": daily_avg_gap_kwh,
            "daily_loss_inr": round(daily_loss_inr, 2),
            "monthly_loss_inr": round(monthly_loss_inr, 2),
            "recommended_action": action,
            "action_cost_inr": round(action_cost_inr, 2),
            "payback_period_days": round(payback_days, 1),
            "net_30d_gain_inr": round(net_30d_gain_inr, 2),
            "dispatch_decision": dispatch_decision,
            "urgency": urgency,
            "priority_score": round(score, 1),
            "rationale": notes
        }

    def generate_ranked_plan(self, all_diagnoses):
        """
        Evaluates and ranks all rooftops from highest priority to lowest.
        """
        results = [self.evaluate_rooftop(d) for d in all_diagnoses]
        df_plan = pd.DataFrame(results)
        # Sort descending by priority score
        df_plan = df_plan.sort_values(by="priority_score", ascending=False).reset_index(drop=True)
        df_plan["rank"] = range(1, len(df_plan) + 1)
        
        cols = ["rank", "system_id", "building_name", "capacity_kw", "diagnosed_category", 
                "specific_fault", "gap_pct", "daily_loss_inr", "monthly_loss_inr", 
                "recommended_action", "action_cost_inr", "payback_period_days", 
                "net_30d_gain_inr", "dispatch_decision", "urgency", "priority_score", "rationale"]
        return df_plan[cols]
