"""
Response Templates - All SMS message templates.
"""
from datetime import datetime


class ResponseTemplates:
    """Collection of SMS response templates."""
    
    # ============================================================
    # REGISTRATION RESPONSES
    # ============================================================
    
    def welcome_message(self):
        return ("Welcome to our dating service with 6000 potential dating partners! "
                "To register SMS start#name#age#gender#county#town to 22141. "
                "E.g., start#John Doe#26#Male#Nakuru#Naivasha")
    
    def registration_success(self, name):
        return (f"Your profile has been created successfully {name}. "
                "SMS details#levelOfEducation#profession#maritalStatus#religion#ethnicity to 22141. "
                "E.g. details#diploma#driver#single#christian#mijikenda")
    
    def already_registered(self, name):
        return (f"Hi {name}, you are already registered. "
                "To search for a MPENZI, SMS match#age#town to 22141")
    
    def continue_registration(self):
        return ("Please complete your registration. "
                "SMS details#levelOfEducation#profession#maritalStatus#religion#ethnicity to 22141.")
    
    def already_complete(self):
        return "Your profile is already complete. To search for a MPENZI, SMS match#age#town to 22141."
    
    def not_registered(self):
        return "You are not registered. Please SMS PENZI to start registration."
    
    def incomplete_registration(self):
        return "Please complete your registration first. SMS details#... and MYSELF ..."
    
    # ============================================================
    # DETAILS REGISTRATION RESPONSES
    # ============================================================
    
    def details_success(self):
        return ("This is the last stage of registration. "
                "SMS a brief description of yourself to 22141 starting with the word MYSELF. "
                "E.g., MYSELF chocolate, lovely, sexy etc.")
    
    def details_required(self):
        return ("Please provide your details first. "
                "SMS details#levelOfEducation#profession#maritalStatus#religion#ethnicity to 22141.")
    
    # ============================================================
    # SELF-DESCRIPTION RESPONSES
    # ============================================================
    
    def registration_complete(self):
        return ("You are now registered for dating. "
                "To search for a MPENZI, SMS match#age#town to 22141 and meet the person of your dreams. "
                "E.g., match#23-25#Kisumu")
    
    def no_description(self):
        return "This person hasn't added a self-description yet."
    
    # ============================================================
    # MATCH RESPONSES
    # ============================================================
    
    def no_matches(self):
        return ("Sorry, we couldn't find any matches with those criteria. "
                "Try a different age range or location. SMS match#age#town to 22141")
    
    def match_results(self, matches, total, batch_number):
        gender_label = 'ladies' if matches and matches[0].get('gender') == 'Female' else 'men'
        singular = 'lady' if gender_label == 'ladies' else 'man'
        
        result = (f"We have {total} {gender_label} who match your choice! "
                  f"We will send you details of 3 of them shortly. "
                  f"To get more details about a {singular}, "
                  f"SMS their number e.g., 0722010203 to 22141\n\n")
        
        for match in matches[:3]:
            result += f"{match.get('full_name', 'Unknown')} aged {match.get('age', '?')}, {match.get('phone_number', 'N/A')}.\n"
        
        remaining = total - 3
        if remaining > 0:
            result += f"\nSend NEXT to 22141 to receive details of the remaining {remaining} {gender_label}"
        
        return result
    
    def next_batch_results(self, matches, remaining):
        if not matches:
            return "No more matches available. Try a new search with match#age#town to 22141"
        
        result = ""
        for match in matches:
            result += f"{match.get('full_name', 'Unknown')} aged {match.get('age', '?')}, {match.get('phone_number', 'N/A')}.\n"
        
        if remaining > 0:
            result += f"\nSend NEXT to 22141 to receive details of the remaining {remaining} matches"
        else:
            result += "\nNo more matches available. Try a new search with match#age#town to 22141"
        
        return result
    
    def no_more_matches(self):
        return "No more matches available. Try a new search with match#age#town to 22141"
    
    # ============================================================
    # PROFILE DETAILS RESPONSES
    # ============================================================
    
    def profile_details(self, user):
        fields = [
            ('full_name', 'Full Name'),
            ('age', 'Age'),
            ('county', 'County'),
            ('town', 'Town'),
            ('education_level', 'Education'),
            ('profession', 'Profession'),
            ('marital_status', 'Marital Status'),
            ('religion', 'Religion'),
            ('ethnicity', 'Ethnicity')
        ]
        
        parts = []
        for attr, label in fields:
            value = getattr(user, attr, None)
            if value:
                if attr in ['county', 'town'] and hasattr(value, 'county_name'):
                    parts.append(f"{label}: {value.county_name}")
                elif attr in ['county', 'town'] and hasattr(value, 'town_name'):
                    parts.append(f"{label}: {value.town_name}")
                elif value:
                    parts.append(f"{label}: {value}")
        
        if not parts:
            return f"{user.full_name} - No additional details available."
        
        result = " | ".join(parts)
        result += f"\n\nSend DESCRIBE {user.phone_number} to get more details about {user.full_name}."
        
        return result
    
    def self_description(self, name, description):
        return f"{name} describes themselves as: {description}"
    
    # ============================================================
    # CONSENT RESPONSES
    # ============================================================
    
    def consent_request_sent(self, target):
        return (f"Your request has been sent to {target.full_name}. "
                "We will notify you when they respond.")
    
    def consent_accepted(self, target, requester):
        # Build requester details
        parts = []
        fields = [
            ('full_name', 'Full Name'),
            ('age', 'Age'),
            ('county', 'County'),
            ('town', 'Town'),
            ('education_level', 'Education'),
            ('profession', 'Profession'),
            ('marital_status', 'Marital Status'),
            ('religion', 'Religion'),
            ('ethnicity', 'Ethnicity')
        ]
        
        for attr, label in fields:
            value = getattr(requester, attr, None)
            if value:
                if attr in ['county', 'town'] and hasattr(value, 'county_name'):
                    parts.append(f"{label}: {value.county_name}")
                elif attr in ['county', 'town'] and hasattr(value, 'town_name'):
                    parts.append(f"{label}: {value.town_name}")
                elif value:
                    parts.append(f"{label}: {value}")
        
        result = " | ".join(parts) if parts else f"{requester.full_name} - No additional details."
        result += f"\n\nSend DESCRIBE {requester.phone_number} to get more details about {requester.full_name}."
        
        return result
    
    def consent_denied(self):
        return "You have declined to share your details. The requester will not see your profile."
    
    def no_pending_consent(self):
        return "You don't have any pending consent requests."
    
    def no_consent(self):
        return "You don't have permission to view this person's description. They must first give consent."
    
    # ============================================================
    # VALIDATION & ERROR RESPONSES
    # ============================================================
    
    def validation_error(self, errors):
        if isinstance(errors, str):
            return f"Validation error: {errors}"
        elif isinstance(errors, list):
            return f"Validation error: {', '.join(errors)}"
        return "Validation error. Please check your input and try again."
    
    def unknown_command(self):
        return ("Unknown command. Please use one of: "
                "PENZI, start#..., details#..., MYSELF ..., match#..., NEXT, "
                "DESCRIBE [phone], [phone number], or YES/NO")
    
    def error_processing(self):
        return "Sorry, there was an error processing your request. Please try again."
    
    def error_registration(self):
        return ("Error registering. Please check your format: "
                "start#name#age#gender#county#town")
    
    def error_details(self):
        return ("Error updating details. Please check your format: "
                "details#education#profession#marital#religion#ethnicity")
    
    def error_description(self):
        return "Error saving description. Please use: MYSELF [your description]"
    
    def error_match(self):
        return "Error finding matches. Please check your format: match#age#town"
    
    def error_consent(self):
        return "Error processing consent. Please try again with YES or NO."
    
    # ============================================================
    # USER NOT FOUND RESPONSES
    # ============================================================
    
    def user_not_found(self):
        return "Phone number not found in our system."
    
    def invalid_match(self):
        return "This person is not in your match list. Please search for matches first with match#age#town"