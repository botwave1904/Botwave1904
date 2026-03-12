import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

class FleetIntelligence:
    def __init__(self):
        self.model = RandomForestRegressor(n_estimators=100)
        self.scaler = StandardScaler()
    
    def train(self, X, y):
        """Train intelligence model on fleet data"""
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
    
    def predict(self, X):
        """Generate predictive insights"""
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)
    
    def simulate_fleet_scenario(self, fleet_data):
        """Generate intelligent fleet simulation"""
        risks = self.predict(fleet_data)
        return {
            'overall_risk': np.mean(risks),
            'high_risk_vehicles': np.where(risks > risks.mean() + risks.std())[0]
        }

def generate_synthetic_fleet_data(n_vehicles=50):
    """Create synthetic fleet data for training"""
    vehicle_types = ['truck', 'van', 'car', 'bus']
    return {
        'vehicles': [np.random.choice(vehicle_types) for _ in range(n_vehicles)],
        'age': np.random.uniform(0, 10, n_vehicles),
        'miles_traveled': np.random.uniform(0, 100000, n_vehicles),
        'maintenance_score': np.random.uniform(0, 100, n_vehicles)
    }