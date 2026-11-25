"""
expected_generation_model.py
Module for calculating expected solar rooftop generation using both:
1. Physics-based photovoltaic model (IEC 61724 / PVWatts standard)
2. Machine-learning baseline model (RandomForest/GradientBoosting)
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

class PhotovoltaicPhysicsModel:
    """
    Standard physics-based PV generation model:
    - Cell temperature estimation (Sandia/King empirical model)
    - Temperature derating factor
    - DC power model
    - Inverter non-linear conversion efficiency
    """
    def __init__(self, noct=45.0, temp_coeff=-0.0038, bop_eff=0.98, inv_nom_eff=0.975):
        self.noct = noct
        self.temp_coeff = temp_coeff
        self.bop_eff = bop_eff
        self.inv_nom_eff = inv_nom_eff

    def estimate_cell_temp(self, t_amb, g_poa):
        """
        Estimate PV module cell temperature based on ambient temp and POA irradiance.
        T_cell = T_amb + G_poa * (NOCT - 20) / 800
        """
        return t_amb + g_poa * (self.noct - 20.0) / 800.0

    def predict(self, capacity_kw, g_poa, t_amb):
        """
        Calculates expected DC and AC generation (kW) under clean, unshaded conditions.
        """
        # Vectorized support
        g_poa = np.maximum(0.0, np.array(g_poa))
        t_amb = np.array(t_amb)
        
        t_cell = self.estimate_cell_temp(t_amb, g_poa)
        temp_derate = 1.0 + self.temp_coeff * (t_cell - 25.0)
        
        # Expected DC power
        p_dc_exp = capacity_kw * (g_poa / 1000.0) * temp_derate * self.bop_eff
        p_dc_exp = np.maximum(0.0, p_dc_exp)
        
        # Inverter efficiency with light-load curve
        # Empirical inverter efficiency drops slightly at very low loading (< 10%)
        loading = np.where(capacity_kw > 0, p_dc_exp / capacity_kw, 0.0)
        inv_eff = np.where(loading > 0.1, self.inv_nom_eff, self.inv_nom_eff * (0.85 + 1.5 * loading))
        
        p_ac_exp = p_dc_exp * inv_eff
        # Cap at inverter maximum capacity
        p_ac_exp = np.minimum(p_ac_exp, capacity_kw)
        
        return {
            "t_cell": np.round(t_cell, 2),
            "p_dc_expected": np.round(p_dc_exp, 2),
            "p_ac_expected": np.round(p_ac_exp, 2)
        }

class MLGenerationModel:
    """
    Data-driven regression model trained on clear-sky, healthy periods.
    """
    def __init__(self):
        self.model = RandomForestRegressor(n_estimators=50, max_depth=10, random_state=42)
        self.is_trained = False

    def train(self, df_train):
        """
        df_train must contain: g_poa, t_amb, hour, capacity_kw, p_ac
        """
        features = ["g_poa", "t_amb", "hour", "capacity_kw"]
        X = df_train[features]
        y = df_train["p_ac"]
        self.model.fit(X, y)
        self.is_trained = True

    def predict(self, df_test):
        features = ["g_poa", "t_amb", "hour", "capacity_kw"]
        return self.model.predict(df_test[features])
