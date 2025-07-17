"""
Query processing service for parsing natural language queries
"""
import re
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import spacy
from datetime import datetime, timedelta

from src.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class ParsedQuery:
    original_query: str
    entities: Dict[str, Any]
    intent: str
    confidence: float
    normalized_query: str

class QueryProcessor:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.warning("spaCy model not found. Using fallback processing.")
            self.nlp = None
        
        # Insurance-specific entity patterns
        self.patterns = {
            'age': [
                r'(\d{1,2})\s*(?:year|yr|y\.o\.?|years?)\s*old',
                r'age\s*(?:of\s*)?(\d{1,2})',
                r'(\d{1,2})\s*(?:male|female|M|F)',
            ],
            'gender': [
                r'\b(?:male|man|M)\b',
                r'\b(?:female|woman|F)\b'
            ],
            'procedure': [
                r'knee\s+surgery',
                r'heart\s+surgery',
                r'surgery',
                r'operation',
                r'procedure',
                r'treatment',
                r'transplant',
                r'dialysis',
                r'chemotherapy'
            ],
            'location': [
                r'\b(Mumbai|Delhi|Bangalore|Chennai|Kolkata|Hyderabad|Pune|Ahmedabad)\b',
                r'\b\w+(?:\s+\w+)*(?:\s+city)?\b'
            ],
            'policy_duration': [
                r'(\d+)\s*(?:month|mon|months?)\s*(?:old\s*)?policy',
                r'(\d+)\s*(?:year|yr|years?)\s*(?:old\s*)?policy',
                r'policy\s*(?:of\s*)?(\d+)\s*(?:month|year)',
            ],
            'amount': [
                r'₹\s*(\d+(?:,\d+)*)',
                r'rs\.?\s*(\d+(?:,\d+)*)',
                r'rupees?\s*(\d+(?:,\d+)*)'
            ]
        }
    
    async def parse_query(self, query: str) -> ParsedQuery:
        """Parse natural language query and extract entities"""
        
        # Normalize query
        normalized_query = self._normalize_query(query)
        
        # Extract entities
        entities = await self._extract_entities(normalized_query)
        
        # Determine intent
        intent = self._classify_intent(normalized_query)
        
        # Calculate confidence
        confidence = self._calculate_confidence(normalized_query, entities)
        
        return ParsedQuery(
            original_query=query,
            entities=entities,
            intent=intent,
            confidence=confidence,
            normalized_query=normalized_query
        )
    
    def _normalize_query(self, query: str) -> str:
        """Normalize query text"""
        # Convert to lowercase
        query = query.lower()
        
        # Remove extra whitespace
        query = re.sub(r'\s+', ' ', query).strip()
        
        # Expand common abbreviations
        abbreviations = {
            'yrs': 'years',
            'yr': 'year',
            'mos': 'months',
            'mo': 'month',
            'hrs': 'hours',
            'hr': 'hour',
            'mins': 'minutes',
            'min': 'minute'
        }
        
        for abbr, full in abbreviations.items():
            query = re.sub(r'\b' + abbr + r'\b', full, query)
        
        return query
    
    async def _extract_entities(self, query: str) -> Dict[str, Any]:
        """Extract key entities from query"""
        entities = {}
        
        # Extract age
        age = self._extract_age(query)
        if age:
            entities['age'] = age
        
        # Extract gender
        gender = self._extract_gender(query)
        if gender:
            entities['gender'] = gender
        
        # Extract procedure/condition
        procedure = self._extract_procedure(query)
        if procedure:
            entities['procedure'] = procedure
        
        # Extract location
        location = self._extract_location(query)
        if location:
            entities['location'] = location
        
        # Extract policy duration
        policy_duration = self._extract_policy_duration(query)
        if policy_duration:
            entities['policy_duration'] = policy_duration
        
        # Extract amount
        amount = self._extract_amount(query)
        if amount:
            entities['amount'] = amount
        
        # Use spaCy for additional entity extraction if available
        if self.nlp:
            entities.update(self._extract_spacy_entities(query))
        
        return entities
    
    def _extract_age(self, query: str) -> Optional[int]:
        """Extract age from query"""
        for pattern in self.patterns['age']:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                try:
                    age = int(match.group(1))
                    if 0 <= age <= 120:  # Reasonable age range
                        return age
                except (ValueError, IndexError):
                    continue
        return None
    
    def _extract_gender(self, query: str) -> Optional[str]:
        """Extract gender from query"""
        for pattern in self.patterns['gender']:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                gender_text = match.group(0).lower()
                if gender_text in ['male', 'man', 'm']:
                    return 'male'
                elif gender_text in ['female', 'woman', 'f']:
                    return 'female'
        return None
    
    def _extract_procedure(self, query: str) -> Optional[str]:
        """Extract medical procedure/condition from query"""
        # Define medical terms and procedures
        medical_terms = [
            'knee surgery', 'heart surgery', 'brain surgery', 'eye surgery',
            'cancer', 'diabetes', 'hypertension', 'surgery', 'operation',
            'procedure', 'treatment', 'transplant', 'dialysis', 'chemotherapy',
            'radiotherapy', 'hospitalization', 'admission'
        ]
        
        found_procedures = []
        for term in medical_terms:
            if term.lower() in query.lower():
                found_procedures.append(term)
        
        # Return the most specific/longest match
        if found_procedures:
            return max(found_procedures, key=len)
        
        return None
    
    def _extract_location(self, query: str) -> Optional[str]:
        """Extract location from query"""
        # Major Indian cities
        cities = [
            'mumbai', 'delhi', 'bangalore', 'chennai', 'kolkata', 'hyderabad',
            'pune', 'ahmedabad', 'surat', 'jaipur', 'lucknow', 'kanpur',
            'nagpur', 'indore', 'thane', 'bhopal', 'visakhapatnam', 'pimpri',
            'patna', 'vadodara', 'ghaziabad', 'ludhiana', 'coimbatore'
        ]
        
        query_lower = query.lower()
        for city in cities:
            if city in query_lower:
                return city.title()
        
        # Use spaCy for location extraction if available
        if self.nlp:
            doc = self.nlp(query)
            for ent in doc.ents:
                if ent.label_ == "GPE":  # Geopolitical entity
                    return ent.text
        
        return None
    
    def _extract_policy_duration(self, query: str) -> Optional[Dict[str, Any]]:
        """Extract policy duration from query"""
        for pattern in self.patterns['policy_duration']:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                try:
                    duration = int(match.group(1))
                    
                    # Determine unit (months or years)
                    match_text = match.group(0).lower()
                    if 'year' in match_text or 'yr' in match_text:
                        unit = 'years'
                        months = duration * 12
                    else:
                        unit = 'months'
                        months = duration
                    
                    return {
                        'duration': duration,
                        'unit': unit,
                        'months': months
                    }
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_amount(self, query: str) -> Optional[Dict[str, Any]]:
        """Extract monetary amount from query"""
        for pattern in self.patterns['amount']:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                try:
                    amount_str = match.group(1).replace(',', '')
                    amount = float(amount_str)
                    return {
                        'amount': amount,
                        'currency': 'INR',
                        'formatted': f"₹{amount:,.0f}"
                    }
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_spacy_entities(self, query: str) -> Dict[str, Any]:
        """Extract additional entities using spaCy"""
        entities = {}
        
        try:
            doc = self.nlp(query)
            
            # Extract dates
            dates = [ent.text for ent in doc.ents if ent.label_ == "DATE"]
            if dates:
                entities['dates'] = dates
            
            # Extract organizations
            orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
            if orgs:
                entities['organizations'] = orgs
            
            # Extract money
            money = [ent.text for ent in doc.ents if ent.label_ == "MONEY"]
            if money:
                entities['money_mentions'] = money
                
        except Exception as e:
            logger.warning(f"spaCy entity extraction failed: {e}")
        
        return entities
    
    def _classify_intent(self, query: str) -> str:
        """Classify query intent"""
        query_lower = query.lower()
        
        # Define intent keywords
        intent_keywords = {
            'coverage_verification': ['cover', 'coverage', 'eligible', 'include', 'apply'],
            'claim_processing': ['claim', 'benefit', 'payout', 'reimburse', 'amount'],
            'exclusion_check': ['exclusion', 'exclude', 'not covered', 'exception'],
            'waiting_period_check': ['waiting period', 'wait', 'when', 'delay'],
            'premium_inquiry': ['premium', 'cost', 'price', 'fee', 'charge'],
            'policy_details': ['policy', 'terms', 'condition', 'detail'],
            'general_inquiry': ['what', 'how', 'when', 'where', 'why']
        }
        
        # Score each intent
        intent_scores = {}
        for intent, keywords in intent_keywords.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            if score > 0:
                intent_scores[intent] = score
        
        # Return highest scoring intent
        if intent_scores:
            return max(intent_scores, key=intent_scores.get)
        
        return 'general_inquiry'
    
    def _calculate_confidence(self, query: str, entities: Dict[str, Any]) -> float:
        """Calculate confidence score based on extracted entities and query structure"""
        base_score = 0.5
        
        # Increase confidence for each extracted entity
        entity_bonus = len(entities) * 0.1
        
        # Increase confidence for specific medical terms
        medical_terms = ['surgery', 'treatment', 'condition', 'procedure', 'hospital']
        medical_bonus = sum(0.05 for term in medical_terms if term in query.lower())
        
        # Increase confidence for insurance terms
        insurance_terms = ['policy', 'claim', 'coverage', 'benefit', 'premium']
        insurance_bonus = sum(0.05 for term in insurance_terms if term in query.lower())
        
        # Increase confidence for structured queries
        structure_bonus = 0.0
        if re.search(r'\d+', query):  # Contains numbers
            structure_bonus += 0.1
        if ',' in query:  # Contains multiple pieces of information
            structure_bonus += 0.1
        
        confidence = min(base_score + entity_bonus + medical_bonus + insurance_bonus + structure_bonus, 1.0)
        return round(confidence, 2)
