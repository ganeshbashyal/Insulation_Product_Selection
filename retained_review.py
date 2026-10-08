def validate_decision(decision, rationale):
    if not isinstance(decision, str):
        raise ValueError('Decision must be a string')
    if decision not in ['retained_confirmed', 'needs_information', 'rejected']:
        raise ValueError('Decision must be one of retained_confirmed, needs_information, rejected')
    if not isinstance(rationale, str) or not 10 <= len(rationale.strip()) <= 10000:
        raise ValueError('Rationale must be a string between 10 and 10000 characters')
    return decision
