"""
data_generator.py
Synthetic Telemetry Generator for 50 Campus Rooftop Solar Systems.
Generates 30 days of 1-hour resolution telemetry with realistic physics,
micro-weather, soiling accumulation, rain events, partial shading profiles,
and inverter hardware faults.
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

def generate_campus_dataset(output_dir="data", n_days=30, n_systems=50):
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Generate Rooftop Metadata
    # Campus buildings: Academic blocks, Hostels, Libraries, Sports Complex, Admin, Labs
    building_types = ["Academic_Block", "Hostel_Boys", "Hostel_Girls", "Central_Library", 
                      "Admin_Building", "Research_Lab", "Sports_Complex", "Dining_Hall", "Auditorium"]
    
    systems = []
    # Assign known ground-truth issues for realistic campus distribution:
    # ~15 Healthy
    # ~15 Soiling / Dust
    # ~12 Partial Shading (Eastern tree, Western building, Rooftop HVAC/parapet)
    # ~8 Inverter / Hardware Faults (String failure, Thermal clipping, Inverter degradation)
    
    issue_types = (
        ["HEALTHY"] * 15 + 
        ["SOILING"] * 15 + 
        ["SHADING_MORNING"] * 4 + 
        ["SHADING_AFTERNOON"] * 5 + 
        ["SHADING_MIDDAY"] * 3 + 
        ["INVERTER_STRING_FAULT"] * 3 + 
        ["INVERTER_THERMAL_CLIPPING"] * 3 + 
        ["INVERTER_DEGRADATION"] * 2
    )
    np.random.shuffle(issue_types)
    
    for i in range(1, n_systems + 1):
        b_type = np.random.choice(building_types)
        cap = float(np.random.choice([25.0, 40.0, 50.0, 75.0, 100.0]))  # kWp
        # Tilt between 15 and 25 degrees, Azimuth south (180 deg +/- 20 deg)
        tilt = np.round(np.random.uniform(18.0, 26.0), 1)
        azimuth = np.round(np.random.uniform(165.0, 195.0), 1)
        issue = issue_types[i - 1]
        
        systems.append({
            "system_id": f"ROOF_{i:02d}",
            "building_name": f"{b_type}_{((i-1)%10)+1}",
            "capacity_kw": cap,
            "tilt_deg": tilt,
            "azimuth_deg": azimuth,
            "inverter_brand": np.random.choice(["Sungrow", "SMA_SunnyTripower", "Huawei_FusionSolar", "Solis"]),
            "true_condition": issue,
            "inverter_nominal_eff": 0.975,
            "temp_coeff_pmax": -0.0038  # -0.38%/deg C
        })
        
    df_systems = pd.DataFrame(systems)
    df_systems.to_csv(os.path.join(output_dir, "campus_rooftop_metadata.csv"), index=False)
    print(f"Generated metadata for {n_systems} systems.")
    
    # 2. Generate Campus Weather Telemetry (30 days, hourly)
    start_date = datetime(2026, 10, 1, 0, 0)
    timestamps = [start_date + timedelta(hours=h) for h in range(n_days * 24)]
    
    # Create realistic diurnal irradiance and ambient temperature curves
    weather_records = []
    
    # Simulate a rain event on Day 18 (cleans dust!)
    rain_days = [18]
    
    for dt in timestamps:
        day_of_sim = (dt - start_date).days
        hour = dt.hour + dt.minute / 60.0
        
        # Solar elevation proxy (sunrise ~ 6:00, sunset ~ 18:00, peak ~ 12:00)
        if 6 <= hour <= 18:
            # Solar angle proxy
            solar_sin = np.sin((hour - 6) / 12.0 * np.pi)
            
            # Cloudiness factor: occasional passing clouds
            # e.g., Day 8 has high clouds, Day 18 has rain/overcast
            if day_of_sim == 18:
                cloud_factor = 0.25  # Rainy overcast
                rain_mm = np.random.uniform(5.0, 15.0) if 10 <= hour <= 14 else 0.0
            elif day_of_sim in [7, 8, 24]:
                cloud_factor = np.random.uniform(0.6, 0.85)  # Partly cloudy
                rain_mm = 0.0
            else:
                cloud_factor = np.random.uniform(0.92, 1.0)  # Clear sunny sky
                
            g_poa = float(np.clip(1000.0 * (solar_sin ** 1.1) * cloud_factor + np.random.normal(0, 8), 0, 1050))
            # Ambient temp peaks around 14:00 (2 PM)
            t_amb = float(22.0 + 12.0 * np.sin((hour - 8) / 14.0 * np.pi) + np.random.normal(0, 0.5))
        else:
            g_poa = 0.0
            t_amb = float(18.0 + np.random.normal(0, 0.5))
            rain_mm = 0.0
            
        wind_speed = float(np.clip(2.5 + np.random.normal(0, 1.0), 0.5, 8.0))
        
        weather_records.append({
            "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "g_poa": round(g_poa, 2),            # W/m^2 (Plane of Array Irradiance)
            "t_amb": round(t_amb, 2),            # deg C
            "wind_speed": round(wind_speed, 2),  # m/s
            "rain_mm": round(rain_mm, 2)
        })
        
    df_weather = pd.DataFrame(weather_records)
    df_weather.to_csv(os.path.join(output_dir, "campus_weather.csv"), index=False)
    print(f"Generated {len(df_weather)} weather timestamps.")
    
    # 3. Generate Rooftop Generation Telemetry with Synthetic Signatures
    gen_records = []
    weather_dict = {row["timestamp"]: row for row in weather_records}
    
    for sys in systems:
        sys_id = sys["system_id"]
        cap_kw = sys["capacity_kw"]
        issue = sys["true_condition"]
        gamma = sys["temp_coeff_pmax"]
        inv_nom_eff = sys["inverter_nominal_eff"]
        
        # Initial soiling level: some systems start with varying dust
        soiling_loss_rate = np.random.uniform(0.007, 0.012) if issue == "SOILING" else 0.001
        current_soiling = np.random.uniform(0.08, 0.15) if issue == "SOILING" else 0.01
        
        for dt in timestamps:
            ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            w = weather_dict[ts_str]
            g_poa = w["g_poa"]
            t_amb = w["t_amb"]
            rain_mm = w["rain_mm"]
            hour = dt.hour + dt.minute / 60.0
            
            if g_poa <= 5:
                # Nighttime / zero sun
                gen_records.append({
                    "timestamp": ts_str,
                    "system_id": sys_id,
                    "v_dc": 0.0,
                    "i_dc": 0.0,
                    "p_dc": 0.0,
                    "p_ac": 0.0,
                    "inverter_eff": 0.0,
                    "status_code": "SLEEP"
                })
                continue
                
            # Physics-based baseline expected cell temperature & power
            # King / Sandia cell temp approximation
            t_cell = t_amb + g_poa * (45.0 - 20.0) / 800.0  # NOCT = 45 C
            temp_derate = 1.0 + gamma * (t_cell - 25.0)
            
            # Expected DC power under clean STC conditions
            p_dc_ideal = cap_kw * (g_poa / 1000.0) * temp_derate * 0.98
            
            # Introduce Real-World Anomaly Modifiers:
            soiling_factor = 1.0
            shading_factor = 1.0
            inverter_factor = 1.0
            status_code = "NORMAL"
            
            # A) SOILING / DUST DYNAMICS
            if issue == "SOILING":
                # Dust accumulates steadily day by day: typical campus loss 15-30%
                if dt.hour == 0:
                    current_soiling += soiling_loss_rate
                # Rain cleans some dust, but leaves residual sticky dirt
                if rain_mm > 5.0:
                    current_soiling = 0.10 # Partial rain wash, leaving 10%
                current_soiling = float(np.clip(current_soiling, 0.15, 0.32)) # 15% to 32% loss
                soiling_factor = 1.0 - current_soiling
            else:
                if rain_mm > 5.0:
                    current_soiling = 0.01
                soiling_factor = 1.0 - current_soiling
                
            # B) PARTIAL SHADING DYNAMICS
            # Shading creates noticeable 15-30% overall daily loss
            if issue == "SHADING_MORNING":
                # Morning obstruction (East tall building/trees from 6am to 10:30am)
                if 6.0 <= hour <= 10.5:
                    shade_pct = 0.65 * (1.0 - (hour - 6.0) / 4.5)
                    shading_factor = 1.0 - shade_pct
                else:
                    shading_factor = 1.0
            elif issue == "SHADING_AFTERNOON":
                # Afternoon obstruction (West tower/parapet from 13:30 to 18:00)
                if 13.5 <= hour <= 18.0:
                    shade_pct = 0.65 * ((hour - 13.5) / 4.5)
                    shading_factor = 1.0 - shade_pct
                else:
                    shading_factor = 1.0
            elif issue == "SHADING_MIDDAY":
                # Overhead HVAC / chimney / high pole blocking midday rays (11:00 to 14:00)
                if 11.0 <= hour <= 14.0:
                    shading_factor = 0.58  # 42% drop at peak sun
                else:
                    shading_factor = 1.0
                    
            # C) INVERTER / HARDWARE ANOMALIES
            eff_actual = inv_nom_eff
            if issue == "INVERTER_STRING_FAULT":
                # 1 of 3 strings has blown fuse / disconnected -> exact 33.3% loss
                inverter_factor = 0.667
                status_code = "STRING_FAULT"
            elif issue == "INVERTER_THERMAL_CLIPPING":
                # Inverter internal cooling fan failed: clips when P_dc > 55% of rated
                max_thermal_cap = cap_kw * 0.55
                if p_dc_ideal > max_thermal_cap:
                    status_code = "THERMAL_DERATING"
            elif issue == "INVERTER_DEGRADATION":
                # Inverter power board degradation (loss of ~22% efficiency)
                eff_actual = 0.76
                status_code = "LOW_EFFICIENCY"
                
            # Apply all effects to DC and AC
            p_dc_actual = p_dc_ideal * soiling_factor * shading_factor * inverter_factor
            p_dc_actual = max(0.0, p_dc_actual + np.random.normal(0, 0.01 * cap_kw))
            
            # AC power after inverter conversion
            p_ac_actual = p_dc_actual * eff_actual
            
            # Check thermal clipping limit if applicable
            if issue == "INVERTER_THERMAL_CLIPPING" and p_ac_actual > cap_kw * 0.60:
                p_ac_actual = cap_kw * 0.60 + np.random.normal(0, 0.2)
                
            # Synthesize electrical measurements (Voltage and Current)
            # Typical string voltage ~ 600V nominal
            v_dc = 600.0 * (0.95 if shading_factor < 0.9 else 1.0) + np.random.normal(0, 5)
            i_dc = (p_dc_actual * 1000.0) / max(v_dc, 100.0)
            inverter_eff = (p_ac_actual / max(p_dc_actual, 0.001)) if p_dc_actual > 0.5 else 0.0
            
            gen_records.append({
                "timestamp": ts_str,
                "system_id": sys_id,
                "v_dc": round(v_dc, 1),
                "i_dc": round(i_dc, 2),
                "p_dc": round(p_dc_actual, 2),
                "p_ac": round(p_ac_actual, 2),
                "inverter_eff": round(inverter_eff, 4),
                "status_code": status_code
            })
            
    df_gen = pd.DataFrame(gen_records)
    df_gen.to_csv(os.path.join(output_dir, "rooftop_generation_telemetry.csv"), index=False)
    print(f"Generated {len(df_gen)} generation records across 50 systems.")

if __name__ == "__main__":
    generate_campus_dataset()
