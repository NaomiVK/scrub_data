import re
import pandas as pd # pandas is used by scrub_pii for pd.isna
import spacy

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
    print("spaCy model en_core_web_sm loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load spaCy model. Some PII detection may be limited. Error: {e}")
    nlp = None

# Regex patterns from the updated process_chatlog.py
POSTAL_CODE_PATTERN = r"[A-Za-z]\s*\d\s*[A-Za-z]\s*[ -]?\s*\d\s*[A-Za-z]\s*\d" # Kept for completeness, though not explicitly tested here
PASSPORT_PATTERN = r"\b([A-Za-z]{2}\s*\d{6})\b"
SIN_PATTERN = r"(\d{3}\s*\d{3}\s*\d{3}|\d{3}\D*\d{3}\D*\d{3})"
PHONE_PATTERN_1 = r"(\+\d{1,2}\s?)?1?\-?\.\s?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
PHONE_PATTERN_2 = r"(?:(?:\+?1\s*(?:[.-]\s*)?)?(?:\(\s*([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9])\s*\)|([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9]))\s*(?:[.-]\s*)?)?([2-9]1[02-9]|[2-9][02-9]1|[2-9][02-9]{2})\s*(?:[.-]\s*)?([0-9]{4})(?:\s*(?:#|x\.?|ext\.?|extension)\s*(\d+))?"
EMAIL_PATTERN = r"([a-zA-Z0-9_\-\.]+)\s*@([\sa-zA-Z0-9_\-\.]+)[\.\,]([a-zA-Z]{1,5})"
DOB_PATTERN = r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\b"
# Regex for detecting PO Box and General Delivery addresses
PO_BOX_PATTERN = r"\b(?:P(?:ost(?:al)?)?\.?\s*O(?:ffice)?\.?\s*Box|General Delivery)\s+\d+\b"
# Regex for detecting common street address formats (updated for alphanumeric street numbers)
ADDRESS_PATTERN = r"\b[A-Za-z0-9]+\s+[A-Za-z0-9\s.-]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd|Crescent|Cres|Court|Ct)\b"
# Pattern to temporarily identify credit card numbers to prevent their accidental scrubbing.
TEMP_CREDIT_CARD_IGNORE_PATTERN = r"\b(?:\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,4}|\d{13,16})\b"


def scrub_pii(text):
    """Remove personally identifiable information from text (with CC protection and new address logic)"""
    if pd.isna(text):
        return text
    
    text = str(text)

    # BEGIN CC IGNORE/RESTORE LOGIC
    cc_matches = []
    def cc_match_replacer(match):
        cc_matches.append(match.group(0))
        return f"@@TEMP_CC_PLACEHOLDER_{len(cc_matches)-1}@@"

    text = re.sub(TEMP_CREDIT_CARD_IGNORE_PATTERN, cc_match_replacer, text, flags=re.IGNORECASE)
    # END CC IGNORE LOGIC (part 1)
    
    # Replace patterns with ***
    text = re.sub(POSTAL_CODE_PATTERN, "***", text, flags=re.IGNORECASE)
    text = re.sub(PASSPORT_PATTERN, "***", text, flags=re.IGNORECASE)
    text = re.sub(SIN_PATTERN, "***", text, flags=re.IGNORECASE)
    text = re.sub(PHONE_PATTERN_1, "***", text, flags=re.IGNORECASE)
    text = re.sub(PHONE_PATTERN_2, "***", text, flags=re.IGNORECASE)
    text = re.sub(EMAIL_PATTERN, "***", text, flags=re.IGNORECASE)
    text = re.sub(DOB_PATTERN, "***", text, flags=re.IGNORECASE)
    text = re.sub(PO_BOX_PATTERN, "***", text, flags=re.IGNORECASE) # New PO Box scrubbing
    text = re.sub(ADDRESS_PATTERN, "***", text, flags=re.IGNORECASE) # Modified Address scrubbing
    
    # Use spaCy to detect and replace person names, organizations, and locations
    if nlp:
        try:
            doc = nlp(text)
            ents_to_scrub = []
            for ent in doc.ents:
                if ent.text.upper() in ["PII", "DOB"] and ent.label_ in ["ORG", "PERSON", "PRODUCT", "WORK_OF_ART", "LAW", "EVENT"]: 
                    pass 
                elif ent.label_ in ["PERSON", "ORG", "GPE", "LOC"]:
                    ents_to_scrub.append(ent)
            
            for ent in reversed(ents_to_scrub):
                text = text[:ent.start_char] + "***" + text[ent.end_char:]
        except Exception as e:
            print(f"spaCy processing error: {e}") 
            pass
    
    # BEGIN CC RESTORE LOGIC (part 2)
    idx = 0
    while True: 
        placeholder_to_find = f"@@TEMP_CC_PLACEHOLDER_{idx}@@"
        if placeholder_to_find in text:
            if idx < len(cc_matches):
                text = text.replace(placeholder_to_find, cc_matches[idx], 1) 
            else:
                text = text.replace(placeholder_to_find, "[UNEXPECTED_CC_PLACEHOLDER]", 1)
            idx += 1
        else:
            break 
    # END CC RESTORE LOGIC

    return text

# Define test data
test_strings = [
    # Street Addresses
    "Visit us at 123 Main Street for more info.",
    "His address is 221B Baker Street, London.",
    "Please send mail to PO Box 12345, Anytown.",
    "Use General Delivery 500 for packages.",
    "She lives at 789 Oak Rd. Apt 10, Smallville.",

    # Credit Card Numbers (to ensure they are NOT scrubbed)
    "My Card is 1234-5678-9012-3456, thanks.",
    "Charge it to Visa 9876543210987654.",
    "AMEX card: 3742-123456-12345.",

    # Personal Names
    "The agent is John Doe.",
    "Prepared for Ms. Alice Wonderland.",

    # Dates of Birth
    "Her birthday is 05/10/1985.",
    "DOB: 1970-01-01.",

    # Emails
    "Contact support@example.com for help.",

    # Phone numbers
    "Call us at (555) 123-4567 or 555.987.6543.",

    # SINs
    "My SIN is 123 456 789.",

    # Passport numbers
    "Passport number: AB123456.",

    # No PII
    "This is a test sentence with no sensitive data.",

    # Combined PII
    "Agent John Smith (j.smith@work.com, born 02/02/1982, SIN 987-654-321) lives at 42 Wallaby Way, Sydney (PO Box 900). His card is 1111-2222-3333-4444 and phone 123-456-7890. Passport: CD789012.",
    "Alice Brown's address is 10 Downing St, Apt 3B, London. DOB: 03/04/1990. Email: alice.b@web.net. Phone: +44 20 7946 0958. Card: Visa 5555666677778888. SIN 111 222 333. Passport GBR123456."
]

# Process and print results
print("\n--- Starting PII Scrubbing Tests (Latest Address Logic, CC Protection) ---")
for i, text in enumerate(test_strings):
    print(f"\nTest String {i+1}:")
    print(f"Original: {text}")
    scrubbed_text = scrub_pii(text)
    print(f"Scrubbed: {scrubbed_text}")

print("\n--- PII Scrubbing Tests Complete ---")

# Test with NaN value
print("\n--- Testing with NaN ---")
nan_value = float('nan')
print(f"Original: {nan_value}")
scrubbed_nan = scrub_pii(nan_value)
print(f"Scrubbed: {scrubbed_nan}")

# Test with None value
print("\n--- Testing with None ---")
none_value = None
print(f"Original: {none_value}")
scrubbed_none = scrub_pii(none_value)
print(f"Scrubbed: {scrubbed_none}")
