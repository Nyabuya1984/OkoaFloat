"""
Validators - Input validation utilities for the PENZI dating system.
"""
import re


class Validators:
    """Collection of validation methods for user input."""
    
    @staticmethod
    def is_valid_phone(phone_number):
        """Validate a phone number."""
        if not phone_number:
            return False
        
        cleaned = Validators.clean_phone(phone_number)
        
        patterns = [
            r'^07[0-9]{8}$',
            r'^\+2547[0-9]{8}$',
            r'^2547[0-9]{8}$'
        ]
        
        for pattern in patterns:
            if re.match(pattern, cleaned):
                return True
        
        return False
    
    @staticmethod
    def clean_phone(phone_number):
        """Clean a phone number by removing spaces and dashes."""
        if not phone_number:
            return ""
        
        cleaned = re.sub(r'[\s\-\(\)\.]', '', phone_number)
        return cleaned
    
    @staticmethod
    def format_phone(phone_number):
        """Format a phone number to standard format."""
        cleaned = Validators.clean_phone(phone_number)
        
        if cleaned.startswith('+254'):
            cleaned = '0' + cleaned[4:]
        elif cleaned.startswith('254'):
            cleaned = '0' + cleaned[3:]
        
        if len(cleaned) == 10 and cleaned.startswith('07'):
            return cleaned
        
        return cleaned
    
    @staticmethod
    def is_valid_age(age, min_age=18, max_age=100):
        """Validate age is within acceptable range."""
        try:
            age = int(age)
            return min_age <= age <= max_age
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def parse_age_range(age_range):
        """Parse age range string into min and max ages."""
        if not age_range:
            return None
        
        age_range = age_range.replace(' ', '')
        
        if '-' not in age_range:
            return None
        
        try:
            parts = age_range.split('-')
            if len(parts) != 2:
                return None
            
            min_age = int(parts[0])
            max_age = int(parts[1])
            
            if min_age < 18 or max_age > 100 or min_age > max_age:
                return None
            
            return (min_age, max_age)
            
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def is_valid_name(name):
        """Validate a person's name."""
        if not name or len(name.strip()) < 2:
            return False
        
        pattern = r'^[A-Za-z\s\-\']+$'
        
        if not re.match(pattern, name):
            return False
        
        if not re.search(r'[A-Za-z]', name):
            return False
        
        return True
    
    @staticmethod
    def is_valid_gender(gender):
        """Validate gender."""
        valid_genders = ['Male', 'Female', 'Other']
        
        if not gender:
            return False
        
        gender = gender.capitalize()
        return gender in valid_genders
    
    @staticmethod
    def is_valid_location(location):
        """Validate a location name."""
        if not location or len(location.strip()) < 2:
            return False
        
        pattern = r'^[A-Za-z\s\-\']+$'
        return bool(re.match(pattern, location))
    
    @staticmethod
    def is_valid_self_description(description):
        """Validate self-description."""
        if not description:
            return False
        
        if len(description.strip()) < 3:
            return False
        
        if len(description) > 500:
            return False
        
        return True
    
    @staticmethod
    def is_valid_marital_status(status):
        """Validate marital status."""
        valid_statuses = ['Single', 'Married', 'Divorced', 'Widowed', 'Separated']
        
        if not status:
            return False
        
        status = status.capitalize()
        return status in valid_statuses
    
    @staticmethod
    def parse_sms_command(message):
        """
        Parse an SMS command and validate its format.
        
        Returns:
            tuple: (command_type, parsed_data, error_message)
        """
        if not message:
            return ('unknown', None, 'Empty message')
        
        message = message.strip()
        message_lower = message.lower()
        
        # 1. PENZI
        if message_lower == 'penzi':
            return ('penzi', {}, None)
        
        # 2. start#name#age#gender#county#town
        if message_lower.startswith('start#'):
            parts = message.split('#')
            if len(parts) < 6:
                return ('unknown', None, 'Invalid format. Use: start#name#age#gender#county#town')
            
            try:
                data = {
                    'name': parts[1].strip(),
                    'age': int(parts[2]) if parts[2].isdigit() else None,
                    'gender': parts[3].strip().capitalize(),
                    'county': parts[4].strip(),
                    'town': parts[5].strip()
                }
                
                if not Validators.is_valid_name(data['name']):
                    return ('unknown', None, 'Invalid name')
                if not Validators.is_valid_age(data['age']):
                    return ('unknown', None, 'Age must be between 18 and 100')
                if not Validators.is_valid_gender(data['gender']):
                    return ('unknown', None, 'Invalid gender. Use Male, Female, or Other')
                if not Validators.is_valid_location(data['county']):
                    return ('unknown', None, 'Invalid county name')
                if not Validators.is_valid_location(data['town']):
                    return ('unknown', None, 'Invalid town name')
                
                return ('start', data, None)
                
            except (ValueError, IndexError):
                return ('unknown', None, 'Invalid format. Use: start#name#age#gender#county#town')
        
        # 3. details#education#profession#marital#religion#ethnicity
        if message_lower.startswith('details#'):
            parts = message.split('#')
            if len(parts) < 6:
                return ('unknown', None, 'Invalid format. Use: details#education#profession#marital#religion#ethnicity')
            
            data = {
                'education_level': parts[1].strip() if len(parts) > 1 else '',
                'profession': parts[2].strip() if len(parts) > 2 else '',
                'marital_status': parts[3].strip() if len(parts) > 3 else '',
                'religion': parts[4].strip() if len(parts) > 4 else '',
                'ethnicity': parts[5].strip() if len(parts) > 5 else ''
            }
            
            return ('details', data, None)
        
        # 4. MYSELF description
        if message_lower.startswith('myself '):
            description = message[7:].strip()
            if not Validators.is_valid_self_description(description):
                return ('unknown', None, 'Description must be at least 3 characters')
            
            return ('myself', {'description': description}, None)
        
        # 5. match#age#town
        if message_lower.startswith('match#'):
            parts = message.split('#')
            if len(parts) < 3:
                return ('unknown', None, 'Invalid format. Use: match#age#town')
            
            age_range = parts[1].strip()
            location = parts[2].strip()
            
            parsed_age = Validators.parse_age_range(age_range)
            if not parsed_age:
                return ('unknown', None, 'Invalid age range. Use format: min-max (e.g., 26-30)')
            
            if not Validators.is_valid_location(location):
                return ('unknown', None, 'Invalid location')
            
            return ('match', {'age_range': age_range, 'location': location}, None)
        
        # 6. NEXT
        if message_lower == 'next':
            return ('next', {}, None)
        
        # 7. YES/NO
        if message_lower == 'yes':
            return ('yes', {'response': True}, None)
        if message_lower == 'no':
            return ('no', {'response': False}, None)
        
        # 8. DESCRIBE phone
        if message_lower.startswith('describe '):
            phone = message[9:].strip()
            if Validators.is_valid_phone(phone):
                return ('describe', {'phone_number': Validators.format_phone(phone)}, None)
            else:
                return ('unknown', None, 'Invalid phone number format')
        
        # 9. Phone number (more details request)
        if Validators.is_valid_phone(message):
            return ('phone_number', {'phone_number': Validators.format_phone(message)}, None)
        
        return ('unknown', None, 'Unknown command')