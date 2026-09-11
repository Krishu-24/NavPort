"""Lightweight regex-based NLP: METAR decoding, briefing summaries, risk scoring."""

import logging
import re
from typing import Dict, List


class SimpleNLPProcessor:
    """Simple NLP processor using regex patterns and basic text analysis."""

    def __init__(self):
        self.metar_patterns = {
            'airport': r'\b([A-Z]{4})\b',
            'time': r'(\d{6}Z)',
            'wind': r'(\d{3})(\d{2,3})(G\d{2,3})?KT',
            'visibility': r'(\d+)SM|(\d{4})\s',
            'weather': r'([-+]?(?:TS|RA|SN|FG|BR|DZ|IC|PL|GR))',
            'clouds': r'(FEW|SCT|BKN|OVC)(\d{3})',
            'temperature': r'(\d{2}|M\d{2})/(\d{2}|M\d{2})',
        }

        self.weather_descriptions = {
            'RA': 'rain', 'SN': 'snow', 'FG': 'fog', 'BR': 'mist',
            'TS': 'thunderstorm', 'DZ': 'drizzle', 'IC': 'ice crystals',
            'PL': 'ice pellets', 'GR': 'hail', '+': 'heavy', '-': 'light',
        }

    def decode_metar_to_natural_language(self, metar_text: str) -> str:
        """Convert METAR code to simple natural language description using regex."""
        try:
            decoded_parts = []

            airport_match = re.search(self.metar_patterns['airport'], metar_text)
            if airport_match:
                decoded_parts.append(f"Airport: {airport_match.group(1)}")

            time_match = re.search(self.metar_patterns['time'], metar_text)
            if time_match:
                time_str = time_match.group(1)
                day = time_str[:2]
                hour = time_str[2:4]
                minute = time_str[4:6]
                decoded_parts.append(f"Observed on day {day} at {hour}:{minute} UTC")

            wind_match = re.search(self.metar_patterns['wind'], metar_text)
            if wind_match:
                direction = wind_match.group(1)
                speed = wind_match.group(2)
                gust = wind_match.group(3)
                wind_desc = f"Wind from {direction} degrees at {speed} knots"
                if gust:
                    wind_desc += f" gusting to {gust[1:]} knots"
                decoded_parts.append(wind_desc)

            vis_match = re.search(self.metar_patterns['visibility'], metar_text)
            if vis_match:
                if vis_match.group(1):
                    decoded_parts.append(f"Visibility {vis_match.group(1)} statute miles")
                elif vis_match.group(2):
                    vis_meters = int(vis_match.group(2))
                    if vis_meters >= 9999:
                        decoded_parts.append("Visibility greater than 10 kilometers")
                    else:
                        decoded_parts.append(f"Visibility {vis_meters} meters")

            weather_matches = re.findall(self.metar_patterns['weather'], metar_text)
            if weather_matches:
                weather_conditions = []
                for match in weather_matches:
                    for code, description in self.weather_descriptions.items():
                        if code in match:
                            weather_conditions.append(description)
                if weather_conditions:
                    decoded_parts.append(f"Weather: {', '.join(set(weather_conditions))}")

            cloud_matches = re.findall(self.metar_patterns['clouds'], metar_text)
            if cloud_matches:
                cloud_desc = []
                cloud_types = {'FEW': 'few', 'SCT': 'scattered', 'BKN': 'broken', 'OVC': 'overcast'}
                for coverage, height in cloud_matches:
                    altitude = int(height) * 100
                    cloud_desc.append(f"{cloud_types[coverage]} clouds at {altitude} feet")
                decoded_parts.append(f"Clouds: {', '.join(cloud_desc)}")

            temp_match = re.search(self.metar_patterns['temperature'], metar_text)
            if temp_match:
                temp = temp_match.group(1).replace('M', '-')
                dew = temp_match.group(2).replace('M', '-')
                decoded_parts.append(f"Temperature {temp}°C, dew point {dew}°C")

            return ". ".join(decoded_parts) + "." if decoded_parts else f"Weather conditions reported: {metar_text}"

        except Exception as e:
            logging.error(f"Error decoding METAR: {e}")
            return f"Weather conditions reported: {metar_text}"

    def summarize_weather_briefing(self, weather_data: Dict) -> str:
        """Create natural language summary of weather briefing."""
        try:
            summary_parts = []

            metars = weather_data.get('metars', [])
            if metars:
                total_stations = len(metars)
                clear_count = sum(1 for m in metars if m.get('category') == 'Clear')
                significant_count = sum(1 for m in metars if m.get('category') == 'Significant')
                severe_count = sum(1 for m in metars if m.get('category') == 'Severe')

                if severe_count > 0:
                    summary_parts.append(f"WEATHER ALERT: {severe_count} stations report severe weather conditions.")
                elif significant_count > total_stations * 0.3:
                    summary_parts.append(f"CAUTION: {significant_count} of {total_stations} stations report significant weather.")
                else:
                    summary_parts.append(f"Generally favorable conditions along route with {clear_count} stations reporting clear weather.")

            notams = weather_data.get('notams', [])
            if notams:
                severe_notams = [n for n in notams if n.get('severity') == 'Severe']
                if severe_notams:
                    summary_parts.append(f"CRITICAL: {len(severe_notams)} severe NOTAMs require immediate attention.")
                else:
                    summary_parts.append(f"{len(notams)} NOTAMs along route - review for operational impact.")

            pireps = weather_data.get('pireps', [])
            if pireps:
                summary_parts.append(f"{len(pireps)} pilot reports available providing real-time conditions.")

            sigmets = weather_data.get('sigmets', [])
            gairmets = weather_data.get('gairmets', [])
            if sigmets or gairmets:
                total_warnings = len(sigmets) + len(gairmets)
                summary_parts.append(f"{total_warnings} weather advisories active in area.")

            if not summary_parts:
                return "Weather briefing: Minimal weather information available for route analysis."

            return " ".join(summary_parts)

        except Exception as e:
            logging.error(f"Error creating weather summary: {e}")
            return "Weather briefing summary unavailable due to processing error."

    def extract_flight_plan_from_text(self, text: str) -> Dict:
        """Extract flight plan information from natural language text using regex."""
        flight_plan = {
            'departure': None,
            'destination': None,
            'waypoints': [],
            'cruise_speed': 450,
            'departure_time': None,
        }
        try:
            icao_pattern = r'\b[A-Z]{4}\b'
            airports = re.findall(icao_pattern, text.upper())

            if len(airports) >= 2:
                flight_plan['departure'] = airports[0]
                flight_plan['destination'] = airports[-1]
                if len(airports) > 2:
                    flight_plan['waypoints'] = airports[1:-1]

            speed_patterns = [
                r'(\d{3,4})\s*(?:knots?|kts?|kt)',
                r'(?:speed|cruise)\s*(?:of\s*)?(\d{3,4})',
                r'(\d{3,4})\s*mph',
            ]

            for pattern in speed_patterns:
                speed_match = re.search(pattern, text.lower())
                if speed_match:
                    flight_plan['cruise_speed'] = int(speed_match.group(1))
                    break

            time_patterns = [
                r'(?:at\s*)?(\d{1,2}):(\d{2})\s*(?:am|pm|utc|z)?',
                r'(?:at\s*)?(\d{4})z',
                r'(?:at\s*)?(\d{1,2})\s*(?:am|pm|o\'?clock)',
                r'(?:tomorrow|today|yesterday)\s*(?:at\s*)?(\d{1,2}):?(\d{2})?',
            ]

            for pattern in time_patterns:
                time_match = re.search(pattern, text.lower())
                if time_match:
                    flight_plan['departure_time'] = time_match.group(0)
                    break

            return flight_plan

        except Exception as e:
            logging.error(f"Error extracting flight plan: {e}")
            return flight_plan

    def generate_risk_assessment(self, timeline: List[Dict]) -> Dict:
        """Generate automated risk assessment with scoring."""
        try:
            severity_scores = {'Clear': 1, 'Significant': 3, 'Severe': 5}

            total_score = 0
            max_possible_score = len(timeline) * 5

            severe_segments = 0
            significant_segments = 0

            for segment in timeline:
                severity = segment.get('severity', 'Clear')
                score = severity_scores.get(severity, 1)
                total_score += score

                if severity == 'Severe':
                    severe_segments += 1
                elif severity == 'Significant':
                    significant_segments += 1

            risk_percentage = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0

            if risk_percentage >= 70:
                risk_level = "HIGH RISK"
                recommendation = "Consider postponing flight or selecting alternate route"
            elif risk_percentage >= 40:
                risk_level = "MODERATE RISK"
                recommendation = "Monitor conditions closely and prepare contingency plans"
            else:
                risk_level = "LOW RISK"
                recommendation = "Conditions acceptable for flight operations"

            return {
                'risk_level': risk_level,
                'risk_percentage': round(risk_percentage, 1),
                'recommendation': recommendation,
                'severe_segments': severe_segments,
                'significant_segments': significant_segments,
                'total_segments': len(timeline),
            }

        except Exception as e:
            logging.error(f"Error generating risk assessment: {e}")
            return {
                'risk_level': 'UNKNOWN',
                'risk_percentage': 0,
                'recommendation': 'Unable to assess risk due to processing error',
                'severe_segments': 0,
                'significant_segments': 0,
                'total_segments': 0,
            }
