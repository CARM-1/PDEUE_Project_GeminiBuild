class DynamicSpreadKellyRegime:
    def __init__(self, base_fraction: float = 0.25, defensive_floor: float = 0.05, max_spread: float = 0.05):
        self.base_fraction = base_fraction
        self.defensive_floor = defensive_floor
        self.max_spread = max_spread

    def calculate_active_fraction(self, current_spread: float) -> float:
        if current_spread <= 0.01:
            return round(self.base_fraction, 4)
        if current_spread >= self.max_spread:
            return round(self.defensive_floor, 4)
        ratio = (current_spread - 0.01) / (self.max_spread - 0.01)
        fraction = self.base_fraction - ratio * (self.base_fraction - self.defensive_floor)
        return round(max(self.defensive_floor, min(self.base_fraction, fraction)), 4)
