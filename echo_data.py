from constants import CHARACTER_STAT_WEIGHTS, SUBSTAT_MAX_VALUES, MAIN_STAT_MULTIPLIER

class EchoData:
    """Echo data class (extended version)."""
    def __init__(self, cost: int, main_stat: str, substats: dict[str, float]):
        self.cost = cost
        self.main_stat = main_stat
        self.substats = substats
        self.level = 25
        self.score = 0.0
        self.rating = ""
        self.effective_stats_count = 0

    def calculate_score(self, stat_weights: dict[str, float] | None = None) -> float:
        """Standard score calculation (normalization method).

        Args:
            stat_weights: Dictionary of weights. If omitted, the weights for the general character are used.
        Returns:
            The calculated score.
        """
        if stat_weights is None:
            stat_weights = CHARACTER_STAT_WEIGHTS["General"]
        
        main_score = MAIN_STAT_MULTIPLIER
        sub_score = 0.0
        
        for stat_name, stat_value in self.substats.items():
            if stat_name in SUBSTAT_MAX_VALUES and stat_name in stat_weights:
                max_value = SUBSTAT_MAX_VALUES[stat_name]
                weight = stat_weights[stat_name]
                normalized = (stat_value / max_value / 5)
                sub_score += weight * normalized * 100
        
        self.score = (self.level / 25) * (main_score + sub_score)
        return self.score

    def calculate_score_normalized(self, stat_weights):
        """Method 1: Normalized Score (GameWith style) - 0-100 points"""
        main_score = 15.0
        sub_score = 0.0
        
        for stat_name, stat_value in self.substats.items():
            max_val = SUBSTAT_MAX_VALUES.get(stat_name, 1)
            weight = stat_weights.get(stat_name, 0)
            normalized = (stat_value / max_val / 5) * weight * 100
            sub_score += normalized
        
        total = (self.level / 25) * (main_score + sub_score)
        return total

    def calculate_score_ratio_based(self, importance_weights):
        """Method 2: Ratio-Based Method (Keisan style)"""
        score = 0.0
        
        for stat_name, stat_value in self.substats.items():
            max_val = SUBSTAT_MAX_VALUES.get(stat_name, 1)
            importance = importance_weights.get(stat_name, 0)
            ratio = (stat_value / max_val / 5) * importance
            score += ratio
        
        final_score = (100 * self.level / 25) * score
        return final_score

    def calculate_score_roll_quality(self, stat_weights):
        """Method 3: Roll Quality Method"""
        ROLL_RANGES = {
            "Crit. Rate": {"Max": 9.3, "Good": 8.7, "Low": 7.5},
            "Crit. DMG": {"Max": 18.6, "Good": 17.4, "Low": 15.0},
            "Energy Regen": {"Max": 10.8, "Good": 10.0, "Low": 8.4},
            "ATK %": {"Max": 10.2, "Good": 9.5, "Low": 8.1},
        }
        
        quality_points = 0
        count = 0
        
        for stat_name, stat_value in self.substats.items():
            if stat_name not in ROLL_RANGES:
                continue
                
            ranges = ROLL_RANGES[stat_name]
            weight = stat_weights.get(stat_name, 0.5)
            
            if stat_value >= ranges["Max"]:
                quality_points += 3 * weight
            elif stat_value >= ranges["Good"]:
                quality_points += 2 * weight
            elif stat_value >= ranges["Low"]:
                quality_points += 1 * weight
            else:
                quality_points += 0.5 * weight
            count += 1
        
        score = (quality_points / (count * 3)) * 100 if count > 0 else 0
        return score * (self.level / 25)


    def calculate_score_effective_stats(self, stat_weights, threshold=0.5):
        """Method 4: Effective Stats Count Method"""
        effective_count = 0
        total_contribution = 0
        
        for stat_name, stat_value in self.substats.items():
            weight = stat_weights.get(stat_name, 0)
            
            if weight >= threshold:
                effective_count += 1
                max_val = SUBSTAT_MAX_VALUES.get(stat_name, 1)
                contribution = (stat_value / max_val) * weight * 20
                total_contribution += contribution
        
        bonus_multiplier = {
            5: 1.2, 4: 1.1, 3: 1.0, 2: 0.8, 1: 0.6
        }.get(effective_count, 0.5)
        
        score = total_contribution * bonus_multiplier * (self.level / 25)
        self.effective_stats_count = effective_count
        return score

    def calculate_score_cv_based(self, stat_weights):
        """Method 5: CV (Crit Value) Based Method - Community Standard
        
        This is the most widely used method in the Wuthering Waves community.
        Formula: (Crit Rate × 2) + Crit DMG + (ATK% × 1.1) + (Flat ATK/10 × 1.2) + (ER × 0.5) + damage bonuses
        
        Evaluation criteria:
        - < 30: Needs improvement
        - 30-38: Acceptable
        - 38-50: Good
        - 50-70: Excellent
        - 70+: Outstanding
        """
        cv_score = 0.0
        
        # Basic CV calculation (most important)
        crit_rate = self.substats.get("クリティカル率", 0)
        crit_dmg = self.substats.get("クリティカルダメージ", 0)
        cv_score += (crit_rate * 2) + crit_dmg
        
        # Extended scoring with other valuable stats
        atk_pct = self.substats.get("攻撃力%", 0)
        flat_atk = self.substats.get("攻撃力", 0)
        er = self.substats.get("共鳴効率", 0)
        
        cv_score += (atk_pct * 1.1)
        cv_score += (flat_atk / 10 * 1.2)
        cv_score += (er * 0.5)
        
        # Character-specific damage bonuses (weighted by character preference)
        damage_bonus_stats = [
            "通常攻撃ダメージアップ", "重撃ダメージアップ", 
            "共鳴スキルダメージアップ", "共鳴解放ダメージアップ",
            "焦熱ダメージアップ", "凝縮ダメージアップ", "電導ダメージアップ",
            "気動ダメージアップ", "回折ダメージアップ", "消滅ダメージアップ"
        ]
        
        for stat_name in damage_bonus_stats:
            if stat_name in self.substats:
                stat_value = self.substats[stat_name]
                weight = stat_weights.get(stat_name, 0.5)
                # Damage bonuses are weighted by character preference and multiplied by 1.1
                cv_score += (stat_value * 1.1 * weight)
        
        # Level scaling
        final_score = cv_score * (self.level / 25)
        return final_score

    def evaluate_comprehensive(self, character_weights, enabled_methods=None):
        """Comprehensive evaluation (selected methods or all methods).
        
        Args:
            character_weights: Dictionary of stat weights for the character
            enabled_methods: Dictionary of {method_name: bool} indicating which methods to use.
                           If None, all methods are used.
        """
        # Default to all methods enabled if not specified
        if enabled_methods is None:
            enabled_methods = {
                "normalized": True,
                "ratio": True,
                "roll": True,
                "effective": True,
                "cv": True
            }
        
        # Calculate scores for enabled methods only
        results = {}
        if enabled_methods.get("normalized", False):
            results["normalized"] = self.calculate_score_normalized(character_weights)
        if enabled_methods.get("ratio", False):
            results["ratio"] = self.calculate_score_ratio_based(character_weights)
        if enabled_methods.get("roll", False):
            results["roll"] = self.calculate_score_roll_quality(character_weights)
        if enabled_methods.get("effective", False):
            results["effective"] = self.calculate_score_effective_stats(character_weights)
        if enabled_methods.get("cv", False):
            results["cv"] = self.calculate_score_cv_based(character_weights)
        
        # Calculate average score from enabled methods
        if results:
            avg_score = sum(results.values()) / len(results)
        else:
            avg_score = 0.0
        
        return {
            "individual_scores": results,
            "total_score": avg_score,
            "effective_count": self.effective_stats_count,
            "rating": self.get_rating(avg_score),
            "recommendation": "rec_continue" if avg_score < 50 else "rec_use"
        }

    def get_rating(self, score):
        """Score evaluation."""
        if score >= 100:
            return "rating_sss_single"
        elif score >= 90:
            return "rating_ss_single"
        elif score >= 80:
            return "rating_s_single"
        elif score >= 70:
            return "rating_a_single"
        elif score >= 60:
            return "rating_b_single"
        else:
            return "rating_c_single"

    def get_rating_normalized(self, score):
        """Normalized score evaluation (0-100 points)."""
        if score >= 90:
            return "rating_sss_norm"
        elif score >= 80:
            return "rating_ss_norm"
        elif score >= 70:
            return "rating_s_norm"
        else:
            return "rating_b_norm"

    def get_rating_ratio(self, score):
        """Ratio score evaluation."""
        if score >= 90:
            return "rating_perf_ratio"
        elif score >= 80:
            return "rating_exc_ratio"
        elif score >= 70:
            return "rating_good_ratio"
        elif score >= 60:
            return "rating_avg_ratio"
        else:
            return "rating_weak_ratio"

    def get_rating_roll(self, score):
        """Roll quality evaluation."""
        if score >= 90:
            return "rating_god_roll"
        elif score >= 80:
            return "rating_win_roll"
        elif score >= 70:
            return "rating_avg_roll"
        else:
            return "rating_bad_roll"

    def get_rating_effective(self, score, eff_count):
        """Effective stats count evaluation."""
        if eff_count >= 5 and score >= 90:
            return ("rating_perf_eff", score)
        elif eff_count >= 4 and score >= 80:
            return ("rating_exc_eff", score)
        elif eff_count >= 3 and score >= 70:
            return ("rating_good_eff", score)
        else:
            return ("rating_bad_eff", eff_count, score)

    def get_rating_cv(self, score):
        """CV (Crit Value) score evaluation - Community Standard.
        
        Based on widely-used community thresholds:
        - < 30: Needs improvement
        - 30-38: Acceptable (minimum passing grade)
        - 38-50: Good (target achieved)
        - 50-70: Excellent
        - 70+: Outstanding (SSS tier)
        """
        if score >= 70:
            return "rating_outstanding_cv"
        elif score >= 50:
            return "rating_excellent_cv"
        elif score >= 38:
            return "rating_good_cv"
        elif score >= 30:
            return "rating_acceptable_cv"
        else:
            return "rating_weak_cv"

    def to_dict(self):
        """Convert to dictionary format."""
        return {
            "cost": self.cost,
            "main_stat": self.main_stat,
            "substats": self.substats,
            "level": self.level,
            "score": self.score,
            "rating": self.rating,
            "effective_stats_count": self.effective_stats_count
        }

    def __str__(self):
        """String representation."""
        substats_str = "\n".join([
            f"  {name}: {value}" for name, value in self.substats.items()
        ])
        return (
            f"Cost {self.cost} - Level {self.level}\n"
            f"Main: {self.main_stat}\n"
            f"Substats:\n{substats_str}\n"
            f"Score: {self.score:.2f}\n"
            f"Rating: {self.rating}"
        )
