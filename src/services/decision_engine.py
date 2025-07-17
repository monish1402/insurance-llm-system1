"""
Decision engine for processing insurance claims and generating structured responses
"""
import re
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from src.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class DecisionResult:
    decision: str  # APPROVED, REJECTED, NEEDS_REVIEW
    amount: float
    justification: Dict[str, Any]
    confidence: float
    processing_details: Dict[str, Any]

class DecisionEngine:
    def __init__(self):
        # Define decision rules and thresholds
        self.waiting_periods = {
            'general': 30,  # days
            'pre_existing': 1095,  # 36 months
            'specific_conditions': 730  # 24 months
        }
        
        self.exclusion_keywords = [
            'excluded', 'not covered', 'exception', 'excluding',
            'except', 'limitation', 'restrict'
        ]
        
        self.benefit_keywords = [
            'covered', 'benefit', 'eligible', 'include',
            'payable', 'reimburs', 'compensat'
        ]
    
    async def make_decision(
        self, 
        query: str, 
        entities: Dict[str, Any], 
        search_results: List[Dict[str, Any]]
    ) -> DecisionResult:
        """Make decision based on query and retrieved documents"""
        
        try:
            # Analyze policy compliance
            compliance_analysis = await self._analyze_policy_compliance(entities, search_results)
            
            # Check waiting periods
            waiting_period_check = await self._check_waiting_periods(entities, search_results)
            
            # Check exclusions
            exclusion_check = await self._check_exclusions(entities, search_results)
            
            # Calculate benefit amount
            benefit_calculation = await self._calculate_benefit_amount(entities, search_results)
            
            # Generate final decision
            decision_result = self._generate_final_decision(
                compliance_analysis,
                waiting_period_check,
                exclusion_check,
                benefit_calculation,
                entities,
                search_results
            )
            
            return decision_result
            
        except Exception as e:
            logger.error(f"Error in decision making: {e}")
            return self._create_error_decision(str(e))
    
    async def _analyze_policy_compliance(
        self, 
        entities: Dict[str, Any], 
        search_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze if the claim complies with policy terms"""
        
        analysis = {
            'policy_active': True,
            'coverage_found': False,
            'conditions_met': [],
            'conditions_failed': [],
            'supporting_clauses': []
        }
        
        procedure = entities.get('procedure', '').lower() if entities.get('procedure') else ''
        
        # Check if procedure is covered
        for result in search_results:
            text_lower = result['text'].lower()
            section_type = result.get('section_type', '')
            
            # Look for procedure in benefit sections
            if section_type in ['benefit', 'coverage'] and procedure:
                if procedure in text_lower or any(proc in text_lower for proc in self._get_procedure_variations(procedure)):
                    analysis['coverage_found'] = True
                    analysis['conditions_met'].append(f"Procedure '{procedure}' found in benefits")
                    analysis['supporting_clauses'].append({
                        'type': 'coverage',
                        'text': result['text'][:200] + '...',
                        'source': result.get('filename', 'Unknown'),
                        'section': section_type
                    })
        
        return analysis
    
    async def _check_waiting_periods(
        self, 
        entities: Dict[str, Any], 
        search_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check waiting period requirements"""
        
        waiting_check = {
            'applicable': False,
            'satisfied': False,
            'required_period': None,
            'current_period': None,
            'details': [],
            'supporting_clauses': []
        }
        
        procedure = entities.get('procedure', '').lower() if entities.get('procedure') else ''
        policy_duration = entities.get('policy_duration', {})
        
        if not policy_duration:
            return waiting_check
        
        current_months = policy_duration.get('months', 0)
        
        # Search for waiting period clauses
        for result in search_results:
            text = result['text']
            text_lower = text.lower()
            
            # Check if this procedure has a waiting period
            if procedure and ('waiting period' in text_lower or 'wait' in text_lower):
                
                # Extract waiting period duration
                period_patterns = [
                    r'(\d+)\s*month[s]?',
                    r'(\d+)\s*year[s]?',
                    r'(\d+)\s*day[s]?'
                ]
                
                for pattern in period_patterns:
                    matches = re.findall(pattern, text_lower)
                    if matches:
                        waiting_check['applicable'] = True
                        
                        # Convert to months
                        duration = int(matches[0])
                        if 'year' in text_lower:
                            required_months = duration * 12
                        elif 'day' in text_lower:
                            required_months = duration / 30.0
                        else:
                            required_months = duration
                        
                        waiting_check['required_period'] = required_months
                        waiting_check['current_period'] = current_months
                        
                        if current_months >= required_months:
                            waiting_check['satisfied'] = True
                            waiting_check['details'].append(
                                f"Waiting period satisfied: {current_months} >= {required_months} months"
                            )
                        else:
                            waiting_check['details'].append(
                                f"Waiting period not satisfied: {current_months} < {required_months} months"
                            )
                        
                        waiting_check['supporting_clauses'].append({
                            'type': 'waiting_period',
                            'text': text[:200] + '...',
                            'source': result.get('filename', 'Unknown'),
                            'required_months': required_months
                        })
                        
                        break
        
        return waiting_check
    
    async def _check_exclusions(
        self, 
        entities: Dict[str, Any], 
        search_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check for exclusions that might apply"""
        
        exclusion_check = {
            'excluded': False,
            'exclusion_reasons': [],
            'applicable_exclusions': [],
            'supporting_clauses': []
        }
        
        procedure = entities.get('procedure', '').lower() if entities.get('procedure') else ''
        age = entities.get('age')
        
        # Check exclusion clauses
        for result in search_results:
            text = result['text']
            text_lower = text.lower()
            section_type = result.get('section_type', '')
            
            if section_type == 'exclusion':
                # Check if procedure is excluded
                if procedure and procedure in text_lower:
                    exclusion_check['excluded'] = True
                    exclusion_check['exclusion_reasons'].append(
                        f"Procedure '{procedure}' found in exclusions"
                    )
                    exclusion_check['supporting_clauses'].append({
                        'type': 'exclusion',
                        'text': text[:200] + '...',
                        'source': result.get('filename', 'Unknown'),
                        'reason': f"Procedure {procedure} excluded"
                    })
                
                # Check age-related exclusions
                if age:
                    age_patterns = [
                        r'above\s+(\d+)\s+years?',
                        r'over\s+(\d+)\s+years?',
                        r'(\d+)\s+years?\s+and\s+above'
                    ]
                    
                    for pattern in age_patterns:
                        matches = re.findall(pattern, text_lower)
                        if matches:
                            exclusion_age = int(matches[0])
                            if age > exclusion_age:
                                exclusion_check['excluded'] = True
                                exclusion_check['exclusion_reasons'].append(
                                    f"Age {age} exceeds exclusion limit of {exclusion_age}"
                                )
        
        return exclusion_check
    
    async def _calculate_benefit_amount(
        self, 
        entities: Dict[str, Any], 
        search_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate benefit amount based on policy terms"""
        
        benefit_calc = {
            'amount': 0.0,
            'currency': 'INR',
            'calculation_basis': 'sum_insured',
            'sub_limits': [],
            'deductions': [],
            'supporting_clauses': []
        }
        
        procedure = entities.get('procedure', '').lower() if entities.get('procedure') else ''
        
        # Look for benefit amounts and sub-limits
        for result in search_results:
            text = result['text']
            section_type = result.get('section_type', '')
            
            if section_type in ['benefit', 'limitation', 'financial']:
                # Extract monetary amounts
                amount_patterns = [
                    r'₹\s*(\d+(?:,\d+)*(?:\.\d+)?)',
                    r'rs\.?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
                    r'rupees?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
                    r'inr\s*(\d+(?:,\d+)*(?:\.\d+)?)',
                    r'(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:rupees?|rs\.?|₹)'
                ]
                
                for pattern in amount_patterns:
                    matches = re.findall(pattern, text.lower())
                    if matches:
                        for amount_str in matches:
                            try:
                                amount = float(amount_str.replace(',', ''))
                                
                                # Check if this amount applies to the procedure
                                if not procedure or procedure in text.lower():
                                    if amount > benefit_calc['amount']:
                                        benefit_calc['amount'] = amount
                                    
                                    benefit_calc['sub_limits'].append({
                                        'procedure': procedure or 'general',
                                        'limit': amount,
                                        'source': result.get('filename', 'Unknown'),
                                        'section': section_type
                                    })
                                    
                                    benefit_calc['supporting_clauses'].append({
                                        'type': 'benefit_amount',
                                        'text': text[:200] + '...',
                                        'amount': amount,
                                        'source': result.get('filename', 'Unknown')
                                    })
                                    
                            except ValueError:
                                continue
        
        return benefit_calc
    
    def _generate_final_decision(
        self,
        compliance_analysis: Dict[str, Any],
        waiting_period_check: Dict[str, Any],
        exclusion_check: Dict[str, Any],
        benefit_calculation: Dict[str, Any],
        entities: Dict[str, Any],
        search_results: List[Dict[str, Any]]
    ) -> DecisionResult:
        """Generate final decision based on all analyses"""
        
        # Determine decision
        decision = "REJECTED"
        amount = 0.0
        
        if exclusion_check['excluded']:
            decision = "REJECTED"
            primary_reason = "Procedure excluded under policy terms"
        elif waiting_period_check['applicable'] and not waiting_period_check['satisfied']:
            decision = "REJECTED"
            primary_reason = "Waiting period not satisfied"
        elif compliance_analysis['coverage_found']:
            decision = "APPROVED"
            amount = benefit_calculation['amount']
            primary_reason = "Coverage applicable under policy terms"
        elif not compliance_analysis['coverage_found']:
            decision = "REJECTED"
            primary_reason = "Procedure not covered under policy"
        else:
            decision = "NEEDS_REVIEW"
            primary_reason = "Insufficient information for automatic decision"
        
        # Build comprehensive justification
        justification = {
            'primary_reason': primary_reason,
            'decision_factors': {
                'coverage_analysis': compliance_analysis,
                'waiting_period_check': waiting_period_check,
                'exclusion_check': exclusion_check,
                'benefit_calculation': benefit_calculation
            },
            'supporting_evidence': self._compile_supporting_evidence(
                compliance_analysis, waiting_period_check, exclusion_check, benefit_calculation
            ),
            'query_analysis': {
                'extracted_entities': entities,
                'confidence_factors': self._analyze_confidence_factors(entities, search_results)
            }
        }
        
        # Calculate confidence
        confidence = self._calculate_decision_confidence(
            compliance_analysis, waiting_period_check, exclusion_check, search_results
        )
        
        processing_details = {
            'documents_analyzed': len(search_results),
            'relevant_sections_found': len([r for r in search_results if r.get('similarity_score', 0) > 0.7]),
            'decision_timestamp': datetime.utcnow().isoformat()
        }
        
        return DecisionResult(
            decision=decision,
            amount=amount,
            justification=justification,
            confidence=confidence,
            processing_details=processing_details
        )
    
    def _compile_supporting_evidence(
        self,
        compliance_analysis: Dict[str, Any],
        waiting_period_check: Dict[str, Any],
        exclusion_check: Dict[str, Any],
        benefit_calculation: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Compile all supporting evidence from analyses"""
        
        evidence = []
        
        # Add coverage evidence
        evidence.extend(compliance_analysis.get('supporting_clauses', []))
        
        # Add waiting period evidence
        evidence.extend(waiting_period_check.get('supporting_clauses', []))
        
        # Add exclusion evidence
        evidence.extend(exclusion_check.get('supporting_clauses', []))
        
        # Add benefit calculation evidence
        evidence.extend(benefit_calculation.get('supporting_clauses', []))
        
        return evidence
    
    def _analyze_confidence_factors(
        self, 
        entities: Dict[str, Any], 
        search_results: List[Dict[str, Any]]
    ) -> List[str]:
        """Analyze factors that affect decision confidence"""
        
        factors = []
        
        # Entity completeness
        entity_count = len(entities)
        if entity_count >= 3:
            factors.append("Complete entity extraction")
        elif entity_count >= 2:
            factors.append("Partial entity extraction")
        else:
            factors.append("Limited entity extraction")
        
        # Search result quality
        high_similarity_results = len([r for r in search_results if r.get('similarity_score', 0) > 0.8])
        if high_similarity_results >= 3:
            factors.append("High-quality search results")
        elif high_similarity_results >= 1:
            factors.append("Good search results")
        else:
            factors.append("Limited search results")
        
        # Document coverage
        unique_documents = len(set(r.get('filename', '') for r in search_results))
        if unique_documents >= 2:
            factors.append("Multiple document sources")
        else:
            factors.append("Single document source")
        
        return factors
    
    def _calculate_decision_confidence(
        self,
        compliance_analysis: Dict[str, Any],
        waiting_period_check: Dict[str, Any],
        exclusion_check: Dict[str, Any],
        search_results: List[Dict[str, Any]]
    ) -> float:
        """Calculate confidence in the decision"""
        
        base_confidence = 0.6
        
        # Increase confidence for clear exclusions
        if exclusion_check['excluded'] and exclusion_check['supporting_clauses']:
            base_confidence += 0.2
        
        # Increase confidence for clear coverage
        if compliance_analysis['coverage_found'] and compliance_analysis['supporting_clauses']:
            base_confidence += 0.15
        
        # Increase confidence for clear waiting period violations
        if waiting_period_check['applicable'] and not waiting_period_check['satisfied']:
            base_confidence += 0.15
        
        # Increase confidence based on search result quality
        avg_similarity = sum(r.get('similarity_score', 0) for r in search_results) / max(len(search_results), 1)
        if avg_similarity > 0.8:
            base_confidence += 0.1
        elif avg_similarity > 0.6:
            base_confidence += 0.05
        
        return min(base_confidence, 1.0)
    
    def _get_procedure_variations(self, procedure: str) -> List[str]:
        """Get variations of procedure names for better matching"""
        variations = [procedure]
        
        # Common variations
        if 'surgery' in procedure:
            variations.append(procedure.replace('surgery', 'operation'))
            variations.append(procedure.replace('surgery', 'procedure'))
        
        if 'knee' in procedure:
            variations.extend(['knee replacement', 'knee arthroscopy', 'knee joint'])
        
        if 'heart' in procedure:
            variations.extend(['cardiac', 'cardiovascular', 'coronary'])
        
        return variations
    
    def _create_error_decision(self, error_message: str) -> DecisionResult:
        """Create decision result for error cases"""
        return DecisionResult(
            decision="ERROR",
            amount=0.0,
            justification={
                'primary_reason': 'Processing error occurred',
                'error_details': error_message,
                'decision_factors': {},
                'supporting_evidence': [],
                'query_analysis': {}
            },
            confidence=0.0,
            processing_details={
                'error': True,
                'error_message': error_message,
                'decision_timestamp': datetime.utcnow().isoformat()
            }
        )
