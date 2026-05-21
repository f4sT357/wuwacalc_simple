"""
Score Calculation Module (PyQt6)

Provides the logic for calculating Echo scores.
"""

from PyQt6.QtWidgets import QMessageBox
from typing import Dict

from constants import CHARACTER_STAT_WEIGHTS
from echo_data import EchoData
from languages import TRANSLATIONS


class ScoreCalculator:
    """Class responsible for score calculation."""
    
    def __init__(self, app):
        """
        Initialization
        
        Args:
            app: The main application instance.
        """
        self.app = app
    
    def calculate_all_scores(self) -> None:
        """Calculate all scores (supports mode selection)."""
        try:
            character = self.app.character_var
            weights = CHARACTER_STAT_WEIGHTS.get(character, CHARACTER_STAT_WEIGHTS["General"])
            score_mode = self.app.score_mode_var
            
            if score_mode == "single":
                self.calculate_single_score(weights, character)
            else:
                self.calculate_batch_scores(weights, character)
                
        except Exception as e:
            self.app.logger.exception(f"An error occurred during score calculation: {e}")
            self.app.gui_log(f"An error occurred during score calculation:\n{e}")
            QMessageBox.critical(self.app, "Error", f"An error occurred during score calculation:\n{e}")
    
    def extract_substats(self, content: dict) -> dict:
        """Extract substats from tab content."""
        substats = {}
        for stat_widget, value_widget in content["sub_entries"]:
            stat_name = stat_widget.currentText()
            value_str = value_widget.text()
            if stat_name and value_str:
                try:
                    value = float(value_str)
                    substats[stat_name] = value
                except ValueError:
                    continue
        return substats
    
    def calculate_single_score(self, weights: dict, character: str) -> None:
        """Calculate a single score (detailed display of selected evaluation types)."""
        try:
            if self.app.notebook is None:
                QMessageBox.warning(self.app, "Warning", "No tab selected.")
                return

            index = self.app.notebook.currentIndex()
            if index == -1:
                QMessageBox.warning(self.app, "Warning", "No tab selected.")
                return
                
            # Get the internal tab name (not the translated label)
            tab_name = self.app.tab_mgr.get_selected_tab_name()
            if not tab_name or tab_name not in self.app.tabs_content:
                QMessageBox.critical(self.app, "Error", "Tab information not found.")
                return
            
            # Get enabled calculation methods from config
            enabled_methods = self.app.app_config.enabled_calc_methods
            
            # Validate that at least one method is enabled
            if not any(enabled_methods.values()):
                QMessageBox.warning(self.app, self.app.tr("warning"), 
                                  self.app.tr("no_methods_selected"))
                return
            
            content = self.app.tabs_content[tab_name]
            main_stat = content["main_widget"].currentText()
            
            self.app.result_text.clear()
            
            if not main_stat:
                self.app.result_text.append(f"The main stat for {tab_name} is not entered.")
                return
            
            substats = self.extract_substats(content)
            
            echo = EchoData(content["cost"], main_stat, substats)
            
            # Calculate scores using enabled methods only
            evaluation = echo.evaluate_comprehensive(weights, enabled_methods)
            
            # --- Result Display ---
            html = self._generate_single_score_html(
                character, tab_name, content, main_stat, echo, evaluation
            )
            
            self.app.result_text.setHtml(html)
            
            # Save calculation result for each tab
            self.app.tab_mgr.save_tab_result(tab_name)
            
            self.app.gui_log(f"Individual evaluation for {tab_name} complete.")
            
        except Exception as e:
            self.app.logger.exception(f"Individual score calculation error: {e}")
            self.app.gui_log(f"Individual score calculation error: {e}")
            QMessageBox.critical(self.app, "Error", f"Individual score calculation error:\n{e}")
    
    def calculate_batch_scores(self, weights: dict, character: str) -> None:
        """Calculate scores in batch (detailed display of selected evaluation types)."""
        try:
            # Get enabled calculation methods from config
            enabled_methods = self.app.app_config.enabled_calc_methods
            
            # Validate that at least one method is enabled
            if not any(enabled_methods.values()):
                QMessageBox.warning(self.app, self.app.tr("warning"), 
                                  self.app.tr("no_methods_selected"))
                return
            
            all_evaluations = []
            # Build total_scores dict based on enabled methods
            total_scores = {"total": 0.0}
            for method in ["normalized", "ratio", "roll", "effective", "cv"]:
                if enabled_methods.get(method, False):
                    total_scores[method] = 0.0
            
            calculated_count = 0
            
            for tab_name, content in self.app.tabs_content.items():
                try:
                    main_stat = content["main_widget"].currentText()
                    if not main_stat:
                        continue
                    
                    substats = self.extract_substats(content)
                    
                    echo = EchoData(content["cost"], main_stat, substats)
                    
                    evaluation = echo.evaluate_comprehensive(weights, enabled_methods)
                    
                    # Build evaluation data with only enabled methods
                    eval_data = {
                        "tab_name": tab_name,
                        "effective_count": evaluation['effective_count'],
                        "total": evaluation['total_score'],
                        "recommendation": TRANSLATIONS.get(self.app.language, TRANSLATIONS["en"])[evaluation['recommendation']]
                    }
                    
                    # Add scores for enabled methods
                    for method, score in evaluation['individual_scores'].items():
                        eval_data[method] = score
                        total_scores[method] += score
                    
                    all_evaluations.append(eval_data)
                    total_scores["total"] += evaluation['total_score']
                    calculated_count += 1
                    
                except Exception as e:
                    self.app.logger.exception(f"Calculation error for {tab_name}: {e}")
                    self.app.gui_log(f"Calculation error for {tab_name}: {e}")
            
            self.app.result_text.clear()
            
            if calculated_count == 0:
                self.app.result_text.setText("No data available.\n")
            else:
                html = self._generate_batch_score_html(
                    character, calculated_count, all_evaluations, total_scores, enabled_methods
                )
                self.app.result_text.setHtml(html)
                self.app.gui_log(f"Batch calculation for {character} complete ({calculated_count} echoes).")
                
        except Exception as e:
            self.app.logger.exception(f"Batch calculation error: {e}")
            self.app.gui_log(f"Batch calculation error: {e}")
            QMessageBox.critical(self.app, "Error", f"Batch calculation error:\n{e}")
    
    def get_score_rating(self, total_score: float) -> str:
        """Get the rating for the total score."""
        if total_score >= 500:
            return "rating_sss_global"
        elif total_score >= 450:
            return "rating_ss_global"
        elif total_score >= 400:
            return "rating_s_global"
        elif total_score >= 350:
            return "rating_a_global"
        elif total_score >= 300:
            return "rating_b_global"
        else:
            return "rating_c_global"

    def _get_rating_color(self, rating_text: str) -> str:
        """Get the appropriate color from the rating text."""
        if any(keyword in rating_text for keyword in ["SSS", "Perfect", "God"]):
            return "#FF4500"
        elif any(keyword in rating_text for keyword in ["SS", "Top", "Excellent"]):
            return "#FF7F50"
        elif any(keyword in rating_text for keyword in ["S", "Win"]):
            return "#1E90FF"
        elif any(keyword in rating_text for keyword in ["A", "Good", "Practical"]):
            return "#32CD32"
        return "#666666"

    def _generate_single_score_html(self, character, tab_name, content, main_stat, echo, evaluation):
        """Generate HTML for single score result (dynamic based on enabled methods)."""
        html = f"<h3><u>{character} - {tab_name} Individual Score</u></h3>"
        html += f"<hr>"
        
        html += f"<b>Echo Information</b><br>"
        html += f"Cost: {content['cost']}<br>"
        html += f"Main Stat: {main_stat}<br>"
        html += f"Level: {echo.level}<br>"
        html += f"Number of Effective Substats: {evaluation['effective_count']}<br>"
        
        html += f"<br><b>Substats</b><br>"
        substats = echo.substats
        if substats:
            for name, value in substats.items():
                html += f"&nbsp;&nbsp;• {name}: {value}<br>"
        else:
            html += "None<br>"
        html += f"<br><hr>"
        
        html += f"<b>Score by Evaluation Method</b><br>"
        
        def format_score_block(label, score, rating_info, desc):
            block = f"[{label}]<br>"
            block += f"<b>Score: {score:.2f}</b><br>"
            
            if isinstance(rating_info, tuple):
                rating_key = rating_info[0]
                rating_args = rating_info[1:]
                rating_text = TRANSLATIONS.get(self.app.language, TRANSLATIONS["en"])[rating_key].format(*rating_args)
            else:
                rating_text = TRANSLATIONS.get(self.app.language, TRANSLATIONS["en"])[rating_info]

            color = self._get_rating_color(rating_text)
            block += f"<span style='color:{color}'>Rating: {rating_text}</span><br>"
            block += f"Description: {desc}<br><br>"
            return block

        # Method labels and descriptions
        method_info = {
            "normalized": {
                "label": self.app.tr("normalized_score_label"),
                "desc": self.app.tr("normalized_score_desc"),
                "rating_func": lambda s: echo.get_rating_normalized(s)
            },
            "ratio": {
                "label": self.app.tr("ratio_score_label"),
                "desc": self.app.tr("ratio_score_desc"),
                "rating_func": lambda s: echo.get_rating_ratio(s)
            },
            "roll": {
                "label": self.app.tr("roll_quality_label"),
                "desc": self.app.tr("roll_quality_desc"),
                "rating_func": lambda s: echo.get_rating_roll(s)
            },
            "effective": {
                "label": self.app.tr("effective_stat_label"),
                "desc": self.app.tr("effective_stat_desc"),
                "rating_func": lambda s: echo.get_rating_effective(s, evaluation['effective_count'])
            },
            "cv": {
                "label": self.app.tr("cv_score_label"),
                "desc": self.app.tr("cv_score_desc"),
                "rating_func": lambda s: echo.get_rating_cv(s)
            }
        }
        
        # Display only enabled methods
        for method, score in evaluation['individual_scores'].items():
            if method in method_info:
                info = method_info[method]
                rating = info["rating_func"](score)
                html += format_score_block(info["label"], score, rating, info["desc"])

        html += f"<hr>"
        html += f"<b>Overall Evaluation</b><br>"
        html += f"<b>Total Score: {evaluation['total_score']:.2f}</b><br>"
        
        final_rating = TRANSLATIONS.get(self.app.language, TRANSLATIONS["en"])[evaluation['rating']]
        final_color = self._get_rating_color(final_rating)
        
        html += f"<span style='color:{final_color}'>Overall Rating: {final_rating}</span><br>"
        html += f"Recommendation: {TRANSLATIONS.get(self.app.language, TRANSLATIONS['en'])[evaluation['recommendation']]}<br>"
        
        return html

    def _generate_batch_score_html(self, character, calculated_count, all_evaluations, total_scores, enabled_methods):
        """Generate HTML for batch score result (dynamic based on enabled methods)."""
        html = f"<h3><u>{character} Echo Scores (Batch Calculation)</u></h3>"
        html += f"<hr>"
        html += f"Calculated: {calculated_count} / {len(self.app.tabs_content)} echoes<br>"
        html += f"<hr>"
        
        # Method display info
        method_labels = {
            "normalized": self.app.tr("method_normalized"),
            "ratio": self.app.tr("method_ratio"),
            "roll": self.app.tr("method_roll"),
            "effective": self.app.tr("method_effective"),
            "cv": self.app.tr("method_cv")
        }
        
        for i, eval_data in enumerate(all_evaluations, 1):
            html += f"<b>--- Echo {i}: {eval_data['tab_name']} ---</b><br>"
            
            # Display scores for enabled methods only
            method_num = 1
            for method in ["normalized", "ratio", "roll", "effective", "cv"]:
                if enabled_methods.get(method, False) and method in eval_data:
                    score = eval_data[method]
                    label = method_labels.get(method, method)
                    
                    # Special handling for effective stats
                    if method == "effective":
                        html += f"├ [{method_num}] {label}: {score:.2f} ({eval_data['effective_count']} stats)<br>"
                    else:
                        html += f"├ [{method_num}] {label}: {score:.2f}<br>"
                    method_num += 1
            
            score_color = "#666666" # C/B default
            if eval_data['total'] >= 80: score_color = "#FF4500" # SSS
            elif eval_data['total'] >= 70: score_color = "#FF7F50" # SS
            elif eval_data['total'] >= 60: score_color = "#1E90FF" # S
            elif eval_data['total'] >= 50: score_color = "#32CD32" # A
            
            html += f"└ <b><span style='color:{score_color}'>Total Score: {eval_data['total']:.2f}</span></b><br>"
            html += f"&nbsp;&nbsp;Recommendation: {eval_data['recommendation']}<br><br>"
        
        html += f"<hr>"
        html += f"<b>Average Scores ({calculated_count} echoes)</b><br>"
        
        # Display averages for enabled methods only
        for method in ["normalized", "ratio", "roll", "effective", "cv"]:
            if enabled_methods.get(method, False) and method in total_scores:
                avg = total_scores[method] / calculated_count
                label = method_labels.get(method, method)
                html += f"├ {label} Average: {avg:.2f}<br>"
        
        avg_total = total_scores["total"] / calculated_count
        avg_rating = self.get_score_rating(avg_total)
        avg_rating_text = TRANSLATIONS.get(self.app.language, TRANSLATIONS["en"])[avg_rating]
        avg_color = self._get_rating_color(avg_rating_text)
        
        html += f"└ <b><span style='color:{avg_color}'>Total Average: {avg_total:.2f}</span></b><br>"
        html += f"<span style='color:{avg_color}'>Overall Rating: {avg_rating_text}</span><br>"
        
        return html