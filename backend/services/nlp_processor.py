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
            identifiers = self._extract_identifiers(text)

            # Positional cues win when the sentence actually states them, since
            # "KLAX to KJFK" and "KJFK to KLAX" contain the same two codes in
            # the same order but mean opposite routes.
            keyed = self._identifiers_by_keyword(text, identifiers)

            departure = keyed.get('from')
            destination = keyed.get('to')
            waypoints = keyed.get('via', [])

            # Fall back to reading order for bare input like "KJFK KORD KLAX".
            remaining = [i for i in identifiers
                         if i != departure and i != destination and i not in waypoints]
            if departure is None and remaining:
                departure = remaining.pop(0)
            if destination is None and remaining:
                destination = remaining.pop()
            waypoints = waypoints + remaining

            if departure and destination:
                flight_plan['departure'] = departure
                flight_plan['destination'] = destination
                flight_plan['waypoints'] = waypoints

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

    # ------------------------------------------------------------------ #
    # Identifier extraction
    # ------------------------------------------------------------------ #

    # Plenty of ordinary English words are four letters long, and a bare
    # `\b[A-Z]{4}\b` happily reads "fly FROM KJFK to KLAX" as a route starting
    # at an airport called FROM. Two filters run in order: drop the words that
    # show up in route phrasing, then keep only what the bundled airport
    # database actually recognises.
    _STOPWORDS = frozenset(["FROM", "INTO", "ONTO", "OVER", "THEN", "WITH", "WILL", "THIS", "THAT", "ARE", "FLY", "VIA", "AND", "THE", "FOR", "PLAN", "ROUTE", "LEGS", "STOP", "KNOT", "KNOTS", "MPH", "TRIP", "HEAD", "EAST", "WEST", "NORT", "SOUT", "TIME", "DATE", "HOUR", "MINS", "TODA", "ZULU", "LAND", "TAKE", "OFF", "DEPA", "DEST", "GOING", "NEXT", "LEAVE", "ABOUT", "AFTER", "JUST", "NEED", "WANT", "SHOW", "GIVE", "TELL", "FIND", "WHAT", "WHEN", "SPEED", "CRUISE", "ALSO", "ONLY", "SOME", "EACH", "BEEN", "HAVE", "DOES", "CANT", "WONT"])

    def _extract_identifiers(self, text: str) -> List[str]:
        """Every plausible ICAO code in `text`, in the order it appears.

        Validating against the airport database is what makes this reliable:
        an unknown four-letter token is far more likely to be an English word
        than an airport nobody has heard of.
        """
        from backend.services import airports

        found = []
        for token in re.findall(r'\b[A-Z][A-Z0-9]{3}\b', text.upper()):
            if token in self._STOPWORDS or token in found:
                continue
            if airports.lookup(token) is None:
                continue
            found.append(token)

        return found

    def _identifiers_by_keyword(self, text: str, identifiers: List[str]) -> Dict:
        """Map 'from'/'to'/'via' onto the identifier each one introduces.

        Only the first code after a keyword is taken, except for `via`, which
        collects every code up to the next keyword so "via KORD KDEN" works.
        """
        if not identifiers:
            return {}

        keywords = {'from': 'from', 'to': 'to', 'via': 'via',
                    'through': 'via', 'through to': 'via', 'towards': 'to',
                    'into': 'to', 'departing': 'from', 'out of': 'from'}

        # Tokenise once, keeping the identifiers recognisable among the words.
        tokens = re.findall(r"[A-Za-z0-9']+", text)
        allowed = set(identifiers)

        result: Dict = {}
        active = None

        for token in tokens:
            lowered = token.lower()
            upper = token.upper()

            if lowered in keywords:
                active = keywords[lowered]
                continue

            if upper not in allowed:
                continue

            if active == 'via':
                result.setdefault('via', []).append(upper)
                allowed.discard(upper)
            elif active in ('from', 'to') and active not in result:
                result[active] = upper
                allowed.discard(upper)
                active = None

        return result

    # Per-interval severity comes from WeatherProcessor.categorize_weather:
    #   Severe       thunderstorms, hail, squalls, gusts >= 35 kt, visibility
    #                under 1 SM, ceiling under 500 ft, or an active TFR/SIGMET
    #   Significant  precipitation, fog, winds >= 25 kt, visibility under 3 SM,
    #                ceiling under 1000 ft
    #   Clear        everything else
    #
    # Clear is worth nothing rather than 1. Giving it a weight meant a route
    # that was clear end to end still scored 20%, so the gauge could never
    # read zero and the entire usable range was squeezed into 20-100.
    SEVERITY_WEIGHTS = {'Clear': 0, 'Significant': 2, 'Severe': 5}

    def generate_risk_assessment(self, timeline: List[Dict]) -> Dict:
        """Score a route: how much bad weather, and how bad the worst of it is."""
        try:
            intervals = len(timeline)
            severe_segments = 0
            significant_segments = 0
            total_score = 0

            for segment in timeline:
                severity = segment.get('severity', 'Clear')
                total_score += self.SEVERITY_WEIGHTS.get(severity, 0)

                if severity == 'Severe':
                    severe_segments += 1
                elif severity == 'Significant':
                    significant_segments += 1

            max_possible_score = intervals * 5
            # How much of the route is affected, weighted by how badly. This is
            # an exposure figure, not the verdict — see below.
            risk_percentage = (total_score / max_possible_score) * 100 if max_possible_score else 0

            severe_share = severe_segments / intervals if intervals else 0
            significant_share = significant_segments / intervals if intervals else 0

            # The verdict is set by the worst conditions on the route, not by
            # the average of it. Averaging alone is what let a route with
            # embedded thunderstorms report "LOW RISK - conditions acceptable
            # for flight operations": nine clear intervals either side of one
            # severe one pulled the mean to 31%, under the 40% threshold, while
            # the summary directly above it read "OUTLOOK: Severe". A pilot
            # reads a briefing the other way round. The worst thing on the
            # route is the story; how much of the route it covers decides how
            # much of a problem it is.
            if severe_segments >= 3 or severe_share >= 0.25 or risk_percentage >= 70:
                risk_level = "HIGH RISK"
                recommendation = "Consider postponing flight or selecting alternate route"
            elif severe_segments or significant_share >= 0.34 or risk_percentage >= 40:
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
                'total_segments': intervals,
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
